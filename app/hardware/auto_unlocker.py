"""
Auto Unlock Engine — One-Click FRP & Lock Screen Bypass Tool.

Automatically detects device connection mode (ADB / Fastboot / EDL / Recovery)
and runs the appropriate bypass method without manual intervention.

Features:
    - USB device auto-detection with continuous monitoring
    - ADB mode: FRP bypass + screen lock removal (non-destructive first)
    - Fastboot mode: bootloader unlock + partition erase
    - EDL 9008 mode: firehose-based FRP partition wipe
    - Recovery mode: factory reset via sideload/commands
    - One-click operation — no manual steps needed
    - Real-time progress callbacks with detailed logging

Requires:
    - Android Platform Tools (adb, fastboot) on PATH
    - pyserial for EDL communication
    - Qualcomm USB drivers for 9008 mode

Usage:
    from app.hardware.auto_unlocker import AutoUnlocker

    unlocker = AutoUnlocker(callback=lambda p, m, l: print(f"{p:.0%} {m}"))
    result = unlocker.detect_and_unlock()
"""

from __future__ import annotations

import logging
import re
import subprocess
import struct
import time
import threading
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Enums & Constants
# ---------------------------------------------------------------------------

class DeviceMode(Enum):
    """Detected device connection mode."""
    NONE = "none"
    ADB_NORMAL = "adb_normal"
    ADB_RECOVERY = "adb_recovery"
    ADB_SIDELOAD = "adb_sideload"
    ADB_UNAUTHORIZED = "adb_unauthorized"
    FASTBOOT = "fastboot"
    EDL_9008 = "edl_9008"


class UnlockAction(Enum):
    """Type of unlock operation performed."""
    FRP_BYPASS = "frp_bypass"
    LOCK_REMOVAL = "lock_removal"
    FULL_UNLOCK = "full_unlock"  # FRP + Lock
    FIRMWARE_FLASH = "firmware_flash"
    FACTORY_RESET = "factory_reset"


ADB_TIMEOUT = 15
FASTBOOT_TIMEOUT = 30
EDL_TIMEOUT = 10
REBOOT_WAIT = 8
MONITOR_INTERVAL = 2  # seconds between USB polls

# Import FRP packages from the main frp_unlocker module
from app.hardware.frp_unlocker import (
    FRP_PACKAGES,
    FRP_BYPASS_INTENTS,
    FRP_DB_COMMANDS,
    FRP_FASTBOOT_PARTITIONS,
)

# Lock files to delete (requires root)
LOCK_FILES = [
    "/data/system/locksettings.db",
    "/data/system/locksettings.db-wal",
    "/data/system/locksettings.db-shm",
    "/data/system/gesture.key",
    "/data/system/password.key",
    "/data/system/gatekeeper.pattern.key",
    "/data/system/gatekeeper.password.key",
    "/data/system/gatekeeper.gesture.key",
]

# Use expanded FRP partition list from frp_unlocker
FRP_PARTITIONS = FRP_FASTBOOT_PARTITIONS

# Qualcomm EDL constants
QUALCOMM_VID_PID = "05C6:9008"


# ---------------------------------------------------------------------------
#  Result Data Classes
# ---------------------------------------------------------------------------

@dataclass
class DeviceInfo:
    """Detected device information."""
    mode: DeviceMode = DeviceMode.NONE
    brand: str = ""
    model: str = ""
    android_version: str = ""
    chipset: str = ""
    serial: str = ""
    has_root: bool = False
    bootloader_unlocked: bool = False
    frp_enabled: bool = False
    screen_locked: bool = False
    lock_type: str = "none"
    edl_port: str = ""


@dataclass
class UnlockResult:
    """Result of an auto-unlock operation."""
    success: bool = False
    device_info: DeviceInfo = field(default_factory=DeviceInfo)
    action: UnlockAction = UnlockAction.FULL_UNLOCK
    methods_tried: List[str] = field(default_factory=list)
    methods_succeeded: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    frp_removed: bool = False
    lock_removed: bool = False
    data_wiped: bool = False
    reboot_required: bool = False
    error: Optional[str] = None
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
#  Low-level Command Helpers
# ---------------------------------------------------------------------------

def _run_cmd(cmd: str, timeout: int = ADB_TIMEOUT) -> Tuple[str, int]:
    """Run a shell command and return (stdout+stderr, return_code)."""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, shell=True, errors="replace",
        )
        combined = r.stdout.strip()
        if r.stderr.strip():
            combined = f"{combined}\n{r.stderr.strip()}" if combined else r.stderr.strip()
        return combined, r.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except FileNotFoundError:
        return "NOT_FOUND", -1
    except Exception as e:
        return str(e), -1


def _adb(cmd: str, timeout: int = ADB_TIMEOUT) -> str:
    """Run ADB command, return stdout."""
    out, _ = _run_cmd(f"adb {cmd}", timeout)
    return out


def _adb_rc(cmd: str, timeout: int = ADB_TIMEOUT) -> Tuple[str, int]:
    """Run ADB command, return (output, return_code)."""
    return _run_cmd(f"adb {cmd}", timeout)


def _shell(cmd: str, timeout: int = ADB_TIMEOUT) -> str:
    """Run adb shell command."""
    return _adb(f'shell "{cmd}"', timeout)


