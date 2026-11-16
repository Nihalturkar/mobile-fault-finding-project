"""
Qualcomm EDL (Emergency Download) Mode Detector.

Communicates with Qualcomm devices in EDL mode (port 9008) using the
Sahara and Firehose protocols to extract deep hardware information.

Sahara protocol handles the initial handshake and device identification.
Firehose protocol (XML-based) handles storage queries, partition reads,
and device configuration extraction.

EDL mode entry methods:
  - Test point short on motherboard + USB connect
  - ADB command: adb reboot edl
  - Volume key combinations (device-specific)

The device appears as "Qualcomm HS-USB QDLoader 9008" (VID:PID 05C6:9008).

Requires: pyserial (pip install pyserial)
"""

import logging
import re
import struct
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUALCOMM_VID = 0x05C6
QUALCOMM_EDL_PID = 0x9008
QUALCOMM_VID_PID_STR = "05C6:9008"

DEFAULT_BAUD = 115200
SAHARA_HELLO_TIMEOUT = 5.0
SAHARA_READ_TIMEOUT = 3.0
FIREHOSE_TIMEOUT = 10.0
FIREHOSE_STORAGE_TIMEOUT = 90.0
SERIAL_WRITE_TIMEOUT = 5.0

# Sahara command IDs
SAHARA_HELLO_ID = 0x01
SAHARA_HELLO_RESP_ID = 0x02
SAHARA_READ_DATA_ID = 0x03
SAHARA_END_TRANSFER_ID = 0x04
SAHARA_DONE_ID = 0x05
SAHARA_DONE_RESP_ID = 0x06
SAHARA_RESET_ID = 0x07
SAHARA_RESET_RESP_ID = 0x08
SAHARA_MEMORY_DEBUG_ID = 0x09
SAHARA_MEMORY_READ_ID = 0x0A
SAHARA_CMD_READY_ID = 0x0B
SAHARA_CMD_SWITCH_ID = 0x0C
SAHARA_CMD_EXEC_ID = 0x0D
SAHARA_CMD_EXEC_RESP_ID = 0x0E
SAHARA_CMD_EXEC_DATA_ID = 0x0F
SAHARA_READ_DATA64_ID = 0x12

# Sahara execute command IDs (for command mode)
SAHARA_EXEC_CMD_NOP = 0x00
SAHARA_EXEC_CMD_SERIAL_NUM = 0x01
SAHARA_EXEC_CMD_MSM_HW_ID = 0x02
SAHARA_EXEC_CMD_OEM_PK_HASH = 0x03
SAHARA_EXEC_CMD_SBL_SW_VER = 0x04
SAHARA_EXEC_CMD_MISC_DEBUG = 0x05
SAHARA_EXEC_CMD_DEVICE_INFO = 0x06
SAHARA_EXEC_CMD_MULTI_IMAGE = 0x07

# Sahara modes
SAHARA_MODE_IMAGE_TX = 0x00
SAHARA_MODE_MEMORY_DEBUG = 0x01
SAHARA_MODE_COMMAND = 0x02
SAHARA_MODE_MEMORY_DUMP = 0x03

SAHARA_MODE_NAMES = {
    SAHARA_MODE_IMAGE_TX: "Image Transfer",
    SAHARA_MODE_MEMORY_DEBUG: "Memory Debug",
    SAHARA_MODE_COMMAND: "Command Mode",
    SAHARA_MODE_MEMORY_DUMP: "Memory Dump",
}

# Sahara status codes
SAHARA_STATUS_SUCCESS = 0x00

# ---------------------------------------------------------------------------
# Known MSM IDs database (at least 30 chipsets)
# ---------------------------------------------------------------------------

QUALCOMM_MSM_IDS: Dict[str, str] = {
    # Verified from real EDL sessions (bkerler/edl logs)
    "0010A0E1": "SM6125 (Snapdragon 665, trinket)",
    "001B80E1": "SM6225 (Snapdragon 680)",
    "001080E1": "SM7125/SDM712 (Snapdragon 712)",
    # Snapdragon 8 series (flagship)
    "00A250E1": "SM8750 (Snapdragon 8 Elite)",
    "009990E1": "SM8650 (Snapdragon 8 Gen 3)",
    "009600E1": "SM8550 (Snapdragon 8 Gen 2)",
    "009470E1": "SM8450 (Snapdragon 8 Gen 1)",
    "009040E1": "SM8350 (Snapdragon 888)",
    "008150E1": "SM8250 (Snapdragon 865)",
    "007B50E1": "SM8150 (Snapdragon 855)",
    "007250E1": "SDM845 (Snapdragon 845)",
    "006220E1": "MSM8998 (Snapdragon 835)",
    "005A10E1": "MSM8996 (Snapdragon 820/821)",
    "004A10E1": "MSM8994 (Snapdragon 810)",
    "003E00E1": "MSM8974 (Snapdragon 800/801)",

    # Snapdragon 7 series (upper mid-range)
    "009230E1": "SM7450 (Snapdragon 7+ Gen 2)",
    "009680E1": "SM7475 (Snapdragon 7 Gen 3)",
    "008C50E1": "SM7350 (Snapdragon 778G)",
    "008F50E1": "SM7325 (Snapdragon 778G+)",
    "008D50E1": "SM7250 (Snapdragon 765G)",
    "007C50E1": "SM7150 (Snapdragon 730/732G)",

    # Snapdragon 6 series (mid-range)
    "009210E1": "SM6450 (Snapdragon 6 Gen 1)",
    "009350E1": "SM6475 (Snapdragon 6 Gen 3)",
    "007F50E1": "SM6350 (Snapdragon 690)",
    "008650E1": "SM6225 (Snapdragon 680)",
    "006B00E1": "SDM660 (Snapdragon 660)",
    "008A00E1": "SDM670 (Snapdragon 670)",
    "006D00E1": "SDM636 (Snapdragon 636)",
    "006C00E1": "SDM630 (Snapdragon 630)",

    # Snapdragon 4 series (budget)
    "009250E1": "SM4450 (Snapdragon 4 Gen 2)",
    "009110E1": "SM4375 (Snapdragon 4 Gen 1)",
    "008B50E1": "SM4350 (Snapdragon 480)",
    "008E50E1": "SM4250 (Snapdragon 460)",
    "009060E1": "SM4325 (Snapdragon 480+)",

    # Snapdragon 2 series (entry-level)
    "009150E1": "QCM2290 (Snapdragon 2 Gen 1)",

    # Legacy / other
    "007060E1": "SDM710 (Snapdragon 710)",
    "005F00E1": "MSM8953 (Snapdragon 625)",
    "005910E1": "MSM8952 (Snapdragon 617)",
    "004F00E1": "MSM8939 (Snapdragon 615)",
    "005100E1": "MSM8937 (Snapdragon 430)",
    "004D00E1": "MSM8916 (Snapdragon 410)",
    "003F00E1": "MSM8226 (Snapdragon 400)",
    "009480E1": "QCS8550 (Snapdragon IoT)",
}

# OEM IDs to manufacturer names
OEM_IDS: Dict[str, str] = {
    "0000": "Unknown / Engineering Sample",
    "0001": "Qualcomm Reference",
    "0003": "Samsung",
    "0005": "LG",
    "0006": "Motorola",
    "0009": "Sony",
    "000A": "HTC",
    "000B": "Lenovo",
    "000D": "Xiaomi (legacy)",
    "0072": "Xiaomi",
    "0073": "vivo",
    "000E": "OnePlus / OPPO / BBK",
    "000F": "Huawei",
    "0010": "ZTE",
    "0011": "vivo / BBK",
    "0012": "Realme / BBK",
    "0013": "Nokia / HMD",
    "0014": "Google",
    "0015": "ASUS",
    "0016": "Nothing",
    "0017": "Fairphone",
}

# UFS manufacturer IDs
UFS_MANUFACTURERS: Dict[int, str] = {
    0xCE: "Samsung",
    0xAD: "SK Hynix",
    0x2C: "Micron",
    0x45: "SanDisk / Western Digital",
    0x98: "Toshiba / Kioxia",
    0x13: "YMTC (Yangtze Memory)",
    0x01: "AMD / Spansion",
    0xC2: "Macronix",
}

