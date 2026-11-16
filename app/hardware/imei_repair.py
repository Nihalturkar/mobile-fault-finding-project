"""
IMEI Repair Module for Mobile Repair Technicians.

Provides IMEI read/write, baseband inspection, and network-lock status
utilities.  All hardware access goes through ADB, AT commands, or the
Qualcomm DIAG interface (NV item 550).

WARNING
-------
IMEI repair functionality is intended **exclusively** for legitimate
repair scenarios — for example restoring a device's original IMEI after
a motherboard swap or reflash.  Changing an IMEI to evade theft
databases, commit fraud, or circumvent carrier policies is **illegal**
in most jurisdictions.  The author(s) accept no liability for misuse.

Requires
--------
* Android Platform Tools (``adb``, ``fastboot``) on PATH
* USB Debugging enabled on the target device
* For AT-command/DIAG methods: root access on the device

Usage::

    from app.hardware.imei_repair import read_imei, write_imei

    result = read_imei(callback=lambda pct, msg: print(f"{pct:.0f}% {msg}"))
    if result.connected:
        print(result.imei1, result.imei2)
"""

from __future__ import annotations

import logging
import re
import struct
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[float, str], None]]

# ---------------------------------------------------------------------------
#  Legal disclaimer (printed once at module load)
# ---------------------------------------------------------------------------
_LEGAL_NOTICE = (
    "IMEI REPAIR MODULE — FOR LEGITIMATE REPAIR USE ONLY.\n"
    "Tampering with IMEI numbers for fraud or theft evasion is a criminal\n"
    "offence in most countries.  By using this module you confirm that you\n"
    "are restoring a device's original, manufacturer-assigned IMEI."
)
logger.warning(_LEGAL_NOTICE)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

ADB_CMD = "adb"
FASTBOOT_CMD = "fastboot"

# Qualcomm NV item for IMEI
NV_UE_IMEI_I = 550

# Common serial device paths for AT commands
AT_DEVICE_PATHS = [
    "/dev/smd0",
    "/dev/ttyUSB0",
    "/dev/ttyUSB1",
    "/dev/ttyACM0",
    "/dev/ttyGS0",
    "/dev/smd11",
    "/dev/smd7",
]

# Timeout for subprocess calls (seconds)
CMD_TIMEOUT = 15

# ---------------------------------------------------------------------------
#  TAC (Type Allocation Code) database — first 8 digits of IMEI
#  Maps TAC prefix to (manufacturer, model_hint)
# ---------------------------------------------------------------------------

TAC_DATABASE: Dict[str, Tuple[str, str]] = {
    "35332508": ("Samsung", "Galaxy S21"),
    "35## 875009": ("Samsung", "Galaxy S22"),
    "35875010": ("Samsung", "Galaxy S23"),
    "35467011": ("Samsung", "Galaxy A54"),
    "35291712": ("Samsung", "Galaxy A14"),
    "35425613": ("Samsung", "Galaxy Z Flip5"),
    "35399411": ("Apple", "iPhone 13"),
    "35407115": ("Apple", "iPhone 14"),
    "35391112": ("Apple", "iPhone 15"),
    "35345210": ("Apple", "iPhone 12"),
    "86762603": ("Xiaomi", "Redmi Note 12"),
    "86152004": ("Xiaomi", "Redmi Note 11"),
    "86783705": ("Xiaomi", "POCO X5"),
    "86263106": ("Xiaomi", "Mi 13"),
    "86861207": ("OnePlus", "11"),
    "86943308": ("OnePlus", "Nord CE 3"),
    "86025409": ("Oppo", "Reno 10"),
    "86129710": ("Oppo", "A78"),
    "86423811": ("Vivo", "V29"),
    "86507912": ("Vivo", "Y36"),
    "35805114": ("Google", "Pixel 7"),
    "35809215": ("Google", "Pixel 8"),
    "35263516": ("Huawei", "P60"),
    "35471017": ("Huawei", "Nova 11"),
    "35923118": ("Motorola", "Edge 40"),
    "35106119": ("Motorola", "Moto G84"),
    "35288220": ("Nokia", "G42"),
    "35711321": ("Nokia", "X30"),
    "35452822": ("Realme", "11 Pro"),
    "35634923": ("Realme", "C55"),
    "35816024": ("Sony", "Xperia 1 V"),
    "35999125": ("Sony", "Xperia 10 V"),
    "35131226": ("LG", "Wing"),
    "35263327": ("LG", "Velvet"),
    "35714428": ("Asus", "ROG Phone 7"),
    "35826529": ("Asus", "Zenfone 10"),
    "35438630": ("ZTE", "Blade V40"),
    "35540731": ("Tecno", "Camon 20"),
    "35652832": ("Infinix", "Note 30"),
    "35764933": ("Lenovo", "Legion Phone"),
}

# ---------------------------------------------------------------------------
#  Band database — region ↦ expected LTE/NR bands
# ---------------------------------------------------------------------------

BAND_DATABASE: Dict[str, List[str]] = {
    "north_america": [
        "B2", "B4", "B5", "B7", "B12", "B13", "B14", "B17",
        "B25", "B26", "B29", "B30", "B41", "B46", "B48",
        "B66", "B71",
        "n2", "n5", "n7", "n25", "n41", "n66", "n71",
        "n77", "n78", "n260", "n261",
    ],
    "europe": [
        "B1", "B3", "B7", "B8", "B20", "B28", "B32", "B38",
        "B40", "B42", "B43",
        "n1", "n3", "n7", "n8", "n20", "n28", "n38",
        "n40", "n41", "n77", "n78",
    ],
    "asia_pacific": [
        "B1", "B3", "B5", "B7", "B8", "B28", "B38", "B39",
        "B40", "B41",
        "n1", "n3", "n5", "n7", "n8", "n28", "n38",
        "n40", "n41", "n77", "n78", "n79",
    ],
    "india": [
        "B1", "B3", "B5", "B8", "B40", "B41",
        "n1", "n3", "n5", "n8", "n28", "n40", "n41",
        "n77", "n78",
    ],
    "china": [
        "B1", "B3", "B5", "B8", "B34", "B38", "B39",
        "B40", "B41",
        "n1", "n3", "n5", "n8", "n28", "n38", "n41",
        "n77", "n78", "n79",
    ],
    "japan": [
        "B1", "B3", "B8", "B11", "B18", "B19", "B21",
        "B26", "B28", "B41", "B42",
        "n1", "n3", "n28", "n41", "n77", "n78", "n79",
        "n257",
    ],
    "south_america": [
        "B1", "B2", "B3", "B4", "B5", "B7", "B8",
        "B28", "B38", "B40",
        "n1", "n3", "n7", "n28", "n41", "n77", "n78",
    ],
    "africa": [
        "B1", "B3", "B5", "B7", "B8", "B20", "B28",
        "B38", "B40", "B41",
        "n1", "n3", "n7", "n28", "n41", "n78",
    ],
}

# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class IMEIReadResult:
    """Result of an IMEI read operation."""
    connected: bool = False
    error: Optional[str] = None
    imei1: str = ""
    imei2: str = ""
    meid: str = ""
    serial_number: str = ""
    read_method: str = ""          # adb / at_command / diag
    sv_number: str = ""
    baseband_version: str = ""


@dataclass
class IMEIWriteResult:
    """Result of an IMEI write operation."""
    success: bool = False
    error: Optional[str] = None
    imei1_written: str = ""
    imei2_written: str = ""
    method_used: str = ""
    steps_performed: List[str] = field(default_factory=list)
    verification_passed: bool = False
    reboot_required: bool = False


@dataclass
class BasebandResult:
    """Result of a baseband version check."""
    connected: bool = False
    error: Optional[str] = None
    baseband_version: str = ""
    modem_version: str = ""
    rf_version: str = ""
    chipset: str = ""
    bands_supported: List[str] = field(default_factory=list)
    status: str = ""               # ok / degraded / missing / unknown


@dataclass
class BasebandRepairResult:
    """Result of a baseband repair attempt."""
    success: bool = False
    error: Optional[str] = None
    steps: List[str] = field(default_factory=list)
    baseband_after: str = ""
    method_used: str = ""
    reboot_done: bool = False


@dataclass
class NetworkLockResult:
    """Result of a network lock status check."""
    connected: bool = False
    error: Optional[str] = None
    lock_status: str = ""          # locked / unlocked / partially_unlocked
    carrier: str = ""
    nck_attempts_remaining: int = -1
    mck_attempts_remaining: int = -1
    spck_attempts_remaining: int = -1
    sim_status: str = ""


# ---------------------------------------------------------------------------
#  Helpers — subprocess wrappers
# ---------------------------------------------------------------------------

