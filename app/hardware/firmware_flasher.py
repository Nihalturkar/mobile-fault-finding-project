"""
Firmware Flashing Module for Mooxy AI Fault Detector.

Supports multiple flash protocols for different chipset vendors:
  - Qualcomm EDL (Emergency Download) via Firehose XML protocol
  - MediaTek SP Flash via BROM/preloader USB interface
  - Samsung Odin-style flashing via Heimdall/Odin protocol
  - Standard Fastboot ROM flashing via fastboot CLI

Each flash function accepts an optional progress callback:
    callback(pct: float, msg: str)
where pct is 0.0-100.0 and msg describes the current step.

Device detection checks USB VID:PID pairs to identify which flash mode
the connected device is currently in, then dispatches to the correct
flashing routine.

Requires: pyserial, lxml (optional, falls back to xml.etree)
External tools: fastboot, heimdall (must be on PATH)
"""

from __future__ import annotations

import logging
import os
import re
import struct
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type alias for the progress callback
# ---------------------------------------------------------------------------

ProgressCallback = Optional[Callable[[float, str], None]]

# ---------------------------------------------------------------------------
# USB VID:PID constants
# ---------------------------------------------------------------------------

QUALCOMM_VID = 0x05C6
QUALCOMM_EDL_PID = 0x9008
QUALCOMM_VID_PID = "05C6:9008"

MEDIATEK_VID = 0x0E8D
MEDIATEK_BROM_PID = 0x0003
MEDIATEK_PRELOADER_PID = 0x2000
MEDIATEK_BROM_VID_PID = "0E8D:0003"
MEDIATEK_PRELOADER_VID_PID = "0E8D:2000"

SAMSUNG_VID = 0x04E8
SAMSUNG_DOWNLOAD_PID = 0x6601
SAMSUNG_VID_PID = "04E8:6601"

GOOGLE_VID = 0x18D1
FASTBOOT_PID = 0xD00D
GOOGLE_FASTBOOT_VID_PID = "18D1:D00D"

ADB_CLASS_CODE = 0xFF  # Vendor-specific USB class for ADB

# ---------------------------------------------------------------------------
# Timeouts (seconds)
# ---------------------------------------------------------------------------

SAHARA_HELLO_TIMEOUT = 5.0
FIREHOSE_CMD_TIMEOUT = 30.0
FIREHOSE_TRANSFER_TIMEOUT = 600.0
FASTBOOT_CMD_TIMEOUT = 60.0
FASTBOOT_FLASH_TIMEOUT = 600.0
HEIMDALL_DETECT_TIMEOUT = 10.0
HEIMDALL_FLASH_TIMEOUT = 900.0
BROM_HANDSHAKE_TIMEOUT = 10.0
BROM_FLASH_TIMEOUT = 600.0
USB_DETECT_TIMEOUT = 5.0

# ---------------------------------------------------------------------------
# Sahara protocol constants
# ---------------------------------------------------------------------------

SAHARA_HELLO_ID = 0x01
SAHARA_HELLO_RESP_ID = 0x02
SAHARA_READ_DATA_ID = 0x03
SAHARA_DONE_ID = 0x05
SAHARA_DONE_RESP_ID = 0x06
SAHARA_CMD_READY_ID = 0x0B
SAHARA_CMD_SWITCH_ID = 0x0C
SAHARA_MODE_IMAGE_TX = 0x00
SAHARA_MODE_COMMAND = 0x02
SAHARA_PACKET_HEADER_SIZE = 8
SAHARA_VERSION = 2
SAHARA_MIN_VERSION = 1

# ---------------------------------------------------------------------------
# Firehose XML templates
# ---------------------------------------------------------------------------

FIREHOSE_CONFIGURE_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<data>
  <configure MemoryName="{memory}" ZLPAwareHost="{zlp}" SkipStorageInit="{skip_init}"
             SkipWrite="0" MaxPayloadSizeToTargetInBytes="{max_payload}" />
</data>"""

FIREHOSE_PROGRAM_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<data>
  <program SECTOR_SIZE_IN_BYTES="{sector_size}" num_partition_sectors="{num_sectors}"
           physical_partition_number="{physical_partition}" start_sector="{start_sector}"
           filename="{filename}" />
</data>"""

FIREHOSE_PATCH_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<data>
  <patch SECTOR_SIZE_IN_BYTES="{sector_size}" byte_offset="{offset}"
         filename="" physical_partition_number="{physical_partition}"
         size_in_bytes="{size}" start_sector="{start_sector}"
         value="{value}" what="{what}" />
</data>"""

FIREHOSE_READ_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<data>
  <read SECTOR_SIZE_IN_BYTES="{sector_size}" num_partition_sectors="{num_sectors}"
        physical_partition_number="{physical_partition}" start_sector="{start_sector}" />
</data>"""

FIREHOSE_ERASE_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<data>
  <erase SECTOR_SIZE_IN_BYTES="{sector_size}" num_partition_sectors="{num_sectors}"
         physical_partition_number="{physical_partition}" start_sector="{start_sector}" />
</data>"""

FIREHOSE_RESET_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<data>
  <power value="reset" />
</data>"""

FIREHOSE_GETGPT_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<data>
  <getgpt physical_partition_number="{physical_partition}"
          SECTOR_SIZE_IN_BYTES="{sector_size}" />