# eMMC manufacturer IDs (JEDEC)
EMMC_MANUFACTURERS: Dict[int, str] = {
    0x11: "Toshiba / Kioxia",
    0x13: "Micron",
    0x15: "Samsung",
    0x45: "SanDisk / Western Digital",
    0x70: "Kingston",
    0x90: "SK Hynix",
    0xFE: "Micron (alt)",
}

# DDR manufacturer IDs (JEDEC JEP106)
DDR_MANUFACTURERS: Dict[int, str] = {
    0x01: "Samsung",
    0x03: "Elpida / Micron",
    0x05: "Nanya",
    0x06: "SK Hynix",
    0x08: "Winbond",
    0x09: "ESMT",
    0xC2: "CXMT (ChangXin Memory)",
    0xFF: "Micron",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EDLDetectionResult:
    """Complete result from EDL mode detection."""

    # Connection state
    connected: bool = False
    port: str = ""
    mode: str = ""  # sahara, firehose, streaming
    usb_product: str = ""        # iProduct, e.g. QUSB_BULK_CID:0411_SN:9DAC9599
    command_mode_supported: bool = True
    firehose_build: str = ""     # loader "Binary build date"
    firehose_loader: str = ""    # path of the programmer that was uploaded
    firehose_auth_required: bool = False

    # Sahara-level identifiers
    serial_number: str = ""
    msm_id: str = ""
    msm_id_raw: str = ""
    chipset_name: str = ""
    oem_id: str = ""
    oem_name: str = ""
    model_id: str = ""
    pk_hash: str = ""
    sbl_sw_version: str = ""

    # Sahara protocol info
    sahara_version: str = ""
    sahara_min_version: str = ""
    sahara_max_packet_size: int = 0
    sahara_mode: str = ""

    # Storage info (from Firehose)
    storage_type: str = ""  # UFS, eMMC
    storage_manufacturer: str = ""
    storage_manufacturer_id: str = ""
    storage_capacity_bytes: int = 0
    storage_capacity_human: str = ""
    storage_health_eol: str = ""
    storage_life_est_a: str = ""
    storage_life_est_b: str = ""
    num_physical_partitions: int = 0
    boot_lun: int = -1

    # Partitions (from Firehose GPT read)
    partitions: List[Dict[str, str]] = field(default_factory=list)

    # Secure boot state
    secure_boot_enabled: bool = False
    debug_disabled: bool = False

    # Detection metadata
    log: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    raw_sahara_hello: bytes = field(default_factory=bytes, repr=False)
    detection_duration_s: float = 0.0


# ---------------------------------------------------------------------------
# Sahara protocol implementation
# ---------------------------------------------------------------------------


class SaharaProtocol:
    """Low-level Sahara protocol handler over a serial connection."""

    def __init__(self, port: str, timeout: float = SAHARA_READ_TIMEOUT):
        self._port_name = port
        self._timeout = timeout
        self._serial = None

    # -- connection management --

    def open(self) -> None:
        """
        Open the connection to the device.

        A port name opens a COM port via pyserial. Passing ``None`` (or
        no COM port being present) falls back to a raw USB bulk link,
        which is how the device appears when bound to WinUSB/libwdi
        rather than the Qualcomm QDLoader VCP driver.
        """
        if self._port_name:
            import serial

            logger.info("Opening serial port %s at %d baud",
                        self._port_name, DEFAULT_BAUD)
            self._serial = serial.Serial(
                port=self._port_name,
                baudrate=DEFAULT_BAUD,
                timeout=self._timeout,
                write_timeout=SERIAL_WRITE_TIMEOUT,
            )
        else:
            dev = find_edl_usb()
            if dev is None:
                raise ConnectionError(
                    "No EDL device found: no 9008 COM port, and no "
                    "WinUSB-bound 05C6:9008 device (is pyusb installed?)")
            logger.info("Opening EDL device over raw USB bulk (WinUSB)")
            self._serial = _WinUsbSerial(dev, timeout=self._timeout)
        # Small delay for the device to settle after port open
        time.sleep(0.3)

    def close(self) -> None:
        """Close the serial port if open."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    # -- low-level I/O --

    def _read_raw(self, size: int, timeout: Optional[float] = None) -> bytes:
        """Read exactly *size* bytes, or as many as arrive before timeout."""
        if not self.is_open:
            raise ConnectionError("Serial port is not open")

        old_timeout = self._serial.timeout
        if timeout is not None:
            self._serial.timeout = timeout
        try:
            data = self._serial.read(size)
        finally:
            self._serial.timeout = old_timeout
        return data

    def _read_until_idle(self, timeout: float = 2.0) -> bytes:
        """Read all available bytes until the port is idle for *timeout*."""
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            waiting = self._serial.in_waiting
            if waiting > 0:
                buf.extend(self._serial.read(waiting))
                deadline = time.monotonic() + 0.3  # extend on activity
            else:
                time.sleep(0.05)
        return bytes(buf)

    def _write(self, data: bytes) -> None:
        if not self.is_open:
            raise ConnectionError("Serial port is not open")
        self._serial.write(data)
        self._serial.flush()

    # -- packet helpers --

    @staticmethod
    def _pack_header(cmd_id: int, length: int) -> bytes:
        """Pack a Sahara packet header (command + length, both LE uint32)."""
        return struct.pack("<II", cmd_id, length)

    @staticmethod
    def _unpack_header(data: bytes) -> Tuple[int, int]:
        """Unpack command ID and length from first 8 bytes."""
        if len(data) < 8:
            raise ValueError(f"Packet too short for header: {len(data)} bytes")
        return struct.unpack("<II", data[:8])

    # -- Sahara Hello / Hello Response --

    def wait_for_hello(self) -> Dict[str, object]:
        """
        Wait for the Sahara HELLO packet from the device.

        Returns a dict with version, compatible_version, max_packet_size,
        mode, and the raw hello bytes.
        """
        logger.info("Waiting for Sahara HELLO packet (timeout %.1fs)...", SAHARA_HELLO_TIMEOUT)
        data = self._read_raw(48, timeout=SAHARA_HELLO_TIMEOUT)

        if len(data) < 48:
            # Sometimes the device sends a shorter probe; try to read more
            extra = self._read_until_idle(timeout=2.0)
            data += extra

        if data.lstrip().startswith(b"<"):
            raise FirehoseAlreadyRunning(
                "Firehose loader already running on device (previous session); using it directly")

        if len(data) == 0:
            self._write(b'<?xml version="1.0" ?><data><nop value="ping" /></data>')
            probe = self._read_raw(64, timeout=1.5)
            if probe.lstrip().startswith(b"<"):
                self._read_until_idle(0.5)
                raise FirehoseAlreadyRunning(
                    "Firehose loader already running on device (previous session); using it directly")
            # PBL sends HELLO once at enumeration; if another process (or an
            # earlier open) consumed it, replying anyway still yields CMD_READY.
            logger.warning("No Sahara HELLO received; assuming it was already sent "
                           "(v2) and continuing with HELLO_RESPONSE")
            return {"version": 2, "compatible_version": 1, "max_packet_size": 1024,
                    "mode": SAHARA_MODE_IMAGE_TX, "mode_name": "Unknown (HELLO lost)",
                    "raw": b"", "reserved": b"", "hello_lost": True}

        if len(data) >= 16 and struct.unpack("<I", data[:4])[0] == SAHARA_END_TRANSFER_ID:
            image_id, status = struct.unpack("<II", data[8:16])
            raise ConnectionError(
                f"Device is in Sahara error state (END_IMAGE_TRANSFER image_id={image_id} "
                f"status={status}) from a previous session; re-enter EDL (replug) and retry")

        if len(data) < 48:
            raise TimeoutError(
                f"Did not receive full Sahara HELLO (got {len(data)} bytes, need 48)"
            )

        cmd_id, length = self._unpack_header(data)
        if cmd_id != SAHARA_HELLO_ID:
            raise ValueError(
                f"Expected SAHARA_HELLO (0x01), got command 0x{cmd_id:02X}"
            )

        # Parse the hello fields
        (
            _cmd, _length,
            version, compat_version,
            max_packet_size, mode,
        ) = struct.unpack("<6I", data[:24])

        # Bytes 24..47 are reserved / may contain additional fields
        reserved = data[24:48]

        info = {
            "version": version,
            "compatible_version": compat_version,
            "max_packet_size": max_packet_size,
            "mode": mode,
            "mode_name": SAHARA_MODE_NAMES.get(mode, f"Unknown(0x{mode:02X})"),
            "raw": data,
            "reserved": reserved,
        }
        logger.info(
            "Sahara HELLO: version=%d, compat=%d, max_pkt=%d, mode=%s",
            version, compat_version, max_packet_size, info["mode_name"],
        )
        return info

    def send_hello_response(
        self, version: int = 2, compat: int = 1,
        desired_mode: int = SAHARA_MODE_COMMAND,
    ) -> None:
        """Send Sahara HELLO_RESPONSE to the device."""
        # Hello Response: cmd, length=0x30, version, compat, status, mode,
        # reserved[6] = 48 bytes. Devices drop a 24-byte response silently.
        pkt = struct.pack(
            "<12I",
            SAHARA_HELLO_RESP_ID, 48,
            version, compat,
            SAHARA_STATUS_SUCCESS, desired_mode,
            0, 0, 0, 0, 0, 0,
        )
        logger.info("Sending Sahara HELLO_RESPONSE (requesting mode %d)", desired_mode)
        self._write(pkt)

    # -- Command mode operations --

    def wait_command_ready(self) -> None:
        """Read the CMD_READY the device sends after HELLO_RESPONSE(mode=command)."""
        resp = self._read_raw(8, timeout=3.0)
        if len(resp) < 8:
            raise TimeoutError("No CMD_READY after HELLO_RESPONSE")
        cmd_id, length = self._unpack_header(resp)
        if cmd_id == SAHARA_END_TRANSFER_ID:
            rest = self._read_raw(max(length - 8, 0), timeout=2.0)
            image_id, status = struct.unpack("<II", (rest + bytes(8))[:8])
            raise PermissionError(
                f"PBL refused command mode (END_IMAGE_TRANSFER image_id={image_id} "
                f"status={status}); Sahara command mode unsupported on this device")
        if cmd_id != SAHARA_CMD_READY_ID:
            raise ValueError(f"Expected CMD_READY (0x0B), got 0x{cmd_id:02X}")
        logger.info("Device is in command mode (CMD_READY received)")

    def switch_to_image_transfer(self) -> None:
        """Leave command mode so a Firehose loader can be sent later (device re-HELLOs)."""
        pkt = struct.pack("<3I", SAHARA_CMD_SWITCH_ID, 12, SAHARA_MODE_IMAGE_TX)
        self._write(pkt)
        logger.info("Sent CMD_SWITCH_MODE -> image transfer")

    def execute_command(self, exec_cmd_id: int) -> bytes:
        """
        Send a SAHARA_CMD_EXEC and read the response data.

        Flow:
            1. Send CMD_EXEC with the command id
            2. Receive CMD_EXEC_RESP with data_offset and data_length
            3. Send CMD_EXEC_DATA to request the data
            4. Receive the raw data bytes
        """
        # CMD_EXEC: cmd(4) + length(4) + exec_cmd_id(4) = 12 bytes
        pkt = struct.pack("<3I", SAHARA_CMD_EXEC_ID, 12, exec_cmd_id)
        logger.debug("Sending CMD_EXEC for command 0x%02X", exec_cmd_id)
        self._write(pkt)

        # Read CMD_EXEC_RESP: cmd(4) + length(4) + exec_cmd_id(4)
        #                     + data_length(4) = 16 bytes
        resp = self._read_raw(16, timeout=3.0)
        if len(resp) < 16:
            raise TimeoutError(
                f"CMD_EXEC_RESP too short: {len(resp)} bytes (expected 16)"
            )

        resp_cmd, resp_len, resp_exec_id, data_length = struct.unpack(
            "<4I", resp[:16]
        )

        if resp_cmd != SAHARA_CMD_EXEC_RESP_ID:
            raise ValueError(
                f"Expected CMD_EXEC_RESP (0x0E), got 0x{resp_cmd:02X}"
            )

        if data_length == 0:
            logger.debug("CMD_EXEC response for 0x%02X has zero data length", exec_cmd_id)
            return b""

        # Send CMD_EXEC_DATA: cmd(4) + length(4) + exec_cmd_id(4) = 12 bytes
        data_pkt = struct.pack("<3I", SAHARA_CMD_EXEC_DATA_ID, 12, exec_cmd_id)
        self._write(data_pkt)

        # Read the actual data payload
        payload = self._read_raw(data_length, timeout=3.0)
        logger.debug(
            "CMD_EXEC 0x%02X returned %d bytes (expected %d)",
            exec_cmd_id, len(payload), data_length,
        )
        return payload

    def upload_image(self, path: str, progress=None) -> None:
        """
        Sahara image transfer: serve the programmer (ELF/MBN) to the PBL.

        Call right after send_hello_response(desired_mode=IMAGE_TX). The PBL
        drives the transfer with READ_DATA / READ_DATA64 requests; we answer
        each with the requested slice, then expect END_IMAGE_TRANSFER(status 0)
        and DONE_RESP. Afterwards the programmer is running (Firehose).
        """
        with open(path, "rb") as fh:
            image = fh.read()
        sent = 0
        while True:
            hdr = self._read_raw(8, timeout=SAHARA_READ_TIMEOUT)
            if len(hdr) < 8:
                raise TimeoutError("PBL stopped requesting image data")
            cmd, length = self._unpack_header(hdr)
            body = self._read_raw(length - 8, timeout=SAHARA_READ_TIMEOUT)
            if cmd == SAHARA_READ_DATA_ID:
                image_id, offset, size = struct.unpack("<3I", body[:12])
            elif cmd == SAHARA_READ_DATA64_ID:
                image_id, offset, size = struct.unpack("<3Q", body[:24])
            elif cmd == SAHARA_END_TRANSFER_ID:
                image_id, status = struct.unpack("<2I", body[:8])
                if status != SAHARA_STATUS_SUCCESS:
                    why = {1: "stale Sahara session (invalid command in this state) - unplug, "
                              "re-enter EDL and run again",
                           37: "signature mismatch - loader not signed for this device's OEM key",
                           6: "unexpected image id",
                           19: "invalid image header", 20: "invalid ELF header"}.get(
                        status, "see Sahara status table")
                    raise PermissionError(
                        f"PBL rejected programmer (image_id={image_id} status={status}: {why})")
                break
            else:
                raise ValueError(f"Unexpected Sahara cmd 0x{cmd:02X} during image transfer")
            chunk = image[offset:offset + size]
            if len(chunk) < size:  # PBL may over-request past EOF; pad
                chunk += bytes(size - len(chunk))
            self._write(chunk)
            sent += size
            if progress:
                progress(min(sent / max(len(image), 1), 1.0))
        self._write(self._pack_header(SAHARA_DONE_ID, 8))
        resp = self._read_raw(12, timeout=SAHARA_READ_TIMEOUT)
        if len(resp) < 12 or struct.unpack("<I", resp[:4])[0] != SAHARA_DONE_RESP_ID:
            raise ValueError("No DONE_RESP after image transfer")
        logger.info("Programmer accepted (%d bytes); Firehose should be live", len(image))

    def send_done(self) -> None:
        """Send SAHARA_DONE to gracefully end the session."""
        pkt = self._pack_header(SAHARA_DONE_ID, 8)
        self._write(pkt)
        logger.info("Sent SAHARA_DONE")

    def send_reset(self) -> None:
        """Send SAHARA_RESET to reset the device-side state."""
        pkt = self._pack_header(SAHARA_RESET_ID, 8)
        self._write(pkt)
        logger.info("Sent SAHARA_RESET")


# ---------------------------------------------------------------------------
# Firehose protocol implementation (XML over Sahara transport)
# ---------------------------------------------------------------------------


class FirehoseProtocol:
    """
    Firehose XML command protocol for Qualcomm EDL.

    Firehose commands are XML strings sent as raw bytes over the serial port
    once Sahara has handed off to Firehose mode.  Responses are XML wrapped
    in ``<data>`` or ``<response>`` elements.
    """

    def __init__(self, serial_conn):
        """
        Parameters
        ----------
        serial_conn : serial.Serial
            An already-open serial connection (typically from SaharaProtocol).
        """
        self._serial = serial_conn

    # -- I/O helpers --

    def _send_xml(self, xml_str: str) -> None:
        """Send a Firehose XML command."""
        payload = xml_str.encode("utf-8")
        logger.debug("Firehose TX (%d bytes): %s", len(payload), xml_str.strip())
        self._serial.write(payload)
        self._serial.flush()

    def _recv_xml(self, timeout: float = FIREHOSE_TIMEOUT) -> str:
        """
        Receive Firehose XML response.

        Reads until a closing ``</data>`` or ``</response>`` tag is found,
        or until timeout.
        """
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            waiting = self._serial.in_waiting
            if waiting > 0:
                buf.extend(self._serial.read(waiting))
                text = buf.decode("utf-8", errors="replace")
                if "<response" in text and ("/>" in text.split("<response", 1)[1]):
                    break
            else:
                time.sleep(0.05)

        result = buf.decode("utf-8", errors="replace")
        logger.debug("Firehose RX (%d bytes): %s", len(buf), result[:500])
        return result

    def _send_and_recv(self, xml_str: str) -> str:
        self._send_xml(xml_str)
        return self._recv_xml()

    @staticmethod
    def _parse_response_value(xml_text: str, attr: str) -> Optional[str]:
        """Extract an attribute value from a Firehose ``<response>`` element."""
        try:
            root = ET.fromstring(xml_text)
            for elem in root.iter("response"):
                val = elem.get(attr)
                if val is not None:
                    return val
            # Might be bare <response> not wrapped in <data>
            if root.tag == "response":
                return root.get(attr)
        except ET.ParseError:
            pass
        return None

    # -- high-level commands --

    def configure(self, storage_type: str = "ufs") -> str:
        """Send <configure>; renegotiate MaxPayloadSizeToTargetInBytes if the loader NAKs."""
        name = {"ufs": "UFS", "emmc": "eMMC"}.get(storage_type.lower(), storage_type)

        def _cfg(payload: int) -> str:
            return self._send_and_recv(
                '<?xml version="1.0" encoding="UTF-8" ?><data>'
                f'<configure MemoryName="{name}" Verbose="0" AlwaysValidate="0" '
                f'MaxDigestTableSizeInBytes="2048" MaxPayloadSizeToTargetInBytes="{payload}" '
                'ZLPAwareHost="1" SkipStorageInit="0" /></data>')

        resp = _cfg(1048576)
        m = re.search(r'MaxPayloadSizeToTargetInBytes="(\d+)"', resp)
        if 'value="NAK"' in resp and m:
            resp = _cfg(int(m.group(1)))
        return resp

    def get_storage_info(self) -> str:
        """
        Send ``<getstorageinfo>`` to retrieve storage details.

        Returns the raw XML response containing manufacturer ID, capacity,
        health indicators, LUN count, etc.
        """
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>\n'
            "<data>\n"
            '  <getstorageinfo physical_partition_number="0" />\n'
            "</data>"
        )
        self._send_xml(xml)
        return self._recv_xml(timeout=FIREHOSE_STORAGE_TIMEOUT)

    def read_gpt(self, lun: int = 0) -> str:
        """
        Read the GPT (GUID Partition Table) from the specified LUN.

        Sends a ``<read>`` for sector 0 with enough sectors to cover the
        primary GPT header + entries (typically 34 sectors).
        """
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>\n'
            "<data>\n"
            f'  <read SECTOR_SIZE_IN_BYTES="4096" '
            f'physical_partition_number="{lun}" '
            f'start_sector="0" num_partition_sectors="34" />\n'
            "</data>"
        )
        return self._send_and_recv(xml)

    def print_gpt(self) -> str:
        """
        Send the ``<printgpt>`` convenience command (supported by some
        Firehose programmers) to get a human-readable partition listing.
        """
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>\n'
            "<data>\n"
            '  <printgpt physical_partition_number="0" />\n'
            "</data>"
        )
        return self._send_and_recv(xml)

    def get_device_info(self) -> str:
        """Send a ``<getdeviceinfo>`` command (non-standard, some loaders)."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>\n'
            "<data>\n"
            "  <getdeviceinfo />\n"
            "</data>"
        )
        return self._send_and_recv(xml)

    @staticmethod
    def log_lines(xml_text: str) -> List[str]:
        """Extract <log value="..."/> messages from a Firehose response blob."""
        return [v.strip() for v in re.findall(r'<log value="([^"]*)"', xml_text)]

    def read_banner(self, timeout: float = 1.5) -> List[str]:
        """Collect the loader's startup log (build date, chip serial, functions)."""
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            waiting = self._serial.in_waiting
            if waiting:
                buf.extend(self._serial.read(waiting))
                deadline = time.monotonic() + 0.3
            else:
                time.sleep(0.05)
        return self.log_lines(buf.decode("utf-8", errors="replace"))

    def nop(self) -> str:
        """Send a NOP to test responsiveness."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8" ?>\n'
            "<data>\n"
            '  <nop value="ping" />\n'
            "</data>"
        )
        return self._send_and_recv(xml)


class _WinUsbSerial:
    """
    Minimal serial-like shim over a raw USB bulk endpoint (pyusb).

    Exists because the EDL 9008 device is often bound to WinUSB/libwdi
    instead of the Qualcomm QDLoader VCP driver, in which case it has no
    COM port at all and pyserial cannot reach it. Sahara/Firehose are
    framed protocols that ignore baud rate, so raw bulk transfers carry
    them unchanged.

    Implements only what SaharaProtocol/FirehoseProtocol touch:
    read, write, flush, close, in_waiting, is_open, timeout.
    """

    def __init__(self, dev, timeout: float = SAHARA_READ_TIMEOUT):
        import usb.util

        self._dev = dev
        self.timeout = timeout
        self._buf = bytearray()
        self._closed = False

        try:
            if dev.is_kernel_driver_active(0):
                dev.detach_kernel_driver(0)
        except Exception:
            pass  # not supported on Windows, and not needed there

        cfg = dev.get_active_configuration()
        intf = cfg[(0, 0)]
        self._ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(
                e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        self._ep_in = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(
                e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        if self._ep_out is None or self._ep_in is None:
            raise ConnectionError(
                "EDL device exposes no bulk IN/OUT endpoint pair")

    # -- pyserial-compatible surface --

    @property
    def is_open(self) -> bool:
        return not self._closed

    @property
    def in_waiting(self) -> int:
        self._pump(timeout_ms=1)
        return len(self._buf)

    def write(self, data: bytes) -> int:
        return self._ep_out.write(bytes(data), int(SERIAL_WRITE_TIMEOUT * 1000))

    def flush(self) -> None:
        pass  # bulk writes are not buffered on our side

    def read(self, size: int = 1) -> bytes:
        deadline = time.time() + (self.timeout or 0)
        while len(self._buf) < size:
            if not self._pump() and time.time() >= deadline:
                break  # short read, same as pyserial on timeout
        out = bytes(self._buf[:size])
        del self._buf[:size]
        return out

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            import usb.util
            usb.util.dispose_resources(self._dev)
        except Exception:
            pass

    # -- internals --

    def _pump(self, timeout_ms: int = 100) -> bool:
        """Pull one bulk packet into the buffer. True if bytes arrived."""
        try:
            chunk = self._ep_in.read(self._ep_in.wMaxPacketSize, timeout_ms)
        except Exception:
            return False  # timeout / no data pending
        if not chunk:
            return False
        self._buf.extend(bytes(chunk))
        return True


def find_edl_usb():
    """
    Find a WinUSB/libusb-bound EDL device (VID:PID 05C6:9008).

    Returns a pyusb device, or ``None`` if pyusb is missing or no such
    device is attached. Used as a fallback when no COM port is present.
    """
    try:
        import usb.core
    except ImportError:
        logger.info("pyusb is not installed; WinUSB EDL fallback unavailable")
        return None

    backend = None
    try:  # bundled libusb-1.0 DLL; without it pyusb has "No backend available" on Windows
        import libusb_package
        backend = libusb_package.get_libusb1_backend()
    except Exception:
        pass

    try:
        dev = usb.core.find(idVendor=QUALCOMM_VID, idProduct=QUALCOMM_EDL_PID,
                            backend=backend)
    except Exception as exc:
        logger.warning("pyusb enumeration failed: %s", exc)
        return None

    if dev is None:
        logger.info("No WinUSB-bound EDL (05C6:9008) device found")
    else:
        logger.info("Found WinUSB EDL device: bus=%s addr=%s",
                    dev.bus, dev.address)
    return dev


# ---------------------------------------------------------------------------
# Port detection
# ---------------------------------------------------------------------------


def find_edl_port() -> Optional[str]:
    """
    Scan serial ports for a Qualcomm EDL device (VID:PID 05C6:9008).

    Returns the port device path (e.g., ``COM3`` or ``/dev/ttyUSB0``),
    or ``None`` if no EDL device is found.
    """
    try:
        import serial.tools.list_ports
    except ImportError:
        logger.error("pyserial is not installed. Install with: pip install pyserial")
        return None

    for port_info in serial.tools.list_ports.comports():
        hwid_upper = (port_info.hwid or "").upper()
        desc_lower = (port_info.description or "").lower()

        vid_pid_match = QUALCOMM_VID_PID_STR in hwid_upper
        desc_match = "9008" in desc_lower or "qdloader" in desc_lower

        if vid_pid_match or desc_match:
            logger.info(
                "Found EDL device: %s [%s] hwid=%s",
                port_info.device, port_info.description, port_info.hwid,
            )
            return port_info.device

    logger.info("No Qualcomm EDL (9008) port found among %d serial ports",
                len(list(serial.tools.list_ports.comports())))
    return None


# ---------------------------------------------------------------------------
# ID resolution helpers
# ---------------------------------------------------------------------------


def resolve_chipset_name(msm_id_hex: str) -> str:
    """
    Look up a human-readable chipset name from an MSM ID hex string.

    The input should be uppercase hex without ``0x`` prefix, e.g. ``"009990E1"``.
    """
    name = QUALCOMM_MSM_IDS.get(msm_id_hex.upper())
    if name:
        return name
    return f"Unknown Qualcomm MSM (0x{msm_id_hex})"


def resolve_oem_name(oem_id_hex: str) -> str:
    """Look up manufacturer name from a 4-character hex OEM ID string."""
    name = OEM_IDS.get(oem_id_hex.upper())
    if name:
        return name
    return f"Unknown OEM (0x{oem_id_hex})"


def resolve_storage_manufacturer(mfr_id: int, storage_type: str = "ufs") -> str:
    """Resolve a storage manufacturer ID to a name."""
    if storage_type.lower() == "ufs":
        return UFS_MANUFACTURERS.get(mfr_id, f"Unknown UFS vendor (0x{mfr_id:02X})")
    return EMMC_MANUFACTURERS.get(mfr_id, f"Unknown eMMC vendor (0x{mfr_id:02X})")


def _bytes_to_human(size_bytes: int) -> str:
    """Convert byte count to human-readable string."""
    if size_bytes <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


# ---------------------------------------------------------------------------
# High-level detection orchestrator
# ---------------------------------------------------------------------------


def _extract_sahara_identifiers(
    sahara: SaharaProtocol, result: EDLDetectionResult
) -> None:
    """
    Use Sahara command mode to extract MSM ID, serial number, OEM PK hash, etc.

    Populates fields directly on *result*.
    """
    # Serial number
    try:
        sn_data = sahara.execute_command(SAHARA_EXEC_CMD_SERIAL_NUM)
        if len(sn_data) >= 4:
            serial_num = struct.unpack("<I", sn_data[:4])[0]
            result.serial_number = f"0x{serial_num:08X}"
            result.log.append(f"  Serial number: {result.serial_number}")
        else:
            result.log.append("  Serial number: <not available>")
    except Exception as exc:
        result.log.append(f"  Serial number read failed: {exc}")
        result.errors.append(f"Serial number: {exc}")

    # MSM Hardware ID (contains MSM ID + OEM ID + Model ID)
    try:
        hw_data = sahara.execute_command(SAHARA_EXEC_CMD_MSM_HW_ID)
        if len(hw_data) >= 8:
            # First 4 bytes: MSM ID, next 2 bytes: OEM ID, next 2 bytes: Model ID
            msm_raw = struct.unpack("<I", hw_data[:4])[0]
            result.msm_id_raw = f"0x{msm_raw:08X}"
            msm_hex = f"{msm_raw:08X}"
            result.msm_id = msm_hex
            result.chipset_name = resolve_chipset_name(msm_hex)
            result.log.append(f"  MSM ID: 0x{msm_hex} -> {result.chipset_name}")

            if len(hw_data) >= 8:
                oem_model = struct.unpack("<I", hw_data[4:8])[0]
                oem_hex = f"{(oem_model >> 16) & 0xFFFF:04X}"
                model_hex = f"{oem_model & 0xFFFF:04X}"
                result.oem_id = oem_hex
                result.model_id = model_hex
                result.oem_name = resolve_oem_name(oem_hex)
                result.log.append(f"  OEM ID: 0x{oem_hex} -> {result.oem_name}")
                result.log.append(f"  Model ID: 0x{model_hex}")
        else:
            result.log.append("  MSM HW ID: <not available>")
    except Exception as exc:
        result.log.append(f"  MSM HW ID read failed: {exc}")
        result.errors.append(f"MSM HW ID: {exc}")

    # OEM PK Hash
    try:
        pk_data = sahara.execute_command(SAHARA_EXEC_CMD_OEM_PK_HASH)
        if len(pk_data) > 0:
            result.pk_hash = pk_data.hex().upper()
            # Truncate for display
            display_hash = result.pk_hash[:16] + "..." if len(result.pk_hash) > 16 else result.pk_hash
            result.log.append(f"  PK Hash: {display_hash} ({len(pk_data)} bytes)")

            # Determine secure boot state from PK hash
            if all(b == 0 for b in pk_data):
                result.secure_boot_enabled = False
                result.log.append("  Secure boot: DISABLED (PK hash is all zeros)")
            else:
                result.secure_boot_enabled = True
                result.log.append("  Secure boot: ENABLED (non-zero PK hash)")
        else:
            result.log.append("  PK Hash: <not available>")
    except Exception as exc:
        result.log.append(f"  PK Hash read failed: {exc}")
        result.errors.append(f"PK Hash: {exc}")

    # SBL SW Version
    try:
        sbl_data = sahara.execute_command(SAHARA_EXEC_CMD_SBL_SW_VER)
        if len(sbl_data) >= 4:
            sbl_ver = struct.unpack("<I", sbl_data[:4])[0]
            result.sbl_sw_version = f"0x{sbl_ver:08X}"
            result.log.append(f"  SBL SW version: {result.sbl_sw_version}")
    except Exception as exc:
        result.log.append(f"  SBL version read failed: {exc}")


def _extract_firehose_info(
    firehose: FirehoseProtocol, result: EDLDetectionResult
) -> None:
    """
    Use Firehose protocol to extract storage info, partitions, and device info.
    """
    banner = firehose.read_banner()
    if not banner:  # resident loader: banner already consumed, nop replays it
        try:
            banner = firehose.log_lines(firehose.nop())
        except Exception:
            banner = []
    for line in banner:
        result.log.append(f"  loader: {line}")
        m = re.search(r"Chip serial num: \d+ \(0x([0-9a-fA-F]+)\)", line)
        if m:
            result.serial_number = "0x" + m.group(1).upper()
        m = re.search(r"Binary build date: (.*)", line)
        if m:
            result.firehose_build = m.group(1).strip()
    if banner:
        result.mode = "firehose"

    # Loaders ACK <configure> for any MemoryName; only <getstorageinfo> proves the chip.
    name = (result.firehose_loader or "").lower()
    order = ("ufs",) if "ufs" in name else ("emmc",) if "emmc" in name else ("emmc", "ufs")
    storage_resp = ""
    for storage_type in order:
        result.log.append(f"  Attempting Firehose configure for {storage_type.upper()}...")
        try:
            cfg_resp = firehose.configure(storage_type=storage_type)
        except Exception as exc:
            result.log.append(f"  Configure {storage_type.upper()} failed: {exc}")
            continue
        for line in firehose.log_lines(cfg_resp):
            result.log.append(f"  loader: {line}")
        if "before authentication" in cfg_resp:
            result.firehose_auth_required = True
            result.log.append("  Loader demands OEM EDL authentication (Xiaomi 'sig') before any storage command.")
            result.errors.append("Firehose: OEM EDL authentication required (Mi authorized account or no-auth loader)")
            return
        if 'value="ACK"' not in cfg_resp:
            result.log.append(f"  {storage_type.upper()} configure NAK, trying next...")
            continue
        try:
            storage_resp = firehose.get_storage_info()
        except Exception as exc:
            storage_resp = ""
            result.log.append(f"  getstorageinfo transport error: {exc}")
        for line in firehose.log_lines(storage_resp):
            result.log.append(f"  loader: {line}")
        if "<response" not in storage_resp:
            if not result.errors:
                result.storage_type = storage_type.upper()
                result.storage_health_eol = "NO RESPONSE"
            result.log.append(f"  LOADER STALLED inside {storage_type.upper()} init for {FIREHOSE_STORAGE_TIMEOUT:.0f}s: "
                              "flash not answering (dead/unpowered chip or CMD/CLK fault).")
            result.errors.append(f"Storage: {storage_type.upper()} not responding (loader stalled in init)")
            return
        if 'value="ACK"' in storage_resp:
            result.storage_type = storage_type.upper()
            result.log.append(f"  Storage type: {result.storage_type}")
            break
        if "Failed to open" in storage_resp:
            result.log.append(f"  {storage_type.upper()} present in loader but chip did not initialise "
                              "(controller open failed): flash not responding.")
            result.errors.append(f"Storage: {storage_type.upper()} chip not responding (controller open failed)")
        result.log.append(f"  {storage_type.upper()} init failed, trying next...")
    else:
        result.log.append("  Could not initialise storage (neither UFS nor eMMC)")
        result.errors.append("Firehose: storage initialisation failed")
        return

    _parse_storage_info_xml(storage_resp, result)

    # Partition table
    try:
        gpt_resp = firehose.print_gpt()
        result.log.append(f"  GPT response received ({len(gpt_resp)} chars)")
        _parse_gpt_response(gpt_resp, result)
    except Exception as exc:
        result.log.append(f"  GPT read failed: {exc}")
        result.errors.append(f"GPT: {exc}")


def _parse_storage_info_xml(xml_text: str, result: EDLDetectionResult) -> None:
    """Parse the XML response from ``<getstorageinfo>``."""
    try:
        # Try to find the <log> elements which contain key=value info
        cleaned = re.sub(r"<\?xml[^>]*\?>", "", xml_text)
        root = ET.fromstring(f"<root>{cleaned}</root>")

        for log_elem in root.iter("log"):
            value = log_elem.get("value", "")

            if "manufacturer" in value.lower() and "id" in value.lower():
                # e.g. "storage_info: Manufacturer ID = 0xCE"
                parts = value.split("=")
                if len(parts) >= 2:
                    mfr_str = parts[-1].strip()
                    try:
                        mfr_id = int(mfr_str, 0)
                        result.storage_manufacturer_id = f"0x{mfr_id:02X}"
                        result.storage_manufacturer = resolve_storage_manufacturer(
                            mfr_id, result.storage_type.lower()
                        )
                        result.log.append(
                            f"    Storage manufacturer: {result.storage_manufacturer} "
                            f"({result.storage_manufacturer_id})"
                        )
                    except ValueError:
                        pass

            elif "total_size" in value.lower() or "capacity" in value.lower():
                parts = value.split("=")
                if len(parts) >= 2:
                    try:
                        size_val = int(parts[-1].strip(), 0)
                        result.storage_capacity_bytes = size_val
                        result.storage_capacity_human = _bytes_to_human(size_val)
                        result.log.append(
                            f"    Storage capacity: {result.storage_capacity_human}"
                        )
                    except ValueError:
                        pass

            elif "num_physical" in value.lower():
                parts = value.split("=")
                if len(parts) >= 2:
                    try:
                        result.num_physical_partitions = int(parts[-1].strip(), 0)
                        result.log.append(
                            f"    Physical partitions (LUNs): {result.num_physical_partitions}"
                        )
                    except ValueError:
                        pass

            elif "eol" in value.lower() or "life_est" in value.lower():
                result.log.append(f"    Health: {value.strip()}")

        # Also check <response> elements
        for resp_elem in root.iter("response"):
            for attr_name in resp_elem.attrib:
                attr_val = resp_elem.get(attr_name, "")
                if "manufacturer" in attr_name.lower():
                    try:
                        mfr_id = int(attr_val, 0)
                        if not result.storage_manufacturer:
                            result.storage_manufacturer_id = f"0x{mfr_id:02X}"
                            result.storage_manufacturer = resolve_storage_manufacturer(
                                mfr_id, result.storage_type.lower()
                            )
                    except ValueError:
                        pass

    except ET.ParseError as exc:
        result.log.append(f"    Storage info XML parse error: {exc}")
        # Fall back to line-by-line text parsing
        for line in xml_text.splitlines():
            stripped = line.strip()
            if stripped:
                result.log.append(f"    [raw] {stripped}")


def _parse_gpt_response(xml_text: str, result: EDLDetectionResult) -> None:
    """Parse the printgpt / GPT read response into partition entries."""
    try:
        root = ET.fromstring(f"<root>{xml_text}</root>")
        for log_elem in root.iter("log"):
            value = log_elem.get("value", "")
            # Typical format: "Label: system, Start: 1234, Size: 5678, ..."
            if "label" in value.lower() or "partition" in value.lower():
                entry = {"raw": value.strip()}
                # Try to extract structured fields
                for segment in value.split(","):
                    segment = segment.strip()
                    if ":" in segment:
                        k, v = segment.split(":", 1)
                        entry[k.strip().lower()] = v.strip()
                result.partitions.append(entry)
    except ET.ParseError:
        # Fall back: treat each non-empty line as a partition entry
        for line in xml_text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("<?xml") and not stripped.startswith("<"):
                result.partitions.append({"raw": stripped})


# ---------------------------------------------------------------------------
# Main detection entry point
# ---------------------------------------------------------------------------


# Signed loaders that a PBL accepted tell us the device's HWID / OEM / PK hash,
# because the PBL only runs code signed for its own fused key. Keyed by MD5[:16]
# (same convention as temblast.com/ref/loaders.htm).
KNOWN_LOADERS: Dict[str, Tuple[str, str, str, str]] = {
    # md5[:16]: (msm_id, oem_id, model_id, pk_hash_prefix)
    "0e69d6eca0fe2842": ("0010A0E1", "0072", "0000", "1bebe3863a6781db"),
}


def _infer_from_loader(path: str, result: EDLDetectionResult) -> None:
    """Fill identity fields from an accepted signed loader (see KNOWN_LOADERS)."""
    import hashlib
    try:
        with open(path, "rb") as fh:
            key = hashlib.md5(fh.read()).hexdigest()[:16]
    except OSError:
        return
    info = KNOWN_LOADERS.get(key)
    if not info:
        return
    result.msm_id, result.oem_id, result.model_id, result.pk_hash = info
    result.msm_id_raw = "0x" + info[0]
    result.chipset_name = resolve_chipset_name(info[0])
    result.oem_name = resolve_oem_name(info[1])
    result.secure_boot_enabled = True
    result.log.append(f"  Identity inferred from accepted signed loader: {result.chipset_name}, "
                      f"OEM {result.oem_name} (0x{info[1]}), PK hash {info[3]}...")


class _SkipToFirehose(Exception):
    """Control flow: programmer uploaded, jump past the command-mode steps."""


class FirehoseAlreadyRunning(Exception):
    """A Firehose loader is already resident (XML seen where Sahara HELLO was expected)."""


def detect_via_edl(callback=None, loader_path: Optional[str] = None) -> EDLDetectionResult:
    """
    Full EDL detection pipeline:

    1. Scan for Qualcomm 9008 port
    2. Sahara handshake and device identification
    3. Attempt Firehose storage / partition extraction
    4. Build and return detection result

    Parameters
    ----------
    callback : callable, optional
        Progress callback with signature ``callback(fraction, message)``
        where *fraction* is 0.0..1.0.

    Returns
    -------
    EDLDetectionResult
        Populated result dataclass.
    """
    result = EDLDetectionResult()
    start_time = time.monotonic()

    def _log(msg: str) -> None:
        result.log.append(msg)
        logger.info(msg)

    def _progress(frac: float, msg: str) -> None:
        if callback:
            callback(frac, msg)

    # ----- Step 1: Find EDL port -----
    _progress(0.05, "Scanning for Qualcomm EDL device...")
    _log("=" * 60)
    _log("Qualcomm EDL Mode Detection")
    _log("=" * 60)
    _log("")
    _log("[1/4] Scanning serial ports for Qualcomm 9008 device...")

    port = find_edl_port()
    if port is None and find_edl_usb() is not None:
        # Bound to WinUSB/libwdi instead of the QDLoader VCP driver, so it
        # has no COM port. SaharaProtocol(None) talks to it over raw bulk.
        _log("  No 9008 COM port, but found a WinUSB-bound 05C6:9008 device.")
        _log("  Falling back to raw USB bulk transport.")
    elif port is None:
        _log("  FAIL: No Qualcomm device in EDL mode found.")
        _log("")
        _log("To enter EDL mode:")
        _log("  - Short the EDL test point on the motherboard + connect USB")
        _log("  - Or run: adb reboot edl")
        _log("  - Or hold Volume Up + Down while connecting USB (device-specific)")
        _log("")
        _log("The device should appear as 'Qualcomm HS-USB QDLoader 9008'")
        _log("  VID:PID = 05C6:9008")
        result.detection_duration_s = time.monotonic() - start_time
        return result

    result.port = port or "USB(05C6:9008)"
    if not port:
        try:
            import usb.util
            dev = find_edl_usb()
            result.usb_product = usb.util.get_string(dev, dev.iProduct) or ""
            usb.util.dispose_resources(dev)
            m = re.search(r"SN:([0-9A-Fa-f]{8})", result.usb_product)
            if m:
                result.serial_number = "0x" + m.group(1).upper()
            _log(f"  USB product string: {result.usb_product}")
        except Exception as exc:
            logger.debug("iProduct read failed: %s", exc)
    result.connected = True
    _log(f"  OK: EDL device found on {result.port}")

    # ----- Step 2: Sahara handshake -----
    _progress(0.15, "Sahara protocol handshake...")
    _log("")
    _log("[2/4] Sahara protocol handshake...")

    sahara = SaharaProtocol(port)
    firehose_available = False

    try:
        sahara.open()
        _log(f"  {result.port} opened"
             + (f" at {DEFAULT_BAUD} baud" if port else " (raw USB bulk)"))

        # Wait for device HELLO
        hello_info = sahara.wait_for_hello()
        result.raw_sahara_hello = hello_info["raw"]
        result.sahara_version = str(hello_info["version"])
        result.sahara_min_version = str(hello_info["compatible_version"])
        result.sahara_max_packet_size = hello_info["max_packet_size"]
        result.sahara_mode = hello_info["mode_name"]
        result.mode = "sahara"

        _log(f"  Sahara version: {result.sahara_version} "
             f"(min compatible: {result.sahara_min_version})")
        _log(f"  Max packet size: {result.sahara_max_packet_size}")
        _log(f"  Device mode: {result.sahara_mode}")

        if loader_path:
            # ponytail: loader given -> go straight to image transfer. PBLs that
            # refuse command mode enter an error state, so we don't probe it first.
            sahara.send_hello_response(
                version=hello_info["version"],
                compat=hello_info["compatible_version"],
                desired_mode=SAHARA_MODE_IMAGE_TX,
            )
            _log(f"  HELLO_RESPONSE sent (image transfer); uploading {loader_path}")
            result.firehose_loader = loader_path
            _progress(0.3, "Uploading Firehose programmer...")
            sahara.upload_image(loader_path, progress=lambda f: _progress(0.3 + 0.3 * f,
                                "Uploading Firehose programmer..."))
            _log("  Programmer accepted by PBL (signature OK). Firehose live.")
            _infer_from_loader(loader_path, result)
            result.command_mode_supported = False
            time.sleep(1.0)
            firehose_available = True
            raise _SkipToFirehose

        # Send hello response requesting command mode
        sahara.send_hello_response(
            version=hello_info["version"],
            compat=hello_info["compatible_version"],
            desired_mode=SAHARA_MODE_COMMAND,
        )
        _log("  HELLO_RESPONSE sent (requesting command mode)")

        try:
            sahara.wait_command_ready()
            _log("  Device entered command mode (CMD_READY)")
        except PermissionError as exc:
            result.command_mode_supported = False
            _log(f"  {exc}")
            _log("  Serial/MSM-ID/PK-hash need a signed Firehose programmer on this PBL.")
            _log("  Device is now in Sahara error state: re-enter EDL before loading a programmer.")
        except Exception as exc:
            _log(f"  No CMD_READY: {exc}")
            _log("  (Will attempt identifier extraction anyway)")

        # ----- Step 3: Extract identifiers via Sahara commands -----
        _progress(0.35, "Reading device identifiers...")
        _log("")
        _log("[3/4] Reading device identifiers via Sahara commands...")

        if result.command_mode_supported:
            _extract_sahara_identifiers(sahara, result)
        else:
            _log("  Skipped (command mode unsupported).")

        # After Sahara identification, attempt to transition to Firehose
        # This requires sending a programmer image, which depends on the
        # specific chipset.  We note this but attempt raw Firehose anyway
        # in case the loader is already active.
        _log("")
        _log("  Sahara identification complete.")
        _log("  Note: Full Firehose access requires loading a programmer image")
        _log("  specific to this chipset. Attempting raw Firehose probe...")

        # Try sending done and see if Firehose picks up
        try:
            if result.command_mode_supported:
                sahara.switch_to_image_transfer()
            time.sleep(0.5)
            firehose_available = result.command_mode_supported
        except Exception:
            _log("  Could not cleanly end Sahara session")

    except _SkipToFirehose:
        pass
    except FirehoseAlreadyRunning as exc:
        _log(f"  {exc}")
        result.mode = "firehose"
        result.command_mode_supported = False
        firehose_available = True
    except PermissionError as exc:
        _log(f"  PROGRAMMER REJECTED: {exc}")
        result.errors.append(f"Programmer: {exc}")
    except ImportError:
        _log("  ERROR: pyserial is not installed.")
        _log("  Install with: pip install pyserial")
        result.errors.append("pyserial not installed")
    except TimeoutError as exc:
        _log(f"  TIMEOUT: {exc}")
        _log("  The device may not be in proper EDL mode or may need a power cycle.")
        result.errors.append(f"Sahara timeout: {exc}")
    except ConnectionError as exc:
        _log(f"  CONNECTION ERROR: {exc}")
        result.errors.append(f"Connection: {exc}")
    except Exception as exc:
        _log(f"  UNEXPECTED ERROR: {type(exc).__name__}: {exc}")
        result.errors.append(f"Sahara: {type(exc).__name__}: {exc}")
    finally:
        # Keep connection open if we want to try Firehose
        if not firehose_available:
            sahara.close()

    # ----- Step 4: Firehose storage / partition extraction -----
    _progress(0.60, "Attempting Firehose storage query...")
    _log("")
    _log("[4/4] Firehose storage and partition extraction...")

    if firehose_available and sahara.is_open:
        firehose = FirehoseProtocol(sahara._serial)
        try:
            _extract_firehose_info(firehose, result)
        except Exception as exc:
            _log(f"  Firehose extraction failed: {type(exc).__name__}: {exc}")
            result.errors.append(f"Firehose: {exc}")
        finally:
            sahara.close()
    else:
        _log("  Firehose not available (Sahara session did not complete or no programmer loaded).")
        _log("  To get full storage/partition data, load the correct Firehose programmer")
        _log("  for this chipset (e.g., prog_firehose_ddr.elf or prog_ufs_firehose.elf).")

    # ----- Finalize -----
    _progress(0.95, "Building report...")
    for line in diagnose(result):
        _log(line)
    result.detection_duration_s = time.monotonic() - start_time

    _log("")
    _log("-" * 60)
    if result.connected and result.msm_id:
        _log(
            f"Detection complete in {result.detection_duration_s:.1f}s. "
            f"Chipset: {result.chipset_name}"
        )
    elif result.connected:
        _log(
            f"Detection complete in {result.detection_duration_s:.1f}s. "
            f"Device connected but identifiers not fully read."
        )
    else:
        _log("Detection complete. No EDL device found.")

    _progress(1.0, "EDL detection complete")
    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def diagnose(result: EDLDetectionResult) -> List[str]:
    """
    Turn the raw EDL facts into a repair-bench explanation:
    what was proven good, what failed, what it means, what to measure next.
    """
    ok, bad, todo = [], [], []
    if not result.connected:
        return ["No 9008 device: phone is not in EDL, or the USB path/driver is broken."]

    ok.append("Phone enumerates as 05C6:9008 -> boot ROM (PBL) runs: SoC core, PMIC main rails, "
              "crystal and USB PHY are working.")
    if result.sahara_version:
        ok.append(f"Sahara v{result.sahara_version} handshake OK -> SoC executes code and talks USB correctly.")
    if not result.command_mode_supported and not result.firehose_build:
        bad.append("Boot ROM refuses Sahara command mode (normal on 2019+ chips): MSM ID / PK hash "
                   "need a signed programmer.")
    if result.firehose_build:
        ok.append(f"Signed programmer accepted by PBL (build {result.firehose_build}) -> secure-boot "
                  "fuses intact, DDR initialised by the loader, this is a genuine OEM board.")
    if result.firehose_auth_required:
        bad.append("Programmer is OEM auth-locked: storage cannot be tested with this file. "
                   "Use the engineering (no-auth) loader for this model.")
    if result.storage_capacity_bytes:
        ok.append(f"{result.storage_type} answers: {result.storage_manufacturer or '?'} "
                  f"{result.storage_capacity_human}; flash bus, rails and chip are alive.")
        if result.partitions:
            ok.append(f"GPT readable with {len(result.partitions)} partitions -> flash contents intact; "
                      "look at the boot images, not the hardware.")
        else:
            bad.append("Storage alive but GPT missing/unreadable -> partition table wiped or flash worn out; "
                       "full EDL flash with rawprogram/patch XML.")
    if any(e.startswith("Programmer:") for e in result.errors):
        bad.append("Programmer upload failed - no storage test was possible this session. "
                   + next(e for e in result.errors if e.startswith("Programmer:")))
    flash_dead = [e for e in result.errors if "not responding" in e]
    if flash_dead:
        bus = result.storage_type or "flash"
        bad.append(f"{bus} controller could not open the chip (loader: 'Failed to open device ... error:3' "
                   "after the full retry cycle) -> the flash never answered on CMD/CLK.")
        bad.append("XBL lives on that flash, so the PBL cannot load it and drops into EDL by itself. "
                   "This matches the no-button 9008 behaviour of this phone.")
        todo += [
            f"1. With the phone in EDL, measure the {bus} rails at the chip pads: VCC ~2.95 V and VCCQ 1.8 V.",
            "2. Rail missing -> PMIC LDO or a shorted decoupling cap on that rail (check for short to GND).",
            "3. Rails present -> chip dead or BGA joints cracked: reflow/reball, else replace the flash.",
            "4. After flash replacement: flash the full fastboot ROM in EDL with the no-auth loader and "
            "the rawprogram0.xml / patch0.xml maps.",
        ]
    elif result.firehose_build and not result.firehose_auth_required and not result.storage_capacity_bytes:
        bad.append("Programmer ran but no storage answered on any bus; see loader lines above.")
    if not result.firehose_build and not result.firehose_auth_required:
        todo.append("Load the signed Firehose programmer for this model to test the flash.")

    out = ["", "--- Diagnosis: how this fault was found ---"]
    out += [f"  [OK]   {l}" for l in ok]
    out += [f"  [FAIL] {l}" for l in bad]
    if todo:
        out.append("  Next on the bench:")
        out += [f"    {l}" for l in todo]
    if not bad:
        out.append("  [OK]   No hardware fault visible from EDL; problem is in firmware/boot images.")
    out.append("  Note: EDL/Firehose only reaches storage. PMIC voltages, DDR vendor and modem data are "
               "not readable here; they come from UART XBL logs (need a working flash) or the multimeter.")
    return out


def generate_edl_report(result: EDLDetectionResult) -> str:
    """
    Generate a formatted text report from an EDL detection result.

    Parameters
    ----------
    result : EDLDetectionResult
        The detection result to format.

    Returns
    -------
    str
        Multi-line human-readable report string.
    """
    lines: List[str] = []

    def section(title: str) -> None:
        lines.append("")
        lines.append(f"--- {title} ---")

    lines.append("=" * 60)
    lines.append("  QUALCOMM EDL MODE DETECTION REPORT")
    lines.append("=" * 60)

    lines.extend(diagnose(result))

    # Connection status
    section("Connection")
    if result.connected:
        lines.append(f"  Status     : CONNECTED")
        lines.append(f"  Port       : {result.port}")
        lines.append(f"  Protocol   : {result.mode.upper() if result.mode else 'N/A'}")
        if any("not responding" in e for e in result.errors):
            lines.append("  VERDICT    : FLASH CHIP NOT RESPONDING - PBL cannot load XBL, hence auto-EDL")
        if result.usb_product:
            lines.append(f"  USB string : {result.usb_product}")
        if result.serial_number:
            lines.append(f"  Serial     : {result.serial_number}")
        if not result.command_mode_supported:
            lines.append("  Cmd mode   : UNSUPPORTED by PBL (programmer required for MSM ID / PK hash)")
        if result.firehose_build:
            lines.append(f"  Programmer : accepted by PBL (signature OK), build {result.firehose_build}")
        if result.firehose_auth_required:
            lines.append("  Firehose   : OEM AUTH REQUIRED - loader refuses storage commands without Mi auth")
    else:
        lines.append(f"  Status     : NOT CONNECTED")
        lines.append(f"  No Qualcomm EDL (9008) device detected.")

    # Sahara info
    if result.sahara_version:
        section("Sahara Protocol")
        lines.append(f"  Version          : {result.sahara_version}")
        lines.append(f"  Min compatible   : {result.sahara_min_version}")
        lines.append(f"  Max packet size  : {result.sahara_max_packet_size}")
        lines.append(f"  Device mode      : {result.sahara_mode}")

    # Chipset identification
    if result.msm_id or result.serial_number:
        section("Device Identification")
        if result.msm_id:
            lines.append(f"  MSM ID     : 0x{result.msm_id}")
            lines.append(f"  Chipset    : {result.chipset_name}")
        if result.oem_id:
            lines.append(f"  OEM ID     : 0x{result.oem_id} ({result.oem_name})")
        if result.model_id:
            lines.append(f"  Model ID   : 0x{result.model_id}")
        if result.serial_number:
            lines.append(f"  Serial     : {result.serial_number}")
        if result.sbl_sw_version:
            lines.append(f"  SBL SW ver : {result.sbl_sw_version}")

    # Security state
    if result.pk_hash:
        section("Security")
        lines.append(f"  Secure boot: {'ENABLED' if result.secure_boot_enabled else 'DISABLED'}")
        # Show first and last 8 chars of PK hash for brevity
        if len(result.pk_hash) > 32:
            display = f"{result.pk_hash[:16]}...{result.pk_hash[-16:]}"
        else:
            display = result.pk_hash
        lines.append(f"  PK Hash    : {display}")
        lines.append(f"  Hash length: {len(result.pk_hash) // 2} bytes")

    # Storage info
    if result.storage_type:
        section("Storage")
        lines.append(f"  Type         : {result.storage_type}")
        if result.storage_manufacturer:
            lines.append(
                f"  Manufacturer : {result.storage_manufacturer} "
                f"({result.storage_manufacturer_id})"
            )
        if result.storage_capacity_human:
            lines.append(f"  Capacity     : {result.storage_capacity_human}")
        if result.num_physical_partitions > 0:
            lines.append(f"  LUN count    : {result.num_physical_partitions}")

    # Partitions
    if result.partitions:
        section(f"Partitions ({len(result.partitions)} found)")
        for i, part in enumerate(result.partitions):
            label = part.get("label", part.get("name", ""))
            if label:
                size = part.get("size", part.get("num_sectors", "?"))
                lines.append(f"  {i + 1:3d}. {label:<30s}  size={size}")
            else:
                lines.append(f"  {i + 1:3d}. {part.get('raw', str(part))}")

    # Errors
    if result.errors:
        section("Errors / Warnings")
        for err in result.errors:
            lines.append(f"  - {err}")

    # Footer
    lines.append("")
    lines.append("-" * 60)
    lines.append(f"  Detection time: {result.detection_duration_s:.1f}s")
    lines.append("=" * 60)

    return "\n".join(lines)
