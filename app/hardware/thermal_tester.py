"""
Thermal Testing Module for Mobile Repair Technicians.

Reads thermal zones, cooling devices, CPU frequency scaling state, and
performs throttle analysis on Android devices via ADB shell commands.
Covers integrated SoC thermal sensors, external thermal sensor ICs, and
Qualcomm-specific MSM thermal parameters.

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
#  Known Thermal Sensor ICs database
# ---------------------------------------------------------------------------

THERMAL_SENSOR_ICS: Dict[str, Dict[str, Any]] = {
    # ---------- Qualcomm (integrated TSENS) ----------
    "QM215_TSENS": {
        "manufacturer": "Qualcomm",
        "description": "QM215 integrated TSENS (entry-level SoC)",
        "resolution_c": 0.1,
        "accuracy_c": 1.0,
        "temp_range": (-40, 125),
        "common_failures": [
            "Thermal zone reads stuck at 0 — TSENS init failure after deep sleep",
            "Erratic jumps >10 C between reads — ADC calibration lost",
        ],
    },
    "SDM845_TSENS": {
        "manufacturer": "Qualcomm",
        "description": "SDM845 integrated TSENS v2 (15 sensors)",
        "resolution_c": 0.1,
        "accuracy_c": 0.5,
        "temp_range": (-40, 125),
        "common_failures": [
            "TSENS critical interrupt storm after prolonged gaming",
            "Sensor offset drift on refurbished boards — recalibration needed",
            "Zone temp stuck at 124 C — TSENS hardware watchdog tripped",
        ],
    },
    "SM8350_TSENS": {
        "manufacturer": "Qualcomm",
        "description": "SM8350 (Snapdragon 888) integrated TSENS v2.3",
        "resolution_c": 0.1,
        "accuracy_c": 0.5,
        "temp_range": (-40, 125),
        "common_failures": [
            "Sustained thermal throttle due to tight thermal envelope",
            "TSENS reports -40 C on dead cores after ESD damage",
            "GPU thermal zone lagging behind actual temperature by 3-5 seconds",
        ],
    },
    "SM8550_TSENS": {
        "manufacturer": "Qualcomm",
        "description": "SM8550 (Snapdragon 8 Gen 2) integrated TSENS v3",
        "resolution_c": 0.05,
        "accuracy_c": 0.5,
        "temp_range": (-40, 125),
        "common_failures": [
            "Aggressive frequency capping above 42 C skin temperature",
            "False critical shutdown triggered by noisy PMIC thermal ADC",
        ],
    },
    # ---------- Texas Instruments ----------
    "TMP103": {
        "manufacturer": "Texas Instruments",
        "description": "TMP103 low-power I2C temperature sensor",
        "resolution_c": 1.0,
        "accuracy_c": 1.0,
        "temp_range": (-40, 125),
        "common_failures": [
            "I2C address conflict with other sensors on shared bus",
            "Reads fixed 0 C — VCC rail drooped below 1.2 V minimum",
        ],
    },
    "TMP108": {
        "manufacturer": "Texas Instruments",
        "description": "TMP108 low-power I2C sensor with alert function",
        "resolution_c": 0.0625,
        "accuracy_c": 0.75,
        "temp_range": (-40, 125),
        "common_failures": [
            "ALERT pin stuck low due to solder bridge on QFN pad",
            "Hysteresis register corrupted after firmware flash — lockup",
        ],
    },
    "TMP117": {
        "manufacturer": "Texas Instruments",
        "description": "TMP117 high-accuracy digital temperature sensor",
        "resolution_c": 0.0078125,
        "accuracy_c": 0.1,
        "temp_range": (-55, 150),
        "common_failures": [
            "Conversion time set too long causing stale reads",
            "EEPROM calibration data lost after ESD event",
        ],
    },
    "TMP461": {
        "manufacturer": "Texas Instruments",
        "description": "TMP461 remote and local temperature sensor",
        "resolution_c": 0.0625,
        "accuracy_c": 1.0,
        "temp_range": (-40, 125),
        "common_failures": [
            "Remote diode open — reads 127 C constantly",
            "Series resistance error on remote junction — offset grows with age",
        ],
    },
    # ---------- STMicroelectronics ----------
    "STTS751": {
        "manufacturer": "STMicroelectronics",
        "description": "STTS751 digital temperature sensor with alarm",
        "resolution_c": 0.0625,
        "accuracy_c": 0.5,
        "temp_range": (-40, 125),
        "common_failures": [
            "EVENT pin not triggering — pull-up resistor missing",
            "I2C NACK after address scan — chip damaged by overvoltage",
        ],
    },
    "STTS22H": {
        "manufacturer": "STMicroelectronics",
        "description": "STTS22H ultra-low-power temperature sensor",
        "resolution_c": 0.01,
        "accuracy_c": 0.5,
        "temp_range": (-40, 125),
        "common_failures": [
            "Startup delay missed — first read returns stale factory default",
            "Low-power mode prevents continuous monitoring — gaps in thermal log",
        ],
    },
    # ---------- Maxim Integrated ----------
    "MAX31725": {
        "manufacturer": "Maxim Integrated",
        "description": "MAX31725 local temperature sensor",
        "resolution_c": 0.00390625,
        "accuracy_c": 0.5,
        "temp_range": (-55, 150),
        "common_failures": [
            "Extended format bit set incorrectly — negative temps read as >128 C",
            "Shutdown mode entered due to firmware bug — sensor appears dead",
        ],
    },
    "MAX31875": {
        "manufacturer": "Maxim Integrated",
        "description": "MAX31875 low-power temperature sensor",
        "resolution_c": 0.0625,
        "accuracy_c": 1.5,
        "temp_range": (-40, 125),
        "common_failures": [
            "PEC (CRC) errors on noisy I2C bus near power amplifier",
            "Configuration register reset after brown-out — defaults to 10-bit",
        ],
    },
    # ---------- NXP ----------
    "PCT2075": {
        "manufacturer": "NXP Semiconductors",
        "description": "PCT2075 I2C-bus temperature sensor",
        "resolution_c": 0.125,
        "accuracy_c": 1.0,
        "temp_range": (-25, 100),
        "common_failures": [
            "OS output stuck asserted — hysteresis programmed incorrectly",
            "Address pin floating — random I2C address on each boot",
        ],
    },
    # ---------- Microchip ----------
    "MCP9808": {
        "manufacturer": "Microchip Technology",
        "description": "MCP9808 high-accuracy temperature sensor",
        "resolution_c": 0.0625,
        "accuracy_c": 0.25,
        "temp_range": (-40, 125),
        "common_failures": [
            "Alert output latch stuck — requires manual clear via register write",
            "Resolution bits changed by rogue I2C traffic — reads coarse 0.5 C",
        ],
    },
    "EMC1403": {
        "manufacturer": "Microchip Technology",
        "description": "EMC1403 triple-channel temperature sensor",
        "resolution_c": 0.125,
        "accuracy_c": 1.0,
        "temp_range": (-40, 125),
        "common_failures": [
            "External diode channel reads FAULT — open diode connection",
            "ALERT# asserted continuously — threshold register at default 0 C",
        ],
    },
    # ---------- Sensirion ----------
    "STS40": {
        "manufacturer": "Sensirion",
        "description": "STS40 digital temperature sensor",
        "resolution_c": 0.01,
        "accuracy_c": 0.2,
        "temp_range": (-40, 125),
        "common_failures": [
            "CRC check failure on data readback — bus integrity issue",
            "Sensor not responding after soft-reset — requires power cycle",
        ],
    },
    "STS4x": {
        "manufacturer": "Sensirion",
        "description": "STS4x next-gen digital temperature sensor family",
        "resolution_c": 0.01,
        "accuracy_c": 0.1,
        "temp_range": (-40, 125),
        "common_failures": [
            "Measurement command rejected — sensor in sleep mode",
            "Repeatability mode mismatch causing inconsistent accuracy",
        ],
    },
    # ---------- ON Semiconductor ----------
    "NCT75": {
        "manufacturer": "ON Semiconductor",
        "description": "NCT75 digital temperature sensor with alert",
        "resolution_c": 0.0625,
        "accuracy_c": 1.0,
        "temp_range": (-55, 125),
        "common_failures": [
            "One-shot mode stuck — continuous conversion never triggers",
            "OS polarity inverted by firmware — thermal protection logic reversed",
        ],
    },
    "CAT34TS02": {
        "manufacturer": "ON Semiconductor",
        "description": "CAT34TS02 JEDEC-compliant temperature sensor + EEPROM",
        "resolution_c": 0.0625,
        "accuracy_c": 1.0,
        "temp_range": (-40, 125),
        "common_failures": [
            "EEPROM write-protect engaged — cannot update thermal thresholds",
            "DIMM SPD address conflict — sensor data returned instead of EEPROM",
        ],
    },
    # ---------- MediaTek (integrated) ----------
    "MTK_TSEN": {
        "manufacturer": "MediaTek",
        "description": "MediaTek integrated thermal sensor engine",
        "resolution_c": 0.1,
        "accuracy_c": 1.0,
        "temp_range": (-40, 125),
        "common_failures": [
            "AUXADC calibration data missing from EFUSE — reads 20 C offset",
            "Thermal zone not registered on kernel boot — driver probe fails",
        ],
    },
    # ---------- Samsung LSI (integrated) ----------
    "EXYNOS_TMU": {
        "manufacturer": "Samsung LSI",
        "description": "Exynos Thermal Management Unit",
        "resolution_c": 0.1,
        "accuracy_c": 1.0,
        "temp_range": (-40, 125),
        "common_failures": [
            "TMU trimming info invalid — reads 15 C below actual",
            "Emergency frequency capping triggered at incorrect threshold",
        ],
    },
}

# ---------------------------------------------------------------------------
#  Thermal zone categories (keywords to classify zone type)
# ---------------------------------------------------------------------------

ZONE_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "cpu": ["cpu", "little", "big", "silver", "gold", "prime", "core",
            "cluster", "cci", "cpuss"],
    "gpu": ["gpu", "graphic", "mali", "adreno", "gpuss"],
    "battery": ["battery", "batt", "bat_therm", "batt_therm", "bcl"],
    "skin": ["skin", "shell", "quiet", "back", "front", "case",
             "therm", "xo_therm", "msm_therm", "sdm_therm"],
    "pmic": ["pmic", "pm8", "pm7", "pm6", "pmk", "pmr", "spmi"],
    "modem": ["modem", "mdm", "pa_therm", "pa0", "pa1", "qfe",
              "rf", "wlan", "wifi", "nss"],
    "camera": ["camera", "cam", "isp", "csi"],
    "display": ["display", "panel", "mdss", "dsi", "brightness"],
}

# ---------------------------------------------------------------------------
#  Temperature thresholds (Celsius)
# ---------------------------------------------------------------------------

TEMP_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "cpu":     {"warm": 55.0, "hot": 75.0, "critical": 95.0, "emergency": 105.0},
    "gpu":     {"warm": 55.0, "hot": 75.0, "critical": 95.0, "emergency": 105.0},
    "battery": {"warm": 38.0, "hot": 43.0, "critical": 50.0, "emergency": 60.0},
    "skin":    {"warm": 37.0, "hot": 42.0, "critical": 48.0, "emergency": 55.0},
    "pmic":    {"warm": 60.0, "hot": 80.0, "critical": 100.0, "emergency": 115.0},
    "modem":   {"warm": 55.0, "hot": 70.0, "critical": 85.0, "emergency": 100.0},
    "camera":  {"warm": 50.0, "hot": 65.0, "critical": 80.0, "emergency": 95.0},
    "display": {"warm": 45.0, "hot": 55.0, "critical": 65.0, "emergency": 75.0},
    "default": {"warm": 50.0, "hot": 70.0, "critical": 90.0, "emergency": 105.0},
}


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class ThermalZone:
    """A single thermal zone read from /sys/class/thermal/thermal_zone*."""
    name: str = ""
    zone_type: str = ""          # cpu, gpu, battery, skin, pmic, modem, ...
    temperature: float = 0.0     # Celsius
    trip_points: List[Dict[str, Any]] = field(default_factory=list)
    policy: str = ""
    is_throttling: bool = False
    status: str = "Normal"       # Normal, Warm, Hot, Critical


@dataclass
class CoolingDevice:
    """A single cooling device from /sys/class/thermal/cooling_device*."""
    name: str = ""
    device_type: str = ""
    current_state: int = 0
    max_state: int = 0
    is_active: bool = False


@dataclass
class CPUThrottleInfo:
    """Per-core CPU throttle information from cpufreq sysfs."""
    core_id: int = 0
    current_freq_mhz: int = 0
    max_freq_mhz: int = 0
    throttle_percent: float = 0.0
    is_throttled: bool = False


@dataclass
class ThermalTestResult:
    """Top-level container returned by ``detect_thermal_status``."""
    connected: bool = False
    error: Optional[str] = None
    thermal_zones: List[ThermalZone] = field(default_factory=list)
    cooling_devices: List[CoolingDevice] = field(default_factory=list)
    cpu_throttle: List[CPUThrottleInfo] = field(default_factory=list)
    battery_temp: float = 0.0
    cpu_temp: float = 0.0
    gpu_temp: float = 0.0
    skin_temp: float = 0.0
    max_temperature: float = 0.0
    hottest_zone: str = ""
    is_any_throttling: bool = False
    throttle_severity: str = "None"   # None, Light, Moderate, Heavy, Critical
    overall_health: str = "Unknown"
    health_score: int = 0
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
#  ADB helper
# ---------------------------------------------------------------------------

def _adb(cmd: str) -> str:
    """Run an ADB shell command and return stdout.

    Parameters
    ----------
    cmd : str
        The command to execute inside ``adb shell``.

    Returns
    -------
    str
        Standard output (stripped).  Returns empty string on any failure.
    """
    full_cmd = f"adb shell {cmd}"
    logger.debug("ADB >>> %s", full_cmd)
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        return proc.stdout.strip()
    except FileNotFoundError:
        logger.error("adb binary not found on PATH")
        return ""
    except subprocess.TimeoutExpired:
        logger.warning("ADB command timed out: %s", full_cmd)
        return ""
    except Exception as exc:
        logger.error("ADB command error: %s", exc)
        return ""


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
#  Step 0 — ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection(callback: ProgressCallback) -> Tuple[bool, str]:
    """Verify ADB connectivity.  Returns (connected, error_or_empty)."""
    _notify(callback, 0.0, "Checking ADB connection...")
    output = _adb("echo __CONNECTED__")
    if "__CONNECTED__" in output:
        _notify(callback, 3.0, "ADB device connected")
        return True, ""

    # Try 'adb devices' to give a better error message
    try:
        proc = subprocess.run(
            "adb devices",
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        lines = proc.stdout.strip().splitlines()
        for line in lines:
            if "\tunauthorized" in line:
                return False, "Device connected but USB Debugging not authorized"
            if "\toffline" in line:
                return False, "Device is offline — replug USB cable"
    except Exception:
        pass

    return False, "No ADB device detected"


# ---------------------------------------------------------------------------
#  Step 1 — Enumerate and read thermal zones
# ---------------------------------------------------------------------------

def _classify_zone_type(zone_name: str) -> str:
    """Classify a thermal zone name into a category (cpu, gpu, etc.)."""
    lower = zone_name.lower()
    for category, keywords in ZONE_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return category
    return "other"


def _classify_temp_status(temp_c: float, zone_type: str) -> str:
    """Classify a temperature reading into Normal/Warm/Hot/Critical."""
    thresholds = TEMP_THRESHOLDS.get(zone_type, TEMP_THRESHOLDS["default"])
    if temp_c >= thresholds["critical"]:
        return "Critical"
    if temp_c >= thresholds["hot"]:
        return "Hot"
    if temp_c >= thresholds["warm"]:
        return "Warm"
    return "Normal"


def _is_throttling(temp_c: float, zone_type: str, trip_points: List[Dict[str, Any]]) -> bool:
    """Determine if the zone is in a throttling state."""
    # If temperature exceeds any passive/active trip point, it is throttling
    for tp in trip_points:
        tp_type = tp.get("type", "").lower()
        tp_temp = tp.get("temperature", 999.0)
        if tp_type in ("passive", "active", "hot") and temp_c >= tp_temp:
            return True

    # Fallback: check against warm threshold
    thresholds = TEMP_THRESHOLDS.get(zone_type, TEMP_THRESHOLDS["default"])
    return temp_c >= thresholds["hot"]


def _read_thermal_zones(callback: ProgressCallback) -> List[ThermalZone]:
    """Read all thermal zones from /sys/class/thermal/thermal_zone*."""
    _notify(callback, 5.0, "Enumerating thermal zones...")
    zones: List[ThermalZone] = []

    # Discover how many thermal zones exist
    listing = _adb("ls -d /sys/class/thermal/thermal_zone* 2>/dev/null")
    if not listing:
        logger.warning("No thermal zones found in /sys/class/thermal/")
        return zones

    zone_paths = [p.strip() for p in listing.splitlines() if p.strip()]
    total_zones = len(zone_paths)
    logger.info("Found %d thermal zone(s)", total_zones)

    for idx, zpath in enumerate(zone_paths):
        zone = ThermalZone()

        # Zone type/name
        zone_type_raw = _adb(f"cat {zpath}/type 2>/dev/null")
        zone.name = zone_type_raw if zone_type_raw else zpath.rsplit("/", 1)[-1]
        zone.zone_type = _classify_zone_type(zone.name)

        # Temperature (millidegrees or raw)
        temp_raw = _adb(f"cat {zpath}/temp 2>/dev/null")
        if temp_raw:
            temp_int = _parse_int(temp_raw)
            # Kernel thermal zones usually report in millidegrees Celsius
            if abs(temp_int) > 1000:
                zone.temperature = temp_int / 1000.0
            elif abs(temp_int) > 200:
                # Some report in tenths of a degree
                zone.temperature = temp_int / 10.0
            else:
                zone.temperature = float(temp_int)

        # Policy
        zone.policy = _adb(f"cat {zpath}/policy 2>/dev/null")

        # Trip points
        zone.trip_points = _read_trip_points(zpath)

        # Determine throttling status
        zone.is_throttling = _is_throttling(
            zone.temperature, zone.zone_type, zone.trip_points
        )
        zone.status = _classify_temp_status(zone.temperature, zone.zone_type)

        zones.append(zone)

        # Progress update periodically
        if total_zones > 0 and idx % 5 == 0:
            progress = 5.0 + (idx / total_zones) * 20.0
            _notify(callback, progress,
                    f"Reading thermal zone {idx+1}/{total_zones}: {zone.name}")

    _notify(callback, 25.0, f"Read {len(zones)} thermal zone(s)")
    return zones


def _read_trip_points(zone_path: str) -> List[Dict[str, Any]]:
    """Read all trip points for a thermal zone."""
    trip_points: List[Dict[str, Any]] = []

    # Discover trip points by listing trip_point_*_temp files
    listing = _adb(f"ls {zone_path}/trip_point_*_temp 2>/dev/null")
    if not listing:
        return trip_points

    for tp_file in listing.splitlines():
        tp_file = tp_file.strip()
        if not tp_file:
            continue

        # Extract trip point index from filename
        match = re.search(r"trip_point_(\d+)_temp", tp_file)
        if not match:
            continue
        tp_idx = match.group(1)

        # Temperature
        temp_raw = _adb(f"cat {zone_path}/trip_point_{tp_idx}_temp 2>/dev/null")
        if not temp_raw:
            continue
        temp_int = _parse_int(temp_raw)
        # Convert from millidegrees if needed
        if abs(temp_int) > 1000:
            temp_c = temp_int / 1000.0
        else:
            temp_c = float(temp_int)

        # Type
        tp_type = _adb(f"cat {zone_path}/trip_point_{tp_idx}_type 2>/dev/null")

        trip_points.append({
            "index": int(tp_idx),
            "temperature": temp_c,
            "type": tp_type if tp_type else "unknown",
        })

    # Sort by temperature ascending
    trip_points.sort(key=lambda tp: tp["temperature"])
    return trip_points


# ---------------------------------------------------------------------------
#  Step 2 — Read cooling devices
# ---------------------------------------------------------------------------

def _read_cooling_devices(callback: ProgressCallback) -> List[CoolingDevice]:
    """Read all cooling devices from /sys/class/thermal/cooling_device*."""
    _notify(callback, 28.0, "Enumerating cooling devices...")
    devices: List[CoolingDevice] = []

    listing = _adb("ls -d /sys/class/thermal/cooling_device* 2>/dev/null")
    if not listing:
        logger.info("No cooling devices found")
        return devices

    dev_paths = [p.strip() for p in listing.splitlines() if p.strip()]
    total_devs = len(dev_paths)
    logger.info("Found %d cooling device(s)", total_devs)

    for idx, dpath in enumerate(dev_paths):
        cd = CoolingDevice()

        # Type / name
        cd_type = _adb(f"cat {dpath}/type 2>/dev/null")
        cd.name = cd_type if cd_type else dpath.rsplit("/", 1)[-1]
        cd.device_type = cd.name

        # Current state
        cur_raw = _adb(f"cat {dpath}/cur_state 2>/dev/null")
        cd.current_state = _parse_int(cur_raw)

        # Max state
        max_raw = _adb(f"cat {dpath}/max_state 2>/dev/null")
        cd.max_state = _parse_int(max_raw)

        # Determine if actively cooling
        cd.is_active = cd.current_state > 0

        devices.append(cd)

        if total_devs > 0 and idx % 10 == 0:
            progress = 28.0 + (idx / total_devs) * 10.0
            _notify(callback, progress,
                    f"Reading cooling device {idx+1}/{total_devs}: {cd.name}")

    _notify(callback, 38.0, f"Read {len(devices)} cooling device(s)")
    return devices


# ---------------------------------------------------------------------------
#  Step 3 — CPU frequency / throttle detection
# ---------------------------------------------------------------------------

def _read_cpu_throttle(callback: ProgressCallback) -> List[CPUThrottleInfo]:
    """Read per-core CPU frequency to detect thermal throttling."""
    _notify(callback, 40.0, "Reading CPU frequency scaling info...")
    cores: List[CPUThrottleInfo] = []

    # Discover online CPUs
    listing = _adb("ls -d /sys/devices/system/cpu/cpu[0-9]* 2>/dev/null")
    if not listing:
        logger.warning("No CPU cores found in /sys/devices/system/cpu/")
        return cores

    cpu_paths = sorted(
        [p.strip() for p in listing.splitlines()
         if p.strip() and re.search(r"cpu\d+$", p.strip())],
        key=lambda p: int(re.search(r"cpu(\d+)", p).group(1))  # type: ignore[union-attr]
    )

    total_cores = len(cpu_paths)
    logger.info("Found %d CPU core(s)", total_cores)

    for idx, cpath in enumerate(cpu_paths):
        info = CPUThrottleInfo()

        # Extract core ID
        core_match = re.search(r"cpu(\d+)", cpath)
        info.core_id = int(core_match.group(1)) if core_match else idx

        # Current scaling frequency (kHz)
        cur_freq_raw = _adb(f"cat {cpath}/cpufreq/scaling_cur_freq 2>/dev/null")
        cur_freq_khz = _parse_int(cur_freq_raw)
        info.current_freq_mhz = cur_freq_khz // 1000 if cur_freq_khz > 0 else 0

        # Max allowed scaling frequency (kHz) — this is the policy max
        max_freq_raw = _adb(f"cat {cpath}/cpufreq/scaling_max_freq 2>/dev/null")
        scaling_max_khz = _parse_int(max_freq_raw)

        # Hardware maximum frequency (kHz)
        hw_max_raw = _adb(f"cat {cpath}/cpufreq/cpuinfo_max_freq 2>/dev/null")
        hw_max_khz = _parse_int(hw_max_raw)

        # Use hardware max as the reference; fall back to scaling max
        reference_khz = hw_max_khz if hw_max_khz > 0 else scaling_max_khz
        info.max_freq_mhz = reference_khz // 1000 if reference_khz > 0 else 0

        # Calculate throttle percentage
        if reference_khz > 0 and cur_freq_khz > 0:
            # Throttle = how much below max we are running
            if cur_freq_khz < reference_khz:
                info.throttle_percent = round(
                    (1.0 - cur_freq_khz / reference_khz) * 100.0, 1
                )
                info.is_throttled = True
            else:
                info.throttle_percent = 0.0
                info.is_throttled = False
        elif cur_freq_khz == 0 and reference_khz > 0:
            # Core might be offline
            info.throttle_percent = 100.0
            info.is_throttled = True

        # Also check if scaling_max_freq < cpuinfo_max_freq (policy capping)
        if hw_max_khz > 0 and scaling_max_khz > 0:
            if scaling_max_khz < hw_max_khz * 0.95:
                # The thermal governor has capped the maximum frequency
                info.is_throttled = True
                if info.throttle_percent == 0.0:
                    info.throttle_percent = round(
                        (1.0 - scaling_max_khz / hw_max_khz) * 100.0, 1
                    )

        cores.append(info)

    _notify(callback, 52.0, f"Read {len(cores)} CPU core frequencies")
    return cores


# ---------------------------------------------------------------------------
#  Step 4 — Battery temperature (dedicated read)
# ---------------------------------------------------------------------------

def _read_battery_temperature(callback: ProgressCallback) -> float:
    """Read battery temperature from power_supply sysfs."""
    _notify(callback, 54.0, "Reading battery temperature...")

    # Try direct sysfs first
    raw = _adb("cat /sys/class/power_supply/battery/temp 2>/dev/null")
    if raw:
        temp_int = _parse_int(raw)
        if abs(temp_int) > 100:
            return temp_int / 10.0  # Tenths of degrees
        return float(temp_int)

    # Fallback: dumpsys battery
    dumpsys = _adb("dumpsys battery")
    if dumpsys:
        match = re.search(r"temperature:\s*(\d+)", dumpsys)
        if match:
            temp_val = int(match.group(1))
            if temp_val > 100:
                return temp_val / 10.0
            return float(temp_val)

    return 0.0


# ---------------------------------------------------------------------------
#  Step 5 — Thermal service dump (Android thermal HAL)
# ---------------------------------------------------------------------------

def _read_thermal_service(callback: ProgressCallback) -> Dict[str, Any]:
    """Parse output of 'dumpsys thermalservice' for additional context."""
    _notify(callback, 56.0, "Reading thermal service dump...")
    result: Dict[str, Any] = {
        "hal_connected": False,
        "current_temperatures": [],
        "current_status": "unknown",
        "cooling_devices_status": [],
    }

    output = _adb("dumpsys thermalservice")
    if not output:
        return result

    result["hal_connected"] = "thermal hal" in output.lower() or \
                              "IThermal" in output

    # Parse temperature entries like:
    # Temperature{mValue=35.1, mType=3, mName=battery, mStatus=0}
    temp_pattern = re.compile(
        r"Temperature\{.*?mValue=([\d.\-]+).*?mType=(\d+).*?"
        r"mName=(\w+).*?mStatus=(\d+)",
        re.DOTALL,
    )
    for m in temp_pattern.finditer(output):
        result["current_temperatures"].append({
            "value": float(m.group(1)),
            "type_id": int(m.group(2)),
            "name": m.group(3),
            "status": int(m.group(4)),
        })

    # Parse thermal status
    status_match = re.search(r"Thermal Status:\s*(\d+)", output)
    if status_match:
        status_code = int(status_match.group(1))
        status_map = {
            0: "none",
            1: "light",
            2: "moderate",
            3: "severe",
            4: "critical",
            5: "emergency",
            6: "shutdown",
        }
        result["current_status"] = status_map.get(status_code, f"unknown({status_code})")

    return result


# ---------------------------------------------------------------------------
#  Step 6 — Qualcomm-specific thermal reads
# ---------------------------------------------------------------------------

def _read_qualcomm_thermal(callback: ProgressCallback) -> Dict[str, Any]:
    """Read Qualcomm-specific thermal data (tz-by-name, msm_thermal)."""
    _notify(callback, 60.0, "Reading Qualcomm-specific thermal data...")
    qcom_data: Dict[str, Any] = {
        "tz_by_name": {},
        "msm_thermal_params": {},
        "is_qualcomm": False,
    }

    # Check for Qualcomm tz-by-name directory
    tz_listing = _adb(
        "ls -d /sys/devices/virtual/thermal/tz-by-name/* 2>/dev/null"
    )
    if tz_listing:
        qcom_data["is_qualcomm"] = True
        for tz_path in tz_listing.splitlines():
            tz_path = tz_path.strip()
            if not tz_path:
                continue
            tz_name = tz_path.rsplit("/", 1)[-1]
            temp_raw = _adb(f"cat {tz_path}/temp 2>/dev/null")
            if temp_raw:
                temp_int = _parse_int(temp_raw)
                if abs(temp_int) > 1000:
                    qcom_data["tz_by_name"][tz_name] = temp_int / 1000.0
                else:
                    qcom_data["tz_by_name"][tz_name] = float(temp_int)

    # Read msm_thermal parameters
    msm_listing = _adb(
        "ls /sys/module/msm_thermal/parameters/ 2>/dev/null"
    )
    if msm_listing:
        qcom_data["is_qualcomm"] = True
        for param in msm_listing.splitlines():
            param = param.strip()
            if not param:
                continue
            val = _adb(f"cat /sys/module/msm_thermal/parameters/{param} 2>/dev/null")
            if val:
                qcom_data["msm_thermal_params"][param] = val

    return qcom_data


# ---------------------------------------------------------------------------
#  Step 7 — Analysis and scoring
# ---------------------------------------------------------------------------

def _extract_summary_temps(
    zones: List[ThermalZone],
    battery_temp: float,
) -> Tuple[float, float, float, float, float, str]:
    """Extract key summary temperatures from all thermal zones.

    Returns
    -------
    tuple
        (cpu_temp, gpu_temp, skin_temp, max_temp, battery_temp, hottest_zone)
    """
    cpu_temps: List[float] = []
    gpu_temps: List[float] = []
    skin_temps: List[float] = []
    max_temp: float = 0.0
    hottest_zone: str = ""

    for z in zones:
        if z.temperature <= -40 or z.temperature > 200:
            continue  # Skip obviously bogus readings

        if z.temperature > max_temp:
            max_temp = z.temperature
            hottest_zone = z.name

        if z.zone_type == "cpu":
            cpu_temps.append(z.temperature)
        elif z.zone_type == "gpu":
            gpu_temps.append(z.temperature)
        elif z.zone_type == "skin":
            skin_temps.append(z.temperature)
        elif z.zone_type == "battery":
            if battery_temp == 0.0:
                battery_temp = z.temperature

    cpu_temp = max(cpu_temps) if cpu_temps else 0.0
    gpu_temp = max(gpu_temps) if gpu_temps else 0.0
    skin_temp = max(skin_temps) if skin_temps else 0.0

    # Also check if battery temp is the hottest
    if battery_temp > max_temp:
        max_temp = battery_temp
        hottest_zone = "battery"

    return cpu_temp, gpu_temp, skin_temp, max_temp, battery_temp, hottest_zone


def _determine_throttle_severity(
    zones: List[ThermalZone],
    cpu_throttle: List[CPUThrottleInfo],
    cooling_devices: List[CoolingDevice],
) -> str:
    """Classify overall throttle severity.

    Returns one of: None, Light, Moderate, Heavy, Critical
    """
    # Count throttling zones
    throttling_zones = [z for z in zones if z.is_throttling]
    critical_zones = [z for z in zones if z.status == "Critical"]
    hot_zones = [z for z in zones if z.status == "Hot"]

    # Count throttled CPU cores
    throttled_cores = [c for c in cpu_throttle if c.is_throttled]
    avg_throttle = 0.0
    if throttled_cores:
        avg_throttle = sum(c.throttle_percent for c in throttled_cores) / len(throttled_cores)

    # Count active cooling devices
    active_coolers = [cd for cd in cooling_devices if cd.is_active]
    high_state_coolers = [
        cd for cd in active_coolers
        if cd.max_state > 0 and cd.current_state >= cd.max_state * 0.7
    ]

    # Severity classification
    if critical_zones:
        return "Critical"

    if len(hot_zones) >= 3 or avg_throttle >= 50.0:
        return "Heavy"

    if (len(hot_zones) >= 1 or avg_throttle >= 25.0 or
            len(high_state_coolers) >= 2):
        return "Moderate"

    if (throttling_zones or throttled_cores or active_coolers):
        return "Light"

    return "None"


def _compute_health_score(
    zones: List[ThermalZone],
    cpu_throttle: List[CPUThrottleInfo],
    cooling_devices: List[CoolingDevice],
    max_temp: float,
    battery_temp: float,
    cpu_temp: float,
    skin_temp: float,
) -> int:
    """Compute a 0-100 thermal health score.

    Weighted factors:
      - Max temperature (relative to critical):  30%
      - CPU throttle severity:                   25%
      - Battery temperature:                     20%
      - Skin temperature:                        15%
      - Active cooling device ratio:             10%
    """
    # -- Max temperature score (100 if cool, 0 if at critical) --
    # Use 40 C as perfect and 100 C as worst
    if max_temp <= 40:
        temp_score = 100.0
    elif max_temp >= 100:
        temp_score = 0.0
    else:
        temp_score = max(0.0, 100.0 - ((max_temp - 40.0) / 60.0) * 100.0)

    # -- CPU throttle score --
    if cpu_throttle:
        throttle_pcts = [c.throttle_percent for c in cpu_throttle]
        avg_throttle = sum(throttle_pcts) / len(throttle_pcts)
        # 0% throttle = 100, 80% throttle = 0
        cpu_score = max(0.0, 100.0 - (avg_throttle / 80.0) * 100.0)
    else:
        cpu_score = 100.0

    # -- Battery temperature score --
    if battery_temp <= 30:
        batt_score = 100.0
    elif battery_temp >= 50:
        batt_score = 0.0
    else:
        batt_score = max(0.0, 100.0 - ((battery_temp - 30.0) / 20.0) * 100.0)

    # -- Skin temperature score --
    if skin_temp <= 33:
        skin_score = 100.0
    elif skin_temp >= 48:
        skin_score = 0.0
    else:
        skin_score = max(0.0, 100.0 - ((skin_temp - 33.0) / 15.0) * 100.0)

    # -- Active cooling ratio score --
    if cooling_devices:
        active_count = sum(1 for cd in cooling_devices if cd.is_active)
        active_ratio = active_count / len(cooling_devices)
        cooling_score = max(0.0, 100.0 - active_ratio * 100.0)
    else:
        cooling_score = 100.0

    # Weighted sum
    score = (
        temp_score * 0.30 +
        cpu_score * 0.25 +
        batt_score * 0.20 +
        skin_score * 0.15 +
        cooling_score * 0.10
    )
    return max(0, min(100, int(round(score))))


def _generate_warnings(
    zones: List[ThermalZone],
    cpu_throttle: List[CPUThrottleInfo],
    cooling_devices: List[CoolingDevice],
    battery_temp: float,
    cpu_temp: float,
    gpu_temp: float,
    skin_temp: float,
    max_temp: float,
    hottest_zone: str,
    thermal_service: Dict[str, Any],
) -> List[str]:
    """Generate actionable warnings for a repair technician."""
    warnings: List[str] = []

    # --- Critical temperature zones ---
    critical_zones = [z for z in zones if z.status == "Critical"]
    for z in critical_zones:
        warnings.append(
            f"CRITICAL: {z.name} ({z.zone_type}) at {z.temperature:.1f} C "
            f"— exceeds critical threshold. Check for thermal paste degradation, "
            f"blocked heat pipes, or shorted components."
        )

    # --- Hot zones ---
    hot_zones = [z for z in zones if z.status == "Hot"]
    for z in hot_zones:
        if z not in critical_zones:
            warnings.append(
                f"HOT: {z.name} ({z.zone_type}) at {z.temperature:.1f} C "
                f"— actively throttling. Sustained high temp may cause damage."
            )

    # --- Battery thermal warning ---
    if battery_temp > 45.0:
        warnings.append(
            f"Battery temperature critically high ({battery_temp:.1f} C). "
            f"Risk of swelling or thermal runaway. Disconnect and inspect."
        )
    elif battery_temp > 40.0:
        warnings.append(
            f"Battery temperature elevated ({battery_temp:.1f} C). "
            f"Monitor for swelling. May indicate charging IC fault or "
            f"degraded battery."
        )
    elif battery_temp < 5.0 and battery_temp > 0.0:
        warnings.append(
            f"Battery temperature low ({battery_temp:.1f} C). "
            f"Charging at low temperatures may cause lithium plating."
        )

    # --- CPU throttle warnings ---
    throttled_cores = [c for c in cpu_throttle if c.is_throttled]
    if throttled_cores:
        max_throttle = max(c.throttle_percent for c in throttled_cores)
        avg_throttle = sum(c.throttle_percent for c in throttled_cores) / len(throttled_cores)

        if max_throttle >= 60.0:
            warnings.append(
                f"Severe CPU throttling detected: {len(throttled_cores)}/{len(cpu_throttle)} "
                f"cores throttled (max {max_throttle:.0f}%, avg {avg_throttle:.0f}%). "
                f"Thermal paste may need replacement. Check heat dissipation path."
            )
        elif max_throttle >= 30.0:
            warnings.append(
                f"Moderate CPU throttling: {len(throttled_cores)}/{len(cpu_throttle)} "
                f"cores throttled (avg {avg_throttle:.0f}%). "
                f"Performance will be reduced under load."
            )
        elif max_throttle > 0.0:
            warnings.append(
                f"Light CPU throttling: {len(throttled_cores)} core(s) "
                f"running below max frequency."
            )

    # --- Skin temperature warning ---
    if skin_temp > 44.0:
        warnings.append(
            f"Skin temperature {skin_temp:.1f} C exceeds comfortable limit. "
            f"Device will feel uncomfortably hot to hold."
        )
    elif skin_temp > 40.0:
        warnings.append(
            f"Skin temperature {skin_temp:.1f} C — device is warm to the touch."
        )

    # --- GPU temperature warning ---
    if gpu_temp > 80.0:
        warnings.append(
            f"GPU temperature {gpu_temp:.1f} C — heavy throttling likely. "
            f"Check for graphical artifacts that may indicate damage."
        )

    # --- Cooling device saturation ---
    if cooling_devices:
        saturated = [
            cd for cd in cooling_devices
            if cd.max_state > 0 and cd.current_state >= cd.max_state
        ]
        if saturated:
            names = ", ".join(cd.name for cd in saturated[:5])
            warnings.append(
                f"Cooling device(s) at maximum state: {names}. "
                f"Thermal management is maxed out — further temp rise is uncontrolled."
            )

    # --- Thermal zones with no readings ---
    dead_zones = [z for z in zones if z.temperature == 0.0 and z.zone_type != "other"]
    if dead_zones:
        names = ", ".join(z.name for z in dead_zones[:5])
        warnings.append(
            f"Thermal zone(s) reporting 0 C: {names}. "
            f"Possible sensor failure or driver not loaded."
        )

    # --- Negative temperature readings (usually sensor fault) ---
    neg_zones = [z for z in zones if z.temperature < -20.0]
    if neg_zones:
        names = ", ".join(f"{z.name}={z.temperature:.0f}C" for z in neg_zones[:5])
        warnings.append(
            f"Abnormal negative temperature readings: {names}. "
            f"Likely sensor hardware fault or miscalibration."
        )

    # --- Thermal service HAL not connected ---
    if not thermal_service.get("hal_connected", False):
        warnings.append(
            "Android Thermal HAL not responding. Thermal management may "
            "not function correctly — OEM thermal policy unavailable."
        )

    # --- Thermal service reports severe or worse ---
    svc_status = thermal_service.get("current_status", "unknown")
    if svc_status in ("severe", "critical", "emergency", "shutdown"):
        warnings.append(
            f"Android ThermalService reports status: {svc_status.upper()}. "
            f"Device is in emergency thermal mitigation mode."
        )

    return warnings


def _generate_overall_health(
    score: int,
    throttle_severity: str,
    warnings: List[str],
    max_temp: float,
    hottest_zone: str,
    zones: List[ThermalZone],
    cpu_throttle: List[CPUThrottleInfo],
    cooling_devices: List[CoolingDevice],
    battery_temp: float,
    cpu_temp: float,
    gpu_temp: float,
    skin_temp: float,
) -> str:
    """Generate a multi-line overall thermal health assessment."""
    lines: List[str] = []

    # --- Verdict ---
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

    lines.append(f"Thermal Health: {verdict} ({score}/100)")
    lines.append(f"Throttle Severity: {throttle_severity}")
    lines.append("")

    # --- Key temperatures ---
    lines.append("Key Temperatures:")
    if cpu_temp > 0:
        lines.append(f"  CPU          : {cpu_temp:.1f} C")
    if gpu_temp > 0:
        lines.append(f"  GPU          : {gpu_temp:.1f} C")
    if battery_temp > 0:
        lines.append(f"  Battery      : {battery_temp:.1f} C")
    if skin_temp > 0:
        lines.append(f"  Skin         : {skin_temp:.1f} C")
    lines.append(f"  Max (overall): {max_temp:.1f} C ({hottest_zone})")
    lines.append("")

    # --- Thermal zones summary ---
    critical_count = sum(1 for z in zones if z.status == "Critical")
    hot_count = sum(1 for z in zones if z.status == "Hot")
    warm_count = sum(1 for z in zones if z.status == "Warm")
    normal_count = sum(1 for z in zones if z.status == "Normal")
    lines.append(f"Thermal Zones  : {len(zones)} total")
    lines.append(f"  Normal={normal_count}  Warm={warm_count}  "
                 f"Hot={hot_count}  Critical={critical_count}")
    lines.append("")

    # --- CPU throttle summary ---
    if cpu_throttle:
        throttled = [c for c in cpu_throttle if c.is_throttled]
        lines.append(f"CPU Cores      : {len(cpu_throttle)} total, "
                     f"{len(throttled)} throttled")
        for c in cpu_throttle:
            flag = " [THROTTLED]" if c.is_throttled else ""
            lines.append(f"  Core {c.core_id}: {c.current_freq_mhz} / "
                         f"{c.max_freq_mhz} MHz "
                         f"({c.throttle_percent:.0f}% reduced){flag}")
        lines.append("")

    # --- Cooling devices summary ---
    if cooling_devices:
        active = [cd for cd in cooling_devices if cd.is_active]
        lines.append(f"Cooling Devices: {len(cooling_devices)} total, "
                     f"{len(active)} active")
        for cd in active[:10]:
            lines.append(f"  {cd.name}: state {cd.current_state}/{cd.max_state}")
        if len(active) > 10:
            lines.append(f"  ... and {len(active) - 10} more")
        lines.append("")

    # --- Warnings ---
    if warnings:
        lines.append("WARNINGS:")
        for w in warnings:
            lines.append(f"  - {w}")
    else:
        lines.append("No warnings — thermal system operating normally.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_thermal_status(
    callback: ProgressCallback = None,
) -> ThermalTestResult:
    """Run the full thermal diagnostic sequence.

    Parameters
    ----------
    callback : optional
        A callable ``(pct: float, msg: str) -> None`` invoked with progress
        updates.  *pct* ranges from 0 to 100.

    Returns
    -------
    ThermalTestResult
        Populated result dataclass with all thermal data and an overall
        health assessment string.
    """
    result = ThermalTestResult()
    logger.info("Starting thermal test sequence")

    # -- Step 0: ADB connection --
    connected, err = _check_adb_connection(callback)
    if not connected:
        result.connected = False
        result.error = err
        result.overall_health = f"UNABLE TO TEST -- {err}"
        _notify(callback, 100.0, f"Test aborted: {err}")
        return result
    result.connected = True

    try:
        # -- Step 1: Read thermal zones --
        result.thermal_zones = _read_thermal_zones(callback)

        # -- Step 2: Read cooling devices --
        result.cooling_devices = _read_cooling_devices(callback)

        # -- Step 3: CPU frequency / throttle --
        result.cpu_throttle = _read_cpu_throttle(callback)

        # -- Step 4: Battery temperature --
        result.battery_temp = _read_battery_temperature(callback)

        # -- Step 5: Thermal service --
        thermal_service = _read_thermal_service(callback)

        # -- Step 6: Qualcomm-specific --
        qcom_data = _read_qualcomm_thermal(callback)

        # Merge Qualcomm tz-by-name data into zones if not already present
        if qcom_data["is_qualcomm"] and qcom_data["tz_by_name"]:
            existing_names = {z.name.lower() for z in result.thermal_zones}
            for tz_name, temp_c in qcom_data["tz_by_name"].items():
                if tz_name.lower() not in existing_names:
                    zone = ThermalZone(
                        name=tz_name,
                        zone_type=_classify_zone_type(tz_name),
                        temperature=temp_c,
                    )
                    zone.status = _classify_temp_status(temp_c, zone.zone_type)
                    zone.is_throttling = _is_throttling(temp_c, zone.zone_type, [])
                    result.thermal_zones.append(zone)

        # -- Step 7: Analysis --
        _notify(callback, 70.0, "Analyzing thermal data...")

        # Extract summary temperatures
        (result.cpu_temp, result.gpu_temp, result.skin_temp,
         result.max_temperature, result.battery_temp,
         result.hottest_zone) = _extract_summary_temps(
            result.thermal_zones, result.battery_temp
        )

        # Check for any throttling
        result.is_any_throttling = (
            any(z.is_throttling for z in result.thermal_zones) or
            any(c.is_throttled for c in result.cpu_throttle) or
            any(cd.is_active for cd in result.cooling_devices)
        )

        # Throttle severity
        result.throttle_severity = _determine_throttle_severity(
            result.thermal_zones, result.cpu_throttle, result.cooling_devices
        )

        # Health score
        _notify(callback, 80.0, "Computing thermal health score...")
        result.health_score = _compute_health_score(
            result.thermal_zones,
            result.cpu_throttle,
            result.cooling_devices,
            result.max_temperature,
            result.battery_temp,
            result.cpu_temp,
            result.skin_temp,
        )

        # Warnings
        _notify(callback, 85.0, "Generating warnings...")
        result.warnings = _generate_warnings(
            result.thermal_zones,
            result.cpu_throttle,
            result.cooling_devices,
            result.battery_temp,
            result.cpu_temp,
            result.gpu_temp,
            result.skin_temp,
            result.max_temperature,
            result.hottest_zone,
            thermal_service,
        )

        # Overall health
        _notify(callback, 92.0, "Generating overall assessment...")
        result.overall_health = _generate_overall_health(
            result.health_score,
            result.throttle_severity,
            result.warnings,
            result.max_temperature,
            result.hottest_zone,
            result.thermal_zones,
            result.cpu_throttle,
            result.cooling_devices,
            result.battery_temp,
            result.cpu_temp,
            result.gpu_temp,
            result.skin_temp,
        )

    except Exception as exc:
        logger.exception("Thermal test sequence failed")
        result.error = str(exc)
        result.overall_health = f"TEST ERROR -- {exc}"

    _notify(callback, 100.0, "Thermal test complete")
    logger.info("Thermal test sequence finished")
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
    print("  Thermal Tester -- Mooxy AI Fault Detector")
    print("=" * 70)
    print()

    test_result = detect_thermal_status(callback=_cli_callback)

    print()
    print("-" * 70)
    print(test_result.overall_health)
    print("-" * 70)

    if "--json" in sys.argv:
        print()
        print(json.dumps(asdict(test_result), indent=2, default=str))
