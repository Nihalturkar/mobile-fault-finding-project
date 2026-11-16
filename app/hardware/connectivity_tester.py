"""
Connectivity Testing Module for Mobile Repair Technicians.

Performs comprehensive diagnostics of all wireless connectivity subsystems
on an Android device via ADB:
  1. WiFi — chipset identification, link state, signal strength, band info
  2. Bluetooth — IC identification, pairing state, address readback
  3. GPS/GNSS — provider enumeration, satellite counts, constellation support
  4. NFC — controller identification, firmware version, enable state
  5. Cellular — signal strength (RSSI/RSRP/RSRQ/SINR), network type, band

Results are structured into typed dataclasses that feed the downstream
fault-analysis engine.  Each wireless IC is matched against a built-in
knowledge database of known chipsets with manufacturer data, supported
standards, and common failure modes for repair technicians.

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Progress callback type alias
# ---------------------------------------------------------------------------
ProgressCallback = Optional[Callable[[float, str], None]]


# ---------------------------------------------------------------------------
#  WiFi Chipset Knowledge Database (26 entries)
# ---------------------------------------------------------------------------
WIFI_CHIPSET_DATABASE: Dict[str, Dict[str, Any]] = {
    # ── Qualcomm ──────────────────────────────────────────────────────────
    "WCN6855": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "WiFi 6E band intermittent disconnect on early firmware",
            "Bluetooth coexistence interference in 6 GHz band",
            "Firmware crash after prolonged 6 GHz scanning",
        ],
    },
    "WCN6856": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "Random WiFi drops in congested environments",
            "DFS channel radar false detection causing disconnect",
            "Power consumption spike during 6 GHz scanning",
        ],
    },
    "WCN6750": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "1.8 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "Reduced range on 6 GHz compared to 5 GHz band",
            "Bluetooth audio stutter during heavy WiFi traffic",
            "WiFi Direct connection failures with legacy devices",
        ],
    },
    "WCN3990": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.73 Gbps",
        "bluetooth_version": "5.1",
        "common_failures": [
            "2.4 GHz interference with Bluetooth audio streaming",
            "WiFi drops under heavy concurrent BT + WiFi load",
            "Roaming issues between access points (sticky client)",
        ],
    },
    "WCN3998": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.73 Gbps",
        "bluetooth_version": "5.1",
        "common_failures": [
            "WPA3 handshake failures with certain router models",
            "Slow reconnect after airplane mode toggle",
            "MU-MIMO performance degradation with 3+ spatial streams",
        ],
    },
    "WCN3988": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 5",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "433 Mbps",
        "bluetooth_version": "5.1",
        "common_failures": [
            "Limited range on 5 GHz band (budget chipset)",
            "WiFi calling drops under network congestion",
            "Slow WiFi scan causing perceived connection delay",
        ],
    },
    "QCA6490": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "Antenna tuner mismatch causing signal attenuation",
            "6 GHz regulatory domain mismatch after region change",
            "TDLS link instability in WiFi Direct mode",
        ],
    },
    "QCA6595": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.2 Gbps",
        "bluetooth_version": "5.1",
        "common_failures": [
            "Automotive-grade chip — overheat in mobile enclosures",
            "Driver compatibility issues on non-automotive kernels",
            "Reduced sensitivity due to shielding differences",
        ],
    },
    "QCA6696": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "3.6 Gbps",
        "bluetooth_version": "5.3",
        "common_failures": [
            "High power draw in tri-band concurrent mode",
            "Firmware hangs during channel switch announcements",
            "Bluetooth LE Audio codec negotiation failures",
        ],
    },
    # ── Broadcom ──────────────────────────────────────────────────────────
    "BCM4389": {
        "manufacturer": "Broadcom",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "WiFi MAC address randomization conflicts with captive portals",
            "6 GHz preferred steering causing dropped connections",
            "Firmware assert crash (dongle trap) under high throughput",
        ],
    },
    "BCM4375": {
        "manufacturer": "Broadcom",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.73 Gbps",
        "bluetooth_version": "5.0",
        "common_failures": [
            "Bluetooth SCO audio codec fallback to CVSD",
            "P2P group formation timeout with legacy devices",
            "Country code enforcement causing 5 GHz band restriction",
        ],
    },
    "BCM4359": {
        "manufacturer": "Broadcom",
        "wifi_standard": "WiFi 5",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "866 Mbps",
        "bluetooth_version": "4.2",
        "common_failures": [
            "Legacy WPA2 authentication failures after security patches",
            "Scanning stall causing 'Saved' but unable to connect",
            "RSSI reporting inaccuracy at edge of coverage",
        ],
    },
    "BCM43752": {
        "manufacturer": "Broadcom",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.3",
        "common_failures": [
            "Initial 6 GHz discovery slow in dense AP environments",
            "BLE connection parameter update rejection by peripherals",
            "Low-latency gaming mode causing packet loss spikes",
        ],
    },
    "BCM4356": {
        "manufacturer": "Broadcom",
        "wifi_standard": "WiFi 5",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "867 Mbps",
        "bluetooth_version": "4.1",
        "common_failures": [
            "Outdated firmware causing WPA3 incompatibility",
            "Beacon loss detection too aggressive (frequent drops)",
            "HT40 mode disabled in regulatory-restricted regions",
        ],
    },
    # ── MediaTek ──────────────────────────────────────────────────────────
    "MT7921": {
        "manufacturer": "MediaTek",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.2 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "Linux kernel driver (mt7921e) firmware load timeout",
            "Bluetooth coexistence not tuned for mobile use cases",
            "Deep sleep recovery delay causing reconnect lag",
        ],
    },
    "MT7922": {
        "manufacturer": "MediaTek",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "6 GHz regulatory support missing in older firmware",
            "Occasional scan result duplication in scan lists",
            "ACS channel selection suboptimal in tri-band routers",
        ],
    },
    "MT6639": {
        "manufacturer": "MediaTek",
        "wifi_standard": "WiFi 7",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "6.5 Gbps",
        "bluetooth_version": "5.4",
        "common_failures": [
            "WiFi 7 MLO (Multi-Link Operation) instability on early silicon",
            "4K QAM modulation fallback to 1024-QAM under noise",
            "Bluetooth 5.4 PBP profile not yet broadly supported",
        ],
    },
    "MT7663": {
        "manufacturer": "MediaTek",
        "wifi_standard": "WiFi 5",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "433 Mbps",
        "bluetooth_version": "5.0",
        "common_failures": [
            "1x1 SISO only — limited throughput and range",
            "Bluetooth reconnection slow after WiFi band switch",
            "Random disconnects in power-save mode",
        ],
    },
    # ── Intel ─────────────────────────────────────────────────────────────
    "AX211": {
        "manufacturer": "Intel",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.3",
        "common_failures": [
            "Primarily a laptop chip — rare in mobile phones",
            "CNVi interface requires Intel CPU (not standalone)",
            "6 GHz intermittent on certain access point vendors",
        ],
    },
    "AX210": {
        "manufacturer": "Intel",
        "wifi_standard": "WiFi 6E",
        "bands": ["2.4 GHz", "5 GHz", "6 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "Rarely used in phones — primarily PC/tablet market",
            "Bluetooth firmware coredump under rapid on/off cycling",
            "Wi-Fi Direct P2P invitation failures with Android peers",
        ],
    },
    "AX201": {
        "manufacturer": "Intel",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "2.4 Gbps",
        "bluetooth_version": "5.0",
        "common_failures": [
            "CNVi companion chip — not used standalone in phones",
            "DHCP renewal stalls on enterprise WPA2-EAP networks",
            "BT audio profile priority conflict with WiFi throughput",
        ],
    },
    # ── Samsung (Shannon) ─────────────────────────────────────────────────
    "S5E5515": {
        "manufacturer": "Samsung (Shannon)",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.2 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "Proprietary Samsung WiFi driver — limited open-source support",
            "Intermittent disconnect on non-Samsung routers with band steering",
            "Bluetooth LDAC codec stutter at 990 kbps quality setting",
        ],
    },
    # ── Realtek ───────────────────────────────────────────────────────────
    "RTL8822CE": {
        "manufacturer": "Realtek",
        "wifi_standard": "WiFi 5",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "867 Mbps",
        "bluetooth_version": "5.0",
        "common_failures": [
            "Driver instability in custom ROM kernels",
            "2.4 GHz TX power limited to meet FCC SAR regulations",
            "BT coexistence causes WiFi throughput reduction up to 40%",
        ],
    },
    "RTL8852AE": {
        "manufacturer": "Realtek",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.2 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "Firmware blob compatibility issues across kernel versions",
            "Occasional beacon loss in PS (power save) mode",
            "BLE advertising conflicts when WiFi P2P is active",
        ],
    },
    "RTL8852BE": {
        "manufacturer": "Realtek",
        "wifi_standard": "WiFi 6",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "1.2 Gbps",
        "bluetooth_version": "5.2",
        "common_failures": [
            "PCIe bus link recovery timeout after deep sleep",
            "Scan offload failure causing foreground scan stalls",
            "Regulatory domain override needed for some regions",
        ],
    },
    "QCA6174": {
        "manufacturer": "Qualcomm",
        "wifi_standard": "WiFi 5",
        "bands": ["2.4 GHz", "5 GHz"],
        "max_speed": "867 Mbps",
        "bluetooth_version": "4.2",
        "common_failures": [
            "WoWLAN (Wake on WLAN) unreliable on older firmware",
            "MCS index capped at 7 on 20 MHz channels",
            "Bluetooth HFP profile audio quality degradation",
        ],
    },
}


# ---------------------------------------------------------------------------
#  Bluetooth IC Knowledge Database (separate BT controllers)
# ---------------------------------------------------------------------------
BLUETOOTH_IC_DATABASE: Dict[str, Dict[str, Any]] = {
    "QCC5171": {
        "manufacturer": "Qualcomm",
        "bt_version": "5.3",
        "type": "Bluetooth Audio SoC",
        "features": ["aptX Adaptive", "aptX Lossless", "LC3", "ANC"],
        "common_failures": [
            "aptX Adaptive fallback to SBC under interference",
            "ANC microphone calibration drift over time",
            "TWS earbud desync during codec switch",
        ],
    },
    "QCC5181": {
        "manufacturer": "Qualcomm",
        "bt_version": "5.4",
        "type": "Bluetooth Audio SoC (Flagship)",
        "features": ["aptX Lossless", "Snapdragon Sound", "LE Audio", "spatial audio"],
        "common_failures": [
            "LE Audio broadcast sink mode not supported by all sources",
            "Spatial audio head-tracking latency on non-Snapdragon hosts",
            "Battery drain increase with lossless codec active",
        ],
    },
    "QCC3034": {
        "manufacturer": "Qualcomm",
        "bt_version": "5.0",
        "type": "Bluetooth Audio SoC (Mid-range)",
        "features": ["aptX", "aptX HD", "AAC"],
        "common_failures": [
            "aptX HD not negotiated with non-Qualcomm sources",
            "Multipoint connection switching delay up to 2 seconds",
            "Power-off pop noise on analog output stage",
        ],
    },
    "QCC3040": {
        "manufacturer": "Qualcomm",
        "bt_version": "5.2",
        "type": "Bluetooth Audio SoC (TWS)",
        "features": ["aptX Adaptive", "TrueWireless Mirroring", "ANC"],
        "common_failures": [
            "TWS mirroring handoff glitch during head movement",
            "Charging case communication timeout (I2C fault)",
            "ANC wind noise cancellation ineffective below 200 Hz",
        ],
    },
    "BCM2076": {
        "manufacturer": "Broadcom",
        "bt_version": "4.1",
        "type": "Bluetooth + FM combo",
        "features": ["A2DP", "HFP", "FM receiver", "BLE"],
        "common_failures": [
            "FM antenna requires headphone cable — no built-in antenna",
            "BLE advertising interval non-compliant with newer specs",
            "Audio routing conflict between BT SCO and FM path",
        ],
    },
}


# ---------------------------------------------------------------------------
#  NFC Controller Knowledge Database
# ---------------------------------------------------------------------------
NFC_CONTROLLER_DATABASE: Dict[str, Dict[str, Any]] = {
    # ── NXP ───────────────────────────────────────────────────────────────
    "PN557": {
        "manufacturer": "NXP",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "ISO-DEP", "NFC-DEP",
                      "MIFARE Classic", "MIFARE DESFire", "eSE (embedded Secure Element)"],
        "common_failures": [
            "eSE applet communication timeout (SWP interface fault)",
            "NFC field strength reduced — antenna flex cable damage",
            "Reader mode fails on MIFARE Classic with diversified keys",
        ],
    },
    "PN553": {
        "manufacturer": "NXP",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "ISO-DEP",
                      "MIFARE Classic", "MIFARE DESFire", "SWP/DWP"],
        "common_failures": [
            "I2C communication error with host processor (NACK)",
            "Peer-to-peer LLCP link drops on large NDEF payloads",
            "Card emulation routing table corruption after OTA update",
        ],
    },
    "PN548": {
        "manufacturer": "NXP",
        "nfc_standard": "NFC Forum Type 1-4",
        "features": ["NFC-A", "NFC-B", "NFC-F", "ISO-DEP", "MIFARE Classic"],
        "common_failures": [
            "Older controller — slower tag discovery latency",
            "No NFC-V (ISO 15693) support for inventory tags",
            "Firmware update path limited on locked bootloaders",
        ],
    },
    "SN110": {
        "manufacturer": "NXP",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "ISO-DEP", "NFC-DEP",
                      "eSE", "UICC SE", "T4T NDEF"],
        "common_failures": [
            "eSE secure channel key rotation failure",
            "Transit card emulation intermittent on low battery",
            "NFC field detection sensitivity reduced by metal case",
        ],
    },
    "SN220": {
        "manufacturer": "NXP",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "ISO-DEP", "NFC-DEP",
                      "eSE", "UWB ranging integration", "UICC SE v2"],
        "common_failures": [
            "UWB+NFC combined ranging unstable on initial firmware",
            "Secure Element OS update failure (GP spec mismatch)",
            "Reader mode power consumption higher than predecessor",
        ],
    },
    # ── Samsung ───────────────────────────────────────────────────────────
    "S3NRN4V": {
        "manufacturer": "Samsung LSI",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "eSE",
                      "Samsung Pay MST emulation"],
        "common_failures": [
            "MST (Magnetic Secure Transmission) coil interference with NFC",
            "Samsung Pay tokenization failure after firmware rollback",
            "Limited third-party HCE applet compatibility",
        ],
    },
    "S3NRN82": {
        "manufacturer": "Samsung LSI",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "eSE",
                      "Samsung Pay", "UWB coexistence"],
        "common_failures": [
            "eSE GP (GlobalPlatform) applet install failure",
            "NFC tag write lock permanent after accidental lock command",
            "Power-on self-test failure after battery disconnect repair",
        ],
    },
    # ── STMicroelectronics ────────────────────────────────────────────────
    "ST21NFC": {
        "manufacturer": "STMicroelectronics",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "ISO-DEP",
                      "SWP UICC", "HCE"],
        "common_failures": [
            "I2C clock stretching timeout on some host SoCs",
            "NDEF format command fails on Type 2 tags with TLV errors",
            "ST proprietary HAL required — AOSP NFC stack incompatible",
        ],
    },
    "ST54J": {
        "manufacturer": "STMicroelectronics",
        "nfc_standard": "NFC Forum Type 1-5",
        "features": ["NFC-A", "NFC-B", "NFC-F", "NFC-V", "ISO-DEP",
                      "eSE (ST Secure)", "SIM-based SE", "GP 2.3"],
        "common_failures": [
            "eSE provisioning failure in non-ST trust chain",
            "NFC polling loop timing conflict with custom kernels",
            "Secure Element firmware update requires ST factory tooling",
        ],
    },
}


# ---------------------------------------------------------------------------
#  Cellular modem reference (for baseband identification)
# ---------------------------------------------------------------------------
CELLULAR_MODEM_DATABASE: Dict[str, Dict[str, Any]] = {
    "SDX55": {
        "manufacturer": "Qualcomm",
        "generation": "5G Sub-6 + mmWave",
        "max_dl": "7.5 Gbps",
        "bands_5g": "n1, n2, n3, n5, n7, n25, n41, n66, n71, n77, n78, n79, n260, n261",
    },
    "SDX65": {
        "manufacturer": "Qualcomm",
        "generation": "5G Sub-6 + mmWave (10 Gbps)",
        "max_dl": "10 Gbps",
        "bands_5g": "n1, n2, n3, n5, n7, n25, n41, n66, n71, n77, n78, n79, n260, n261",
    },
    "SDX75": {
        "manufacturer": "Qualcomm",
        "generation": "5G-Advanced",
        "max_dl": "12 Gbps",
        "bands_5g": "n1-n79, n257, n258, n260, n261 (full NR band support)",
    },
    "Exynos5123": {
        "manufacturer": "Samsung",
        "generation": "5G Sub-6 + mmWave",
        "max_dl": "5.1 Gbps",
        "bands_5g": "n1, n3, n5, n7, n28, n41, n66, n77, n78, n79, n260, n261",
    },
    "Exynos5300": {
        "manufacturer": "Samsung",
        "generation": "5G Sub-6 + mmWave",
        "max_dl": "5.1 Gbps",
        "bands_5g": "n1, n3, n5, n7, n28, n41, n66, n77, n78, n79, n257, n258",
    },
    "Helio_M80": {
        "manufacturer": "MediaTek",
        "generation": "5G Sub-6 + mmWave",
        "max_dl": "7.67 Gbps",
        "bands_5g": "n1, n2, n3, n5, n7, n25, n41, n66, n71, n77, n78, n79",
    },
    "T700": {
        "manufacturer": "MediaTek",
        "generation": "5G Sub-6",
        "max_dl": "4.7 Gbps",
        "bands_5g": "n1, n3, n5, n7, n28, n41, n77, n78, n79",
    },
}


# ---------------------------------------------------------------------------
#  GPS / GNSS chipset reference
# ---------------------------------------------------------------------------
GPS_CHIPSET_DATABASE: Dict[str, Dict[str, Any]] = {
    "BCM47765": {
        "manufacturer": "Broadcom",
        "constellations": ["GPS", "GLONASS", "Galileo", "BeiDou", "QZSS", "NavIC"],
        "dual_frequency": True,
        "accuracy": "sub-meter (L1+L5 dual-frequency)",
    },
    "BCM47755": {
        "manufacturer": "Broadcom",
        "constellations": ["GPS", "GLONASS", "Galileo", "BeiDou", "QZSS"],
        "dual_frequency": True,
        "accuracy": "sub-meter (L1+L5)",
    },
    "QMC5883": {
        "manufacturer": "QST Corporation",
        "constellations": ["GPS", "GLONASS"],
        "dual_frequency": False,
        "accuracy": "3-5 meters (single frequency L1)",
    },
    "Adreno_GNSS": {
        "manufacturer": "Qualcomm (integrated)",
        "constellations": ["GPS", "GLONASS", "Galileo", "BeiDou", "QZSS", "NavIC"],
        "dual_frequency": True,
        "accuracy": "sub-meter (L1+L5 with carrier phase)",
    },
}


# ---------------------------------------------------------------------------
#  Signal quality thresholds (for health scoring)
# ---------------------------------------------------------------------------
WIFI_SIGNAL_THRESHOLDS = {
    "excellent": -50,   # dBm and above
    "good": -60,
    "fair": -70,
    "poor": -80,
    "unusable": -90,
}

CELLULAR_RSRP_THRESHOLDS = {
    "excellent": -80,
    "good": -90,
    "fair": -100,
    "poor": -110,
    "no_signal": -120,
}

CELLULAR_SINR_THRESHOLDS = {
    "excellent": 20,  # dB
    "good": 13,
    "fair": 0,
    "poor": -5,
}


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WiFiInfo:
    """WiFi subsystem diagnostic results."""
    enabled: bool = False
    connected: bool = False
    ssid: str = ""
    bssid: str = ""
    mac_address: str = ""
    ip_address: str = ""
    signal_strength: int = 0   # dBm
    link_speed: str = ""
    frequency: str = ""
    wifi_standard: str = ""
    chipset: str = ""
    chipset_manufacturer: str = ""
    channel: str = ""
    status: str = "Unknown"
    common_failures: List[str] = field(default_factory=list)


@dataclass
class BluetoothInfo:
    """Bluetooth subsystem diagnostic results."""
    enabled: bool = False
    address: str = ""
    chipset: str = ""
    bt_version: str = ""
    paired_devices: int = 0
    status: str = "Unknown"


@dataclass
class GPSInfo:
    """GPS / GNSS subsystem diagnostic results."""
    enabled: bool = False
    providers: List[str] = field(default_factory=list)
    satellites_visible: int = 0
    satellites_used: int = 0
    fix_accuracy: str = ""
    chipset: str = ""
    supports_glonass: bool = False
    supports_galileo: bool = False
    supports_beidou: bool = False
    status: str = "Unknown"


@dataclass
class NFCInfo:
    """NFC subsystem diagnostic results."""
    present: bool = False
    enabled: bool = False
    controller: str = ""
    controller_manufacturer: str = ""
    firmware_version: str = ""
    status: str = "Unknown"


@dataclass
class CellularInfo:
    """Cellular modem diagnostic results."""
    signal_strength_dbm: int = 0
    signal_quality: str = ""
    network_type: str = ""     # LTE, 5G NR, etc.
    rsrp: str = ""
    rsrq: str = ""
    sinr: str = ""
    band: str = ""
    operator: str = ""
    status: str = "Unknown"


@dataclass
class ConnectivityTestResult:
    """Top-level result aggregating all connectivity subsystem tests."""
    connected: bool = False
    error: Optional[str] = None
    wifi: WiFiInfo = field(default_factory=WiFiInfo)
    bluetooth: BluetoothInfo = field(default_factory=BluetoothInfo)
    gps: GPSInfo = field(default_factory=GPSInfo)
    nfc: NFCInfo = field(default_factory=NFCInfo)
    cellular: CellularInfo = field(default_factory=CellularInfo)
    overall_health: str = "Unknown"
    health_score: int = 0
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
#  Helper — progress notification
# ---------------------------------------------------------------------------

def _notify(callback: ProgressCallback, pct: float, msg: str) -> None:
    """Fire the progress callback if provided."""
    if callback is not None:
        try:
            callback(pct, msg)
        except Exception:
            logger.debug("Progress callback raised; ignoring", exc_info=True)


# ---------------------------------------------------------------------------
#  Helper — ADB command execution
# ---------------------------------------------------------------------------

def _adb(cmd: str) -> str:
    """Run ``adb shell <cmd>`` and return stripped stdout.

    Returns an empty string on any error (timeout, non-zero exit, etc.)
    so callers can safely parse without try/except.
    """
    try:
        proc = subprocess.run(
            f"adb shell {cmd}",
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        logger.warning("ADB command timed out: %s", cmd)
        return ""
    except FileNotFoundError:
        logger.error("adb binary not found on PATH")
        return ""
    except Exception as exc:
        logger.warning("ADB command failed (%s): %s", cmd, exc)
        return ""


def _adb_host(cmd: str) -> str:
    """Run an ADB host command (not ``shell``) and return stdout.

    Used for commands like ``adb devices`` that don't need a device shell.
    """
    try:
        proc = subprocess.run(
            f"adb {cmd}",
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception as exc:
        logger.warning("ADB host command failed (%s): %s", cmd, exc)
        return ""


# ---------------------------------------------------------------------------
#  Step 0 — ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection(callback: ProgressCallback) -> Tuple[bool, str]:
    """Verify ADB connectivity.  Returns ``(connected, error_or_empty)``."""
    _notify(callback, 0.0, "Checking ADB connection...")
    output = _adb_host("devices")
    if not output:
        return False, "Cannot run 'adb devices' — ensure Android Platform Tools are on PATH"

    lines = [ln for ln in output.splitlines() if "\tdevice" in ln]
    if not lines:
        unauthorized = [ln for ln in output.splitlines() if "\tunauthorized" in ln]
        if unauthorized:
            return False, "Device connected but USB Debugging not authorized — accept the prompt on the phone"
        return False, "No ADB device detected — connect a device with USB Debugging enabled"

    serial = lines[0].split("\t")[0]
    logger.info("ADB device connected: %s", serial)
    _notify(callback, 3.0, f"ADB connected — serial {serial}")
    return True, ""


# ---------------------------------------------------------------------------
#  Step 1 — WiFi diagnostics
# ---------------------------------------------------------------------------

def _identify_wifi_chipset(dump: str) -> Tuple[str, Dict[str, Any]]:
    """Attempt to identify the WiFi chipset from various ADB outputs.

    Searches the combined dump text for known chipset identifiers from
    the WIFI_CHIPSET_DATABASE.

    Returns
    -------
    (chipset_name, chipset_info_dict)   or  ("", {})
    """
    upper = dump.upper()
    for chipset_id, info in WIFI_CHIPSET_DATABASE.items():
        # Check for the chipset ID anywhere in the collected data
        if chipset_id.upper() in upper:
            logger.info("WiFi chipset identified: %s", chipset_id)
            return chipset_id, info

    # Heuristic fallback: look for manufacturer keywords
    mfg_hints = [
        ("qca", "Qualcomm"),
        ("wcn", "Qualcomm"),
        ("bcm", "Broadcom"),
        ("brcm", "Broadcom"),
        ("mt76", "MediaTek"),
        ("mt66", "MediaTek"),
        ("iwl", "Intel"),
        ("rtl88", "Realtek"),
        ("rtw", "Realtek"),
        ("s5e", "Samsung (Shannon)"),
    ]
    lower = dump.lower()
    for hint, mfg in mfg_hints:
        if hint in lower:
            logger.info("WiFi chipset manufacturer heuristic: %s", mfg)
            return f"Unknown ({mfg})", {"manufacturer": mfg, "common_failures": []}
    return "", {}


def _parse_wifi_frequency_to_channel(freq_mhz: int) -> str:
    """Convert a WiFi frequency in MHz to the human-readable channel number."""
    # 2.4 GHz band
    if 2412 <= freq_mhz <= 2484:
        if freq_mhz == 2484:
            return "14"
        return str((freq_mhz - 2407) // 5)
    # 5 GHz band
    if 5170 <= freq_mhz <= 5835:
        return str((freq_mhz - 5000) // 5)
    # 6 GHz band (WiFi 6E)
    if 5955 <= freq_mhz <= 7115:
        return str((freq_mhz - 5950) // 5)
    return str(freq_mhz)


def _classify_wifi_signal(dbm: int) -> str:
    """Return a human-readable quality label for a WiFi RSSI value."""
    if dbm >= WIFI_SIGNAL_THRESHOLDS["excellent"]:
        return "Excellent"
    if dbm >= WIFI_SIGNAL_THRESHOLDS["good"]:
        return "Good"
    if dbm >= WIFI_SIGNAL_THRESHOLDS["fair"]:
        return "Fair"
    if dbm >= WIFI_SIGNAL_THRESHOLDS["poor"]:
        return "Poor"
    return "Unusable"


def _detect_wifi(callback: ProgressCallback) -> Tuple[WiFiInfo, List[str]]:
    """Gather WiFi subsystem information via ADB.

    Returns the populated WiFiInfo dataclass and a list of warning strings.
    """
    info = WiFiInfo()
    warnings: List[str] = []
    _notify(callback, 5.0, "Probing WiFi subsystem...")

    # -- Collect raw data from multiple sources --
    wifi_dump = _adb("dumpsys wifi")
    connectivity_dump = _adb("dumpsys connectivity")
    mac_addr = _adb("cat /sys/class/net/wlan0/address")
    wlan_params = _adb("cat /sys/module/wlan/parameters/* 2>/dev/null")
    ip_info = _adb("ip addr show wlan0")
    wifi_iface = _adb("getprop wifi.interface")
    wifi_hw = _adb("getprop ro.hardware.wifi")

    combined_dump = "\n".join([wifi_dump, connectivity_dump, wlan_params,
                               wifi_iface, wifi_hw])

    _notify(callback, 10.0, "Parsing WiFi state...")

    # -- Enabled state --
    if re.search(r"Wi-Fi is (\S+)", wifi_dump):
        state_match = re.search(r"Wi-Fi is (\S+)", wifi_dump)
        if state_match:
            state_str = state_match.group(1).lower()
            info.enabled = state_str in ("enabled", "connected", "on")

    if not info.enabled:
        # Fallback: check for wlan0 interface existence
        if "wlan0" in ip_info:
            info.enabled = True

    # -- MAC address --
    if mac_addr and re.match(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac_addr):
        info.mac_address = mac_addr.strip()
    else:
        # Fallback: parse from ip addr output
        mac_match = re.search(r"link/ether\s+([0-9a-fA-F:]{17})", ip_info)
        if mac_match:
            info.mac_address = mac_match.group(1)

    # -- Connection details from dumpsys wifi --
    # Look for the current WifiInfo block
    ssid_match = re.search(r'SSID:\s*"?([^"\n,]+)"?', wifi_dump)
    if ssid_match:
        info.ssid = ssid_match.group(1).strip()
        info.connected = True

    bssid_match = re.search(r'BSSID:\s*([0-9a-fA-F:]{17})', wifi_dump)
    if bssid_match:
        info.bssid = bssid_match.group(1)

    # IP address from wlan0
    ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', ip_info)
    if ip_match:
        info.ip_address = ip_match.group(1)

    # Signal strength (RSSI)
    rssi_match = re.search(r'RSSI:\s*(-?\d+)', wifi_dump)
    if rssi_match:
        info.signal_strength = int(rssi_match.group(1))

    # Link speed
    speed_match = re.search(r'(?:Link speed|Tx Link speed):\s*(\d+\s*Mbps)', wifi_dump)
    if speed_match:
        info.link_speed = speed_match.group(1)

    # Frequency
    freq_match = re.search(r'Frequency:\s*(\d+)', wifi_dump)
    if freq_match:
        freq_mhz = int(freq_match.group(1))
        info.frequency = f"{freq_mhz} MHz"
        info.channel = _parse_wifi_frequency_to_channel(freq_mhz)
        # Determine band category
        if freq_mhz > 5950:
            info.wifi_standard = "WiFi 6E (6 GHz)"
        elif freq_mhz > 5000:
            info.wifi_standard = "WiFi 5/6 (5 GHz)"
        else:
            info.wifi_standard = "WiFi (2.4 GHz)"

    _notify(callback, 15.0, "Identifying WiFi chipset...")

    # -- Chipset identification --
    chipset_id, chipset_info = _identify_wifi_chipset(combined_dump)
    if chipset_id:
        info.chipset = chipset_id
        info.chipset_manufacturer = chipset_info.get("manufacturer", "")
        info.common_failures = chipset_info.get("common_failures", [])
        # Override wifi_standard with chipset database if we have it
        if "wifi_standard" in chipset_info and not info.wifi_standard:
            info.wifi_standard = chipset_info["wifi_standard"]

    # -- Status and warnings --
    if info.enabled and info.connected:
        if info.signal_strength != 0:
            quality = _classify_wifi_signal(info.signal_strength)
            info.status = f"Connected — Signal {quality} ({info.signal_strength} dBm)"
            if info.signal_strength < WIFI_SIGNAL_THRESHOLDS["poor"]:
                warnings.append(
                    f"WiFi signal very weak ({info.signal_strength} dBm) — "
                    f"possible antenna damage or shielding issue"
                )
        else:
            info.status = "Connected"
    elif info.enabled:
        info.status = "Enabled but not connected"
        warnings.append("WiFi is enabled but not connected to any network")
    else:
        info.status = "Disabled or not detected"
        warnings.append("WiFi subsystem appears disabled or absent")

    # Check for MAC address anomalies
    if info.mac_address and info.mac_address.startswith("02:"):
        warnings.append(
            "WiFi MAC address appears randomized (locally administered) — "
            "hardware MAC may be obscured by Android privacy feature"
        )

    _notify(callback, 20.0, f"WiFi: {info.status}")
    return info, warnings


# ---------------------------------------------------------------------------
#  Step 2 — Bluetooth diagnostics
# ---------------------------------------------------------------------------

def _identify_bt_chipset(dump: str) -> Tuple[str, Dict[str, Any]]:
    """Identify Bluetooth IC from dumpsys and property data."""
    upper = dump.upper()
    # First check dedicated BT ICs
    for ic_id, ic_info in BLUETOOTH_IC_DATABASE.items():
        if ic_id.upper() in upper:
            return ic_id, ic_info
    # Then check WiFi combo chips (they include BT)
    for chipset_id, chipset_info in WIFI_CHIPSET_DATABASE.items():
        if chipset_id.upper() in upper:
            return chipset_id, chipset_info
    return "", {}


def _detect_bluetooth(callback: ProgressCallback) -> Tuple[BluetoothInfo, List[str]]:
    """Gather Bluetooth subsystem information via ADB."""
    info = BluetoothInfo()
    warnings: List[str] = []
    _notify(callback, 22.0, "Probing Bluetooth subsystem...")

    bt_dump = _adb("dumpsys bluetooth_manager")
    bt_addr_sysfs = _adb("cat /sys/class/bluetooth/*/address 2>/dev/null")
    bt_hw = _adb("getprop ro.hardware.bt")
    bt_chip = _adb("getprop bluetooth.hci.chipname")
    bt_addr_settings = _adb("settings get secure bluetooth_address")

    combined = "\n".join([bt_dump, bt_hw, bt_chip])

    _notify(callback, 27.0, "Parsing Bluetooth state...")

    # -- Enabled state --
    enabled_match = re.search(r'enabled:\s*(true|false)', bt_dump, re.IGNORECASE)
    if enabled_match:
        info.enabled = enabled_match.group(1).lower() == "true"
    else:
        # Fallback: check for "state:" in dumpsys
        state_match = re.search(r'Bluetooth adapter state:\s*(\S+)', bt_dump, re.IGNORECASE)
        if state_match:
            info.enabled = state_match.group(1).upper() in ("ON", "STATE_ON", "12")
        elif re.search(r'isEnabled\(\):\s*true', bt_dump, re.IGNORECASE):
            info.enabled = True
        elif "AdapterState" in bt_dump and "ON" in bt_dump:
            info.enabled = True

    # -- Bluetooth address --
    if bt_addr_settings and re.match(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", bt_addr_settings):
        info.address = bt_addr_settings.strip()
    elif bt_addr_sysfs and re.match(r"([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", bt_addr_sysfs):
        info.address = bt_addr_sysfs.strip()
    else:
        addr_match = re.search(r'address:\s*([0-9a-fA-F:]{17})', bt_dump)
        if addr_match:
            info.address = addr_match.group(1)

    # -- Paired devices count --
    bonded_match = re.search(r'Bonded devices:\s*(\d+)', bt_dump)
    if bonded_match:
        info.paired_devices = int(bonded_match.group(1))
    else:
        # Count bonded device entries
        bonded_entries = re.findall(r'Bond state:\s*bonded', bt_dump, re.IGNORECASE)
        info.paired_devices = len(bonded_entries)

    _notify(callback, 32.0, "Identifying Bluetooth chipset...")

    # -- Chipset identification --
    chipset_id, chipset_info = _identify_bt_chipset(combined)
    if chipset_id:
        info.chipset = chipset_id
        info.bt_version = chipset_info.get("bt_version",
                                           chipset_info.get("bluetooth_version", ""))
    elif bt_chip:
        info.chipset = bt_chip

    # -- Status and warnings --
    if info.enabled:
        info.status = "Enabled"
        if info.paired_devices > 0:
            info.status += f" — {info.paired_devices} paired device(s)"
    else:
        info.status = "Disabled or not detected"
        warnings.append("Bluetooth appears disabled — enable it for full diagnostics")

    if info.address and info.address.upper() in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
        warnings.append(
            "Bluetooth address is invalid (all zeros or all FFs) — "
            "possible BT IC failure or missing calibration data"
        )
        info.status = "ERROR — Invalid BT address"

    _notify(callback, 35.0, f"Bluetooth: {info.status}")
    return info, warnings


# ---------------------------------------------------------------------------
#  Step 3 — GPS / GNSS diagnostics
# ---------------------------------------------------------------------------

def _detect_gps(callback: ProgressCallback) -> Tuple[GPSInfo, List[str]]:
    """Gather GPS / GNSS subsystem information via ADB."""
    info = GPSInfo()
    warnings: List[str] = []
    _notify(callback, 37.0, "Probing GPS/GNSS subsystem...")

    location_dump = _adb("dumpsys location")
    gnss_type = _adb("cat /sys/class/gnss/*/type 2>/dev/null")
    gps_hw = _adb("getprop ro.hardware.gps")

    _notify(callback, 42.0, "Parsing GPS state...")

    # -- Enabled state --
    if re.search(r'Location Mode:\s*(high|battery)', location_dump, re.IGNORECASE):
        info.enabled = True
    elif re.search(r'location is currently enabled', location_dump, re.IGNORECASE):
        info.enabled = True
    elif re.search(r'gps.*enabled', location_dump, re.IGNORECASE):
        info.enabled = True

    # -- Location providers --
    provider_matches = re.findall(
        r'(?:LocationProvider|provider)\[(\w+)\]', location_dump
    )
    if provider_matches:
        info.providers = list(set(provider_matches))
    else:
        # Fallback: look for known provider names
        for provider in ("gps", "network", "fused", "passive"):
            if provider in location_dump.lower():
                info.providers.append(provider)
        info.providers = list(set(info.providers))

    # -- Satellite information --
    # Look for GNSS satellite status in the dump
    svs_visible_match = re.search(r'Satellites visible:\s*(\d+)', location_dump)
    if svs_visible_match:
        info.satellites_visible = int(svs_visible_match.group(1))

    svs_used_match = re.search(r'Satellites used:\s*(\d+)', location_dump)
    if svs_used_match:
        info.satellites_used = int(svs_used_match.group(1))

    # Alternative: parse SV count from NMEA-like data
    sv_count_match = re.search(r'SvCount:\s*(\d+)', location_dump)
    if sv_count_match and info.satellites_visible == 0:
        info.satellites_visible = int(sv_count_match.group(1))

    # -- Fix accuracy --
    accuracy_match = re.search(r'Accuracy:\s*([\d.]+)', location_dump)
    if accuracy_match:
        info.fix_accuracy = f"{accuracy_match.group(1)} m"

    # -- Constellation support --
    dump_lower = location_dump.lower() + " " + gnss_type.lower()
    info.supports_glonass = any(kw in dump_lower for kw in ("glonass", "glo", "constellation=1"))
    info.supports_galileo = any(kw in dump_lower for kw in ("galileo", "gal", "constellation=2"))
    info.supports_beidou = any(kw in dump_lower for kw in ("beidou", "bds", "constellation=3"))

    # -- Chipset identification --
    if gps_hw:
        info.chipset = gps_hw
    elif gnss_type:
        info.chipset = gnss_type
    else:
        # Try to identify from dumpsys
        for chip_id, chip_info in GPS_CHIPSET_DATABASE.items():
            if chip_id.lower() in dump_lower:
                info.chipset = chip_id
                break

    _notify(callback, 47.0, "Evaluating GPS health...")

    # -- Status and warnings --
    if info.enabled:
        if info.satellites_visible > 0:
            info.status = f"Active — {info.satellites_visible} SVs visible, {info.satellites_used} in use"
            if info.satellites_used == 0 and info.satellites_visible > 3:
                warnings.append(
                    "GPS sees satellites but cannot get a fix — "
                    "possible almanac/ephemeris data issue or antenna obstruction"
                )
        elif "gps" in [p.lower() for p in info.providers]:
            info.status = "Enabled — GPS provider available (no satellite data currently)"
        else:
            info.status = "Enabled — no GPS provider found"
            warnings.append("Location is enabled but GPS provider not listed — GPS hardware may be faulty")
    else:
        info.status = "Location services disabled"
        warnings.append("Location services appear disabled — enable for GPS diagnostics")

    constellation_count = sum([info.supports_glonass, info.supports_galileo, info.supports_beidou])
    if info.enabled and constellation_count == 0:
        warnings.append(
            "No multi-constellation GNSS support detected — "
            "device may only support GPS L1 (reduced accuracy)"
        )

    _notify(callback, 50.0, f"GPS: {info.status}")
    return info, warnings


# ---------------------------------------------------------------------------
#  Step 4 — NFC diagnostics
# ---------------------------------------------------------------------------

def _identify_nfc_controller(dump: str) -> Tuple[str, Dict[str, Any]]:
    """Identify NFC controller from dumpsys and sysfs data."""
    upper = dump.upper()
    for ctrl_id, ctrl_info in NFC_CONTROLLER_DATABASE.items():
        if ctrl_id.upper() in upper:
            return ctrl_id, ctrl_info
    # Heuristic fallback by manufacturer keyword
    lower = dump.lower()
    nxp_keywords = ["nxp", "pn5", "sn1", "sn2", "nxpnci"]
    samsung_keywords = ["s3nrn", "sec_nfc", "samsung_nfc"]
    st_keywords = ["st21", "st54", "st_nfc", "stmicro"]
    for kw in nxp_keywords:
        if kw in lower:
            return "Unknown (NXP)", {"manufacturer": "NXP", "common_failures": []}
    for kw in samsung_keywords:
        if kw in lower:
            return "Unknown (Samsung)", {"manufacturer": "Samsung LSI", "common_failures": []}
    for kw in st_keywords:
        if kw in lower:
            return "Unknown (STMicro)", {"manufacturer": "STMicroelectronics", "common_failures": []}
    return "", {}


def _detect_nfc(callback: ProgressCallback) -> Tuple[NFCInfo, List[str]]:
    """Gather NFC subsystem information via ADB."""
    info = NFCInfo()
    warnings: List[str] = []
    _notify(callback, 52.0, "Probing NFC subsystem...")

    nfc_dump = _adb("dumpsys nfc")
    nfc_hw = _adb("getprop ro.hardware.nfc")
    nfc_sysfs = _adb("cat /sys/class/nfc/*/name 2>/dev/null")

    combined = "\n".join([nfc_dump, nfc_hw, nfc_sysfs])

    _notify(callback, 57.0, "Parsing NFC state...")

    # -- Presence detection --
    if nfc_dump and "NfcService" in nfc_dump:
        info.present = True
    elif nfc_hw:
        info.present = True
    elif nfc_sysfs:
        info.present = True
    elif "no nfc" not in nfc_dump.lower() and len(nfc_dump) > 20:
        info.present = True

    # -- Enabled state --
    enabled_match = re.search(r'mState=(\d+)', nfc_dump)
    if enabled_match:
        # NfcAdapter states: 1=OFF, 2=TURNING_ON, 3=ON, 4=TURNING_OFF
        info.enabled = enabled_match.group(1) == "3"
    else:
        enabled_str_match = re.search(r'NFC is (enabled|on)', nfc_dump, re.IGNORECASE)
        if enabled_str_match:
            info.enabled = True
        elif re.search(r'mIsNfcEnabled\s*=\s*true', nfc_dump, re.IGNORECASE):
            info.enabled = True

    # -- Firmware version --
    fw_match = re.search(r'(?:FW Version|Firmware)\s*[:=]\s*([\w.]+)', nfc_dump, re.IGNORECASE)
    if fw_match:
        info.firmware_version = fw_match.group(1)
    else:
        fw_match2 = re.search(r'(?:fw_ver|nci_ver)\s*[:=]\s*([\w.]+)', nfc_dump, re.IGNORECASE)
        if fw_match2:
            info.firmware_version = fw_match2.group(1)

    _notify(callback, 62.0, "Identifying NFC controller...")

    # -- Controller identification --
    ctrl_id, ctrl_info = _identify_nfc_controller(combined)
    if ctrl_id:
        info.controller = ctrl_id
        info.controller_manufacturer = ctrl_info.get("manufacturer", "")

    # -- Status and warnings --
    if info.present and info.enabled:
        info.status = "Present and enabled"
    elif info.present and not info.enabled:
        info.status = "Present but disabled"
        warnings.append("NFC hardware detected but currently disabled")
    else:
        info.status = "Not detected"
        # This might be normal for budget phones without NFC
        warnings.append(
            "NFC controller not detected — device may lack NFC hardware "
            "or the NFC service is not running"
        )

    if info.present and info.controller:
        info.status += f" — {info.controller}"

    _notify(callback, 65.0, f"NFC: {info.status}")
    return info, warnings


# ---------------------------------------------------------------------------
#  Step 5 — Cellular / Modem diagnostics
# ---------------------------------------------------------------------------

def _classify_rsrp(rsrp_dbm: int) -> str:
    """Return signal quality label from an LTE/NR RSRP value in dBm."""
    if rsrp_dbm >= CELLULAR_RSRP_THRESHOLDS["excellent"]:
        return "Excellent"
    if rsrp_dbm >= CELLULAR_RSRP_THRESHOLDS["good"]:
        return "Good"
    if rsrp_dbm >= CELLULAR_RSRP_THRESHOLDS["fair"]:
        return "Fair"
    if rsrp_dbm >= CELLULAR_RSRP_THRESHOLDS["poor"]:
        return "Poor"
    return "No signal"


def _parse_network_type(raw: str) -> str:
    """Normalise network type strings into user-friendly labels."""
    raw_upper = raw.upper().strip()
    net_type_map = {
        "LTE": "4G LTE",
        "LTE_CA": "4G LTE-Advanced (Carrier Aggregation)",
        "NR": "5G NR",
        "NR_NSA": "5G NR (Non-Standalone)",
        "NR_SA": "5G NR (Standalone)",
        "HSPAP": "3G HSPA+",
        "HSPA": "3G HSPA",
        "UMTS": "3G UMTS",
        "EDGE": "2G EDGE",
        "GPRS": "2G GPRS",
        "GSM": "2G GSM",
        "CDMA": "CDMA",
        "EVDO": "CDMA EV-DO",
        "EHRPD": "CDMA eHRPD",
        "IWLAN": "WiFi Calling (IWLAN)",
    }
    for key, label in net_type_map.items():
        if key in raw_upper:
            return label
    return raw if raw else "Unknown"


def _detect_cellular(callback: ProgressCallback) -> Tuple[CellularInfo, List[str]]:
    """Gather cellular modem information via ADB."""
    info = CellularInfo()
    warnings: List[str] = []
    _notify(callback, 67.0, "Probing cellular modem...")

    telephony_dump = _adb("dumpsys telephony.registry")
    baseband = _adb("getprop gsm.version.baseband")
    nitz = _adb("getprop gsm.nitz.time")
    phone_dump = _adb("dumpsys phone")

    combined = "\n".join([telephony_dump, phone_dump])

    _notify(callback, 72.0, "Parsing cellular signal data...")

    # -- Signal strength (RSSI / dBm) --
    # Look for SignalStrength in telephony registry
    sig_match = re.search(
        r'mSignalStrength\s*=\s*(-?\d+)', telephony_dump
    )
    if sig_match:
        info.signal_strength_dbm = int(sig_match.group(1))

    # -- RSRP (LTE/NR Reference Signal Received Power) --
    rsrp_match = re.search(r'(?:rsrp|mRsrp)\s*=\s*(-?\d+)', combined, re.IGNORECASE)
    if rsrp_match:
        rsrp_val = int(rsrp_match.group(1))
        info.rsrp = f"{rsrp_val} dBm"
        info.signal_quality = _classify_rsrp(rsrp_val)
        # Use RSRP for primary signal if we didn't get one
        if info.signal_strength_dbm == 0:
            info.signal_strength_dbm = rsrp_val

    # -- RSRQ (Reference Signal Received Quality) --
    rsrq_match = re.search(r'(?:rsrq|mRsrq)\s*=\s*(-?[\d.]+)', combined, re.IGNORECASE)
    if rsrq_match:
        info.rsrq = f"{rsrq_match.group(1)} dB"

    # -- SINR (Signal to Interference and Noise Ratio) --
    sinr_match = re.search(r'(?:sinr|mSinr|rssnr)\s*=\s*(-?[\d.]+)', combined, re.IGNORECASE)
    if sinr_match:
        info.sinr = f"{sinr_match.group(1)} dB"

    # -- Network type --
    net_type_match = re.search(
        r'(?:mDataNetworkType|mNetworkType|dataNetworkType)\s*=\s*(\S+)', combined
    )
    if net_type_match:
        info.network_type = _parse_network_type(net_type_match.group(1))
    else:
        # Try getprop based detection
        net_type_prop = _adb("getprop gsm.network.type")
        if net_type_prop:
            info.network_type = _parse_network_type(net_type_prop)

    # -- Band --
    band_match = re.search(r'(?:mBand|Band|earfcn)\s*=?\s*(\d+)', combined, re.IGNORECASE)
    if band_match:
        info.band = f"Band {band_match.group(1)}"

    # -- Operator --
    operator_match = re.search(
        r'(?:mOperatorAlphaLong|mOperatorName|operator)\s*=\s*([^\n,]+)',
        combined, re.IGNORECASE
    )
    if operator_match:
        info.operator = operator_match.group(1).strip()
    else:
        operator_prop = _adb("getprop gsm.sim.operator.alpha")
        if operator_prop:
            info.operator = operator_prop

    _notify(callback, 78.0, "Evaluating cellular health...")

    # -- Signal quality classification (fallback if RSRP didn't provide it) --
    if not info.signal_quality:
        if info.signal_strength_dbm != 0:
            # Generic RSSI classification
            rssi = info.signal_strength_dbm
            if rssi >= -70:
                info.signal_quality = "Excellent"
            elif rssi >= -85:
                info.signal_quality = "Good"
            elif rssi >= -100:
                info.signal_quality = "Fair"
            elif rssi >= -110:
                info.signal_quality = "Poor"
            else:
                info.signal_quality = "No signal"

    # -- Status and warnings --
    if info.network_type and info.network_type != "Unknown":
        info.status = f"{info.network_type}"
        if info.signal_quality:
            info.status += f" — Signal {info.signal_quality}"
        if info.operator:
            info.status += f" ({info.operator})"
    elif info.signal_strength_dbm != 0:
        info.status = f"Registered — {info.signal_strength_dbm} dBm"
    else:
        info.status = "No cellular signal detected or SIM absent"
        warnings.append(
            "No cellular signal data found — check if SIM is inserted and "
            "the device is not in airplane mode"
        )

    # Baseband firmware info
    if baseband:
        logger.info("Baseband version: %s", baseband)
        # Check for known modem chipsets
        for modem_id in CELLULAR_MODEM_DATABASE:
            if modem_id.lower() in baseband.lower():
                info.status += f" [Modem: {modem_id}]"
                break

    # Signal quality warnings
    if info.signal_quality == "Poor":
        warnings.append(
            f"Cellular signal is poor ({info.rsrp or str(info.signal_strength_dbm) + ' dBm'}) — "
            "may indicate antenna damage, RF filter issue, or weak coverage area"
        )
    elif info.signal_quality == "No signal":
        warnings.append(
            "No cellular signal detected — possible modem failure, "
            "missing/damaged antenna, or SIM card issue"
        )

    # Check SINR for interference
    if info.sinr:
        try:
            sinr_val = float(info.sinr.replace(" dB", ""))
            if sinr_val < CELLULAR_SINR_THRESHOLDS["poor"]:
                warnings.append(
                    f"SINR is very low ({info.sinr}) — heavy interference detected, "
                    "possible RF front-end or antenna tuner damage"
                )
        except ValueError:
            pass

    _notify(callback, 82.0, f"Cellular: {info.status}")
    return info, warnings


# ---------------------------------------------------------------------------
#  Step 6 — Overall health scoring
# ---------------------------------------------------------------------------

def _compute_health(
    wifi: WiFiInfo,
    bluetooth: BluetoothInfo,
    gps: GPSInfo,
    nfc: NFCInfo,
    cellular: CellularInfo,
    warnings: List[str],
) -> Tuple[int, str]:
    """Compute an overall connectivity health score (0-100) and summary label.

    Scoring weights:
      WiFi       — 30 points
      Bluetooth  — 20 points
      GPS        — 15 points
      NFC        — 10 points
      Cellular   — 25 points

    Deductions are applied for missing/disabled/faulty subsystems.
    """
    score = 0

    # -- WiFi (30 pts max) --
    if wifi.enabled:
        score += 10
        if wifi.connected:
            score += 10
            if wifi.signal_strength != 0:
                if wifi.signal_strength >= WIFI_SIGNAL_THRESHOLDS["good"]:
                    score += 10
                elif wifi.signal_strength >= WIFI_SIGNAL_THRESHOLDS["fair"]:
                    score += 7
                elif wifi.signal_strength >= WIFI_SIGNAL_THRESHOLDS["poor"]:
                    score += 3
                # else: 0 bonus
            else:
                score += 5  # Connected but no RSSI data — assume OK
        else:
            score += 5  # Enabled but not connected — hardware probably OK
    # WiFi disabled: 0 out of 30

    # -- Bluetooth (20 pts max) --
    if bluetooth.enabled:
        score += 12
        if bluetooth.address and bluetooth.address.upper() not in (
            "00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"
        ):
            score += 8
        else:
            score += 2  # Enabled but bad address
    # BT disabled: 0 out of 20

    # -- GPS (15 pts max) --
    if gps.enabled:
        score += 5
        if gps.satellites_visible > 0:
            score += 5
            if gps.satellites_used > 0:
                score += 5
            elif gps.satellites_visible >= 4:
                score += 2
        elif "gps" in [p.lower() for p in gps.providers]:
            score += 3  # Provider available even if no SV data now
    # GPS disabled: 0 out of 15

    # -- NFC (10 pts max) --
    if nfc.present:
        score += 5
        if nfc.enabled:
            score += 5
    elif nfc.status == "Not detected":
        # Many budget phones lack NFC — don't penalize too harshly
        score += 3

    # -- Cellular (25 pts max) --
    if cellular.signal_strength_dbm != 0 or cellular.network_type not in ("", "Unknown"):
        score += 10
        if cellular.signal_quality in ("Excellent", "Good"):
            score += 15
        elif cellular.signal_quality == "Fair":
            score += 10
        elif cellular.signal_quality == "Poor":
            score += 5
    # No cellular: 0 out of 25

    # -- Warning penalty --
    # Each warning deducts a small amount, capped at -15
    warning_deduction = min(len(warnings) * 3, 15)
    score = max(0, score - warning_deduction)

    # -- Summary label --
    if score >= 85:
        label = "Excellent — All connectivity subsystems healthy"
    elif score >= 70:
        label = "Good — Minor connectivity issues detected"
    elif score >= 50:
        label = "Fair — Some connectivity subsystems impaired"
    elif score >= 30:
        label = "Poor — Multiple connectivity faults detected"
    else:
        label = "Critical — Major connectivity hardware failure suspected"

    return score, label


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_connectivity_status(
    callback: ProgressCallback = None,
) -> ConnectivityTestResult:
    """Run the full connectivity diagnostic sequence.

    This is the main entry point for the connectivity testing module.
    It runs all five sub-tests in sequence:

    1. **WiFi** — chipset identification, link state, signal analysis
    2. **Bluetooth** — IC identification, address validation, pairing info
    3. **GPS/GNSS** — provider enumeration, satellite data, constellation support
    4. **NFC** — controller identification, firmware version, enable state
    5. **Cellular** — signal measurement (RSRP/RSRQ/SINR), network type

    Finally it computes an overall ``health_score`` (0-100) and
    ``overall_health`` summary string.

    Parameters
    ----------
    callback : callable, optional
        A callable ``(pct: float, msg: str) -> None`` invoked with progress
        updates.  *pct* ranges from 0 to 100.

    Returns
    -------
    ConnectivityTestResult
        Populated result dataclass with all sub-results and an overall
        health assessment.
    """
    result = ConnectivityTestResult()
    logger.info("Starting connectivity diagnostic sequence")

    # ── Step 0: ADB connection ──────────────────────────────────────────
    connected, err = _check_adb_connection(callback)
    if not connected:
        result.connected = False
        result.error = err
        result.overall_health = f"UNABLE TO TEST — {err}"
        _notify(callback, 100.0, f"Test aborted: {err}")
        return result
    result.connected = True

    try:
        all_warnings: List[str] = []

        # ── Step 1: WiFi ────────────────────────────────────────────────
        wifi_info, wifi_warnings = _detect_wifi(callback)
        result.wifi = wifi_info
        all_warnings.extend(wifi_warnings)

        # ── Step 2: Bluetooth ───────────────────────────────────────────
        bt_info, bt_warnings = _detect_bluetooth(callback)
        result.bluetooth = bt_info
        all_warnings.extend(bt_warnings)

        # ── Step 3: GPS / GNSS ──────────────────────────────────────────
        gps_info, gps_warnings = _detect_gps(callback)
        result.gps = gps_info
        all_warnings.extend(gps_warnings)

        # ── Step 4: NFC ─────────────────────────────────────────────────
        nfc_info, nfc_warnings = _detect_nfc(callback)
        result.nfc = nfc_info
        all_warnings.extend(nfc_warnings)

        # ── Step 5: Cellular ────────────────────────────────────────────
        cell_info, cell_warnings = _detect_cellular(callback)
        result.cellular = cell_info
        all_warnings.extend(cell_warnings)

        # ── Step 6: Overall health ──────────────────────────────────────
        _notify(callback, 85.0, "Computing overall connectivity health...")
        result.warnings = all_warnings
        score, label = _compute_health(
            result.wifi, result.bluetooth, result.gps,
            result.nfc, result.cellular, all_warnings,
        )
        result.health_score = score
        result.overall_health = label

        _notify(callback, 95.0, f"Health score: {score}/100 — {label}")
        logger.info(
            "Connectivity diagnostics complete — score=%d, health=%s, warnings=%d",
            score, label, len(all_warnings),
        )

    except Exception as exc:
        logger.exception("Unhandled error during connectivity diagnostics")
        result.error = f"Diagnostic error: {exc}"
        result.overall_health = f"ERROR — {exc}"
        result.warnings.append(f"Internal error during testing: {exc}")

    _notify(callback, 100.0, "Connectivity diagnostics complete")
    return result
