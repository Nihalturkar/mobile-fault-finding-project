"""
FRP / Unlock Features Module for Mobile Repair Technicians.

Provides Factory Reset Protection (FRP) bypass, screen-lock removal,
Mi Account binding checks, and Samsung Knox status inspection using
standard ADB and Fastboot commands from Android Platform Tools.

This module is intended for **authorized repair technicians** who have
legitimate access to the device.  All commands used are part of
Android's official developer toolset (adb, fastboot).

Requires:
    - Android Platform Tools (adb, fastboot) on PATH
    - USB Debugging enabled (or device in recovery/fastboot mode)
    - For some operations: ADB root access or unlocked bootloader

Usage:
    from app.hardware.frp_unlocker import (
        check_lock_status,
        remove_frp,
        remove_screen_lock,
        check_mi_account,
        check_knox_status,
    )

    status = check_lock_status(callback=lambda p, m: print(f"{p:.0%} {m}"))
    if status.frp_enabled:
        result = remove_frp(callback=lambda p, m: print(f"{p:.0%} {m}"))
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

ADB_TIMEOUT = 15          # seconds per command
FASTBOOT_TIMEOUT = 30     # fastboot commands can be slower
REBOOT_WAIT = 5           # grace period after reboot commands

# Google Services Framework content provider
GSF_PROVIDER = "content://com.google.android.gsf.gservices"
GSF_PROVIDER_ALT = "content://com.google.android.gsf.gservices/prefix"

# FRP-related packages — comprehensive list for all brands
FRP_PACKAGES = [
    # Google core FRP packages
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.gsf.login",
    "com.google.android.setupwizard",
    "com.google.android.partnersetup",
    "com.google.android.packageinstaller",
    "com.google.android.backuptransport",
    # Samsung
    "com.samsung.android.setupwizard",
    "com.samsung.sec.android.setupwizard",
    "com.samsung.android.fmm",
    "com.samsung.android.samsungaccount",
    # OnePlus / OPPO / Realme (ColorOS / OxygenOS)
    "com.oplus.setupwizard",
    "com.oneplus.setupwizard",
    "com.coloros.setupwizard",
    "com.oppo.setupwizard",
    "com.heytap.cloud",
    "com.oplus.account",
    # Xiaomi / Redmi / POCO (MIUI / HyperOS)
    "com.miui.cloudservice",
    "com.miui.cloudservice.sysbase",
    "com.xiaomi.finddevice",
    "com.miui.securitycenter",
    "com.miui.guardprovider",
    # Vivo / iQOO
    "com.vivo.setupwizard",
    "com.iqoo.setupwizard",
    "com.vivo.id",
    # Motorola
    "com.motorola.setupwizard",
    # Huawei / Honor
    "com.huawei.hwid",
    "com.huawei.android.setupwizard",
    # Nothing
    "com.nothing.setupwizard",
    # Generic Android
    "com.android.provision",
    "com.android.managedprovisioning",
]

# Screen lock file paths (Android internal storage)
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

# Settings-bypass activities — expanded for all brands
SETTINGS_ACTIVITIES = [
    # Core Android settings
    "com.android.settings/.Settings",
    "com.android.settings/.CryptKeeper",
    "com.android.settings/.Settings\$AccountsSettingsActivity",
    "com.android.settings/.Settings\$SecuritySettingsActivity",
    "com.android.settings/.Settings\$DevelopmentSettingsActivity",
    "com.android.settings/.wifi.WifiPickerActivity",
    # Google
    "com.google.android.gsf.login/.LoginActivity",
    "com.google.android.gms/.auth.setup.wizard.AnalyticsOptInActivity",
    "com.google.android.gms/.auth.login.LoginActivity",
    "com.google.android.gms/.setup.wizard.GmsCheckinCompleteActivity",
    # Samsung
    "com.samsung.android.settings/.Settings",
    # OnePlus
    "com.oneplus.opsetupwizard/.SetupWizardActivity",
]

# Intent actions for FRP bypass — launch system activities without knowing package names
FRP_BYPASS_INTENTS = [
    # Settings intents
    "android.settings.SETTINGS",
    "android.settings.SYNC_SETTINGS",
    "android.settings.ADD_ACCOUNT_SETTINGS",
    "android.settings.WIFI_SETTINGS",
    "android.settings.APPLICATION_SETTINGS",
    "android.settings.SECURITY_SETTINGS",
    "android.settings.PRIVACY_SETTINGS",
    "android.settings.APPLICATION_DEVELOPMENT_SETTINGS",
    "android.settings.DATE_SETTINGS",
    "android.settings.ACCESSIBILITY_SETTINGS",
    "android.settings.DEVICE_INFO_SETTINGS",
    "android.settings.MANAGE_APPLICATIONS_SETTINGS",
    "android.settings.USER_SETTINGS",
    # Browser intents
    "android.intent.action.VIEW -d https://accounts.google.com",
    "android.intent.action.VIEW -d https://www.google.com",
    # Dialer intent (for secret codes)
    "android.intent.action.DIAL -d tel:*#*#4636#*#*",
    # Home intent
    "android.intent.action.MAIN -c android.intent.category.HOME",
    # File manager
    "android.intent.action.VIEW -t application/pdf",
]

# ADB-based FRP database/settings manipulations
FRP_DB_COMMANDS = [
    # Clear FRP data from secure settings
    'settings delete secure lock_screen_lock_after_timeout',
    'settings delete secure lockscreen.password_type',
    'settings delete secure lockscreen.password_type_alternate',
    'settings delete global device_provisioned',
    'settings delete secure user_setup_complete',
    # Set bypass flags
    'settings put global device_provisioned 1',
    'settings put secure user_setup_complete 1',
    'settings put global setup_wizard_has_run 1',
    'settings put secure install_non_market_apps 1',
    'settings put global verifier_verify_adb_installs 0',
    # Clear Google account data
    'settings put secure android_id ""',
    'settings put secure account_fingerprint ""',
    # Disable FRP at system level
    'settings put global frp_locked 0',
    'settings put secure frp_mode 0',
    # Content provider manipulations
    'content insert --uri content://settings/secure --bind name:s:user_setup_complete --bind value:s:1',
    'content insert --uri content://settings/global --bind name:s:device_provisioned --bind value:s:1',
    'content insert --uri content://settings/secure --bind name:s:install_non_market_apps --bind value:s:1',
]

# Fastboot partitions to erase for FRP — comprehensive
FRP_FASTBOOT_PARTITIONS = [
    "frp",
    "config",
    "persistent",
    "param",
    "devinfo",
    "oem",
    "reserve1",
    "reserve2",
    "misc",
]

# Mi Account related properties
MI_ACCOUNT_PROPS = [
    "persist.sys.micloud_user_id",
    "persist.sys.micloud_account",
    "ro.miui.has_micloud",
]

# Knox related properties and paths
KNOX_PROPS = [
    "ro.boot.warranty_bit",
    "ro.warranty_bit",
    "ro.boot.flash.locked",
    "ro.knox.enhance.zimage.support",
]


# ---------------------------------------------------------------------------
#  Result Data Classes
# ---------------------------------------------------------------------------

@dataclass
class LockStatusResult:
    """Complete lock/security status of the connected device."""
    connected: bool = False
    error: Optional[str] = None
    frp_enabled: bool = False
    screen_lock_type: str = "none"       # none / pattern / pin / password / fingerprint
    encryption_status: str = "unknown"
    mi_account_bound: bool = False
    knox_tripped: bool = False
    google_accounts: List[str] = field(default_factory=list)
    samsung_account: bool = False
    secure_startup: bool = False
    device_brand: str = ""
    device_model: str = ""
    android_version: str = ""
    adb_mode: str = "unknown"            # normal / recovery / sideload / fastboot
    bootloader_unlocked: bool = False
    root_access: bool = False


@dataclass
class FRPResult:
    """Result from an FRP removal attempt."""
    success: bool = False
    method_used: str = ""
    error: Optional[str] = None
    steps_performed: List[str] = field(default_factory=list)
    reboot_required: bool = False
    methods_tried: int = 0
    device_brand: str = ""


@dataclass
class ScreenLockResult:
    """Result from a screen-lock removal attempt."""
    success: bool = False
    lock_type_removed: str = ""
    method_used: str = ""
    error: Optional[str] = None
    steps_performed: List[str] = field(default_factory=list)
    reboot_required: bool = False
    data_wiped: bool = False


@dataclass
class MiAccountResult:
    """Xiaomi Mi Account binding status."""
    connected: bool = False
    error: Optional[str] = None
    mi_account_bound: bool = False
    mi_user_id: str = ""
    mi_email: str = ""
    micloud_enabled: bool = False
    find_device_active: bool = False
    mi_account_packages: List[str] = field(default_factory=list)
    device_model: str = ""
    miui_version: str = ""


@dataclass
class KnoxResult:
    """Samsung Knox warranty/trip status."""
    connected: bool = False
    error: Optional[str] = None
    knox_tripped: bool = False
    warranty_bit: str = "unknown"        # 0x0 = not tripped, 0x1 = tripped
    knox_version: str = ""
    knox_container_active: bool = False
    secure_folder_active: bool = False
    device_model: str = ""
    firmware_version: str = ""
    bootloader_locked: bool = True
    dm_verity_enabled: bool = True
    oem_unlock_enabled: bool = False


# ---------------------------------------------------------------------------
#  Low-level ADB / Fastboot Helpers
# ---------------------------------------------------------------------------

def _run_adb(cmd: str, timeout: int = ADB_TIMEOUT) -> str:
    """Run an ADB command and return stdout.  Never raises."""
    full_cmd = f"adb {cmd}"
    logger.debug("ADB exec: %s", full_cmd)
    try:
        r = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            errors="replace",
        )
        out = r.stdout.strip()
        if r.returncode != 0 and r.stderr.strip():
            logger.debug("ADB stderr: %s", r.stderr.strip())
        return out
    except subprocess.TimeoutExpired:
        logger.warning("ADB command timed out: %s", full_cmd)
        return ""
    except FileNotFoundError:
        logger.error("ADB binary not found on PATH")
        return "ADB_NOT_FOUND"
    except Exception as exc:
        logger.error("ADB unexpected error: %s", exc)
        return ""


def _run_adb_rc(cmd: str, timeout: int = ADB_TIMEOUT) -> Tuple[str, int]:
    """Run ADB command and return (stdout, return_code)."""
    full_cmd = f"adb {cmd}"
    logger.debug("ADB exec (rc): %s", full_cmd)
    try:
        r = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            errors="replace",
        )
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1
    except FileNotFoundError:
        return "ADB_NOT_FOUND", -1
    except Exception:
        return "", -1


def _shell(cmd: str, timeout: int = ADB_TIMEOUT) -> str:
    """Run an ``adb shell`` command with proper quoting."""
    return _run_adb(f'shell "{cmd}"', timeout)


def _shell_raw(cmd: str, timeout: int = ADB_TIMEOUT) -> str:
    """Run ``adb shell`` without extra quoting (for pipes/redirects)."""
    return _run_adb(f"shell {cmd}", timeout)


def _run_fastboot(cmd: str, timeout: int = FASTBOOT_TIMEOUT) -> str:
    """Run a fastboot command and return stdout.  Never raises."""
    full_cmd = f"fastboot {cmd}"
    logger.debug("Fastboot exec: %s", full_cmd)
    try:
        r = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            errors="replace",
        )
        combined = r.stdout.strip()
        if r.stderr.strip():
            combined = combined + "\n" + r.stderr.strip() if combined else r.stderr.strip()
        return combined
    except subprocess.TimeoutExpired:
        logger.warning("Fastboot command timed out: %s", full_cmd)
        return ""
    except FileNotFoundError:
        logger.error("Fastboot binary not found on PATH")
        return "FASTBOOT_NOT_FOUND"
    except Exception as exc:
        logger.error("Fastboot unexpected error: %s", exc)
        return ""


def _run_fastboot_rc(cmd: str, timeout: int = FASTBOOT_TIMEOUT) -> Tuple[str, int]:
    """Run fastboot command and return (combined_output, return_code)."""
    full_cmd = f"fastboot {cmd}"
    logger.debug("Fastboot exec (rc): %s", full_cmd)
    try:
        r = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            errors="replace",
        )
        combined = r.stdout.strip()
        if r.stderr.strip():
            combined = combined + "\n" + r.stderr.strip() if combined else r.stderr.strip()
        return combined, r.returncode
    except subprocess.TimeoutExpired:
        return "", -1
    except FileNotFoundError:
        return "FASTBOOT_NOT_FOUND", -1
    except Exception:
        return "", -1


def _safe_int(s: str, default: int = 0) -> int:
    """Parse integer from string, returning *default* on failure."""
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return default


# ---------------------------------------------------------------------------
#  Connection Helpers
# ---------------------------------------------------------------------------

def _check_adb_connection() -> Tuple[bool, str]:
    """
    Check if a device is connected via ADB.

    Returns:
        (connected, mode) where mode is one of:
        'normal', 'recovery', 'sideload', 'unauthorized', 'offline', 'none'
    """
    output = _run_adb("devices")
    if output == "ADB_NOT_FOUND":
        return False, "adb_not_found"

    lines = output.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("List") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            state = parts[1].lower()
            if state == "device":
                return True, "normal"
            elif state == "recovery":
                return True, "recovery"
            elif state == "sideload":
                return True, "sideload"
            elif state == "unauthorized":
                return True, "unauthorized"
            elif state == "offline":
                return True, "offline"
    return False, "none"


def _check_fastboot_connection() -> bool:
    """Check if a device is connected in fastboot mode."""
    output = _run_fastboot("devices")
    if "FASTBOOT_NOT_FOUND" in output:
        return False
    for line in output.splitlines():
        line = line.strip()
        if line and "fastboot" in line.lower():
            return True
    return False


def _check_root_access() -> bool:
    """Check if ADB has root access on the device."""
    output = _shell("id")
    if "uid=0" in output:
        return True
    # Try adb root
    root_out = _run_adb("root")
    if "adbd is already running as root" in root_out or "restarting adbd as root" in root_out:
        time.sleep(1)
        return True
    return False


def _get_device_brand() -> str:
    """Get the device brand/manufacturer."""
    brand = _shell("getprop ro.product.brand").lower()
    if not brand:
        brand = _shell("getprop ro.product.manufacturer").lower()
    return brand


def _get_device_model() -> str:
    """Get the device model name."""
    model = _shell("getprop ro.product.model")
    if not model:
        model = _shell("getprop ro.product.device")
    return model


def _get_android_version() -> str:
    """Get the Android version string."""
    return _shell("getprop ro.build.version.release")


def _get_sdk_version() -> int:
    """Get the Android SDK/API level as an integer."""
    return _safe_int(_shell("getprop ro.build.version.sdk"))


# ---------------------------------------------------------------------------
#  Detection Helpers
# ---------------------------------------------------------------------------

def _detect_frp_status() -> Tuple[bool, List[str]]:
    """
    Detect whether FRP (Factory Reset Protection) is active.

    Checks:
        1. Google account provisioning flag in secure settings
        2. Presence of Google accounts on the device
        3. Setup wizard completion state

    Returns:
        (frp_enabled, google_accounts_list)
    """
    google_accounts: List[str] = []
    frp_enabled = False

    # Check if setup wizard has been completed
    setup_complete = _shell("settings get secure user_setup_complete")
    logger.debug("user_setup_complete = %s", setup_complete)

    # Check FRP-specific secure setting
    frp_state = _shell("settings get secure frp_mode")
    logger.debug("frp_mode = %s", frp_state)

    # Check provisioned account
    prov = _shell("settings get global device_provisioned")
    logger.debug("device_provisioned = %s", prov)

    # List Google accounts
    accounts_raw = _shell("dumpsys account")
    if accounts_raw:
        # Parse account names that look like email addresses
        email_pattern = re.compile(r"Account\s*\{[^}]*name=([^,}]+@[^,}]+)")
        matches = email_pattern.findall(accounts_raw)
        for m in matches:
            acct = m.strip()
            if acct and acct not in google_accounts:
                google_accounts.append(acct)
        logger.debug("Found %d Google accounts", len(google_accounts))

    # Alternative: use content provider query
    if not google_accounts:
        acct_alt = _shell("content query --uri content://com.android.contacts/raw_contacts")
        if acct_alt and "com.google" in acct_alt.lower():
            logger.debug("Google contacts provider indicates bound accounts")

    # FRP is enabled when there are Google accounts and setup is complete
    if google_accounts:
        frp_enabled = True
    elif frp_state == "1":
        frp_enabled = True
    elif setup_complete == "1" and prov == "1":
        # Device is provisioned and set up -- check for GSF ID
        gsf_id = _shell("settings get secure android_id")
        if gsf_id and gsf_id not in ("null", ""):
            # May have FRP even without visible accounts in some ROMs
            pass

    return frp_enabled, google_accounts


def _detect_screen_lock_type() -> str:
    """
    Detect the current screen lock type.

    Returns one of: 'none', 'swipe', 'pattern', 'pin', 'password', 'fingerprint'
    """
    # Method 1: locksettings (Android 8+)
    lock_out = _shell("locksettings get-disabled")
    logger.debug("locksettings get-disabled = %s", lock_out)

    # Method 2: dumpsys lock_settings
    ls_dump = _shell("dumpsys lock_settings")
    logger.debug("lock_settings dump length = %d", len(ls_dump))

    # Method 3: Check via settings secure
    lock_screen_owner = _shell("settings get secure lockscreen.password_type")
    logger.debug("lockscreen.password_type = %s", lock_screen_owner)

    # Parse password type value
    # 0       = no lock
    # 65536   = swipe / none
    # 131072  = slide
    # 65536   = pattern (some devices)
    # 327680  = pattern
    # 262144  = PIN
    # 393216  = password
    # 524288  = fingerprint/biometric (combined)
    try:
        pw_type = int(lock_screen_owner)
    except (ValueError, TypeError):
        pw_type = -1

    if pw_type <= 0 or pw_type == 65536:
        # Double-check: look for actual lock files
        gesture_exists = _shell("ls /data/system/gesture.key 2>/dev/null")
        password_exists = _shell("ls /data/system/password.key 2>/dev/null")
        gk_pattern = _shell("ls /data/system/gatekeeper.pattern.key 2>/dev/null")
        gk_password = _shell("ls /data/system/gatekeeper.password.key 2>/dev/null")

        if gesture_exists and "No such file" not in gesture_exists:
            return "pattern"
        if gk_pattern and "No such file" not in gk_pattern:
            return "pattern"
        if password_exists and "No such file" not in password_exists:
            return "password"
        if gk_password and "No such file" not in gk_password:
            return "password"
        return "none"

    if pw_type == 327680 or pw_type == 65536:
        return "pattern"
    elif pw_type == 262144:
        return "pin"
    elif pw_type == 393216:
        return "password"
    elif pw_type >= 524288:
        return "fingerprint"
    else:
        return "none"


def _detect_encryption_status() -> str:
    """
    Check the device encryption status.

    Returns: 'encrypted', 'decrypted', 'unencrypted', 'file-based', or 'unknown'
    """
    # Check vold for FDE
    vold = _shell("getprop ro.crypto.state")
    logger.debug("ro.crypto.state = %s", vold)

    if vold == "encrypted":
        # Check if file-based encryption
        fbe = _shell("getprop ro.crypto.type")
        if fbe == "file":
            return "file-based"
        return "encrypted"
    elif vold == "unencrypted":
        return "unencrypted"

    # Fallback: check dm-crypt or metadata encryption
    dm_output = _shell("getprop ro.crypto.dm_default_key")
    if dm_output:
        return "file-based"

    return "unknown"


def _detect_secure_startup() -> bool:
    """Check if secure startup (require password before boot) is enabled."""
    secure = _shell("getprop vold.decrypt")
    if secure and "trigger_restart" in secure:
        return True
    # Check secure start up setting
    ss = _shell("settings get global require_password_to_decrypt")
    return ss == "1"


def _detect_samsung_account() -> bool:
    """Check if a Samsung account is bound to the device."""
    sa_dump = _shell("dumpsys account")
    if "com.osp.app.signin" in sa_dump or "sec.android.signin" in sa_dump:
        return True
    sa_pkg = _shell("pm list packages com.samsung.android.samsungaccount")
    if "com.samsung.android.samsungaccount" in sa_pkg:
        # Package exists; check if account is active
        sa_running = _shell("dumpsys activity services com.samsung.android.samsungaccount")
        if sa_running and "ServiceRecord" in sa_running:
            return True
    return False


def _detect_bootloader_status() -> bool:
    """
    Check if the bootloader is unlocked.

    Returns True if unlocked, False if locked or unknown.
    """
    # Check via getprop
    bl = _shell("getprop ro.boot.flash.locked")
    if bl == "0":
        return True  # unlocked

    bl2 = _shell("getprop ro.boot.verifiedbootstate")
    if bl2 == "orange":
        return True  # unlocked

    oem = _shell("getprop sys.oem_unlock_allowed")
    if oem == "1":
        return True

    return False


# ---------------------------------------------------------------------------
#  check_lock_status  --  Main Detection Flow
# ---------------------------------------------------------------------------

def check_lock_status(
    callback: Optional[Callable[[float, str], None]] = None,
) -> LockStatusResult:
    """
    Perform a full lock/security status check on the connected device.

    Detection flow:
        1. Check ADB connection (normal mode or recovery)
        2. Read device identity (brand, model, Android version)
        3. Check FRP status via secure settings
        4. Check screen lock type
        5. Check encryption status
        6. Check Google accounts
        7. Check Mi account (Xiaomi devices only)
        8. Check Knox status (Samsung devices only)
        9. Check bootloader / root status

    Args:
        callback: Optional progress callback ``(pct: float, msg: str)``.

    Returns:
        Populated :class:`LockStatusResult`.
    """
    result = LockStatusResult()

    def _cb(pct: float, msg: str) -> None:
        logger.info("[%3.0f%%] %s", pct * 100, msg)
        if callback:
            callback(pct, msg)

    # -- Step 1: ADB connection ------------------------------------------
    _cb(0.0, "Checking ADB connection...")
    connected, mode = _check_adb_connection()
    result.adb_mode = mode

    if not connected:
        # Try fastboot
        _cb(0.05, "No ADB device found, checking fastboot...")
        if _check_fastboot_connection():
            result.connected = True
            result.adb_mode = "fastboot"
            _cb(0.10, "Device connected in fastboot mode (limited detection)")
            # In fastboot we can only get limited info
            fb_var = _run_fastboot("getvar all")
            if "product" in fb_var.lower():
                for line in fb_var.splitlines():
                    if "product" in line.lower():
                        result.device_model = line.split(":")[-1].strip()
                        break
            _cb(1.0, "Fastboot detection complete (limited)")
            return result

        result.connected = False
        result.error = (
            "No device connected.  Ensure USB Debugging is enabled "
            "and the device is connected via USB."
        )
        _cb(1.0, "No device detected")
        return result

    if mode == "unauthorized":
        result.connected = True
        result.error = (
            "Device connected but not authorized.  "
            "Accept the USB debugging prompt on the device screen."
        )
        _cb(1.0, "Device unauthorized")
        return result

    if mode == "offline":
        result.connected = True
        result.error = "Device is offline.  Reconnect the USB cable."
        _cb(1.0, "Device offline")
        return result

    result.connected = True
    _cb(0.10, f"Device connected in {mode} mode")

    # -- Step 2: Device identity -----------------------------------------
    _cb(0.15, "Reading device identity...")
    result.device_brand = _get_device_brand()
    result.device_model = _get_device_model()
    result.android_version = _get_android_version()
    _cb(0.20, f"Device: {result.device_brand} {result.device_model} "
               f"(Android {result.android_version})")

    # -- Step 3: Root / Bootloader ----------------------------------------
    _cb(0.25, "Checking root and bootloader status...")
    result.root_access = _check_root_access()
    result.bootloader_unlocked = _detect_bootloader_status()
    logger.info("Root: %s, Bootloader unlocked: %s",
                result.root_access, result.bootloader_unlocked)

    # -- Step 4: FRP status -----------------------------------------------
    _cb(0.35, "Checking FRP (Factory Reset Protection) status...")
    frp_enabled, google_accounts = _detect_frp_status()
    result.frp_enabled = frp_enabled
    result.google_accounts = google_accounts
    _cb(0.45, f"FRP: {'ENABLED' if frp_enabled else 'disabled'}, "
               f"Google accounts: {len(google_accounts)}")

    # -- Step 5: Screen lock type -----------------------------------------
    _cb(0.50, "Detecting screen lock type...")
    result.screen_lock_type = _detect_screen_lock_type()
    _cb(0.55, f"Screen lock: {result.screen_lock_type}")

    # -- Step 6: Encryption -----------------------------------------------
    _cb(0.60, "Checking encryption status...")
    result.encryption_status = _detect_encryption_status()
    result.secure_startup = _detect_secure_startup()
    _cb(0.65, f"Encryption: {result.encryption_status}")

    # -- Step 7: Samsung account ------------------------------------------
    _cb(0.70, "Checking Samsung account...")
    if "samsung" in result.device_brand.lower():
        result.samsung_account = _detect_samsung_account()
        _cb(0.75, f"Samsung account: {'bound' if result.samsung_account else 'none'}")
    else:
        _cb(0.75, "Not a Samsung device -- skipping Samsung account check")

    # -- Step 8: Mi account (Xiaomi) --------------------------------------
    _cb(0.80, "Checking Mi account...")
    if any(kw in result.device_brand.lower() for kw in ("xiaomi", "redmi", "poco")):
        mi_result = check_mi_account()
        result.mi_account_bound = mi_result.mi_account_bound
        _cb(0.85, f"Mi account: {'bound' if result.mi_account_bound else 'none'}")
    else:
        _cb(0.85, "Not a Xiaomi device -- skipping Mi account check")

    # -- Step 9: Knox (Samsung) -------------------------------------------
    _cb(0.90, "Checking Knox status...")
    if "samsung" in result.device_brand.lower():
        knox_result = check_knox_status()
        result.knox_tripped = knox_result.knox_tripped
        _cb(0.95, f"Knox: {'TRIPPED' if result.knox_tripped else 'intact'}")
    else:
        _cb(0.95, "Not a Samsung device -- skipping Knox check")

    _cb(1.0, "Lock status check complete")
    return result


# ---------------------------------------------------------------------------
#  FRP Removal  --  Four Methods
# ---------------------------------------------------------------------------

def _frp_method_content_provider(steps: List[str]) -> bool:
    """
    Method 1: Remove Google account via ADB content provider commands.

    Uses ``adb shell content delete`` to remove the GSF (Google Services
    Framework) ID and related account data.
    """
    logger.info("FRP Method 1: Content provider delete")
    steps.append("Method 1: Content provider delete started")

    # Delete GSF ID
    out1, rc1 = _run_adb_rc(
        'shell content delete --uri content://com.google.android.gsf.gservices '
        '--where "name=\'android_id\'"'
    )
    steps.append(f"Deleted GSF android_id (rc={rc1})")
    logger.debug("GSF delete result: %s (rc=%d)", out1, rc1)

    # Delete Google account from account manager
    out2, rc2 = _run_adb_rc(
        'shell content delete --uri content://com.android.contacts/raw_contacts '
        '--where "account_type=\'com.google\'"'
    )
    steps.append(f"Deleted Google contacts entries (rc={rc2})")

    # Reset Google services
    out3, rc3 = _run_adb_rc(
        'shell content delete --uri content://com.google.android.gsf.gservices/prefix'
    )
    steps.append(f"Cleared GSF gservices prefix (rc={rc3})")

    # Delete FRP-specific content
    out4, rc4 = _run_adb_rc(
        'shell content delete --uri content://com.google.android.gms.auth.accounts/accounts'
    )
    steps.append(f"Cleared GMS auth accounts (rc={rc4})")

    # Reset device provisioning flag
    out5, rc5 = _run_adb_rc(
        'shell settings put global device_provisioned 0'
    )
    steps.append(f"Set device_provisioned=0 (rc={rc5})")

    # Clear setup wizard state
    out6, rc6 = _run_adb_rc(
        'shell settings put secure user_setup_complete 0'
    )
    steps.append(f"Set user_setup_complete=0 (rc={rc6})")

    # Verify removal
    verify = _shell("settings get secure user_setup_complete")
    if verify == "0":
        steps.append("Verification: setup state cleared successfully")
        return True

    steps.append("Verification: content provider method may need reboot to take effect")
    return rc1 == 0 or rc3 == 0


def _frp_method_settings_bypass(steps: List[str]) -> bool:
    """
    Method 2: Bypass FRP by launching Settings activity directly.

    Uses ``am start`` to open the device settings, allowing a technician
    to manually remove the Google account from the settings UI.
    """
    logger.info("FRP Method 2: Settings activity bypass")
    steps.append("Method 2: Settings activity bypass started")

    # Try launching main Settings
    for activity in SETTINGS_ACTIVITIES:
        out, rc = _run_adb_rc(f'shell am start -n {activity}')
        steps.append(f"Launched {activity} (rc={rc})")
        if rc == 0 and "Error" not in out:
            logger.info("Successfully launched: %s", activity)
            break

    # Try opening Accounts section directly via intent
    out_accounts, rc_accounts = _run_adb_rc(
        'shell am start -a android.settings.SYNC_SETTINGS'
    )
    steps.append(f"Launched SYNC_SETTINGS intent (rc={rc_accounts})")

    # Try opening Add Account screen
    out_add, rc_add = _run_adb_rc(
        'shell am start -a android.settings.ADD_ACCOUNT_SETTINGS'
    )
    steps.append(f"Launched ADD_ACCOUNT_SETTINGS intent (rc={rc_add})")

    # Open Google account manager
    out_gam, rc_gam = _run_adb_rc(
        'shell am start -n com.google.android.gms/.auth.login.LoginActivity'
    )
    steps.append(f"Launched Google login activity (rc={rc_gam})")

    # Disable setup wizard to skip FRP after reboot
    out_sw, rc_sw = _run_adb_rc(
        'shell pm disable-user --user 0 com.google.android.setupwizard'
    )
    steps.append(f"Disabled setup wizard (rc={rc_sw})")

    if rc_accounts == 0 or rc_sw == 0:
        steps.append("Settings bypass launched -- manual account removal possible")
        return True

    steps.append("Settings bypass: activities launched, verify on device screen")
    return False


def _frp_method_package_disable(steps: List[str]) -> bool:
    """
    Method 3: Disable FRP-related packages using the package manager.

    Uses ``pm disable-user`` and ``pm clear`` to disable and clear data
    from packages responsible for FRP enforcement.
    """
    logger.info("FRP Method 3: Package manager disable")
    steps.append("Method 3: Package manager disable started")

    success_count = 0
    for pkg in FRP_PACKAGES:
        # First clear the package data
        out_clear, rc_clear = _run_adb_rc(f'shell pm clear {pkg}')
        steps.append(f"Cleared {pkg} data (rc={rc_clear})")

        # Then disable the package
        out_disable, rc_disable = _run_adb_rc(
            f'shell pm disable-user --user 0 {pkg}'
        )
        steps.append(f"Disabled {pkg} (rc={rc_disable})")

        if rc_clear == 0 or rc_disable == 0:
            success_count += 1

    # Also try to remove the account directly
    out_rm, rc_rm = _run_adb_rc(
        'shell am broadcast -a android.accounts.LOGIN_ACCOUNTS_CHANGED'
    )
    steps.append(f"Broadcast LOGIN_ACCOUNTS_CHANGED (rc={rc_rm})")

    # Clear Google Play Services data
    out_gps, rc_gps = _run_adb_rc(
        'shell pm clear com.google.android.gms'
    )
    steps.append(f"Cleared Google Play Services data (rc={rc_gps})")

    # Reset content provider
    out_cp, rc_cp = _run_adb_rc(
        'shell settings put secure android_id ""'
    )
    steps.append(f"Reset android_id (rc={rc_cp})")

    if success_count >= 2:
        steps.append(f"Package disable: {success_count} packages processed")
        return True

    steps.append("Package disable: some packages may not have been accessible")
    return False


def _frp_method_fastboot_erase(steps: List[str]) -> bool:
    """
    Method 4: Erase FRP/config partitions via fastboot.

    Requires the device to be in fastboot mode with an unlocked bootloader.
    Uses ``fastboot erase`` on frp and config partitions.
    """
    logger.info("FRP Method 4: Fastboot partition erase")
    steps.append("Method 4: Fastboot partition erase started")

    # Check if we are in fastboot mode
    if not _check_fastboot_connection():
        # Try rebooting to bootloader
        _run_adb("reboot bootloader")
        steps.append("Sent reboot-bootloader command, waiting...")
        time.sleep(REBOOT_WAIT)

        if not _check_fastboot_connection():
            steps.append("Fastboot mode not available -- method skipped")
            return False

    steps.append("Device detected in fastboot mode")

    # Erase FRP partition
    out_frp, rc_frp = _run_fastboot_rc("erase frp")
    steps.append(f"Fastboot erase frp (rc={rc_frp}): {out_frp[:80]}")

    # Erase config partition (some devices store FRP data here)
    out_cfg, rc_cfg = _run_fastboot_rc("erase config")
    steps.append(f"Fastboot erase config (rc={rc_cfg}): {out_cfg[:80]}")

    # Erase persistent data partition
    out_pdb, rc_pdb = _run_fastboot_rc("erase persistent")
    steps.append(f"Fastboot erase persistent (rc={rc_pdb}): {out_pdb[:80]}")

    # Some Samsung devices use a "param" partition
    out_param, rc_param = _run_fastboot_rc("erase param")
    steps.append(f"Fastboot erase param (rc={rc_param}): {out_param[:80]}")

    if rc_frp == 0 or rc_cfg == 0:
        steps.append("Fastboot erase successful -- reboot required")
        return True

    steps.append("Fastboot erase: partitions may not exist on this device")
    return False


def _frp_method_db_manipulation(steps: List[str]) -> bool:
    """
    Method 5: Direct database and settings manipulation.

    Aggressively modifies secure/global settings and content providers
    to mark the device as provisioned and skip FRP verification.
    """
    logger.info("FRP Method 5: Database/settings manipulation")
    steps.append("Method 5: Direct DB manipulation started")

    success_count = 0
    for cmd in FRP_DB_COMMANDS:
        out, rc = _run_adb_rc(f'shell {cmd}')
        steps.append(f"  {cmd[:60]}... (rc={rc})")
        if rc == 0:
            success_count += 1

    steps.append(f"  DB commands: {success_count}/{len(FRP_DB_COMMANDS)} succeeded")
    return success_count >= len(FRP_DB_COMMANDS) // 2


def _frp_method_intent_flood(steps: List[str]) -> bool:
    """
    Method 6: Launch multiple intents to break out of FRP setup wizard.

    Floods the device with intent launches to open Settings, Browser,
    or any activity that can escape the setup wizard sandbox.
    """
    logger.info("FRP Method 6: Intent flood bypass")
    steps.append("Method 6: Intent flood bypass started")

    launched = False
    for intent in FRP_BYPASS_INTENTS:
        out, rc = _run_adb_rc(f'shell am start -a {intent}')
        if rc == 0 and "Error" not in out:
            steps.append(f"  Launched: {intent[:50]} -- SUCCESS")
            launched = True
        else:
            steps.append(f"  Failed: {intent[:50]}")

    # Try launching via URI scheme
    uri_schemes = [
        "market://details?id=com.android.settings",
        "tel:*%23*%234636%23*%23*",
        "content://settings/secure",
    ]
    for uri in uri_schemes:
        out, rc = _run_adb_rc(f'shell am start -a android.intent.action.VIEW -d "{uri}"')
        if rc == 0:
            steps.append(f"  URI launch: {uri[:40]} -- SUCCESS")
            launched = True

    return launched


def _frp_method_accessibility_bypass(steps: List[str]) -> bool:
    """
    Method 7: Enable accessibility services to bypass FRP.

    Uses ADB to enable TalkBack or other accessibility services,
    then uses them to navigate out of the setup wizard.
    """
    logger.info("FRP Method 7: Accessibility bypass")
    steps.append("Method 7: Accessibility bypass started")

    cmds = [
        # Enable accessibility
        ('settings put secure enabled_accessibility_services com.google.android.marvin.talkback/com.google.android.marvin.talkback.TalkBackService',
         "Enable TalkBack"),
        ('settings put secure accessibility_enabled 1', "Enable accessibility"),
        # Open accessibility settings
        ('am start -a android.settings.ACCESSIBILITY_SETTINGS', "Open accessibility settings"),
        # Try to enable developer options
        ('settings put global development_settings_enabled 1', "Enable developer options"),
        ('settings put global adb_enabled 1', "Enable ADB via settings"),
        # Enable unknown sources
        ('settings put secure install_non_market_apps 1', "Enable unknown sources"),
        # Try opening browser via accessibility
        ('am start -a android.intent.action.VIEW -d https://google.com', "Launch browser"),
    ]

    success = 0
    for cmd, desc in cmds:
        out, rc = _run_adb_rc(f'shell {cmd}')
        steps.append(f"  {desc} (rc={rc})")
        if rc == 0:
            success += 1

    return success >= 3


def _frp_method_emergency_dialer(steps: List[str]) -> bool:
    """
    Method 8: Use emergency dialer to bypass FRP.

    Simulates key events to open emergency dialer, dial secret codes,
    and navigate to settings from there.
    """
    logger.info("FRP Method 8: Emergency dialer bypass")
    steps.append("Method 8: Emergency dialer bypass started")

    cmds = [
        # Open emergency dialer
        ('am start -a android.intent.action.CALL_EMERGENCY', "Open emergency dialer"),
        ('am start -n com.android.phone/.EmergencyDialer', "Launch EmergencyDialer"),
        # Type testing code via input
        ('input text "*#*#4636#*#*"', "Input testing code"),
        ('am start -a android.intent.action.DIAL -d "tel:*%23*%234636%23*%23*"', "Dial testing code"),
        # Try to open phone info directly
        ('am start -n com.android.settings/.TestingSettings', "Open testing settings"),
        ('am start -n com.android.phone/.settings.PhoneAccountSettingsActivity', "Phone settings"),
        # Try opening calculator (some FRP bypasses use this)
        ('am start -n com.google.android.calculator/com.android.calculator2.Calculator', "Open calculator"),
        # Open Google app
        ('am start -n com.google.android.googlequicksearchbox/.SearchActivity', "Google search"),
    ]

    success = 0
    for cmd, desc in cmds:
        out, rc = _run_adb_rc(f'shell {cmd}')
        steps.append(f"  {desc} (rc={rc})")
        if rc == 0 and "Error" not in out:
            success += 1

    return success >= 2


def _frp_method_account_manager(steps: List[str]) -> bool:
    """
    Method 9: Direct account manager manipulation.

    Removes all accounts via Android's AccountManager service,
    clears credential storage, and resets authentication state.
    """
    logger.info("FRP Method 9: Account manager manipulation")
    steps.append("Method 9: Account manager manipulation started")

    cmds = [
        # Remove all Google accounts
        ('content delete --uri content://com.google.android.gms.auth.accounts/accounts',
         "Delete GMS auth accounts"),
        ('content delete --uri content://com.android.contacts/raw_contacts --where "account_type=\'com.google\'"',
         "Delete Google contacts"),
        ('content delete --uri content://com.google.android.gsf.gservices --where "name=\'android_id\'"',
         "Delete GSF android_id"),
        # Clear credential storage
        ('pm clear com.android.providers.contacts', "Clear contacts provider"),
        ('pm clear com.google.android.gms', "Clear Google Play Services"),
        ('pm clear com.google.android.gsf', "Clear GSF"),
        ('pm clear com.android.vending', "Clear Play Store"),
        ('pm clear com.google.android.backuptransport', "Clear backup transport"),
        # Reset accounts database
        ('rm -f /data/system/users/0/accounts.db', "Delete accounts.db"),
        ('rm -f /data/system/users/0/accounts.db-journal', "Delete accounts journal"),
        ('rm -f /data/system/sync/accounts.xml', "Delete sync accounts"),
        # Clear account manager
        ('pm clear com.android.providers.settings', "Clear settings provider"),
        # Force stop and clear all Google services
        ('am force-stop com.google.android.gms', "Force stop GMS"),
        ('am force-stop com.google.android.gsf', "Force stop GSF"),
        ('am force-stop com.google.android.setupwizard', "Force stop setup wizard"),
    ]

    success = 0
    for cmd, desc in cmds:
        out, rc = _run_adb_rc(f'shell {cmd}')
        steps.append(f"  {desc} (rc={rc})")
        if rc == 0:
            success += 1

    return success >= 5


def _frp_method_setup_wizard_kill(steps: List[str]) -> bool:
    """
    Method 10: Kill and replace setup wizard.

    Aggressively disables all setup wizard variants, clears their data,
    hides them, and marks setup as complete.
    """
    logger.info("FRP Method 10: Setup wizard kill")
    steps.append("Method 10: Setup wizard kill started")

    # All known setup wizard packages
    wizards = [
        "com.google.android.setupwizard",
        "com.samsung.android.setupwizard",
        "com.oplus.setupwizard",
        "com.oneplus.setupwizard",
        "com.coloros.setupwizard",
        "com.miui.cloudservice",
        "com.vivo.setupwizard",
        "com.motorola.setupwizard",
        "com.nothing.setupwizard",
        "com.android.provision",
        "com.android.managedprovisioning",
        "com.google.android.partnersetup",
    ]

    killed = 0
    for pkg in wizards:
        # Force stop
        _run_adb_rc(f'shell am force-stop {pkg}')
        # Clear data
        out1, rc1 = _run_adb_rc(f'shell pm clear {pkg}')
        # Disable
        out2, rc2 = _run_adb_rc(f'shell pm disable-user --user 0 {pkg}')
        # Hide
        out3, rc3 = _run_adb_rc(f'shell pm hide {pkg}')
        # Uninstall for user
        out4, rc4 = _run_adb_rc(f'shell pm uninstall -k --user 0 {pkg}')

        if rc1 == 0 or rc2 == 0 or rc4 == 0:
            killed += 1
            steps.append(f"  Killed: {pkg}")
        else:
            steps.append(f"  Skip: {pkg} (not found)")

    # Mark setup complete
    _run_adb_rc('shell settings put global device_provisioned 1')
    _run_adb_rc('shell settings put secure user_setup_complete 1')
    _run_adb_rc('shell settings put global setup_wizard_has_run 1')

    # Try to go HOME
    _run_adb_rc('shell am start -a android.intent.action.MAIN -c android.intent.category.HOME')
    steps.append("  Sent HOME intent")

    steps.append(f"  Killed {killed} setup wizard packages")
    return killed >= 2


def _frp_method_fastboot_full(steps: List[str]) -> bool:
    """
    Method 11: Comprehensive fastboot partition erase.

    Tries bootloader unlock + erases all FRP-related partitions
    including brand-specific ones.
    """
    logger.info("FRP Method 11: Fastboot full erase")
    steps.append("Method 11: Fastboot comprehensive erase started")

    if not _check_fastboot_connection():
        _run_adb("reboot bootloader")
        steps.append("Sent reboot-bootloader, waiting...")
        time.sleep(REBOOT_WAIT)

        if not _check_fastboot_connection():
            steps.append("Fastboot not available -- skipped")
            return False

    steps.append("Device in fastboot mode")

    # Try bootloader unlock first
    for cmd in ["flashing unlock", "oem unlock", "flashing unlock_critical"]:
        out, rc = _run_fastboot_rc(cmd)
        steps.append(f"  fastboot {cmd} (rc={rc})")
        if rc == 0:
            steps.append(f"  Bootloader unlock SUCCESS via {cmd}")
            break

    # Erase all FRP-related partitions
    erased = 0
    for part in FRP_FASTBOOT_PARTITIONS:
        out, rc = _run_fastboot_rc(f"erase {part}")
        steps.append(f"  erase {part} (rc={rc})")
        if rc == 0:
            erased += 1

    if erased > 0:
        steps.append(f"  Erased {erased} partitions")
        return True

    steps.append("  No partitions erased")
    return False


def _frp_method_factory_reset_fastboot(steps: List[str]) -> bool:
    """
    Method 12: Complete factory reset via fastboot (nuclear option).

    Erases userdata, cache, metadata — removes ALL data including FRP.
    This is the last resort.
    """
    logger.info("FRP Method 12: Fastboot factory reset")
    steps.append("Method 12: Fastboot factory reset (NUCLEAR)")
    steps.append("WARNING: This will ERASE ALL DATA on the device")

    if not _check_fastboot_connection():
        _run_adb("reboot bootloader")
        steps.append("Rebooting to bootloader...")
        time.sleep(REBOOT_WAIT)

        if not _check_fastboot_connection():
            steps.append("Fastboot not available -- skipped")
            return False

    # Erase everything
    partitions = ["userdata", "cache", "metadata"] + FRP_FASTBOOT_PARTITIONS
    erased = 0
    for part in partitions:
        out, rc = _run_fastboot_rc(f"erase {part}")
        steps.append(f"  erase {part} (rc={rc})")
        if rc == 0:
            erased += 1

    if erased < 1:
        # Last resort: fastboot -w
        out, rc = _run_fastboot_rc("-w")
        steps.append(f"  fastboot -w (rc={rc})")
        if rc == 0:
            return True

    return erased >= 2


def remove_frp(
    callback: Optional[Callable[[float, str], None]] = None,
) -> FRPResult:
    """
    Attempt to remove FRP (Factory Reset Protection) from the connected device.

    Enhanced with 12 methods in sequence from least to most invasive:
        1.  ADB content provider delete
        2.  Settings activity bypass
        3.  Package manager disable
        4.  Fastboot FRP partition erase
        5.  Direct DB/settings manipulation
        6.  Intent flood bypass
        7.  Accessibility bypass
        8.  Emergency dialer bypass
        9.  Account manager manipulation
        10. Setup wizard kill
        11. Fastboot comprehensive erase (all FRP partitions)
        12. Fastboot factory reset (nuclear — wipes all data)

    Args:
        callback: Optional progress callback ``(pct: float, msg: str)``.

    Returns:
        Populated :class:`FRPResult`.
    """
    result = FRPResult()
    steps: List[str] = []

    def _cb(pct: float, msg: str) -> None:
        logger.info("[%3.0f%%] %s", pct * 100, msg)
        if callback:
            callback(pct, msg)

    _cb(0.0, "Starting ENHANCED FRP removal (12 methods)...")

    # Pre-check: verify connection
    connected, mode = _check_adb_connection()
    fastboot_connected = _check_fastboot_connection()
    result.device_brand = _get_device_brand() if connected and mode == "normal" else ""

    if not connected and not fastboot_connected:
        result.error = "No device connected via ADB or fastboot"
        result.steps_performed = ["Connection check failed"]
        _cb(1.0, "Failed: no device connected")
        return result

    steps.append(f"Device connected (ADB: {mode}, Fastboot: {fastboot_connected})")

    # Define all 12 methods with names and progress ranges
    methods = [
        ("Content Provider Delete", _frp_method_content_provider, 0.03, 0.10),
        ("Settings Activity Bypass", _frp_method_settings_bypass, 0.10, 0.17),
        ("Package Manager Disable", _frp_method_package_disable, 0.17, 0.25),
        ("Fastboot FRP Erase", _frp_method_fastboot_erase, 0.25, 0.33),
        ("DB/Settings Manipulation", _frp_method_db_manipulation, 0.33, 0.40),
        ("Intent Flood Bypass", _frp_method_intent_flood, 0.40, 0.48),
        ("Accessibility Bypass", _frp_method_accessibility_bypass, 0.48, 0.55),
        ("Emergency Dialer Bypass", _frp_method_emergency_dialer, 0.55, 0.63),
        ("Account Manager Manipulation", _frp_method_account_manager, 0.63, 0.70),
        ("Setup Wizard Kill", _frp_method_setup_wizard_kill, 0.70, 0.78),
        ("Fastboot Full Erase", _frp_method_fastboot_full, 0.78, 0.88),
        ("Fastboot Factory Reset", _frp_method_factory_reset_fastboot, 0.88, 0.98),
    ]

    for i, (name, method, pct_start, pct_end) in enumerate(methods):
        _cb(pct_start, f"Method {i+1}/12: {name}...")
        result.methods_tried += 1
        steps.append(f"--- Method {i+1}: {name} ---")

        try:
            success = method(steps)
            if success:
                result.success = True
                result.method_used = name.lower().replace(" ", "_")
                result.reboot_required = True
                result.steps_performed = steps
                _cb(pct_end, f"Method {i+1} ({name}) SUCCEEDED!")
                _cb(1.0, f"FRP removal complete via {name}")
                return result
            else:
                steps.append(f"Method {i+1} ({name}) -- did not succeed")
        except Exception as exc:
            steps.append(f"Method {i+1} exception: {exc}")
            logger.exception(f"FRP Method {i+1} ({name}) failed")

        _cb(pct_end, f"Method {i+1} did not succeed, trying next...")

    # All methods failed
    result.steps_performed = steps
    result.error = (
        f"All {result.methods_tried} FRP removal methods failed. "
        "Options remaining:\n"
        "  - EDL flash with MSM Download Tool (manufacturer-specific)\n"
        "  - Firmware flash via QFIL/SP Flash Tool\n"
        "  - Contact manufacturer with proof of purchase"
    )
    _cb(1.0, "FRP removal failed -- all 12 methods exhausted")
    return result


# ---------------------------------------------------------------------------
#  Screen Lock Removal  --  Three Methods
# ---------------------------------------------------------------------------

def _screen_lock_method_locksettings(
    lock_type: str,
    steps: List[str],
) -> bool:
    """
    Method 1: Use ``locksettings clear`` command (Android 8.0+).

    This is the cleanest method and works on Android 8+ devices
    when ADB shell has sufficient privileges.
    """
    logger.info("Screen lock Method 1: locksettings clear")
    steps.append("Method 1: locksettings clear (Android 8+)")

    sdk = _get_sdk_version()
    if sdk < 26:
        steps.append(f"SDK level {sdk} < 26 (Android 8) -- method not available")
        return False

    # Try clearing without a current password/pattern
    out, rc = _run_adb_rc('shell locksettings clear')
    steps.append(f"locksettings clear (rc={rc}): {out[:120]}")

    if rc == 0 and "error" not in out.lower():
        steps.append("Lock cleared via locksettings")

        # Also disable the lock setting
        out2, rc2 = _run_adb_rc(
            'shell locksettings set-disabled true'
        )
        steps.append(f"locksettings set-disabled true (rc={rc2})")

        # Reset the password type in settings
        out3, rc3 = _run_adb_rc(
            'shell settings put secure lockscreen.password_type 65536'
        )
        steps.append(f"Reset password_type to 65536/swipe (rc={rc3})")

        return True

    # Some devices require specifying an empty old credential
    out_alt, rc_alt = _run_adb_rc('shell locksettings clear --old ""')
    steps.append(f'locksettings clear --old "" (rc={rc_alt}): {out_alt[:120]}')

    if rc_alt == 0 and "error" not in out_alt.lower():
        steps.append("Lock cleared with empty old credential")
        return True

    steps.append("locksettings clear did not succeed")
    return False


def _screen_lock_method_delete_files(
    lock_type: str,
    steps: List[str],
) -> bool:
    """
    Method 2: Delete lock database and key files via ADB root.

    Requires root access (``adb root`` or rooted device).  Removes
    locksettings.db, gesture.key, password.key, and gatekeeper key files.
    """
    logger.info("Screen lock Method 2: Delete lock files (root required)")
    steps.append("Method 2: Delete lock files (requires root)")

    # Check / obtain root
    if not _check_root_access():
        steps.append("Root access not available -- method skipped")
        return False

    steps.append("Root access confirmed")

    deleted_count = 0
    for lock_file in LOCK_FILES:
        # Check if file exists first
        check = _shell(f"ls {lock_file} 2>/dev/null")
        if not check or "No such file" in check:
            steps.append(f"File not found: {lock_file}")
            continue

        out, rc = _run_adb_rc(f'shell rm -f {lock_file}')
        steps.append(f"Deleted {lock_file} (rc={rc})")
        if rc == 0:
            deleted_count += 1
        else:
            logger.warning("Failed to delete %s: %s", lock_file, out)

    # Also try to reset the locksettings database via sqlite
    _run_adb_rc(
        'shell sqlite3 /data/system/locksettings.db '
        '"UPDATE locksettings SET value=0 WHERE name=\'lockscreen.password_type\'"'
    )
    steps.append("Reset password_type in locksettings.db via sqlite3")

    _run_adb_rc(
        'shell sqlite3 /data/system/locksettings.db '
        '"DELETE FROM locksettings WHERE name=\'lock_pattern_autolock\'"'
    )
    steps.append("Deleted lock_pattern_autolock from locksettings.db")

    _run_adb_rc(
        'shell sqlite3 /data/system/locksettings.db '
        '"DELETE FROM locksettings WHERE name LIKE \'lockscreen%\'"'
    )
    steps.append("Deleted all lockscreen entries from locksettings.db")

    if deleted_count > 0:
        steps.append(f"Deleted {deleted_count} lock file(s) -- reboot required")
        return True

    steps.append("No lock files were deleted")
    return False


def _screen_lock_method_factory_reset(
    lock_type: str,
    steps: List[str],
) -> Tuple[bool, bool]:
    """
    Method 3: Factory reset via fastboot erase userdata.

    This is the nuclear option -- it WIPES ALL USER DATA but guarantees
    lock removal.  The device must be in fastboot mode.

    Returns:
        (success, data_wiped) tuple.
    """
    logger.info("Screen lock Method 3: Fastboot factory reset")
    steps.append("Method 3: Fastboot erase userdata (FACTORY RESET)")
    steps.append("WARNING: This method ERASES ALL USER DATA")

    # Reboot to bootloader if not already there
    if not _check_fastboot_connection():
        _run_adb("reboot bootloader")
        steps.append("Rebooting to bootloader...")
        time.sleep(REBOOT_WAIT)

        if not _check_fastboot_connection():
            steps.append("Could not enter fastboot mode")
            return False, False

    steps.append("Device in fastboot mode")

    # Erase userdata partition
    out_ud, rc_ud = _run_fastboot_rc("erase userdata")
    steps.append(f"Fastboot erase userdata (rc={rc_ud}): {out_ud[:120]}")

    # Erase cache
    out_cache, rc_cache = _run_fastboot_rc("erase cache")
    steps.append(f"Fastboot erase cache (rc={rc_cache}): {out_cache[:120]}")

    # Erase metadata (encryption metadata)
    out_meta, rc_meta = _run_fastboot_rc("erase metadata")
    steps.append(f"Fastboot erase metadata (rc={rc_meta}): {out_meta[:120]}")

    if rc_ud == 0:
        steps.append("Factory reset successful via fastboot")
        return True, True

    # Alternative: try format instead of erase
    out_fmt, rc_fmt = _run_fastboot_rc("-w")
    steps.append(f"Fastboot -w (format userdata+cache) (rc={rc_fmt}): {out_fmt[:120]}")

    if rc_fmt == 0:
        steps.append("Factory reset successful via fastboot -w")
        return True, True

    steps.append("Fastboot factory reset did not succeed")
    return False, False


def remove_screen_lock(
    lock_type: str = "pattern",
    callback: Optional[Callable[[float, str], None]] = None,
) -> ScreenLockResult:
    """
    Remove the screen lock (pattern, PIN, or password) from the device.

    Tries methods in order of least-to-most destructive:
        1. ``locksettings clear`` (Android 8+, non-destructive)
        2. Delete lock files via ADB root (non-destructive)
        3. Fastboot erase userdata (factory reset -- WIPES DATA)

    Args:
        lock_type: The type of lock to remove ('pattern', 'pin', 'password').
                   Used for logging; all methods remove any lock type.
        callback:  Optional progress callback ``(pct: float, msg: str)``.

    Returns:
        Populated :class:`ScreenLockResult`.
    """
    result = ScreenLockResult()
    result.lock_type_removed = lock_type
    steps: List[str] = []

    def _cb(pct: float, msg: str) -> None:
        logger.info("[%3.0f%%] %s", pct * 100, msg)
        if callback:
            callback(pct, msg)

    _cb(0.0, f"Starting screen lock removal (type: {lock_type})...")

    # Verify connection
    connected, mode = _check_adb_connection()
    if not connected and not _check_fastboot_connection():
        result.error = "No device connected"
        result.steps_performed = ["Connection check failed"]
        _cb(1.0, "Failed: no device connected")
        return result

    steps.append(f"Device connected in {mode} mode")

    # Detect current lock
    if connected and mode == "normal":
        detected_lock = _detect_screen_lock_type()
        steps.append(f"Detected lock type: {detected_lock}")
        if detected_lock == "none":
            result.success = True
            result.method_used = "none_needed"
            result.lock_type_removed = "none"
            result.steps_performed = steps
            _cb(1.0, "No screen lock detected -- nothing to remove")
            return result
        result.lock_type_removed = detected_lock

    # ---- Method 1: locksettings clear ----------------------------------
    _cb(0.10, "Method 1: locksettings clear...")
    try:
        if _screen_lock_method_locksettings(lock_type, steps):
            result.success = True
            result.method_used = "locksettings_clear"
            result.reboot_required = True
            result.steps_performed = steps
            _cb(1.0, "Screen lock removed (locksettings)")
            return result
    except Exception as exc:
        steps.append(f"Method 1 exception: {exc}")
        logger.exception("Screen lock Method 1 failed")

    _cb(0.35, "Method 1 did not succeed, trying Method 2...")

    # ---- Method 2: Delete lock files ------------------------------------
    _cb(0.40, "Method 2: Delete lock files (requires root)...")
    try:
        if _screen_lock_method_delete_files(lock_type, steps):
            result.success = True
            result.method_used = "delete_lock_files"
            result.reboot_required = True
            result.steps_performed = steps
            _cb(1.0, "Screen lock removed (file deletion)")
            return result
    except Exception as exc:
        steps.append(f"Method 2 exception: {exc}")
        logger.exception("Screen lock Method 2 failed")

    _cb(0.65, "Method 2 did not succeed, trying Method 3 (factory reset)...")

    # ---- Method 3: Factory reset ----------------------------------------
    _cb(0.70, "Method 3: Fastboot factory reset (DATA WILL BE LOST)...")
    try:
        success, data_wiped = _screen_lock_method_factory_reset(lock_type, steps)
        if success:
            result.success = True
            result.method_used = "fastboot_factory_reset"
            result.reboot_required = True
            result.data_wiped = data_wiped
            result.steps_performed = steps
            _cb(1.0, "Screen lock removed (factory reset -- data wiped)")
            return result
    except Exception as exc:
        steps.append(f"Method 3 exception: {exc}")
        logger.exception("Screen lock Method 3 failed")

    # All methods failed
    result.steps_performed = steps
    result.error = (
        "All screen lock removal methods failed.  "
        "A firmware flash may be required."
    )
    _cb(1.0, "Screen lock removal failed")
    return result


# ---------------------------------------------------------------------------
#  Mi Account (Xiaomi) Check
# ---------------------------------------------------------------------------

def _parse_mi_packages() -> List[str]:
    """List installed Mi/Xiaomi cloud-related packages."""
    pkgs_raw = _shell("pm list packages com.miui.cloud")
    pkgs: List[str] = []
    for line in pkgs_raw.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkgs.append(line.replace("package:", "").strip())
    # Also check for Xiaomi account packages
    pkgs_raw2 = _shell("pm list packages com.xiaomi.account")
    for line in pkgs_raw2.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            pkg = line.replace("package:", "").strip()
            if pkg not in pkgs:
                pkgs.append(pkg)
    return pkgs


def _check_find_device_active() -> bool:
    """Check if Xiaomi Find Device service is active."""
    find_svc = _shell("dumpsys activity services com.xiaomi.finddevice")
    if find_svc and "ServiceRecord" in find_svc:
        return True
    # Also check the Find My Phone alternative package
    find_pkg = _shell("pm list packages com.miui.finddevice")
    if "com.miui.finddevice" in find_pkg:
        find_run = _shell("dumpsys activity services com.miui.finddevice")
        if find_run and "ServiceRecord" in find_run:
            return True
    return False


def check_mi_account(
    callback: Optional[Callable[[float, str], None]] = None,
) -> MiAccountResult:
    """
    Check Xiaomi Mi Account binding status on the connected device.

    Reads system properties and package states to determine whether
    a Mi Account is bound.  A bound Mi Account can trigger a
    device lock similar to FRP on non-Xiaomi devices.

    Args:
        callback: Optional progress callback ``(pct: float, msg: str)``.

    Returns:
        Populated :class:`MiAccountResult`.
    """
    result = MiAccountResult()

    def _cb(pct: float, msg: str) -> None:
        logger.info("[%3.0f%%] %s", pct * 100, msg)
        if callback:
            callback(pct, msg)

    _cb(0.0, "Checking Mi Account status...")

    # Verify connection
    connected, mode = _check_adb_connection()
    result.connected = connected
    if not connected or mode not in ("normal", "recovery"):
        result.error = f"Device not connected or in unsupported mode ({mode})"
        _cb(1.0, "Mi account check failed: no device")
        return result

    # Device info
    result.device_model = _get_device_model()
    _cb(0.10, f"Device: {result.device_model}")

    # MIUI version
    result.miui_version = _shell("getprop ro.miui.ui.version.name")
    if not result.miui_version:
        result.miui_version = _shell("getprop ro.miui.ui.version.code")
    _cb(0.20, f"MIUI version: {result.miui_version or 'unknown'}")

    # Check Mi Account system properties
    _cb(0.30, "Reading Mi Account properties...")
    for prop in MI_ACCOUNT_PROPS:
        val = _shell(f"getprop {prop}")
        logger.debug("%s = %s", prop, val)
        if val and val not in ("", "null", "0"):
            if "user_id" in prop or "account" in prop:
                result.mi_account_bound = True
                if "user_id" in prop:
                    result.mi_user_id = val
                elif "account" in prop:
                    result.mi_email = val
            elif "has_micloud" in prop:
                result.micloud_enabled = val == "1"

    _cb(0.50, f"Mi account bound: {result.mi_account_bound}")

    # Check cloud service package state
    _cb(0.55, "Checking Mi Cloud service packages...")
    cloud_dump = _shell("dumpsys account")
    if "com.xiaomi" in cloud_dump.lower() or "xiaomi.com" in cloud_dump:
        result.mi_account_bound = True
        # Try to extract the account email
        mi_emails = re.findall(
            r"name=([^\s,}]+@[^\s,}]*xiaomi[^\s,}]*)", cloud_dump, re.IGNORECASE
        )
        if mi_emails and not result.mi_email:
            result.mi_email = mi_emails[0]
        # Also look for non-xiaomi emails tied to mi account
        if not result.mi_email:
            mi_emails_alt = re.findall(
                r"Account\s*\{[^}]*name=([^,}]+@[^,}]+)[^}]*type=com\.xiaomi",
                cloud_dump,
                re.IGNORECASE,
            )
            if mi_emails_alt:
                result.mi_email = mi_emails_alt[0]

    _cb(0.70, "Checking Mi Account packages...")
    result.mi_account_packages = _parse_mi_packages()

    # Check cloud service state
    cloud_state = _shell("dumpsys activity services com.miui.cloudservice")
    if cloud_state and "ServiceRecord" in cloud_state:
        result.micloud_enabled = True
    _cb(0.80, f"MiCloud enabled: {result.micloud_enabled}")

    # Check Find Device
    _cb(0.85, "Checking Find Device status...")
    result.find_device_active = _check_find_device_active()
    _cb(0.90, f"Find Device active: {result.find_device_active}")

    # If Find Device is active, the Mi account is definitely bound
    if result.find_device_active:
        result.mi_account_bound = True

    _cb(1.0, f"Mi Account check complete (bound={result.mi_account_bound})")
    return result


# ---------------------------------------------------------------------------
#  Samsung Knox Status Check
# ---------------------------------------------------------------------------

def _parse_knox_version() -> str:
    """Read the Knox SDK version from system properties."""
    knox_ver = _shell("getprop net.knoxvpn.tun.ver")
    if not knox_ver:
        knox_ver = _shell("getprop ro.config.knox")
    if not knox_ver:
        knox_ver = _shell("getprop persist.security.ams.enforcing")
    return knox_ver or ""


def _check_knox_container() -> bool:
    """Check if Knox container (Secure Folder/Work Profile) is active."""
    # Check Knox container service
    knox_svc = _shell("dumpsys activity services com.samsung.knox.container")
    if knox_svc and "ServiceRecord" in knox_svc:
        return True
    # Fallback: check package existence
    knox_pkg = _shell("pm list packages com.samsung.knox.container")
    return "com.samsung.knox.container" in knox_pkg


def _check_secure_folder() -> bool:
    """Check if Samsung Secure Folder is active."""
    sf_pkg = _shell("pm list packages com.samsung.knox.securefolder")
    if "com.samsung.knox.securefolder" not in sf_pkg:
        return False
    # Check if it's actively running
    sf_svc = _shell("dumpsys activity services com.samsung.knox.securefolder")
    return bool(sf_svc and "ServiceRecord" in sf_svc)


def _check_dm_verity() -> bool:
    """Check if dm-verity is enabled (Android Verified Boot)."""
    verity = _shell("getprop ro.boot.veritymode")
    if verity == "enforcing":
        return True
    avb = _shell("getprop ro.boot.avb_version")
    if avb:
        return True
    return False


def _check_oem_unlock() -> bool:
    """Check if OEM unlock is enabled in developer options."""
    oem = _shell("settings get global oem_unlock_enabled")
    return oem == "1"


def check_knox_status(
    callback: Optional[Callable[[float, str], None]] = None,
) -> KnoxResult:
    """
    Check Samsung Knox warranty and security status.

    Knox is Samsung's security platform.  A 'tripped' Knox warranty
    bit (0x1) indicates the device has been tampered with (custom
    firmware, root, etc.) and is irreversible on most Samsung devices.

    Checks performed:
        - Knox warranty bit (ro.boot.warranty_bit)
        - Knox version and container status
        - Secure Folder status
        - Bootloader lock state
        - dm-verity / AVB status
        - OEM unlock toggle

    Args:
        callback: Optional progress callback ``(pct: float, msg: str)``.

    Returns:
        Populated :class:`KnoxResult`.
    """
    result = KnoxResult()

    def _cb(pct: float, msg: str) -> None:
        logger.info("[%3.0f%%] %s", pct * 100, msg)
        if callback:
            callback(pct, msg)

    _cb(0.0, "Checking Samsung Knox status...")

    # Verify connection
    connected, mode = _check_adb_connection()
    result.connected = connected
    if not connected or mode not in ("normal", "recovery"):
        result.error = f"Device not connected or in unsupported mode ({mode})"
        _cb(1.0, "Knox check failed: no device")
        return result

    # Device identity
    result.device_model = _get_device_model()
    result.firmware_version = _shell("getprop ro.build.display.id")
    _cb(0.10, f"Device: {result.device_model}")

    # Knox warranty bit -- the key indicator
    _cb(0.20, "Reading Knox warranty bit...")
    warranty_bit = ""
    for prop in KNOX_PROPS:
        val = _shell(f"getprop {prop}")
        logger.debug("%s = %s", prop, val)
        if "warranty" in prop and val:
            warranty_bit = val
            break

    if warranty_bit:
        result.warranty_bit = warranty_bit
        # 0x0 = not tripped; 0x1 = tripped
        try:
            bit_int = int(warranty_bit, 0)  # handles "0x0", "0x1", "0", "1"
            result.knox_tripped = bit_int != 0
        except (ValueError, TypeError):
            result.knox_tripped = warranty_bit.strip() not in ("0", "0x0", "")
    else:
        # If property not found, check /proc/knox
        knox_proc = _shell("cat /proc/knox/knox_state 2>/dev/null")
        if knox_proc:
            result.warranty_bit = knox_proc.strip()
            result.knox_tripped = "1" in knox_proc
        else:
            result.warranty_bit = "unknown"

    _cb(0.40, f"Knox warranty bit: {result.warranty_bit} "
               f"({'TRIPPED' if result.knox_tripped else 'intact'})")

    # Knox version
    _cb(0.50, "Reading Knox version...")
    result.knox_version = _parse_knox_version()
    _cb(0.55, f"Knox version: {result.knox_version or 'unknown'}")

    # Knox container
    _cb(0.60, "Checking Knox container status...")
    result.knox_container_active = _check_knox_container()
    _cb(0.65, f"Knox container active: {result.knox_container_active}")

    # Secure Folder
    _cb(0.70, "Checking Secure Folder status...")
    result.secure_folder_active = _check_secure_folder()
    _cb(0.75, f"Secure Folder active: {result.secure_folder_active}")

    # Bootloader status
    _cb(0.80, "Checking bootloader lock state...")
    bl_locked = _shell("getprop ro.boot.flash.locked")
    if bl_locked == "1":
        result.bootloader_locked = True
    elif bl_locked == "0":
        result.bootloader_locked = False
    else:
        # Fallback: check verified boot state
        vb_state = _shell("getprop ro.boot.verifiedbootstate")
        result.bootloader_locked = vb_state != "orange"

    _cb(0.85, f"Bootloader locked: {result.bootloader_locked}")

    # dm-verity
    _cb(0.88, "Checking dm-verity / AVB status...")
    result.dm_verity_enabled = _check_dm_verity()
    _cb(0.92, f"dm-verity enabled: {result.dm_verity_enabled}")

    # OEM unlock
    _cb(0.95, "Checking OEM unlock toggle...")
    result.oem_unlock_enabled = _check_oem_unlock()
    _cb(0.98, f"OEM unlock enabled: {result.oem_unlock_enabled}")

    _cb(1.0, f"Knox status check complete (tripped={result.knox_tripped})")
    return result


# ---------------------------------------------------------------------------
#  Utility / Batch Operations
# ---------------------------------------------------------------------------

def reboot_device(mode: str = "normal") -> bool:
    """
    Reboot the device into the specified mode.

    Args:
        mode: One of 'normal', 'recovery', 'bootloader', 'fastboot',
              'download' (Samsung Odin mode).

    Returns:
        True if the reboot command was sent successfully.
    """
    logger.info("Rebooting device into %s mode", mode)

    cmd_map: Dict[str, str] = {
        "normal": "reboot",
        "recovery": "reboot recovery",
        "bootloader": "reboot bootloader",
        "fastboot": "reboot fastboot",
        "download": "reboot download",
        "edl": "reboot edl",
    }

    cmd = cmd_map.get(mode.lower())
    if cmd is None:
        logger.error("Unknown reboot mode: %s", mode)
        return False

    # Check if we're in fastboot mode
    if _check_fastboot_connection():
        if mode == "normal":
            out, rc = _run_fastboot_rc("reboot")
        elif mode == "bootloader":
            out, rc = _run_fastboot_rc("reboot-bootloader")
        else:
            out, rc = _run_fastboot_rc(f"oem reboot-{mode}")
        return rc == 0

    out, rc = _run_adb_rc(cmd)
    return rc == 0


def get_full_report(
    callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Generate a comprehensive security/lock report for the device.

    Runs all checks and returns a dict containing every result object.

    Args:
        callback: Optional progress callback ``(pct: float, msg: str)``.

    Returns:
        Dictionary with keys 'lock_status', 'mi_account', 'knox_status',
        and 'device_info'.
    """
    def _cb(pct: float, msg: str) -> None:
        logger.info("[%3.0f%%] %s", pct * 100, msg)
        if callback:
            callback(pct, msg)

    _cb(0.0, "Generating full security report...")

    # Lock status (this already includes Mi/Knox sub-checks)
    _cb(0.05, "Running lock status check...")
    lock_status = check_lock_status(
        callback=lambda p, m: _cb(0.05 + p * 0.50, m) if callback else None,
    )

    report: Dict[str, Any] = {
        "device_info": {
            "brand": lock_status.device_brand,
            "model": lock_status.device_model,
            "android_version": lock_status.android_version,
            "adb_mode": lock_status.adb_mode,
            "root_access": lock_status.root_access,
            "bootloader_unlocked": lock_status.bootloader_unlocked,
        },
        "lock_status": lock_status,
    }

    # Mi Account (detailed, even if already checked in lock_status)
    if any(kw in lock_status.device_brand.lower()
           for kw in ("xiaomi", "redmi", "poco")):
        _cb(0.60, "Running detailed Mi Account check...")
        mi_result = check_mi_account(
            callback=lambda p, m: _cb(0.60 + p * 0.15, m) if callback else None,
        )
        report["mi_account"] = mi_result
    else:
        report["mi_account"] = None

    # Knox (detailed)
    if "samsung" in lock_status.device_brand.lower():
        _cb(0.80, "Running detailed Knox check...")
        knox_result = check_knox_status(
            callback=lambda p, m: _cb(0.80 + p * 0.15, m) if callback else None,
        )
        report["knox_status"] = knox_result
    else:
        report["knox_status"] = None

    _cb(1.0, "Full security report complete")
    return report


