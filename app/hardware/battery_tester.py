"""
Advanced Battery Testing Module for Mooxy AI Fault Detector.

Performs deep battery diagnostics via ADB by reading sysfs power_supply
nodes, charging IC registers, thermistor data, and fast-charge protocol
information.  Results are structured into typed dataclasses that feed the
downstream fault-analysis engine.

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
#  Constants & reference databases
# ---------------------------------------------------------------------------

# Sysfs base paths probed in order of likelihood
BATTERY_SYSFS_PATHS: List[str] = [
    "/sys/class/power_supply/battery",
    "/sys/class/power_supply/bms",
    "/sys/class/power_supply/Battery",
]

USB_SYSFS_PATHS: List[str] = [
    "/sys/class/power_supply/usb",
    "/sys/class/power_supply/USB",
]

DC_SYSFS_PATHS: List[str] = [
    "/sys/class/power_supply/dc",
    "/sys/class/power_supply/DC",
    "/sys/class/power_supply/wireless",
]

CHARGER_SYSFS_PATHS: List[str] = [
    "/sys/class/power_supply/charger",
    "/sys/class/power_supply/main",
    "/sys/class/power_supply/parallel",
    "/sys/class/power_supply/smb5",
    "/sys/class/power_supply/smb1390",
    "/sys/class/power_supply/smb1396",
    "/sys/class/power_supply/charge_pump_master",
]

# ---------- Known Charging ICs ----------
KNOWN_CHARGING_ICS: Dict[str, Dict[str, str]] = {
    "SMB1390": {
        "manufacturer": "Qualcomm",
        "type": "Charge Pump",
        "description": "Qualcomm SMB1390 Charge Pump Divider",
        "max_power_w": "30",
    },
    "SMB1396": {
        "manufacturer": "Qualcomm",
        "type": "Charge Pump",
        "description": "Qualcomm SMB1396 Dual-Phase Charge Pump",
        "max_power_w": "45",
    },
    "SMB1398": {
        "manufacturer": "Qualcomm",
        "type": "Charge Pump",
        "description": "Qualcomm SMB1398 Triple Charge Pump",
        "max_power_w": "65",
    },
    "SMB1355": {
        "manufacturer": "Qualcomm",
        "type": "Parallel Charger",
        "description": "Qualcomm SMB1355 Parallel Charger",
        "max_power_w": "18",
    },
    "SMB1360": {
        "manufacturer": "Qualcomm",
        "type": "Linear Charger",
        "description": "Qualcomm SMB1360 Fuel Gauge + Charger",
        "max_power_w": "15",
    },
    "SMB5": {
        "manufacturer": "Qualcomm",
        "type": "Main Charger",
        "description": "Qualcomm SMB5 USB Type-C Charger",
        "max_power_w": "25",
    },
    "PM8150B": {
        "manufacturer": "Qualcomm",
        "type": "PMIC Charger",
        "description": "Qualcomm PM8150B Power Management IC",
        "max_power_w": "27",
    },
    "PM7250B": {
        "manufacturer": "Qualcomm",
        "type": "PMIC Charger",
        "description": "Qualcomm PM7250B Power Management IC",
        "max_power_w": "25",
    },
    "PM8350B": {
        "manufacturer": "Qualcomm",
        "type": "PMIC Charger",
        "description": "Qualcomm PM8350B Power Management IC",
        "max_power_w": "30",
    },
    "PM8550B": {
        "manufacturer": "Qualcomm",
        "type": "PMIC Charger",
        "description": "Qualcomm PM8550B Power Management IC",
        "max_power_w": "45",
    },
    "BQ25890": {
        "manufacturer": "Texas Instruments",
        "type": "Switch-Mode Charger",
        "description": "TI BQ25890 5A Buck-Boost Battery Charger",
        "max_power_w": "25",
    },
    "BQ25970": {
        "manufacturer": "Texas Instruments",
        "type": "Charge Pump",
        "description": "TI BQ25970 Dual-Phase Switched-Cap Converter",
        "max_power_w": "45",
    },
    "BQ25980": {
        "manufacturer": "Texas Instruments",
        "type": "Charge Pump",
        "description": "TI BQ25980 Flash Charge Converter",
        "max_power_w": "65",
    },
    "RT9471": {
        "manufacturer": "Richtek",
        "type": "Linear Charger",
        "description": "Richtek RT9471 Switching Battery Charger",
        "max_power_w": "15",
    },
    "SC8551": {
        "manufacturer": "SouthChip",
        "type": "Charge Pump",
        "description": "SouthChip SC8551 Direct Charge IC",
        "max_power_w": "100",
    },
    # MediaTek Charging ICs
    "MT6370": {"name": "MT6370", "manufacturer": "MediaTek", "max_input_v": 12000, "max_input_i": 3000, "max_charge_v": 4450, "max_charge_i": 5000, "features": ["PE+2.0", "PD", "Type-C", "OTG", "LED driver"]},
    "MT6371": {"name": "MT6371", "manufacturer": "MediaTek", "max_input_v": 12000, "max_input_i": 3000, "max_charge_v": 4450, "max_charge_i": 5000, "features": ["PE+3.0", "PD3.0", "PPS"]},
    "MT6360": {"name": "MT6360", "manufacturer": "MediaTek", "max_input_v": 14000, "max_input_i": 3250, "max_charge_v": 4600, "max_charge_i": 6000, "features": ["PE+2.0", "PD", "Type-C", "TCPC", "LED", "LDO", "Buck"]},
    "MT6362": {"name": "MT6362", "manufacturer": "MediaTek", "max_input_v": 14000, "max_input_i": 3250, "max_charge_v": 4600, "max_charge_i": 6000, "features": ["PE+4.0", "PD3.1", "PPS", "UFCS"]},
    # Samsung Charging ICs
    "SM5701": {"name": "SM5701", "manufacturer": "Samsung", "max_input_v": 9000, "max_input_i": 2000, "max_charge_v": 4350, "max_charge_i": 2100, "features": ["AFC", "OTG"]},
    "SM5714": {"name": "SM5714", "manufacturer": "Samsung/Silicon Mitus", "max_input_v": 12000, "max_input_i": 3000, "max_charge_v": 4400, "max_charge_i": 3150, "features": ["AFC", "PD", "Type-C"]},
    "S2MU106": {"name": "S2MU106", "manufacturer": "Samsung LSI", "max_input_v": 12000, "max_input_i": 3250, "max_charge_v": 4400, "max_charge_i": 3500, "features": ["AFC", "PD", "Super Fast Charging"]},
    "MFC_CHARGER": {"name": "MFC Charger", "manufacturer": "Samsung", "max_input_v": 12000, "max_input_i": 3000, "max_charge_v": 4400, "max_charge_i": 3000, "features": ["AFC", "PD", "WPC"]},
    # Huawei/HiSilicon Charging ICs
    "HI6523": {"name": "HI6523", "manufacturer": "HiSilicon", "max_input_v": 12000, "max_input_i": 4000, "max_charge_v": 4400, "max_charge_i": 4500, "features": ["SCP", "FCP", "PD"]},
    "HI6526": {"name": "HI6526", "manufacturer": "HiSilicon", "max_input_v": 20000, "max_input_i": 4000, "max_charge_v": 4450, "max_charge_i": 5000, "features": ["SCP", "FCP", "PD", "65W SuperCharge"]},
    # Unisoc Charging ICs
    "SC2730_CHG": {"name": "SC2730 Charger", "manufacturer": "Unisoc", "max_input_v": 6500, "max_input_i": 2000, "max_charge_v": 4400, "max_charge_i": 2000, "features": ["DCP"]},
}

# ---------- Fast Charge Protocol Signatures ----------
FAST_CHARGE_PROTOCOLS: Dict[str, Dict[str, Any]] = {
    "QC2.0": {
        "voltages_v": [5.0, 9.0, 12.0, 20.0],
        "max_current_a": 3.0,
        "max_wattage_w": 36.0,
        "identifiers": ["quick_charge", "qc2", "hvdcp"],
        "description": "Qualcomm Quick Charge 2.0",
    },
    "QC3.0": {
        "voltages_v": [3.6, 20.0],  # continuous range
        "max_current_a": 3.0,
        "max_wattage_w": 36.0,
        "identifiers": ["quick_charge_3", "qc3", "hvdcp_3"],
        "description": "Qualcomm Quick Charge 3.0 (200mV steps)",
    },
    "QC4.0": {
        "voltages_v": [3.3, 21.0],
        "max_current_a": 5.0,
        "max_wattage_w": 100.0,
        "identifiers": ["quick_charge_4", "qc4", "hvdcp_3p5"],
        "description": "Qualcomm Quick Charge 4.0 (USB-PD compatible)",
    },
    "QC5.0": {
        "voltages_v": [3.3, 20.0],
        "max_current_a": 5.0,
        "max_wattage_w": 100.0,
        "identifiers": ["quick_charge_5", "qc5"],
        "description": "Qualcomm Quick Charge 5.0 (100W+)",
    },
    "USB-PD": {
        "voltages_v": [5.0, 9.0, 15.0, 20.0],
        "max_current_a": 5.0,
        "max_wattage_w": 100.0,
        "identifiers": ["pd", "usb_pd", "power_delivery", "PD"],
        "description": "USB Power Delivery",
    },
    "USB-PD-PPS": {
        "voltages_v": [3.3, 21.0],
        "max_current_a": 5.0,
        "max_wattage_w": 100.0,
        "identifiers": ["pps", "pd_pps", "programmable"],
        "description": "USB PD Programmable Power Supply",
    },
    "VOOC": {
        "voltages_v": [5.0],
        "max_current_a": 4.0,
        "max_wattage_w": 20.0,
        "identifiers": ["vooc", "dash", "warp"],
        "description": "OPPO VOOC (low voltage, high current)",
    },
    "SuperVOOC": {
        "voltages_v": [10.0],
        "max_current_a": 6.5,
        "max_wattage_w": 65.0,
        "identifiers": ["supervooc", "super_vooc", "svooc"],
        "description": "OPPO SuperVOOC (dual-cell, high power)",
    },
    "SuperVOOC2.0": {
        "voltages_v": [10.0, 11.0],
        "max_current_a": 12.0,
        "max_wattage_w": 120.0,
        "identifiers": ["supervooc2", "svooc2"],
        "description": "OPPO SuperVOOC 2.0 (120W+)",
    },
    "Warp": {
        "voltages_v": [5.0],
        "max_current_a": 6.0,
        "max_wattage_w": 30.0,
        "identifiers": ["warp", "warp_charge"],
        "description": "OnePlus Warp Charge 30",
    },
    "Dash": {
        "voltages_v": [5.0],
        "max_current_a": 4.0,
        "max_wattage_w": 20.0,
        "identifiers": ["dash", "dash_charge"],
        "description": "OnePlus Dash Charge",
    },
    "SuperCharge": {
        "voltages_v": [5.0, 10.0],
        "max_current_a": 4.5,
        "max_wattage_w": 40.0,
        "identifiers": ["supercharge", "super_charge", "scp", "fcp"],
        "description": "Huawei SuperCharge (SCP/FCP)",
    },
    "SuperCharge2.0": {
        "voltages_v": [10.0, 20.0],
        "max_current_a": 5.5,
        "max_wattage_w": 100.0,
        "identifiers": ["supercharge2", "scp2"],
        "description": "Huawei SuperCharge 2.0 (100W)",
    },
    "Samsung-AFC": {
        "voltages_v": [5.0, 9.0],
        "max_current_a": 1.67,
        "max_wattage_w": 15.0,
        "identifiers": ["afc", "adaptive_fast"],
        "description": "Samsung Adaptive Fast Charging",
    },
    "Samsung-Super": {
        "voltages_v": [5.0, 9.0, 11.0],
        "max_current_a": 4.0,
        "max_wattage_w": 45.0,
        "identifiers": ["super_fast", "super_fast_2"],
        "description": "Samsung Super Fast Charging (25W/45W)",
    },
    "MediaTek-PE": {
        "voltages_v": [5.0, 7.0, 9.0, 12.0],
        "max_current_a": 3.0,
        "max_wattage_w": 36.0,
        "identifiers": ["pe", "pump_express", "pe_plus", "pe_30"],
        "description": "MediaTek Pump Express",
    },
    "Xiaomi-HyperCharge": {
        "voltages_v": [10.0, 20.0],
        "max_current_a": 6.0,
        "max_wattage_w": 120.0,
        "identifiers": ["hypercharge", "mi_turbo", "turbo_charge"],
        "description": "Xiaomi HyperCharge (67W-120W)",
    },
}

# ---------- Battery Manufacturer Codes ----------
BATTERY_MANUFACTURER_CODES: Dict[str, Dict[str, str]] = {
    "ATL": {
        "full_name": "Amperex Technology Limited",
        "country": "China / Hong Kong",
        "aliases": "atl,amperex,ATL,AMPEREX",
        "common_clients": "Apple, Huawei, Samsung, Xiaomi, OPPO",
    },
    "BYD": {
        "full_name": "BYD Company Limited",
        "country": "China",
        "aliases": "byd,BYD,FinDreams",
        "common_clients": "Samsung, Apple, Huawei",
    },
    "LGC": {
        "full_name": "LG Chem / LG Energy Solution",
        "country": "South Korea",
        "aliases": "lgc,lg_chem,LGC,LGES,lg_energy",
        "common_clients": "LG, Google, Tesla",
    },
    "SDI": {
        "full_name": "Samsung SDI Co., Ltd.",
        "country": "South Korea",
        "aliases": "sdi,samsung_sdi,SDI,SAMSUNG_SDI",
        "common_clients": "Samsung, BMW, Volkswagen",
    },
    "CATL": {
        "full_name": "Contemporary Amperex Technology Co., Limited",
        "country": "China",
        "aliases": "catl,CATL",
        "common_clients": "Tesla, BMW, Volkswagen, NIO",
    },
    "LISHEN": {
        "full_name": "Tianjin Lishen Battery Joint-Stock Co., Ltd.",
        "country": "China",
        "aliases": "lishen,LISHEN,Lishen",
        "common_clients": "Motorola, ZTE, various ODMs",
    },
    "COSLIGHT": {
        "full_name": "Coslight Technology (International) Group",
        "country": "China",
        "aliases": "coslight,COSLIGHT,Coslight",
        "common_clients": "Samsung, Huawei",
    },
    "SUNWODA": {
        "full_name": "Sunwoda Electronic Co., Ltd.",
        "country": "China",
        "aliases": "sunwoda,SUNWODA,Sunwoda",
        "common_clients": "Huawei, Xiaomi, OPPO, Vivo",
    },
    "MURATA": {
        "full_name": "Murata Manufacturing Co., Ltd. (ex-Sony Energy)",
        "country": "Japan",
        "aliases": "murata,MURATA,sony_energy",
        "common_clients": "Sony, various laptops",
    },
    "SCUD": {
        "full_name": "SCUD Group",
        "country": "China",
        "aliases": "scud,SCUD,Scud",
        "common_clients": "Samsung, Xiaomi, OPPO",
    },
    "DESAY": {
        "full_name": "Desay Battery Technology Co., Ltd.",
        "country": "China",
        "aliases": "desay,DESAY,Desay",
        "common_clients": "Apple, Samsung",
    },
}

# ---------- Expected Battery Parameters by Capacity Range ----------
EXPECTED_PARAMS_BY_CAPACITY: Dict[str, Dict[str, Any]] = {
    "1000-2000": {
        "min_voltage_mv": 3000,
        "max_voltage_mv": 4400,
        "nominal_voltage_mv": 3850,
        "max_temp_c": 45,
        "min_temp_c": 0,
        "max_current_ma": 2000,
        "expected_resistance_mohm_range": (80, 250),
        "max_cycle_count": 800,
        "description": "Small capacity (feature phones, small smartphones)",
    },
    "2000-3500": {
        "min_voltage_mv": 3000,
        "max_voltage_mv": 4450,
        "nominal_voltage_mv": 3870,
        "max_temp_c": 45,
        "min_temp_c": 0,
        "max_current_ma": 3500,
        "expected_resistance_mohm_range": (50, 180),
        "max_cycle_count": 800,
        "description": "Medium capacity (standard smartphones)",
    },
    "3500-5000": {
        "min_voltage_mv": 3000,
        "max_voltage_mv": 4480,
        "nominal_voltage_mv": 3870,
        "max_temp_c": 45,
        "min_temp_c": 0,
        "max_current_ma": 6000,
        "expected_resistance_mohm_range": (30, 150),
        "max_cycle_count": 1000,
        "description": "Large capacity (modern flagships)",
    },
    "5000-7000": {
        "min_voltage_mv": 3000,
        "max_voltage_mv": 4500,
        "nominal_voltage_mv": 3870,
        "max_temp_c": 45,
        "min_temp_c": 0,
        "max_current_ma": 10000,
        "expected_resistance_mohm_range": (20, 120),
        "max_cycle_count": 1000,
        "description": "Extra-large capacity (gaming / rugged phones, dual-cell)",
    },
    "7000-10000": {
        "min_voltage_mv": 3000,
        "max_voltage_mv": 4500,
        "nominal_voltage_mv": 3870,
        "max_temp_c": 45,
        "min_temp_c": 0,
        "max_current_ma": 12000,
        "expected_resistance_mohm_range": (15, 100),
        "max_cycle_count": 1000,
        "description": "Tablet / ultra-large battery devices",
    },
}

# Thermistor type mapping based on typical resistance at 25 C
THERMISTOR_TYPE_MAP: Dict[str, Tuple[int, int]] = {
    "10K NTC B3950":  (8000, 12000),
    "47K NTC B4050":  (40000, 55000),
    "100K NTC B3950": (85000, 115000),
    "10K NTC B3435":  (8500, 11500),
    "30K NTC":        (25000, 35000),
}


# ---------------------------------------------------------------------------
#  Data classes — test results
# ---------------------------------------------------------------------------

@dataclass
class BatteryInfo:
    """Core battery identification and real-time readings."""
    manufacturer: str = "Unknown"
    chemistry: str = "Unknown"
    technology: str = "Unknown"
    design_capacity_mah: int = 0
    current_capacity_mah: int = 0
    health_percent: float = 0.0
    cycle_count: int = 0
    voltage_mv: int = 0
    current_ma: int = 0
    temperature_c: float = 0.0
    status: str = "Unknown"
    serial_number: str = "Unknown"
    charge_counter_uah: int = 0
    present: bool = False
    raw_properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class ThermistorInfo:
    """Battery thermistor (NTC) diagnostics."""
    present: bool = False
    resistance_ohm: int = 0
    temperature_c: float = 0.0
    status: str = "Unknown"
    type: str = "Unknown"
    raw_adc: int = 0
    secondary_temp_c: float = 0.0
    secondary_present: bool = False


@dataclass
class ChargingICInfo:
    """Charging IC / PMIC charger block information."""
    ic_name: str = "Unknown"
    manufacturer: str = "Unknown"
    input_voltage_mv: int = 0
    input_current_ma: int = 0
    charge_voltage_mv: int = 0
    charge_current_ma: int = 0
    status: str = "Unknown"
    registers: Dict[str, str] = field(default_factory=dict)
    usb_type: str = "Unknown"
    connector_type: str = "Unknown"
    otg_enabled: bool = False
    thermal_regulation_active: bool = False
    raw_properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class FastChargeInfo:
    """Fast-charge protocol detection results."""
    supported_protocols: List[str] = field(default_factory=list)
    active_protocol: str = "None"
    max_wattage: float = 0.0
    voltage_v: float = 0.0
    current_a: float = 0.0
    adapter_type: str = "Unknown"
    status: str = "Unknown"
    pd_revision: str = "Unknown"
    pd_contract_voltage_mv: int = 0
    pd_contract_current_ma: int = 0
    raw_properties: Dict[str, str] = field(default_factory=dict)


@dataclass
class BatteryHealthDetail:
    """Derived health metrics computed from raw readings."""
    capacity_fade_pct: float = 0.0
    internal_resistance_mohm: float = 0.0
    charge_full_design: int = 0
    charge_full_actual: int = 0
    wear_level: str = "Unknown"
    estimated_life_months: int = 0
    capacity_ratio: float = 0.0
    voltage_under_load_drop_mv: int = 0
    temperature_delta_c: float = 0.0
    overall_score: float = 0.0


@dataclass
class BatteryTestResult:
    """Top-level container returned by ``detect_battery_status``."""
    connected: bool = False
    error: Optional[str] = None
    battery_info: BatteryInfo = field(default_factory=BatteryInfo)
    thermistor_info: ThermistorInfo = field(default_factory=ThermistorInfo)
    charging_ic_info: ChargingICInfo = field(default_factory=ChargingICInfo)
    fast_charge_info: FastChargeInfo = field(default_factory=FastChargeInfo)
    battery_health_detail: BatteryHealthDetail = field(default_factory=BatteryHealthDetail)
    overall_health: str = "Unknown"


# ---------------------------------------------------------------------------
#  ADB helpers
# ---------------------------------------------------------------------------

def _run_adb(args: List[str], timeout: int = 10) -> Tuple[bool, str]:
    """Execute an ADB command and return (success, stdout)."""
    cmd = ["adb"] + args
    logger.debug("ADB >>> %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = proc.stdout.strip()
        if proc.returncode != 0:
            err = proc.stderr.strip()
            logger.debug("ADB command failed (rc=%d): %s", proc.returncode, err)
            return False, err
        return True, output
    except FileNotFoundError:
        logger.error("adb binary not found on PATH")
        return False, "adb not found"
    except subprocess.TimeoutExpired:
        logger.error("ADB command timed out after %ds: %s", timeout, " ".join(cmd))
        return False, "timeout"


def _adb_shell(command: str, timeout: int = 10) -> Tuple[bool, str]:
    """Shorthand for ``adb shell <command>``."""
    return _run_adb(["shell", command], timeout=timeout)


def _read_sysfs_node(path: str) -> Tuple[bool, str]:
    """Read a single sysfs file via ``adb shell cat``."""
    return _adb_shell(f"cat {path}")


def _read_sysfs_dir(directory: str) -> Dict[str, str]:
    """Read all attribute files in a sysfs directory, return dict."""
    ok, listing = _adb_shell(f"ls {directory} 2>/dev/null")
    if not ok:
        return {}
    props: Dict[str, str] = {}
    for attr in listing.splitlines():
        attr = attr.strip()
        if not attr:
            continue
        ok_val, val = _read_sysfs_node(f"{directory}/{attr}")
        if ok_val:
            props[attr] = val
    return props


def _find_valid_sysfs_path(candidates: List[str]) -> Optional[str]:
    """Return the first sysfs path that exists on the device."""
    for path in candidates:
        ok, output = _adb_shell(f"test -d {path} && echo EXISTS")
        if ok and "EXISTS" in output:
            return path
    return None


def _parse_int(value: str, default: int = 0) -> int:
    """Safely parse an integer from a sysfs value string."""
    try:
        cleaned = re.sub(r"[^\d\-]", "", value.split("\n")[0].strip())
        return int(cleaned) if cleaned else default
    except (ValueError, IndexError):
        return default


def _parse_float(value: str, default: float = 0.0) -> float:
    """Safely parse a float from a sysfs value string."""
    try:
        cleaned = re.sub(r"[^\d.\-]", "", value.split("\n")[0].strip())
        return float(cleaned) if cleaned else default
    except (ValueError, IndexError):
        return default


def _notify(callback: ProgressCallback, pct: float, msg: str) -> None:
    """Fire the progress callback if provided."""
    if callback is not None:
        try:
            callback(pct, msg)
        except Exception:
            logger.debug("Progress callback raised; ignoring", exc_info=True)


# ---------------------------------------------------------------------------
#  Step 1 — ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection(callback: ProgressCallback) -> Tuple[bool, str]:
    """Verify ADB connectivity.  Returns (connected, error_or_empty)."""
    _notify(callback, 0.0, "Checking ADB connection...")
    ok, output = _run_adb(["devices"])
    if not ok:
        return False, f"Cannot run 'adb devices': {output}"

    lines = [
        ln for ln in output.splitlines()
        if "\tdevice" in ln
    ]
    if not lines:
        # Check for unauthorized
        unauthorized = [ln for ln in output.splitlines() if "\tunauthorized" in ln]
        if unauthorized:
            return False, "Device connected but USB Debugging not authorized"
        return False, "No ADB device detected"

    serial = lines[0].split("\t")[0]
    logger.info("ADB device connected: %s", serial)
    _notify(callback, 5.0, f"ADB connected — serial {serial}")
    return True, ""


# ---------------------------------------------------------------------------
#  Step 2 — Battery info from sysfs
# ---------------------------------------------------------------------------

def _read_battery_info(callback: ProgressCallback) -> BatteryInfo:
    """Read core battery properties from /sys/class/power_supply/battery/."""
    _notify(callback, 10.0, "Reading battery info from sysfs...")
    info = BatteryInfo()

    batt_path = _find_valid_sysfs_path(BATTERY_SYSFS_PATHS)
    if batt_path is None:
        logger.warning("No battery sysfs path found")
        info.status = "sysfs not found"
        return info

    props = _read_sysfs_dir(batt_path)
    info.raw_properties = props

    # Present
    present_val = props.get("present", "0")
    info.present = present_val.strip() in ("1", "true", "True")

    # Status (Charging / Discharging / Full / Not charging)
    info.status = props.get("status", "Unknown").strip()

    # Technology / chemistry
    info.technology = props.get("technology", "Unknown").strip()
    info.chemistry = _classify_chemistry(info.technology)

    # Manufacturer
    manufacturer_raw = props.get("manufacturer", "")
    if not manufacturer_raw:
        manufacturer_raw = props.get("battery_manufacturer", "")
    info.manufacturer = _resolve_manufacturer(manufacturer_raw.strip())

    # Serial number
    info.serial_number = props.get("serial_number",
                                    props.get("battery_id", "Unknown")).strip()

    # Capacity
    design_cap = props.get("charge_full_design", props.get("energy_full_design", "0"))
    info.design_capacity_mah = _uah_to_mah(_parse_int(design_cap))

    current_cap = props.get("charge_full", props.get("energy_full", "0"))
    info.current_capacity_mah = _uah_to_mah(_parse_int(current_cap))

    # Health percent
    if info.design_capacity_mah > 0 and info.current_capacity_mah > 0:
        info.health_percent = round(
            (info.current_capacity_mah / info.design_capacity_mah) * 100, 1
        )
    else:
        capacity_pct = props.get("capacity", "0")
        info.health_percent = _parse_float(capacity_pct)

    # Cycle count
    info.cycle_count = _parse_int(props.get("cycle_count", "0"))

    # Voltage (uV -> mV)
    voltage_uv = _parse_int(props.get("voltage_now", "0"))
    info.voltage_mv = voltage_uv // 1000 if voltage_uv > 10000 else voltage_uv

    # Current (uA -> mA)  — can be negative when discharging
    current_ua = _parse_int(props.get("current_now", "0"))
    info.current_ma = current_ua // 1000 if abs(current_ua) > 10000 else current_ua

    # Temperature (tenths of degree C)
    temp_raw = _parse_int(props.get("temp", "0"))
    info.temperature_c = temp_raw / 10.0 if abs(temp_raw) > 100 else float(temp_raw)

    # Charge counter (uAh)
    info.charge_counter_uah = _parse_int(props.get("charge_counter", "0"))

    _notify(callback, 25.0, f"Battery info read — {info.manufacturer} "
                            f"{info.design_capacity_mah}mAh, "
                            f"{info.voltage_mv}mV, {info.temperature_c}C")
    return info


def _uah_to_mah(uah: int) -> int:
    """Convert micro-amp-hours to milli-amp-hours."""
    if uah > 100000:  # value is in uAh
        return uah // 1000
    return uah  # already mAh or zero


def _classify_chemistry(technology: str) -> str:
    """Map technology string to chemistry family."""
    tech = technology.lower()
    if "li-poly" in tech or "lipo" in tech:
        return "Lithium Polymer (LiPo)"
    if "li-ion" in tech or "lion" in tech:
        return "Lithium Ion (Li-ion)"
    if "lifepo" in tech or "lfp" in tech:
        return "Lithium Iron Phosphate (LiFePO4)"
    if "nimh" in tech:
        return "Nickel Metal Hydride (NiMH)"
    if "nicd" in tech:
        return "Nickel Cadmium (NiCd)"
    return technology if technology else "Unknown"


def _resolve_manufacturer(raw: str) -> str:
    """Attempt to match a raw manufacturer string to a known vendor."""
    if not raw:
        return "Unknown"
    raw_lower = raw.lower()
    for code, info in BATTERY_MANUFACTURER_CODES.items():
        aliases = info["aliases"].lower().split(",")
        if raw_lower in aliases or code.lower() == raw_lower:
            return info["full_name"]
        for alias in aliases:
            if alias.strip() in raw_lower:
                return info["full_name"]
    return raw


# ---------------------------------------------------------------------------
#  Step 3 — Thermistor data
# ---------------------------------------------------------------------------

def _read_thermistor_info(
    callback: ProgressCallback,
    battery_props: Dict[str, str],
) -> ThermistorInfo:
    """Read battery thermistor (NTC) readings from sysfs and dumpsys."""
    _notify(callback, 30.0, "Reading thermistor data...")
    therm = ThermistorInfo()

    # Primary: temp from battery sysfs (already parsed, but we also want
    # resistance if the kernel exports it)
    temp_raw = _parse_int(battery_props.get("temp", "0"))
    if temp_raw != 0:
        therm.present = True
        therm.temperature_c = temp_raw / 10.0 if abs(temp_raw) > 100 else float(temp_raw)

    # Some kernels expose thermistor resistance directly
    resistance_raw = battery_props.get("resistance", "")
    if not resistance_raw:
        resistance_raw = battery_props.get("batt_therm", "")
    if not resistance_raw:
        # Try reading from specific paths
        for suffix in ["resistance", "batt_therm", "resistance_id",
                        "batt_resistance", "therm_resistance"]:
            for base in BATTERY_SYSFS_PATHS:
                ok, val = _read_sysfs_node(f"{base}/{suffix}")
                if ok and val.strip():
                    resistance_raw = val.strip()
                    break
            if resistance_raw:
                break

    if resistance_raw:
        therm.resistance_ohm = _parse_int(resistance_raw)
    else:
        # Estimate from temperature using Steinhart-Hart (10K NTC B3950)
        therm.resistance_ohm = _estimate_resistance_from_temp(therm.temperature_c)

    # ADC raw value (if available)
    adc_raw = battery_props.get("batt_therm_adc", "")
    if not adc_raw:
        for base in BATTERY_SYSFS_PATHS:
            ok, val = _read_sysfs_node(f"{base}/batt_therm_adc")
            if ok and val.strip():
                adc_raw = val.strip()
                break
    therm.raw_adc = _parse_int(adc_raw) if adc_raw else 0

    # Secondary thermistor (some dual-cell batteries)
    for suffix in ["skin_temp", "batt_therm_2", "sub_batt_temp"]:
        for base in BATTERY_SYSFS_PATHS:
            ok, val = _read_sysfs_node(f"{base}/{suffix}")
            if ok and val.strip():
                sec_temp = _parse_int(val)
                therm.secondary_temp_c = sec_temp / 10.0 if abs(sec_temp) > 100 else float(sec_temp)
                therm.secondary_present = True
                break
        if therm.secondary_present:
            break

    # Classify thermistor type
    therm.type = _classify_thermistor_type(therm.resistance_ohm)

    # Status assessment
    therm.status = _assess_thermistor_status(therm)

    _notify(callback, 38.0, f"Thermistor — {therm.resistance_ohm} ohm, "
                            f"{therm.temperature_c}C, status={therm.status}")
    return therm


def _estimate_resistance_from_temp(temp_c: float) -> int:
    """Estimate NTC 10K B3950 resistance at given temperature (Steinhart-Hart)."""
    if temp_c == 0.0:
        return 0
    try:
        import math
        r_ref = 10000.0  # 10K at 25C
        b = 3950.0
        t0 = 298.15  # 25C in Kelvin
        t_k = temp_c + 273.15
        if t_k <= 0:
            return 0
        resistance = r_ref * math.exp(b * (1.0 / t_k - 1.0 / t0))
        return int(round(resistance))
    except (OverflowError, ZeroDivisionError, ValueError):
        return 0


def _classify_thermistor_type(resistance_ohm: int) -> str:
    """Determine thermistor type from resistance at current temperature."""
    if resistance_ohm <= 0:
        return "Unknown"
    for name, (low, high) in THERMISTOR_TYPE_MAP.items():
        if low <= resistance_ohm <= high:
            return name
    if resistance_ohm < 8000:
        return f"Low-R NTC (~{resistance_ohm} ohm)"
    return f"High-R NTC (~{resistance_ohm} ohm)"


def _assess_thermistor_status(therm: ThermistorInfo) -> str:
    """Return a human-readable thermistor health status."""
    if not therm.present:
        return "NOT_DETECTED"
    if therm.temperature_c < -20 or therm.temperature_c > 70:
        return "FAULT — temperature out of physical range"
    if therm.resistance_ohm == 0:
        return "WARNING — resistance read as zero (open/short?)"
    if therm.temperature_c > 50:
        return "WARNING — high temperature"
    if therm.temperature_c < 0:
        return "WARNING — low temperature"
    return "OK"


# ---------------------------------------------------------------------------
#  Step 4 — Charging IC detection
# ---------------------------------------------------------------------------

def _read_charging_ic_info(callback: ProgressCallback) -> ChargingICInfo:
    """Identify the charging IC and read its registers / status."""
    _notify(callback, 40.0, "Reading charging IC information...")
    ic = ChargingICInfo()

    # --- Read USB power supply node ---
    usb_path = _find_valid_sysfs_path(USB_SYSFS_PATHS)
    usb_props: Dict[str, str] = {}
    if usb_path:
        usb_props = _read_sysfs_dir(usb_path)
        ic.raw_properties.update({f"usb/{k}": v for k, v in usb_props.items()})

    # --- Read DC / wireless node ---
    dc_path = _find_valid_sysfs_path(DC_SYSFS_PATHS)
    dc_props: Dict[str, str] = {}
    if dc_path:
        dc_props = _read_sysfs_dir(dc_path)
        ic.raw_properties.update({f"dc/{k}": v for k, v in dc_props.items()})

    # --- Read charger-specific nodes ---
    charger_props: Dict[str, str] = {}
    for cp in CHARGER_SYSFS_PATHS:
        ok, _ = _adb_shell(f"test -d {cp} && echo EXISTS")
        if ok and "EXISTS" in _:
            props = _read_sysfs_dir(cp)
            charger_props.update(props)
            ic.raw_properties.update({f"charger/{k}": v for k, v in props.items()})
            # Try to identify IC name from the path
            path_tail = cp.rsplit("/", 1)[-1]
            if path_tail.lower().startswith("smb") or path_tail.lower().startswith("pm"):
                ic.ic_name = path_tail.upper()
            break  # use first found

    # Attempt identification from combined properties
    if ic.ic_name == "Unknown":
        ic.ic_name = _identify_charging_ic(usb_props, dc_props, charger_props)

    # Look up known IC info
    ic_key = ic.ic_name.upper().replace("-", "")
    if ic_key in KNOWN_CHARGING_ICS:
        ic_info = KNOWN_CHARGING_ICS[ic_key]
        ic.manufacturer = ic_info["manufacturer"]
    else:
        # Partial match
        for key, info in KNOWN_CHARGING_ICS.items():
            if key in ic_key or ic_key in key:
                ic.manufacturer = info["manufacturer"]
                ic.ic_name = key
                break

    # Parse voltages and currents from USB node
    ic.input_voltage_mv = _parse_int(usb_props.get("voltage_now", "0"))
    if ic.input_voltage_mv > 100000:
        ic.input_voltage_mv = ic.input_voltage_mv // 1000  # uV -> mV

    ic.input_current_ma = _parse_int(usb_props.get("input_current_limit", "0"))
    if ic.input_current_ma > 100000:
        ic.input_current_ma = ic.input_current_ma // 1000  # uA -> mA

    ic.charge_voltage_mv = _parse_int(
        charger_props.get("voltage_max", usb_props.get("voltage_max", "0"))
    )
    if ic.charge_voltage_mv > 100000:
        ic.charge_voltage_mv = ic.charge_voltage_mv // 1000

    ic.charge_current_ma = _parse_int(
        charger_props.get("constant_charge_current_max",
                          usb_props.get("current_max", "0"))
    )
    if ic.charge_current_ma > 100000:
        ic.charge_current_ma = ic.charge_current_ma // 1000

    # USB type
    ic.usb_type = usb_props.get("usb_type",
                                 usb_props.get("type", "Unknown")).strip()

    # Connector type
    ic.connector_type = usb_props.get("typec_mode",
                                       usb_props.get("connector_type", "Unknown")).strip()

    # OTG
    otg_val = usb_props.get("otg_switch", usb_props.get("boost_current", ""))
    ic.otg_enabled = otg_val.strip() in ("1", "enabled", "true")

    # Thermal regulation
    therm_reg = charger_props.get("charge_term_current",
                                   charger_props.get("thermal_regulation", ""))
    ic.thermal_regulation_active = "active" in therm_reg.lower() if therm_reg else False

    # Read registers (if kernel exposes debug registers)
    ic.registers = _read_ic_registers(charger_props, usb_props)

    # Charger status
    charger_status = charger_props.get("status",
                                        usb_props.get("status", "Unknown")).strip()
    ic.status = charger_status

    _notify(callback, 52.0, f"Charging IC — {ic.ic_name} ({ic.manufacturer}), "
                            f"Vin={ic.input_voltage_mv}mV, Iin={ic.input_current_ma}mA")
    return ic


def _identify_charging_ic(
    usb_props: Dict[str, str],
    dc_props: Dict[str, str],
    charger_props: Dict[str, str],
) -> str:
    """Heuristic IC identification from sysfs property names and values."""
    all_keys = set(usb_props.keys()) | set(dc_props.keys()) | set(charger_props.keys())
    all_vals = " ".join(
        list(usb_props.values()) + list(dc_props.values()) + list(charger_props.values())
    ).lower()

    # Check for known IC string matches in values
    for ic_name in KNOWN_CHARGING_ICS:
        if ic_name.lower() in all_vals:
            return ic_name

    # Heuristic: Qualcomm PMIC charger nodes use specific keys
    qcom_keys = {"pd_active", "real_type", "hvdcp_opti", "moisture_detected"}
    if qcom_keys & all_keys:
        # Try to narrow down
        if "charge_pump" in all_vals:
            return "SMB1390"
        return "SMB5"

    # TI charger keys
    ti_keys = {"charge_done", "vindpm", "iinlim"}
    if ti_keys & all_keys:
        return "BQ25890"

    # MediaTek charger keys
    mtk_keys = {"pe_ready", "pump_express", "mtk", "mediatek"}
    if mtk_keys & all_keys:
        if "mt6360" in all_vals:
            return "MT6360"
        if "mt6362" in all_vals:
            return "MT6362"
        if "mt6371" in all_vals:
            return "MT6371"
        return "MT6370"

    # Samsung charger keys
    samsung_keys = {"afc", "hv_charger_status", "samsung", "mfc"}
    if samsung_keys & all_keys:
        if "s2mu106" in all_vals:
            return "S2MU106"
        if "sm5714" in all_vals:
            return "SM5714"
        if "mfc" in all_vals:
            return "MFC_CHARGER"
        return "SM5701"

    # Huawei/HiSilicon charger keys
    huawei_keys = {"scp", "fcp", "hisilicon"}
    if huawei_keys & all_keys:
        if "hi6526" in all_vals:
            return "HI6526"
        return "HI6523"

    # Unisoc charger keys
    unisoc_keys = {"unisoc", "sc2730", "sprd"}
    if unisoc_keys & all_keys:
        return "SC2730_CHG"

    return "Unknown"


def _read_ic_registers(
    charger_props: Dict[str, str],
    usb_props: Dict[str, str],
) -> Dict[str, str]:
    """Extract register-like properties from charger sysfs nodes."""
    registers: Dict[str, str] = {}
    register_patterns = re.compile(
        r"(reg_|register|debug_|dump|config|param_|setting)", re.IGNORECASE
    )
    for key, val in {**charger_props, **usb_props}.items():
        if register_patterns.search(key):
            registers[key] = val.strip()

    # Also try dedicated debug register dump
    for base in CHARGER_SYSFS_PATHS:
        for node in ("registers", "reg_dump", "debug_dump"):
            ok, val = _read_sysfs_node(f"{base}/{node}")
            if ok and val.strip():
                for line in val.strip().splitlines():
                    parts = line.split(":", 1) if ":" in line else line.split("=", 1)
                    if len(parts) == 2:
                        registers[parts[0].strip()] = parts[1].strip()
                break
    return registers


# ---------------------------------------------------------------------------
#  Step 5 — Fast charge protocol detection
# ---------------------------------------------------------------------------

def _detect_fast_charge_protocol(
    callback: ProgressCallback,
    usb_props: Dict[str, str],
    ic_info: ChargingICInfo,
) -> FastChargeInfo:
    """Detect which fast-charge protocol is active / supported."""
    _notify(callback, 55.0, "Detecting fast charge protocol...")
    fc = FastChargeInfo()

    # ---- Gather clues from multiple sources ----

    # 1. USB sysfs real_type / type
    real_type = usb_props.get("real_type", usb_props.get("type", "")).lower()

    # 2. dumpsys battery
    ok, dumpsys_out = _adb_shell("dumpsys battery")
    dumpsys_lines: Dict[str, str] = {}
    if ok:
        for line in dumpsys_out.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                dumpsys_lines[k.strip().lower()] = v.strip()
        fc.raw_properties.update({f"dumpsys/{k}": v for k, v in dumpsys_lines.items()})

    # 3. dumpsys batterystats (quick charge info)
    ok_bs, bs_out = _adb_shell("dumpsys batterystats | head -50")
    if ok_bs:
        fc.raw_properties["dumpsys/batterystats_head"] = bs_out[:2000]

    # 4. Power supply USB properties (already in ic_info.raw_properties)
    combined_text = (
        real_type + " " +
        " ".join(usb_props.values()) + " " +
        " ".join(v for k, v in ic_info.raw_properties.items())
    ).lower()

    # ---- Match protocols ----
    detected_protocols: List[str] = []

    for proto_name, proto_info in FAST_CHARGE_PROTOCOLS.items():
        for identifier in proto_info["identifiers"]:
            if identifier.lower() in combined_text:
                detected_protocols.append(proto_name)
                break

    fc.supported_protocols = sorted(set(detected_protocols))

    # ---- Determine active protocol ----
    fc.active_protocol = _determine_active_protocol(
        real_type, combined_text, detected_protocols, ic_info
    )

    # ---- Voltage and current (live) ----
    fc.voltage_v = ic_info.input_voltage_mv / 1000.0 if ic_info.input_voltage_mv else 0.0
    fc.current_a = ic_info.input_current_ma / 1000.0 if ic_info.input_current_ma else 0.0
    fc.max_wattage = round(fc.voltage_v * fc.current_a, 1)

    # If protocol is known, use its rated max wattage if higher
    if fc.active_protocol in FAST_CHARGE_PROTOCOLS:
        proto = FAST_CHARGE_PROTOCOLS[fc.active_protocol]
        rated_max = proto["max_wattage_w"]
        if rated_max > fc.max_wattage:
            fc.max_wattage = rated_max

    # ---- Adapter type ----
    fc.adapter_type = _classify_adapter_type(real_type, ic_info.usb_type, fc.active_protocol)

    # ---- USB-PD specifics ----
    pd_active = usb_props.get("pd_active", "0")
    if pd_active.strip() == "1":
        fc.pd_revision = usb_props.get("pd_revision", "Unknown").strip()
        fc.pd_contract_voltage_mv = _parse_int(
            usb_props.get("pd_voltage_max", usb_props.get("pd_contract_voltage", "0"))
        )
        fc.pd_contract_current_ma = _parse_int(
            usb_props.get("pd_current_max", usb_props.get("pd_contract_current", "0"))
        )
        if fc.pd_contract_voltage_mv > 100000:
            fc.pd_contract_voltage_mv //= 1000
        if fc.pd_contract_current_ma > 100000:
            fc.pd_contract_current_ma //= 1000

    # ---- Status ----
    if fc.active_protocol != "None":
        fc.status = f"Active — {fc.active_protocol}"
    elif fc.supported_protocols:
        fc.status = f"Idle — supports {', '.join(fc.supported_protocols)}"
    else:
        fc.status = "Standard charging or no adapter"

    _notify(callback, 68.0, f"Fast charge — {fc.active_protocol}, "
                            f"{fc.max_wattage}W ({fc.voltage_v}V / {fc.current_a}A)")
    return fc


def _determine_active_protocol(
    real_type: str,
    combined_text: str,
    detected: List[str],
    ic_info: ChargingICInfo,
) -> str:
    """Pick the single active protocol from detected candidates."""
    if not detected:
        return "None"

    # HVDCP variants
    if "hvdcp_3p5" in combined_text or "qc4" in combined_text:
        return "QC4.0"
    if "hvdcp_3" in combined_text or "qc3" in combined_text:
        return "QC3.0"
    if "hvdcp" in combined_text:
        return "QC2.0"

    # PD active
    if "pd" in real_type:
        if "pps" in combined_text:
            return "USB-PD-PPS"
        return "USB-PD"

    # VOOC family
    if "svooc2" in combined_text or "supervooc2" in combined_text:
        return "SuperVOOC2.0"
    if "svooc" in combined_text or "supervooc" in combined_text:
        return "SuperVOOC"
    if "vooc" in combined_text or "dash" in combined_text:
        return "VOOC"

    # SuperCharge
    if "supercharge2" in combined_text or "scp2" in combined_text:
        return "SuperCharge2.0"
    if "supercharge" in combined_text or "scp" in combined_text:
        return "SuperCharge"

    # Warp
    if "warp" in combined_text:
        return "Warp"

    # Samsung
    if "super_fast" in combined_text:
        return "Samsung-Super"
    if "afc" in combined_text or "adaptive_fast" in combined_text:
        return "Samsung-AFC"

    # Xiaomi
    if "hypercharge" in combined_text or "mi_turbo" in combined_text:
        return "Xiaomi-HyperCharge"

    # MediaTek PE
    if "pump_express" in combined_text or "pe_plus" in combined_text:
        return "MediaTek-PE"

    # Fallback to first detected
    return detected[0] if detected else "None"


def _classify_adapter_type(
    real_type: str,
    usb_type: str,
    active_protocol: str,
) -> str:
    """Classify the connected adapter."""
    combined = (real_type + " " + usb_type).lower()

    if "dcp" in combined:
        return "Dedicated Charging Port (DCP)"
    if "cdp" in combined:
        return "Charging Downstream Port (CDP)"
    if "sdp" in combined:
        return "Standard Downstream Port (SDP)"
    if "pd" in combined or "USB-PD" in active_protocol:
        return "USB Power Delivery Adapter"
    if "hvdcp" in combined:
        return "Qualcomm HVDCP Adapter"
    if active_protocol in ("VOOC", "SuperVOOC", "SuperVOOC2.0", "Dash", "Warp"):
        return "OPPO/OnePlus Proprietary Adapter"
    if "SuperCharge" in active_protocol:
        return "Huawei SuperCharge Adapter"
    if "unknown" in combined or not combined.strip():
        return "No adapter / Unknown"
    return f"Other ({usb_type})"


# ---------------------------------------------------------------------------
#  Step 6 — Battery health calculation
# ---------------------------------------------------------------------------

def _calculate_battery_health(
    callback: ProgressCallback,
    battery_info: BatteryInfo,
    thermistor_info: ThermistorInfo,
) -> BatteryHealthDetail:
    """Derive detailed battery health metrics from raw readings."""
    _notify(callback, 72.0, "Calculating battery health metrics...")
    health = BatteryHealthDetail()

    design = battery_info.design_capacity_mah
    actual = battery_info.current_capacity_mah

    health.charge_full_design = design
    health.charge_full_actual = actual

    # --- Capacity fade ---
    if design > 0 and actual > 0:
        health.capacity_ratio = round(actual / design, 4)
        health.capacity_fade_pct = round((1.0 - health.capacity_ratio) * 100, 1)
    elif design > 0:
        health.capacity_fade_pct = 100.0
        health.capacity_ratio = 0.0

    # --- Internal resistance estimation ---
    # Use voltage drop and current if available; otherwise heuristic from
    # cycle count and capacity fade.
    health.internal_resistance_mohm = _estimate_internal_resistance(
        battery_info, thermistor_info
    )

    # --- Voltage under load drop ---
    # If current is negative (discharging) and voltage is known, we estimate
    # IR drop = |I| * R_internal
    if battery_info.current_ma < 0 and health.internal_resistance_mohm > 0:
        health.voltage_under_load_drop_mv = int(
            abs(battery_info.current_ma) * health.internal_resistance_mohm / 1000
        )

    # --- Temperature delta (from ambient ~25C) ---
    if thermistor_info.present:
        health.temperature_delta_c = round(thermistor_info.temperature_c - 25.0, 1)

    # --- Wear level classification ---
    health.wear_level = _classify_wear_level(
        health.capacity_fade_pct,
        battery_info.cycle_count,
        health.internal_resistance_mohm,
    )

    # --- Estimated remaining life ---
    health.estimated_life_months = _estimate_remaining_life(
        health.capacity_fade_pct,
        battery_info.cycle_count,
    )

    # --- Overall score (0-100) ---
    health.overall_score = _compute_health_score(
        health.capacity_fade_pct,
        health.internal_resistance_mohm,
        battery_info.cycle_count,
        battery_info.temperature_c,
        battery_info.design_capacity_mah,
    )

    _notify(callback, 82.0, f"Battery health — fade={health.capacity_fade_pct}%, "
                            f"Rint={health.internal_resistance_mohm}mOhm, "
                            f"score={health.overall_score}/100")
    return health


def _estimate_internal_resistance(
    battery_info: BatteryInfo,
    thermistor_info: ThermistorInfo,
) -> float:
    """Estimate internal resistance in milliohms.

    If we have both voltage and current (discharging), we can do a rough
    estimation.  Otherwise fall back to heuristic based on cycle count
    and design capacity.
    """
    # Method 1: direct calculation from V/I under load
    if battery_info.current_ma < -100 and battery_info.voltage_mv > 0:
        # We don't have OCV, so estimate based on capacity range
        capacity = battery_info.design_capacity_mah
        expected = _get_expected_params(capacity)
        nominal_v = expected.get("nominal_voltage_mv", 3850)
        # dV = V_nominal - V_under_load (rough)
        v_drop = nominal_v - battery_info.voltage_mv
        if v_drop > 0:
            r_est = (v_drop / abs(battery_info.current_ma)) * 1000  # mOhm
            # Sanity-clamp
            if 5 < r_est < 500:
                return round(r_est, 1)

    # Method 2: heuristic
    capacity = battery_info.design_capacity_mah
    cycle = battery_info.cycle_count
    base_r = 120.0  # baseline for a 3000mAh cell

    if capacity > 0:
        # Larger cells have lower resistance
        base_r = 120.0 * (3000 / max(capacity, 500))

    # Resistance grows with cycles (~0.05% per cycle as a rough model)
    aging_factor = 1.0 + (cycle * 0.0005)
    estimated = round(base_r * aging_factor, 1)

    # Temperature correction: resistance is higher when cold
    if thermistor_info.present and thermistor_info.temperature_c < 15:
        cold_factor = 1.0 + (25 - thermistor_info.temperature_c) * 0.015
        estimated = round(estimated * cold_factor, 1)

    return estimated


def _get_expected_params(capacity_mah: int) -> Dict[str, Any]:
    """Return expected parameter dict for the given capacity."""
    for key, params in EXPECTED_PARAMS_BY_CAPACITY.items():
        lo, hi = (int(x) for x in key.split("-"))
        if lo <= capacity_mah <= hi:
            return params
    # Default to medium range
    return EXPECTED_PARAMS_BY_CAPACITY.get("2000-3500", {})


def _classify_wear_level(
    fade_pct: float,
    cycle_count: int,
    resistance_mohm: float,
) -> str:
    """Classify wear level into human-readable categories."""
    if fade_pct <= 3 and cycle_count < 100:
        return "New / Excellent"
    if fade_pct <= 10 and cycle_count < 300:
        return "Good"
    if fade_pct <= 20 and cycle_count < 500:
        return "Moderate"
    if fade_pct <= 30 and cycle_count < 800:
        return "Worn"
    if fade_pct <= 40:
        return "Heavily Worn"
    return "End of Life"


def _estimate_remaining_life(
    fade_pct: float,
    cycle_count: int,
) -> int:
    """Estimate remaining useful life in months (to 80% design capacity = 20% fade).

    Uses linear extrapolation from current fade and cycle count.
    Assumes ~1 cycle per day for an average user.
    """
    if fade_pct >= 20:
        return 0  # Already past 80% threshold

    if cycle_count <= 0:
        # No cycle info; estimate from fade alone
        if fade_pct <= 0:
            return 36  # assume roughly 3 years remaining
        # Rough: if x% fade over unknown time, assume linear
        remaining_fade = 20.0 - fade_pct
        # Guess ~2% fade per 100 cycles, 1 cycle/day
        cycles_left = int(remaining_fade / 0.02) if fade_pct > 0 else 600
        return max(1, cycles_left // 30)

    # Fade rate per cycle
    if fade_pct > 0:
        fade_per_cycle = fade_pct / cycle_count
    else:
        fade_per_cycle = 0.02  # default ~2% per 100 cycles

    remaining_fade = 20.0 - fade_pct
    if fade_per_cycle <= 0:
        return 36

    cycles_left = remaining_fade / fade_per_cycle
    # ~30 cycles per month (1/day)
    months = int(cycles_left / 30)
    return max(0, min(months, 120))  # cap at 10 years


def _compute_health_score(
    fade_pct: float,
    resistance_mohm: float,
    cycle_count: int,
    temperature_c: float,
    design_capacity_mah: int,
) -> float:
    """Compute a 0-100 battery health score.

    Weighted factors:
      - Capacity retention: 50%
      - Internal resistance:  20%
      - Cycle count:          15%
      - Temperature:          15%
    """
    # Capacity score (100 @ 0% fade, 0 @ 40% fade)
    cap_score = max(0.0, min(100.0, 100.0 - (fade_pct * 2.5)))

    # Resistance score
    expected = _get_expected_params(design_capacity_mah)
    r_range = expected.get("expected_resistance_mohm_range", (50, 180))
    r_mid = (r_range[0] + r_range[1]) / 2
    r_max = r_range[1] * 2.0  # double the expected max = 0 score
    if resistance_mohm <= r_mid:
        r_score = 100.0
    elif resistance_mohm >= r_max:
        r_score = 0.0
    else:
        r_score = max(0.0, 100.0 * (1 - (resistance_mohm - r_mid) / (r_max - r_mid)))

    # Cycle score (100 @ 0 cycles, 0 @ 1000 cycles)
    max_cycles = expected.get("max_cycle_count", 800)
    cycle_score = max(0.0, min(100.0, 100.0 * (1 - cycle_count / (max_cycles * 1.5))))

    # Temperature score (100 @ 20-30C, lower outside)
    if 15.0 <= temperature_c <= 35.0:
        temp_score = 100.0
    elif temperature_c < 15.0:
        temp_score = max(0.0, 100.0 - (15.0 - temperature_c) * 5)
    else:
        temp_score = max(0.0, 100.0 - (temperature_c - 35.0) * 5)

    # Weighted total
    score = (
        cap_score * 0.50 +
        r_score * 0.20 +
        cycle_score * 0.15 +
        temp_score * 0.15
    )
    return round(max(0.0, min(100.0, score)), 1)


# ---------------------------------------------------------------------------
#  Step 7 — Overall health assessment
# ---------------------------------------------------------------------------

def _generate_overall_assessment(
    battery_info: BatteryInfo,
    thermistor_info: ThermistorInfo,
    charging_ic_info: ChargingICInfo,
    fast_charge_info: FastChargeInfo,
    health_detail: BatteryHealthDetail,
) -> str:
    """Generate a human-readable overall battery health verdict.

    Returns a multi-line string summarising the battery condition,
    suitable for display to a repair technician.
    """
    lines: List[str] = []

    # --- Header ---
    score = health_detail.overall_score
    if score >= 85:
        verdict = "EXCELLENT"
    elif score >= 70:
        verdict = "GOOD"
    elif score >= 50:
        verdict = "FAIR"
    elif score >= 30:
        verdict = "POOR"
    else:
        verdict = "CRITICAL"

    lines.append(f"Battery Health: {verdict} ({score}/100)")
    lines.append("")

    # --- Battery identification ---
    lines.append(f"Manufacturer : {battery_info.manufacturer}")
    lines.append(f"Chemistry    : {battery_info.chemistry}")
    lines.append(f"Technology   : {battery_info.technology}")
    lines.append(f"Design Cap   : {battery_info.design_capacity_mah} mAh")
    lines.append(f"Actual Cap   : {battery_info.current_capacity_mah} mAh")
    lines.append(f"Capacity Fade: {health_detail.capacity_fade_pct}%")
    lines.append(f"Cycle Count  : {battery_info.cycle_count}")
    lines.append(f"Wear Level   : {health_detail.wear_level}")
    lines.append(f"Est. Life    : {health_detail.estimated_life_months} months remaining")
    lines.append("")

    # --- Live readings ---
    lines.append(f"Voltage      : {battery_info.voltage_mv} mV")
    lines.append(f"Current      : {battery_info.current_ma} mA")
    lines.append(f"Temperature  : {battery_info.temperature_c} C")
    lines.append(f"Status       : {battery_info.status}")
    lines.append(f"Int. Resist. : {health_detail.internal_resistance_mohm} mOhm")
    lines.append("")

    # --- Thermistor ---
    lines.append(f"Thermistor   : {thermistor_info.status}")
    if thermistor_info.present:
        lines.append(f"  Resistance : {thermistor_info.resistance_ohm} ohm")
        lines.append(f"  Type       : {thermistor_info.type}")
        if thermistor_info.secondary_present:
            lines.append(f"  Secondary  : {thermistor_info.secondary_temp_c} C")
    lines.append("")

    # --- Charging IC ---
    lines.append(f"Charging IC  : {charging_ic_info.ic_name} ({charging_ic_info.manufacturer})")
    lines.append(f"  Input V/I  : {charging_ic_info.input_voltage_mv} mV / "
                 f"{charging_ic_info.input_current_ma} mA")
    lines.append(f"  Charge V/I : {charging_ic_info.charge_voltage_mv} mV / "
                 f"{charging_ic_info.charge_current_ma} mA")
    lines.append(f"  USB Type   : {charging_ic_info.usb_type}")
    lines.append(f"  Connector  : {charging_ic_info.connector_type}")
    lines.append("")

    # --- Fast charge ---
    lines.append(f"Fast Charge  : {fast_charge_info.status}")
    if fast_charge_info.supported_protocols:
        lines.append(f"  Supported  : {', '.join(fast_charge_info.supported_protocols)}")
    lines.append(f"  Active     : {fast_charge_info.active_protocol}")
    lines.append(f"  Max Wattage: {fast_charge_info.max_wattage} W")
    lines.append(f"  Adapter    : {fast_charge_info.adapter_type}")
    if fast_charge_info.pd_contract_voltage_mv > 0:
        lines.append(f"  PD Contract: {fast_charge_info.pd_contract_voltage_mv} mV / "
                     f"{fast_charge_info.pd_contract_current_ma} mA")
    lines.append("")

    # --- Warnings ---
    warnings = _generate_warnings(
        battery_info, thermistor_info, charging_ic_info, health_detail
    )
    if warnings:
        lines.append("WARNINGS:")
        for w in warnings:
            lines.append(f"  - {w}")
    else:
        lines.append("No warnings.")

    return "\n".join(lines)


def _generate_warnings(
    battery_info: BatteryInfo,
    thermistor_info: ThermistorInfo,
    charging_ic_info: ChargingICInfo,
    health_detail: BatteryHealthDetail,
) -> List[str]:
    """Produce a list of actionable warning strings for the technician."""
    warnings: List[str] = []

    # Capacity fade
    if health_detail.capacity_fade_pct > 30:
        warnings.append(
            f"Severe capacity fade ({health_detail.capacity_fade_pct}%). "
            f"Battery replacement strongly recommended."
        )
    elif health_detail.capacity_fade_pct > 20:
        warnings.append(
            f"Significant capacity fade ({health_detail.capacity_fade_pct}%). "
            f"Battery nearing end of useful life."
        )

    # High cycle count
    expected = _get_expected_params(battery_info.design_capacity_mah)
    max_cycles = expected.get("max_cycle_count", 800)
    if battery_info.cycle_count > max_cycles:
        warnings.append(
            f"Cycle count ({battery_info.cycle_count}) exceeds expected maximum "
            f"({max_cycles}). Battery may be degraded."
        )

    # Temperature
    if battery_info.temperature_c > 45:
        warnings.append(
            f"Battery temperature critically high ({battery_info.temperature_c}C). "
            f"Check for swelling or short circuit."
        )
    elif battery_info.temperature_c > 40:
        warnings.append(
            f"Battery temperature elevated ({battery_info.temperature_c}C). "
            f"Monitor for thermal issues."
        )
    elif battery_info.temperature_c < 0:
        warnings.append(
            f"Battery temperature below freezing ({battery_info.temperature_c}C). "
            f"Charging at low temperature risks lithium plating."
        )

    # Thermistor fault
    if thermistor_info.status.startswith("FAULT"):
        warnings.append(
            f"Thermistor fault detected: {thermistor_info.status}. "
            f"Safety protection may be compromised."
        )
    elif thermistor_info.status.startswith("NOT_DETECTED"):
        warnings.append(
            "Battery thermistor not detected. Temperature monitoring unavailable."
        )

    # High internal resistance
    r_range = expected.get("expected_resistance_mohm_range", (50, 180))
    if health_detail.internal_resistance_mohm > r_range[1] * 1.5:
        warnings.append(
            f"Internal resistance ({health_detail.internal_resistance_mohm} mOhm) "
            f"significantly above expected range ({r_range[0]}-{r_range[1]} mOhm). "
            f"Battery may be aged or damaged."
        )

    # Voltage anomalies
    if battery_info.voltage_mv > 0:
        min_v = expected.get("min_voltage_mv", 3000)
        max_v = expected.get("max_voltage_mv", 4450)
        if battery_info.voltage_mv < min_v:
            warnings.append(
                f"Battery voltage ({battery_info.voltage_mv}mV) below minimum "
                f"safe threshold ({min_v}mV). Over-discharge may have occurred."
            )
        if battery_info.voltage_mv > max_v + 100:
            warnings.append(
                f"Battery voltage ({battery_info.voltage_mv}mV) above maximum "
                f"({max_v}mV). Possible charger IC fault or BMS issue."
            )

    # Not present
    if not battery_info.present:
        warnings.append(
            "Battery reports as not present. Check connector / flex cable."
        )

    return warnings


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_battery_status(
    callback: ProgressCallback = None,
) -> BatteryTestResult:
    """Run the full battery diagnostic sequence.

    Parameters
    ----------
    callback : optional
        A callable ``(pct: float, msg: str) -> None`` invoked with progress
        updates.  *pct* ranges from 0 to 100.

    Returns
    -------
    BatteryTestResult
        Populated result dataclass with all sub-results and an overall
        health assessment string.
    """
    result = BatteryTestResult()
    logger.info("Starting advanced battery test sequence")

    # ── Step 1: ADB connection ──
    connected, err = _check_adb_connection(callback)
    if not connected:
        result.connected = False
        result.error = err
        result.overall_health = f"UNABLE TO TEST — {err}"
        _notify(callback, 100.0, f"Test aborted: {err}")
        return result
    result.connected = True

    try:
        # ── Step 2: Battery info ──
        result.battery_info = _read_battery_info(callback)

        # ── Step 3: Thermistor ──
        result.thermistor_info = _read_thermistor_info(
            callback, result.battery_info.raw_properties
        )

        # ── Step 4: Charging IC ──
        result.charging_ic_info = _read_charging_ic_info(callback)

        # ── Step 5: Fast charge protocol ──
        usb_props = {
            k.replace("usb/", ""): v
            for k, v in result.charging_ic_info.raw_properties.items()
            if k.startswith("usb/")
        }
        result.fast_charge_info = _detect_fast_charge_protocol(
            callback, usb_props, result.charging_ic_info
        )

        # ── Step 6: Health calculation ──
        result.battery_health_detail = _calculate_battery_health(
            callback, result.battery_info, result.thermistor_info
        )

        # ── Step 7: Overall assessment ──
        _notify(callback, 90.0, "Generating overall assessment...")
        result.overall_health = _generate_overall_assessment(
            result.battery_info,
            result.thermistor_info,
            result.charging_ic_info,
            result.fast_charge_info,
            result.battery_health_detail,
        )

    except Exception as exc:
        logger.exception("Battery test sequence failed")
        result.error = str(exc)
        result.overall_health = f"TEST ERROR — {exc}"

    _notify(callback, 100.0, "Battery test complete")
    logger.info("Battery test sequence finished")
    return result


# ---------------------------------------------------------------------------
#  CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys
    from dataclasses import asdict

    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def _cli_callback(pct: float, msg: str) -> None:
        print(f"  [{pct:5.1f}%] {msg}")

    print("=" * 70)
    print("  Advanced Battery Tester — Mooxy AI Fault Detector")
    print("=" * 70)
    print()

    test_result = detect_battery_status(callback=_cli_callback)

    print()
    print("-" * 70)
    print(test_result.overall_health)
    print("-" * 70)

    if "--json" in sys.argv:
        print()
        print(json.dumps(asdict(test_result), indent=2, default=str))