def _shell_rc(cmd: str, timeout: int = ADB_TIMEOUT) -> Tuple[str, int]:
    """Run adb shell command with return code."""
    return _adb_rc(f'shell "{cmd}"', timeout)


def _fastboot(cmd: str, timeout: int = FASTBOOT_TIMEOUT) -> str:
    """Run fastboot command."""
    out, _ = _run_cmd(f"fastboot {cmd}", timeout)
    return out


def _fastboot_rc(cmd: str, timeout: int = FASTBOOT_TIMEOUT) -> Tuple[str, int]:
    """Run fastboot command with return code."""
    return _run_cmd(f"fastboot {cmd}", timeout)


# ---------------------------------------------------------------------------
#  USB Device Detection
# ---------------------------------------------------------------------------

def detect_usb_devices() -> Dict[str, str]:
    """
    Detect connected USB devices relevant to mobile repair.
    Returns dict of {device_type: details}.
    """
    devices = {}

    # Check ADB devices
    adb_out = _adb("devices")
    if adb_out and "ADB_NOT_FOUND" not in adb_out:
        for line in adb_out.splitlines():
            line = line.strip()
            if not line or line.startswith("List") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                serial = parts[0]
                state = parts[1].lower()
                if state == "device":
                    devices["adb"] = f"{serial} (normal)"
                elif state == "recovery":
                    devices["adb_recovery"] = f"{serial} (recovery)"
                elif state == "sideload":
                    devices["adb_sideload"] = f"{serial} (sideload)"
                elif state == "unauthorized":
                    devices["adb_unauthorized"] = f"{serial} (unauthorized)"

    # Check fastboot devices
    fb_out = _fastboot("devices")
    if fb_out and "NOT_FOUND" not in fb_out:
        for line in fb_out.splitlines():
            if line.strip() and "fastboot" in line.lower():
                devices["fastboot"] = line.strip()

    # Check EDL 9008 via Windows WMI
    try:
        wmi_out, _ = _run_cmd(
            'wmic path Win32_PnPEntity where "DeviceID like \'%05C6%9008%\'" '
            'get Caption,DeviceID,Status 2>NUL',
            timeout=10,
        )
        if wmi_out and "9008" in wmi_out:
            devices["edl_9008"] = "Qualcomm HS-USB QDLoader 9008"
    except Exception:
        pass

    # Also check COM ports for 9008
    try:
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            hwid = port.hwid.upper() if port.hwid else ""
            desc = port.description.upper() if port.description else ""
            if "9008" in desc or "05C6" in hwid:
                devices["edl_9008"] = f"{port.device} - {port.description}"
    except Exception:
        pass

    return devices


def find_edl_port() -> Optional[str]:
    """Find the COM port for Qualcomm 9008 EDL mode."""
    try:
        import serial.tools.list_ports
        for port in serial.tools.list_ports.comports():
            hwid = port.hwid.upper() if port.hwid else ""
            desc = port.description.upper() if port.description else ""
            if "9008" in desc or ("05C6" in hwid and "9008" in hwid):
                return port.device
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
#  AutoUnlocker — Main Engine
# ---------------------------------------------------------------------------