def format_lock_status_text(status: LockStatusResult) -> str:
    """
    Format a :class:`LockStatusResult` into a human-readable text report.

    Useful for CLI output or logging.
    """
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  DEVICE SECURITY STATUS REPORT")
    lines.append("=" * 60)

    if not status.connected:
        lines.append(f"  ERROR: {status.error or 'No device connected'}")
        lines.append("=" * 60)
        return "\n".join(lines)

    lines.append(f"  Device:         {status.device_brand} {status.device_model}")
    lines.append(f"  Android:        {status.android_version}")
    lines.append(f"  ADB Mode:       {status.adb_mode}")
    lines.append(f"  Root Access:    {'Yes' if status.root_access else 'No'}")
    lines.append(f"  Bootloader:     {'UNLOCKED' if status.bootloader_unlocked else 'Locked'}")
    lines.append("-" * 60)
    lines.append(f"  FRP Enabled:    {'YES' if status.frp_enabled else 'No'}")
    lines.append(f"  Screen Lock:    {status.screen_lock_type}")
    lines.append(f"  Encryption:     {status.encryption_status}")
    lines.append(f"  Secure Startup: {'Yes' if status.secure_startup else 'No'}")
    lines.append("-" * 60)
    lines.append(f"  Google Accounts: {len(status.google_accounts)}")
    for acct in status.google_accounts:
        lines.append(f"    - {acct}")
    lines.append(f"  Samsung Acct:   {'Yes' if status.samsung_account else 'No'}")
    lines.append(f"  Mi Account:     {'BOUND' if status.mi_account_bound else 'None'}")
    lines.append(f"  Knox Tripped:   {'YES' if status.knox_tripped else 'No'}")
    lines.append("=" * 60)

    return "\n".join(lines)


