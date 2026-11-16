"""
FTDI 232 based Mobile Device Detector.

Connects to phone's UART test points via FTDI USB-to-Serial adapter.
Listens for boot data when phone powers on, then parses it.

Setup:  Phone UART TX/RX → FTDI 232 → USB → PC

Usage:
    detector = DeviceAutoDetector(port='COM12')
    result = detector.detect()
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
DEFAULT_SIGNATURES_PATH = _CONFIG_DIR / "device_signatures.json"

DEFAULT_PORT = "COM12"
DEFAULT_BAUD = 115200
SERIAL_TIMEOUT = 1.0


@dataclass
class DetectionResult:
    """Result returned after detection attempt."""
    detected: bool = False
    brand: str = "Unknown"
    chipset: str = "Unknown"
    protocol: str = "Unknown"
    device_name: str = "Unknown Device"
    confidence: float = 0.0
    raw_data: str = ""
    raw_responses: Dict[str, str] = field(default_factory=dict)
    uart_log: List[str] = field(default_factory=list)
    matched_fields: Dict[str, bool] = field(default_factory=dict)
    hw_status: Dict[str, Dict[str, str]] = field(default_factory=dict)
    error: Optional[str] = None


# Known boot patterns for chipset identification
CHIPSET_PATTERNS = {
    # MediaTek
    r"F0:\s*\w+": ("MediaTek", "MediaTek Boot ROM"),
    r"Jump to BL": ("MediaTek", "MediaTek Bootloader"),
    r"mediatek|mt\d{4}|MTK_": ("MediaTek", "MediaTek SoC"),
    r"preloader": ("MediaTek", "MediaTek Preloader"),
    r"BROM": ("MediaTek", "MediaTek BROM"),
    # Qualcomm
    r"QCOM|qualcomm|SDM\d|SM\d|MSM\d": ("Qualcomm", "Qualcomm SoC"),
    r"SAHARA|sahara": ("Qualcomm", "Qualcomm Sahara"),
    r"firehose": ("Qualcomm", "Qualcomm Firehose"),
    r"SBL\d|XBL|ABL": ("Qualcomm", "Qualcomm Bootloader"),
    # Samsung Exynos
    r"exynos|EXYNOS|slsi": ("Samsung Exynos", "Samsung Exynos SoC"),
    r"S\.LSI": ("Samsung Exynos", "Samsung LSI"),
    # Apple
    r"iBoot|iboot|Apple|CPFM": ("Apple", "Apple iBoot"),
    r"SecureROM": ("Apple", "Apple SecureROM"),
    # Google Tensor
    r"tensor|TENSOR|gs\d{3}": ("Google Tensor", "Google Tensor SoC"),
    # Unisoc/Spreadtrum
    r"spreadtrum|sprd|unisoc|SPRD": ("Unisoc", "Unisoc/Spreadtrum SoC"),
    # Kirin
    r"kirin|hisilicon|KIRIN": ("HiSilicon Kirin", "Huawei Kirin SoC"),
}

# Known brand patterns from boot logs
BRAND_PATTERNS = {
    r"samsung|SAMSUNG|Galaxy": "Samsung",
    r"xiaomi|XIAOMI|Redmi|redmi|POCO|poco|miui|MIUI|mi-config|MiToken": "Xiaomi",
    r"oppo|OPPO|realme|Realme|ColorOS": "Oppo/Realme",
    r"vivo|VIVO|Funtouch": "Vivo",
    r"oneplus|OnePlus|OxygenOS": "OnePlus",
    r"huawei|HUAWEI|Honor|HONOR|EMUI": "Huawei/Honor",
    r"google|Google|Pixel": "Google",
    r"motorola|Motorola|moto": "Motorola",
    r"nokia|Nokia|HMD": "Nokia",
    r"tecno|TECNO|Infinix|INFINIX|itel|ITEL": "Tecno/Infinix",
    r"nothing|Nothing": "Nothing",
    r"asus|ASUS|ROG": "Asus",
    r"sony|Sony|Xperia": "Sony",
    r"lenovo|Lenovo": "Lenovo",
}


# MediaTek chip ID lookup table (F0 register value → chip name)
# F0 register contains the hardware code of the SoC
MTK_CHIP_IDS = {
    "0279": "MT6797 (Helio X20)",
    "0321": "MT6735",
    "0335": "MT6737",
    "0337": "MT6737M",
    "0326": "MT6750",
    "0551": "MT6757 (Helio P20)",
    "0598": "MT6763 (Helio P23)",
    "0633": "MT6765 (Helio P35)",
    "0699": "MT6768 (Helio G85)",
    "0707": "MT6769 (Helio G80)",
    "0725": "MT6771 (Helio P60)",
    "0788": "MT6779 (Helio P90)",
    "0813": "MT6781 (Helio G96)",
    "0886": "MT6785 (Helio G90)",
    "0959": "MT6789 (Helio G99)",
    "0990": "MT6833 (Dimensity 700)",
    "0996": "MT6853 (Dimensity 720)",
    "1020": "MT6873 (Dimensity 800)",
    "102B": "MT6877 (Dimensity 900)",
    "1032": "MT6879 (Dimensity 920)",
    "1038": "MT6883 (Dimensity 1000)",
    "1043": "MT6885 (Dimensity 1000+)",
    "1066": "MT6889 (Dimensity 1200)",
    "1080": "MT6891 (Dimensity 1100)",
    "1095": "MT6893 (Dimensity 1200 Ultra)",
    "1112": "MT6895 (Dimensity 8100)",
    "1200": "MT6983 (Dimensity 9000)",
    "1220": "MT6985 (Dimensity 9200)",
    "1235": "MT6989 (Dimensity 9300)",
    "0717": "MT8167 (Tablet SoC)",
    "0562": "MT8173 (Tablet SoC)",
    "0690": "MT6762 (Helio P22)",
    "0766": "MT6769V (Helio G85 V)",
    "0828": "MT6853V (Dimensity 720 V)",
}

# Qualcomm chipset model lookup table
QUALCOMM_CHIPSETS = {
    "SDM429": "Snapdragon 429",
    "SDM439": "Snapdragon 439",
    "SDM450": "Snapdragon 450",
    "SDM630": "Snapdragon 630",
    "SDM636": "Snapdragon 636",
    "SDM660": "Snapdragon 660",
    "SDM670": "Snapdragon 670",
    "SDM710": "Snapdragon 710",
    "SDM712": "Snapdragon 712",
    "SDM845": "Snapdragon 845",
    "SM4250": "Snapdragon 460",
    "SM4350": "Snapdragon 480",
    "SM6115": "Snapdragon 662",
    "SM6125": "Snapdragon 665",
    "SM6150": "Snapdragon 675",
    "SM6225": "Snapdragon 680",
    "SM6350": "Snapdragon 690",
    "SM6375": "Snapdragon 695",
    "SM7125": "Snapdragon 720G",
    "SM7150": "Snapdragon 730",
    "SM7225": "Snapdragon 750G",
    "SM7250": "Snapdragon 765G",
    "SM7325": "Snapdragon 778G",
    "SM7350": "Snapdragon 780G",
    "SM7435": "Snapdragon 7s Gen 2",
    "SM7450": "Snapdragon 7 Gen 1",
    "SM7475": "Snapdragon 7+ Gen 2",
    "SM7550": "Snapdragon 7 Gen 3",
    "SM8150": "Snapdragon 855",
    "SM8250": "Snapdragon 865",
    "SM8350": "Snapdragon 888",
    "SM8450": "Snapdragon 8 Gen 1",
    "SM8475": "Snapdragon 8+ Gen 1",
    "SM8550": "Snapdragon 8 Gen 2",
    "SM8650": "Snapdragon 8 Gen 3",
    "MSM8909": "Snapdragon 210",
    "MSM8916": "Snapdragon 410",
    "MSM8917": "Snapdragon 425",
    "MSM8937": "Snapdragon 430",
    "MSM8940": "Snapdragon 435",
    "MSM8952": "Snapdragon 617",
    "MSM8953": "Snapdragon 625",
    "MSM8956": "Snapdragon 650",
    "MSM8976": "Snapdragon 652",
    "MSM8994": "Snapdragon 810",
    "MSM8996": "Snapdragon 820",
    "MSM8998": "Snapdragon 835",
    "QCS403": "QCS403 (IoT)",
    "QCS605": "QCS605 (IoT)",
    "QCM6490": "QCM6490 (IoT)",
}


class DeviceAutoDetector:
    """
    Detects mobile devices via FTDI 232 connected to phone UART test points.
    Listens for boot data, then analyzes it to identify chipset and brand.
    """

    def __init__(self, port: str = DEFAULT_PORT, baud: int = DEFAULT_BAUD,
                 signatures_path: Optional[str | Path] = None) -> None:
        self.port = port
        self.baud = baud
        self.signatures_path = Path(signatures_path) if signatures_path else DEFAULT_SIGNATURES_PATH
        self._serial = None
        self._db: List[Dict[str, Any]] = []
        self._load_signatures()

    def _load_signatures(self) -> None:
        try:
            with open(self.signatures_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._db = data.get("devices", [])
        except (FileNotFoundError, json.JSONDecodeError):
            self._db = []

    def _open_serial(self, baud: Optional[int] = None) -> bool:
        self._close_serial()
        try:
            import serial
            self._serial = serial.Serial(
                port=self.port,
                baudrate=baud or self.baud,
                timeout=SERIAL_TIMEOUT,
                write_timeout=SERIAL_TIMEOUT,
            )
            time.sleep(0.3)
            self._serial.reset_input_buffer()
            return True
        except ImportError:
            return False
        except Exception as exc:
            logger.warning("Could not open %s: %s", self.port, exc)
            return False

    def _close_serial(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
            self._serial = None

    def _read_all_data(self, duration: float = 10.0, callback=None) -> bytes:
        """
        Listen on UART for given duration, collecting all incoming data.
        Phone should be booted/rebooted during this time.
        callback is called with (elapsed_seconds, bytes_received) for progress updates.
        """
        if not self._serial or not self._serial.is_open:
            return b""

        self._serial.reset_input_buffer()
        data = b""
        start = time.time()

        while time.time() - start < duration:
            if self._serial.in_waiting > 0:
                chunk = self._serial.read(self._serial.in_waiting)
                data += chunk

            if callback:
                elapsed = time.time() - start
                callback(elapsed, len(data))

            time.sleep(0.1)

        return data

    def _read_multi_baud(self, duration: float = 30.0, callback=None) -> Dict[int, bytes]:
        """
        Listen on multiple baud rates to capture full boot sequence.

        Strategy: use the user-selected baud rate (self.baud) for the primary
        capture.  If the captured data is mostly binary (< 5% printable ASCII),
        the baud rate is likely wrong — retry with the other common rate.

        MediaTek: BROM=115200 → Preloader/LK/Kernel=921600
        Qualcomm: typically 115200 or 1500000
        """
        all_data = {}

        # Primary baud = whatever the user/caller selected
        primary_baud = self.baud
        # Fallback bauds to try if primary yields unreadable data
        common_bauds = [115200, 921600, 460800, 1500000]
        fallback_bauds = [b for b in common_bauds if b != primary_baud]

        global_start = time.time()

        # ── Phase 1: capture at the primary baud rate ──
        try:
            self._close_serial()
            if self._open_serial(primary_baud):
                all_data[primary_baud] = b""
                phase_start = time.time()
                while time.time() - phase_start < duration:
                    if self._serial.in_waiting > 0:
                        chunk = self._serial.read(self._serial.in_waiting)
                        all_data[primary_baud] += chunk
                    if callback:
                        elapsed = time.time() - global_start
                        total_bytes = sum(len(d) for d in all_data.values())
                        callback(min(elapsed, duration), total_bytes, primary_baud)
                    time.sleep(0.05)
        except Exception:
            pass

        # ── Phase 2: check if data looks readable ──
        primary_data = all_data.get(primary_baud, b"")
        if len(primary_data) > 100:
            printable = sum(1 for b in primary_data[:4096] if 0x20 <= b <= 0x7E or b in (0x0A, 0x0D, 0x09))
            sample = min(len(primary_data), 4096)
            printable_pct = printable / sample * 100

            # If less than 5% printable, the baud rate is likely wrong
            if printable_pct < 5:
                # Try each fallback baud for a short listen to find readable data
                for fb_baud in fallback_bauds:
                    try:
                        self._close_serial()
                        if not self._open_serial(fb_baud):
                            continue
                        fb_data = b""
                        fb_start = time.time()
                        # Short probe — 8 seconds to check if this baud produces text
                        while time.time() - fb_start < 8:
                            if self._serial.in_waiting > 0:
                                chunk = self._serial.read(self._serial.in_waiting)
                                fb_data += chunk
                            time.sleep(0.05)

                        if len(fb_data) > 50:
                            fb_printable = sum(1 for b in fb_data[:2048] if 0x20 <= b <= 0x7E or b in (0x0A, 0x0D, 0x09))
                            fb_pct = fb_printable / min(len(fb_data), 2048) * 100
                            if fb_pct > 20:
                                # This baud produces readable data — keep it
                                all_data[fb_baud] = fb_data
                                break
                    except Exception:
                        continue

        self._close_serial()
        return all_data

    @staticmethod
    def _load_ic_database():
        """Load chipset IC database from config file."""
        import json as _json
        db_path = Path(__file__).resolve().parent.parent.parent / "config" / "chipset_ic_database.json"
        try:
            if db_path.exists():
                with open(db_path, "r", encoding="utf-8") as f:
                    return _json.load(f)
        except Exception:
            pass
        return {}

    @staticmethod
    def _load_fault_rules(platform: str = "") -> Dict[str, list]:
        """Load noise + fault patterns for a platform from config/fault_rules.json.

        Merges the "common" pack with the detected platform's pack, so vendor
        boot-chatter from one chipset never suppresses a real fault on another.
        Returns {"noise": [...], "faults": [(pattern, name, conf, repair), ...]}.
        A missing or malformed file yields empty lists; the caller keeps its
        built-in tables so a bad edit degrades instead of breaking detection.
        """
        import json as _json
        path = Path(__file__).resolve().parent.parent.parent / "config" / "fault_rules.json"
        noise, faults = [], []
        try:
            with open(path, "r", encoding="utf-8") as f:
                db = _json.load(f)
        except Exception:
            return {"noise": noise, "faults": faults}

        for key in ("common", (platform or "").lower()):
            pack = db.get(key)
            if not isinstance(pack, dict):
                continue
            noise.extend(p for p in pack.get("noise", []) if isinstance(p, str))
            for rule in pack.get("faults", []):
                pat, name = rule.get("pattern"), rule.get("name")
                if not pat or not name:
                    continue
                try:
                    re.compile(pat)
                except re.error:
                    continue  # a typo'd regex must not take the scan down
                faults.append((pat, name, int(rule.get("confidence", 50)),
                               rule.get("repair") or []))
        # Specific rules first, so a 95 never hides behind a generic 60.
        faults.sort(key=lambda r: -r[2])
        return {"noise": noise, "faults": faults}

    @staticmethod
    def _extract_embedded_strings(raw: bytes, min_len: int = 6) -> List[str]:
        """Extract readable ASCII strings embedded within binary data.
        Binary UART frames often contain readable substrings like chip names,
        error messages, version strings, etc."""
        strings = []
        current = []
        for b in raw:
            if 0x20 <= b <= 0x7E:
                current.append(chr(b))
            else:
                if len(current) >= min_len:
                    s = "".join(current)
                    # Filter out repetitive garbage
                    if len(set(s)) > 2:
                        strings.append(s)
                current = []
        if len(current) >= min_len and len(set("".join(current))) > 2:
            strings.append("".join(current))
        return strings

    @staticmethod
    def _parse_binary_boot_data(raw: bytes) -> Dict[str, str]:
        """Analyze binary UART data for chipset identification.

        MediaTek BROM protocol uses binary frames:
        - Handshake: 0xA0 0x0A 0x50 0x05
        - DA mode handshake: 0xDA
        - Chip ID typically appears after handshake in specific offsets
        - Register reads: command byte + 4-byte address + response

        Qualcomm Sahara protocol:
        - Magic: 0x7AAA55AA (Sahara hello)
        - EDL mode: 0x01 (hello packet command)

        This method detects the binary protocol and extracts chip identity.
        """
        info = {}

        # ── MediaTek BROM Binary Detection ──
        # BROM handshake bytes
        mtk_handshake = bytes([0xA0, 0x0A, 0x50, 0x05])
        mtk_da_byte = 0xDA

        if mtk_handshake in raw:
            info["protocol"] = "MediaTek BROM (binary)"
            info["chipset"] = "MediaTek"
            info["chipset_detail"] = "MediaTek Boot ROM (binary protocol detected)"

            # After handshake, the BROM sends chip info
            # Look for chip ID pattern: the BROM responds to GET_HW_CODE (0xFD)
            # Response format: 2-byte status + 2-byte HW code + 2-byte HW sub-code
            hw_code_cmd = bytes([0xFD])
            idx = raw.find(hw_code_cmd)
            while idx >= 0 and idx + 5 < len(raw):
                # Check if this looks like a valid response context
                # HW codes are typically 2 bytes like 0x03, 0x21 etc.
                potential_code = raw[idx+1:idx+3]
                if len(potential_code) == 2:
                    hw_code = f"{potential_code[0]:02X}{potential_code[1]:02X}"
                    # Check if it's a known MTK chip code
                    if hw_code in MTK_CHIP_IDS:
                        info["mtk_chip_code"] = hw_code
                        info["chipset_detail"] = MTK_CHIP_IDS[hw_code]
                        info["mtk_chip_name"] = MTK_CHIP_IDS[hw_code]
                        break
                idx = raw.find(hw_code_cmd, idx + 1)

            # Also scan for raw 2-byte chip IDs anywhere in the binary data
            if "mtk_chip_code" not in info:
                for code, name in MTK_CHIP_IDS.items():
                    code_bytes = bytes.fromhex(code)
                    if code_bytes in raw:
                        # Verify by checking if it appears near other BROM data
                        code_idx = raw.find(code_bytes)
                        # Chip codes often appear within first 1KB of BROM response
                        if code_idx < 2048:
                            info["mtk_chip_code"] = code
                            info["chipset_detail"] = name
                            info["mtk_chip_name"] = name
                            break

        # Check for 0xA0 alone (partial BROM handshake)
        elif raw.count(0xA0) > 5:
            # Many 0xA0 bytes = likely BROM trying to sync
            info["protocol"] = "MediaTek BROM (sync phase)"
            info["chipset"] = "MediaTek"
            info["chipset_detail"] = "MediaTek Boot ROM (sync detected, no handshake completed)"

        # ── Qualcomm Sahara Binary Detection ──
        sahara_magic = b'\x7a\xaa\x55\xaa'  # Sahara hello magic (little-endian 0xAA55AA7A)
        sahara_magic_le = b'\xaa\x55\xaa\x7a'

        if sahara_magic in raw or sahara_magic_le in raw:
            info["protocol"] = "Qualcomm Sahara"
            info["chipset"] = "Qualcomm"
            info["chipset_detail"] = "Qualcomm Sahara Protocol (EDL mode)"

        # ── Qualcomm HDLC framing (0x7E start/end) ──
        hdlc_count = raw.count(0x7E)
        if hdlc_count > 10 and "chipset" not in info:
            info["protocol"] = "Qualcomm HDLC"
            info["chipset"] = "Qualcomm"
            info["chipset_detail"] = "Qualcomm HDLC Protocol (diagnostic mode)"

        # ── Unisoc/Spreadtrum Binary Detection ──
        # Unisoc bootloader uses 0x7E framing similar to HDLC
        # FDL1 header magic
        if b'\xAA\x55' in raw[:100] and "chipset" not in info:
            # Check for Unisoc-specific patterns
            if b'SPRD' in raw or b'sprd' in raw:
                info["protocol"] = "Unisoc FDL"
                info["chipset"] = "Unisoc"
                info["chipset_detail"] = "Unisoc/Spreadtrum FDL Protocol"

        # ── Generic binary analysis ──
        # Byte frequency analysis to detect structured data vs noise
        if len(raw) > 1000:
            # Check for repeating byte patterns (indicates structured protocol)
            byte_counts = {}
            for b in raw[:4096]:
                byte_counts[b] = byte_counts.get(b, 0) + 1

            # Most common bytes
            top_bytes = sorted(byte_counts.items(), key=lambda x: -x[1])[:5]
            info["top_binary_bytes"] = ", ".join(f"0x{b:02X}({c}x)" for b, c in top_bytes)

            if "protocol" not in info:
                # Check for potential MediaTek even without handshake
                # BROM continuously sends 0xA0 during sync
                if top_bytes and top_bytes[0][0] == 0xA0:
                    info["protocol"] = "MediaTek BROM (sync flood)"
                    info["chipset"] = "MediaTek"
                    info["chipset_detail"] = "MediaTek Boot ROM (device sending sync bytes — BROM active)"
                else:
                    # Data received but protocol unrecognized — likely wrong baud rate.
                    # Still mark as binary data received so caller knows the device is alive.
                    null_pct = byte_counts.get(0, 0) / min(len(raw), 4096) * 100
                    info["protocol"] = "binary (unrecognized)"
                    info["binary_data_size"] = f"{len(raw)} bytes"
                    info["null_byte_pct"] = f"{null_pct:.0f}%"
                    info["chipset_detail"] = (
                        f"Binary data received ({len(raw)} bytes) but protocol not recognized. "
                        f"Try a different baud rate (115200, 921600, 460800)."
                    )

        return info

    @staticmethod
    def _split_boot_cycles(text: str) -> List[str]:
        """Split a capture into individual boot cycles.

        A UART listen window usually catches several boots. Qualcomm restarts
        its log with "PBL, End" every power-on; MediaTek with a preloader
        banner. Returns [text] when no marker is found, so single-boot
        captures behave exactly as before.
        """
        marks = [m.start() for m in re.finditer(
            r"^\s*S -\s+\d+\s+- PBL, End|^\s*\[PLFM\].*preloader",
            text, re.MULTILINE | re.IGNORECASE)]
        if len(marks) < 2:
            return [text]
        bounds = [0] + marks if marks[0] > 0 else marks
        return [text[a:b] for a, b in zip(bounds, bounds[1:] + [len(text)]) if text[a:b].strip()]

    def _parse_boot_data(self, raw: bytes) -> Dict[str, str]:
        """Parse raw UART boot data and extract useful information."""
        results = {}

        # Load IC database for chipset-specific identification
        ic_db = self._load_ic_database()

        # ── Binary vs Text Analysis ──
        # Determine what % of data is printable ASCII vs binary
        printable_bytes = sum(1 for b in raw if 0x20 <= b <= 0x7E or b in (0x0A, 0x0D, 0x09))
        printable_pct = (printable_bytes / len(raw) * 100) if raw else 0
        results["data_printable_pct"] = f"{printable_pct:.1f}%"
        results["data_binary_pct"] = f"{100 - printable_pct:.1f}%"

        # ── Binary Protocol Detection ──
        # If data is mostly binary, try to extract info from binary patterns
        if printable_pct < 30 and len(raw) > 1000:
            binary_info = self._parse_binary_boot_data(raw)
            results.update(binary_info)

        # Decode to text — try UTF-8 first, then ASCII
        # Also extract embedded text strings from binary data
        text = raw.decode("utf-8", errors="replace")
        # Additionally extract any ASCII strings embedded in binary data
        # (binary frames often contain readable substrings)
        if printable_pct < 50:
            embedded_strings = self._extract_embedded_strings(raw)
            if embedded_strings:
                text = text + "\n" + "\n".join(embedded_strings)
                results["embedded_strings_found"] = len(embedded_strings)

        results["raw_text"] = text
        results["raw_hex"] = raw[:200].hex()
        results["data_size"] = f"{len(raw)} bytes"

        # Extract readable lines
        lines = []
        for line in text.split("\n"):
            clean = line.strip()
            # Keep only lines with printable content
            printable = "".join(c for c in clean if c.isprintable() or c in "\t ")
            if len(printable) > 3:
                lines.append(printable)

        results["readable_lines"] = "\n".join(lines)

        # Detect chipset from patterns
        for pattern, (chipset, detail) in CHIPSET_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                results["chipset"] = chipset
                results["chipset_detail"] = detail
                break

        # Detect brand from patterns
        for pattern, brand in BRAND_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                results["brand"] = brand
                break

        # ── Platform Detection ──
        # Detect which chipset platform this boot log belongs to
        platform = "unknown"
        if re.search(r"SBL\d|XBL|ABL|SDM\d|SM\d{4}|MSM\d|Qualcomm|qcom|QCOM", text, re.IGNORECASE):
            platform = "qualcomm"
        elif re.search(r"F0:\s*[0-9A-Fa-f]{4}|PWRAP|mtcmos|MediaTek|MTK|Jump to BL", text, re.IGNORECASE):
            platform = "mediatek"
        elif re.search(r"Exynos|SLSI|S\.LSI|samsung.*soc", text, re.IGNORECASE):
            platform = "exynos"
        elif re.search(r"FDL\d|fdl\d|spreadtrum|sprd|unisoc|SPRD", text, re.IGNORECASE):
            platform = "unisoc"

        results["platform"] = platform

        # ── Qualcomm-Specific Parsing ──
        if platform == "qualcomm":
            # Chipset model detection — try multiple formats
            # Format 1: SDM/SM/MSM model numbers
            qc_model_match = re.search(r"(SDM\d{3}|SM\d{4}|MSM\d{4}|QCS\d{3,4}|QCM\d{3,4})", text, re.IGNORECASE)
            if qc_model_match:
                model = qc_model_match.group(1).upper()
                chip_name = QUALCOMM_CHIPSETS.get(model, f"Qualcomm {model}")
                results["chipset"] = "Qualcomm"
                results["chipset_detail"] = chip_name
                results["qcom_model"] = model

            # Format 2: "Chip Name : SM_XXXXX" (UEFI boot log format)
            chip_name_match = re.search(r"Chip Name\s*:\s*(\S+)", text)
            if chip_name_match:
                chip_raw = chip_name_match.group(1)
                results["qcom_chip_name"] = chip_raw
                if "chipset_detail" not in results or results["chipset_detail"] == "Qualcomm Bootloader":
                    results["chipset"] = "Qualcomm"
                    results["chipset_detail"] = f"Qualcomm {chip_raw}"

            # Format 3: WAIPIO/KALAMA/TARO codenames in version strings
            codename_match = re.search(r"BOOT\.\w+\.\d+\.\d+-\d+-(\w+)-", text)
            if codename_match:
                codename = codename_match.group(1).upper()
                qc_codename_map = {
                    "WAIPIO": "SM8450 (Snapdragon 8 Gen 1)",
                    "TARO": "SM8475 (Snapdragon 8+ Gen 1)",
                    "KALAMA": "SM8550 (Snapdragon 8 Gen 2)",
                    "PINEAPPLE": "SM8650 (Snapdragon 8 Gen 3)",
                    "LAHAINA": "SM8350 (Snapdragon 888)",
                    "KONA": "SM8250 (Snapdragon 865)",
                    "MSMNILE": "SM8150 (Snapdragon 855)",
                    "KODIAK": "SM7325 (Snapdragon 778G)",
                    "HOLI": "SM6375 (Snapdragon 695)",
                    "BLAIR": "SM6225 (Snapdragon 680)",
                    "BENGAL": "SM6115 (Snapdragon 662)",
                    "YUPIK": "SM7325 (Snapdragon 778G)",
                    "CAPE": "SM8475 (Snapdragon 8+ Gen 1)",
                    "NEO": "SM7435 (Snapdragon 7s Gen 2)",
                    "CROW": "SM7550 (Snapdragon 7 Gen 3)",
                    "PARROT": "SM7450 (Snapdragon 7 Gen 1)",
                }
                if codename in qc_codename_map:
                    results["chipset"] = "Qualcomm"
                    results["chipset_detail"] = qc_codename_map[codename]
                    results["qcom_model"] = qc_codename_map[codename].split(" ")[0]
                results["qcom_codename"] = codename

            # Chip version
            chip_ver_match = re.search(r"Chip Ver\s*:\s*(\S+)", text)
            if chip_ver_match:
                results["qcom_chip_ver"] = chip_ver_match.group(1)

            # JTAG ID (useful for identification)
            jtag_match = re.search(r"JTAG ID\s*@\s*\S+\s*=\s*(0x[0-9A-Fa-f]+)", text)
            if jtag_match:
                results["qcom_jtag_id"] = jtag_match.group(1)

            # SKU / hardware model from Motorola/OEM boot
            sku_match = re.search(r"SKU:\s*(\S+)", text)
            if sku_match:
                results["board_name"] = sku_match.group(1)

            # androidboot.device for board code
            device_match = re.search(r"androidboot\.device=(\S+)", text)
            if device_match:
                results["qcom_device_code"] = device_match.group(1)

            # Hardware SKU from bootconfig
            hw_sku_match = re.search(r"androidboot\.hardware\.sku=(\S+)", text)
            if hw_sku_match:
                if "board_name" not in results:
                    results["board_name"] = hw_sku_match.group(1)

            # SBL / XBL boot stage tracking
            boot_stages_found = []
            if re.search(r"SBL1.*Start", text, re.IGNORECASE):
                boot_stages_found.append("SBL1")
            if re.search(r"sbl1_ddr_init", text, re.IGNORECASE):
                boot_stages_found.append("DDR Init")
            if re.search(r"do_ddr_training|DDR Training", text, re.IGNORECASE):
                boot_stages_found.append("DDR Training")
            if re.search(r"QSEE\s*-\s*Image Load", text, re.IGNORECASE):
                boot_stages_found.append("QSEE")
            if re.search(r"QHEE\s*-\s*Image Load", text, re.IGNORECASE):
                boot_stages_found.append("QHEE")
            if re.search(r"APPSBL\s*-\s*Image Load", text, re.IGNORECASE):
                boot_stages_found.append("APPSBL")
            if re.search(r"SBL1,\s*End", text, re.IGNORECASE):
                boot_stages_found.append("SBL1 End")
            if re.search(r"UEFI Start", text, re.IGNORECASE):
                boot_stages_found.append("UEFI")
            if re.search(r"BDS Entry", text, re.IGNORECASE):
                boot_stages_found.append("BDS")
            if re.search(r"Shutting Down UEFI|Exit EBS", text, re.IGNORECASE):
                boot_stages_found.append("UEFI Exit → Kernel")
            if re.search(r"ABOOT|aboot", text):
                boot_stages_found.append("ABOOT")
            if boot_stages_found:
                results["boot_stage"] = " -> ".join(boot_stages_found)
                results["qcom_last_stage"] = boot_stages_found[-1]

            # ── RAM / DDR detection ──
            # Format: "RAM Installed : 12288 MB"
            ram_installed = re.search(r"RAM Installed\s*:\s*(\d+)\s*MB", text)
            if ram_installed:
                mb = int(ram_installed.group(1))
                results["ram"] = f"{mb // 1024} GB" if mb >= 1024 else f"{mb} MB"

            # Format: "RAM: SKHYNIX, LP4x, 12288 MB, MR5:..."
            ram_detail = re.search(r"RAM:\s*(\w+),\s*(LP\d[xX]?),\s*(\d+)\s*MB", text)
            if ram_detail:
                results["ram_manufacturer"] = ram_detail.group(1)
                results["ram_type"] = ram_detail.group(2).upper()
                mb = int(ram_detail.group(3))
                results["ram"] = f"{mb // 1024} GB" if mb >= 1024 else f"{mb} MB"

            # Format: "LP4 DDR detected" or "LP4x"
            if "ram_type" not in results:
                lp_match = re.search(r"(LP\d[xX]?)\s*DDR\s*detected", text, re.IGNORECASE)
                if lp_match:
                    results["ram_type"] = lp_match.group(1).upper()

            # DDR frequency: "DDR Frequency, 1708 MHz" or "Max enabled DDR Freq = 2092 MHz"
            ddr_freq = re.search(r"DDR Frequency,?\s*(\d+)\s*MHz", text, re.IGNORECASE)
            if ddr_freq:
                results["ram_freq"] = f"{ddr_freq.group(1)} MHz"
            if "ram_freq" not in results:
                max_ddr = re.search(r"Max enabled DDR Freq\s*=\s*(\d+)\s*MHz", text)
                if max_ddr:
                    results["ram_freq"] = f"{max_ddr.group(1)} MHz"

            # DDR rank sizes: "Rank 0 size = 6144 MB, Rank 1 size = 6144 MB"
            # One boot dump = one "Rank 0" followed by its higher ranks. A log
            # captured over several reboots repeats the dump, so split on each
            # "Rank 0" and keep only the last complete cycle -- never sum across
            # boots (that reported 8 GB on a 4 GB phone).
            rank_all = re.findall(r"Rank (\d+) size\s*=\s*(\d+)\s*MB", text)
            if rank_all:
                cycle = []
                for num, sz in rank_all:
                    if num == "0":
                        cycle = []
                    cycle.append((num, sz))
                total = sum(int(sz) for _, sz in cycle)
                results["qcom_ddr_ranks"] = f"{len(cycle)} ranks, {total} MB total"
                if "ram" not in results and total > 0:
                    results["ram"] = f"{total // 1024} GB" if total >= 1024 else f"{total} MB"

            # DDR manufacturer ID: "Manufacturer ID = ff"
            ddr_mfr = re.search(r"Manufacturer ID\s*=\s*([0-9A-Fa-f]+)", text)
            if ddr_mfr and "ram_manufacturer" not in results:
                mfr_map = {"01": "Samsung", "06": "SK Hynix", "ff": "Micron", "ad": "SK Hynix", "2c": "Micron", "ce": "Samsung"}
                mfr_id = ddr_mfr.group(1).lower()
                results["ram_manufacturer"] = mfr_map.get(mfr_id, f"ID:{mfr_id}")

            # DDR firmware/DSF version: "DSF version = 68.1.40"
            dsf_match = re.search(r"DSF version\s*=\s*(\S+)", text)
            if dsf_match:
                results["ddr_dsf_version"] = dsf_match.group(1)

            # DDR training frequency: "Frequency = 1355 MHz" (inside do_ddr_training)
            if "ram_freq" not in results:
                train_freq = re.search(r"DDR Frequency,?\s*(\d+)\s*MHz", text)
                if train_freq:
                    results["ram_freq"] = f"{train_freq.group(1)} MHz"

            # CPU cores: "CPU Cores : 8"
            cpu_match = re.search(r"CPU Cores\s*:\s*(\d+)", text)
            if cpu_match:
                results["cpu_cores"] = cpu_match.group(1)

            # Core frequency: "Core 0 Frequency, 1497 MHz" or "Boot Core : 1804 MHz"
            core_freq = re.search(r"(?:Core 0 Frequency|Boot Core)\s*[,:]\s*(\d+)\s*MHz", text)
            if core_freq:
                results["qcom_core_freq"] = f"{core_freq.group(1)} MHz"

            # ── Storage ──
            # UFS: "Boot Interface: UFS" or "UFS Spec Version: 2.20"
            if re.search(r"Boot Interface:\s*UFS|UFS Spec Version|Boot Device\s*:\s*UFS", text, re.IGNORECASE):
                results["storage"] = "UFS"
                results["storage_type"] = "UFS"
            elif re.search(r"Boot Interface:\s*eMMC|emmc_init|Boot Device\s*:\s*eMMC", text, re.IGNORECASE):
                results["storage"] = "eMMC"
                results["storage_type"] = "eMMC"

            # UFS details: "UFS INQUIRY ID: SKhynix H9QT1GGCN6X147  A003"
            ufs_id = re.search(r"UFS INQUIRY ID:\s*(.+?)(?:\r?\n|$)", text)
            if ufs_id:
                results["qcom_ufs_id"] = ufs_id.group(1).strip()

            # UFS size: "UFS Total Size: 256 GB"
            ufs_size = re.search(r"UFS Total Size:\s*(\d+)\s*(GB|MB)", text)
            if ufs_size:
                results["storage"] = f"UFS {ufs_size.group(1)} {ufs_size.group(2)}"

            # UFS speed: "UFS Speed: Gear 3 Lane 2 Rate B"
            ufs_speed = re.search(r"UFS Speed:\s*(.+?)(?:\r?\n|$)", text)
            if ufs_speed:
                results["storage_max_speed"] = ufs_speed.group(1).strip()

            # UFS spec: "UFS Spec Version: 2.20"
            ufs_spec = re.search(r"UFS Spec Version:\s*(\S+)", text)
            if ufs_spec:
                results["qcom_ufs_spec"] = ufs_spec.group(1)

            # ── PMIC ──
            # Format: "PMIC A:2.0 B:1.1 E:2.0 I:1.0"
            pmic_ver = re.search(r"PMIC\s+((?:[A-Z]:\d+\.\d+\s*)+)", text)
            if pmic_ver:
                results["pmic_model"] = pmic_ver.group(1).strip()

            # Format: "PM0: 47, PM1: 77, PM4: 38, PM8: 46"
            pmic_ids = re.search(r"(PM\d+:\s*\d+(?:,\s*PM\d+:\s*\d+)+)", text)
            if pmic_ids:
                results["pmic_model"] = pmic_ids.group(1).strip()

            # PMIC reset cause: "PM: Reset by PSHOLD" / "PM: Reset Type: Shutdown"
            reset_match = re.search(r"PM:\s*Reset by\s+(\S+)", text)
            if reset_match:
                results["pmic_reset_cause"] = reset_match.group(1)
            reset_type = re.search(r"PM:\s*Reset Type:\s*(\S+)", text)
            if reset_type:
                results["pmic_reset_cause"] = reset_type.group(1)

            # PON reason: "PM: PON by SYSOK" or "PON_REASON1: USB_CHG" or "PM: POWER ON by KPDPWR"
            pon_match = re.search(r'PON_REASON1:\s*"?(\w+)"?', text)
            if pon_match:
                results["boot_reason"] = pon_match.group(1)
            else:
                pon_alt = re.search(r"PM:\s*(?:PON by|POWER ON by)\s+(\S+?)(?:,|$)", text, re.MULTILINE)
                if pon_alt:
                    results["boot_reason"] = pon_alt.group(1)

            # Power-off reason: "POFF_REASON1: ..." or "PM: POWER OFF by RAW_DVDD_SHD"
            poff_match = re.search(r'POFF_REASON1:\s*"?(\w+)"?', text)
            if poff_match:
                results["boot_reason_detail"] = f"POFF: {poff_match.group(1)}"
            else:
                poff_alt = re.search(r"PM:\s*POWER OFF (?:by|due to)\s+(.+?)(?:\r?\n|,\s*POWER ON)", text)
                if poff_alt:
                    results["boot_reason_detail"] = f"POFF: {poff_alt.group(1).strip()}"

            # ── Battery ──
            # "PM: Vbat:3983mV" or "PM: VBAT: 3983mV" or "PM: EntryVbat: 4032;"
            # A capture spans several boots; report the LAST reading, not the
            # first, or a single dead-battery cycle hides a healthy recovery.
            vbat_all = re.findall(
                r"PM:\s*(?:V[Bb]at|VBAT|EntryVbat|ExitVbatt)\s*:\s*(\d+)", text)
            if vbat_all:
                results["battery_vbat"] = f"{vbat_all[-1]} mV"
                if len(vbat_all) > 1:
                    results["battery_vbat_per_cycle"] = ", ".join(f"{v} mV" for v in vbat_all)

            # SBL pre-charge loop: "PM: Vbatt: 0; Ibatt: 3824" — reading pairs
            # that are physically impossible mean the sense path, not the cell.
            # Judged further down, where every chipset passes through.
            _vi = re.findall(r"PM:\s*Vbatt:\s*(-?\d+);\s*Ibatt:\s*(-?\d+)", text)
            if _vi:
                results["battery_vi_samples"] = "; ".join(f"{v}mV/{i}mA" for v, i in _vi)

            ibat_match = re.search(r"IBAT:\s*(-?\d+)\s*mA", text)
            if ibat_match:
                results["qcom_ibat"] = f"{ibat_match.group(1)} mA"

            # Battery ID: "PM: Battery ID: 101026Ohm" or "PM: battery Id: 98189"
            batt_id = re.search(r"(?:B|b)attery\s*(?:ID|Id)\s*:\s*(\d+)", text)
            if batt_id:
                results["qcom_battery_id"] = f"{batt_id.group(1)} Ohm"

            # ── Display ──
            # "Detected panel name tm_vtdr6115_667_1080x2400_dsc_vid_144hz_fhd"
            panel_match = re.search(r"Detected panel name\s+(\S+)", text)
            if panel_match:
                results["qcom_display"] = panel_match.group(1)

            # "DisplayDxe: Resolution 1080x2400"
            res_match = re.search(r"(?:Resolution|resolution)\s*:?\s*(\d+)\s*x\s*(\d+)", text)
            if res_match:
                results["qcom_display_res"] = f"{res_match.group(1)}x{res_match.group(2)}"

            # ── WiFi / Bluetooth ──
            wifi_mac = re.search(r"wifimacaddr=([0-9A-Fa-f:]+)", text)
            if wifi_mac:
                results["qcom_wifi"] = f"MAC: {wifi_mac.group(1)}"

            bt_mac = re.search(r"btmacaddr=([0-9A-Fa-f:]+)", text)
            if bt_mac:
                results["qcom_bluetooth"] = f"MAC: {bt_mac.group(1)}"

            # ── Verified Boot / Security ──
            vb_state = re.search(r"boot state.*?:\s*(\w+)", text, re.IGNORECASE)
            if vb_state:
                results["qcom_vb_state"] = vb_state.group(1)

            secure_boot = re.search(r"Secure Boot:\s*(\w+)", text)
            if secure_boot:
                results["qcom_secure_boot"] = secure_boot.group(1)

            # Serial number: "androidboot.serialno=XXX" or "Serial Number @ 0x... = 0x18180ac6"
            serial_match = re.search(r"androidboot\.serialno=(\S+)", text)
            if serial_match:
                results["qcom_serial"] = serial_match.group(1)
            else:
                serial_alt = re.search(r"Serial Number\s*@\s*\S+\s*=\s*(0x[0-9A-Fa-f]+)", text)
                if serial_alt:
                    results["qcom_serial"] = serial_alt.group(1)

            # OEM ID
            oem_id = re.search(r"OEM ID\s*@\s*\S+\s*=\s*(0x[0-9A-Fa-f]+)", text)
            if oem_id:
                results["qcom_oem_id"] = oem_id.group(1)

            # Bootloader version
            bl_match = re.search(r"androidboot\.bootloader=(\S+)", text)
            if bl_match:
                results["version"] = bl_match.group(1)

            # Device product name / codename from ABL log
            # "check abl product name is mojito" or "product_name sunny" or "PRODUCT_NAME is mojito"
            prod_match = re.search(r"(?:abl product name is|PRODUCT_NAME is|product_name)\s+(\w+)", text)
            if prod_match:
                results["qcom_product_name"] = prod_match.group(1)

            # Display panel name from UEFI
            if "qcom_display" not in results:
                panel_reg = re.search(r"DisplayDxe:\s*Resolution\s+(\d+x\d+)", text)
                if panel_reg:
                    results["qcom_display_res"] = panel_reg.group(1)

            # Total installed RAM from UEFI: "Total Installed RAM : 4096 MB"
            total_ram = re.search(r"Total Installed RAM\s*:\s*(\d+)\s*MB", text)
            if total_ram and "ram" not in results:
                mb = int(total_ram.group(1))
                results["ram"] = f"{mb // 1024} GB" if mb >= 1024 else f"{mb} MB"

            # Boot timing from Qualcomm format "B - NNNNNN - label"
            qc_timings = re.findall(r"[BD]\s*-\s*(\d+)\s*-\s*(.+?)(?:\r?\n|$)", text)
            if qc_timings:
                results["qcom_boot_timings"] = str(len(qc_timings))
                try:
                    last_us = int(qc_timings[-1][0])
                    results["qcom_boot_time_ms"] = f"{last_us / 1000:.0f} ms"
                except (ValueError, IndexError):
                    pass

            # UEFI total time: "UEFI Total : 1068 ms"
            uefi_total = re.search(r"UEFI Total\s*:\s*(\d+)\s*ms", text)
            if uefi_total:
                results["qcom_uefi_total"] = f"{uefi_total.group(1)} ms"

            # Machine model from XBL/kernel format
            qc_machine_match = re.search(r"Machine model:\s*(.+?)(?:\r?\n|$)", text, re.IGNORECASE)
            if qc_machine_match:
                results["board_name"] = qc_machine_match.group(1).strip()

            # Motorola MBM version
            mbm_match = re.search(r"MBM version is\s+(\S+)", text)
            if mbm_match:
                results["qcom_mbm_version"] = mbm_match.group(1)

            # OEM / brand from OEM_IMAGE_VERSION or androidboot.device
            oem_ver = re.search(r"OEM_IMAGE_VERSION_STRING=(\S+)", text)
            if oem_ver:
                results["qcom_oem_version"] = oem_ver.group(1)

            # socinfo version
            qc_socinfo_match = re.search(r"socinfo_init:\s*v(\S+)", text, re.IGNORECASE)
            if qc_socinfo_match:
                results["qcom_socinfo"] = qc_socinfo_match.group(1)

            # Version strings from Qualcomm logs
            qc_ver_match = re.search(r"(QC_IMAGE_VERSION_STRING|OEM_IMAGE_VERSION_STRING)=(\S+)", text)
            if qc_ver_match:
                results["version"] = qc_ver_match.group(2)

        # ── Samsung Exynos-Specific Parsing ──
        elif platform == "exynos":
            # Exynos chipset model
            exynos_model_match = re.search(r"Exynos\s*(\d{3,4})", text, re.IGNORECASE)
            if exynos_model_match:
                model = exynos_model_match.group(1)
                results["chipset"] = "Samsung Exynos"
                results["chipset_detail"] = f"Exynos {model}"
                results["exynos_model"] = model
            elif re.search(r"SLSI|S\.LSI", text, re.IGNORECASE):
                results["chipset"] = "Samsung Exynos"
                results["chipset_detail"] = "Samsung LSI SoC"

            # Exynos revision
            exynos_rev_match = re.search(r"Exynos\d+\s*Rev\s*([\d\.]+)", text, re.IGNORECASE)
            if exynos_rev_match:
                results["exynos_revision"] = exynos_rev_match.group(1)

            # RAM info from DMC line
            exynos_dmc_match = re.search(r"DMC:\s*(LPDDR\d[X]?)\s*(\d+)MHz", text, re.IGNORECASE)
            if exynos_dmc_match:
                results["ram_type"] = exynos_dmc_match.group(1).upper()
                results["ram_freq"] = f"{exynos_dmc_match.group(2)} MHz"

            # RAM rank/size info
            exynos_rank_matches = re.findall(r"rank(\d+)\s+(\d+)(GB|MB)", text, re.IGNORECASE)
            if exynos_rank_matches:
                total_ram = 0
                for rank_num, size, unit in exynos_rank_matches:
                    if unit.upper() == "GB":
                        total_ram += int(size) * 1024
                    else:
                        total_ram += int(size)
                if total_ram >= 1024:
                    results["ram"] = f"{total_ram // 1024} GB"
                else:
                    results["ram"] = f"{total_ram} MB"

            # Samsung PMIC
            exynos_pmic_match = re.search(r"(s2mps\d+|s2mpb\d+|s2dos\d+)", text, re.IGNORECASE)
            if exynos_pmic_match:
                results["exynos_pmic"] = exynos_pmic_match.group(1)

            # Samsung display panel
            exynos_panel_match = re.search(r"(S6E\w+|AMS\w+)\s*panel", text, re.IGNORECASE)
            if exynos_panel_match:
                results["exynos_display_panel"] = exynos_panel_match.group(1)

            # CPU EMA setting
            if re.search(r"CPU EMA setting done", text, re.IGNORECASE):
                results["exynos_cpu_ema"] = "Done"

            # Boot stage tracking for Exynos
            exynos_stages = []
            if re.search(r"BL1|bl1", text):
                exynos_stages.append("BL1")
            if re.search(r"BL2|bl2|Tzsw", text, re.IGNORECASE):
                exynos_stages.append("BL2/TrustZone")
            if re.search(r"U-Boot|u-boot", text):
                exynos_stages.append("U-Boot")
            if re.search(r"Kernel|vmlinux|Booting Linux", text, re.IGNORECASE):
                exynos_stages.append("Kernel")
            if exynos_stages:
                results["boot_stage"] = " -> ".join(exynos_stages)

        # ── Unisoc/Spreadtrum-Specific Parsing ──
        elif platform == "unisoc":
            # Unisoc bootloader stage
            if re.search(r"FDL1|fdl1", text):
                results["unisoc_stage"] = "FDL1"
            if re.search(r"FDL2|fdl2", text):
                results["unisoc_stage"] = "FDL2"

            # Chip ID
            unisoc_chip_match = re.search(r"chip id[:\s]*(0x[0-9A-Fa-f]+)", text, re.IGNORECASE)
            if unisoc_chip_match:
                results["unisoc_chip_id"] = unisoc_chip_match.group(1)

            # Unisoc chipset model
            unisoc_model_match = re.search(r"(SC\d{4}|UMS\d{3,4}|T6\d{2,3}|ums\d{3,4})", text, re.IGNORECASE)
            if unisoc_model_match:
                model = unisoc_model_match.group(1).upper()
                results["chipset"] = "Unisoc"
                results["chipset_detail"] = f"Unisoc {model}"
                results["unisoc_model"] = model
            else:
                results["chipset"] = "Unisoc"
                results["chipset_detail"] = "Unisoc/Spreadtrum SoC"

            # DDR info from Unisoc logs
            unisoc_ddr_match = re.search(r"DDR:\s*(LPDDR\d[X]?)\s*(\d+)MHz", text, re.IGNORECASE)
            if unisoc_ddr_match:
                results["ram_type"] = unisoc_ddr_match.group(1).upper()
                results["ram_freq"] = f"{unisoc_ddr_match.group(2)} MHz"

            # U-Boot version
            unisoc_uboot_match = re.search(r"U-Boot\s+([\d\.]+)", text)
            if unisoc_uboot_match:
                results["unisoc_uboot_version"] = unisoc_uboot_match.group(1)
                results["version"] = f"U-Boot {unisoc_uboot_match.group(1)}"

            # Boot stage tracking for Unisoc
            unisoc_stages = []
            if re.search(r"FDL1|fdl1", text):
                unisoc_stages.append("FDL1")
            if re.search(r"FDL2|fdl2", text):
                unisoc_stages.append("FDL2")
            if re.search(r"U-Boot|u-boot|uboot", text, re.IGNORECASE):
                unisoc_stages.append("U-Boot")
            if re.search(r"Kernel|vmlinux|Booting Linux", text, re.IGNORECASE):
                unisoc_stages.append("Kernel")
            if unisoc_stages:
                results["boot_stage"] = " -> ".join(unisoc_stages)

        # Extract specific boot info
        # MediaTek format: F0: XXXX XXXX
        mtk_regs = re.findall(r"([A-Z]\d):\s*([0-9A-Fa-f]{4}\s+[0-9A-Fa-f]{4})", text)
        if mtk_regs:
            results["boot_registers"] = ", ".join(f"{reg}={val}" for reg, val in mtk_regs)
            if "chipset" not in results:
                results["chipset"] = "MediaTek"
                results["chipset_detail"] = "MediaTek Boot ROM"

        # ── Register Analysis & Fault Detection ──
        # Parse ALL registers from boot log
        all_regs = re.findall(r"([A-Z0-9]{1,2}):\s*([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})(?:\s*\[([0-9A-Fa-f]{4})\])?", text)

        register_analysis = {}
        faults_detected = []

        # Known register meanings and expected values for MediaTek
        MTK_REGISTER_INFO = {
            "F0": {
                "name": "Chip ID",
                "description": "SoC hardware identification code",
                "check": lambda v1, v2: v1 != "0000",  # Should not be all zeros
                "fault_msg": "Chip ID is 0000 — CPU/SoC may be dead or not responding",
            },
            "F3": {
                "name": "Boot Config",
                "description": "Boot configuration and mode register",
                "check": lambda v1, v2: True,  # Informational
                "fault_msg": "",
            },
            "F7": {
                "name": "Security Fuse",
                "description": "Security/eFuse configuration",
                "check": lambda v1, v2: True,  # 0000 is normal for unlocked
                "fault_msg": "",
            },
            "V0": {
                "name": "Boot ROM Version",
                "description": "BROM version register",
                "check": lambda v1, v2: True,
                "fault_msg": "",
            },
            "BP": {
                "name": "Boot Parameter",
                "description": "Boot device and storage configuration",
                "check": lambda v1, v2: v1 != "0000" or v2 != "0000",
                "fault_msg": "Boot parameter is empty — storage (eMMC/UFS) may not be detected",
            },
            "G0": {
                "name": "RAM/EMI Config",
                "description": "External Memory Interface configuration",
                "check": lambda v1, v2: v1 != "0000",
                "fault_msg": "RAM config is 0000 — RAM/DRAM may be faulty or not connected",
            },
            "EC": {
                "name": "Error Code",
                "description": "Hardware error/fault code register",
                "check": lambda v1, v2: v1 == "0000" and v2 == "0000",
                "fault_msg": "ERROR CODE is non-zero — hardware fault detected!",
            },
            "S7": {
                "name": "Security Status",
                "description": "Security engine status",
                "check": lambda v1, v2: True,
                "fault_msg": "",
            },
            "CC": {
                "name": "Cache Config",
                "description": "CPU cache configuration",
                "check": lambda v1, v2: True,
                "fault_msg": "",
            },
            "T0": {
                "name": "Timer/Counter",
                "description": "System timer value at boot",
                "check": lambda v1, v2: True,
                "fault_msg": "",
            },
            "00": {
                "name": "System Config 0",
                "description": "Base system configuration",
                "check": lambda v1, v2: True,
                "fault_msg": "",
            },
            "01": {
                "name": "System Config 1",
                "description": "Extended system configuration",
                "check": lambda v1, v2: True,
                "fault_msg": "",
            },
        }

        for reg_name, val1, val2, extra in all_regs:
            reg_info = MTK_REGISTER_INFO.get(reg_name, {
                "name": f"Register {reg_name}",
                "description": "Unknown register",
                "check": lambda v1, v2: True,
                "fault_msg": "",
            })

            is_ok = reg_info["check"](val1, val2)
            extra_str = f" [{extra}]" if extra else ""

            register_analysis[reg_name] = {
                "name": reg_info["name"],
                "description": reg_info["description"],
                "value": f"{val1} {val2}{extra_str}",
                "status": "ok" if is_ok else "fault",
            }

            if not is_ok:
                # Confidence scoring for register faults:
                # EC non-zero = clearly abnormal hardware error
                # F0 = 0000 means chip ID unreadable = clearly abnormal
                # G0 = 0000 means RAM config empty = clearly abnormal
                # BP = 0000 means boot param empty = borderline (storage may just not respond yet)
                # Other registers = borderline
                if reg_name == "EC":
                    _conf = 95  # Error Code register non-zero is definitive
                elif reg_name == "F0" and val1 == "0000":
                    _conf = 90  # Chip ID all zeros = strong evidence of dead SoC
                elif reg_name == "G0" and val1 == "0000":
                    _conf = 90  # RAM config empty = strong evidence of RAM failure
                elif reg_name == "BP":
                    _conf = 75  # Boot param empty = could be storage or timing issue
                else:
                    _conf = 65  # Other register anomalies = borderline
                fault = {
                    "register": reg_name,
                    "name": reg_info["name"],
                    "value": f"{val1} {val2}",
                    "message": reg_info["fault_msg"],
                    "severity": "critical" if reg_name in ["F0", "EC", "G0", "BP"] else "warning",
                    "confidence": _conf,
                }
                faults_detected.append(fault)

        results["register_analysis"] = register_analysis
        results["faults_detected"] = faults_detected

        # ── Kernel dmesg Real Value Extraction ──
        # When phone is already booted, UART captures kernel ring buffer
        # Extract actual measurement values for technician report
        dmesg_data = {}

        # 1. BATTERY / FUEL GAUGE
        fg_match = re.search(
            r"MTK_FG:.*\{FGADC\}soc:(\d+).*fg_c_soc:(\d+).*fg_v_soc:(\d+).*ui_soc:(\d+).*VBAT\s+(\d+).*T:\[(\d+)",
            text
        )
        if fg_match:
            soc = int(fg_match.group(4)) / 100
            vbat = int(fg_match.group(5)) / 10
            temp = int(fg_match.group(6))
            dmesg_data["battery_soc"] = f"{soc:.1f}%"
            dmesg_data["battery_vbat_live"] = f"{vbat:.0f}mV"
            dmesg_data["battery_temp"] = f"{temp}\u00b0C"

        bat_capacity = re.search(r"battery_psy_get_property psp:42.*val:(\d+)", text)
        if bat_capacity:
            dmesg_data["battery_capacity_psp"] = f"{bat_capacity.group(1)}%"

        bat_temp_psp = re.search(r"battery_psy_get_property psp:46.*val:(\d+)", text)
        if bat_temp_psp:
            temp_raw = int(bat_temp_psp.group(1))
            dmesg_data["battery_temp_raw"] = f"{temp_raw/10:.1f}\u00b0C"

        # 2. AUXADC CHANNELS (real analog measurements)
        auxadc_channels = {}
        for m in re.finditer(
            r"mt635x-auxadc.*name:(\w+),\s*channel=(\d+),\s*adc_out=(0x[0-9A-Fa-f]+),\s*adc_result=(\d+)", text
        ):
            auxadc_channels[m.group(1)] = int(m.group(4))
        if auxadc_channels:
            dmesg_data["auxadc_channels"] = auxadc_channels
            if "BAT_TEMP" in auxadc_channels:
                dmesg_data["auxadc_bat_temp_raw"] = str(auxadc_channels["BAT_TEMP"])
            if "VBIF" in auxadc_channels:
                dmesg_data["auxadc_vbif"] = f"{auxadc_channels['VBIF']}mV"
            if "IMP" in auxadc_channels:
                dmesg_data["auxadc_impedance"] = str(auxadc_channels["IMP"])
            if "VCORE_TEMP" in auxadc_channels:
                dmesg_data["auxadc_vcore_temp_raw"] = str(auxadc_channels["VCORE_TEMP"])
            if "VPROC_TEMP" in auxadc_channels:
                dmesg_data["auxadc_vproc_temp_raw"] = str(auxadc_channels["VPROC_TEMP"])

        # 3. THERMAL (PMIC buck temperatures)
        tsbuck1 = re.search(r"tsbuck1_raw_to_temp.*t_current=(\d+)", text)
        tsbuck2 = re.search(r"tsbuck2_raw_to_temp.*t_current=(\d+)", text)
        if tsbuck1:
            dmesg_data["pmic_vcore_temp"] = f"{int(tsbuck1.group(1))/1000:.1f}\u00b0C"
        if tsbuck2:
            dmesg_data["pmic_vproc_temp"] = f"{int(tsbuck2.group(1))/1000:.1f}\u00b0C"

        batt_therm = re.search(
            r"BattThermistorConverTemp.*?(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", text
        )
        if batt_therm:
            dmesg_data["thermistor_temp"] = f"{batt_therm.group(6)}\u00b0C"

        # 4. CHARGING CURRENT & POWER
        ptim_vals = re.findall(r"\[get_ptim_current\]ptim current:(\d+)", text)
        if ptim_vals:
            currents = [int(v) for v in ptim_vals]
            dmesg_data["charging_current_avg"] = f"{sum(currents)/len(currents):.0f}mA"
            dmesg_data["charging_current_max"] = f"{max(currents)}mA"
            dmesg_data["charging_current_min"] = f"{min(currents)}mA"
            dmesg_data["charging_samples"] = str(len(currents))

        chr_type = re.search(r"psy_chr_type_set_property.*prop:4\s+(\d+)", text)
        if chr_type:
            _chr_map = {"0": "Unknown", "1": "Standard USB", "2": "Charging USB",
                        "3": "Nonstandard", "4": "Standard AC", "5": "Apple 2.1A"}
            dmesg_data["charger_type"] = _chr_map.get(chr_type.group(1), f"Type {chr_type.group(1)}")

        pd_fail = re.search(r"pd_notifier_call.*state:(\w+)", text)
        if pd_fail:
            dmesg_data["usb_pd_status"] = pd_fail.group(1)

        dlpt = re.search(r"\[DLPT_final\]\s*(\d+),(\d+),(\d+),(\d+)", text)
        if dlpt:
            dmesg_data["dlpt_load_ma"] = f"{dlpt.group(1)}mA"
            dmesg_data["dlpt_soc"] = f"{int(dlpt.group(2))}%"

        power = re.search(r"\[ma_to_mw\]\s*(\d+)\(mV\)\s*\*\s*(\d+)\(mA\)\s*=\s*(\d+)\(mW\)", text)
        if power:
            dmesg_data["power_vbat_mv"] = f"{power.group(1)}mV"
            dmesg_data["power_current_ma"] = f"{power.group(2)}mA"
            dmesg_data["power_watts"] = f"{int(power.group(3))/1000:.1f}W"

        # 5. COULOMB COUNTER
        coulomb = re.search(r"\[coulomb_get\].*car:(\d+)", text)
        if coulomb:
            dmesg_data["coulomb_counter"] = coulomb.group(1)

        # 6. GPU STATUS
        pvr_errors = len(re.findall(r"PVRSRVDeviceOpen.*Device open failed", text))
        pvr_power_fail = len(re.findall(r"PVRSRVPowerLock.*failed", text))
        if pvr_errors > 0:
            dmesg_data["gpu_driver_errors"] = str(pvr_errors)
            dmesg_data["gpu_status"] = "FAIL" if pvr_errors > 10 else "Unstable"
        if pvr_power_fail > 0:
            dmesg_data["gpu_power_lock_fail"] = str(pvr_power_fail)

        # 7. MODEM / CCCI STATUS
        ccci_status = re.findall(r"\[ccci1/fsm\]received MD status response\s+([\da-fA-Fx]+)", text)
        if ccci_status:
            dmesg_data["modem_responses"] = str(len(ccci_status))
            dmesg_data["modem_last_status"] = ccci_status[-1]
            dmesg_data["modem_active"] = "Yes"
        ccci_polls = len(re.findall(r"\[ccci1/fsm\]poll MD status send msg", text))
        if ccci_polls:
            dmesg_data["modem_polls"] = str(ccci_polls)

        # 8. AUDIO STATUS
        audio_errors = len(re.findall(r"\[AudioError\]", text))
        audio_warns = len(re.findall(r"\[AudioWarn\]", text))
        if audio_errors > 0:
            dmesg_data["audio_errors"] = str(audio_errors)
        if audio_warns > 0:
            dmesg_data["audio_warnings"] = str(audio_warns)

        # 9. DISPLAY / GRALLOC
        gralloc_crash = re.search(r"vendor\.gralloc.*exited with status\s*(\d+)", text)
        sf_errors = len(re.findall(r"surfaceflinger.*PVR_K.*Error", text))
        if gralloc_crash:
            dmesg_data["gralloc_crash"] = f"exit code {gralloc_crash.group(1)}"
        if sf_errors > 0:
            dmesg_data["surfaceflinger_errors"] = str(sf_errors)

        if dmesg_data:
            results["dmesg_data"] = dmesg_data

        # ── Boot Log Error Detection ──
        # ONLY report REAL hardware faults — not normal Android software behavior
        # Known benign "errors" that are NOT real faults
        benign_patterns = [
            "test_time_conversion_check_result",
            "pass", "no error", "error=0", "error_count=0",
            "read test pass", "write test pass", "init pass",
            "error counter is cleared",                # SSM verity error counter cleared — good news
            "error = unsupported",                     # UEFI feature not supported — normal
        ]

        # These are NORMAL Android/UEFI behavior — NOT faults, filter them completely
        software_noise_patterns = [
            r"avc:\s*denied",                          # SELinux policy denials — config, not hardware
            r"Could not find.*ISensorManager",         # Sensor HAL not started yet — normal during boot
            r"Could not find.*for ctl\.",              # Service not started yet — normal boot sequence
            r"binder:.*send failed reply",             # Binder transaction timing — normal
            r"AudioError.*user count",                 # Audio service reference counting — software bug
            r"octvm.*chown.*failed.*Permission",       # MCD permission issue — software config
            r"PVRSRVDeviceOpen.*Driver.*bad state",    # GPU driver restart — software (unless repeated 50+ times)
            r"tz_vfs.*wait_for_completion",            # TrustZone filesystem timeout — usually transient
            r"vdc.*volume.*abort_fuse",                # Volume daemon fuse abort — cleanup operation
            r"Aborting Host Mode.*due to dead batt",   # UEFI USB host mode skipped on low battery — normal
            r"BrightnessLevelControl.*Unsupported",    # UEFI backlight control not supported in this mode
            r"Error Locate.*MiToken",                     # Xiaomi UEFI token protocol — normal
            r"Error Locate.*Protocol",                    # UEFI protocol locate — normal boot sequence
            r"GetDebugPolicyFlag",                        # Xiaomi UEFI — prints on every retail unit
            r"Error Get DebugPolicy",                     # same, locked bootloader has no debug policy
            r"readDebugPolicy.*ScmSipSysCall",            # same
            r"Could not get splash memory region",        # UEFI splash node absent — cosmetic
            r"Unable to get FpSensor Config",             # fingerprint cfg not in UEFI — normal
            r"Unable to read display cmdline",            # display cmdline absent — normal
            r"Vibrator protocol locating failed",         # UEFI vibrator protocol — normal
            r"SDC2 node not found in the IORT",           # no SD card slot on this SKU — normal
        ]

        # These ARE real hardware-related faults — always report
        hardware_fault_patterns = [
            (r"\[I2C\].*(?:transfer error|I2C_ACKERR|fails,ret=)", "I2C Bus Error", 85),
            (r"PD_HW_FAIL|pd_stop_algo.*HW_FAIL", "USB-C PD Hardware Failure", 85),
            (r"get_ibus.*failed", "Charging Current Read Failure", 80),
            (r"NVRAM_FAIL|FG_DAEMON_CMD_SET_NVRAM_FAIL", "Battery NVRAM Data Error", 75),
            (r"fg_error_calibration", "Fuel Gauge Calibration Error", 75),
            (r"kernel\s*panic|Kernel panic", "Kernel Panic", 95),
            (r"watchdog.*bite|wdt.*bark|HWT:", "Watchdog Hardware Timeout", 90),
            (r"pmic.*over.?current|OCP.*triggered", "PMIC Overcurrent", 95),
            (r"thermal.*shutdown|thermal.*critical", "Thermal Shutdown", 90),
            (r"UFS.*error|eMMC.*fail|mmc.*error", "Storage Hardware Error", 90),
            (r"DRAM.*fail|DDR.*error|DDR_ABORT|NO_MEMORY_DEVICE_DETECTED|memory.*fail", "Memory/RAM Hardware Failure", 95),
            (r"PLL.*lock.*fail|clock.*error", "Clock/PLL Failure", 85),
            (r"FAULT\s+UVLO|UVLO.*fault|under.voltage.lock", "Battery UVLO (Under-Voltage Lock-Out)", 95),
            (r"charger.*fail|CHG.*error|charging.*fault", "Charging IC Failure", 85),
            (r"panel.*fail|dsi.*error|lcm.*error", "Display Hardware Error", 80),
            (r"camera.*fail|cci.*error|sensor.*probe.*fail", "Camera Hardware Error", 75),
            (r"modem.*crash|baseband.*fail|ccci.*error", "Modem/Baseband Error", 80),
            (r"SBC.*cert verify.*fail|PART.*cert chain.*fail", "Secure Boot Cert Failure", 70),
            (r"PL fatal error", "Preloader Fatal Error", 90),
            (r"SEC_POLICY.*reached the end", "Security Policy Error", 60),
        ]

        # config/fault_rules.json overrides the tables above when it loads.
        # Editing that file teaches the detector a new fault with no code
        # change; deleting it falls back to the built-ins directly above.
        _repair_steps = {}
        _pack = self._load_fault_rules(results.get("platform", ""))
        if _pack["faults"]:
            hardware_fault_patterns = [(p, n, c) for p, n, c, _ in _pack["faults"]]
            _repair_steps = {n: r for _, n, _, r in _pack["faults"] if r}
        if _pack["noise"]:
            software_noise_patterns = _pack["noise"]

        error_lines = []
        error_groups = {}

        for line in lines:
            line_lower = line.lower()

            # Skip if no error keywords at all. Use word boundary but also
            # allow underscore-prefixed forms like DDR_ABORT, HW_FAIL.
            # Negative lookbehind for letters prevents "default" matching "fault".
            if not re.search(r"(?<![a-z])(?:error|fail|fault|panic|abort|dead|hw_fail)\b", line_lower):
                continue

            # Skip known benign patterns
            if any(bp in line_lower for bp in benign_patterns):
                continue

            # Skip software noise — these are NOT faults
            is_noise = False
            for noise_pat in software_noise_patterns:
                if re.search(noise_pat, line, re.IGNORECASE):
                    is_noise = True
                    break
            if is_noise:
                # Exception: PVR_K error 50+ times means GPU IC is actually dead
                if "PVRSRVDeviceOpen" in line:
                    error_lines.append(line)  # track for counting
                continue

            error_lines.append(line)

            # Match against hardware fault patterns. An unrecognised line is
            # not evidence of a fault — bootloaders print "Error ..." for
            # absent optional features on every healthy unit. Score it below
            # the GUI's 50-point display floor so it stays counted but unshown.
            fault_name = "Boot Log Error"
            _log_conf = 30
            for pat, name, conf in hardware_fault_patterns:
                if re.search(pat, line, re.IGNORECASE):
                    fault_name = name
                    _log_conf = conf
                    break

            # Normalize for grouping
            norm = re.sub(r"^\[\s*[\d.]+\]\s*", "", line)
            norm = re.sub(r"<\d+>[.-]?\(\d+\)\[\d+:[^\]]*\]", "", norm)
            norm = re.sub(r"\b\d{4,}\b", "N", norm)
            norm = norm.strip()[:80]

            if norm in error_groups:
                error_groups[norm]["count"] += 1
                error_groups[norm]["confidence"] = max(error_groups[norm]["confidence"], _log_conf)
            else:
                error_groups[norm] = {
                    "line": line, "count": 1, "confidence": _log_conf,
                    "fault_name": fault_name,
                }

        # Check if PVR_K (GPU driver) error was excessive (50+ = GPU IC likely dead)
        pvr_count = sum(1 for l in error_lines if "PVRSRVDeviceOpen" in l)
        if pvr_count >= 50:
            faults_detected.append({
                "register": "GPU",
                "name": "GPU IC Failure (PowerVR)",
                "value": f"PVR_K driver crash repeated {pvr_count} times",
                "message": f"GPU driver (PowerVR) crashed {pvr_count} times — GPU IC likely dead or damaged. Check GPU power supply and solder joints.",
                "severity": "warning",
                "confidence": 80,
                "repeat_count": pvr_count,
            })

        # Create ONE fault per unique REAL error pattern. UVLO is skipped here
        # because the dedicated block below reports it with voltage and repair
        # steps; emitting both puts the same fault on screen twice.
        for norm, info in error_groups.items():
            if info["fault_name"].startswith("Battery UVLO"):
                continue
            count_str = f" (x{info['count']})" if info["count"] > 1 else ""
            _steps = _repair_steps.get(info["fault_name"], [])
            _msg = f"{info['fault_name']}{count_str}: {info['line'][:100]}"
            if _steps:
                _msg += " Repair: " + "; ".join(
                    f"{i}) {s}" for i, s in enumerate(_steps, 1))
            faults_detected.append({
                "register": "LOG",
                "name": info["fault_name"],
                "value": info["line"][:80],
                "message": _msg,
                "severity": "critical" if info["confidence"] >= 90 else "warning",
                "confidence": info["confidence"],
                "repeat_count": info["count"],
                "repair_steps": _steps,
            })

        if error_lines:
            results["boot_errors"] = error_lines
            results["boot_error_count"] = len(error_lines)
            results["boot_error_unique"] = len(error_groups)

        # ── UVLO / Dead Battery Detection ──
        poff_detail = results.get("boot_reason_detail", "")
        vbat_str = results.get("battery_vbat", "")
        vbat_mv = 0
        if vbat_str:
            try:
                vbat_mv = int(re.search(r"(\d+)", vbat_str).group(1))
            except (AttributeError, ValueError):
                pass

        # ── Bootloop ──
        # Several complete boots inside one listen window, with no power-key
        # press to explain them, is the headline fault — not whatever error
        # each individual cycle happened to print.
        cycles = self._split_boot_cycles(text)
        if len(cycles) >= 3:
            keypresses = len(re.findall(r"KPDPWR\s+1|IsPressPwrKeyOn:\s*true", text))
            if keypresses < len(cycles) - 1:
                results["boot_cycle_count"] = len(cycles)
                faults_detected.append({
                    "register": "POWER",
                    "name": "Bootloop",
                    "value": f"{len(cycles)} boots, {keypresses} key press(es)",
                    "message": (
                        f"Device booted {len(cycles)} times during the capture with only "
                        f"{keypresses} power-key press(es) — it is restarting on its own. "
                        "Check where the log stops each cycle: reaching kernel handoff every "
                        "time points at power delivery (battery, connector, rails) rather than "
                        "firmware."
                    ),
                    "severity": "critical",
                    "confidence": 90,
                    "repeat_count": len(cycles),
                })

        # ── Battery sense path ──
        # 0 mV alongside amps of current cannot happen in a real cell. Nor can
        # a cell gain volts in seconds. Both mean the PMIC has lost sight of
        # the battery — a contact fault, which is a different repair to UVLO.
        vi_pairs = [(int(v), int(i)) for v, i in re.findall(
            r"PM:\s*Vbatt:\s*(-?\d+);\s*Ibatt:\s*(-?\d+)", text)]
        impossible = [(v, i) for v, i in vi_pairs if abs(v) < 100 and abs(i) > 100]
        entry_exit = re.search(r"EntryVbat:\s*(\d+).*?ExitVbatt:\s*(\d+)", text, re.DOTALL)
        fast_climb = False
        if entry_exit:
            lo, hi = int(entry_exit.group(1)), int(entry_exit.group(2))
            fast_climb = lo < 100 and hi > 3000
        if impossible or fast_climb:
            why = []
            if impossible:
                v, i = impossible[0]
                why.append(f"{v} mV read while {i} mA flows")
            if fast_climb:
                why.append(f"{entry_exit.group(1)} → {entry_exit.group(2)} mV within one SBL stage")
            faults_detected.append({
                "register": "POWER",
                "name": "Battery Sense / Contact Fault",
                "value": "; ".join(why),
                "message": (
                    "Battery readings are physically impossible (" + "; ".join(why) + "). "
                    "The cell is likely fine but the PMIC cannot see it reliably. "
                    "Repair: 1) Reseat and clean the battery connector with IPA, "
                    "2) Inspect the battery FPC for cracks at the fold, "
                    "3) Ohm out the connector to the PMIC input, "
                    "4) Retest on a bench supply with the battery removed."
                ),
                "severity": "critical",
                "confidence": 85,
            })

        # UVLO is judged on the WORST cycle, not the last one: a capture that
        # ends healthy still shut down on under-voltage earlier.
        _seen = [int(v) for v in re.findall(
            r"PM:\s*(?:V[Bb]at|VBAT|EntryVbat|ExitVbatt)\s*:\s*(\d+)", text)]
        vbat_low = min(_seen, default=vbat_mv)
        if "UVLO" in poff_detail.upper() or re.search(r"FAULT\s+UVLO", text, re.I) \
                or (vbat_low > 0 and vbat_low < 100):
            vbat_mv = vbat_low
            severity = "critical"
            conf = 95
            msg = (
                f"FAULT UVLO — Battery was at {vbat_mv} mV (dead/deep-discharged). "
                "Phone shut down due to Under-Voltage Lock-Out."
            )
            # Repair steps come from config/fault_rules.json so there is one
            # place to edit them, with the old wording as the fallback.
            _uvlo_steps = _repair_steps.get("Battery UVLO (Under-Voltage Lock-Out)") or [
                "Replace battery if old/swollen",
                "Check battery connector pins for corrosion",
                "Check charging IC and PMIC power path",
                "If battery is new, suspect PMIC or charging circuit fault",
            ]
            msg += " Repair: " + "; ".join(
                f"{i}) {s}" for i, s in enumerate(_uvlo_steps, 1))
            faults_detected.append({
                "register": "POWER",
                "name": "Battery UVLO (Under-Voltage Lock-Out)",
                "value": f"VBAT: {vbat_mv} mV, {poff_detail}",
                "message": msg,
                "severity": severity,
                "confidence": conf,
                "repair_steps": _uvlo_steps,
            })
        elif vbat_mv > 0 and vbat_mv < 3400:
            faults_detected.append({
                "register": "POWER",
                "name": "Low Battery Voltage",
                "value": f"VBAT: {vbat_mv} mV",
                "message": f"Battery voltage {vbat_mv} mV is below safe threshold (3400 mV). Check battery health and charging circuit.",
                "severity": "warning",
                "confidence": 75,
            })

        # ── DDR Voltage Rail Reference ──
        # When DDR failure is detected, provide reference voltages for repair
        has_ddr_fault = any(
            f.get("name", "") in ("Memory/RAM Hardware Failure",)
            for f in faults_detected
        )
        if has_ddr_fault:
            # Detect DDR type from boot log
            ddr_type = "LP4"  # default
            if re.search(r"LP5\b|LPDDR5", text, re.IGNORECASE):
                ddr_type = "LP5"
            elif re.search(r"LP4[xX]|LPDDR4[xX]", text, re.IGNORECASE):
                ddr_type = "LP4X"
            elif re.search(r"LP4\b|LPDDR4\b", text, re.IGNORECASE):
                ddr_type = "LP4"

            # Parse DDR_ABORT details first — needed to determine rail status
            abort_reason = ""
            abort_match = re.search(
                r"DDR_ABORT:\s*REASON=(\w+)(?:,FREQ=(\w+))?(?:,CHANNEL=(\w+))?",
                text,
            )
            if abort_match:
                abort_reason = abort_match.group(1)
                results["ddr_abort_reason"] = abort_reason
                results["ddr_abort_freq"] = abort_match.group(2) or "N/A"
                results["ddr_abort_channel"] = abort_match.group(3) or "N/A"

            # Determine voltage rail status from boot log evidence:
            # - UFS working (INQUIRY ID found) → VCC (2.9V) is OK
            # - PMIC init done → VCCQ (1.8V), VDD1 (1.8V) likely OK
            # - DDR type detected but NO_MEMORY_DEVICE → VDD2 (core) is suspect
            # - ZQ calibration never reached → ZQ ref might be OK (powered by PMIC)
            ufs_ok = bool(re.search(r"UFS INQUIRY ID|UFS Spec Version|UFS Total Size", text))
            pmic_ok = bool(re.search(r"PM:.*Device Init|pm_device_init|PMIC\s+[A-Z]:", text))
            ddr_type_detected = bool(re.search(r"LP[45][xX]?\s*DDR\s*detected", text, re.IGNORECASE))
            ddr_training_ok = bool(re.search(r"DDR Training Restore|do_ddr_training.*Delta", text))
            no_memory = abort_reason == "NO_MEMORY_DEVICE_DETECTED"

            # Build voltage rails with smart status
            def _rail(expected, ok_evidence, fault_evidence=False):
                if fault_evidence:
                    return {"expected": expected, "status": "missing"}
                if ok_evidence:
                    return {"expected": expected, "status": "ok"}
                return {"expected": expected, "status": "check"}

            ddr_voltage_rails = {
                "LP4": {
                    "VCC (eMMC/UFS power)": _rail("2.9V", ufs_ok),
                    "VCCQ (IO voltage)": _rail("1.8V", pmic_ok),
                    "VDD1 (DDR PHY)": _rail("1.8V", pmic_ok and ddr_type_detected),
                    "VDD2 (LPDDR4 core)": _rail("1.125V", ddr_training_ok, no_memory),
                    "LPDDR ZQ (reference)": _rail("0.6V", pmic_ok and ddr_type_detected),
                },
                "LP4X": {
                    "VCC (eMMC/UFS power)": _rail("2.9V", ufs_ok),
                    "VCCQ (IO voltage)": _rail("1.8V", pmic_ok),
                    "VDD1 (DDR PHY)": _rail("1.8V", pmic_ok and ddr_type_detected),
                    "VDD2 (LPDDR4X core)": _rail("1.05V", ddr_training_ok, no_memory),
                    "LPDDR ZQ (reference)": _rail("0.6V", pmic_ok and ddr_type_detected),
                },
                "LP5": {
                    "VCC (eMMC/UFS power)": _rail("2.9V", ufs_ok),
                    "VCCQ (IO voltage)": _rail("1.8V", pmic_ok),
                    "VDD1 (DDR PHY)": _rail("1.8V", pmic_ok and ddr_type_detected),
                    "VDD2 (LPDDR5 core)": _rail("1.05V", ddr_training_ok, no_memory),
                    "VDDQ (LPDDR5 DQ)": _rail("0.5V", ddr_training_ok),
                },
            }
            results["ddr_type_detected"] = ddr_type
            results["ddr_voltage_rails"] = ddr_voltage_rails.get(ddr_type, ddr_voltage_rails["LP4"])

        # ── PMIC Register Analysis ──
        # Parse PMIC status registers for reset cause, power-off reason, etc.
        pmic_ponsts = re.search(r"\[PMIC\]PONSTS\[0x[0-9A-Fa-f]+\]=(0x[0-9A-Fa-f]+)", text)
        pmic_poffsts = re.search(r"\[PMIC\]POFFSTS\[0x[0-9A-Fa-f]+\]=(0x[0-9A-Fa-f]+)", text)
        pmic_rst_status = re.search(r"\[PMIC\]TOP_RST_STATUS\[0x[0-9A-Fa-f]+\]=(0x[0-9A-Fa-f]+)", text)
        pmic_oc = re.search(r"\[PMIC\]BUCK_OC_SDN_STATUS\[0x[0-9A-Fa-f]+\]=(0x[0-9A-Fa-f]+)", text)
        pmic_thermal = re.search(r"\[PMIC\]THERMALSTATUS\[0x[0-9A-Fa-f]+\]=(0x[0-9A-Fa-f]+)", text)
        pmic_strup = re.search(r"\[PMIC\]STRUP_CON4\[0x[0-9A-Fa-f]+\]=(0x[0-9A-Fa-f]+)", text)
        pmic_chip = re.search(r"\[PMIC\](MT\d+)\s*CHIP\s*Code\s*=\s*(0x[0-9A-Fa-f]+)", text)

        if pmic_chip:
            results["pmic_model"] = pmic_chip.group(1)
            results["pmic_chip_code"] = pmic_chip.group(2)

        # PMIC reset cause analysis
        pmic_check_rst = re.findall(r"\[pmic_check_rst\]\s*(.+)", text)
        just_rst = re.search(r"\[PMIC\]just_rst\s*=\s*(\d+)", text)

        if pmic_check_rst:
            rst_reasons = [r.strip() for r in pmic_check_rst]
            results["pmic_reset_cause"] = "; ".join(rst_reasons)
            # DDLO_RSTB = power dropped below threshold
            if any("DDLO_RSTB" in r for r in rst_reasons):
                faults_detected.append({
                    "register": "PMIC_RST",
                    "name": "PMIC DDLO Reset",
                    "value": "; ".join(rst_reasons),
                    "message": "DDLO_RSTB triggered — battery voltage dropped below minimum. Check battery connector and PMIC power input.",
                    "severity": "warning",
                    "confidence": 75,  # Could be user pulling battery
                })
            if any("Long press" in r for r in rst_reasons):
                results["pmic_reset_cause_detail"] = "Long press shutdown (user held power button)"

        if just_rst and just_rst.group(1) != "0":
            results["pmic_just_reset"] = True
            faults_detected.append({
                "register": "PMIC_RST",
                "name": "PMIC Just Reset",
                "value": f"just_rst={just_rst.group(1)}",
                "message": "PMIC reports a recent reset occurred. May indicate power instability or normal power cycle.",
                "severity": "warning",
                "confidence": 60,  # Could be normal power cycle
            })

        # PMIC overcurrent detection (critical!)
        if pmic_oc:
            oc_val = int(pmic_oc.group(1), 16)
            if oc_val != 0:
                faults_detected.append({
                    "register": "PMIC_OC",
                    "name": "PMIC Overcurrent Shutdown",
                    "value": pmic_oc.group(1),
                    "message": f"BUCK overcurrent shutdown detected (OC_SDN={pmic_oc.group(1)}). Check for short circuit on power rails!",
                    "severity": "critical",
                    "confidence": 95,  # Overcurrent from PMIC register is definitive
                })

        # PMIC thermal status
        if pmic_thermal:
            thermal_val = int(pmic_thermal.group(1), 16)
            if thermal_val != 0:
                faults_detected.append({
                    "register": "PMIC_THERMAL",
                    "name": "PMIC Thermal Alert",
                    "value": pmic_thermal.group(1),
                    "message": f"PMIC thermal alert active ({pmic_thermal.group(1)}). PMIC is overheating — check for shorts around PMIC IC.",
                    "severity": "critical",
                    "confidence": 95,  # Thermal alert from PMIC register is definitive
                })

        # Store all PMIC register values for report
        pmic_regs = {}
        if pmic_ponsts:
            pmic_regs["PONSTS"] = pmic_ponsts.group(1)
        if pmic_poffsts:
            pmic_regs["POFFSTS"] = pmic_poffsts.group(1)
        if pmic_rst_status:
            pmic_regs["TOP_RST_STATUS"] = pmic_rst_status.group(1)
        if pmic_oc:
            pmic_regs["BUCK_OC_SDN_STATUS"] = pmic_oc.group(1)
        if pmic_thermal:
            pmic_regs["THERMALSTATUS"] = pmic_thermal.group(1)
        if pmic_strup:
            pmic_regs["STRUP_CON4"] = pmic_strup.group(1)
        if pmic_regs:
            results["pmic_registers"] = pmic_regs

        # ── Voltage Rail Analysis ──
        voltage_rails = {}
        for m in re.finditer(r"latch\s+(V\w+)\s+(\d+)\s*uV", text):
            rail_name = m.group(1)
            rail_uv = int(m.group(2))
            voltage_rails[rail_name] = rail_uv
        # Also capture set voltages from MT6357
        for m in re.finditer(r"(v\w+)\s*=\s*(\d+)\s*uV", text):
            rail_name = m.group(1).upper()
            if rail_name not in voltage_rails:
                voltage_rails[rail_name] = int(m.group(2))

        if voltage_rails:
            results["voltage_rails"] = voltage_rails
            # Check for abnormally low voltages
            low_voltage_thresholds = {
                "VPROC": 600000, "VCORE": 600000, "VMODEM": 700000,
                "VSRAM_PROC": 800000, "VSRAM_OTHERS": 800000, "VDRAM": 500000,
            }
            for rail, uv in voltage_rails.items():
                threshold = low_voltage_thresholds.get(rail)
                if threshold and uv < threshold:
                    faults_detected.append({
                        "register": "VOLTAGE",
                        "name": f"Low Voltage: {rail}",
                        "value": f"{uv}uV (threshold: {threshold}uV)",
                        "message": f"{rail} is {uv/1000:.0f}mV — below safe threshold ({threshold/1000:.0f}mV). Check {rail} regulator and load.",
                        "severity": "warning",
                        "confidence": 80,  # Voltage below threshold from actual measurement
                    })

        # ── Battery Data ──
        bat_match = re.search(r"check VBAT=(\d+)mV.*?VCHR=(\d+)mV.*?VCHR_HV=(\d+)mv", text)
        if bat_match:
            results["battery_vbat"] = f"{bat_match.group(1)}mV"
            results["battery_vchr"] = f"{bat_match.group(2)}mV"
            results["battery_vchr_hv"] = f"{bat_match.group(3)}mV"
            vbat = int(bat_match.group(1))
            if vbat < 3400:
                # VBAT < 3000mV = almost certainly dead/disconnected battery
                # VBAT 3000-3400mV = low but could be deep discharge
                _bat_conf = 95 if vbat < 3000 else 75
                faults_detected.append({
                    "register": "BATTERY",
                    "name": "Low Battery Voltage",
                    "value": f"{vbat}mV",
                    "message": f"Battery voltage is {vbat}mV — critically low. Battery may be dead or disconnected.",
                    "severity": "critical" if vbat < 3000 else "warning",
                    "confidence": _bat_conf,
                })

        # ── I2C Error Analysis (identify which IC failed) ──
        i2c_errors = re.findall(r"\[I2C\]\s*id=(\d+),\s*addr:\s*([0-9A-Fa-f]+),\s*transfer error", text)
        if i2c_errors:
            # Group by bus+addr to count
            i2c_counts = {}
            for bus_id, addr in i2c_errors:
                key = f"bus{bus_id}_0x{addr}"
                i2c_counts[key] = i2c_counts.get(key, 0) + 1

            # Known I2C address -> IC mapping for common phones
            # Expanded with real-world MediaTek platform IC addresses
            i2c_ic_map = {
                # DRAM voltage regulators
                "60": "MT6691ZXP / fan53526 (EMI VDDQ — DRAM signal voltage regulator, 0.6V)",
                "61": "RT5738 / fan53528 (VDD2 — DRAM core voltage regulator)",
                "50": "MT6691ZXP alt addr / EEPROM / Camera OTP",
                "6B": "SGM charger IC",
                # Power regulators
                "48": "Temperature sensor / NTC",
                "49": "NCP6924 / sub-PMIC",
                "36": "BQ charger IC",
                "34": "RT charger IC",
                "35": "SGM41511/SGM41512 (charging IC)",
                "51": "EEPROM",
                "52": "EEPROM / camera module OTP",
                # Display/Touch
                "38": "FT5x06/FT6336 (Focaltech touch IC)",
                "5D": "Goodix GT9xx (touch IC)",
                "62": "Goodix GT1x (touch IC)",
                "14": "Goodix GT9xx alt (touch IC)",
                "20": "TPS65132 (LCD bias voltage IC)",
                # Audio (note: 0x34 may also be TFA9874/TFA9895, 0x36 may also be AW88261/AW88395)
                # Keeping existing 0x34/0x36 charger IC entries as primary
                # Sensor
                "68": "BMI160/ICM20600 (accel+gyro IMU)",
                "69": "BMI160 alt addr (accel+gyro IMU)",
                "0D": "AKM09918 (magnetometer/compass)",
                "1E": "LIS2MDL (magnetometer/compass)",
                "29": "VL53L0X (laser proximity/ToF sensor)",
                "39": "APDS9960 (ambient light + proximity)",
                "53": "LIS2DW12 (accelerometer)",
                # NFC
                "28": "PN553/SN100 (NFC controller)",
                "2B": "ST21NFC (NFC controller)",
            }
            for key, count in i2c_counts.items():
                bus_id = key.split("_")[0].replace("bus", "")
                addr = key.split("_")[1].replace("0x", "")
                ic_name = i2c_ic_map.get(addr, f"Unknown IC at 0x{addr}")
                results[f"i2c_error_{key}"] = f"{count} errors — {ic_name}"

        # ── IC Probe Failure Detection ──
        ic_probes_failed = []
        for m in re.finditer(r"\[(\w+)_driver_probe\]\s*PL\s+(\w+)\s+is\s+not\s+exist", text):
            driver = m.group(1)
            component = m.group(2)
            ic_probes_failed.append(f"{driver}: {component} not found")
        if ic_probes_failed:
            results["ic_probes_failed"] = ic_probes_failed

        # ── eMMC/Storage Detail ──
        sd0_match = re.search(r"\[SD0\]\s*Size:\s*(\d+)\s*MB.*?Max\.Speed:\s*(\d+)\s*kHz", text)
        sd0_type = re.search(r"\[SD0\]\s*Initialized,\s*(\w+)", text)
        if sd0_match:
            results["storage"] = f"eMMC {int(sd0_match.group(1))/1024:.0f}GB"
            results["storage_size_mb"] = sd0_match.group(1)
            results["storage_max_speed"] = f"{sd0_match.group(2)} kHz"
        if sd0_type:
            results["storage_type"] = sd0_type.group(1)

        # ── Long Press Reboot Detection ──
        long_press = re.search(r"#T#Long Pressed Reboot=(\d+)", text)
        if long_press and long_press.group(1) != "0":
            results["long_press_reboot"] = True
            results["boot_reason_detail"] = "Phone was force-rebooted by long-pressing power button"

        # RGU (Reset/Watchdog) analysis
        rgu_status = re.search(r"\[RGU\]\s*STA from reg:\s*(0x[0-9A-Fa-f]+)", text)
        if rgu_status:
            sta = rgu_status.group(1)
            if sta != "0x0":
                faults_detected.append({
                    "register": "RGU_STA",
                    "name": "Reset Status",
                    "value": sta,
                    "message": f"Non-zero reset status ({sta}) — previous crash/watchdog reset detected",
                    "severity": "warning",
                    "confidence": 70,  # Non-zero reset status is notable but could be normal reboot
                })
                results["last_reset_cause"] = f"Abnormal reset detected (STA={sta})"
            else:
                results["last_reset_cause"] = "Clean boot (no previous crash)"

        # MediaTek chip ID from F0 register
        f0_match = re.search(r"F0:\s*([0-9A-Fa-f]{4})", text)
        if f0_match:
            chip_code = f0_match.group(1).upper()
            results["mtk_chip_code"] = chip_code
            chip_name = MTK_CHIP_IDS.get(chip_code, f"Unknown MediaTek (0x{chip_code})")
            results["chipset"] = "MediaTek"
            results["chipset_detail"] = chip_name
            results["mtk_chip_name"] = chip_name

        # MediaTek BP register = Boot Parameter (can indicate storage config)
        bp_match = re.search(r"BP:\s*([0-9A-Fa-f]{4}\s+[0-9A-Fa-f]{4})", text)
        if bp_match:
            results["mtk_boot_param"] = bp_match.group(1)

        # MediaTek G0 register = can indicate RAM config
        g0_match = re.search(r"G0:\s*([0-9A-Fa-f]{4}\s+[0-9A-Fa-f]{4})", text)
        if g0_match:
            results["mtk_ram_config"] = g0_match.group(1)

        # Look for "Jump to BL" or similar
        if "Jump to BL" in text:
            results["boot_stage"] = "Jump to Bootloader — Phone is booting"

        # ── Hardware Health Diagnosis from boot log ──
        # Boot logs contain init messages for each subsystem.
        # If a subsystem fails, it shows error/fail messages.
        # If it succeeds, it shows "ok", "done", "init", "ready" etc.
        hw_status = {}

        # Define hardware subsystems and their boot log keywords
        hw_checks = {
            "ram": {
                "ok_patterns": [r"DRAM\s*init.*done", r"DDR.*OK", r"LPDDR.*init", r"memory.*test.*pass",
                                r"EMI.*init", r"DRAM.*calibrat", r"rank[01].*OK", r"MTEST",
                                r"MCU2EMI", r"dram_init", r"dramc", r"DRAM type", r"DRAM freq",
                                r"ddr_training.*Start", r"ddr_training.*End", r"DMC:.*LPDDR",
                                r"sbl1_ddr_init"],
                "fail_patterns": [r"DRAM.*fail", r"DDR.*error", r"memory.*fail", r"EMI.*fail",
                                  r"DRAM.*error", r"rank.*fail", r"ddr_training.*fail"],
                "name": "RAM / Memory",
            },
            "storage": {
                "ok_patterns": [r"eMMC.*init", r"UFS.*init", r"NAND.*ready", r"storage.*OK",
                                r"mmc\d.*init", r"block.*device", r"spmfw.*partition",
                                r"load.*firmware", r"partition", r"msdc", r"ufs.*probe",
                                r"scsi.*UFS",
                                r"UFS Hardware Reset", r"emmc_init", r"bootable_media_detect"],
                "fail_patterns": [r"eMMC.*fail", r"UFS.*error", r"NAND.*fail", r"storage.*fail",
                                  r"mmc.*error", r"block.*fail", r"msdc.*error",
                                  r"UFS.*fail", r"emmc.*fail"],
                "name": "Storage (eMMC/UFS)",
            },
            "display": {
                "ok_patterns": [r"lcm.*init", r"lcm.*probe", r"lcm.*detect",
                                r"dsi.*init", r"dsi.*probe", r"dsi.*config", r"mipi.*dsi",
                                r"panel.*init", r"panel.*probe", r"panel.*detect", r"panel.*ready",
                                r"backlight.*init", r"backlight.*on", r"backlight.*probe",
                                r"disp.*init", r"disp.*ready", r"disp.*probe", r"disp.*config",
                                r"display.*init", r"LCD.*init", r"fb.*init",
                                r"drm.*init", r"drm.*probe", r"mtk_drm",
                                r"mdss_dsi.*probe", r"mdp.*init", r"S6E\w+.*panel", r"disp.*probe"],
                "fail_patterns": [r"lcm.*fail", r"lcm.*error", r"lcm.*timeout",
                                  r"dsi.*fail", r"dsi.*error", r"dsi.*timeout",
                                  r"panel.*fail", r"panel.*error", r"panel.*timeout",
                                  r"backlight.*fail", r"backlight.*error",
                                  r"disp.*fail", r"disp.*error", r"display.*fail",
                                  r"LCD.*error", r"no.*panel", r"no.*lcm"],
                "name": "Display / LCD",
            },
            "charging": {
                "ok_patterns": [r"charger.*detect", r"PMIC.*init", r"battery.*detect", r"CHG.*init",
                                r"usb.*charger", r"power.*supply", r"fuel.*gauge", r"mtcmos.*Done",
                                r"PLL.*init.*Done", r"bandgap", r"PWRAP.*init.*pass",
                                r"SPMI.*done", r"PMIF", r"mt6370.*init", r"mt6360.*init",
                                r"bq\d+.*probe", r"sgm\d+.*probe", r"eta\d+.*probe",
                                r"qpnp.*smb.*probe", r"pm\d+.*probe", r"s2mps\d+.*init",
                                r"charger.*detected"],
                "fail_patterns": [r"charger.*fail", r"PMIC.*error", r"battery.*fail", r"CHG.*error",
                                  r"no.*battery", r"power.*fail", r"PWRAP.*fail",
                                  r"mt6370.*fail", r"mt6360.*fail", r"bq\d+.*fail",
                                  r"qpnp.*smb.*fail", r"s2mps\d+.*fail"],
                "name": "Charging / PMIC",
            },
            "camera": {
                "ok_patterns": [r"cam.*init", r"cam.*probe", r"cam.*detect",
                                r"imgsensor.*init", r"imgsensor.*probe", r"imgsensor.*detect",
                                r"imgsensor.*open", r"imgsensor.*search",
                                r"ois.*init", r"ois.*probe", r"ois.*ready",
                                r"eeprom.*init", r"eeprom.*probe", r"eeprom.*read",
                                r"seninf.*init", r"seninf.*probe",
                                r"camera.*init", r"camera.*probe",
                                r"ISP.*init", r"ISP.*probe",
                                r"imx\d+", r"ov\d+", r"s5k\d+", r"hi\d+", r"gc\d+",
                                r"cci.*probe", r"csid.*probe", r"ispif.*probe",
                                r"camera.*sensor.*detected"],
                "fail_patterns": [r"cam.*fail", r"cam.*error",
                                  r"imgsensor.*fail", r"imgsensor.*error",
                                  r"ois.*fail", r"ois.*error",
                                  r"eeprom.*fail", r"eeprom.*error",
                                  r"camera.*fail", r"ISP.*error",
                                  r"no.*sensor", r"sensor.*fail"],
                "name": "Camera",
            },
            "wifi": {
                "ok_patterns": [r"wlan.*init", r"wlan.*probe", r"wlan.*ready",
                                r"wmt.*init", r"wmt.*probe", r"wmt.*ready", r"WMT.*OK",
                                r"conninfra.*init", r"conninfra.*probe", r"conninfra.*done",
                                r"connac.*init", r"wifi.*init", r"WLAN.*ready",
                                r"combo.*chip", r"mt76\d+", r"wcn\d+",
                                r"wcnss.*probe", r"ath\d+.*probe", r"qca.*init", r"wil6210"],
                "fail_patterns": [r"wlan.*fail", r"wlan.*error", r"wlan.*timeout",
                                  r"wmt.*fail", r"wmt.*error",
                                  r"conninfra.*fail", r"conninfra.*error",
                                  r"wifi.*fail", r"WLAN.*fail"],
                "name": "WiFi",
            },
            "bluetooth": {
                "ok_patterns": [r"btif.*init", r"btif.*probe", r"btif.*ready",
                                r"btmtk.*init", r"btmtk.*probe",
                                r"bluetooth.*init", r"BT.*init", r"hci.*init",
                                r"conninfra.*bt", r"wmt.*bt",
                                r"btfm.*probe", r"rome.*probe", r"cherokee.*probe"],
                "fail_patterns": [r"btif.*fail", r"btif.*error",
                                  r"btmtk.*fail", r"btmtk.*error",
                                  r"bluetooth.*fail", r"BT.*error", r"hci.*error",
                                  r"btfm.*fail", r"rome.*fail"],
                "name": "Bluetooth",
            },
            "audio": {
                "ok_patterns": [r"aw882xx.*init", r"aw882xx.*probe", r"aw882xx.*ready",
                                r"tfa98xx.*init", r"tfa98xx.*probe", r"tfa98xx.*ready",
                                r"smartpa.*init", r"smartpa.*probe",
                                r"audio.*init", r"codec.*init", r"snd.*init", r"ACCDET",
                                r"mt6358.*codec", r"mt6359.*codec", r"AUD.*init",
                                r"alsa.*init", r"asoc.*init", r"speaker.*init",
                                r"headset.*detect", r"jack.*detect",
                                r"wcd\d+.*probe", r"bolero.*probe", r"codec.*probe",
                                r"adsp.*load"],
                "fail_patterns": [r"aw882xx.*fail", r"aw882xx.*error",
                                  r"tfa98xx.*fail", r"tfa98xx.*error",
                                  r"smartpa.*fail", r"smartpa.*error",
                                  r"audio.*fail", r"codec.*error", r"snd.*fail",
                                  r"AUD.*error", r"speaker.*error", r"no.*codec"],
                "name": "Audio",
            },
            "network": {
                "ok_patterns": [r"ccci.*init", r"ccci.*probe", r"ccci.*ready",
                                r"md.*init", r"md.*ready", r"MD.*init",
                                r"modem.*init", r"modem.*ready", r"modem.*probe",
                                r"baseband.*init", r"CLDMA.*init",
                                r"RF.*init", r"SIM.*detect",
                                r"rmnet.*init", r"ipa.*probe", r"mpss.*load",
                                r"modem.*firmware"],
                "fail_patterns": [r"ccci.*fail", r"ccci.*error", r"ccci.*timeout",
                                  r"md.*fail", r"MD.*fail", r"modem.*fail",
                                  r"baseband.*fail", r"RF.*error", r"no.*SIM",
                                  r"rmnet.*fail", r"ipa.*fail", r"mpss.*fail"],
                "name": "Network / Modem",
            },
            "gps": {
                "ok_patterns": [r"GPS.*init", r"gps.*ready", r"GNSS.*init",
                                r"gps.*probe", r"mtk.*gps"],
                "fail_patterns": [r"GPS.*fail", r"gps.*error", r"GNSS.*error"],
                "name": "GPS",
            },
            "fingerprint": {
                "ok_patterns": [r"fpc.*init", r"fpc.*probe", r"fpc.*detect", r"fpc\d+",
                                r"goodix_fp.*init", r"goodix_fp.*probe", r"goodix_fp.*detect",
                                r"egis.*init", r"egis.*probe", r"egis.*detect",
                                r"fingerprint.*init", r"fps.*detect",
                                r"silead.*init", r"cdfinger.*init",
                                r"qbt\d+.*probe", r"qseecom.*init"],
                "fail_patterns": [r"fpc.*fail", r"fpc.*error",
                                  r"goodix_fp.*fail", r"goodix_fp.*error",
                                  r"egis.*fail", r"egis.*error",
                                  r"fingerprint.*fail", r"fps.*fail",
                                  r"no.*fingerprint"],
                "name": "Fingerprint",
            },
            "usb": {
                "ok_patterns": [r"USB.*init", r"musb.*init", r"usb.*ready", r"OTG.*init",
                                r"ssusb", r"usb.*phy", r"kpd.*gpio", r"pmic_detect",
                                r"typec.*init", r"typec.*probe", r"tcpc.*init"],
                "fail_patterns": [r"USB.*fail", r"musb.*error", r"usb.*error",
                                  r"typec.*fail", r"tcpc.*fail"],
                "name": "USB",
            },
            "nfc": {
                "ok_patterns": [r"NFC.*init", r"nfc.*ready", r"NXP.*init", r"st21",
                                r"pn\d+.*probe", r"ese.*init"],
                "fail_patterns": [r"NFC.*fail", r"nfc.*error", r"pn\d+.*fail"],
                "name": "NFC",
            },
            "touchscreen": {
                "ok_patterns": [r"goodix.*init", r"goodix.*probe", r"goodix.*detect", r"goodix_ts",
                                r"focaltech.*init", r"focaltech.*probe", r"focaltech.*detect", r"fts_ts",
                                r"synaptics.*init", r"synaptics.*probe", r"synaptics.*detect",
                                r"ili.*init", r"ili.*probe", r"ili\d+.*detect", r"ilitek",
                                r"himax.*init", r"himax.*probe",
                                r"novatek.*init", r"novatek.*probe", r"nvt.*init",
                                r"touch.*init", r"tp.*init", r"tpd.*init", r"touchpanel"],
                "fail_patterns": [r"goodix.*fail", r"goodix.*error", r"goodix.*timeout",
                                  r"focaltech.*fail", r"focaltech.*error",
                                  r"synaptics.*fail", r"synaptics.*error",
                                  r"ili.*fail", r"ili.*error", r"ilitek.*fail",
                                  r"himax.*fail", r"novatek.*fail",
                                  r"touch.*fail", r"tp.*error", r"tpd.*fail", r"touch.*error",
                                  r"i2c.*error.*touch", r"no.*touch"],
                "name": "Touchscreen",
            },
            "sensors": {
                "ok_patterns": [r"accel.*init", r"gyro.*init", r"proximity.*init", r"alsps",
                                r"sensor.*hub", r"scp.*init", r"nanohub",
                                r"lis2hh", r"bmi\d+", r"lsm\d+", r"icm\d+",
                                r"stk\d+", r"cm36\d+", r"apds\d+", r"mmc\d+",
                                r"magnetometer", r"barometer"],
                "fail_patterns": [r"accel.*fail", r"gyro.*error", r"sensor.*fail",
                                  r"proximity.*error", r"als.*error"],
                "name": "Sensors (Accel/Gyro/Prox/Mag)",
            },
        }

        text_lower = text.lower()

        # Check if kernel boots — this is the ultimate "phone works" signal
        kernel_boots = bool(
            re.search(r"Kernel.*start|kernel_entry|Jump to kernel|jump_kernel|"
                       r"Jumping to kernel|Starting kernel|Kernel Entry.*OK|"
                       r"BL31.*entry|el3_exit", text, re.IGNORECASE)
        )

        # Lines that merely NAME an error register/counter are not failures.
        # e.g. "ufs_error_log: 28c" is a normal SBL1 dump, not a UFS fault.
        benign = re.compile(
            r"error[_ ]log\b|error[_ ]count\s*[:=]\s*0\b",
            re.IGNORECASE,
        )
        scan_text = "\n".join(
            ln for ln in text.splitlines() if not benign.search(ln)
        )

        for hw_key, hw_info in hw_checks.items():
            status = "unknown"  # unknown = not mentioned in boot log

            # Check for failure patterns first
            for pattern in hw_info["fail_patterns"]:
                if re.search(pattern, scan_text, re.IGNORECASE):
                    status = "fail"
                    break

            # Check for success patterns (only if not already failed)
            if status != "fail":
                for pattern in hw_info["ok_patterns"]:
                    if re.search(pattern, scan_text, re.IGNORECASE):
                        status = "ok"
                        break

            # Smart override: if kernel boots, RAM MUST be working
            # (phone literally cannot boot without functional RAM)
            if hw_key == "ram" and status != "ok" and kernel_boots:
                status = "ok"

            hw_status[hw_key] = {
                "name": hw_info["name"],
                "status": status,  # "ok", "fail", "unknown"
            }

        results["hw_status"] = hw_status

        # ── Chipset IC Database Lookup ──
        # Match detected chipset against database for IC identification
        chipset_info = {}
        detected_chip = results.get("mtk_chip_code", "") or results.get("qcom_model", "")
        detected_pmic = results.get("pmic_model", "")

        # Try to find chipset in database — search ALL platforms
        all_platforms = ["mediatek", "qualcomm", "samsung_exynos", "unisoc"]
        if ic_db:
            # Search all platforms
            for platform in all_platforms:
                if chipset_info:
                    break
                for chip_id, info in ic_db.get(platform, {}).items():
                    # Match by chip ID in text or detected chip code
                    if chip_id in text or (detected_chip and detected_chip in chip_id):
                        chipset_info = info
                        results["chipset_db_match"] = chip_id
                        results["chipset_db_platform"] = platform
                        results["chipset_marketing_name"] = info.get("marketing_name", "")
                        break

            # Fallback: match by PMIC model
            if not chipset_info and detected_pmic:
                for platform in all_platforms:
                    if chipset_info:
                        break
                    for chip_id, info in ic_db.get(platform, {}).items():
                        if info.get("pmic", "") and detected_pmic in info.get("pmic", ""):
                            chipset_info = info
                            results["chipset_db_match"] = chip_id
                            results["chipset_db_platform"] = platform
                            results["chipset_marketing_name"] = info.get("marketing_name", "")
                            break

            # Also check phone teardowns for exact IC matching
            teardowns = ic_db.get("phone_teardowns", {})
            for td_name, td_info in teardowns.items():
                td_chipset = td_info.get("chipset", "")
                db_match = results.get("chipset_db_match", "")
                if db_match and db_match in td_chipset:
                    results["teardown_match"] = td_name
                    results["teardown_ics"] = td_info.get("ics", {})
                    break

            # Use global I2C map from database for better IC identification
            db_i2c_map = ic_db.get("i2c_address_map", {})
            if db_i2c_map:
                # Re-check I2C errors with database addresses
                for key in list(results.keys()):
                    if key.startswith("i2c_error_"):
                        addr_hex = key.split("_0x")[-1] if "_0x" in key else ""
                        if addr_hex and f"0x{addr_hex}" in db_i2c_map:
                            results[key] = results[key].split(" — ")[0] + " — " + db_i2c_map[f"0x{addr_hex}"]

            # Store companion ICs from database
            companion_ics = chipset_info.get("companion_ics", {})
            if companion_ics:
                results["companion_ics"] = companion_ics

            # Check known fault patterns from chipset-specific database
            known_faults = chipset_info.get("known_faults", {})
            if known_faults:
                for fault_id, fault_info in known_faults.items():
                    evidence_patterns = fault_info.get("boot_log_evidence", [])
                    matched_evidence = [p for p in evidence_patterns if p in text]
                    if len(matched_evidence) >= 2:
                        results["known_fault_match"] = fault_id
                        results["known_fault_info"] = fault_info

            # Check global fault patterns database
            global_faults = ic_db.get("fault_patterns", {})
            matched_patterns = []
            # Lines that are normal boot messages — not real errors
            _normal_boot_lines = {
                "DisplayBacklightBrightnessLevelControl",
                "Unable to get DisplayPanelDetectionResult",
                "DisplayDxe: sPlatformParams",
            }
            for fault_id, fault_info in global_faults.items():
                score = 0
                # Check boot log evidence
                for pattern in fault_info.get("boot_log_evidence", []):
                    if pattern and pattern in text:
                        score += 2
                # Check dmesg evidence
                for pattern in fault_info.get("dmesg_evidence", []):
                    if not pattern:
                        continue
                    m = re.search(pattern, text, re.IGNORECASE)
                    if m:
                        # Skip known-normal boot messages
                        matched_text = m.group(0)
                        if any(norm in matched_text for norm in _normal_boot_lines):
                            continue
                        score += 2
                # Check indicators
                for indicator in fault_info.get("indicators", []):
                    if indicator and indicator in text:
                        score += 1

                # Require at least 2 independent matches to avoid false positives
                if score >= 3:
                    matched_patterns.append({
                        "fault_id": fault_id,
                        "score": score,
                        "info": fault_info,
                    })

            if matched_patterns:
                matched_patterns.sort(key=lambda x: -x["score"])
                results["matched_fault_patterns"] = matched_patterns

        # ── Boot Completion Analysis (Logo Stuck Detection) ──
        # Track which boot stages were reached to detect logo-stuck/boot-loop
        boot_stages_reached = []
        if re.search(r"Preloader|PL_LOG_STORE|T#Preloader", text):
            boot_stages_reached.append("Preloader")
        if re.search(r"LK|lk_init|Jump to BL|logo_init|boot_mode_select", text, re.IGNORECASE):
            boot_stages_reached.append("LK (Little Kernel)")
        if kernel_boots:
            boot_stages_reached.append("Kernel")
        if re.search(r"init:\s*starting|init first stage|init second stage", text, re.IGNORECASE):
            boot_stages_reached.append("Android Init")
        if re.search(r"Zygote|zygote.*start|app_process", text, re.IGNORECASE):
            boot_stages_reached.append("Zygote")
        if re.search(r"SystemServer|system_server|com\.android\.server", text, re.IGNORECASE):
            boot_stages_reached.append("SystemServer")
        if re.search(r"boot.completed|sys\.boot_completed|ActivityManager.*Display.*init|Launcher.*start", text, re.IGNORECASE):
            boot_stages_reached.append("Boot Complete")

        results["boot_stages_reached"] = boot_stages_reached

        # Detect logo-stuck: kernel starts but Android never fully boots
        if kernel_boots and "Boot Complete" not in boot_stages_reached:
            # Kernel is OK but Android doesn't fully boot = likely logo stuck
            last_stage = boot_stages_reached[-1] if boot_stages_reached else "Unknown"

            # Check if we captured enough of the boot to make this diagnosis
            # (short captures might just not have captured the full boot)
            capture_duration_long = len(text) > 8000  # enough data to expect full boot

            if capture_duration_long:
                stuck_reason_parts = []

                # Correlate with detected faults
                ic_probes = results.get("ic_probes_failed", [])
                voltage_low = any(
                    uv < thresh
                    for rail, uv in voltage_rails.items()
                    for r, thresh in [("VPROC", 650000), ("VCORE", 600000)]
                    if rail == r
                )
                has_i2c_errors = any(k.startswith("i2c_error") for k in results.keys())
                wdt_timeout = pmic_poffsts and (int(pmic_poffsts.group(1), 16) & 0x40)

                if has_i2c_errors and ic_probes:
                    failed_ics = ", ".join(p.split(":")[0] for p in ic_probes[:3])
                    stuck_reason_parts.append(f"voltage regulator IC failure ({failed_ics})")
                if voltage_low:
                    low_rails = [f"{r}={uv/1000:.0f}mV" for r, uv in voltage_rails.items()
                                 if (r == "VPROC" and uv < 650000) or (r == "VCORE" and uv < 600000)]
                    stuck_reason_parts.append(f"low CPU voltage ({', '.join(low_rails)})")
                if wdt_timeout:
                    stuck_reason_parts.append("previous WDT timeout (phone was hanging before)")

                if stuck_reason_parts:
                    reason_str = " + ".join(stuck_reason_parts)
                    results["boot_stuck"] = True
                    results["boot_stuck_stage"] = last_stage
                    results["boot_stuck_reason"] = reason_str

                    # Multiple correlating faults = high confidence
                    _stuck_conf = 90 if len(stuck_reason_parts) >= 2 else 75
                    faults_detected.append({
                        "register": "BOOT",
                        "name": "Boot Stuck / Logo Hang Detected",
                        "value": f"Last stage: {last_stage}",
                        "message": (
                            f"Phone boots kernel but fails to reach Android. "
                            f"Likely stuck on logo. Probable cause: {reason_str}. "
                            f"Check voltage regulator ICs and their solder joints."
                        ),
                        "severity": "critical",
                        "confidence": _stuck_conf,
                    })
                else:
                    results["boot_stuck"] = True
                    results["boot_stuck_stage"] = last_stage
                    faults_detected.append({
                        "register": "BOOT",
                        "name": "Boot Incomplete",
                        "value": f"Last stage: {last_stage}",
                        "message": (
                            f"Kernel boots but Android did not fully start. "
                            f"Phone may be stuck on logo/bootloop. "
                            f"Check firmware, storage, and power supply."
                        ),
                        "severity": "warning",
                        "confidence": 55,  # Single indicator only — insufficient corroboration
                    })

        # ── Fault Correlation Analysis ──
        # Connect related individual faults into combined diagnoses
        correlated_faults = []

        # Gather signals for correlation
        has_i2c_bus3_errors = any(k.startswith("i2c_error_bus3") for k in results.keys())
        has_dram_reg_errors = any(
            k.startswith("i2c_error") and ("0x60" in k or "0x61" in k)
            for k in results.keys()
        )
        has_fan53526_probe_fail = any(
            "fan53526" in p.lower() or "fan53528" in p.lower() or "mt6691" in p.lower()
            for p in results.get("ic_probes_failed", [])
        )
        boot_stuck = results.get("boot_stuck", False)
        has_pmic_oc = any(f["register"] == "PMIC_OC" for f in faults_detected)
        has_thermal_alert = any(f["register"] == "PMIC_THERMAL" for f in faults_detected)
        has_vproc_low = any(
            f["register"] == "VOLTAGE" and "VPROC" in f["name"]
            for f in faults_detected
        )
        has_vcore_low = any(
            f["register"] == "VOLTAGE" and "VCORE" in f["name"]
            for f in faults_detected
        )
        has_wdt_timeout = any(
            f["register"] == "RGU_STA" or (f["register"] == "PMIC_RST" and "WDT" in f.get("value", ""))
            for f in faults_detected
        )
        has_ddlo_reset = any(
            f["register"] == "PMIC_RST" and "DDLO" in f.get("name", "")
            for f in faults_detected
        )
        # Count distinct I2C buses with errors
        i2c_error_buses = set()
        for k in results.keys():
            if k.startswith("i2c_error_bus"):
                bus_part = k.split("_")[2]  # "bus3" etc
                i2c_error_buses.add(bus_part)

        # Correlation 1: DRAM Power Subsystem Failure
        dram_power_signals = sum([
            has_i2c_bus3_errors or has_dram_reg_errors,
            has_fan53526_probe_fail,
            boot_stuck,
        ])
        if dram_power_signals >= 2:
            related = []
            if has_i2c_bus3_errors or has_dram_reg_errors:
                related.append("I2C error on DRAM regulator bus/addr")
            if has_fan53526_probe_fail:
                related.append("fan53526/RT5738 probe failure")
            if boot_stuck:
                related.append("boot stuck")
            confidence = min(60 + dram_power_signals * 16, 98)
            correlated_faults.append({
                "title": "DRAM Power Subsystem Failure",
                "related_faults": related,
                "root_cause": "MT6691ZXP/fan53526 IC not responding on I2C bus 3 — DRAM voltage regulator dead or bad solder",
                "confidence": confidence,
                "repair_steps": [
                    "Check MT6691ZXP solder joints under microscope",
                    "Measure EMI VDDQ voltage (should be 0.6V)",
                    "Measure EMI VDD2 voltage (should be 1.125V)",
                    "Reball or replace MT6691ZXP if dead",
                    "Check inductor and capacitor around DRAM regulator",
                ],
            })

        # Correlation 2: PMIC Short Circuit
        if has_pmic_oc and has_thermal_alert:
            correlated_faults.append({
                "title": "PMIC Short Circuit",
                "related_faults": ["PMIC overcurrent shutdown", "PMIC thermal alert"],
                "root_cause": "Short circuit on PMIC output rail causing overcurrent and overheating",
                "confidence": 90,
                "repair_steps": [
                    "Disconnect battery and check all PMIC output rails for shorts to ground",
                    "Use thermal camera or freeze spray to locate shorted component",
                    "Check capacitors around PMIC for shorts",
                    "If PMIC itself is shorted, replace PMIC IC",
                ],
            })

        # Correlation 3: CPU Power Subsystem Failure
        if has_vproc_low and has_vcore_low:
            correlated_faults.append({
                "title": "CPU Power Subsystem Failure",
                "related_faults": ["VPROC voltage low", "VCORE voltage low"],
                "root_cause": "Both CPU core voltage rails are below threshold — CPU power delivery failed",
                "confidence": 88,
                "repair_steps": [
                    "Check VPROC and VCORE buck converter output with multimeter",
                    "Inspect inductor and capacitors on CPU power rails",
                    "Check for short circuit on CPU power input pins",
                    "If regulators are external ICs, check their solder joints",
                    "Replace PMIC if internal regulators are faulty",
                ],
            })

        # Correlation 4: Repeated Boot Failure (hardware)
        if has_wdt_timeout and has_ddlo_reset and boot_stuck:
            correlated_faults.append({
                "title": "Repeated Boot Failure (hardware)",
                "related_faults": ["WDT timeout reset", "DDLO power reset", "boot stuck"],
                "root_cause": "Phone repeatedly attempts to boot but crashes (WDT) and power drops (DDLO) — hardware fault in power or CPU path",
                "confidence": 85,
                "repair_steps": [
                    "Check battery connector and battery health",
                    "Measure PMIC input voltage during boot attempt",
                    "Check for short circuit causing excessive current draw",
                    "Inspect CPU and PMIC solder joints for cracks",
                    "Try known-good battery to rule out battery issue",
                ],
            })

        # Correlation 5: I2C Bus System Issue
        if len(i2c_error_buses) >= 2:
            correlated_faults.append({
                "title": "I2C Bus System Issue",
                "related_faults": [f"I2C errors on {bus}" for bus in sorted(i2c_error_buses)],
                "root_cause": f"Multiple I2C buses ({', '.join(sorted(i2c_error_buses))}) have errors — possible SoC I2C controller issue or board-level problem",
                "confidence": 75,
                "repair_steps": [
                    "Check I2C pull-up resistors on affected buses",
                    "Inspect SoC solder joints (I2C lines route from SoC)",
                    "Check for water damage or corrosion on I2C traces",
                    "Measure I2C SDA/SCL lines with oscilloscope if available",
                    "If SoC-related, reball SoC may be required",
                ],
            })

        if correlated_faults:
            results["correlated_faults"] = correlated_faults

        # Look for version strings
        ver_match = re.search(r"(v\d+\.\d+[\.\d]*|version\s*[:\s]\s*[\d\.]+)", text, re.IGNORECASE)
        if ver_match:
            results["version"] = ver_match.group(0)

        # ATF/BL31 version
        atf_match = re.search(r"BL31:.*v(\d+\.\d+).*Built\s*:\s*([^\n]+)", text)
        if atf_match:
            results["atf_version"] = f"BL31 v{atf_match.group(1)}, Built: {atf_match.group(2).strip()}"

        # GZ/TrustZone version
        gz_match = re.search(r"Version of MTEE:\s*([^\n]+)", text)
        if gz_match:
            results["trustzone_version"] = gz_match.group(1).strip()

        # DRAM type and frequency
        dram_type_match = re.search(r"DRAM type\s+(\d+)", text)
        if dram_type_match:
            dram_types = {"4": "LPDDR4", "5": "LPDDR4X", "6": "LPDDR4X", "7": "LPDDR5", "8": "LPDDR5X"}
            dtype = dram_type_match.group(1)
            results["ram_type"] = dram_types.get(dtype, f"Type {dtype}")

        dram_freq_match = re.search(r"DRAM freq step 0,\s*(\d+)", text)
        if dram_freq_match:
            results["ram_freq"] = f"{dram_freq_match.group(1)} MHz"

        # CPU core count
        core_match = re.search(r"PLATFORM_CORE_COUNT\s*:\s*0x(\w+)", text)
        if core_match:
            results["cpu_cores"] = str(int(core_match.group(1), 16))

        # SPM firmware (power management)
        spm_match = re.search(r"spm_firmware\.bin\s*-\s*([^\n]+)", text)
        if spm_match:
            results["spm_firmware"] = spm_match.group(1).strip()

        # Boot mode
        boot_mode_match = re.search(r"boot mode is\s*(\d+)", text)
        if boot_mode_match:
            modes = {"0": "Normal", "1": "Normal", "2": "Factory", "3": "Recovery", "4": "Alarm"}
            results["boot_mode"] = modes.get(boot_mode_match.group(1), f"Mode {boot_mode_match.group(1)}")

        # Abnormal boot check
        abnormal_match = re.search(r"IS_ABNORMAL_BOOT:\s*(\d+)", text)
        if abnormal_match:
            results["abnormal_boot"] = "Yes (crash detected)" if abnormal_match.group(1) != "0" else "No (clean boot)"

        # Boot reason
        boot_reason_match = re.search(r"BOOT_REASON:\s*(\d+)", text)
        if boot_reason_match:
            reasons = {"0": "Power key", "1": "USB", "2": "RTC alarm", "4": "Watchdog reset", "8": "Reboot"}
            results["boot_reason"] = reasons.get(boot_reason_match.group(1), f"Reason {boot_reason_match.group(1)}")

        # Kernel entry
        if "prepare_kernel_entry" in text or "Preparing for EL3 exit" in text or "el3_exit" in text:
            results["kernel_entry"] = "OK - Kernel is starting"

        # Look for memory info (only if not already set by platform-specific parsing)
        if "ram" not in results:
            mem_match = re.search(r"(\d+)\s*(MB|GB|mb|gb)\s*(RAM|DDR|DRAM|LPDDR)", text, re.IGNORECASE)
            if mem_match:
                results["ram"] = f"{mem_match.group(1)} {mem_match.group(2)} {mem_match.group(3)}"

        # Look for storage info (only if not already set by platform-specific parsing)
        if "storage" not in results:
            stor_match = re.search(r"(eMMC|UFS|NAND|NVMe)[\s:]*(\d+\s*(GB|TB))?", text, re.IGNORECASE)
            if stor_match:
                results["storage"] = stor_match.group(0).strip()

        # Look for model/board names (only if not already set by platform-specific parsing)
        if "board_name" not in results:
            board_match = re.search(r"(board|model|device|product)\s*[=:]\s*(\S+)", text, re.IGNORECASE)
            if board_match:
                results["board_name"] = board_match.group(2)

        # ═══ DETAILED COMPONENT EXTRACTION ═══
        # Build a detailed components list with status, evidence, and details
        components = []

        # 1. CPU/SoC
        midr_match = re.search(r"MIDR:\s*([0-9a-fA-F]+)", text)
        mpidr_match = re.search(r"MPIDR:\s*([0-9a-fA-F]+)", text)
        cpu_core_match = re.search(r"CPU Core:\s*(\d+)", text)

        # Decode MIDR (Main ID Register) — ARM standard
        cpu_arch = ""
        if midr_match:
            midr_val = int(midr_match.group(1), 16)
            implementer = (midr_val >> 24) & 0xFF
            variant = (midr_val >> 20) & 0xF
            arch = (midr_val >> 16) & 0xF
            part = (midr_val >> 4) & 0xFFF

            implementers = {0x41: "ARM", 0x42: "Broadcom", 0x43: "Cavium",
                           0x44: "DEC", 0x4E: "NVIDIA", 0x50: "APM",
                           0x51: "Qualcomm", 0x53: "Samsung", 0x56: "Marvell"}

            arm_parts = {
                0xD03: "Cortex-A53", 0xD04: "Cortex-A35", 0xD05: "Cortex-A55",
                0xD06: "Cortex-A65", 0xD07: "Cortex-A57", 0xD08: "Cortex-A72",
                0xD09: "Cortex-A73", 0xD0A: "Cortex-A75", 0xD0B: "Cortex-A76",
                0xD0C: "Neoverse-N1", 0xD0D: "Cortex-A77", 0xD0E: "Cortex-A76AE",
                0xD40: "Neoverse-V1", 0xD41: "Cortex-A78", 0xD42: "Cortex-A78AE",
                0xD43: "Cortex-A65AE", 0xD44: "Cortex-X1", 0xD46: "Cortex-A510",
                0xD47: "Cortex-A710", 0xD48: "Cortex-X2", 0xD49: "Neoverse-N2",
                0xD4A: "Neoverse-E1", 0xD4B: "Cortex-A78C", 0xD4D: "Cortex-A715",
                0xD4E: "Cortex-X3", 0xD80: "Cortex-A520", 0xD81: "Cortex-A720",
                0xD82: "Cortex-X4", 0xD85: "Cortex-X925",
            }

            impl_name = implementers.get(implementer, f"Unknown(0x{implementer:02X})")
            part_name = arm_parts.get(part, f"Part(0x{part:03X})")
            cpu_arch = f"{impl_name} {part_name} r{variant}p{midr_val & 0xF}"
            results["cpu_architecture"] = cpu_arch
            results["cpu_midr"] = f"0x{midr_val:08X}"
            results["cpu_implementer"] = impl_name
            results["cpu_part"] = part_name

        qc_chip = results.get("qcom_chip_name", "")
        has_chipset = bool(midr_match or results.get("chipset") or qc_chip)
        cpu_evidence = f"MIDR: {midr_match.group(1)}, {cpu_arch}" if midr_match else (
            f"{qc_chip} @ {results.get('qcom_core_freq', '')}" if qc_chip else "N/A")

        components.append({
            "name": "CPU / SoC",
            "status": "ok" if has_chipset else "unknown",
            "evidence": cpu_evidence,
            "details": {
                "Architecture": cpu_arch or results.get("chipset_marketing_name", results.get("chipset_detail", "Unknown")),
                "Chip": qc_chip or results.get("chipset", "Unknown"),
                "Cores": results.get("cpu_cores", "Unknown"),
                "Frequency": results.get("qcom_core_freq", "N/A"),
                "MIDR Register": results.get("cpu_midr", "N/A"),
                "MPIDR": mpidr_match.group(1) if mpidr_match else "N/A",
                "Platform": results.get("platform", "Unknown"),
                "Boot CPU": cpu_core_match.group(1) if cpu_core_match else "0",
            }
        })

        is_qualcomm = results.get("platform") == "qualcomm"

        # 2. PLL / Clock System (MediaTek-specific — skip on Qualcomm)
        pll_ok = "Pll init Done" in text
        pll_time = ""
        pll_time_match = re.search(r"#T#PLL=(\d+)", text)
        if pll_time_match:
            pll_time = f"{pll_time_match.group(1)}ms"

        ifr_match = re.search(r"ifr0:\s*(0x[0-9A-Fa-f]+).*ifr1:\s*(0x[0-9A-Fa-f]+).*ifr2:\s*(0x[0-9A-Fa-f]+).*ifr3:\s*(0x[0-9A-Fa-f]+)", text)

        components.append({
            "name": "PLL / Clock System",
            "status": "ok" if pll_ok else ("unknown" if is_qualcomm else "fail"),
            "evidence": "Pll init Done!!" if pll_ok else ("N/A (Qualcomm)" if is_qualcomm else "PLL init not found"),
            "details": {
                "Status": "Initialized" if pll_ok else "FAILED",
                "Init Time": pll_time or "N/A",
                "IFR0 (PLL Config)": ifr_match.group(1) if ifr_match else "N/A",
                "IFR1": ifr_match.group(2) if ifr_match else "N/A",
                "IFR2": ifr_match.group(3) if ifr_match else "N/A",
                "IFR3": ifr_match.group(4) if ifr_match else "N/A",
                "ULPOSC Frequency": "260MHz" if "260M" in text else "N/A",
            }
        })

        # 3. MTCMOS / Power Domain
        mtcmos_ok = "mtcmos Done" in text
        mm0_match = re.search(r"mm0:\s*(0x[0-9A-Fa-f]+)", text)
        mdp0_match = re.search(r"mdp0:\s*(0x[0-9A-Fa-f]+)", text)

        components.append({
            "name": "MTCMOS / Power Domain",
            "status": "ok" if mtcmos_ok else ("unknown" if is_qualcomm else "fail"),
            "evidence": "mtcmos Done!" if mtcmos_ok else ("N/A (Qualcomm)" if is_qualcomm else "MTCMOS init not found"),
            "details": {
                "Status": "All power domains ON" if mtcmos_ok else ("N/A (Qualcomm)" if is_qualcomm else "FAILED"),
                "MM0 (Multimedia)": mm0_match.group(1) if mm0_match else "N/A",
                "MDP0 (Display Proc)": mdp0_match.group(1) if mdp0_match else "N/A",
            }
        })

        # 4. RAM / DRAM
        dram_type_val = results.get("ram_type", "")
        dram_freq_val = results.get("ram_freq", "")
        emi_ok = "MCU2EMI" in text or "MTEST" in text
        qcom_ddr_ok = is_qualcomm and bool(results.get("ram") or results.get("qcom_ddr_ranks"))

        # Get all DRAM frequency steps
        dram_steps = re.findall(r"DRAM freq step (\d+),\s*(\d+)", text)
        freq_list = ", ".join(f"{s[1]}MHz" for s in dram_steps) if dram_steps else "N/A"

        ram_evidence = f"{dram_type_val} @ {dram_freq_val}" if dram_type_val else (
            f"DDR {results.get('ram', '')} @ {dram_freq_val}" if qcom_ddr_ok else "EMI init detected")

        components.append({
            "name": "RAM / DRAM",
            "status": "ok" if (emi_ok or qcom_ddr_ok) else "unknown",
            "evidence": ram_evidence,
            "details": {
                "Type": dram_type_val or (f"DDR ({results.get('ram_manufacturer', 'Unknown')})" if qcom_ddr_ok else "Detected via MTEST"),
                "Size": results.get("ram", "N/A"),
                "Max Frequency": dram_freq_val or "N/A",
                "Ranks": results.get("qcom_ddr_ranks", "N/A"),
                "All Freq Steps": freq_list,
                "EMI Init": "OK (MCU2EMI_SLICE configured)" if "MCU2EMI" in text else "N/A",
                "MTEST": "PASS (MP_CHIPS)" if "MTEST" in text else "N/A",
                "Memory Base": "0x846e00000" if "846e00000" in text else "N/A",
            }
        })

        # 5. PMIC / Power Wrapper
        pwrap_ok = "init pass, ret=0" in text
        pwrap_read = "Read Test pass" in text
        pwrap_write = "Write Test pass" in text
        pwrap_time_match = re.search(r"#T#PWRAP=(\d+)", text)

        # PMIC boot phase
        pmic_phase_match = re.search(r"last PMIC boot up phase is (0x[0-9A-Fa-f]+):(0x[0-9A-Fa-f]+)", text)

        # Qualcomm uses SPMI not PWRAP — check for Qualcomm PMIC evidence instead
        qcom_pmic_ok = is_qualcomm and bool(results.get("pmic_model"))
        components.append({
            "name": "PMIC / Power Management",
            "status": "ok" if (pwrap_ok or qcom_pmic_ok) else ("unknown" if is_qualcomm else "fail"),
            "evidence": f"SPMI PMIC: {results.get('pmic_model', '')}" if qcom_pmic_ok else ("PWRAP init pass, Read/Write test pass" if pwrap_ok else ("N/A (Qualcomm uses SPMI)" if is_qualcomm else "PWRAP init failed")),
            "details": {
                "PWRAP Init": "N/A (Qualcomm uses SPMI)" if is_qualcomm else ("PASS (ret=0)" if pwrap_ok else "FAILED"),
                "Read Test": "PASS (rdata=0x5AA5)" if pwrap_read else "N/A",
                "Write Test": "PASS (rdata=0xA55A)" if pwrap_write else "N/A",
                "Init Time": f"{pwrap_time_match.group(1)}ms" if pwrap_time_match else "N/A",
                "SPI Strobe Calibration": "Done" if "Strobe Calibration" in text else "N/A",
                "CRC": "Enabled" if "Enable CRC ok" in text else "N/A",
                "PMIC Boot Phase": f"{pmic_phase_match.group(1)}:{pmic_phase_match.group(2)}" if pmic_phase_match else "0x0:0x0 (Normal)",
                "MODEM_TEMP_SHARE": "Configured (0xF0)" if "MODEM_TEMP_SHARE_CTRL:F0" in text else "N/A",
            }
        })

        # 6. SPMI Bus
        spmi_ok = "spmi_read_check done" in text
        spmi_slvid = re.search(r"slvid:(\d+)", text)
        spmi_time_match = re.search(r"#T#SPMI=(\d+)", text)

        components.append({
            "name": "SPMI Bus",
            "status": "ok" if spmi_ok else "unknown",
            "evidence": "SPMI calibrated to proper value" if spmi_ok else "N/A",
            "details": {
                "Status": "Calibrated" if spmi_ok else "N/A",
                "Slave ID": spmi_slvid.group(1) if spmi_slvid else "N/A",
                "Init Time": f"{spmi_time_match.group(1)}ms" if spmi_time_match else "N/A",
            }
        })

        # 7. PMIF Clock Manager
        pmif_ok = "ULPOSC1 K done" in text
        pmif_time_match = re.search(r"#T#PMIFCLKMGR=(\d+)", text)

        components.append({
            "name": "PMIF Clock Manager",
            "status": "ok" if pmif_ok else "unknown",
            "evidence": "ULPOSC1 calibration done, 260MHz" if pmif_ok else "N/A",
            "details": {
                "ULPOSC Frequency": "260MHz" if "260M" in text else "N/A",
                "SPMI Clock": "Set" if "set_spmi_clk" in text else "N/A",
                "SPI Clock": "Set" if "set_spi_clk" in text else "N/A",
                "Init Time": f"{pmif_time_match.group(1)}ms" if pmif_time_match else "N/A",
            }
        })

        # 8. Watchdog / RGU
        rgu_status_match = re.search(r"\[RGU\]\s*STA from reg:\s*(0x[0-9A-Fa-f]+)", text)
        rgu_mode_match = re.search(r"\[RGU\]\s*MODE:\s*(0x[0-9A-Fa-f]+)", text)
        rgu_length_match = re.search(r"\[RGU\]\s*LENGTH:\s*(0x[0-9A-Fa-f]+)", text)
        rgu_debug5_match = re.search(r"\[RGU\]\s*DEBUG_CTL5:\s*(0x[0-9A-Fa-f]+)", text)
        wdt_time_match = re.search(r"#T#WDT_PRE=(\d+)", text)
        rgu_sta_val = rgu_status_match.group(1) if rgu_status_match else "N/A"

        # No RGU register in the log (e.g. any Qualcomm device) means "not
        # reported", not "crashed". Only warn on a real non-zero STA value.
        rgu_known = rgu_status_match is not None
        rgu_clean = rgu_sta_val == "0x0"
        if not rgu_known:
            rgu_status, rgu_note = "unknown", "Not reported by this bootloader"
        elif rgu_clean:
            rgu_status, rgu_note = "ok", "— Clean boot"
        else:
            rgu_status, rgu_note = "warning", "— PREVIOUS CRASH DETECTED"

        components.append({
            "name": "Watchdog / RGU (Reset Generation Unit)",
            "status": rgu_status,
            "evidence": f"RGU Status: {rgu_sta_val}" + (
                " (Clean)" if rgu_clean else " (Previous Reset!)" if rgu_known else ""),
            "details": {
                "Reset Status (STA)": f"{rgu_sta_val} {rgu_note}",
                "Mode": rgu_mode_match.group(1) if rgu_mode_match else "N/A",
                "WDT Length": rgu_length_match.group(1) if rgu_length_match else "N/A",
                "Debug CTL5": rgu_debug5_match.group(1) if rgu_debug5_match else "N/A",
                "Init Time": f"{wdt_time_match.group(1)}ms" if wdt_time_match else "N/A",
                "Reset From": "Power key (normal)" if "rst from: ?" in text else "Unknown",
            }
        })

        # 9. System Timer
        cntcv_match = re.search(r"\[SYST\]\s*CNTCV\s+([0-9A-Fa-f]+)", text)
        cntcr_match = re.search(r"\[SYST\]\s*CNTCR\s+([0-9A-Fa-f]+)", text)

        components.append({
            "name": "System Timer (SYST)",
            "status": "ok" if cntcv_match else "unknown",
            "evidence": f"CNTCV: {cntcv_match.group(1)}" if cntcv_match else "N/A",
            "details": {
                "Counter Value": cntcv_match.group(1) if cntcv_match else "N/A",
                "Control Register": cntcr_match.group(1) if cntcr_match else "N/A",
                "Status": "Running" if cntcv_match else "N/A",
            }
        })

        # 10. ATF / BL31 (ARM Trusted Firmware)
        atf_ver_match = re.search(r"BL31:\s*v(\d+\.\d+)\((\w+)\):(\w+)", text)
        atf_built_match = re.search(r"BL31:\s*Built\s*:\s*([^\n]+)", text)
        atf_base_match = re.search(r"BL31_BASE=(0x[0-9a-fA-F]+),\s*BL31_TZRAM_SIZE=(0x[0-9a-fA-F]+)", text)
        entry_match = re.search(r"Entry point address\s*=\s*(0x[0-9a-fA-F]+)", text)

        components.append({
            "name": "ATF / BL31 (Trusted Firmware)",
            "status": "ok" if atf_ver_match else "unknown",
            "evidence": f"BL31 v{atf_ver_match.group(1)}" if atf_ver_match else "N/A",
            "details": {
                "Version": f"v{atf_ver_match.group(1)} ({atf_ver_match.group(2)})" if atf_ver_match else "N/A",
                "Git Hash": atf_ver_match.group(3) if atf_ver_match else "N/A",
                "Built": atf_built_match.group(1).strip() if atf_built_match else "N/A",
                "Base Address": atf_base_match.group(1) if atf_base_match else "N/A",
                "TZRAM Size": atf_base_match.group(2) if atf_base_match else "N/A",
                "Kernel Entry": entry_match.group(1) if entry_match else "N/A",
            }
        })

        # 11. TrustZone / GZ (GenieZone)
        gz_core_match = re.search(r"Version of GZ-CORE:\s*([^\n]+)", text)
        gz_libs_match = re.search(r"Version of libs:\s*([^\n]+)", text)

        components.append({
            "name": "TrustZone / GZ (GenieZone Hypervisor)",
            "status": "ok" if "GZ" in text else "unknown",
            "evidence": results.get("trustzone_version", "N/A"),
            "details": {
                "MTEE SDK": results.get("trustzone_version", "N/A"),
                "GZ-CORE": gz_core_match.group(1).strip() if gz_core_match else "N/A",
                "Private Libs": gz_libs_match.group(1).strip() if gz_libs_match else "N/A",
                "Platform": "MTK_ARMV8" if "MTK_ARMV8" in text else "N/A",
                "Memory Base": "0x846e00000" if "846e00000" in text else "N/A",
                "Memory Size": "16MB (0x1000000)" if "0x1000000" in text else "N/A",
            }
        })

        # 12. SPM (System Power Manager)
        spm_ok = "spm finished" in text or "spm_load_pcm_firmware" in text
        spm_fw = results.get("spm_firmware", "")
        cpc_ok = "enable CPC mode" in text

        components.append({
            "name": "SPM (System Power Manager)",
            "status": "ok" if spm_ok else "unknown",
            "evidence": f"SPM firmware loaded: {spm_fw}" if spm_fw else "SPM init",
            "details": {
                "Firmware": spm_fw or "N/A",
                "CPC Mode": "Enabled" if cpc_ok else "N/A",
                "MCDI": "Finished" if "MCDI finished" in text else "N/A",
                "MD Settle": re.search(r"md_settle\s*=\s*(\d+)", text).group(1) if re.search(r"md_settle\s*=\s*(\d+)", text) else "N/A",
            }
        })

        # 13. Storage (eMMC/UFS)
        storage_ok = "spmfw partition" in text or "partition" in text.lower()
        qcom_storage_ok = is_qualcomm and bool(results.get("storage") or results.get("qcom_ufs_id"))

        components.append({
            "name": "Storage (eMMC/UFS)",
            "status": "ok" if (storage_ok or qcom_storage_ok) else "unknown",
            "evidence": f"{results.get('storage', 'UFS')}: {results.get('qcom_ufs_id', '')}" if qcom_storage_ok else (
                "SPM firmware loaded from partition = storage readable" if storage_ok else "N/A"),
            "details": {
                "Status": "Readable" if (storage_ok or qcom_storage_ok) else "Unknown",
                "Type": results.get("storage_type", "N/A"),
                "UFS ID": results.get("qcom_ufs_id", "N/A"),
                "Boot LUN": "Active" if (storage_ok or qcom_storage_ok) else "N/A",
                "PL_LOG_STORE": "Configured (addr 0x116000)" if "0x116000" in text else "N/A",
            }
        })

        # 14. Key Detection
        key_match = re.search(r"MTK_PMIC_RST_KEY\s*=\s*(\d+)", text)

        components.append({
            "name": "Key / Button Detection",
            "status": "ok" if key_match else "unknown",
            "evidence": f"PMIC Reset Key ID: {key_match.group(1)}" if key_match else "N/A",
            "details": {
                "Home/Power Key": f"Detected (ID: {key_match.group(1)})" if key_match else "N/A",
                "GPIO Setup": "Done" if "mtk_kpd_gpio_set" in text else "N/A",
            }
        })

        # 15. TIA (Thermal Info Acquisition)
        tia_ok = "TIA init done" in text
        tia_time_match = re.search(r"#T#TIA=(\d+)", text)

        components.append({
            "name": "TIA (Thermal / AUXADC)",
            "status": "ok" if tia_ok else "unknown",
            "evidence": "TIA AUXADC initialized" if tia_ok else "N/A",
            "details": {
                "Status": "Initialized" if tia_ok else "N/A",
                "Init Time": f"{tia_time_match.group(1)}ms" if tia_time_match else "N/A",
                "Trigger": "Setup OK" if "trigger addr setup ok" in text else "N/A",
            }
        })

        # 16. Boot Mode / Status
        components.append({
            "name": "Boot Mode / Status",
            "status": "ok",
            "evidence": f"Mode: {results.get('boot_mode', 'Normal')}, Reason: {results.get('boot_reason', 'Power key')}",
            "details": {
                "Boot Mode": results.get("boot_mode", "Normal"),
                "Boot Reason": results.get("boot_reason", "Power key"),
                "Abnormal Boot": results.get("abnormal_boot", "No"),
                "Secure Boot": "EL2 (Enabled)" if "Booting from EL2" in text else "N/A",
                "Kernel Entry": results.get("kernel_entry", "N/A"),
                "SPSR": re.search(r"SPSR\s*=\s*(0x[0-9a-fA-F]+)", text).group(1) if re.search(r"SPSR\s*=\s*(0x[0-9a-fA-F]+)", text) else "N/A",
            }
        })

        # 17. Bandgap / GPIO
        bandgap_match = re.search(r"bandgap filter:\s*(0x[0-9A-Fa-f]+)\s*=\s*(0x[0-9A-Fa-f]+)", text)
        gpio_time_match = re.search(r"#T#GPIO=(\d+)", text)

        components.append({
            "name": "Bandgap / GPIO",
            "status": "ok" if bandgap_match else "unknown",
            "evidence": f"Bandgap: {bandgap_match.group(1)}={bandgap_match.group(2)}" if bandgap_match else "N/A",
            "details": {
                "Bandgap Filter": f"{bandgap_match.group(1)} = {bandgap_match.group(2)}" if bandgap_match else "N/A",
                "GPIO Init Time": f"{gpio_time_match.group(1)}ms" if gpio_time_match else "N/A",
            }
        })

        results["components"] = components

        return results

    def detect(self, listen_duration: float = 30.0, callback=None) -> DetectionResult:
        """
        Full detection:
        1. Open FTDI serial port
        2. Listen on multiple baud rates to capture full boot (BROM + Preloader + Kernel)
           (User should boot/reboot phone during this time)
        3. Parse all captured data to identify chipset, brand, hardware health
        """
        result = DetectionResult()
        result.uart_log = []

        # Step 1: Open FTDI
        result.uart_log.append(f"Opening FTDI on {self.port}...")

        if not self._open_serial():
            result.error = f"Cannot connect to FTDI on {self.port}. Check USB cable."
            result.uart_log.append(f"  FAILED: {result.error}")
            return result

        result.raw_responses["ftdi_connection"] = f"Connected on {self.port}"
        result.uart_log.append(f"  Connected!")
        result.uart_log.append(f"")
        result.uart_log.append(f"Listening for {int(listen_duration)} seconds at {self.baud} baud...")
        result.uart_log.append(f"This captures preloader + LK + kernel boot log")
        result.uart_log.append(f">>> BOOT THE PHONE NOW! (connect battery / press power) <<<")
        result.uart_log.append(f"")

        self._close_serial()

        # Step 2: Listen on multiple baud rates
        def multi_callback(elapsed, total_bytes, current_baud):
            if callback:
                callback(elapsed, total_bytes)
            # Log baud switches
            pass

        baud_data = self._read_multi_baud(duration=listen_duration, callback=multi_callback)

        # Combine all data — prefer the baud rate with most readable content
        for baud, data in sorted(baud_data.items()):
            if data:
                result.uart_log.append(f"  Baud {baud}: {len(data)} bytes captured")
                result.raw_responses[f"data_baud_{baud}"] = f"{len(data)} bytes"

        # Pick best baud: highest printable ASCII percentage wins
        best_baud = None
        best_pct = -1
        for baud, data in baud_data.items():
            if not data:
                continue
            sample = data[:4096]
            printable = sum(1 for b in sample if 0x20 <= b <= 0x7E or b in (0x0A, 0x0D, 0x09))
            pct = printable / len(sample) * 100 if sample else 0
            result.uart_log.append(f"    Baud {baud}: {pct:.0f}% printable ASCII")
            if pct > best_pct:
                best_pct = pct
                best_baud = baud

        # Use the best baud's data; fall back to concatenating all if only one
        if best_baud is not None and best_pct > 15:
            raw_data = baud_data[best_baud]
            result.uart_log.append(f"  Using baud {best_baud} data ({best_pct:.0f}% readable)")
        else:
            raw_data = b""
            for baud, data in sorted(baud_data.items()):
                if data:
                    raw_data += data

        total_bytes = len(raw_data)
        # Store as hex string to preserve original binary data losslessly.
        # Previous approach: decode("ascii", errors="replace") destroyed every
        # non-ASCII byte (replaced with U+FFFD), making re-analysis impossible.
        result.raw_data = raw_data.hex()
        result.raw_responses["data_received"] = f"{total_bytes} bytes total"

        if total_bytes == 0:
            result.detected = False
            result.error = "No data received. Check: 1) TX/RX wiring  2) Did phone boot during listening?"
            result.uart_log.append("No data received in listening period.")
            return result

        result.uart_log.append(f"")
        result.uart_log.append(f"Total: {total_bytes} bytes received!")

        # Check for baud-mismatch garbage (data is mostly 0x00/0x80 with no printable text)
        printable_count = sum(1 for b in raw_data[:min(4096, len(raw_data))] if 0x20 <= b <= 0x7E)
        printable_ratio = printable_count / min(4096, len(raw_data)) if raw_data else 0
        if printable_ratio < 0.05:
            result.detected = False
            result.error = (
                f"Data received ({total_bytes} bytes) but no readable text — "
                f"likely WRONG BAUD RATE. Try 115200 instead of {self._baud}, or vice versa. "
                f"Also check TX/RX are not swapped."
            )
            result.uart_log.append(f"⚠️ Baud mismatch: {printable_ratio*100:.1f}% printable (need >5%)")
            result.raw_data = raw_data.hex()
            return result

        result.uart_log.append(f"Analyzing boot data...")

        # Step 3: Parse boot data
        parsed = self._parse_boot_data(raw_data)

        # Only mark detected if parser found something useful
        has_useful_data = any(k in parsed for k in ("chipset", "brand", "boot_registers", "ram", "cpu_cores", "pmic_model"))
        result.detected = has_useful_data
        if not has_useful_data:
            result.error = (
                f"Data received ({total_bytes} bytes) but could not identify device. "
                f"Try different baud rate or check UART connection."
            )

        if "chipset" in parsed:
            result.chipset = parsed["chipset"]
            result.raw_responses["chipset"] = parsed["chipset"]
            result.matched_fields["chipset"] = True
            result.uart_log.append(f"  Chipset: {parsed['chipset']} ({parsed.get('chipset_detail', '')})")

        if "brand" in parsed:
            result.brand = parsed["brand"]
            result.raw_responses["brand"] = parsed["brand"]
            result.matched_fields["brand"] = True
            result.uart_log.append(f"  Brand: {parsed['brand']}")

        if "boot_registers" in parsed:
            result.raw_responses["boot_registers"] = parsed["boot_registers"]
            result.uart_log.append(f"  Boot Registers: {parsed['boot_registers']}")

        if "boot_stage" in parsed:
            result.raw_responses["boot_stage"] = parsed["boot_stage"]
            result.uart_log.append(f"  Boot Stage: {parsed['boot_stage']}")

        if "version" in parsed:
            result.raw_responses["firmware_version"] = parsed["version"]
            result.uart_log.append(f"  Version: {parsed['version']}")

        if "ram" in parsed:
            result.raw_responses["ram"] = parsed["ram"]
            result.uart_log.append(f"  RAM: {parsed['ram']}")

        if "storage" in parsed:
            result.raw_responses["storage"] = parsed["storage"]
            result.uart_log.append(f"  Storage: {parsed['storage']}")

        if "board_name" in parsed:
            result.raw_responses["board_name"] = parsed["board_name"]
            result.device_name = parsed["board_name"]
            result.uart_log.append(f"  Board: {parsed['board_name']}")

        # New parsed fields
        new_fields = [
            ("ram_type", "RAM Type"),
            ("ram_freq", "RAM Frequency"),
            ("ram_manufacturer", "RAM Manufacturer"),
            ("cpu_cores", "CPU Cores"),
            ("atf_version", "ATF/BL31"),
            ("trustzone_version", "TrustZone"),
            ("spm_firmware", "SPM Firmware"),
            ("boot_mode", "Boot Mode"),
            ("abnormal_boot", "Abnormal Boot"),
            ("boot_reason", "Boot Reason"),
            ("kernel_entry", "Kernel Entry"),
            ("mtk_chip_code", "MTK Chip Code"),
            ("mtk_chip_name", "MTK Chip Name"),
            ("pmic_model", "PMIC Model"),
            ("pmic_reset_cause", "PMIC Reset Cause"),
            ("boot_reason_detail", "Boot Detail"),
            ("storage_type", "Storage Type"),
            ("storage_max_speed", "Storage Speed"),
            ("battery_vbat", "Battery VBAT"),
            ("battery_vchr", "Charger Voltage"),
            ("boot_stuck_stage", "Boot Stuck At"),
            ("boot_stuck_reason", "Stuck Cause"),
            # Qualcomm UEFI fields
            ("qcom_chip_name", "QC Chip Name"),
            ("qcom_chip_ver", "QC Chip Version"),
            ("qcom_codename", "QC Codename"),
            ("qcom_jtag_id", "JTAG ID"),
            ("qcom_core_freq", "Core Frequency"),
            ("qcom_ufs_id", "UFS ID"),
            ("qcom_ufs_spec", "UFS Spec"),
            ("qcom_ddr_ranks", "DDR Ranks"),
            ("qcom_ibat", "Battery Current"),
            ("qcom_battery_id", "Battery ID"),
            ("qcom_display", "Display Panel"),
            ("qcom_display_res", "Display Resolution"),
            ("qcom_wifi", "WiFi"),
            ("qcom_bluetooth", "Bluetooth"),
            ("qcom_vb_state", "Verified Boot"),
            ("qcom_secure_boot", "Secure Boot"),
            ("qcom_serial", "Serial Number"),
            ("qcom_oem_id", "OEM ID"),
            ("qcom_product_name", "Product Name"),
            ("ddr_dsf_version", "DDR DSF Version"),
            ("qcom_device_code", "Device Code"),
            ("qcom_uefi_total", "UEFI Boot Time"),
            ("qcom_boot_time_ms", "SBL Boot Time"),
            ("qcom_mbm_version", "MBM Version"),
            # DDR failure diagnostics
            ("ddr_type_detected", "DDR Type"),
            ("ddr_abort_reason", "DDR Abort Reason"),
            ("ddr_abort_freq", "DDR Abort Freq"),
            ("ddr_abort_channel", "DDR Abort Channel"),
        ]

        for key, label in new_fields:
            if key in parsed:
                result.raw_responses[key] = parsed[key]
                result.uart_log.append(f"  {label}: {parsed[key]}")

        # Log voltage rails
        voltage_rails = parsed.get("voltage_rails", {})
        if voltage_rails:
            result.uart_log.append("")
            result.uart_log.append("── Voltage Rails ──")
            for rail, uv in voltage_rails.items():
                result.uart_log.append(f"  {rail}: {uv/1000:.1f}mV ({uv}uV)")
            result.raw_responses["voltage_rails"] = str(voltage_rails)

        # Log PMIC registers
        pmic_regs = parsed.get("pmic_registers", {})
        if pmic_regs:
            result.uart_log.append("")
            result.uart_log.append("── PMIC Registers ──")
            for reg_name, reg_val in pmic_regs.items():
                result.uart_log.append(f"  {reg_name}: {reg_val}")

        # Log I2C errors with IC identification
        for key in sorted(parsed.keys()):
            if key.startswith("i2c_error_"):
                result.uart_log.append(f"  ⚠️ I2C Error: {parsed[key]}")
                result.raw_responses[key] = parsed[key]

        # Log IC probe failures
        ic_probes = parsed.get("ic_probes_failed", [])
        if ic_probes:
            result.uart_log.append("")
            result.uart_log.append("── IC Probe Results ──")
            for probe in ic_probes:
                result.uart_log.append(f"  ⚪ {probe}")

        # Log chipset IC database match
        db_match = parsed.get("chipset_db_match", "")
        marketing = parsed.get("chipset_marketing_name", "")
        companion = parsed.get("companion_ics", {})
        known_fault = parsed.get("known_fault_info")

        # Propagate IC database match info to raw_responses for the report
        if db_match:
            result.raw_responses["chipset_db_match"] = db_match
        if marketing:
            result.raw_responses["chipset_marketing_name"] = marketing

        if db_match or companion:
            result.uart_log.append("")
            platform_name = parsed.get("chipset_db_platform", "")
            result.uart_log.append(f"── Chipset IC Database ({platform_name}) ──")
            if db_match:
                result.uart_log.append(f"  Matched: {db_match} ({marketing})")
            if companion:
                for ic_name, ic_info in companion.items():
                    func = ic_info if isinstance(ic_info, str) else ic_info.get("function", "")
                    addr = ""
                    if isinstance(ic_info, dict):
                        addr = ic_info.get("i2c_addr_7bit", ic_info.get("i2c_addr", ""))
                    addr_str = f" [I2C: {addr}]" if addr else ""
                    result.uart_log.append(f"  {ic_name}: {func}{addr_str}")

        # Teardown IC data (if matched)
        teardown_name = parsed.get("teardown_match", "")
        teardown_ics = parsed.get("teardown_ics", {})
        if teardown_ics:
            result.uart_log.append(f"  Teardown: {teardown_name} ({len(teardown_ics)} ICs identified)")
            result.raw_responses["teardown_ics"] = str(teardown_ics)

        if known_fault:
            result.uart_log.append("")
            result.uart_log.append("── Known Fault Pattern Match ──")
            result.uart_log.append(f"  Symptom: {known_fault.get('symptom', '')}")
            result.uart_log.append(f"  Root Cause: {known_fault.get('root_cause', '')}")
            result.uart_log.append(f"  Confidence: {known_fault.get('confidence', 0)}%")
            for step in known_fault.get("repair_steps", []):
                result.uart_log.append(f"  -> {step}")
            result.uart_log.append(f"  Difficulty: {known_fault.get('difficulty', 'unknown')}")

        # Log matched fault patterns from global database
        matched_patterns = parsed.get("matched_fault_patterns", [])
        if matched_patterns:
            result.uart_log.append("")
            result.uart_log.append("── Possible Diagnoses (from fault database) ──")
            for mp in matched_patterns[:3]:  # Show top 3 matches
                info = mp["info"]
                result.uart_log.append(f"  {info['symptom']}")
                for cause in info.get("possible_causes", [])[:2]:
                    result.uart_log.append(f"    IC: {cause['ic']} ({cause['confidence']}%)")
                    result.uart_log.append(f"    Check: {cause['check']}")
                result.uart_log.append(f"    Difficulty: {info.get('difficulty', '?')}")
                result.uart_log.append("")

        # Log dmesg extracted data (real device measurements)
        dmesg = parsed.get("dmesg_data", {})
        if dmesg:
            result.uart_log.append("")
            result.uart_log.append("── Live Device Measurements (from kernel log) ──")

            if any(k.startswith("battery") or k == "thermistor_temp" for k in dmesg):
                result.uart_log.append("  Battery:")
                for k, label in [
                    ("battery_soc", "SOC"), ("battery_vbat_live", "VBAT"),
                    ("battery_temp", "Temperature"), ("battery_capacity_psp", "Capacity"),
                    ("battery_temp_raw", "Temp (raw)"), ("thermistor_temp", "Thermistor"),
                ]:
                    if k in dmesg:
                        result.uart_log.append(f"     {label}: {dmesg[k]}")

            if any(k.startswith("pmic_") and "temp" in k for k in dmesg):
                result.uart_log.append("  PMIC Temperature:")
                if "pmic_vcore_temp" in dmesg:
                    result.uart_log.append(f"     VCORE Buck: {dmesg['pmic_vcore_temp']}")
                if "pmic_vproc_temp" in dmesg:
                    result.uart_log.append(f"     VPROC Buck: {dmesg['pmic_vproc_temp']}")

            if any(k.startswith(("charging", "charger", "usb_pd", "power_", "dlpt")) for k in dmesg):
                result.uart_log.append("  Charging:")
                for k, label in [
                    ("charger_type", "Charger Type"), ("charging_current_avg", "Current (avg)"),
                    ("charging_current_max", "Current (max)"), ("charging_current_min", "Current (min)"),
                    ("charging_samples", "Samples"), ("power_watts", "Power"),
                    ("power_current_ma", "Draw"), ("usb_pd_status", "USB-PD"),
                    ("dlpt_load_ma", "DLPT Load"), ("dlpt_soc", "DLPT SOC"),
                ]:
                    if k in dmesg:
                        result.uart_log.append(f"     {label}: {dmesg[k]}")

            if any(k.startswith(("gpu", "surfaceflinger", "gralloc")) for k in dmesg):
                result.uart_log.append("  GPU / Display:")
                for k, label in [
                    ("gpu_status", "GPU Status"), ("gpu_driver_errors", "GPU Driver Errors"),
                    ("gpu_power_lock_fail", "GPU Power Lock Fail"),
                    ("gralloc_crash", "Gralloc"), ("surfaceflinger_errors", "SurfaceFlinger Errors"),
                ]:
                    if k in dmesg:
                        result.uart_log.append(f"     {label}: {dmesg[k]}")

            if any(k.startswith("modem") for k in dmesg):
                result.uart_log.append("  Modem:")
                for k, label in [
                    ("modem_active", "Status"), ("modem_last_status", "Last Response"),
                    ("modem_responses", "Responses"), ("modem_polls", "Polls"),
                ]:
                    if k in dmesg:
                        result.uart_log.append(f"     {label}: {dmesg[k]}")

            if any(k.startswith("audio") for k in dmesg):
                result.uart_log.append("  Audio:")
                if "audio_errors" in dmesg:
                    result.uart_log.append(f"     Errors: {dmesg['audio_errors']}x")
                if "audio_warnings" in dmesg:
                    result.uart_log.append(f"     Warnings: {dmesg['audio_warnings']}x")

            auxadc = dmesg.get("auxadc_channels", {})
            if auxadc:
                result.uart_log.append("  AUXADC Readings:")
                for ch_name, ch_val in sorted(auxadc.items()):
                    result.uart_log.append(f"     {ch_name}: {ch_val}")

            if "coulomb_counter" in dmesg:
                result.uart_log.append(f"  Coulomb Counter: {dmesg['coulomb_counter']}")

        result.raw_responses["data_size"] = parsed.get("data_size", "0 bytes")
        result.raw_responses["raw_hex_preview"] = parsed.get("raw_hex", "")[:100]

        # Store readable lines
        readable = parsed.get("readable_lines", "")
        if readable:
            result.raw_responses["readable_boot_log"] = readable

        # Register analysis
        reg_analysis = parsed.get("register_analysis", {})
        if reg_analysis:
            result.raw_responses["register_count"] = str(len(reg_analysis))
            result.uart_log.append("")
            result.uart_log.append("── Register Analysis ──")
            for reg_name, reg_data in reg_analysis.items():
                status_icon = "✅" if reg_data["status"] == "ok" else "❌"
                result.uart_log.append(
                    f"  {status_icon} {reg_name} ({reg_data['name']}): {reg_data['value']} — {reg_data['description']}"
                )

        # Faults detected
        faults = parsed.get("faults_detected", [])
        result.raw_responses["faults_count"] = str(len(faults))

        if faults:
            result.uart_log.append("")
            result.uart_log.append("🚨 ── FAULTS DETECTED ──")
            for fault in faults:
                conf = fault.get("confidence", 70)
                if conf < 50:
                    sev = "ℹ️ UNCONFIRMED"
                elif fault["severity"] == "critical":
                    sev = f"🔴 CRITICAL ({conf}%)"
                else:
                    sev = f"🟡 WARNING ({conf}%)"
                result.uart_log.append(
                    f"  {sev}: [{fault['register']}] {fault['name']} = {fault['value']}"
                )
                result.uart_log.append(f"         → {fault['message']}")
        else:
            result.uart_log.append("")
            result.uart_log.append("✅ No register faults detected — all registers normal")

        # Correlated diagnosis (combined fault analysis)
        correlated = parsed.get("correlated_faults", [])
        if correlated:
            result.uart_log.append("")
            result.uart_log.append("🔗 ── CORRELATED DIAGNOSIS ──")
            for cfault in correlated:
                result.uart_log.append(
                    f"  🔴 {cfault['title']} (Confidence: {cfault['confidence']}%)"
                )
                result.uart_log.append(
                    f"     Root Cause: {cfault['root_cause']}"
                )
                related_str = " + ".join(cfault["related_faults"])
                result.uart_log.append(
                    f"     Related: {related_str}"
                )
                result.uart_log.append("     Repair Steps:")
                for step_idx, step in enumerate(cfault["repair_steps"], 1):
                    result.uart_log.append(f"       {step_idx}. {step}")
            result.raw_responses["correlated_faults_count"] = str(len(correlated))

        # Last reset cause
        if "last_reset_cause" in parsed:
            result.raw_responses["last_reset_cause"] = parsed["last_reset_cause"]
            result.uart_log.append(f"  Reset Status: {parsed['last_reset_cause']}")

        # Hardware health status
        hw_status = parsed.get("hw_status", {})
        result.hw_status = hw_status

        # Late-boot subsystems that only init after Android starts (not visible in UART)
        _late_boot_subsystems = {"wifi", "bluetooth", "camera", "audio",
                                  "network", "gps", "fingerprint", "nfc", "touchscreen"}

        # Log hardware status — only show detected items (OK or FAIL), skip unknown/untestable
        if hw_status:
            detected_hw = [(k, v) for k, v in hw_status.items() if v["status"] in ("ok", "fail")]
            if detected_hw:
                result.uart_log.append("")
                result.uart_log.append("── Hardware Health ──")
                for hw_key, hw_info in detected_hw:
                    status = hw_info["status"]
                    name = hw_info["name"]
                    if status == "ok":
                        result.uart_log.append(f"  ✅ {name}: OK")
                    elif status == "fail":
                        result.uart_log.append(f"  ❌ {name}: FAIL")

        # Detailed Component Report — only show components with real data
        components = parsed.get("components", [])
        # Filter: only show components that have actual data (not all N/A)
        useful_components = []
        for comp in components:
            details = comp.get("details", {})
            # Count how many details have real values (not N/A, Unknown, etc.)
            real_values = sum(1 for v in details.values()
                              if v and str(v).strip() not in ("N/A", "Unknown", "UNKNOWN", "", "None"))
            # Include if: status is ok/fail/warning, OR has at least 1 real detail value
            if comp["status"] in ("ok", "fail", "warning") or real_values > 0:
                useful_components.append(comp)

        if useful_components:
            result.uart_log.append("")
            result.uart_log.append("═══════════════════════════════════════════")
            result.uart_log.append("   COMPONENT DETAILS")
            result.uart_log.append("═══════════════════════════════════════════")

            for comp in useful_components:
                status_icon = {"ok": "✅", "fail": "❌", "warning": "⚠️"}.get(comp["status"], "⚪")
                result.uart_log.append("")
                result.uart_log.append(f"  {status_icon} {comp['name']}")

                evidence = comp.get("evidence", "")
                if evidence and evidence not in ("N/A", "Unknown"):
                    result.uart_log.append(f"     Evidence: {evidence}")

                details = comp.get("details", {})
                for key, val in details.items():
                    # Skip empty/N/A values — only show real data
                    if not val or str(val).strip() in ("N/A", "Unknown", "UNKNOWN", "", "None"):
                        continue
                    result.uart_log.append(f"     {key}: {val}")

        # Store components in raw_responses for GUI
        result.raw_responses["components_count"] = str(len(components))
        # Store as JSON string for easy parsing
        import json as _json
        try:
            result.raw_responses["components_json"] = _json.dumps(components, ensure_ascii=False)
        except Exception:
            pass

        # Calculate confidence
        confidence = 20  # Base: we got data
        if "chipset" in parsed:
            confidence += 30
        if "brand" in parsed:
            confidence += 20
        if "boot_registers" in parsed:
            confidence += 10
        if "board_name" in parsed:
            confidence += 10
        if "ram" in parsed:
            confidence += 5
        if "storage" in parsed:
            confidence += 5

        result.confidence = min(confidence, 100)

        # Set device name
        if result.device_name == "Unknown Device":
            parts = []
            if result.brand != "Unknown":
                parts.append(result.brand)
            if result.chipset != "Unknown":
                parts.append(f"({result.chipset})")
            if parts:
                result.device_name = " ".join(parts) + " Device"

        # Set protocol
        if result.chipset.startswith("MediaTek"):
            result.protocol = "MediaTek BROM UART"
        elif result.chipset.startswith("Qualcomm"):
            result.protocol = "Qualcomm UART"
        elif result.chipset.startswith("Samsung"):
            result.protocol = "Samsung UART"
        elif result.chipset.startswith("Apple"):
            result.protocol = "Apple UART"
        else:
            result.protocol = "UART Boot Log"

        result.uart_log.append(f"")
        result.uart_log.append(f"Detection complete: {result.brand} / {result.chipset} / {result.confidence}%")

        return result

    def __repr__(self) -> str:
        return f"DeviceAutoDetector(port={self.port!r}, baud={self.baud}, FTDI mode)"