class AutoUnlocker:
    """
    Auto-detect device mode and perform one-click FRP/Lock bypass.

    Usage:
        unlocker = AutoUnlocker(callback=my_callback)
        result = unlocker.detect_and_unlock()

    The callback signature is: callback(progress: float, message: str, level: str)
    where level is one of: "info", "success", "warning", "error", "step"
    """

    def __init__(
        self,
        callback: Optional[Callable[[float, str, str], None]] = None,
        auto_reboot: bool = True,
    ):
        self.callback = callback
        self.auto_reboot = auto_reboot
        self._stop = threading.Event()
        self._device = DeviceInfo()

    def stop(self):
        """Signal the unlock process to stop."""
        self._stop.set()

    def _cb(self, pct: float, msg: str, level: str = "info"):
        """Fire progress callback."""
        logger.info("[%3.0f%%] [%s] %s", pct * 100, level, msg)
        if self.callback:
            try:
                self.callback(pct, msg, level)
            except Exception:
                pass

    def _stopped(self) -> bool:
        return self._stop.is_set()

    # ------------------------------------------------------------------
    #  Phase 1: Device Detection
    # ------------------------------------------------------------------

    def detect_device(self) -> DeviceInfo:
        """
        Auto-detect connected device and its mode.
        Returns populated DeviceInfo.
        """
        self._device = DeviceInfo()
        info = self._device

        self._cb(0.02, "Scanning USB ports for devices...", "info")

        devices = detect_usb_devices()

        if not devices:
            self._cb(0.05, "No device detected on USB", "warning")
            return info

        # Priority: EDL > Fastboot > ADB Recovery > ADB Normal
        if "edl_9008" in devices:
            info.mode = DeviceMode.EDL_9008
            info.edl_port = find_edl_port() or ""
            self._cb(0.05, f"EDL 9008 device detected: {devices['edl_9008']}", "success")
            self._detect_edl_info(info)
            return info

        if "fastboot" in devices:
            info.mode = DeviceMode.FASTBOOT
            self._cb(0.05, f"Fastboot device detected: {devices['fastboot']}", "success")
            self._detect_fastboot_info(info)
            return info

        if "adb_recovery" in devices:
            info.mode = DeviceMode.ADB_RECOVERY
            self._cb(0.05, f"ADB Recovery device: {devices['adb_recovery']}", "success")
            self._detect_adb_info(info)
            return info

        if "adb_sideload" in devices:
            info.mode = DeviceMode.ADB_SIDELOAD
            self._cb(0.05, "ADB Sideload mode detected", "success")
            return info

        if "adb" in devices:
            info.mode = DeviceMode.ADB_NORMAL
            self._cb(0.05, f"ADB device detected: {devices['adb']}", "success")
            self._detect_adb_info(info)
            return info

        if "adb_unauthorized" in devices:
            info.mode = DeviceMode.ADB_UNAUTHORIZED
            self._cb(0.05, "Device connected but UNAUTHORIZED — accept USB debug prompt on phone", "warning")
            return info

        return info

    def _detect_adb_info(self, info: DeviceInfo):
        """Populate device info via ADB commands."""
        self._cb(0.08, "Reading device information via ADB...", "info")

        info.brand = _shell("getprop ro.product.brand").strip().lower()
        if not info.brand:
            info.brand = _shell("getprop ro.product.manufacturer").strip().lower()

        info.model = _shell("getprop ro.product.model").strip()
        if not info.model:
            info.model = _shell("getprop ro.product.device").strip()

        info.android_version = _shell("getprop ro.build.version.release").strip()
        info.chipset = _shell("getprop ro.hardware").strip()
        info.serial = _shell("getprop ro.serialno").strip()

        # Root check
        id_out = _shell("id")
        if "uid=0" in id_out:
            info.has_root = True
        else:
            root_out = _adb("root")
            if "already running as root" in root_out or "restarting adbd as root" in root_out:
                info.has_root = True
                time.sleep(1)

        # Bootloader check
        bl = _shell("getprop ro.boot.flash.locked")
        if bl.strip() == "0":
            info.bootloader_unlocked = True
        vb = _shell("getprop ro.boot.verifiedbootstate")
        if vb.strip() == "orange":
            info.bootloader_unlocked = True

        # FRP check
        accounts_raw = _shell("dumpsys account")
        if accounts_raw:
            emails = re.findall(r"Account\s*\{[^}]*name=([^,}]+@[^,}]+)", accounts_raw)
            if emails:
                info.frp_enabled = True

        setup = _shell("settings get secure user_setup_complete")
        provisioned = _shell("settings get global device_provisioned")
        if setup.strip() == "1" and provisioned.strip() == "1" and info.frp_enabled:
            info.frp_enabled = True

        # Screen lock check
        pw_type = _shell("settings get secure lockscreen.password_type")
        try:
            pt = int(pw_type.strip())
            if pt > 65536:
                info.screen_locked = True
                if pt == 327680:
                    info.lock_type = "pattern"
                elif pt == 262144:
                    info.lock_type = "pin"
                elif pt == 393216:
                    info.lock_type = "password"
                else:
                    info.lock_type = "unknown"
        except (ValueError, TypeError):
            pass

        self._cb(0.12, f"Device: {info.brand} {info.model} | Android {info.android_version} | "
                        f"Root: {info.has_root} | FRP: {info.frp_enabled} | Lock: {info.lock_type}", "info")

    def _detect_fastboot_info(self, info: DeviceInfo):
        """Populate device info via fastboot."""
        self._cb(0.08, "Reading device information via Fastboot...", "info")

        fb_all = _fastboot("getvar all")
        for line in fb_all.splitlines():
            line_lower = line.lower()
            if "product" in line_lower:
                info.model = line.split(":")[-1].strip()
            elif "serialno" in line_lower:
                info.serial = line.split(":")[-1].strip()
            elif "unlocked" in line_lower:
                if "yes" in line_lower or "true" in line_lower:
                    info.bootloader_unlocked = True

        self._cb(0.12, f"Fastboot device: {info.model} | BL unlocked: {info.bootloader_unlocked}", "info")

    def _detect_edl_info(self, info: DeviceInfo):
        """Populate device info via EDL/Sahara protocol."""
        self._cb(0.08, f"EDL device on port: {info.edl_port or 'detecting...'}", "info")

    # ------------------------------------------------------------------
    #  Phase 2: Auto Unlock — Main Entry Point
    # ------------------------------------------------------------------

    def detect_and_unlock(self) -> UnlockResult:
        """
        Main entry: detect device mode and perform appropriate unlock.
        This is the one-click operation.
        """
        start_time = time.time()
        result = UnlockResult()
        result.action = UnlockAction.FULL_UNLOCK

        self._cb(0.0, "=== AUTO UNLOCK ENGINE STARTED ===", "info")
        self._cb(0.01, "Detecting device...", "info")

        # Phase 1: Detect
        info = self.detect_device()
        result.device_info = info

        if info.mode == DeviceMode.NONE:
            result.error = (
                "No device detected. Connect device via USB in one of these modes:\n"
                "  - ADB (USB Debugging ON)\n"
                "  - Fastboot (Volume Down + Power)\n"
                "  - EDL 9008 (Test point + USB)\n"
                "  - Recovery mode"
            )
            self._cb(1.0, result.error, "error")
            result.duration_seconds = time.time() - start_time
            return result

        if info.mode == DeviceMode.ADB_UNAUTHORIZED:
            result.error = "Device is unauthorized. Accept the USB debugging prompt on the phone screen."
            self._cb(1.0, result.error, "warning")
            result.duration_seconds = time.time() - start_time
            return result

        self._cb(0.15, f"Device mode: {info.mode.value}", "success")
        result.steps.append(f"Device detected in {info.mode.value} mode")

        if self._stopped():
            result.error = "Operation stopped by user"
            result.duration_seconds = time.time() - start_time
            return result

        # Phase 2: Unlock based on mode
        if info.mode == DeviceMode.ADB_NORMAL:
            self._unlock_via_adb(result)
        elif info.mode == DeviceMode.ADB_RECOVERY:
            self._unlock_via_recovery(result)
        elif info.mode == DeviceMode.FASTBOOT:
            self._unlock_via_fastboot(result)
        elif info.mode == DeviceMode.EDL_9008:
            self._unlock_via_edl(result)
        elif info.mode == DeviceMode.ADB_SIDELOAD:
            self._unlock_via_sideload(result)

        # Final status
        result.duration_seconds = time.time() - start_time
        result.success = result.frp_removed or result.lock_removed or result.data_wiped

        if result.success:
            self._cb(1.0, f"UNLOCK COMPLETE in {result.duration_seconds:.1f}s | "
                          f"FRP: {'removed' if result.frp_removed else 'n/a'} | "
                          f"Lock: {'removed' if result.lock_removed else 'n/a'}", "success")
        else:
            self._cb(1.0, f"Unlock failed after {result.duration_seconds:.1f}s — "
                          f"{result.error or 'all methods exhausted'}", "error")

        return result

    # ------------------------------------------------------------------
    #  Phase 2a: ADB Normal Mode Unlock
    # ------------------------------------------------------------------

    def _unlock_via_adb(self, result: UnlockResult):
        """Full unlock via ADB — FRP + Screen Lock removal."""
        info = result.device_info
        self._cb(0.18, "Starting ADB-based unlock...", "info")

        # --- FRP Removal ---
        if info.frp_enabled:
            self._cb(0.20, "FRP detected — starting FRP bypass...", "warning")
            self._adb_frp_bypass(result)
        else:
            self._cb(0.20, "No FRP detected — skipping FRP bypass", "success")
            result.steps.append("FRP not enabled — skipped")

        if self._stopped():
            return

        # --- Screen Lock Removal ---
        if info.screen_locked:
            self._cb(0.55, f"Screen lock detected ({info.lock_type}) — starting removal...", "warning")
            self._adb_lock_removal(result)
        else:
            self._cb(0.55, "No screen lock detected — skipping", "success")
            result.steps.append("No screen lock — skipped")

        # --- Reboot if needed ---
        if result.reboot_required and self.auto_reboot:
            self._cb(0.95, "Rebooting device...", "info")
            _adb("reboot")
            result.steps.append("Device rebooted")

    def _adb_frp_bypass(self, result: UnlockResult):
        """Try all ADB-based FRP bypass methods using the enhanced 12-method engine."""
        from app.hardware.frp_unlocker import remove_frp as _enhanced_remove_frp

        self._cb(0.22, "Running ENHANCED FRP removal (12 methods)...", "step")

        def frp_callback(pct, msg):
            # Map frp_unlocker progress (0-1) to our range (0.22-0.52)
            mapped_pct = 0.22 + (pct * 0.30)
            self._cb(mapped_pct, msg, "step")

        frp_result = _enhanced_remove_frp(callback=frp_callback)

        # Transfer results
        for step in frp_result.steps_performed:
            result.steps.append(f"  [FRP] {step}")

        result.methods_tried.append(f"Enhanced FRP ({frp_result.methods_tried} methods)")

        if frp_result.success:
            result.frp_removed = True
            result.reboot_required = frp_result.reboot_required
            result.methods_succeeded.append(f"FRP: {frp_result.method_used}")
            self._cb(0.52, f"FRP bypass successful via {frp_result.method_used}", "success")
            return

        self._cb(0.52, f"All {frp_result.methods_tried} FRP methods exhausted", "warning")

    def _frp_fastboot_erase(self, result: UnlockResult):
        """Fallback: Reboot to fastboot and erase FRP partitions."""
        self._cb(0.50, "Rebooting to fastboot for FRP partition erase...", "step")
        result.methods_tried.append("Fastboot FRP Erase")
        result.steps.append("Fastboot FRP partition erase — started")

        # Try reboot to bootloader
        _adb("reboot bootloader")
        result.steps.append("Sent reboot-bootloader command")
        self._cb(0.52, "Waiting for fastboot mode...", "info")
        time.sleep(REBOOT_WAIT)

        # Wait for fastboot with retries
        fb_detected = False
        for i in range(5):
            if self._stopped():
                return
            fb_out = _fastboot("devices")
            if fb_out and "fastboot" in fb_out.lower():
                fb_detected = True
                break
            time.sleep(2)

        if not fb_detected:
            result.steps.append("Fastboot mode not available — skipped")
            return

        result.steps.append("Device in fastboot mode")
        self._cb(0.55, "Erasing FRP partitions...", "step")

        success = False
        for part in FRP_PARTITIONS:
            out, rc = _fastboot_rc(f"erase {part}")
            result.steps.append(f"  fastboot erase {part} (rc={rc})")
            if rc == 0:
                success = True

        if success:
            result.frp_removed = True
            result.reboot_required = True
            result.methods_succeeded.append("Fastboot FRP Erase")
            result.steps.append("FRP partition erase successful")
            self._cb(0.58, "FRP partitions erased — rebooting...", "success")

            if self.auto_reboot:
                _fastboot("reboot")
                result.steps.append("Rebooted from fastboot")

    # ------------------------------------------------------------------
    #  ADB Screen Lock Removal
    # ------------------------------------------------------------------

    def _adb_lock_removal(self, result: UnlockResult):
        """Try all methods to remove screen lock via ADB."""
        methods = [
            ("Locksettings Clear", self._lock_locksettings),
            ("Delete Lock Files", self._lock_delete_files),
            ("InputManager Bypass", self._lock_input_bypass),
        ]

        for i, (name, method) in enumerate(methods):
            if self._stopped():
                return
            pct = 0.58 + (i * 0.10)
            self._cb(pct, f"Lock Method {i+1}: {name}...", "step")
            result.methods_tried.append(name)
            result.steps.append(f"Lock Method {i+1}: {name} — started")

            try:
                success = method(result)
                if success:
                    result.lock_removed = True
                    result.reboot_required = True
                    result.methods_succeeded.append(name)
                    result.steps.append(f"Lock Method {i+1}: {name} — SUCCESS")
                    self._cb(pct + 0.05, f"Lock removed via {name}", "success")
                    return
                else:
                    result.steps.append(f"Lock Method {i+1}: {name} — did not succeed")
            except Exception as e:
                result.steps.append(f"Lock Method {i+1}: {name} — error: {e}")

    def _lock_locksettings(self, result: UnlockResult) -> bool:
        """Method 1: locksettings clear (Android 8+)."""
        sdk_str = _shell("getprop ro.build.version.sdk")
        try:
            sdk = int(sdk_str.strip())
        except (ValueError, TypeError):
            sdk = 0

        if sdk < 26:
            result.steps.append(f"  SDK {sdk} < 26, skipping locksettings")
            return False

        out, rc = _adb_rc("shell locksettings clear")
        result.steps.append(f"  locksettings clear (rc={rc}): {out[:100]}")

        if rc == 0 and "error" not in out.lower():
            _adb_rc("shell locksettings set-disabled true")
            _adb_rc("shell settings put secure lockscreen.password_type 65536")
            result.steps.append("  Lock disabled + password_type reset")
            return True

        # Try with empty old credential
        out2, rc2 = _adb_rc('shell locksettings clear --old ""')
        result.steps.append(f'  locksettings clear --old "" (rc={rc2})')
        if rc2 == 0 and "error" not in out2.lower():
            return True

        return False

    def _lock_delete_files(self, result: UnlockResult) -> bool:
        """Method 2: Delete lock files (requires root)."""
        info = result.device_info
        if not info.has_root:
            result.steps.append("  No root access — skipping file deletion")
            return False

        deleted = 0
        for lock_file in LOCK_FILES:
            check = _shell(f"ls {lock_file} 2>/dev/null")
            if not check or "No such file" in check:
                continue
            out, rc = _adb_rc(f"shell rm -f {lock_file}")
            result.steps.append(f"  Deleted {lock_file} (rc={rc})")
            if rc == 0:
                deleted += 1

        # Reset via sqlite
        _adb_rc('shell sqlite3 /data/system/locksettings.db '
                '"UPDATE locksettings SET value=0 WHERE name=\'lockscreen.password_type\'"')
        result.steps.append("  Reset password_type in locksettings.db")

        return deleted > 0

    def _lock_input_bypass(self, result: UnlockResult) -> bool:
        """Method 3: Try input-based bypass (send key events)."""
        # Disable keyguard
        out, rc = _adb_rc("shell wm dismiss-keyguard")
        result.steps.append(f"  wm dismiss-keyguard (rc={rc})")
        if rc == 0:
            return True

        # Try disabling lock screen via settings
        out2, rc2 = _shell_rc("settings put secure lockscreen.disabled 1")
        result.steps.append(f"  Set lockscreen.disabled=1 (rc={rc2})")

        out3, rc3 = _shell_rc("settings put secure lockscreen.password_type 65536")
        result.steps.append(f"  Set password_type=65536 (rc={rc3})")

        return rc2 == 0 and rc3 == 0

    # ------------------------------------------------------------------
    #  Phase 2b: Recovery Mode Unlock
    # ------------------------------------------------------------------

    def _unlock_via_recovery(self, result: UnlockResult):
        """Unlock via ADB in recovery mode — wipe data."""
        self._cb(0.20, "Device in Recovery mode — attempting wipe...", "info")

        # Try ADB sideload-based wipe
        out, rc = _adb_rc("shell recovery --wipe_data")
        result.steps.append(f"recovery --wipe_data (rc={rc})")
        result.methods_tried.append("Recovery Wipe")

        if rc != 0:
            # Try twrp commands
            out2, rc2 = _adb_rc("shell twrp wipe data")
            result.steps.append(f"twrp wipe data (rc={rc2})")

            if rc2 != 0:
                # Try erasing via shell
                out3, rc3 = _adb_rc("shell wipe data")
                result.steps.append(f"wipe data (rc={rc3})")

        # Try to delete lock files directly in recovery
        self._cb(0.40, "Attempting to delete lock files in recovery...", "step")
        deleted = 0
        for lock_file in LOCK_FILES:
            out, rc = _adb_rc(f"shell rm -f {lock_file}")
            if rc == 0:
                deleted += 1
            result.steps.append(f"  rm {lock_file} (rc={rc})")

        if deleted > 0:
            result.lock_removed = True
            result.methods_succeeded.append("Recovery File Delete")
            result.steps.append(f"Deleted {deleted} lock files in recovery")

        # Try to erase FRP in recovery
        self._cb(0.60, "Attempting FRP partition erase in recovery...", "step")
        for part in FRP_PARTITIONS:
            out, rc = _adb_rc(f"shell dd if=/dev/zero of=/dev/block/by-name/{part} bs=4096 count=1")
            result.steps.append(f"  Zero-fill {part} (rc={rc})")
            if rc == 0:
                result.frp_removed = True

        if result.frp_removed:
            result.methods_succeeded.append("Recovery FRP Erase")

        result.reboot_required = True
        if self.auto_reboot:
            _adb("reboot")
            result.steps.append("Rebooted from recovery")

    # ------------------------------------------------------------------
    #  Phase 2c: Fastboot Mode Unlock
    # ------------------------------------------------------------------

    def _unlock_via_fastboot(self, result: UnlockResult):
        """Unlock via Fastboot — OEM unlock + partition erase."""
        info = result.device_info
        self._cb(0.20, "Device in Fastboot mode — starting unlock...", "info")

        # Step 1: Try OEM unlock
        self._cb(0.25, "Attempting bootloader unlock...", "step")
        result.methods_tried.append("Fastboot OEM Unlock")

        out, rc = _fastboot_rc("flashing unlock")
        result.steps.append(f"fastboot flashing unlock (rc={rc}): {out[:120]}")

        if rc != 0:
            out2, rc2 = _fastboot_rc("oem unlock")
            result.steps.append(f"fastboot oem unlock (rc={rc2}): {out2[:120]}")
            if rc2 == 0:
                rc = 0

        if rc == 0:
            result.methods_succeeded.append("Fastboot OEM Unlock")
            info.bootloader_unlocked = True
            self._cb(0.35, "Bootloader unlocked!", "success")

        # Step 2: Erase FRP partitions
        self._cb(0.40, "Erasing FRP partitions...", "step")
        result.methods_tried.append("Fastboot FRP Erase")
        frp_erased = False

        for part in FRP_PARTITIONS:
            if self._stopped():
                return
            out, rc = _fastboot_rc(f"erase {part}")
            result.steps.append(f"  fastboot erase {part} (rc={rc})")
            if rc == 0:
                frp_erased = True

        if frp_erased:
            result.frp_removed = True
            result.methods_succeeded.append("Fastboot FRP Erase")
            self._cb(0.55, "FRP partitions erased", "success")

        # Step 3: Factory reset (wipe data)
        self._cb(0.60, "Performing factory reset...", "step")
        result.methods_tried.append("Fastboot Factory Reset")

        out, rc = _fastboot_rc("erase userdata")
        result.steps.append(f"fastboot erase userdata (rc={rc})")

        out2, rc2 = _fastboot_rc("erase cache")
        result.steps.append(f"fastboot erase cache (rc={rc2})")

        out3, rc3 = _fastboot_rc("erase metadata")
        result.steps.append(f"fastboot erase metadata (rc={rc3})")

        if rc == 0:
            result.lock_removed = True
            result.data_wiped = True
            result.methods_succeeded.append("Fastboot Factory Reset")
            self._cb(0.80, "Factory reset complete — data wiped", "success")
        else:
            # Fallback: fastboot -w
            out4, rc4 = _fastboot_rc("-w")
            result.steps.append(f"fastboot -w (rc={rc4})")
            if rc4 == 0:
                result.lock_removed = True
                result.data_wiped = True
                result.methods_succeeded.append("Fastboot -w")

        result.reboot_required = True
        if self.auto_reboot:
            self._cb(0.90, "Rebooting device...", "info")
            _fastboot("reboot")
            result.steps.append("Rebooted from fastboot")

    # ------------------------------------------------------------------
    #  Phase 2d: EDL 9008 Mode Unlock
    # ------------------------------------------------------------------

    def _unlock_via_edl(self, result: UnlockResult):
        """Unlock via EDL 9008 mode — firehose-based FRP partition wipe."""
        info = result.device_info
        self._cb(0.20, "Device in EDL 9008 mode — starting firehose unlock...", "info")

        edl_port = info.edl_port or find_edl_port()
        if not edl_port:
            result.error = "EDL 9008 device detected but COM port not found. Install Qualcomm USB drivers."
            result.steps.append("EDL COM port not found")
            self._cb(0.25, result.error, "error")
            return

        result.steps.append(f"EDL port: {edl_port}")
        result.methods_tried.append("EDL Firehose FRP Erase")

        try:
            import serial
        except ImportError:
            result.error = "pyserial not installed — run: pip install pyserial"
            result.steps.append("pyserial missing")
            return

        self._cb(0.25, f"Connecting to EDL on {edl_port}...", "step")

        try:
            ser = serial.Serial(
                port=edl_port,
                baudrate=115200,
                timeout=EDL_TIMEOUT,
                write_timeout=5,
            )
            result.steps.append(f"Serial port {edl_port} opened")
        except Exception as e:
            result.error = f"Cannot open EDL port {edl_port}: {e}"
            result.steps.append(result.error)
            return

        try:
            # Sahara handshake
            self._cb(0.30, "Sahara handshake...", "step")
            sahara_ok = self._edl_sahara_handshake(ser, result)

            if not sahara_ok:
                # Try sending firehose commands directly (some devices skip Sahara)
                self._cb(0.35, "Trying direct firehose commands...", "step")

            # Firehose: erase FRP partition
            self._cb(0.40, "Sending firehose erase commands for FRP...", "step")
            frp_erased = self._edl_firehose_erase_frp(ser, result)

            if frp_erased:
                result.frp_removed = True
                result.methods_succeeded.append("EDL Firehose FRP Erase")
                self._cb(0.70, "FRP partition erased via EDL!", "success")

            # Firehose: erase userdata (optional, for lock removal)
            self._cb(0.75, "Erasing userdata partition...", "step")
            ud_erased = self._edl_firehose_erase_userdata(ser, result)

            if ud_erased:
                result.lock_removed = True
                result.data_wiped = True
                result.methods_succeeded.append("EDL Userdata Erase")
                self._cb(0.85, "Userdata erased — lock removed", "success")

            # Reset device
            self._cb(0.90, "Resetting device...", "step")
            self._edl_reset(ser, result)
            result.reboot_required = True

        except Exception as e:
            result.steps.append(f"EDL error: {e}")
            result.error = str(e)
        finally:
            try:
                ser.close()
            except Exception:
                pass

    def _edl_sahara_handshake(self, ser, result: UnlockResult) -> bool:
        """Perform Sahara protocol handshake."""
        try:
            # Wait for Sahara HELLO
            data = ser.read(48)
            if len(data) < 8:
                result.steps.append("No Sahara HELLO received")
                return False

            cmd_id = struct.unpack_from("<I", data, 0)[0]
            if cmd_id != 0x01:  # SAHARA_HELLO_ID
                result.steps.append(f"Unexpected Sahara command: 0x{cmd_id:02X}")
                return False

            result.steps.append("Sahara HELLO received")

            # Parse HELLO packet
            if len(data) >= 48:
                version = struct.unpack_from("<I", data, 4)[0]
                min_ver = struct.unpack_from("<I", data, 12)[0]
                mode = struct.unpack_from("<I", data, 24)[0]
                result.steps.append(f"  Sahara version: {version}, mode: {mode}")

            # Send HELLO response — switch to command mode
            hello_resp = struct.pack("<IIIIIIII",
                0x02,  # SAHARA_HELLO_RESP_ID
                48,    # packet length
                2,     # version
                0,     # version_compatible
                0,     # status
                0x02,  # mode = command mode
                0, 0,  # reserved
            )
            ser.write(hello_resp)
            result.steps.append("Sahara HELLO response sent (command mode)")

            # Wait for CMD_READY
            resp = ser.read(8)
            if len(resp) >= 4:
                resp_cmd = struct.unpack_from("<I", resp, 0)[0]
                if resp_cmd == 0x0B:  # SAHARA_CMD_READY_ID
                    result.steps.append("Sahara CMD_READY received — switching to firehose")
                    return True

            result.steps.append("Sahara handshake incomplete")
            return False

        except Exception as e:
            result.steps.append(f"Sahara error: {e}")
            return False

    def _edl_firehose_erase_frp(self, ser, result: UnlockResult) -> bool:
        """Send firehose XML command to erase FRP partition."""
        # Firehose erase command for common FRP partition locations
        erase_configs = [
            # (start_sector, num_sectors, physical_partition) — common FRP locations
            {"label": "frp", "start": "0", "num": "1024"},
            {"label": "config", "start": "0", "num": "1024"},
            {"label": "persistent", "start": "0", "num": "512"},
        ]

        erased = False
        for cfg in erase_configs:
            xml_cmd = (
                f'<?xml version="1.0" ?>\n'
                f'<data>\n'
                f'  <erase SECTOR_SIZE_IN_BYTES="4096" '
                f'num_partition_sectors="{cfg["num"]}" '
                f'physical_partition_number="0" '
                f'start_sector="{cfg["start"]}" '
                f'StorageDrive="0" />\n'
                f'</data>'
            )
            try:
                ser.write(xml_cmd.encode("utf-8"))
                result.steps.append(f"  Firehose erase sent for {cfg['label']}")
                time.sleep(1)

                resp = ser.read(4096)
                resp_text = resp.decode("utf-8", errors="replace") if resp else ""
                if "ACK" in resp_text or "response value" in resp_text.lower():
                    result.steps.append(f"  {cfg['label']} partition erased — ACK received")
                    erased = True
                else:
                    result.steps.append(f"  {cfg['label']} erase response: {resp_text[:100]}")
            except Exception as e:
                result.steps.append(f"  Firehose erase error ({cfg['label']}): {e}")

        return erased

    def _edl_firehose_erase_userdata(self, ser, result: UnlockResult) -> bool:
        """Send firehose XML command to erase userdata partition."""
        xml_cmd = (
            '<?xml version="1.0" ?>\n'
            '<data>\n'
            '  <erase SECTOR_SIZE_IN_BYTES="4096" '
            'num_partition_sectors="0" '
            'physical_partition_number="0" '
            'start_sector="0" '
            'StorageDrive="0" '
            'label="userdata" />\n'
            '</data>'
        )
        try:
            ser.write(xml_cmd.encode("utf-8"))
            result.steps.append("  Firehose erase sent for userdata")
            time.sleep(2)

            resp = ser.read(4096)
            resp_text = resp.decode("utf-8", errors="replace") if resp else ""
            if "ACK" in resp_text:
                result.steps.append("  Userdata partition erased — ACK received")
                return True
            else:
                result.steps.append(f"  Userdata erase response: {resp_text[:100]}")
                return False
        except Exception as e:
            result.steps.append(f"  Firehose userdata erase error: {e}")
            return False

    def _edl_reset(self, ser, result: UnlockResult):
        """Send firehose reset command."""
        xml_cmd = (
            '<?xml version="1.0" ?>\n'
            '<data>\n'
            '  <power value="reset" />\n'
            '</data>'
        )
        try:
            ser.write(xml_cmd.encode("utf-8"))
            result.steps.append("Firehose reset command sent")
        except Exception as e:
            result.steps.append(f"Reset error: {e}")

    # ------------------------------------------------------------------
    #  Phase 2e: ADB Sideload Mode
    # ------------------------------------------------------------------

    def _unlock_via_sideload(self, result: UnlockResult):
        """Limited options in sideload mode."""
        self._cb(0.20, "Device in ADB Sideload mode — limited options", "warning")
        result.steps.append("Sideload mode — trying reboot to other modes")
        result.methods_tried.append("Sideload Reboot")

        # Try to reboot to bootloader
        _adb("reboot bootloader")
        result.steps.append("Sent reboot-bootloader command")
        self._cb(0.30, "Rebooting to fastboot mode...", "info")
        time.sleep(REBOOT_WAIT)

        # Check if we're now in fastboot
        fb_out = _fastboot("devices")
        if fb_out and "fastboot" in fb_out.lower():
            self._cb(0.40, "Now in fastboot — proceeding with fastboot unlock", "success")
            self._detect_fastboot_info(result.device_info)
            result.device_info.mode = DeviceMode.FASTBOOT
            self._unlock_via_fastboot(result)
        else:
            result.steps.append("Could not enter fastboot from sideload")
            result.error = "Device stuck in sideload mode — try manual fastboot entry"

    # ------------------------------------------------------------------
    #  USB Monitor — Continuous Device Watching
    # ------------------------------------------------------------------

    def start_monitoring(
        self,
        on_device_found: Optional[Callable[[DeviceInfo], None]] = None,
        on_device_lost: Optional[Callable[[], None]] = None,
    ) -> threading.Event:
        """
        Start background USB monitoring. Calls on_device_found when a device
        is detected, on_device_lost when disconnected.

        Returns a threading.Event that can be set to stop monitoring.
        """
        stop_event = threading.Event()

        def monitor_loop():
            last_mode = DeviceMode.NONE

            while not stop_event.is_set():
                try:
                    devices = detect_usb_devices()

                    current_mode = DeviceMode.NONE
                    if "edl_9008" in devices:
                        current_mode = DeviceMode.EDL_9008
                    elif "fastboot" in devices:
                        current_mode = DeviceMode.FASTBOOT
                    elif "adb_recovery" in devices:
                        current_mode = DeviceMode.ADB_RECOVERY
                    elif "adb" in devices:
                        current_mode = DeviceMode.ADB_NORMAL
                    elif "adb_unauthorized" in devices:
                        current_mode = DeviceMode.ADB_UNAUTHORIZED

                    if current_mode != DeviceMode.NONE and last_mode == DeviceMode.NONE:
                        # Device just connected
                        info = self.detect_device()
                        if on_device_found:
                            on_device_found(info)
                    elif current_mode == DeviceMode.NONE and last_mode != DeviceMode.NONE:
                        # Device just disconnected
                        if on_device_lost:
                            on_device_lost()

                    last_mode = current_mode

                except Exception as e:
                    logger.debug("Monitor error: %s", e)

                stop_event.wait(MONITOR_INTERVAL)

        thread = threading.Thread(target=monitor_loop, daemon=True, name="usb-monitor")
        thread.start()
        return stop_event


# ---------------------------------------------------------------------------
#  Module-level convenience
# ---------------------------------------------------------------------------

__all__ = [
    "DeviceMode",
    "UnlockAction",
    "DeviceInfo",
    "UnlockResult",
    "AutoUnlocker",
    "detect_usb_devices",
    "find_edl_port",
]