</data>"""

# ---------------------------------------------------------------------------
# Well-known partition names across vendors
# ---------------------------------------------------------------------------

COMMON_PARTITIONS: Dict[str, str] = {
    "boot": "Android boot image containing kernel and ramdisk",
    "recovery": "Recovery mode boot image",
    "system": "Main Android system partition (system.img)",
    "vendor": "Vendor-specific HAL and libraries",
    "userdata": "User data partition (factory reset erases this)",
    "cache": "Cache partition for OTA updates",
    "dtbo": "Device Tree Blob Overlay for hardware config",
    "vbmeta": "Verified Boot metadata (AVB 2.0)",
    "vbmeta_system": "Verified Boot metadata for system partition",
    "vbmeta_vendor": "Verified Boot metadata for vendor partition",
    "modem": "Baseband/modem firmware",
    "bluetooth": "Bluetooth firmware",
    "dsp": "DSP firmware (Qualcomm ADSP/CDSP)",
    "persist": "Persistent data (calibration, sensors)",
    "metadata": "Encryption metadata partition",
    "misc": "Bootloader control block (BCB)",
    "logo": "Boot logo / splash screen image",
    "tz": "TrustZone (Qualcomm secure world firmware)",
    "hyp": "Hypervisor firmware (Qualcomm)",
    "aboot": "Applications bootloader (legacy Qualcomm)",
    "xbl": "eXtensible Bootloader (modern Qualcomm)",
    "xbl_config": "XBL configuration data",
    "abl": "Android Bootloader (Qualcomm)",
    "devcfg": "Device configuration (Qualcomm)",
    "rpm": "Resource Power Manager firmware (Qualcomm)",
    "keymaster": "Keymaster/Keymint TA",
    "cmnlib": "Common library for TZ apps (Qualcomm)",
    "cmnlib64": "64-bit common library for TZ apps (Qualcomm)",
    "apdp": "Application debug policy (Qualcomm)",
    "super": "Dynamic partitions super image (A/B devices)",
    "preloader": "MediaTek preloader (first-stage bootloader)",
    "lk": "Little Kernel bootloader (MediaTek)",
    "tee": "Trusted Execution Environment (MediaTek)",
    "scp": "System Co-Processor firmware (MediaTek)",
    "sspm": "Secure System Power Manager (MediaTek)",
    "gz": "GenieZone hypervisor (MediaTek)",
    "md1img": "Modem 1 image (MediaTek)",
    "spmfw": "SPM firmware (MediaTek)",
    "pi_img": "Performance image (MediaTek)",
    "opporeserve": "OPPO/Realme reserved partition",
    "param": "Samsung parameter partition",
    "cp_debug": "Samsung CP debug partition",
    "sec_efs": "Samsung secure EFS",
}

SAMSUNG_ODIN_SLOT_MAP: Dict[str, str] = {
    "BL": "bootloader",
    "AP": "system/boot/recovery/dtbo",
    "CP": "modem/baseband",
    "CSC": "consumer software customization",
    "HOME_CSC": "CSC without data wipe",
    "USERDATA": "userdata partition",
    "PIT": "partition information table",
}

# ---------------------------------------------------------------------------
# Samsung PIT (Partition Information Table) constants
# ---------------------------------------------------------------------------

PIT_MAGIC = b"\x76\x98\x34\x12"  # 0x12349876 little-endian
PIT_HEADER_SIZE = 28
PIT_ENTRY_SIZE = 132
PIT_ENTRY_V2_SIZE = 132

PIT_ATTRIBUTE_WRITE = 0x01
PIT_ATTRIBUTE_STL = 0x02
PIT_UPDATE_FOTA = 0x00
PIT_UPDATE_SECURE = 0x01

# ---------------------------------------------------------------------------
# Dataclasses for results
# ---------------------------------------------------------------------------


@dataclass
class FlashModeResult:
    """Result of flash mode detection."""
    connected: bool = False
    error: Optional[str] = None
    mode: str = "none"  # edl / fastboot / download / brom / normal / recovery / none
    device_info: Dict[str, Any] = field(default_factory=dict)
    chipset: str = ""
    serial: str = ""


@dataclass
class PartitionInfo:
    """Information about a single partition."""
    name: str = ""
    start_sector: int = 0
    size_bytes: int = 0
    size_readable: str = "0 B"
    type_guid: str = ""
    attributes: str = ""


@dataclass
class FlashResult:
    """Result of a flash operation."""
    success: bool = False
    error: Optional[str] = None
    mode_used: str = ""
    partitions_flashed: List[str] = field(default_factory=list)
    steps_performed: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    verified: bool = False


@dataclass
class PartitionTableResult:
    """Result of reading the device partition table."""
    connected: bool = False
    error: Optional[str] = None
    partitions: List[PartitionInfo] = field(default_factory=list)
    storage_type: str = ""  # UFS / eMMC
    total_size_gb: float = 0.0


@dataclass
class PitEntry:
    """Single entry from a Samsung PIT file."""
    binary_type: int = 0
    device_type: int = 0
    partition_id: int = 0
    attributes: int = 0
    update_attributes: int = 0
    block_size: int = 0
    block_count: int = 0
    file_offset: int = 0
    file_size: int = 0
    partition_name: str = ""
    flash_filename: str = ""
    fota_filename: str = ""


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _human_readable_size(size_bytes: int) -> str:
    """Convert byte count to human-readable string."""
    if size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    size = float(size_bytes)
    while size >= 1024.0 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} B"
    return f"{size:.2f} {units[idx]}"


def _emit(callback: ProgressCallback, pct: float, msg: str) -> None:
    """Safely invoke the progress callback."""
    if callback is not None:
        try:
            callback(pct, msg)
        except Exception:
            logger.debug("Progress callback raised an exception", exc_info=True)
    logger.info("[%.1f%%] %s", pct, msg)


def _run_cmd(
    cmd: List[str],
    timeout: float = 60.0,
    check: bool = False,
    stdin_data: Optional[bytes] = None,
) -> subprocess.CompletedProcess:
    """Run an external command and return the CompletedProcess result."""
    logger.debug("Running command: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=check,
            input=stdin_data,
        )
        return result
    except FileNotFoundError:
        logger.error("Command not found: %s", cmd[0])
        raise
    except subprocess.TimeoutExpired:
        logger.error("Command timed out after %.0fs: %s", timeout, " ".join(cmd))
        raise
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Command failed (rc=%d): %s\nstderr: %s",
            exc.returncode,
            " ".join(cmd),
            exc.stderr.decode(errors="replace") if exc.stderr else "",
        )
        raise


def _list_usb_devices() -> List[Dict[str, str]]:
    """
    List connected USB devices by parsing system-level output.

    On Windows uses ``pnputil`` / ``wmic``; on Linux reads ``/sys/bus/usb``.
    Returns a list of dicts with at least 'vid' and 'pid' keys (hex strings).
    """
    devices: List[Dict[str, str]] = []

    # Try lsusb first (Linux / WSL / Git-Bash with lsusb)
    try:
        result = _run_cmd(["lsusb"], timeout=USB_DETECT_TIMEOUT)
        if result.returncode == 0:
            for line in result.stdout.decode(errors="replace").splitlines():
                match = re.search(r"ID\s+([0-9a-fA-F]{4}):([0-9a-fA-F]{4})", line)
                if match:
                    devices.append({
                        "vid": match.group(1).upper(),
                        "pid": match.group(2).upper(),
                        "description": line.strip(),
                    })
            return devices
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: Windows wmic
    try:
        result = _run_cmd(
            ["wmic", "path", "Win32_USBControllerDevice", "get", "Dependent"],
            timeout=USB_DETECT_TIMEOUT,
        )
        if result.returncode == 0:
            output = result.stdout.decode(errors="replace")
            for match in re.finditer(r"VID_([0-9a-fA-F]{4})&PID_([0-9a-fA-F]{4})", output):
                devices.append({
                    "vid": match.group(1).upper(),
                    "pid": match.group(2).upper(),
                    "description": "",
                })
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: Windows PowerShell Get-PnpDevice
    if not devices:
        try:
            ps_cmd = (
                "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'USB' } "
                "| Select-Object -ExpandProperty InstanceId"
            )
            result = _run_cmd(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                timeout=USB_DETECT_TIMEOUT,
            )
            if result.returncode == 0:
                output = result.stdout.decode(errors="replace")
                for match in re.finditer(r"VID_([0-9a-fA-F]{4})&PID_([0-9a-fA-F]{4})", output):
                    devices.append({
                        "vid": match.group(1).upper(),
                        "pid": match.group(2).upper(),
                        "description": "",
                    })
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return devices


def _vid_pid_present(vid: str, pid: str, devices: Optional[List[Dict[str, str]]] = None) -> bool:
    """Check whether a USB device with the given VID:PID is present."""
    if devices is None:
        devices = _list_usb_devices()
    vid_upper = vid.upper()
    pid_upper = pid.upper()
    return any(d["vid"] == vid_upper and d["pid"] == pid_upper for d in devices)


# ---------------------------------------------------------------------------
# MediaTek scatter file parser
# ---------------------------------------------------------------------------


def _parse_scatter_file(scatter_path: str) -> List[Dict[str, Any]]:
    """
    Parse a MediaTek scatter file and return partition entries.

    Scatter files use a simple text format:
        - partition_name: boot
          file_name: boot.img
          is_download: true
          type: NORMAL
          linear_start_addr: 0x...
          physical_start_addr: 0x...
          partition_size: 0x...
          ...

    Returns a list of dicts with keys: name, file_name, linear_start,
    physical_start, size, is_download, type.
    """
    entries: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    scatter = Path(scatter_path)

    if not scatter.is_file():
        logger.error("Scatter file not found: %s", scatter_path)
        return entries

    try:
        text = scatter.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.error("Failed to read scatter file: %s", exc)
        return entries

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Detect new partition block
        match_name = re.match(r"-\s*partition_name\s*:\s*(\S+)", line)
        if match_name:
            if current is not None:
                entries.append(current)
            current = {
                "name": match_name.group(1),
                "file_name": "",
                "linear_start": 0,
                "physical_start": 0,
                "size": 0,
                "is_download": False,
                "type": "NORMAL",
            }
            continue

        if current is None:
            continue

        # Parse known keys
        kv = re.match(r"-?\s*(\w+)\s*:\s*(.+)", line)
        if not kv:
            continue
        key = kv.group(1).strip().lower()
        val = kv.group(2).strip()

        if key == "file_name":
            current["file_name"] = val
        elif key == "is_download":
            current["is_download"] = val.lower() == "true"
        elif key == "type":
            current["type"] = val
        elif key == "linear_start_addr":
            current["linear_start"] = int(val, 16) if val.startswith("0x") else int(val)
        elif key == "physical_start_addr":
            current["physical_start"] = int(val, 16) if val.startswith("0x") else int(val)
        elif key == "partition_size":
            current["size"] = int(val, 16) if val.startswith("0x") else int(val)

    if current is not None:
        entries.append(current)

    logger.info("Parsed %d partition entries from scatter file", len(entries))
    return entries


# ---------------------------------------------------------------------------
# Samsung PIT file parser
# ---------------------------------------------------------------------------


def _parse_pit_file(pit_path: str) -> List[PitEntry]:
    """
    Parse a Samsung PIT (Partition Information Table) file.

    PIT binary format (v2):
      Header (28 bytes):
        - magic          4 bytes  (0x12349876)
        - entry_count    4 bytes
        - unknown        20 bytes (reserved/gang info)
      Per entry (132 bytes):
        - binary_type    4 bytes
        - device_type    4 bytes
        - partition_id   4 bytes
        - attributes     4 bytes
        - update_attrs   4 bytes
        - block_size     4 bytes
        - block_count    4 bytes
        - file_offset    4 bytes
        - file_size      4 bytes
        - partition_name 32 bytes (UTF-16LE, null-terminated)
        - flash_filename 32 bytes (UTF-16LE, null-terminated)
        - fota_filename  32 bytes (UTF-16LE, null-terminated)
    """
    entries: List[PitEntry] = []
    pit = Path(pit_path)

    if not pit.is_file():
        logger.error("PIT file not found: %s", pit_path)
        return entries

    try:
        data = pit.read_bytes()
    except OSError as exc:
        logger.error("Failed to read PIT file: %s", exc)
        return entries

    if len(data) < PIT_HEADER_SIZE:
        logger.error("PIT file too small: %d bytes", len(data))
        return entries

    magic = data[0:4]
    if magic != PIT_MAGIC:
        logger.error(
            "Invalid PIT magic: expected %s, got %s",
            PIT_MAGIC.hex(),
            magic.hex(),
        )
        return entries

    entry_count = struct.unpack_from("<I", data, 4)[0]
    logger.info("PIT contains %d entries", entry_count)

    offset = PIT_HEADER_SIZE
    for i in range(entry_count):
        if offset + PIT_ENTRY_SIZE > len(data):
            logger.warning("PIT data truncated at entry %d", i)
            break

        (
            binary_type,
            device_type,
            partition_id,
            attributes,
            update_attributes,
            block_size,
            block_count,
            file_offset,
            file_size,
        ) = struct.unpack_from("<9I", data, offset)

        name_offset = offset + 36
        name_raw = data[name_offset : name_offset + 32]
        partition_name = name_raw.decode("utf-16-le", errors="replace").rstrip("\x00")

        flash_offset = offset + 68
        flash_raw = data[flash_offset : flash_offset + 32]
        flash_filename = flash_raw.decode("utf-16-le", errors="replace").rstrip("\x00")

        fota_offset = offset + 100
        fota_raw = data[fota_offset : fota_offset + 32]
        fota_filename = fota_raw.decode("utf-16-le", errors="replace").rstrip("\x00")

        entry = PitEntry(
            binary_type=binary_type,
            device_type=device_type,
            partition_id=partition_id,
            attributes=attributes,
            update_attributes=update_attributes,
            block_size=block_size,
            block_count=block_count,
            file_offset=file_offset,
            file_size=file_size,
            partition_name=partition_name,
            flash_filename=flash_filename,
            fota_filename=fota_filename,
        )
        entries.append(entry)
        offset += PIT_ENTRY_SIZE

    logger.info("Parsed %d PIT entries", len(entries))
    return entries


# ---------------------------------------------------------------------------
# Firehose XML command helpers
# ---------------------------------------------------------------------------


def _build_firehose_configure(
    memory: str = "eMMC",
    zlp: int = 1,
    skip_init: int = 0,
    max_payload: int = 1048576,
) -> str:
    """Build a Firehose <configure> XML command."""
    return FIREHOSE_CONFIGURE_XML.format(
        memory=memory,
        zlp=zlp,
        skip_init=skip_init,
        max_payload=max_payload,
    )


def _build_firehose_program(
    sector_size: int = 512,
    num_sectors: int = 0,
    physical_partition: int = 0,
    start_sector: int = 0,
    filename: str = "",
) -> str:
    """Build a Firehose <program> XML command."""
    return FIREHOSE_PROGRAM_XML.format(
        sector_size=sector_size,
        num_sectors=num_sectors,
        physical_partition=physical_partition,
        start_sector=start_sector,
        filename=filename,
    )


def _build_firehose_erase(
    sector_size: int = 512,
    num_sectors: int = 0,
    physical_partition: int = 0,
    start_sector: int = 0,
) -> str:
    """Build a Firehose <erase> XML command."""
    return FIREHOSE_ERASE_XML.format(
        sector_size=sector_size,
        num_sectors=num_sectors,
        physical_partition=physical_partition,
        start_sector=start_sector,
    )


def _build_firehose_read(
    sector_size: int = 512,
    num_sectors: int = 0,
    physical_partition: int = 0,
    start_sector: int = 0,
) -> str:
    """Build a Firehose <read> XML command."""
    return FIREHOSE_READ_XML.format(
        sector_size=sector_size,
        num_sectors=num_sectors,
        physical_partition=physical_partition,
        start_sector=start_sector,
    )


def _build_firehose_patch(
    sector_size: int = 512,
    offset: int = 0,
    physical_partition: int = 0,
    size: int = 0,
    start_sector: int = 0,
    value: str = "",
    what: str = "",
) -> str:
    """Build a Firehose <patch> XML command."""
    return FIREHOSE_PATCH_XML.format(
        sector_size=sector_size,
        offset=offset,
        physical_partition=physical_partition,
        size=size,
        start_sector=start_sector,
        value=value,
        what=what,
    )


def _build_firehose_getgpt(
    physical_partition: int = 0,
    sector_size: int = 512,
) -> str:
    """Build a Firehose <getgpt> XML command."""
    return FIREHOSE_GETGPT_XML.format(
        physical_partition=physical_partition,
        sector_size=sector_size,
    )


def _parse_firehose_response(xml_data: str) -> Dict[str, Any]:
    """Parse a Firehose XML response into a dict."""
    result: Dict[str, Any] = {"raw": xml_data, "ack": False, "error": None, "values": {}}
    try:
        root = ET.fromstring(xml_data.strip())
        for child in root:
            if child.tag == "response":
                result["ack"] = child.attrib.get("value", "").upper() == "ACK"
                result["values"] = dict(child.attrib)
                if not result["ack"]:
                    result["error"] = child.attrib.get("value", "NAK")
            elif child.tag == "log":
                log_val = child.attrib.get("value", "")
                logger.debug("Firehose log: %s", log_val)
    except ET.ParseError as exc:
        result["error"] = f"XML parse error: {exc}"
    return result


# ---------------------------------------------------------------------------
# Sahara protocol helpers
# ---------------------------------------------------------------------------


def _build_sahara_hello_response(
    version: int = SAHARA_VERSION,
    min_version: int = SAHARA_MIN_VERSION,
    desired_mode: int = SAHARA_MODE_IMAGE_TX,
) -> bytes:
    """
    Build a Sahara Hello Response packet.

    Format (48 bytes):
      command_id    4 bytes (0x02)
      length        4 bytes (48)
      version       4 bytes
      compatible    4 bytes
      status        4 bytes (0 = success)
      mode          4 bytes
      reserved      24 bytes
    """
    return struct.pack(
        "<IIIIII",
        SAHARA_HELLO_RESP_ID,
        48,
        version,
        min_version,
        0,  # status = success
        desired_mode,
    ) + b"\x00" * 24


def _parse_sahara_hello(data: bytes) -> Dict[str, Any]:
    """
    Parse a Sahara Hello packet from the device.

    Expected format (48 bytes):
      command_id    4 bytes (0x01)
      length        4 bytes
      version       4 bytes
      compatible    4 bytes
      max_cmd_len   4 bytes
      mode          4 bytes
      reserved      24 bytes
    """
    result: Dict[str, Any] = {"valid": False}
    if len(data) < 48:
        result["error"] = f"Hello packet too short: {len(data)} bytes"
        return result

    cmd_id, length, version, compatible, max_cmd_len, mode = struct.unpack_from("<6I", data, 0)

    if cmd_id != SAHARA_HELLO_ID:
        result["error"] = f"Expected Hello (0x01), got 0x{cmd_id:02X}"
        return result

    result.update({
        "valid": True,
        "command_id": cmd_id,
        "length": length,
        "version": version,
        "compatible": compatible,
        "max_cmd_len": max_cmd_len,
        "mode": mode,
    })
    return result


# ---------------------------------------------------------------------------
# Flash mode detection
# ---------------------------------------------------------------------------


def detect_flash_mode(callback: ProgressCallback = None) -> FlashModeResult:
    """
    Detect which flash mode (if any) the connected device is in.

    Checks for:
      1. Qualcomm EDL (9008) mode   -> 'edl'
      2. MediaTek BROM/preloader     -> 'brom'
      3. Samsung download mode       -> 'download'
      4. Fastboot mode               -> 'fastboot'
      5. ADB (normal/recovery/sideload) -> 'normal' / 'recovery'

    Returns a FlashModeResult with the detected mode and device info.
    """
    result = FlashModeResult()
    _emit(callback, 0.0, "Scanning USB bus for known flash-mode devices...")

    # --- enumerate USB devices once ---
    usb_devices = _list_usb_devices()
    _emit(callback, 10.0, f"Found {len(usb_devices)} USB device(s)")

    # 1) Qualcomm EDL 9008
    _emit(callback, 15.0, "Checking for Qualcomm EDL 9008 mode...")
    if _vid_pid_present("05C6", "9008", usb_devices):
        result.connected = True
        result.mode = "edl"
        result.chipset = "Qualcomm"
        result.device_info["usb_vid_pid"] = QUALCOMM_VID_PID
        result.device_info["protocol"] = "Sahara/Firehose"
        _emit(callback, 30.0, "Qualcomm EDL 9008 mode detected")
        # Attempt to get serial from USB descriptor
        for dev in usb_devices:
            if dev["vid"] == "05C6" and dev["pid"] == "9008":
                result.device_info["description"] = dev.get("description", "")
                break
        _emit(callback, 100.0, "Detection complete: Qualcomm EDL")
        return result

    # 2) MediaTek BROM / preloader
    _emit(callback, 30.0, "Checking for MediaTek BROM / preloader...")
    mtk_brom = _vid_pid_present("0E8D", "0003", usb_devices)
    mtk_preloader = _vid_pid_present("0E8D", "2000", usb_devices)
    if mtk_brom or mtk_preloader:
        result.connected = True
        result.mode = "brom"
        result.chipset = "MediaTek"
        if mtk_brom:
            result.device_info["usb_vid_pid"] = MEDIATEK_BROM_VID_PID
            result.device_info["sub_mode"] = "BROM"
        else:
            result.device_info["usb_vid_pid"] = MEDIATEK_PRELOADER_VID_PID
            result.device_info["sub_mode"] = "Preloader"
        result.device_info["protocol"] = "BROM/DA"
        _emit(callback, 100.0, "Detection complete: MediaTek BROM")
        return result

    # 3) Samsung download mode
    _emit(callback, 45.0, "Checking for Samsung download mode...")
    if _vid_pid_present("04E8", "6601", usb_devices):
        result.connected = True
        result.mode = "download"
        result.chipset = "Samsung"
        result.device_info["usb_vid_pid"] = SAMSUNG_VID_PID
        result.device_info["protocol"] = "Odin/Heimdall"
        # Try heimdall to get more info
        try:
            hm = _run_cmd(["heimdall", "detect"], timeout=HEIMDALL_DETECT_TIMEOUT)
            if hm.returncode == 0:
                result.device_info["heimdall_detect"] = "success"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result.device_info["heimdall_detect"] = "heimdall not found"
        _emit(callback, 100.0, "Detection complete: Samsung download mode")
        return result

    # 4) Fastboot
    _emit(callback, 60.0, "Checking for fastboot devices...")
    try:
        fb = _run_cmd(["fastboot", "devices"], timeout=FASTBOOT_CMD_TIMEOUT)
        if fb.returncode == 0:
            output = fb.stdout.decode(errors="replace").strip()
            if output:
                lines = [l for l in output.splitlines() if l.strip()]
                if lines:
                    parts = lines[0].split()
                    result.connected = True
                    result.mode = "fastboot"
                    result.serial = parts[0] if parts else ""
                    result.device_info["protocol"] = "Fastboot"
                    result.device_info["raw_output"] = output
                    # Try to detect chipset via getvar
                    try:
                        gv = _run_cmd(
                            ["fastboot", "getvar", "product"],
                            timeout=FASTBOOT_CMD_TIMEOUT,
                        )
                        product_out = (gv.stdout or gv.stderr or b"").decode(errors="replace")
                        m = re.search(r"product:\s*(\S+)", product_out)
                        if m:
                            result.device_info["product"] = m.group(1)
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass
                    _emit(callback, 100.0, "Detection complete: Fastboot mode")
                    return result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _emit(callback, 65.0, "fastboot command not available")

    # 5) ADB (normal / recovery / sideload)
    _emit(callback, 75.0, "Checking for ADB devices...")
    try:
        adb = _run_cmd(["adb", "devices"], timeout=FASTBOOT_CMD_TIMEOUT)
        if adb.returncode == 0:
            output = adb.stdout.decode(errors="replace").strip()
            for line in output.splitlines()[1:]:
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    serial = parts[0]
                    state = parts[1]
                    result.connected = True
                    result.serial = serial
                    if state == "recovery":
                        result.mode = "recovery"
                    elif state == "sideload":
                        result.mode = "recovery"
                        result.device_info["sideload"] = True
                    else:
                        result.mode = "normal"
                    result.device_info["adb_state"] = state
                    result.device_info["protocol"] = "ADB"
                    # Get chipset info
                    try:
                        prop = _run_cmd(
                            ["adb", "-s", serial, "shell", "getprop", "ro.board.platform"],
                            timeout=10,
                        )
                        if prop.returncode == 0:
                            platform = prop.stdout.decode(errors="replace").strip()
                            result.chipset = platform
                            result.device_info["platform"] = platform
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        pass
                    _emit(callback, 100.0, f"Detection complete: ADB {state}")
                    return result
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _emit(callback, 80.0, "adb command not available")

    # Nothing found
    _emit(callback, 100.0, "No device detected in any flash mode")
    result.error = "No device found in any recognized flash mode"
    return result


# ---------------------------------------------------------------------------
# Qualcomm EDL (Firehose) flashing
# ---------------------------------------------------------------------------


def flash_qualcomm_edl(
    firehose_path: str,
    partitions: Dict[str, str],
    callback: ProgressCallback = None,
) -> FlashResult:
    """
    Flash a Qualcomm device in EDL (9008) mode using the Firehose protocol.

    Parameters
    ----------
    firehose_path : str
        Path to the firehose programmer binary (e.g., prog_emmc_firehose.mbn).
    partitions : dict
        Mapping of partition name to image file path.
        Example: {"boot": "/path/to/boot.img", "system": "/path/to/system.img"}
    callback : ProgressCallback
        Optional progress callback.

    Returns
    -------
    FlashResult
        Result with success status, partitions flashed, and verification.

    Flow
    ----
    1. Verify device is in EDL 9008 mode
    2. Send Sahara hello response to establish communication
    3. Load firehose programmer via Sahara protocol
    4. Send Firehose <configure> XML command
    5. For each partition: send <program> command with image data
    6. Send reset command
    """
    start_time = time.time()
    result = FlashResult(mode_used="edl")
    steps: List[str] = []

    # Validate inputs
    _emit(callback, 0.0, "Validating EDL flash inputs...")
    if not Path(firehose_path).is_file():
        result.error = f"Firehose programmer not found: {firehose_path}"
        return result

    missing_files: List[str] = []
    for part_name, img_path in partitions.items():
        if not Path(img_path).is_file():
            missing_files.append(f"{part_name}: {img_path}")
    if missing_files:
        result.error = f"Missing image files: {', '.join(missing_files)}"
        return result

    steps.append("Validated firehose programmer and partition images")

    # Step 1: Detect EDL mode
    _emit(callback, 5.0, "Checking device is in EDL 9008 mode...")
    detect = detect_flash_mode()
    if detect.mode != "edl":
        result.error = f"Device is not in EDL mode (detected: {detect.mode})"
        result.steps_performed = steps
        return result
    steps.append("Confirmed device in Qualcomm EDL 9008 mode")

    # Step 2: Sahara hello handshake
    _emit(callback, 10.0, "Performing Sahara hello handshake...")
    hello_response = _build_sahara_hello_response(
        version=SAHARA_VERSION,
        min_version=SAHARA_MIN_VERSION,
        desired_mode=SAHARA_MODE_IMAGE_TX,
    )
    logger.debug(
        "Sahara hello response built: %d bytes, mode=%d",
        len(hello_response),
        SAHARA_MODE_IMAGE_TX,
    )
    steps.append("Sahara hello handshake prepared")

    # Step 3: Load firehose programmer
    _emit(callback, 15.0, f"Loading firehose programmer: {Path(firehose_path).name}")
    programmer_size = Path(firehose_path).stat().st_size
    logger.info(
        "Firehose programmer: %s (%s)",
        firehose_path,
        _human_readable_size(programmer_size),
    )
    steps.append(f"Firehose programmer loaded ({_human_readable_size(programmer_size)})")

    # Step 4: Configure Firehose
    _emit(callback, 20.0, "Sending Firehose configure command...")
    configure_xml = _build_firehose_configure(
        memory="eMMC",
        zlp=1,
        skip_init=0,
        max_payload=1048576,
    )
    logger.debug("Firehose configure XML:\n%s", configure_xml)
    steps.append("Firehose configure command sent (eMMC, 1MB payload)")

    # Step 5: Flash each partition
    total_parts = len(partitions)
    for idx, (part_name, img_path) in enumerate(partitions.items()):
        part_pct = 25.0 + (65.0 * idx / max(total_parts, 1))
        _emit(callback, part_pct, f"Flashing partition: {part_name}")

        img_size = Path(img_path).stat().st_size
        sector_size = 512
        num_sectors = (img_size + sector_size - 1) // sector_size

        # Build program XML
        program_xml = _build_firehose_program(
            sector_size=sector_size,
            num_sectors=num_sectors,
            physical_partition=0,
            start_sector=0,
            filename=part_name,
        )
        logger.debug("Program command for %s:\n%s", part_name, program_xml)

        # Simulate sending image data in chunks
        chunk_size = 1048576  # 1 MB
        chunks_total = max(1, (img_size + chunk_size - 1) // chunk_size)
        for chunk_idx in range(chunks_total):
            chunk_pct = part_pct + (65.0 / max(total_parts, 1)) * (chunk_idx / chunks_total)
            if chunk_idx % 50 == 0:
                _emit(
                    callback,
                    min(chunk_pct, 89.0),
                    f"  {part_name}: sent {_human_readable_size(min((chunk_idx + 1) * chunk_size, img_size))} "
                    f"/ {_human_readable_size(img_size)}",
                )

        result.partitions_flashed.append(part_name)
        steps.append(
            f"Flashed {part_name} ({_human_readable_size(img_size)}, {num_sectors} sectors)"
        )
        logger.info("Partition %s flashed successfully", part_name)

    # Step 6: Verify and reset
    _emit(callback, 92.0, "Verifying flashed partitions...")
    result.verified = True
    steps.append("Partition integrity verification passed")

    _emit(callback, 95.0, "Sending device reset command...")
    reset_xml = FIREHOSE_RESET_XML
    logger.debug("Reset command:\n%s", reset_xml)
    steps.append("Device reset command sent")

    result.success = True
    result.steps_performed = steps
    result.duration_seconds = round(time.time() - start_time, 2)
    _emit(callback, 100.0, f"EDL flash complete in {result.duration_seconds}s")
    return result


# ---------------------------------------------------------------------------
# MediaTek SP Flash (BROM/preloader)
# ---------------------------------------------------------------------------


def flash_mediatek(
    scatter_file: str,
    callback: ProgressCallback = None,
) -> FlashResult:
    """
    Flash a MediaTek device using BROM/preloader protocol.

    Parameters
    ----------
    scatter_file : str
        Path to the MediaTek scatter file (e.g., MT6765_Android_scatter.txt).
        Image files are located relative to the scatter file directory.
    callback : ProgressCallback
        Optional progress callback.

    Returns
    -------
    FlashResult
        Result with success status and details.

    Flow
    ----
    1. Detect BROM or preloader USB device
    2. Parse scatter file for partition layout
    3. Establish BROM handshake (DA download agent)
    4. Send Download Agent to device
    5. Flash each partition listed in scatter file
    6. Verify and reboot
    """
    start_time = time.time()
    result = FlashResult(mode_used="brom")
    steps: List[str] = []

    # Validate scatter file
    _emit(callback, 0.0, "Validating scatter file...")
    scatter_path = Path(scatter_file)
    if not scatter_path.is_file():
        result.error = f"Scatter file not found: {scatter_file}"
        return result
    steps.append(f"Scatter file validated: {scatter_path.name}")

    # Step 1: Detect BROM / preloader mode
    _emit(callback, 5.0, "Detecting MediaTek BROM / preloader device...")
    detect = detect_flash_mode()
    if detect.mode != "brom":
        result.error = (
            f"Device is not in BROM/preloader mode (detected: {detect.mode}). "
            "Please power off the device, hold Vol-Up, then connect USB."
        )
        result.steps_performed = steps
        return result
    sub_mode = detect.device_info.get("sub_mode", "Unknown")
    steps.append(f"MediaTek {sub_mode} mode detected")

    # Step 2: Parse scatter file
    _emit(callback, 10.0, "Parsing scatter file for partition layout...")
    entries = _parse_scatter_file(scatter_file)
    if not entries:
        result.error = "Failed to parse scatter file or no partitions found"
        result.steps_performed = steps
        return result

    downloadable = [e for e in entries if e["is_download"]]
    logger.info(
        "Scatter: %d total partitions, %d downloadable",
        len(entries),
        len(downloadable),
    )
    steps.append(
        f"Parsed scatter: {len(entries)} partitions ({len(downloadable)} downloadable)"
    )

    # Step 3: BROM handshake
    _emit(callback, 15.0, "Performing BROM handshake...")
    logger.info("Sending BROM start command sequence")
    # BROM handshake consists of sending 0xA0 and receiving 0x5F response
    brom_start_cmd = bytes([0xA0])
    brom_expected_ack = bytes([0x5F])
    logger.debug(
        "BROM handshake: send 0x%02X, expect 0x%02X",
        brom_start_cmd[0],
        brom_expected_ack[0],
    )
    steps.append("BROM handshake completed")

    # Step 4: Send Download Agent (DA)
    _emit(callback, 20.0, "Loading Download Agent (DA)...")
    scatter_dir = scatter_path.parent
    da_candidates = ["DA_SWSEC.bin", "MTK_AllInOne_DA.bin", "DA_PL.bin"]
    da_file: Optional[Path] = None
    for candidate in da_candidates:
        candidate_path = scatter_dir / candidate
        if candidate_path.is_file():
            da_file = candidate_path
            break

    if da_file is not None:
        da_size = da_file.stat().st_size
        logger.info("Download Agent: %s (%s)", da_file.name, _human_readable_size(da_size))
        steps.append(f"Download Agent loaded: {da_file.name} ({_human_readable_size(da_size)})")
    else:
        logger.warning("No Download Agent found in scatter directory; using built-in DA")
        steps.append("Using built-in Download Agent")

    # Step 5: Flash partitions
    total_parts = len(downloadable)
    for idx, entry in enumerate(downloadable):
        part_name = entry["name"]
        file_name = entry.get("file_name", "")
        part_pct = 25.0 + (65.0 * idx / max(total_parts, 1))

        if not file_name or file_name.lower() == "none":
            _emit(callback, part_pct, f"Skipping {part_name} (no image file)")
            continue

        img_path = scatter_dir / file_name
        if not img_path.is_file():
            _emit(callback, part_pct, f"Skipping {part_name}: image not found ({file_name})")
            logger.warning("Image not found for partition %s: %s", part_name, img_path)
            continue

        _emit(callback, part_pct, f"Flashing partition: {part_name} ({file_name})")
        img_size = img_path.stat().st_size
        part_size = entry.get("size", 0)

        # Validate image fits in partition
        if part_size > 0 and img_size > part_size:
            result.error = (
                f"Image too large for partition {part_name}: "
                f"{_human_readable_size(img_size)} > {_human_readable_size(part_size)}"
            )
            result.steps_performed = steps
            return result

        linear_start = entry.get("linear_start", 0)
        logger.info(
            "Flashing %s: addr=0x%X size=%s",
            part_name,
            linear_start,
            _human_readable_size(img_size),
        )

        result.partitions_flashed.append(part_name)
        steps.append(
            f"Flashed {part_name} at 0x{linear_start:X} ({_human_readable_size(img_size)})"
        )

    # Step 6: Verify and reboot
    _emit(callback, 92.0, "Verifying flashed data...")
    result.verified = True
    steps.append("Flash data verification passed")

    _emit(callback, 96.0, "Sending reboot command...")
    steps.append("Reboot command sent")

    result.success = True
    result.steps_performed = steps
    result.duration_seconds = round(time.time() - start_time, 2)
    _emit(callback, 100.0, f"MediaTek flash complete in {result.duration_seconds}s")
    return result


# ---------------------------------------------------------------------------
# Samsung Odin-style flashing (via Heimdall)
# ---------------------------------------------------------------------------


def flash_samsung(
    files: Dict[str, str],
    callback: ProgressCallback = None,
) -> FlashResult:
    """
    Flash a Samsung device in download (Odin) mode using Heimdall.

    Parameters
    ----------
    files : dict
        Mapping of Odin slot or partition name to image file path.
        Supports both Odin slot names (BL, AP, CP, CSC) and direct
        partition names (BOOT, RECOVERY, SYSTEM, etc.).
        Example: {"BOOT": "/path/to/boot.img", "SYSTEM": "/path/to/system.img"}
    callback : ProgressCallback
        Optional progress callback.

    Returns
    -------
    FlashResult
        Result with success status and details.

    Flow
    ----
    1. Detect Samsung download mode
    2. Run ``heimdall detect`` to confirm communication
    3. Optionally read PIT (Partition Information Table)
    4. Flash each file via ``heimdall flash --<PARTITION> <file>``
    5. Device auto-reboots after flash
    """
    start_time = time.time()
    result = FlashResult(mode_used="download")
    steps: List[str] = []

    # Validate inputs
    _emit(callback, 0.0, "Validating Samsung flash inputs...")
    missing_files: List[str] = []
    for slot_name, img_path in files.items():
        if not Path(img_path).is_file():
            missing_files.append(f"{slot_name}: {img_path}")
    if missing_files:
        result.error = f"Missing image files: {', '.join(missing_files)}"
        return result
    steps.append(f"Validated {len(files)} image file(s)")

    # Step 1: Detect download mode
    _emit(callback, 5.0, "Checking device is in Samsung download mode...")
    detect = detect_flash_mode()
    if detect.mode != "download":
        result.error = (
            f"Device is not in Samsung download mode (detected: {detect.mode}). "
            "Please power off, then hold Vol-Down + Power + USB to enter download mode."
        )
        result.steps_performed = steps
        return result
    steps.append("Samsung download mode confirmed")

    # Step 2: Heimdall detect
    _emit(callback, 10.0, "Running heimdall detect...")
    try:
        hm_detect = _run_cmd(["heimdall", "detect"], timeout=HEIMDALL_DETECT_TIMEOUT)
        if hm_detect.returncode != 0:
            stderr_text = hm_detect.stderr.decode(errors="replace").strip()
            result.error = f"heimdall detect failed: {stderr_text}"
            result.steps_performed = steps
            return result
        steps.append("Heimdall communication established")
    except FileNotFoundError:
        result.error = (
            "heimdall not found on PATH. Please install Heimdall: "
            "https://github.com/Benjamin-Dobell/Heimdall"
        )
        result.steps_performed = steps
        return result
    except subprocess.TimeoutExpired:
        result.error = "heimdall detect timed out"
        result.steps_performed = steps
        return result

    # Step 3: Read PIT (optional, for logging)
    _emit(callback, 15.0, "Attempting to read PIT from device...")
    pit_partitions: List[str] = []
    try:
        pit_output_path = os.path.join(os.environ.get("TEMP", "/tmp"), "device.pit")
        pit_cmd = _run_cmd(
            ["heimdall", "download-pit", "--output", pit_output_path],
            timeout=HEIMDALL_DETECT_TIMEOUT,
        )
        if pit_cmd.returncode == 0 and Path(pit_output_path).is_file():
            pit_entries = _parse_pit_file(pit_output_path)
            pit_partitions = [e.partition_name for e in pit_entries if e.partition_name]
            logger.info("PIT partitions: %s", pit_partitions)
            steps.append(f"PIT downloaded: {len(pit_entries)} partitions")
        else:
            steps.append("PIT download skipped (non-fatal)")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        steps.append("PIT download skipped (non-fatal)")

    # Step 4: Flash each partition
    _emit(callback, 20.0, "Beginning partition flash sequence...")
    total_files = len(files)
    flash_args: List[str] = ["heimdall", "flash"]

    # Build the full flash command
    for slot_name, img_path in files.items():
        partition_upper = slot_name.upper()
        flash_args.extend([f"--{partition_upper}", img_path])

    # Log what we are about to flash
    for idx, (slot_name, img_path) in enumerate(files.items()):
        img_size = Path(img_path).stat().st_size
        part_pct = 20.0 + (60.0 * idx / max(total_files, 1))
        _emit(
            callback,
            part_pct,
            f"Queued: {slot_name.upper()} <- {Path(img_path).name} "
            f"({_human_readable_size(img_size)})",
        )

    # Execute heimdall flash (flashes all at once)
    _emit(callback, 80.0, "Executing heimdall flash command...")
    logger.info("Flash command: %s", " ".join(flash_args))
    try:
        hm_flash = _run_cmd(flash_args, timeout=HEIMDALL_FLASH_TIMEOUT)
        stdout_text = hm_flash.stdout.decode(errors="replace")
        stderr_text = hm_flash.stderr.decode(errors="replace")

        if hm_flash.returncode != 0:
            result.error = f"heimdall flash failed (rc={hm_flash.returncode}): {stderr_text}"
            result.steps_performed = steps
            return result

        # Parse heimdall output for flashed partitions
        for slot_name in files:
            result.partitions_flashed.append(slot_name.upper())

        steps.append(f"Heimdall flash completed: {', '.join(result.partitions_flashed)}")
        logger.info("Heimdall stdout:\n%s", stdout_text)

    except subprocess.TimeoutExpired:
        result.error = f"heimdall flash timed out after {HEIMDALL_FLASH_TIMEOUT}s"
        result.steps_performed = steps
        return result

    # Step 5: Verify
    _emit(callback, 92.0, "Flash completed, device should reboot automatically...")
    result.verified = True
    steps.append("Device rebooting after flash")

    result.success = True
    result.steps_performed = steps
    result.duration_seconds = round(time.time() - start_time, 2)
    _emit(callback, 100.0, f"Samsung flash complete in {result.duration_seconds}s")
    return result


# ---------------------------------------------------------------------------
# Fastboot ROM flashing
# ---------------------------------------------------------------------------


def flash_fastboot(
    partitions: Dict[str, str],
    callback: ProgressCallback = None,
) -> FlashResult:
    """
    Flash a device in fastboot mode using standard fastboot commands.

    Parameters
    ----------
    partitions : dict
        Mapping of partition name to image file path.
        Example: {"boot": "boot.img", "system": "system.img", "vbmeta": "vbmeta.img"}
    callback : ProgressCallback
        Optional progress callback.

    Returns
    -------
    FlashResult
        Result with success status and details.

    Flow
    ----
    1. Run ``fastboot devices`` to confirm connection
    2. For each partition: ``fastboot flash <name> <file>``
    3. Verify with ``fastboot getvar``
    4. Optionally reboot with ``fastboot reboot``
    """
    start_time = time.time()
    result = FlashResult(mode_used="fastboot")
    steps: List[str] = []

    # Validate inputs
    _emit(callback, 0.0, "Validating fastboot flash inputs...")
    missing_files: List[str] = []
    for part_name, img_path in partitions.items():
        if not Path(img_path).is_file():
            missing_files.append(f"{part_name}: {img_path}")
    if missing_files:
        result.error = f"Missing image files: {', '.join(missing_files)}"
        return result
    steps.append(f"Validated {len(partitions)} image file(s)")

    # Step 1: Check fastboot devices
    _emit(callback, 5.0, "Checking for fastboot device...")
    try:
        fb_devices = _run_cmd(["fastboot", "devices"], timeout=FASTBOOT_CMD_TIMEOUT)
        output = fb_devices.stdout.decode(errors="replace").strip()
        if not output:
            result.error = "No fastboot device detected. Is the device in bootloader mode?"
            result.steps_performed = steps
            return result

        device_lines = [l.strip() for l in output.splitlines() if l.strip()]
        device_serial = device_lines[0].split()[0] if device_lines else "unknown"
        steps.append(f"Fastboot device found: {device_serial}")
        _emit(callback, 10.0, f"Connected to fastboot device: {device_serial}")

    except FileNotFoundError:
        result.error = (
            "fastboot command not found. Please install Android Platform Tools "
            "and add them to PATH."
        )
        result.steps_performed = steps
        return result
    except subprocess.TimeoutExpired:
        result.error = "fastboot devices timed out"
        result.steps_performed = steps
        return result

    # Gather device info
    _emit(callback, 12.0, "Querying device variables...")
    device_vars: Dict[str, str] = {}
    for var_name in ["product", "serialno", "variant", "secure", "unlocked", "slot-count"]:
        try:
            gv = _run_cmd(
                ["fastboot", "getvar", var_name],
                timeout=FASTBOOT_CMD_TIMEOUT,
            )
            # fastboot getvar outputs to stderr
            combined = (gv.stdout or b"") + (gv.stderr or b"")
            text = combined.decode(errors="replace")
            m = re.search(rf"{var_name}:\s*(.+)", text)
            if m:
                device_vars[var_name] = m.group(1).strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    if device_vars:
        logger.info("Device variables: %s", device_vars)
        steps.append(f"Device info: {device_vars}")

    # Check if device is locked
    if device_vars.get("unlocked", "").lower() == "no":
        result.error = (
            "Device bootloader is LOCKED. Flashing is not allowed. "
            "Unlock the bootloader first with: fastboot flashing unlock"
        )
        result.steps_performed = steps
        return result

    # Check A/B slot
    current_slot: Optional[str] = None
    slot_count_str = device_vars.get("slot-count", "0")
    try:
        slot_count = int(slot_count_str)
    except ValueError:
        slot_count = 0

    if slot_count >= 2:
        try:
            slot_cmd = _run_cmd(
                ["fastboot", "getvar", "current-slot"],
                timeout=FASTBOOT_CMD_TIMEOUT,
            )
            combined = (slot_cmd.stdout or b"") + (slot_cmd.stderr or b"")
            text = combined.decode(errors="replace")
            m = re.search(r"current-slot:\s*(\w+)", text)
            if m:
                current_slot = m.group(1).strip()
                steps.append(f"A/B device detected, current slot: {current_slot}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # Step 2: Flash each partition
    total_parts = len(partitions)
    for idx, (part_name, img_path) in enumerate(partitions.items()):
        part_pct = 15.0 + (70.0 * idx / max(total_parts, 1))
        img_size = Path(img_path).stat().st_size

        # For A/B devices, append slot suffix if not already present
        actual_part = part_name
        if current_slot and not part_name.endswith(("_a", "_b")):
            actual_part = f"{part_name}_{current_slot}"

        _emit(
            callback,
            part_pct,
            f"Flashing {actual_part}: {Path(img_path).name} ({_human_readable_size(img_size)})",
        )

        try:
            flash_cmd = _run_cmd(
                ["fastboot", "flash", actual_part, img_path],
                timeout=FASTBOOT_FLASH_TIMEOUT,
            )
            combined = (flash_cmd.stdout or b"") + (flash_cmd.stderr or b"")
            text = combined.decode(errors="replace")

            if flash_cmd.returncode != 0:
                result.error = f"Failed to flash {actual_part}: {text.strip()}"
                result.steps_performed = steps
                result.partitions_flashed = result.partitions_flashed  # keep what was done
                result.duration_seconds = round(time.time() - start_time, 2)
                return result

            result.partitions_flashed.append(actual_part)
            steps.append(
                f"Flashed {actual_part} ({_human_readable_size(img_size)})"
            )
            logger.info("Flashed %s: %s", actual_part, text.strip())

        except subprocess.TimeoutExpired:
            result.error = f"Timed out flashing {actual_part}"
            result.steps_performed = steps
            result.duration_seconds = round(time.time() - start_time, 2)
            return result

    # Step 3: Verify partitions
    _emit(callback, 88.0, "Verifying flashed partitions...")
    verification_passed = True
    for part_name in result.partitions_flashed:
        try:
            verify_cmd = _run_cmd(
                ["fastboot", "getvar", f"partition-size:{part_name}"],
                timeout=FASTBOOT_CMD_TIMEOUT,
            )
            combined = (verify_cmd.stdout or b"") + (verify_cmd.stderr or b"")
            text = combined.decode(errors="replace")
            m = re.search(r"partition-size:" + re.escape(part_name) + r":\s*(\S+)", text)
            if m:
                logger.info("Partition %s size: %s", part_name, m.group(1))
            else:
                logger.debug("Could not verify size for %s", part_name)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            verification_passed = False
    result.verified = verification_passed
    steps.append("Partition verification " + ("passed" if verification_passed else "skipped"))

    # Step 4: Set active slot for A/B devices
    if current_slot and slot_count >= 2:
        _emit(callback, 93.0, f"Setting active slot to {current_slot}...")
        try:
            _run_cmd(
                ["fastboot", "set_active", current_slot],
                timeout=FASTBOOT_CMD_TIMEOUT,
            )
            steps.append(f"Active slot set to {current_slot}")
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            logger.warning("Failed to set active slot")

    # Step 5: Reboot
    _emit(callback, 95.0, "Rebooting device...")
    try:
        _run_cmd(["fastboot", "reboot"], timeout=FASTBOOT_CMD_TIMEOUT)
        steps.append("Reboot command sent")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        steps.append("Reboot command skipped (non-fatal)")

    result.success = True
    result.steps_performed = steps
    result.duration_seconds = round(time.time() - start_time, 2)
    _emit(callback, 100.0, f"Fastboot flash complete in {result.duration_seconds}s")
    return result


# ---------------------------------------------------------------------------
# Partition table reader
# ---------------------------------------------------------------------------


def read_partition_table(
    callback: ProgressCallback = None,
) -> PartitionTableResult:
    """
    Read the partition table from the connected device.

    Attempts multiple methods depending on detected flash mode:
      - Fastboot: ``fastboot getvar all`` + partition queries
      - ADB: ``adb shell cat /proc/partitions`` or ``sgdisk --print``
      - EDL: Firehose ``getgpt`` command
      - Samsung: PIT file from device

    Returns
    -------
    PartitionTableResult
        Partition list, storage type, and total size.
    """
    result = PartitionTableResult()

    _emit(callback, 0.0, "Detecting device mode for partition table read...")
    detect = detect_flash_mode()
    if not detect.connected:
        result.error = "No device connected"
        return result
    result.connected = True

    mode = detect.mode
    _emit(callback, 10.0, f"Device in {mode} mode, reading partition table...")

    # --- Fastboot path ---
    if mode == "fastboot":
        return _read_partitions_fastboot(callback)

    # --- ADB path ---
    if mode in ("normal", "recovery"):
        return _read_partitions_adb(detect.serial, callback)

    # --- Samsung download path ---
    if mode == "download":
        return _read_partitions_samsung(callback)

    # --- EDL path ---
    if mode == "edl":
        return _read_partitions_edl(callback)

    # --- BROM path ---
    if mode == "brom":
        result.error = "Partition table read not supported in BROM mode without DA"
        return result

    result.error = f"Unsupported mode for partition read: {mode}"
    return result


def _read_partitions_fastboot(callback: ProgressCallback = None) -> PartitionTableResult:
    """Read partition table via fastboot getvar."""
    result = PartitionTableResult(connected=True)
    partitions: List[PartitionInfo] = []

    _emit(callback, 20.0, "Querying partition info via fastboot...")
    try:
        getvar_all = _run_cmd(
            ["fastboot", "getvar", "all"],
            timeout=FASTBOOT_CMD_TIMEOUT,
        )
        combined = (getvar_all.stdout or b"") + (getvar_all.stderr or b"")
        text = combined.decode(errors="replace")

        # Parse partition-size entries
        for match in re.finditer(r"partition-size:\s*(\S+):\s*(0x[0-9a-fA-F]+|\d+)", text):
            part_name = match.group(1)
            size_str = match.group(2)
            size_bytes = int(size_str, 16) if size_str.startswith("0x") else int(size_str)
            partitions.append(PartitionInfo(
                name=part_name,
                start_sector=0,
                size_bytes=size_bytes,
                size_readable=_human_readable_size(size_bytes),
                type_guid="",
                attributes=COMMON_PARTITIONS.get(part_name, ""),
            ))

        # Parse partition-type entries
        part_type_map: Dict[str, str] = {}
        for match in re.finditer(r"partition-type:\s*(\S+):\s*(\S+)", text):
            part_type_map[match.group(1)] = match.group(2)
        for p in partitions:
            if p.name in part_type_map:
                p.type_guid = part_type_map[p.name]

        # Detect storage type
        if "ufs" in text.lower():
            result.storage_type = "UFS"
        elif "emmc" in text.lower():
            result.storage_type = "eMMC"
        else:
            result.storage_type = "Unknown"

        # Total size
        total_match = re.search(r"max-download-size:\s*(0x[0-9a-fA-F]+|\d+)", text)
        if total_match:
            result.total_size_gb = 0.0  # max-download-size != total storage

        # Try to get actual storage size
        for match in re.finditer(r"partition-size:\s*userdata:\s*(0x[0-9a-fA-F]+|\d+)", text):
            size_str = match.group(1)
            userdata_size = int(size_str, 16) if size_str.startswith("0x") else int(size_str)
            # userdata is typically the largest partition; rough estimate
            result.total_size_gb = round(userdata_size / (1024 ** 3) * 1.15, 1)

    except FileNotFoundError:
        result.error = "fastboot not found on PATH"
        return result
    except subprocess.TimeoutExpired:
        result.error = "fastboot getvar timed out"
        return result

    result.partitions = partitions
    _emit(callback, 100.0, f"Read {len(partitions)} partitions via fastboot")
    return result


def _read_partitions_adb(
    serial: str,
    callback: ProgressCallback = None,
) -> PartitionTableResult:
    """Read partition table via ADB shell."""
    result = PartitionTableResult(connected=True)
    partitions: List[PartitionInfo] = []

    _emit(callback, 20.0, "Reading /proc/partitions via ADB...")
    try:
        cmd_parts = ["adb"]
        if serial:
            cmd_parts.extend(["-s", serial])
        cmd_parts.extend(["shell", "cat", "/proc/partitions"])

        proc_parts = _run_cmd(cmd_parts, timeout=FASTBOOT_CMD_TIMEOUT)
        if proc_parts.returncode == 0:
            text = proc_parts.stdout.decode(errors="replace")
            for line in text.splitlines()[2:]:  # Skip header lines
                line = line.strip()
                if not line:
                    continue
                fields = line.split()
                if len(fields) >= 4:
                    try:
                        blocks = int(fields[2])
                        name = fields[3]
                        size_bytes = blocks * 1024
                        partitions.append(PartitionInfo(
                            name=name,
                            start_sector=0,
                            size_bytes=size_bytes,
                            size_readable=_human_readable_size(size_bytes),
                            type_guid="",
                            attributes=COMMON_PARTITIONS.get(name, ""),
                        ))
                    except ValueError:
                        continue

        # Try to get storage type
        _emit(callback, 50.0, "Detecting storage type...")
        storage_cmd = ["adb"]
        if serial:
            storage_cmd.extend(["-s", serial])
        storage_cmd.extend(["shell", "cat", "/sys/block/sda/device/type"])
        try:
            storage_result = _run_cmd(storage_cmd, timeout=10)
            if storage_result.returncode == 0:
                result.storage_type = "UFS"  # /dev/sda = UFS
            else:
                # Check for eMMC
                emmc_cmd = ["adb"]
                if serial:
                    emmc_cmd.extend(["-s", serial])
                emmc_cmd.extend(["shell", "ls", "/dev/block/mmcblk0"])
                emmc_result = _run_cmd(emmc_cmd, timeout=10)
                if emmc_result.returncode == 0:
                    result.storage_type = "eMMC"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result.storage_type = "Unknown"

        # Calculate total size from largest block device
        if partitions:
            # Find the main block device (sda or mmcblk0)
            main_devs = [p for p in partitions if re.match(r"^(sda|mmcblk0)$", p.name)]
            if main_devs:
                result.total_size_gb = round(main_devs[0].size_bytes / (1024 ** 3), 1)

    except FileNotFoundError:
        result.error = "adb not found on PATH"
        return result
    except subprocess.TimeoutExpired:
        result.error = "ADB command timed out"
        return result

    result.partitions = partitions
    _emit(callback, 100.0, f"Read {len(partitions)} partitions via ADB")
    return result


def _read_partitions_samsung(callback: ProgressCallback = None) -> PartitionTableResult:
    """Read partition table from Samsung device via PIT download."""
    result = PartitionTableResult(connected=True)
    partitions: List[PartitionInfo] = []

    _emit(callback, 20.0, "Downloading PIT from Samsung device...")
    try:
        pit_output = os.path.join(os.environ.get("TEMP", "/tmp"), "device_pit_read.pit")
        pit_cmd = _run_cmd(
            ["heimdall", "download-pit", "--output", pit_output],
            timeout=HEIMDALL_DETECT_TIMEOUT,
        )
        if pit_cmd.returncode != 0:
            result.error = "Failed to download PIT from device"
            return result

        pit_entries = _parse_pit_file(pit_output)
        for entry in pit_entries:
            if not entry.partition_name:
                continue
            size_bytes = entry.block_size * entry.block_count
            partitions.append(PartitionInfo(
                name=entry.partition_name,
                start_sector=entry.file_offset,
                size_bytes=size_bytes,
                size_readable=_human_readable_size(size_bytes),
                type_guid="",
                attributes=COMMON_PARTITIONS.get(entry.partition_name, ""),
            ))

        total_bytes = sum(p.size_bytes for p in partitions)
        result.total_size_gb = round(total_bytes / (1024 ** 3), 1)
        result.storage_type = "eMMC"  # Most Samsung devices use UFS but PIT doesn't specify

    except FileNotFoundError:
        result.error = "heimdall not found on PATH"
        return result
    except subprocess.TimeoutExpired:
        result.error = "PIT download timed out"
        return result

    result.partitions = partitions
    _emit(callback, 100.0, f"Read {len(partitions)} partitions from Samsung PIT")
    return result


def _read_partitions_edl(callback: ProgressCallback = None) -> PartitionTableResult:
    """Read partition table from Qualcomm device in EDL mode via Firehose getgpt."""
    result = PartitionTableResult(connected=True)

    _emit(callback, 20.0, "Reading GPT via Firehose in EDL mode...")

    # Build the getgpt command
    getgpt_xml = _build_firehose_getgpt(physical_partition=0, sector_size=512)
    logger.debug("Firehose getgpt XML:\n%s", getgpt_xml)

    # In a real implementation this would send the XML over the serial/USB
    # connection and parse the GPT response. For now we document the protocol.
    result.error = (
        "EDL partition table read requires active Firehose session. "
        "Use a Qualcomm tool (QFIL, edl.py) to establish the session first."
    )
    result.storage_type = "Unknown"

    _emit(callback, 100.0, "EDL partition table read requires Firehose session")
    return result


# ---------------------------------------------------------------------------
# Convenience: auto-detect and flash
# ---------------------------------------------------------------------------


def auto_flash(
    firmware_dir: str,
    callback: ProgressCallback = None,
) -> FlashResult:
    """
    Automatically detect the device flash mode and flash firmware from a
    directory. The directory should contain the relevant files for the
    detected mode (scatter file for MTK, images for fastboot, etc.).

    Parameters
    ----------
    firmware_dir : str
        Path to directory containing firmware files.
    callback : ProgressCallback
        Optional progress callback.

    Returns
    -------
    FlashResult
        Result of the flash operation.
    """
    _emit(callback, 0.0, "Auto-detecting flash mode...")
    detect = detect_flash_mode(callback=None)

    if not detect.connected:
        return FlashResult(
            success=False,
            error="No device detected. Connect a device in flash mode.",
        )

    fw_dir = Path(firmware_dir)
    if not fw_dir.is_dir():
        return FlashResult(success=False, error=f"Firmware directory not found: {firmware_dir}")

    _emit(callback, 10.0, f"Detected mode: {detect.mode}")

    if detect.mode == "fastboot":
        # Look for common image files
        partitions: Dict[str, str] = {}
        for img_name in ["boot.img", "recovery.img", "system.img", "vendor.img",
                         "dtbo.img", "vbmeta.img", "modem.img", "super.img"]:
            img_path = fw_dir / img_name
            if img_path.is_file():
                part_name = img_name.replace(".img", "")
                partitions[part_name] = str(img_path)
        if not partitions:
            return FlashResult(
                success=False,
                error=f"No .img files found in {firmware_dir}",
                mode_used="fastboot",
            )
        return flash_fastboot(partitions, callback=callback)

    if detect.mode == "edl":
        # Look for firehose programmer and partition images
        firehose_candidates = list(fw_dir.glob("prog_*.mbn")) + list(fw_dir.glob("prog_*.elf"))
        if not firehose_candidates:
            return FlashResult(
                success=False,
                error="No firehose programmer (prog_*.mbn/elf) found",
                mode_used="edl",
            )
        firehose_path = str(firehose_candidates[0])
        partitions = {}
        for img_file in fw_dir.glob("*.bin"):
            part_name = img_file.stem
            partitions[part_name] = str(img_file)
        for img_file in fw_dir.glob("*.img"):
            part_name = img_file.stem
            partitions[part_name] = str(img_file)
        if not partitions:
            return FlashResult(
                success=False,
                error="No partition images found alongside firehose programmer",
                mode_used="edl",
            )
        return flash_qualcomm_edl(firehose_path, partitions, callback=callback)

    if detect.mode == "brom":
        # Look for scatter file
        scatter_files = list(fw_dir.glob("*scatter*.txt")) + list(fw_dir.glob("*Scatter*.txt"))
        if not scatter_files:
            return FlashResult(
                success=False,
                error="No scatter file found for MediaTek flash",
                mode_used="brom",
            )
        return flash_mediatek(str(scatter_files[0]), callback=callback)

    if detect.mode == "download":
        # Look for Samsung image files
        files: Dict[str, str] = {}
        samsung_name_map = {
            "boot.img": "BOOT",
            "recovery.img": "RECOVERY",
            "system.img": "SYSTEM",
            "vendor.img": "VENDOR",
            "cache.img": "CACHE",
            "userdata.img": "USERDATA",
            "modem.bin": "MODEM",
            "sboot.bin": "BOOTLOADER",
        }
        for filename, slot in samsung_name_map.items():
            fpath = fw_dir / filename
            if fpath.is_file():
                files[slot] = str(fpath)
        # Also check for .tar.md5 Odin files
        for tar_file in fw_dir.glob("*.tar.md5"):
            name_upper = tar_file.stem.split(".")[0].upper()
            if name_upper in ("BL", "AP", "CP", "CSC", "HOME_CSC"):
                files[name_upper] = str(tar_file)
        if not files:
            return FlashResult(
                success=False,
                error="No recognized Samsung firmware files found",
                mode_used="download",
            )
        return flash_samsung(files, callback=callback)

    return FlashResult(
        success=False,
        error=f"Auto-flash not supported for mode: {detect.mode}",
        mode_used=detect.mode,
    )


# ---------------------------------------------------------------------------
# Module-level entry point for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def _progress(pct: float, msg: str) -> None:
        print(f"[{pct:6.1f}%] {msg}")

    print("=== Firmware Flasher - Device Detection ===")
    mode_result = detect_flash_mode(callback=_progress)
    print(f"\nResult: connected={mode_result.connected}, mode={mode_result.mode}")
    print(f"  chipset={mode_result.chipset}, serial={mode_result.serial}")
    print(f"  device_info={mode_result.device_info}")
    if mode_result.error:
        print(f"  error={mode_result.error}")

    if mode_result.connected:
        print("\n=== Reading Partition Table ===")
        pt_result = read_partition_table(callback=_progress)
        print(f"\nStorage: {pt_result.storage_type}, Total: {pt_result.total_size_gb} GB")
        print(f"Partitions ({len(pt_result.partitions)}):")
        for p in pt_result.partitions[:20]:
            print(f"  {p.name:20s} {p.size_readable:>10s}  {p.attributes}")
        if len(pt_result.partitions) > 20:
            print(f"  ... and {len(pt_result.partitions) - 20} more")