def format_frp_result_text(result: FRPResult) -> str:
    """Format an :class:`FRPResult` into a human-readable text report."""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  FRP REMOVAL RESULT")
    lines.append("=" * 60)
    lines.append(f"  Success:        {'YES' if result.success else 'NO'}")
    lines.append(f"  Method Used:    {result.method_used or 'none'}")
    lines.append(f"  Methods Tried:  {result.methods_tried}")
    lines.append(f"  Reboot Needed:  {'Yes' if result.reboot_required else 'No'}")
    if result.error:
        lines.append(f"  Error:          {result.error}")
    lines.append("-" * 60)
    lines.append("  Steps Performed:")
    for i, step in enumerate(result.steps_performed, 1):
        lines.append(f"    {i:3d}. {step}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_screen_lock_result_text(result: ScreenLockResult) -> str:
    """Format a :class:`ScreenLockResult` into a human-readable text report."""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  SCREEN LOCK REMOVAL RESULT")
    lines.append("=" * 60)
    lines.append(f"  Success:        {'YES' if result.success else 'NO'}")
    lines.append(f"  Lock Removed:   {result.lock_type_removed}")
    lines.append(f"  Method Used:    {result.method_used or 'none'}")
    lines.append(f"  Reboot Needed:  {'Yes' if result.reboot_required else 'No'}")
    lines.append(f"  Data Wiped:     {'YES' if result.data_wiped else 'No'}")
    if result.error:
        lines.append(f"  Error:          {result.error}")
    lines.append("-" * 60)
    lines.append("  Steps Performed:")
    for i, step in enumerate(result.steps_performed, 1):
        lines.append(f"    {i:3d}. {step}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_mi_account_result_text(result: MiAccountResult) -> str:
    """Format a :class:`MiAccountResult` into a human-readable text report."""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  MI ACCOUNT STATUS")
    lines.append("=" * 60)
    lines.append(f"  Device:         {result.device_model}")
    lines.append(f"  MIUI Version:   {result.miui_version or 'unknown'}")
    lines.append(f"  Mi Account:     {'BOUND' if result.mi_account_bound else 'None'}")
    if result.mi_user_id:
        lines.append(f"  Mi User ID:     {result.mi_user_id}")
    if result.mi_email:
        lines.append(f"  Mi Email:       {result.mi_email}")
    lines.append(f"  MiCloud:        {'Active' if result.micloud_enabled else 'Inactive'}")
    lines.append(f"  Find Device:    {'Active' if result.find_device_active else 'Inactive'}")
    lines.append(f"  Mi Packages:    {len(result.mi_account_packages)}")
    for pkg in result.mi_account_packages:
        lines.append(f"    - {pkg}")
    if result.error:
        lines.append(f"  Error:          {result.error}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_knox_result_text(result: KnoxResult) -> str:
    """Format a :class:`KnoxResult` into a human-readable text report."""
    lines: List[str] = []
    lines.append("=" * 60)
    lines.append("  SAMSUNG KNOX STATUS")
    lines.append("=" * 60)
    lines.append(f"  Device:         {result.device_model}")
    lines.append(f"  Firmware:       {result.firmware_version}")
    lines.append(f"  Knox Tripped:   {'YES' if result.knox_tripped else 'No'}")
    lines.append(f"  Warranty Bit:   {result.warranty_bit}")
    lines.append(f"  Knox Version:   {result.knox_version or 'unknown'}")
    lines.append(f"  Knox Container: {'Active' if result.knox_container_active else 'Inactive'}")
    lines.append(f"  Secure Folder:  {'Active' if result.secure_folder_active else 'Inactive'}")
    lines.append(f"  Bootloader:     {'Locked' if result.bootloader_locked else 'UNLOCKED'}")
    lines.append(f"  dm-verity:      {'Enabled' if result.dm_verity_enabled else 'Disabled'}")
    lines.append(f"  OEM Unlock:     {'Enabled' if result.oem_unlock_enabled else 'Disabled'}")
    if result.error:
        lines.append(f"  Error:          {result.error}")
    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Module-level convenience
# ---------------------------------------------------------------------------

__all__ = [
    # Data classes
    "LockStatusResult",
    "FRPResult",
    "ScreenLockResult",
    "MiAccountResult",
    "KnoxResult",
    # Main functions
    "check_lock_status",
    "remove_frp",
    "remove_screen_lock",
    "check_mi_account",
    "check_knox_status",
    # Utilities
    "reboot_device",
    "get_full_report",
    # Formatters
    "format_lock_status_text",
    "format_frp_result_text",
    "format_screen_lock_result_text",
    "format_mi_account_result_text",
    "format_knox_result_text",
]