def _run_adb(args: List[str], timeout: int = CMD_TIMEOUT) -> Tuple[int, str, str]:
    """Run an ``adb`` command and return (returncode, stdout, stderr)."""
    cmd = [ADB_CMD] + args
    logger.debug("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return -1, "", "adb not found on PATH"
    except subprocess.TimeoutExpired:
        return -2, "", f"adb command timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return -3, "", str(exc)


def _run_adb_shell(command: str, timeout: int = CMD_TIMEOUT) -> Tuple[int, str, str]:
    """Run ``adb shell <command>``."""
    return _run_adb(["shell", command], timeout=timeout)


def _run_fastboot(args: List[str], timeout: int = CMD_TIMEOUT) -> Tuple[int, str, str]:
    """Run a ``fastboot`` command and return (returncode, stdout, stderr)."""
    cmd = [FASTBOOT_CMD] + args
    logger.debug("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return -1, "", "fastboot not found on PATH"
    except subprocess.TimeoutExpired:
        return -2, "", f"fastboot command timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return -3, "", str(exc)


def _emit(callback: ProgressCallback, pct: float, msg: str) -> None:
    """Safely invoke a progress callback."""
    if callback is not None:
        try:
            callback(pct, msg)
        except Exception:  # noqa: BLE001
            logger.debug("Progress callback raised; ignoring.")


# ---------------------------------------------------------------------------
#  IMEI validation utilities
# ---------------------------------------------------------------------------

def luhn_checksum(number_str: str) -> int:
    """Compute the Luhn check digit for a numeric string.

    For a 14-digit IMEI body the return value is the 15th check digit.
    """
    digits = [int(d) for d in number_str]
    odd_sum = sum(digits[-1::-2])
    even_digits = digits[-2::-2]
    even_sum = 0
    for d in even_digits:
        d *= 2
        even_sum += d if d < 10 else d - 9
    total = odd_sum + even_sum
    return (10 - (total % 10)) % 10


def validate_imei(imei: str) -> Tuple[bool, str]:
    """Validate an IMEI string (15 digits, Luhn check).

    Returns (valid, reason).
    """
    if not imei:
        return False, "IMEI is empty"
    if not imei.isdigit():
        return False, "IMEI must contain only digits"
    if len(imei) != 15:
        return False, f"IMEI must be 15 digits, got {len(imei)}"

    body = imei[:14]
    expected_check = luhn_checksum(body)
    actual_check = int(imei[14])
    if expected_check != actual_check:
        return False, (
            f"Luhn check failed: expected check digit {expected_check}, "
            f"got {actual_check}"
        )
    return True, "Valid"


def compute_imei_check_digit(imei_body: str) -> str:
    """Given 14-digit IMEI body, return the full 15-digit IMEI."""
    if len(imei_body) != 14 or not imei_body.isdigit():
        raise ValueError("IMEI body must be exactly 14 digits")
    return imei_body + str(luhn_checksum(imei_body))


def lookup_tac(imei: str) -> Tuple[str, str]:
    """Look up manufacturer and model hint from the TAC (first 8 digits).

    Returns (manufacturer, model_hint) or ("Unknown", "Unknown").
    """
    tac = imei[:8]
    if tac in TAC_DATABASE:
        return TAC_DATABASE[tac]
    # Try a 6-digit prefix match (less precise)
    for key, value in TAC_DATABASE.items():
        if key[:6] == tac[:6]:
            return value
    return ("Unknown", "Unknown")


def imei_to_nv_bytes(imei: str) -> bytes:
    """Encode a 15-digit IMEI into the 9-byte NV format used by Qualcomm
    NV item 550 (NV_UE_IMEI_I).

    Byte layout::

        byte 0   = 0x08 (length indicator — 8 IMEI nibble-pairs follow)
        byte 1   = (digit1 << 4) | 0x0A   (0x0A marks the start)
        byte 2-8 = packed BCD pairs of remaining digits
    """
    if len(imei) != 15 or not imei.isdigit():
        raise ValueError("IMEI must be exactly 15 digits")

    result = bytearray(9)
    result[0] = 0x08

    # First byte after length: start marker + first digit
    result[1] = (int(imei[0]) << 4) | 0x0A

    # Remaining 14 digits packed as BCD pairs
    idx = 1
    for byte_pos in range(2, 9):
        d1 = int(imei[idx])
        d2 = int(imei[idx + 1]) if idx + 1 < 15 else 0
        result[byte_pos] = (d2 << 4) | d1
        idx += 2

    return bytes(result)


def nv_bytes_to_imei(data: bytes) -> str:
    """Decode the 9-byte Qualcomm NV IMEI format back to a 15-digit string."""
    if len(data) < 9:
        raise ValueError(f"Expected 9 bytes, got {len(data)}")

    digits: List[str] = []

    # First digit comes from high nibble of byte 1
    digits.append(str((data[1] >> 4) & 0x0F))

    # Remaining digits are packed BCD in bytes 2-8
    for byte_pos in range(2, 9):
        lo = data[byte_pos] & 0x0F
        hi = (data[byte_pos] >> 4) & 0x0F
        digits.append(str(lo))
        digits.append(str(hi))

    return "".join(digits[:15])


# ---------------------------------------------------------------------------
#  ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection() -> Tuple[bool, str]:
    """Return (connected, error_or_empty) for ADB device presence."""
    rc, out, err = _run_adb(["devices"])
    if rc != 0:
        return False, err or "adb command failed"

    lines = [l for l in out.splitlines() if "\tdevice" in l]
    if not lines:
        return False, "No ADB device found (is USB debugging enabled?)"
    return True, ""


# ---------------------------------------------------------------------------
#  IMEI reading — individual methods
# ---------------------------------------------------------------------------

def _parse_parcel_string(parcel_output: str) -> str:
    """Extract a string from Android Binder parcel output.

    ``service call iphonesubinfo`` returns data in this format::

        Result: Parcel(
          0x00000000: 00000000 0000000f 00350033 00330033 '........3.5.3.3.'
          0x00000010: 00310030 00390030 00380037 00360035 '0.1.0.9.7.8.5.6.'
          0x00000020: 00330032 00000034                    '2.3.4...'        )

    Each data line starts with ``0xNNNNNNNN:`` (the byte offset), followed
    by 1-4 hex words, and an ASCII preview in single quotes.

    Each 32-bit hex word holds two UTF-16 code-units packed as:
    ``HHHHLLLL`` where ``LLLL`` (low 16 bits) is the first character and
    ``HHHH`` (high 16 bits) is the second.  For example ``00350033``
    encodes ``'3'`` (0x0033) then ``'5'`` (0x0035).

    The first two data words are always:
      - word 0: status/error code (usually ``00000000``)
      - word 1: string length in UTF-16 chars (e.g. ``0000000f`` = 15)

    **This function parses the hex data words directly**, skipping line
    addresses and the ASCII preview, to reliably extract all digits
    including the last 2-3 that the old quote-based method lost.
    """
    # Parse each data line individually, extracting only the hex words
    # between the "0xNNNNNNNN:" prefix and the "'" that starts the preview.
    # This avoids mixing up line addresses with data words.
    all_data_words: List[str] = []

    for line in parcel_output.splitlines():
        # Match lines like: "  0x00000000: 00000000 0000000f 00350033 ... '...'"
        m = re.match(r"\s*0x[0-9a-fA-F]+:\s+(.+?)(?:'|$)", line)
        if not m:
            continue
        # Extract hex words from the data portion (before the quote)
        data_part = m.group(1)
        words = re.findall(r'[0-9a-fA-F]{8}', data_part)
        all_data_words.extend(words)

    if len(all_data_words) < 3:
        # Fallback: try the old quote-based method
        chars = re.findall(r"'(.*?)'", parcel_output)
        raw = "".join(chars).replace(".", "").replace(" ", "")
        return re.sub(r"[^0-9]", "", raw)

    # Skip word[0] (status) and word[1] (string length).
    # Data words start at index 2.
    str_len = int(all_data_words[1], 16) if len(all_data_words) > 1 else 0
    result_chars: List[str] = []

    for word_hex in all_data_words[2:]:
        word_val = int(word_hex, 16)
        # Low 16 bits = first character, high 16 bits = second character
        ch1 = word_val & 0xFFFF
        ch2 = (word_val >> 16) & 0xFFFF
        if ch1 != 0:
            result_chars.append(chr(ch1))
        if ch2 != 0:
            result_chars.append(chr(ch2))

    # Trim to declared string length if available
    if 0 < str_len < len(result_chars):
        result_chars = result_chars[:str_len]

    return "".join(result_chars)


def _read_imei_adb_service_call() -> Tuple[str, str]:
    """Read IMEI via ``service call iphonesubinfo 1``.

    The output is a Binder parcel with UTF-16LE encoded IMEI string.
    We parse the hex words directly (not the quote preview) to avoid
    losing the last 2-3 digits.

    On Android 5+, ``service call iphonesubinfo 1 s16 com.android.shell``
    is also tried (some ROMs require the package name argument).
    """
    # Try with and without package argument
    commands = [
        "service call iphonesubinfo 1 s16 com.android.shell",
        "service call iphonesubinfo 1",
    ]

    imei1 = ""
    for cmd in commands:
        rc, out, err = _run_adb_shell(cmd)
        if rc == 0 and out and "Parcel" in out:
            raw = _parse_parcel_string(out)
            digits = re.sub(r"[^0-9]", "", raw)
            if len(digits) >= 15:
                imei1 = digits[:15]
                break

    # Slot 2 — subId 2
    commands2 = [
        "service call iphonesubinfo 3 s16 com.android.shell",
        "service call iphonesubinfo 3",
    ]

    imei2 = ""
    for cmd in commands2:
        rc2, out2, err2 = _run_adb_shell(cmd)
        if rc2 == 0 and out2 and "Parcel" in out2:
            raw = _parse_parcel_string(out2)
            digits = re.sub(r"[^0-9]", "", raw)
            if len(digits) >= 15:
                imei2 = digits[:15]
                break

    return imei1, imei2


def _read_imei_adb_getprop() -> Tuple[str, str]:
    """Read IMEI from system properties."""
    props_to_try_slot1 = [
        "persist.radio.imei",
        "gsm.imei",
        "ro.ril.oem.imei",
        "persist.radio.imei1",
        "ril.imei",
    ]
    props_to_try_slot2 = [
        "persist.radio.imei2",
        "gsm.imei2",
        "persist.radio.imei1_2",
    ]

    imei1 = ""
    for prop in props_to_try_slot1:
        rc, out, _ = _run_adb_shell(f"getprop {prop}")
        if rc == 0 and out and len(out) >= 15:
            digits = re.sub(r"[^0-9]", "", out)
            if len(digits) >= 15:
                imei1 = digits[:15]
                break

    imei2 = ""
    for prop in props_to_try_slot2:
        rc, out, _ = _run_adb_shell(f"getprop {prop}")
        if rc == 0 and out and len(out) >= 15:
            digits = re.sub(r"[^0-9]", "", out)
            if len(digits) >= 15:
                imei2 = digits[:15]
                break

    return imei1, imei2


def _read_imei_dumpsys() -> Tuple[str, str]:
    """Read IMEI via ``dumpsys iphonesubinfo``."""
    rc, out, err = _run_adb_shell("dumpsys iphonesubinfo")
    imei1, imei2 = "", ""
    if rc == 0 and out:
        matches = re.findall(r"Device ID\s*=\s*(\d{15})", out)
        if matches:
            imei1 = matches[0]
        if len(matches) > 1:
            imei2 = matches[1]

        # Fallback: look for "Phone 0" / "Phone 1" sections
        if not imei1:
            m = re.search(r"Phone\s*0.*?IMEI\s*[=:]\s*(\d{15})", out, re.S)
            if m:
                imei1 = m.group(1)
        if not imei2:
            m = re.search(r"Phone\s*1.*?IMEI\s*[=:]\s*(\d{15})", out, re.S)
            if m:
                imei2 = m.group(1)

    return imei1, imei2


def _read_imei_at_command() -> Tuple[str, str]:
    """Read IMEI via AT+CGSN sent to a serial device node.

    Requires root (``adb shell su -c ...``).
    """
    imei1 = ""
    for dev in AT_DEVICE_PATHS:
        # Check if device node exists
        rc, out, _ = _run_adb_shell(f"su -c 'test -e {dev} && echo EXISTS'")
        if rc != 0 or "EXISTS" not in out:
            continue

        # Send AT+CGSN
        cmd = f"su -c 'echo -e \"AT+CGSN\\r\" > {dev} && cat {dev}'"
        rc, out, _ = _run_adb_shell(cmd, timeout=8)
        if rc == 0 and out:
            match = re.search(r"(\d{15})", out)
            if match:
                imei1 = match.group(1)
                logger.info("IMEI read via AT+CGSN on %s", dev)
                break

    # Try slot 2 via AT+CGSN on second port
    imei2 = ""
    for dev in AT_DEVICE_PATHS:
        if "USB1" in dev or "smd11" in dev:
            rc, out, _ = _run_adb_shell(f"su -c 'test -e {dev} && echo EXISTS'")
            if rc != 0 or "EXISTS" not in out:
                continue
            cmd = f"su -c 'echo -e \"AT+CGSN\\r\" > {dev} && cat {dev}'"
            rc, out, _ = _run_adb_shell(cmd, timeout=8)
            if rc == 0 and out:
                match = re.search(r"(\d{15})", out)
                if match:
                    imei2 = match.group(1)
                    break

    return imei1, imei2


def _read_imei_diag() -> Tuple[str, str]:
    """Read IMEI via Qualcomm DIAG — NV read item 550.

    Sends an NV_READ_F (0x26) command to ``/dev/diag`` and parses the
    9-byte IMEI payload.  Requires root.
    """
    imei1, imei2 = "", ""

    # Build NV_READ_F packet:  cmd_code(1) + nv_item(2) + data(128) + status(2)
    nv_item_bytes = struct.pack("<H", NV_UE_IMEI_I)
    read_cmd_hex = "26" + nv_item_bytes.hex() + "00" * 128 + "0000"

    rc, out, _ = _run_adb_shell(
        f"su -c 'echo {read_cmd_hex} | xxd -r -p > /dev/diag "
        f"&& dd if=/dev/diag bs=133 count=1 2>/dev/null | xxd -p'",
        timeout=10,
    )
    if rc == 0 and out:
        hex_str = out.replace("\n", "").replace(" ", "")
        # Response: cmd_code(1) + nv_item(2) + data(128) + status(2)
        if len(hex_str) >= 266:  # 133 bytes * 2 hex chars
            data_start = 6  # skip cmd(2) + nv_item(4)
            imei_hex = hex_str[data_start:data_start + 18]  # 9 bytes
            try:
                imei_bytes = bytes.fromhex(imei_hex)
                imei1 = nv_bytes_to_imei(imei_bytes)
                logger.info("IMEI read via DIAG NV550")
            except (ValueError, IndexError):
                logger.warning("Failed to decode DIAG NV550 response")

    # Try NV item 1920 for second IMEI slot (some chipsets)
    nv_item2_bytes = struct.pack("<H", 1920)
    read_cmd2_hex = "26" + nv_item2_bytes.hex() + "00" * 128 + "0000"

    rc2, out2, _ = _run_adb_shell(
        f"su -c 'echo {read_cmd2_hex} | xxd -r -p > /dev/diag "
        f"&& dd if=/dev/diag bs=133 count=1 2>/dev/null | xxd -p'",
        timeout=10,
    )
    if rc2 == 0 and out2:
        hex_str = out2.replace("\n", "").replace(" ", "")
        if len(hex_str) >= 266:
            data_start = 6
            imei_hex = hex_str[data_start:data_start + 18]
            try:
                imei_bytes = bytes.fromhex(imei_hex)
                imei2 = nv_bytes_to_imei(imei_bytes)
            except (ValueError, IndexError):
                pass

    return imei1, imei2


# ---------------------------------------------------------------------------
#  Ancillary info helpers
# ---------------------------------------------------------------------------

def _read_meid() -> str:
    """Read MEID (for CDMA devices)."""
    rc, out, _ = _run_adb_shell("service call iphonesubinfo 6")
    if rc == 0 and out and "Parcel" in out:
        raw = _parse_parcel_string(out)
        digits = re.sub(r"[^0-9A-Fa-f]", "", raw)
        if len(digits) >= 14:
            return digits[:14].upper()
    # Fallback
    rc, out, _ = _run_adb_shell("getprop persist.radio.meid")
    if rc == 0 and out:
        cleaned = re.sub(r"[^0-9A-Fa-f]", "", out)
        if len(cleaned) >= 14:
            return cleaned[:14].upper()
    return ""


def _read_serial_number() -> str:
    """Read device serial number."""
    rc, out, _ = _run_adb(["get-serialno"])
    if rc == 0 and out and out != "unknown":
        return out.strip()
    rc, out, _ = _run_adb_shell("getprop ro.serialno")
    if rc == 0 and out:
        return out.strip()
    return ""


def _read_sv_number() -> str:
    """Read IMEISV (software version appended to IMEI)."""
    rc, out, _ = _run_adb_shell("service call iphonesubinfo 2")
    if rc == 0 and out and "Parcel" in out:
        raw = _parse_parcel_string(out)
        digits = re.sub(r"[^0-9]", "", raw)
        if digits:
            return digits
    rc, out, _ = _run_adb_shell("getprop gsm.version.imeisv")
    if rc == 0 and out:
        return out.strip()
    return ""


def _read_baseband_version_simple() -> str:
    """Read the baseband version string."""
    rc, out, _ = _run_adb_shell("getprop gsm.version.baseband")
    if rc == 0 and out:
        return out.strip()
    rc, out, _ = _run_adb_shell("getprop ro.baseband")
    if rc == 0 and out:
        return out.strip()
    return ""


# ---------------------------------------------------------------------------
#  Public: read_imei
# ---------------------------------------------------------------------------

def read_imei(callback: ProgressCallback = None) -> IMEIReadResult:
    """Read IMEI(s) from the connected device using multiple methods.

    Methods are tried in order of reliability:

    1. ``service call iphonesubinfo`` (ADB, no root)
    2. ``getprop`` system properties (ADB, no root)
    3. ``dumpsys iphonesubinfo`` (ADB, no root)
    4. AT+CGSN via serial device (root required)
    5. Qualcomm DIAG NV read (root required)

    Parameters
    ----------
    callback : callable, optional
        ``callback(pct: float, msg: str)`` for progress updates.

    Returns
    -------
    IMEIReadResult
    """
    result = IMEIReadResult()
    _emit(callback, 0.0, "Checking ADB connection...")

    connected, conn_err = _check_adb_connection()
    if not connected:
        result.error = conn_err
        _emit(callback, 100.0, f"Connection failed: {conn_err}")
        return result

    result.connected = True
    _emit(callback, 10.0, "Device connected — reading IMEI...")

    methods: List[Tuple[str, Callable[[], Tuple[str, str]]]] = [
        ("adb", _read_imei_adb_service_call),
        ("adb", _read_imei_adb_getprop),
        ("adb", _read_imei_dumpsys),
        ("at_command", _read_imei_at_command),
        ("diag", _read_imei_diag),
    ]

    pct_step = 60.0 / len(methods)
    current_pct = 10.0

    for method_name, method_fn in methods:
        _emit(callback, current_pct, f"Trying method: {method_name} ({method_fn.__name__})")
        logger.info("Trying IMEI read method: %s", method_fn.__name__)

        try:
            imei1, imei2 = method_fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Method %s failed: %s", method_fn.__name__, exc)
            current_pct += pct_step
            continue

        if imei1:
            result.imei1 = imei1
            result.read_method = method_name
            if imei2:
                result.imei2 = imei2
            logger.info("IMEI1 obtained via %s: %s***", method_name, imei1[:6])
            break

        current_pct += pct_step

    if not result.imei1:
        result.error = "Could not read IMEI via any available method"
        _emit(callback, 100.0, "IMEI read failed")
        return result

    # If we still need IMEI2, try remaining methods
    if not result.imei2:
        for _, method_fn in methods:
            try:
                _, imei2 = method_fn()
                if imei2:
                    result.imei2 = imei2
                    break
            except Exception:  # noqa: BLE001
                continue

    _emit(callback, 75.0, "Reading ancillary identifiers...")

    # Ancillary info
    result.meid = _read_meid()
    result.serial_number = _read_serial_number()
    result.sv_number = _read_sv_number()
    result.baseband_version = _read_baseband_version_simple()

    _emit(callback, 95.0, "Validating IMEI...")
    valid, reason = validate_imei(result.imei1)
    if not valid:
        logger.warning("IMEI1 validation: %s", reason)

    _emit(callback, 100.0, "IMEI read complete")
    return result


# ---------------------------------------------------------------------------
#  IMEI writing — internal methods
# ---------------------------------------------------------------------------

def _write_imei_at_command(
    imei1: str,
    imei2: Optional[str],
    callback: ProgressCallback,
) -> Tuple[bool, List[str], str]:
    """Write IMEI via AT+EGMR commands.  Requires root.

    AT+EGMR=1,7,"<IMEI>"  → slot 1
    AT+EGMR=1,10,"<IMEI>" → slot 2

    Returns (success, steps, error).
    """
    steps: List[str] = []
    active_dev = ""

    # Find a working AT device
    for dev in AT_DEVICE_PATHS:
        rc, out, _ = _run_adb_shell(f"su -c 'test -e {dev} && echo EXISTS'")
        if rc == 0 and "EXISTS" in out:
            active_dev = dev
            steps.append(f"Found AT device: {dev}")
            break

    if not active_dev:
        return False, steps, "No AT command device found (need root)"

    _emit(callback, 40.0, f"Writing IMEI1 via AT+EGMR on {active_dev}...")
    cmd1 = f'su -c \'echo -e "AT+EGMR=1,7,\\"{imei1}\\"\\r" > {active_dev}\''
    rc, out, err = _run_adb_shell(cmd1, timeout=10)
    if rc != 0:
        return False, steps, f"AT+EGMR slot 1 failed: {err}"
    steps.append(f"AT+EGMR=1,7 sent for IMEI1: {imei1}")

    # Verify write
    time.sleep(1)
    cmd_verify = f"su -c 'echo -e \"AT+EGMR=0,7\\r\" > {active_dev} && cat {active_dev}'"
    rc, out, _ = _run_adb_shell(cmd_verify, timeout=8)
    if rc == 0 and imei1 in out:
        steps.append("IMEI1 verification via AT+EGMR read: PASS")
    else:
        steps.append("IMEI1 verification via AT+EGMR read: could not confirm")

    if imei2:
        _emit(callback, 55.0, f"Writing IMEI2 via AT+EGMR on {active_dev}...")
        cmd2 = f'su -c \'echo -e "AT+EGMR=1,10,\\"{imei2}\\"\\r" > {active_dev}\''
        rc, out, err = _run_adb_shell(cmd2, timeout=10)
        if rc != 0:
            return False, steps, f"AT+EGMR slot 2 failed: {err}"
        steps.append(f"AT+EGMR=1,10 sent for IMEI2: {imei2}")

        time.sleep(1)
        cmd_verify2 = f"su -c 'echo -e \"AT+EGMR=0,10\\r\" > {active_dev} && cat {active_dev}'"
        rc, out, _ = _run_adb_shell(cmd_verify2, timeout=8)
        if rc == 0 and imei2 in out:
            steps.append("IMEI2 verification via AT+EGMR read: PASS")
        else:
            steps.append("IMEI2 verification via AT+EGMR read: could not confirm")

    return True, steps, ""


def _write_imei_diag(
    imei1: str,
    imei2: Optional[str],
    callback: ProgressCallback,
) -> Tuple[bool, List[str], str]:
    """Write IMEI via Qualcomm DIAG — NV write item 550.

    Sends an NV_WRITE_F (0x27) command to ``/dev/diag``.
    Requires root and Qualcomm chipset.

    Returns (success, steps, error).
    """
    steps: List[str] = []

    # Check /dev/diag exists
    rc, out, _ = _run_adb_shell("su -c 'test -c /dev/diag && echo EXISTS'")
    if rc != 0 or "EXISTS" not in out:
        return False, steps, "/dev/diag not available (non-Qualcomm or DIAG not enabled)"

    steps.append("DIAG device /dev/diag is accessible")
    _emit(callback, 40.0, "Encoding IMEI1 for NV write...")

    # Encode IMEI to NV format
    try:
        nv_data = imei_to_nv_bytes(imei1)
    except ValueError as exc:
        return False, steps, f"IMEI encoding error: {exc}"

    steps.append(f"IMEI1 encoded to NV format: {nv_data.hex()}")

    # Build NV_WRITE_F packet:  cmd_code(1) + nv_item(2) + data(128) + status(2)
    nv_item_bytes = struct.pack("<H", NV_UE_IMEI_I)
    # Pad NV data to 128 bytes
    padded_data = nv_data + b"\x00" * (128 - len(nv_data))
    write_cmd = b"\x27" + nv_item_bytes + padded_data + b"\x00\x00"
    write_cmd_hex = write_cmd.hex()

    _emit(callback, 50.0, "Writing IMEI1 to NV item 550...")
    rc, out, err = _run_adb_shell(
        f"su -c 'echo {write_cmd_hex} | xxd -r -p > /dev/diag'",
        timeout=10,
    )
    if rc != 0:
        return False, steps, f"DIAG NV write failed: {err}"
    steps.append("NV_WRITE_F command sent for IMEI1 (NV item 550)")

    # Read back for verification
    time.sleep(1)
    _emit(callback, 55.0, "Verifying IMEI1 NV write...")
    read_cmd_hex = "26" + nv_item_bytes.hex() + "00" * 128 + "0000"
    rc, out, _ = _run_adb_shell(
        f"su -c 'echo {read_cmd_hex} | xxd -r -p > /dev/diag "
        f"&& dd if=/dev/diag bs=133 count=1 2>/dev/null | xxd -p'",
        timeout=10,
    )
    if rc == 0 and out:
        hex_str = out.replace("\n", "").replace(" ", "")
        if len(hex_str) >= 266:
            data_start = 6
            readback_hex = hex_str[data_start:data_start + 18]
            try:
                readback_bytes = bytes.fromhex(readback_hex)
                readback_imei = nv_bytes_to_imei(readback_bytes)
                if readback_imei == imei1:
                    steps.append("IMEI1 NV readback verification: PASS")
                else:
                    steps.append(
                        f"IMEI1 NV readback mismatch: wrote {imei1}, "
                        f"read {readback_imei}"
                    )
            except (ValueError, IndexError):
                steps.append("IMEI1 NV readback: could not decode")
        else:
            steps.append("IMEI1 NV readback: short response")
    else:
        steps.append("IMEI1 NV readback: read command failed")

    # Write IMEI2 if provided (NV item 1920 on some chipsets)
    if imei2:
        _emit(callback, 60.0, "Encoding IMEI2 for NV write...")
        try:
            nv_data2 = imei_to_nv_bytes(imei2)
        except ValueError as exc:
            steps.append(f"IMEI2 encoding error: {exc}")
            return True, steps, ""  # IMEI1 succeeded, IMEI2 failed

        nv_item2_bytes = struct.pack("<H", 1920)
        padded_data2 = nv_data2 + b"\x00" * (128 - len(nv_data2))
        write_cmd2 = b"\x27" + nv_item2_bytes + padded_data2 + b"\x00\x00"
        write_cmd2_hex = write_cmd2.hex()

        _emit(callback, 65.0, "Writing IMEI2 to NV item 1920...")
        rc, out, err = _run_adb_shell(
            f"su -c 'echo {write_cmd2_hex} | xxd -r -p > /dev/diag'",
            timeout=10,
        )
        if rc != 0:
            steps.append(f"IMEI2 DIAG write failed: {err}")
        else:
            steps.append("NV_WRITE_F command sent for IMEI2 (NV item 1920)")

    return True, steps, ""


# ---------------------------------------------------------------------------
#  Public: write_imei
# ---------------------------------------------------------------------------

def write_imei(
    imei1: str,
    imei2: Optional[str] = None,
    callback: ProgressCallback = None,
) -> IMEIWriteResult:
    """Write IMEI to the connected device.

    Attempts AT+EGMR first; falls back to Qualcomm DIAG NV write.
    Both methods require root access on the device.

    .. warning::

        This function is intended **only** for restoring a device's
        original, manufacturer-assigned IMEI after a legitimate
        motherboard repair or replacement.  Misuse may violate local
        law.

    Parameters
    ----------
    imei1 : str
        15-digit IMEI for SIM slot 1.
    imei2 : str, optional
        15-digit IMEI for SIM slot 2 (dual-SIM devices).
    callback : callable, optional
        ``callback(pct: float, msg: str)`` for progress updates.

    Returns
    -------
    IMEIWriteResult
    """
    result = IMEIWriteResult()

    # -- Validate inputs ----------------------------------------------------
    _emit(callback, 0.0, "Validating IMEI input...")
    logger.warning(
        "IMEI WRITE requested — this is for legitimate repair only. "
        "Ensure you are restoring the device's original IMEI."
    )

    valid1, reason1 = validate_imei(imei1)
    if not valid1:
        result.error = f"IMEI1 invalid: {reason1}"
        _emit(callback, 100.0, result.error)
        return result

    if imei2:
        valid2, reason2 = validate_imei(imei2)
        if not valid2:
            result.error = f"IMEI2 invalid: {reason2}"
            _emit(callback, 100.0, result.error)
            return result

    result.steps_performed.append(f"IMEI1 validated: {imei1}")
    if imei2:
        result.steps_performed.append(f"IMEI2 validated: {imei2}")

    # -- Connection check ---------------------------------------------------
    _emit(callback, 10.0, "Checking ADB connection...")
    connected, conn_err = _check_adb_connection()
    if not connected:
        result.error = conn_err
        _emit(callback, 100.0, f"Connection failed: {conn_err}")
        return result
    result.steps_performed.append("ADB connection verified")

    # -- Read current IMEI for backup ---------------------------------------
    _emit(callback, 15.0, "Reading current IMEI for backup...")
    current_imei1, current_imei2 = "", ""
    try:
        current_imei1, current_imei2 = _read_imei_adb_service_call()
    except Exception:  # noqa: BLE001
        pass
    if current_imei1:
        result.steps_performed.append(f"Current IMEI1 backed up: {current_imei1}")
        logger.info("Current IMEI1 before write: %s", current_imei1)
    if current_imei2:
        result.steps_performed.append(f"Current IMEI2 backed up: {current_imei2}")

    # -- Attempt AT command method ------------------------------------------
    _emit(callback, 25.0, "Attempting AT+EGMR write method...")
    at_ok, at_steps, at_err = _write_imei_at_command(imei1, imei2, callback)
    result.steps_performed.extend(at_steps)

    if at_ok:
        result.success = True
        result.method_used = "at_command"
        result.imei1_written = imei1
        result.imei2_written = imei2 or ""
        result.reboot_required = True
        result.steps_performed.append("AT+EGMR write method succeeded")
    else:
        result.steps_performed.append(f"AT+EGMR method failed: {at_err}")
        logger.info("AT method failed, trying DIAG...")

        # -- Fallback to DIAG method ----------------------------------------
        _emit(callback, 35.0, "Attempting Qualcomm DIAG NV write method...")
        diag_ok, diag_steps, diag_err = _write_imei_diag(imei1, imei2, callback)
        result.steps_performed.extend(diag_steps)

        if diag_ok:
            result.success = True
            result.method_used = "diag"
            result.imei1_written = imei1
            result.imei2_written = imei2 or ""
            result.reboot_required = True
            result.steps_performed.append("DIAG NV write method succeeded")
        else:
            result.error = f"All write methods failed. AT: {at_err}; DIAG: {diag_err}"
            _emit(callback, 100.0, "IMEI write failed")
            return result

    # -- Post-write verification --------------------------------------------
    _emit(callback, 80.0, "Rebooting device for verification...")
    result.steps_performed.append("Initiating device reboot")
    _run_adb(["reboot"])

    # Wait for device to come back
    _emit(callback, 85.0, "Waiting for device to reboot...")
    rc, _, _ = _run_adb(["wait-for-device"], timeout=120)
    if rc != 0:
        result.steps_performed.append("Device did not reconnect after reboot")
        result.verification_passed = False
        _emit(callback, 100.0, "Write done but verification skipped (device offline)")
        return result

    # Give the radio stack time to initialise
    time.sleep(5)
    result.steps_performed.append("Device reconnected after reboot")

    _emit(callback, 90.0, "Verifying written IMEI...")
    try:
        verify_imei1, verify_imei2 = _read_imei_adb_service_call()
    except Exception:  # noqa: BLE001
        verify_imei1, verify_imei2 = "", ""

    if verify_imei1 == imei1:
        result.verification_passed = True
        result.steps_performed.append(f"IMEI1 post-reboot verification: PASS ({verify_imei1})")
    else:
        result.verification_passed = False
        result.steps_performed.append(
            f"IMEI1 post-reboot verification: MISMATCH "
            f"(expected {imei1}, got {verify_imei1 or 'empty'})"
        )

    if imei2 and verify_imei2:
        if verify_imei2 == imei2:
            result.steps_performed.append(f"IMEI2 post-reboot verification: PASS ({verify_imei2})")
        else:
            result.steps_performed.append(
                f"IMEI2 post-reboot verification: MISMATCH "
                f"(expected {imei2}, got {verify_imei2})"
            )

    _emit(callback, 100.0, "IMEI write complete")
    return result


# ---------------------------------------------------------------------------
#  Public: check_baseband
# ---------------------------------------------------------------------------

def check_baseband(callback: ProgressCallback = None) -> BasebandResult:
    """Read baseband / modem / RF version info from the connected device.

    Parameters
    ----------
    callback : callable, optional
        ``callback(pct: float, msg: str)`` for progress updates.

    Returns
    -------
    BasebandResult
    """
    result = BasebandResult()
    _emit(callback, 0.0, "Checking ADB connection...")

    connected, conn_err = _check_adb_connection()
    if not connected:
        result.error = conn_err
        _emit(callback, 100.0, f"Connection failed: {conn_err}")
        return result

    result.connected = True
    _emit(callback, 10.0, "Reading baseband version...")

    # Baseband version
    rc, out, _ = _run_adb_shell("getprop gsm.version.baseband")
    if rc == 0 and out:
        result.baseband_version = out.strip()
    else:
        rc, out, _ = _run_adb_shell("getprop ro.baseband")
        if rc == 0 and out:
            result.baseband_version = out.strip()

    _emit(callback, 25.0, "Reading modem version...")

    # Modem version
    rc, out, _ = _run_adb_shell("getprop persist.radio.modem.version")
    if rc == 0 and out:
        result.modem_version = out.strip()
    else:
        rc, out, _ = _run_adb_shell("getprop gsm.version.ril-impl")
        if rc == 0 and out:
            result.modem_version = out.strip()

    _emit(callback, 40.0, "Reading RF version...")

    # RF version
    rc, out, _ = _run_adb_shell("getprop gsm.version.rfcal")
    if rc == 0 and out:
        result.rf_version = out.strip()
    else:
        # Some devices store RF info in build props
        rc, out, _ = _run_adb_shell("getprop ro.hardware.rf")
        if rc == 0 and out:
            result.rf_version = out.strip()

    _emit(callback, 55.0, "Detecting chipset...")

    # Chipset
    chipset_props = [
        "ro.hardware.chipname",
        "ro.board.platform",
        "ro.hardware",
        "ro.soc.model",
        "persist.radio.multisim.config",
    ]
    for prop in chipset_props:
        rc, out, _ = _run_adb_shell(f"getprop {prop}")
        if rc == 0 and out and out.strip():
            result.chipset = out.strip()
            break

    _emit(callback, 70.0, "Reading supported bands...")

    # Supported bands — try multiple sources
    bands: List[str] = []

    # Method 1: dumpsys telephony.registry
    rc, out, _ = _run_adb_shell("dumpsys telephony.registry")
    if rc == 0 and out:
        band_matches = re.findall(r"(?:Band|band)\s*[:=]\s*(\d+)", out)
        for b in band_matches:
            band_str = f"B{b}"
            if band_str not in bands:
                bands.append(band_str)

    # Method 2: AT+COPS from serial (root)
    rc, out, _ = _run_adb_shell(
        "su -c 'cat /sys/devices/platform/*/capability 2>/dev/null'"
    )
    if rc == 0 and out:
        nr_bands = re.findall(r"n(\d+)", out)
        lte_bands = re.findall(r"B(\d+)", out)
        for b in lte_bands:
            band_str = f"B{b}"
            if band_str not in bands:
                bands.append(band_str)
        for b in nr_bands:
            band_str = f"n{b}"
            if band_str not in bands:
                bands.append(band_str)

    # Method 3: Read from build prop
    rc, out, _ = _run_adb_shell("getprop ro.telephony.default_network")
    if rc == 0 and out and out.strip():
        # The value is a numeric network type — not bands, but useful context
        logger.debug("Default network type: %s", out.strip())

    result.bands_supported = sorted(bands)

    _emit(callback, 85.0, "Determining baseband status...")

    # Determine overall status
    if result.baseband_version:
        if "unknown" in result.baseband_version.lower():
            result.status = "degraded"
        elif "null" in result.baseband_version.lower():
            result.status = "missing"
        else:
            result.status = "ok"
    else:
        result.status = "unknown"

    _emit(callback, 100.0, "Baseband check complete")
    return result


# ---------------------------------------------------------------------------
#  Public: repair_baseband  (MTK + Qualcomm)
# ---------------------------------------------------------------------------

def repair_baseband(callback: ProgressCallback = None) -> BasebandRepairResult:
    """Attempt to repair a missing/dead baseband on MediaTek and Qualcomm devices.

    Strategy (tried in order):
      1. Restart rild + ril-daemon services (no root needed)
      2. Restart ccci_mdinit / mdlogger (MTK-specific, no root)
      3. Clear ril/modem service crash counters via setprop (no root)
      4. Force modem reset via /sys/kernel/ccci/md1/reset (MTK, root)
      5. Restart rild with root + setenforce 0
      6. NVRAM modem data integrity check + touch (MTK, root)
      7. Reboot device and verify baseband appears

    Parameters
    ----------
    callback : callable, optional
        ``callback(pct: float, msg: str)`` for progress updates.

    Returns
    -------
    BasebandRepairResult
    """
    result = BasebandRepairResult()
    _emit(callback, 0.0, "Checking ADB connection...")

    connected, conn_err = _check_adb_connection()
    if not connected:
        result.error = conn_err
        _emit(callback, 100.0, f"Connection failed: {conn_err}")
        return result

    result.steps.append("ADB connection verified")
    _emit(callback, 5.0, "Reading initial baseband state...")

    # -- Read current state --------------------------------------------------
    rc, bb_before, _ = _run_adb_shell("getprop gsm.version.baseband")
    bb_before = bb_before.strip()
    result.steps.append(f"Baseband before repair: '{bb_before or 'EMPTY'}'")

    rc, chipset_raw, _ = _run_adb_shell("getprop ro.hardware.chipname")
    if not chipset_raw.strip():
        rc, chipset_raw, _ = _run_adb_shell("getprop ro.board.platform")
    chipset = chipset_raw.strip().lower()
    is_mtk = any(k in chipset for k in ["mt", "mtk", "dimensity", "helio"])
    result.steps.append(f"Chipset detected: '{chipset}' ({'MTK' if is_mtk else 'non-MTK'})")

    # -- Step 1: Stop + restart ril services (no root) -----------------------
    _emit(callback, 12.0, "Step 1: Restarting RIL daemon services...")
    ril_services = ["ril-daemon", "vendor.ril-daemon", "ril_daemon"]
    for svc in ril_services:
        _run_adb_shell(f"stop {svc}")
        time.sleep(0.5)
        _run_adb_shell(f"start {svc}")
    result.steps.append("RIL daemon stop/start sent")

    # -- Step 2: MTK-specific ccci/modem services (no root) ------------------
    if is_mtk:
        _emit(callback, 20.0, "Step 2: Restarting MTK modem init services...")
        mtk_services = [
            "ccci_mdinit", "mdlogger", "vendor.ccci_mdinit",
            "mtk_ril", "rilproxy", "gsm0710muxd",
        ]
        for svc in mtk_services:
            _run_adb_shell(f"stop {svc}")
            time.sleep(0.3)
            _run_adb_shell(f"start {svc}")
        result.steps.append("MTK ccci/modem services restarted")
    else:
        result.steps.append("Step 2 skipped (non-MTK)")

    # -- Step 3: Clear crash counters / radio restart props ------------------
    _emit(callback, 28.0, "Step 3: Clearing modem crash counters...")
    _run_adb_shell("setprop ril.approved.modemver none")
    _run_adb_shell("setprop vendor.mtk.md1.status init")
    _run_adb_shell("setprop gsm.version.baseband ''")
    _run_adb_shell("setprop ctl.restart ril-daemon")
    _run_adb_shell("setprop ctl.restart vendor.ril-daemon")
    result.steps.append("Modem crash counters / props cleared")

    # Wait for ril to settle
    time.sleep(4)

    # Quick check — did baseband appear already?
    rc, bb_now, _ = _run_adb_shell("getprop gsm.version.baseband")
    bb_now = bb_now.strip()
    if bb_now and bb_now not in ["unknown", "null", ""]:
        result.steps.append(f"Baseband recovered after service restart: {bb_now}")
        result.method_used = "service_restart"
        result.baseband_after = bb_now
        result.success = True
        _emit(callback, 50.0, f"Baseband recovered: {bb_now}")
        # Still do a reboot to make it permanent
    else:
        result.steps.append("Baseband still empty after service restart — trying deeper methods")

    # -- Step 4: MTK modem hardware reset via sysfs (root) -------------------
    if is_mtk and not result.success:
        _emit(callback, 35.0, "Step 4: MTK modem sysfs reset (needs root)...")
        rc, out, _ = _run_adb_shell(
            "su -c 'test -e /sys/kernel/ccci/md1/reset && echo EXISTS'"
        )
        if rc == 0 and "EXISTS" in out:
            _run_adb_shell("su -c 'echo 1 > /sys/kernel/ccci/md1/reset'")
            result.steps.append("MTK CCCI md1 reset triggered via sysfs")
            time.sleep(5)
        else:
            # Try via property
            _run_adb_shell("su -c 'setprop vendor.mtk.md.rst 1'")
            result.steps.append("MTK modem reset via vendor property")
            time.sleep(3)

    # -- Step 5: Force rild with SELinux permissive (root) -------------------
    if not result.success:
        _emit(callback, 42.0, "Step 5: Restarting rild with root + setenforce 0...")
        rc, _, _ = _run_adb_shell("su -c 'echo EXISTS'")
        has_root = rc == 0
        if has_root:
            _run_adb_shell("su -c 'setenforce 0'")
            _run_adb_shell("su -c 'stop ril-daemon'")
            _run_adb_shell("su -c 'stop vendor.ril-daemon'")
            time.sleep(1)
            _run_adb_shell("su -c 'start ril-daemon'")
            _run_adb_shell("su -c 'start vendor.ril-daemon'")
            result.steps.append("rild restarted as root with SELinux permissive")
            time.sleep(4)
        else:
            result.steps.append("Step 5 skipped — device not rooted")

    # -- Step 6: NVRAM modem data check (MTK, root) --------------------------
    if is_mtk and not result.success:
        _emit(callback, 52.0, "Step 6: Checking MTK NVRAM modem data...")
        rc, _, _ = _run_adb_shell("su -c 'echo EXISTS'")
        has_root = rc == 0
        if has_root:
            nvram_paths = [
                "/mnt/vendor/nvdata/md",
                "/nvdata/md",
                "/data/vendor/nvram/md",
            ]
            for nvpath in nvram_paths:
                rc, out, _ = _run_adb_shell(
                    f"su -c 'test -d {nvpath} && echo EXISTS'"
                )
                if rc == 0 and "EXISTS" in out:
                    # List and touch NVRAM IMEI file to trigger re-read
                    _run_adb_shell(
                        f"su -c 'ls {nvpath}/NVRAM/NVD_IMEI/ 2>/dev/null'"
                    )
                    _run_adb_shell(
                        f"su -c 'touch {nvpath}/NVRAM/NVD_IMEI/1 2>/dev/null'"
                    )
                    result.steps.append(f"NVRAM modem data touched: {nvpath}")
                    break
            else:
                result.steps.append("NVRAM modem path not accessible")
        else:
            result.steps.append("Step 6 skipped — device not rooted")

    # -- Step 7: Reboot and verify -------------------------------------------
    _emit(callback, 65.0, "Step 7: Rebooting device...")
    result.steps.append("Initiating reboot for modem stack reinit")
    _run_adb(["reboot"])
    result.reboot_done = True

    _emit(callback, 72.0, "Waiting for device to come back online...")
    rc, _, _ = _run_adb(["wait-for-device"], timeout=120)
    if rc != 0:
        result.steps.append("Device did not reconnect after reboot — verify manually")
        result.error = "Device offline after reboot — check manually"
        _emit(callback, 100.0, "Reboot wait timed out")
        return result

    result.steps.append("Device reconnected after reboot")
    _emit(callback, 85.0, "Waiting for modem stack to initialize...")
    time.sleep(8)  # Give rild and modem time to fully start

    # -- Final verification --------------------------------------------------
    _emit(callback, 92.0, "Verifying baseband after reboot...")
    rc, bb_after, _ = _run_adb_shell("getprop gsm.version.baseband")
    bb_after = bb_after.strip()
    result.baseband_after = bb_after

    if bb_after and bb_after not in ["unknown", "null", ""]:
        result.success = True
        if not result.method_used:
            result.method_used = "reboot_reinit"
        result.steps.append(f"Baseband recovered: '{bb_after}'")
        _emit(callback, 100.0, f"Baseband fixed: {bb_after}")
    else:
        result.success = False
        result.error = (
            "Baseband still empty after all repair steps. "
            "Modem firmware reflash (SP Flash Tool / Odin) required."
        )
        result.steps.append("Baseband still EMPTY after reboot — hardware/firmware flash needed")
        _emit(callback, 100.0, "Baseband repair failed — firmware flash required")

    return result


# ---------------------------------------------------------------------------
#  Public: check_network_lock
# ---------------------------------------------------------------------------

def check_network_lock(callback: ProgressCallback = None) -> NetworkLockResult:
    """Check network/SIM lock status on the connected device.

    Inspects NCK (Network Control Key), MCK (Master Control Key), and
    SPCK (Service Provider Control Key) counters when available.

    Parameters
    ----------
    callback : callable, optional
        ``callback(pct: float, msg: str)`` for progress updates.

    Returns
    -------
    NetworkLockResult
    """
    result = NetworkLockResult()
    _emit(callback, 0.0, "Checking ADB connection...")

    connected, conn_err = _check_adb_connection()
    if not connected:
        result.error = conn_err
        _emit(callback, 100.0, f"Connection failed: {conn_err}")
        return result

    result.connected = True
    _emit(callback, 10.0, "Checking SIM status...")

    # SIM status
    rc, out, _ = _run_adb_shell("getprop gsm.sim.state")
    if rc == 0 and out:
        result.sim_status = out.strip()
    else:
        result.sim_status = "UNKNOWN"

    _emit(callback, 25.0, "Reading carrier information...")

    # Carrier / operator
    carrier_props = [
        "gsm.sim.operator.alpha",
        "gsm.operator.alpha",
        "ro.cdma.home.operator.alpha",
        "persist.sys.carrier",
    ]
    for prop in carrier_props:
        rc, out, _ = _run_adb_shell(f"getprop {prop}")
        if rc == 0 and out and out.strip():
            result.carrier = out.strip()
            break

    _emit(callback, 40.0, "Checking network lock status...")

    # --- Network lock detection ---

    # Method 1: getprop checks
    lock_props = [
        "persist.sys.sim.locked",
        "gsm.sim.lock.status",
        "ro.sim.lock",
        "persist.radio.sim.lock",
    ]
    lock_detected = False
    for prop in lock_props:
        rc, out, _ = _run_adb_shell(f"getprop {prop}")
        if rc == 0 and out and out.strip():
            val = out.strip().lower()
            if val in ("1", "true", "locked"):
                lock_detected = True
                break

    # Method 2: dumpsys carrier_config
    _emit(callback, 50.0, "Inspecting carrier configuration...")
    rc, out, _ = _run_adb_shell("dumpsys carrier_config")
    if rc == 0 and out:
        if re.search(r"sim_lock.*?true", out, re.I):
            lock_detected = True
        if re.search(r"carrier_lock.*?true", out, re.I):
            lock_detected = True

    # Method 3: service call for lock status (Samsung-specific)
    _emit(callback, 60.0, "Querying lock service...")
    rc, out, _ = _run_adb_shell("service call phone 31")
    if rc == 0 and out:
        # Parse parcel output for lock indicator
        chars = re.findall(r"'(.*?)'", out)
        raw = "".join(chars).replace(".", "").replace(" ", "")
        if "1" in raw[:4]:
            lock_detected = True

    # Method 4: AT command query (root)
    _emit(callback, 70.0, "Querying AT lock counters...")
    nck_remaining = -1
    mck_remaining = -1
    spck_remaining = -1

    for dev in AT_DEVICE_PATHS:
        rc, out, _ = _run_adb_shell(f"su -c 'test -e {dev} && echo EXISTS'")
        if rc != 0 or "EXISTS" not in out:
            continue

        # Query lock counters via AT+CLCK
        at_queries = [
            ("PN", "nck"),    # Network Personalization
            ("PU", "mck"),    # Network Subset (master)
            ("PP", "spck"),   # Service Provider
        ]
        for facility, counter_name in at_queries:
            cmd = (
                f"su -c 'echo -e \"AT+CLCK=\\\"{facility}\\\",2\\r\" "
                f"> {dev} && cat {dev}'"
            )
            rc, out, _ = _run_adb_shell(cmd, timeout=8)
            if rc == 0 and out:
                # Parse +CLCK: <status>[,<remaining>]
                m = re.search(r"\+CLCK:\s*(\d+)(?:,\s*(\d+))?", out)
                if m:
                    status_val = int(m.group(1))
                    remaining = int(m.group(2)) if m.group(2) else -1
                    if status_val == 1:
                        lock_detected = True
                    if counter_name == "nck":
                        nck_remaining = remaining
                    elif counter_name == "mck":
                        mck_remaining = remaining
                    elif counter_name == "spck":
                        spck_remaining = remaining
        break  # Only need one working device

    result.nck_attempts_remaining = nck_remaining
    result.mck_attempts_remaining = mck_remaining
    result.spck_attempts_remaining = spck_remaining

    _emit(callback, 85.0, "Determining lock status...")

    # Check for partial unlock
    if lock_detected:
        # If some counters show unlocked but others locked
        has_locked = nck_remaining > 0 or mck_remaining > 0 or spck_remaining > 0
        all_known = nck_remaining >= 0 and mck_remaining >= 0 and spck_remaining >= 0
        if all_known and not has_locked:
            result.lock_status = "unlocked"
        elif all_known:
            some_zero = (
                nck_remaining == 0 or mck_remaining == 0 or spck_remaining == 0
            )
            if some_zero and has_locked:
                result.lock_status = "partially_unlocked"
            else:
                result.lock_status = "locked"
        else:
            result.lock_status = "locked"
    else:
        result.lock_status = "unlocked"

    # Method 5: Check SIM state for lock indicators
    if result.sim_status:
        sim_upper = result.sim_status.upper()
        if "NETWORK_LOCKED" in sim_upper:
            result.lock_status = "locked"
        elif "SIM_LOCKED" in sim_upper:
            result.lock_status = "locked"

    _emit(callback, 100.0, "Network lock check complete")
    return result


# ---------------------------------------------------------------------------
#  Convenience helpers
# ---------------------------------------------------------------------------

def get_device_summary(callback: ProgressCallback = None) -> Dict[str, object]:
    """Run all checks and return a combined summary dict.

    Useful for populating a repair-tool dashboard in one call.

    Parameters
    ----------
    callback : callable, optional
        ``callback(pct: float, msg: str)`` for progress updates.

    Returns
    -------
    dict
        Keys: ``imei``, ``baseband``, ``network_lock``, ``manufacturer``,
        ``model_hint``.
    """
    _emit(callback, 0.0, "Starting full device summary...")

    imei_result = read_imei(
        callback=lambda p, m: _emit(callback, p * 0.4, f"[IMEI] {m}")
    )
    baseband_result = check_baseband(
        callback=lambda p, m: _emit(callback, 40 + p * 0.3, f"[Baseband] {m}")
    )
    lock_result = check_network_lock(
        callback=lambda p, m: _emit(callback, 70 + p * 0.3, f"[Lock] {m}")
    )

    manufacturer, model_hint = "", ""
    if imei_result.imei1:
        manufacturer, model_hint = lookup_tac(imei_result.imei1)

    _emit(callback, 100.0, "Device summary complete")

    return {
        "imei": imei_result,
        "baseband": baseband_result,
        "network_lock": lock_result,
        "manufacturer": manufacturer,
        "model_hint": model_hint,
    }


def format_imei_result(result: IMEIReadResult) -> str:
    """Return a human-readable multiline string for an IMEIReadResult."""
    lines = [
        "=== IMEI Read Result ===",
        f"Connected       : {result.connected}",
        f"IMEI 1          : {result.imei1 or '(not read)'}",
        f"IMEI 2          : {result.imei2 or '(not read)'}",
        f"MEID            : {result.meid or '(not read)'}",
        f"Serial          : {result.serial_number or '(not read)'}",
        f"SV Number       : {result.sv_number or '(not read)'}",
        f"Baseband        : {result.baseband_version or '(not read)'}",
        f"Read Method     : {result.read_method or '(none)'}",
    ]
    if result.imei1:
        valid, reason = validate_imei(result.imei1)
        lines.append(f"IMEI1 Valid     : {valid} ({reason})")
        mfr, model = lookup_tac(result.imei1)
        lines.append(f"Manufacturer    : {mfr}")
        lines.append(f"Model Hint      : {model}")
    if result.error:
        lines.append(f"Error           : {result.error}")
    return "\n".join(lines)


def format_write_result(result: IMEIWriteResult) -> str:
    """Return a human-readable multiline string for an IMEIWriteResult."""
    lines = [
        "=== IMEI Write Result ===",
        f"Success         : {result.success}",
        f"IMEI1 Written   : {result.imei1_written or '(none)'}",
        f"IMEI2 Written   : {result.imei2_written or '(none)'}",
        f"Method Used     : {result.method_used or '(none)'}",
        f"Verification    : {'PASS' if result.verification_passed else 'FAIL/SKIPPED'}",
        f"Reboot Required : {result.reboot_required}",
        "Steps:",
    ]
    for step in result.steps_performed:
        lines.append(f"  - {step}")
    if result.error:
        lines.append(f"Error           : {result.error}")
    return "\n".join(lines)


def format_baseband_result(result: BasebandResult) -> str:
    """Return a human-readable multiline string for a BasebandResult."""
    lines = [
        "=== Baseband Check Result ===",
        f"Connected       : {result.connected}",
        f"Baseband Ver    : {result.baseband_version or '(not read)'}",
        f"Modem Ver       : {result.modem_version or '(not read)'}",
        f"RF Ver          : {result.rf_version or '(not read)'}",
        f"Chipset         : {result.chipset or '(not read)'}",
        f"Status          : {result.status or 'unknown'}",
        f"Bands Supported : {', '.join(result.bands_supported) if result.bands_supported else '(none detected)'}",
    ]
    if result.error:
        lines.append(f"Error           : {result.error}")
    return "\n".join(lines)


def format_network_lock_result(result: NetworkLockResult) -> str:
    """Return a human-readable multiline string for a NetworkLockResult."""
    lines = [
        "=== Network Lock Check Result ===",
        f"Connected       : {result.connected}",
        f"Lock Status     : {result.lock_status or '(unknown)'}",
        f"Carrier         : {result.carrier or '(unknown)'}",
        f"SIM Status      : {result.sim_status or '(unknown)'}",
        f"NCK Remaining   : {result.nck_attempts_remaining if result.nck_attempts_remaining >= 0 else '(unknown)'}",
        f"MCK Remaining   : {result.mck_attempts_remaining if result.mck_attempts_remaining >= 0 else '(unknown)'}",
        f"SPCK Remaining  : {result.spck_attempts_remaining if result.spck_attempts_remaining >= 0 else '(unknown)'}",
    ]
    if result.error:
        lines.append(f"Error           : {result.error}")
    return "\n".join(lines)


def bands_for_region(region: str) -> List[str]:
    """Return the expected LTE/NR bands for a given region key.

    Parameters
    ----------
    region : str
        One of the keys in :data:`BAND_DATABASE`, e.g. ``"north_america"``,
        ``"europe"``, ``"india"``.

    Returns
    -------
    list[str]
        Band identifiers such as ``["B1", "B3", "n78", ...]``.
    """
    return BAND_DATABASE.get(region.lower(), [])


def check_band_compatibility(
    device_bands: List[str],
    region: str,
) -> Tuple[List[str], List[str]]:
    """Compare a device's bands against a region's expected bands.

    Parameters
    ----------
    device_bands : list[str]
        Bands reported by the device (from :func:`check_baseband`).
    region : str
        Target region key (see :data:`BAND_DATABASE`).

    Returns
    -------
    tuple[list[str], list[str]]
        ``(supported, missing)`` — bands the device supports in that
        region, and bands the region expects but the device lacks.
    """
    expected = set(bands_for_region(region))
    device_set = set(device_bands)
    supported = sorted(expected & device_set)
    missing = sorted(expected - device_set)
    return supported, missing


# ---------------------------------------------------------------------------
#  Module self-test (only when run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def _cli_progress(pct: float, msg: str) -> None:
        sys.stdout.write(f"\r[{pct:5.1f}%] {msg:<60s}")
        sys.stdout.flush()
        if pct >= 100:
            sys.stdout.write("\n")

    print("=" * 70)
    print("IMEI Repair Tool — Self-Test")
    print("FOR LEGITIMATE REPAIR USE ONLY")
    print("=" * 70)

    # IMEI validation tests
    print("\n--- IMEI Validation Tests ---")
    test_imeis = [
        ("353325082505123", True),   # Valid format example
        ("123456789012345", False),  # Likely fails Luhn
        ("12345", False),           # Too short
        ("abcdefghijklmno", False), # Non-digits
        ("", False),                # Empty
    ]
    for test_imei, expected_valid in test_imeis:
        valid, reason = validate_imei(test_imei)
        status = "PASS" if valid == expected_valid else "FAIL"
        print(f"  [{status}] validate_imei('{test_imei}'): {valid} — {reason}")

    # NV encoding round-trip test
    print("\n--- NV Encoding Round-Trip Test ---")
    sample_imei = "353325082505123"
    valid, _ = validate_imei(sample_imei)
    if valid:
        nv = imei_to_nv_bytes(sample_imei)
        decoded = nv_bytes_to_imei(nv)
        rt_status = "PASS" if decoded == sample_imei else "FAIL"
        print(f"  [{rt_status}] encode/decode: {sample_imei} → {nv.hex()} → {decoded}")
    else:
        print(f"  [SKIP] Sample IMEI {sample_imei} did not pass Luhn — "
              "using compute_imei_check_digit")
        body = sample_imei[:14]
        corrected = compute_imei_check_digit(body)
        nv = imei_to_nv_bytes(corrected)
        decoded = nv_bytes_to_imei(nv)
        rt_status = "PASS" if decoded == corrected else "FAIL"
        print(f"  [{rt_status}] encode/decode: {corrected} → {nv.hex()} → {decoded}")

    # TAC lookup test
    print("\n--- TAC Lookup Test ---")
    for tac, (expected_mfr, expected_model) in list(TAC_DATABASE.items())[:5]:
        test_imei_body = tac + "0" * 6
        full = compute_imei_check_digit(test_imei_body)
        mfr, model = lookup_tac(full)
        status = "PASS" if mfr == expected_mfr else "FAIL"
        print(f"  [{status}] TAC {tac}: {mfr} / {model}")

    # Band compatibility test
    print("\n--- Band Compatibility Test ---")
    device_bands = ["B1", "B3", "B7", "B8", "B20", "n78"]
    supported, missing = check_band_compatibility(device_bands, "europe")
    print(f"  Device bands : {device_bands}")
    print(f"  Europe match : {supported}")
    print(f"  Europe missing: {missing}")

    # Live device check (if connected)
    print("\n--- Live Device Check ---")
    connected, err = _check_adb_connection()
    if connected:
        print("  ADB device detected — running read_imei...")
        imei_res = read_imei(callback=_cli_progress)
        print(format_imei_result(imei_res))

        print("\n  Running check_baseband...")
        bb_res = check_baseband(callback=_cli_progress)
        print(format_baseband_result(bb_res))

        print("\n  Running check_network_lock...")
        lock_res = check_network_lock(callback=_cli_progress)
        print(format_network_lock_result(lock_res))
    else:
        print(f"  No ADB device connected ({err}) — skipping live tests.")

    print("\n" + "=" * 70)
    print("Self-test complete.")
