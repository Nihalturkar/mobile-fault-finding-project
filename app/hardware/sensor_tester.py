"""
Advanced Sensor Testing Module for Mooxy AI Fault Detector.

Performs comprehensive sensor diagnostics via ADB by reading sensorservice
dumps, sysfs sensor nodes, input device enumeration, and hardware property
queries.  Identifies sensor ICs against a detailed knowledge database,
evaluates individual sensor health, and computes an aggregate health score.

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
#  Constants & sysfs paths
# ---------------------------------------------------------------------------

# Sysfs sensor base paths probed in order of likelihood
SENSOR_SYSFS_PATHS: List[str] = [
    "/sys/class/sensors",
    "/sys/bus/iio/devices",
    "/sys/devices/virtual/sensors",
    "/sys/devices/platform/sensors",
]

# Individual sensor type sysfs subdirectories
SENSOR_TYPE_SYSFS: Dict[str, List[str]] = {
    "accelerometer": [
        "/sys/class/sensors/accelerometer",
        "/sys/class/sensors/accel",
        "/sys/class/sensors/lsm6dso_accel",
        "/sys/class/sensors/bmi160_accel",
        "/sys/class/sensors/icm42607_accel",
    ],
    "gyroscope": [
        "/sys/class/sensors/gyroscope",
        "/sys/class/sensors/gyro",
        "/sys/class/sensors/lsm6dso_gyro",
        "/sys/class/sensors/bmi160_gyro",
        "/sys/class/sensors/icm42607_gyro",
    ],
    "magnetometer": [
        "/sys/class/sensors/magnetic_field",
        "/sys/class/sensors/compass",
        "/sys/class/sensors/magnetometer",
        "/sys/class/sensors/ak09918",
        "/sys/class/sensors/lis2mdl",
    ],
    "proximity": [
        "/sys/class/sensors/proximity",
        "/sys/class/sensors/prox",
        "/sys/class/sensors/stk3311",
        "/sys/class/sensors/vcnl4040",
    ],
    "light": [
        "/sys/class/sensors/light",
        "/sys/class/sensors/als",
        "/sys/class/sensors/ambient_light",
        "/sys/class/sensors/tmd2772",
        "/sys/class/sensors/ltr559",
    ],
    "barometer": [
        "/sys/class/sensors/barometer",
        "/sys/class/sensors/pressure",
        "/sys/class/sensors/bmp380",
        "/sys/class/sensors/bmp390",
    ],
    "gravity": [
        "/sys/class/sensors/gravity",
        "/sys/class/sensors/gravity_sensor",
    ],
    "step_counter": [
        "/sys/class/sensors/step_counter",
        "/sys/class/sensors/step_cnt",
        "/sys/class/sensors/pedometer",
    ],
}

# Sensor type strings as reported by sensorservice (Android sensor type IDs)
SENSOR_TYPE_IDS: Dict[int, str] = {
    1: "accelerometer",
    2: "magnetometer",
    4: "gyroscope",
    5: "light",
    6: "barometer",
    8: "proximity",
    9: "gravity",
    19: "step_counter",
    10: "rotation_vector",
    11: "humidity",
    13: "ambient_temperature",
    15: "game_rotation_vector",
    16: "gyroscope_uncalibrated",
    17: "significant_motion",
    18: "step_detector",
    20: "geomagnetic_rotation_vector",
    28: "pose_6dof",
    35: "hinge_angle",
}

# Human-readable sensor type labels
SENSOR_TYPE_LABELS: Dict[str, str] = {
    "accelerometer": "Accelerometer",
    "gyroscope": "Gyroscope",
    "magnetometer": "Magnetometer / Compass",
    "proximity": "Proximity Sensor",
    "light": "Ambient Light Sensor",
    "barometer": "Barometer / Pressure",
    "gravity": "Gravity Sensor",
    "step_counter": "Step Counter",
    "rotation_vector": "Rotation Vector",
    "humidity": "Humidity Sensor",
    "ambient_temperature": "Temperature Sensor",
    "game_rotation_vector": "Game Rotation Vector",
    "gyroscope_uncalibrated": "Gyroscope (Uncalibrated)",
    "significant_motion": "Significant Motion Detector",
    "step_detector": "Step Detector",
    "geomagnetic_rotation_vector": "Geomagnetic Rotation Vector",
}


# ---------------------------------------------------------------------------
#  Known Sensor ICs database
# ---------------------------------------------------------------------------

KNOWN_SENSOR_ICS: Dict[str, Dict[str, Any]] = {
    # ── Bosch Sensortec ──
    "BMI160": {
        "manufacturer": "Bosch Sensortec",
        "type": "accelerometer+gyroscope",
        "description": "6-axis IMU (accel + gyro), low power, widely used in mid-range devices",
        "common_failures": [
            "Gyroscope drift after drop impact",
            "Accelerometer offset calibration lost after firmware update",
            "I2C/SPI bus hang requiring power cycle",
            "Intermittent data stall under high-g shock",
        ],
    },
    "BMI260": {
        "manufacturer": "Bosch Sensortec",
        "type": "accelerometer+gyroscope",
        "description": "6-axis IMU with improved low-noise gyroscope, successor to BMI160",
        "common_failures": [
            "Gyroscope noise floor increase after thermal cycling",
            "Self-test failure after prolonged vibration exposure",
            "SPI mode bit corruption on noisy power rail",
            "Step counter inaccuracy after firmware rollback",
        ],
    },
    "BMI270": {
        "manufacturer": "Bosch Sensortec",
        "type": "accelerometer+gyroscope",
        "description": "6-axis IMU optimised for wearables and AR, ultra-low power",
        "common_failures": [
            "Activity recognition false triggers in pocket mode",
            "Gyroscope zero-rate offset drift in cold temperatures",
            "Firmware config CRC mismatch after incomplete OTA",
            "Interrupt line stuck high after deep sleep wake",
        ],
    },
    "BMA255": {
        "manufacturer": "Bosch Sensortec",
        "type": "accelerometer",
        "description": "3-axis MEMS accelerometer, 14-bit, low-power, entry-level phones",
        "common_failures": [
            "Auto-rotation stuck after drop impact",
            "Offset exceeds spec after reflow soldering repair",
            "I2C address conflict with aftermarket flex cable",
            "Data ready interrupt not firing after sleep resume",
        ],
    },
    "BMA456": {
        "manufacturer": "Bosch Sensortec",
        "type": "accelerometer",
        "description": "3-axis accelerometer with built-in step counter and activity recognition",
        "common_failures": [
            "Step counter over-counting on vibrating surfaces",
            "Any-motion interrupt latching in noisy RF environment",
            "Feature engine firmware corruption after battery disconnect",
            "FIFO watermark interrupt missed under high ODR",
        ],
    },
    "BMM150": {
        "manufacturer": "Bosch Sensortec",
        "type": "magnetometer",
        "description": "3-axis geomagnetic sensor, low power, commonly paired with BMI160/270",
        "common_failures": [
            "Compass heading offset after exposure to strong magnets (case/mount)",
            "Hard-iron calibration lost after factory reset",
            "Data output saturated near NFC antenna during payment",
            "Self-test X/Y axis failure after board-level rework",
        ],
    },
    "BMP380": {
        "manufacturer": "Bosch Sensortec",
        "type": "barometer",
        "description": "High-precision barometric pressure sensor, +/- 0.5 hPa accuracy",
        "common_failures": [
            "Pressure reading offset after water ingress through vent hole",
            "Altitude calculation drift in sealed device (blocked vent)",
            "Temperature compensation failure in extreme cold",
            "I2C NACK after prolonged high-humidity exposure",
        ],
    },
    "BMP390": {
        "manufacturer": "Bosch Sensortec",
        "type": "barometer",
        "description": "Next-gen barometric pressure sensor, +/- 0.3 hPa, lower noise",
        "common_failures": [
            "Vent hole blocked by adhesive during screen replacement",
            "Output stuck at last reading after power glitch",
            "Calibration PROM read failure on cold boot",
            "Noise floor increase after ultrasonic cleaning",
        ],
    },
    "BME680": {
        "manufacturer": "Bosch Sensortec",
        "type": "environment",
        "description": "4-in-1 environmental sensor: gas, pressure, humidity, temperature",
        "common_failures": [
            "Gas sensor resistance baseline shift after solvent exposure",
            "Humidity reading stuck at 100% after condensation event",
            "Heater element degradation reducing VOC sensitivity",
            "Long stabilisation time (burn-in) after replacement",
        ],
    },

    # ── STMicroelectronics ──
    "LSM6DSO": {
        "manufacturer": "STMicroelectronics",
        "type": "accelerometer+gyroscope",
        "description": "6-axis IMU, always-on accel, machine learning core, flagship devices",
        "common_failures": [
            "Machine learning core misclassification after OTA update",
            "Gyroscope self-test failure at elevated temperature (>55C)",
            "FIFO pattern mismatch when switching between modes",
            "Interrupt routing broken after kernel driver update",
        ],
    },
    "LSM6DSR": {
        "manufacturer": "STMicroelectronics",
        "type": "accelerometer+gyroscope",
        "description": "6-axis IMU with OIS (Optical Image Stabilization) interface",
        "common_failures": [
            "OIS data path latency increase causing camera shake",
            "Gyro sensitivity shift after mechanical shock to camera module",
            "Auxiliary SPI interface timeout with camera ISP",
            "Cross-axis sensitivity out of spec after drop test",
        ],
    },
    "LSM6DSOX": {
        "manufacturer": "STMicroelectronics",
        "type": "accelerometer+gyroscope",
        "description": "6-axis IMU with machine learning core and finite state machine",
        "common_failures": [
            "FSM program corruption after unexpected power loss",
            "Pedometer count reset on deep sleep entry",
            "I3C mode handshake failure with certain SoC revisions",
            "Activity/inactivity detection false positives in vehicle",
        ],
    },
    "LIS2DW12": {
        "manufacturer": "STMicroelectronics",
        "type": "accelerometer",
        "description": "3-axis MEMS accelerometer, ultra-low power (< 1uA), 14-bit",
        "common_failures": [
            "Wake-up interrupt not triggering after battery replacement",
            "Offset drift exceeding 40mg after thermal shock",
            "SPI 4-wire/3-wire mode confusion after driver reload",
            "Free-fall detection false alarms on uneven surfaces",
        ],
    },
    "LIS3DH": {
        "manufacturer": "STMicroelectronics",
        "type": "accelerometer",
        "description": "3-axis MEMS accelerometer, 16-bit, versatile general-purpose sensor",
        "common_failures": [
            "FIFO overrun causing missed orientation change events",
            "Click/double-click detection unreliable after screen replacement",
            "Temperature sensor output erratic after ESD event",
            "BDU bit not set causing torn reads in multi-byte access",
        ],
    },
    "LIS2MDL": {
        "manufacturer": "STMicroelectronics",
        "type": "magnetometer",
        "description": "3-axis magnetometer, ultra-low power, high-performance digital output",
        "common_failures": [
            "Hard-iron offset exceeds calibration range near metal case",
            "Continuous mode data rate drops to zero after I2C bus error",
            "Soft-iron compensation matrix singular after refurbishment",
            "Magnetic interference from replacement speaker magnet",
        ],
    },

    # ── InvenSense / TDK ──
    "ICM-20689": {
        "manufacturer": "InvenSense / TDK",
        "type": "accelerometer+gyroscope",
        "description": "6-axis MotionTracking device, high-performance, low noise",
        "common_failures": [
            "Gyro turn-on time exceeds spec in cold environment",
            "DLPF configuration lost after soft reset",
            "FIFO overflow not generating interrupt on SPI bus",
            "Cross-axis alignment error after drop onto corner",
        ],
    },
    "ICM-42607": {
        "manufacturer": "InvenSense / TDK",
        "type": "accelerometer+gyroscope",
        "description": "6-axis MEMS MotionTracking, next-gen low noise, APEX motion features",
        "common_failures": [
            "APEX pedometer algorithm gives inconsistent counts",
            "Wake-on-motion threshold too sensitive after calibration wipe",
            "AUX I2C master not enumerating external magnetometer",
            "Power mode transition delay causing first-sample glitch",
        ],
    },
    "ICM-45686": {
        "manufacturer": "InvenSense / TDK",
        "type": "accelerometer+gyroscope",
        "description": "High-end 6-axis IMU for premium smartphones, ultra-low gyro noise",
        "common_failures": [
            "Gyroscope bias instability increases after reflow rework",
            "High-g event triggers false FIFO reset",
            "OIS interface desync with camera module after FW update",
            "Self-test intermittently fails at boundary temperature",
        ],
    },
    "MPU-6050": {
        "manufacturer": "InvenSense / TDK",
        "type": "accelerometer+gyroscope",
        "description": "Legacy 6-axis MotionProcessing Unit, I2C, widely used in older devices",
        "common_failures": [
            "I2C SDA line stuck low requiring hard power cycle",
            "DMP firmware upload fails on noisy power supply",
            "Gyro drift >2 deg/s after extended storage (>2 years)",
            "AUX I2C pass-through broken for external compass",
        ],
    },
    "MPU-6500": {
        "manufacturer": "InvenSense / TDK",
        "type": "accelerometer+gyroscope",
        "description": "6-axis IMU, SPI/I2C, improved successor to MPU-6050",
        "common_failures": [
            "SPI clock phase mismatch with certain MediaTek SoCs",
            "Self-test values outside factory trim limits after rework",
            "Motion interrupt fires continuously in portrait orientation",
            "Accel full-scale range register resets after warm boot",
        ],
    },

    # ── AKM (Asahi Kasei Microdevices) ──
    "AK09918": {
        "manufacturer": "AKM",
        "type": "magnetometer",
        "description": "3-axis electronic compass, 16-bit, ultra-small package, flagship phones",
        "common_failures": [
            "Compass heading 30-90 deg off after magnetic case attachment",
            "Self-test overflow on Z-axis near wireless charging coil",
            "I2C repeated-start not supported causing bus timeout",
            "Output rate drops to 10Hz when paired with certain IMUs",
        ],
    },
    "AK09915": {
        "manufacturer": "AKM",
        "type": "magnetometer",
        "description": "3-axis electronic compass with built-in magnetic switch function",
        "common_failures": [
            "Magnetic switch false triggers from belt clip magnet",
            "Sensitivity degradation after exposure to >10mT field",
            "NSF noise floor increase after ESD zap on flex connector",
            "Continuous measurement mode stalls after I2C bus reset",
        ],
    },
    "AK8963": {
        "manufacturer": "AKM",
        "type": "magnetometer",
        "description": "3-axis electronic compass, 16-bit, commonly integrated via MPU-9250",
        "common_failures": [
            "Fuse ROM adjustment values read as zero on cold boot",
            "Output clamped at +-4912uT after nearby magnet exposure",
            "I2C bypass mode conflict with MPU host controller",
            "Self-test H-field generation weak after aging (>3 years)",
        ],
    },

    # ── Kionix (ROHM Group) ──
    "KX022": {
        "manufacturer": "Kionix (ROHM)",
        "type": "accelerometer",
        "description": "3-axis accelerometer, ultra-low power, 16-bit, wearable/entry phones",
        "common_failures": [
            "Tap/double-tap engine fails to trigger through thick case",
            "Buffer mode read returns stale data after mode change",
            "I2C address pin floating causing intermittent bus errors",
            "Wake-up from standby takes >50ms exceeding spec",
        ],
    },
    "KX126": {
        "manufacturer": "Kionix (ROHM)",
        "type": "accelerometer",
        "description": "3-axis accelerometer with built-in pedometer, tilt, and tap detection",
        "common_failures": [
            "Pedometer step length calibration reset after power cycle",
            "Tilt angle stuck at 0 when mounted 90 degrees rotated",
            "SPI read returns 0xFF on first access after reset",
            "Interrupt pin leakage current exceeds spec at 85C",
        ],
    },

    # ── MEMSIC ──
    "MMC5603NJ": {
        "manufacturer": "MEMSIC",
        "type": "magnetometer",
        "description": "3-axis AMR magnetic sensor, auto-degauss, high sensitivity, thin package",
        "common_failures": [
            "SET/RESET coil degradation causing heading error growth",
            "Auto-degauss fails near NFC antenna during transaction",
            "Bridge offset exceeds trim range after thermal cycling",
            "I2C stretching too long for some SoC I2C controllers",
        ],
    },
    "MMC3630KJ": {
        "manufacturer": "MEMSIC",
        "type": "magnetometer",
        "description": "3-axis AMR magnetic sensor, budget alternative, older generation",
        "common_failures": [
            "SET pulse circuit damage from ESD on exposed test pads",
            "Output saturates near magnetic phone case flap",
            "Temperature coefficient compensation disabled by default",
            "Continuous mode current consumption 3x higher than spec",
        ],
    },

    # ── Vishay ──
    "VCNL4040": {
        "manufacturer": "Vishay",
        "type": "proximity+light",
        "description": "Fully integrated proximity and ambient light sensor with I2C interface",
        "common_failures": [
            "Proximity false triggers from screen protector air gap",
            "ALS reading drifts after prolonged UV exposure",
            "IR LED degradation causing reduced proximity range over time",
            "I2C NACK when reading ALS and PS registers back-to-back",
        ],
    },
    "VCNL36866": {
        "manufacturer": "Vishay",
        "type": "proximity+light",
        "description": "Long-distance proximity sensor with ALS, designed for bezel-less phones",
        "common_failures": [
            "Proximity detection range reduced behind tinted cover glass",
            "Crosstalk cancellation fails with cracked screen",
            "Sunlight cancellation overwhelmed in direct tropical sun",
            "Low-power mode transitions cause 200ms proximity gap",
        ],
    },

    # ── AMS / OSRAM ──
    "TMD2772": {
        "manufacturer": "AMS / OSRAM",
        "type": "proximity+light",
        "description": "Combined proximity/ALS sensor with IR LED driver, legacy design",
        "common_failures": [
            "Proximity threshold needs recalibration after screen replacement",
            "ALS integration time misconfigured causing lux overflow",
            "IR LED forward voltage drop indicates aging emitter",
            "Wait timer not functioning in low-power idle state",
        ],
    },
    "TCS3407": {
        "manufacturer": "AMS / OSRAM",
        "type": "light",
        "description": "Spectral ambient light sensor, multi-channel (RGBC + flicker)",
        "common_failures": [
            "Flicker detection reporting wrong frequency under PWM LED",
            "Color channel gain mismatch after sensor window contamination",
            "SMUX configuration lost after I2C bus reset",
            "Lux calculation algorithm mismatch with kernel driver version",
        ],
    },
    "TSL2591": {
        "manufacturer": "AMS / OSRAM",
        "type": "light",
        "description": "Very high sensitivity light-to-digital converter, wide dynamic range",
        "common_failures": [
            "Sensor saturates at moderate indoor lighting (gain too high)",
            "Channel 0/1 ratio out of range under fluorescent lighting",
            "Interrupt persistence filter not clearing after acknowledge",
            "ALS data invalid flag ignored by driver causing wrong readings",
        ],
    },

    # ── Lite-On ──
    "LTR-559": {
        "manufacturer": "Lite-On",
        "type": "proximity+light",
        "description": "Integrated ALS and proximity sensor, small optical package",
        "common_failures": [
            "Proximity cross-talk from internal light guide degradation",
            "ALS lux calculation wrong after replacing cover glass color",
            "PS LED current setting lost during system sleep/wake cycle",
            "Dark current increases after high-temperature storage",
        ],
    },
    "LTR-578": {
        "manufacturer": "Lite-On",
        "type": "proximity+light",
        "description": "ALS + proximity with improved SNR, designed for narrow bezels",
        "common_failures": [
            "Near-field crosstalk not compensated for curved display edge",
            "ALS dynamic range insufficient under direct sunlight",
            "Proximity false positive during phone call with wet ear",
            "I2C bus contention with nearby NFC controller",
        ],
    },
    "LTR-553": {
        "manufacturer": "Lite-On",
        "type": "proximity+light",
        "description": "ALS + proximity sensor, budget alternative for entry-level devices",
        "common_failures": [
            "PS offset calibration drift over temperature",
            "ALS reading stuck after overflow condition",
            "Proximity detection distance < 2cm with thick protector",
            "Part-to-part variation causing inconsistent call behavior",
        ],
    },

    # ── Sensortek ──
    "STK3311": {
        "manufacturer": "Sensortek",
        "type": "proximity",
        "description": "Proximity sensor with ambient light rejection, I2C, cost-effective",
        "common_failures": [
            "Proximity stuck in 'near' state after screen repair (ink contamination)",
            "Ambient light rejection fails under IR-rich light sources",
            "Software calibration values incompatible after board rework",
            "State machine hang requiring register reset sequence",
        ],
    },
    "STK3338": {
        "manufacturer": "Sensortek",
        "type": "proximity",
        "description": "Enhanced proximity sensor with dynamic ALS, improved crosstalk",
        "common_failures": [
            "Dynamic threshold adaptation too slow for rapid hand gestures",
            "PS data register returns 0xFFFF intermittently (bus glitch)",
            "Crosstalk compensation offset exceeds factory trim range",
            "Sleep mode current leakage exceeds 5uA (spec is 1uA)",
        ],
    },
}

# Mapping from sensor type keyword to the primary types we track
_SENSOR_TYPE_ALIASES: Dict[str, str] = {
    "accelerometer": "accelerometer",
    "accel": "accelerometer",
    "acceleration": "accelerometer",
    "gyroscope": "gyroscope",
    "gyro": "gyroscope",
    "angular_velocity": "gyroscope",
    "rotation": "gyroscope",
    "magnetometer": "magnetometer",
    "magnetic": "magnetometer",
    "magnetic_field": "magnetometer",
    "compass": "magnetometer",
    "geomagnetic": "magnetometer",
    "proximity": "proximity",
    "prox": "proximity",
    "light": "light",
    "als": "light",
    "ambient_light": "light",
    "illuminance": "light",
    "barometer": "barometer",
    "pressure": "barometer",
    "baro": "barometer",
    "gravity": "gravity",
    "step_counter": "step_counter",
    "step_cnt": "step_counter",
    "pedometer": "step_counter",
    "step counter": "step_counter",
}


# ---------------------------------------------------------------------------
#  Data classes -- test results
# ---------------------------------------------------------------------------

@dataclass
class SensorInfo:
    """Describes a single detected sensor and its current status."""
    name: str = ""
    vendor: str = ""
    sensor_type: str = ""           # accelerometer, gyroscope, etc.
    ic_name: str = ""
    ic_manufacturer: str = ""
    resolution: str = ""
    max_range: str = ""
    power_consumption: str = ""
    is_active: bool = False
    status: str = "Unknown"         # OK, Warning, Fault
    common_failures: List[str] = field(default_factory=list)
    handle: str = ""
    version: int = 0
    min_delay_us: int = 0
    max_delay_us: int = 0
    fifo_reserved: int = 0
    fifo_max: int = 0
    is_wake_up: bool = False
    raw_data: Dict[str, str] = field(default_factory=dict)


@dataclass
class SensorTestResult:
    """Top-level container returned by ``detect_sensor_status``."""
    connected: bool = False
    error: Optional[str] = None
    sensors_found: int = 0
    sensors: List[SensorInfo] = field(default_factory=list)
    accelerometer: Optional[SensorInfo] = None
    gyroscope: Optional[SensorInfo] = None
    magnetometer: Optional[SensorInfo] = None
    proximity: Optional[SensorInfo] = None
    light_sensor: Optional[SensorInfo] = None
    barometer: Optional[SensorInfo] = None
    gravity: Optional[SensorInfo] = None
    step_counter: Optional[SensorInfo] = None
    overall_health: str = "Unknown"
    health_score: int = 0
    warnings: List[str] = field(default_factory=list)


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


def _adb(cmd: str, timeout: int = 10) -> str:
    """Run ``adb shell <cmd>`` and return stdout (empty string on failure)."""
    try:
        proc = subprocess.run(
            f"adb shell {cmd}",
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
        return proc.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _adb_shell(command: str, timeout: int = 10) -> Tuple[bool, str]:
    """Shorthand for ``adb shell <command>``, returns (ok, output)."""
    return _run_adb(["shell", command], timeout=timeout)


def _read_sysfs_node(path: str) -> Tuple[bool, str]:
    """Read a single sysfs file via ``adb shell cat``."""
    return _adb_shell(f"cat {path}")


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
#  Step 1 -- ADB connection check
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
    _notify(callback, 5.0, f"ADB connected -- serial {serial}")
    return True, ""


# ---------------------------------------------------------------------------
#  Step 2 -- Enumerate sensors via sensorservice
# ---------------------------------------------------------------------------

def _parse_sensorservice_dump(dump: str) -> List[SensorInfo]:
    """Parse the output of ``dumpsys sensorservice`` into SensorInfo objects.

    The sensorservice dump has several sections.  The most reliable is the
    sensor list that appears early in the output with lines like:

        0x00000001) {Sensor name="BMI160 Accelerometer" vendor="Bosch" version=1
                     type=1 ...}

    We also look for the alternative format used on newer Android versions:

        Sensor name="...", vendor="...", version=..., type=..., ...

    Returns a list of SensorInfo objects.
    """
    sensors: List[SensorInfo] = []

    if not dump:
        return sensors

    # ----- Pattern 1: handle-prefixed sensor entries -----
    # Matches: 0x00000001) {Sensor name="..." ...}  or  1) {...}
    block_pattern = re.compile(
        r"(?:0x[0-9a-fA-F]+|\d+)\)\s*\{(.+?)\}",
        re.DOTALL,
    )

    # ----- Pattern 2: flat key=value lines -----
    # Matches individual key="value" or key=value tokens
    kv_pattern = re.compile(
        r'(\w+)\s*=\s*(?:"([^"]*?)"|(\S+))'
    )

    for block_match in block_pattern.finditer(dump):
        block_text = block_match.group(1)
        props: Dict[str, str] = {}
        for kv_match in kv_pattern.finditer(block_text):
            key = kv_match.group(1).lower()
            value = kv_match.group(2) if kv_match.group(2) is not None else kv_match.group(3)
            props[key] = value

        if not props:
            continue

        sensor = SensorInfo()
        sensor.name = props.get("name", "").strip()
        sensor.vendor = props.get("vendor", "").strip()
        sensor.handle = props.get("handle", "").strip()
        sensor.resolution = props.get("resolution", "").strip()
        sensor.max_range = props.get("maxrange", props.get("max_range", "")).strip()
        sensor.power_consumption = props.get("power", props.get("minconsumption", "")).strip()
        sensor.version = _parse_int(props.get("version", "0"))
        sensor.min_delay_us = _parse_int(props.get("mindelay", "0"))
        sensor.max_delay_us = _parse_int(props.get("maxdelay", "0"))
        sensor.fifo_reserved = _parse_int(props.get("fiforescount", "0"))
        sensor.fifo_max = _parse_int(props.get("fifomaxcount", "0"))

        # Determine sensor type from Android type ID
        type_id = _parse_int(props.get("type", "0"))
        if type_id in SENSOR_TYPE_IDS:
            sensor.sensor_type = SENSOR_TYPE_IDS[type_id]
        else:
            # Fall back to name-based heuristic
            sensor.sensor_type = _classify_sensor_type_from_name(sensor.name)

        # Wake-up sensor
        wake_str = props.get("wakeup", props.get("flags", "")).lower()
        sensor.is_wake_up = "wake" in wake_str or "wakeup" in wake_str

        sensor.raw_data = props
        sensors.append(sensor)

    # ----- Pattern 3: simpler line-based format (some OEMs) -----
    # Looks for lines like:  "Accelerometer | vendor: Bosch | ..."
    if not sensors:
        line_pattern = re.compile(
            r"^\s*(?:Sensor\s+)?(.+?)\s*\|\s*vendor:\s*(.+?)\s*\|",
            re.MULTILINE | re.IGNORECASE,
        )
        for lm in line_pattern.finditer(dump):
            sensor = SensorInfo()
            sensor.name = lm.group(1).strip()
            sensor.vendor = lm.group(2).strip()
            sensor.sensor_type = _classify_sensor_type_from_name(sensor.name)
            sensors.append(sensor)

    # ----- Pattern 4: scan for "active sensor" lines -----
    # Example: "name=BMI160 Accelerometer, active=true"
    active_pattern = re.compile(
        r"name\s*=\s*(.+?),.*?active\s*=\s*(true|false|1|0)",
        re.IGNORECASE,
    )
    active_names: set = set()
    for am in active_pattern.finditer(dump):
        if am.group(2).lower() in ("true", "1"):
            active_names.add(am.group(1).strip().lower())

    # Mark active sensors
    for s in sensors:
        if s.name.lower() in active_names:
            s.is_active = True

    # Also scan for "active sensors" section
    if "active sensors" in dump.lower():
        active_section = dump[dump.lower().index("active sensors"):]
        active_section = active_section[:active_section.find("\n\n") + 1] if "\n\n" in active_section else active_section[:500]
        for s in sensors:
            if s.name and s.name.lower() in active_section.lower():
                s.is_active = True

    return sensors


def _classify_sensor_type_from_name(name: str) -> str:
    """Heuristically classify sensor type from its display name."""
    name_lower = name.lower()
    for keyword, stype in _SENSOR_TYPE_ALIASES.items():
        if keyword in name_lower:
            return stype
    # Additional heuristics
    if "imu" in name_lower or "6-axis" in name_lower or "6axis" in name_lower:
        return "accelerometer"
    if "rotation" in name_lower and "game" in name_lower:
        return "game_rotation_vector"
    if "rotation" in name_lower:
        return "rotation_vector"
    if "significant" in name_lower and "motion" in name_lower:
        return "significant_motion"
    if "humidity" in name_lower:
        return "humidity"
    if "temperature" in name_lower or "therm" in name_lower:
        return "ambient_temperature"
    return "unknown"


# ---------------------------------------------------------------------------
#  Step 3 -- Read additional sensor details from sysfs
# ---------------------------------------------------------------------------

def _read_sysfs_sensor_details(
    callback: ProgressCallback,
    sensors: List[SensorInfo],
) -> List[SensorInfo]:
    """Enrich sensor info with data from sysfs nodes and input devices."""
    _notify(callback, 30.0, "Reading sensor details from sysfs nodes...")

    # Read all sensor names under /sys/class/sensors/*/name
    raw_names_output = _adb("cat /sys/class/sensors/*/name 2>/dev/null")
    sysfs_names: List[str] = [
        n.strip() for n in raw_names_output.splitlines() if n.strip()
    ]

    # Read all vendor strings
    raw_vendor_output = _adb("cat /sys/class/sensors/*/vendor 2>/dev/null")
    sysfs_vendors: List[str] = [
        v.strip() for v in raw_vendor_output.splitlines() if v.strip()
    ]

    # Read enable status
    raw_enable_output = _adb("cat /sys/class/sensors/*/enable 2>/dev/null")
    sysfs_enables: List[str] = [
        e.strip() for e in raw_enable_output.splitlines() if e.strip()
    ]

    # Build lookup from sysfs names
    sysfs_info: Dict[str, Dict[str, str]] = {}
    for i, name in enumerate(sysfs_names):
        entry: Dict[str, str] = {"name": name}
        if i < len(sysfs_vendors):
            entry["vendor"] = sysfs_vendors[i]
        if i < len(sysfs_enables):
            entry["enabled"] = sysfs_enables[i]
        sysfs_info[name.lower()] = entry

    # Enrich existing sensors with sysfs data
    for sensor in sensors:
        key = sensor.name.lower()
        if key in sysfs_info:
            info = sysfs_info[key]
            if not sensor.vendor and "vendor" in info:
                sensor.vendor = info["vendor"]
            if "enabled" in info and info["enabled"] in ("1", "true"):
                sensor.is_active = True

    # Try per-type sysfs paths for additional attributes
    for sensor in sensors:
        stype = sensor.sensor_type
        if stype in SENSOR_TYPE_SYSFS:
            for path in SENSOR_TYPE_SYSFS[stype]:
                ok, _ = _adb_shell(f"test -d {path} && echo EXISTS")
                if ok and "EXISTS" in _:
                    # Read additional attributes
                    for attr in ("name", "vendor", "enable", "poll_delay",
                                 "max_range", "resolution", "sensor_power"):
                        ok_val, val = _read_sysfs_node(f"{path}/{attr}")
                        if ok_val and val.strip():
                            sensor.raw_data[f"sysfs_{attr}"] = val.strip()
                            if attr == "name" and not sensor.name:
                                sensor.name = val.strip()
                            elif attr == "vendor" and not sensor.vendor:
                                sensor.vendor = val.strip()
                            elif attr == "max_range" and not sensor.max_range:
                                sensor.max_range = val.strip()
                            elif attr == "resolution" and not sensor.resolution:
                                sensor.resolution = val.strip()
                            elif attr == "sensor_power" and not sensor.power_consumption:
                                sensor.power_consumption = val.strip()
                            elif attr == "enable" and val.strip() in ("1", "true"):
                                sensor.is_active = True
                    break  # use first matching path

    # Parse /proc/bus/input/devices for input-layer sensors
    _notify(callback, 40.0, "Reading input device enumeration...")
    input_devices_raw = _adb("cat /proc/bus/input/devices 2>/dev/null")
    if input_devices_raw:
        _enrich_from_input_devices(sensors, input_devices_raw)

    # Read hardware sensors property
    hw_sensors_prop = _adb("getprop ro.hardware.sensors")
    if hw_sensors_prop:
        logger.info("ro.hardware.sensors = %s", hw_sensors_prop)
        for sensor in sensors:
            sensor.raw_data["ro.hardware.sensors"] = hw_sensors_prop

    return sensors


def _enrich_from_input_devices(
    sensors: List[SensorInfo],
    input_dump: str,
) -> None:
    """Parse /proc/bus/input/devices to find sensor-related input devices
    and cross-reference with our sensor list."""
    # Each device block is separated by blank lines
    blocks = input_dump.split("\n\n")
    sensor_input_blocks: List[Dict[str, str]] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue
        info: Dict[str, str] = {}
        for line in lines:
            line = line.strip()
            if line.startswith("I:"):
                info["id"] = line[2:].strip()
            elif line.startswith("N:"):
                # N: Name="..."
                name_match = re.search(r'Name="(.+?)"', line)
                if name_match:
                    info["name"] = name_match.group(1)
            elif line.startswith("P:"):
                info["phys"] = line[2:].strip().replace("Phys=", "")
            elif line.startswith("S:"):
                info["sysfs"] = line[2:].strip().replace("Sysfs=", "")
            elif line.startswith("H:"):
                info["handlers"] = line[2:].strip().replace("Handlers=", "")

        name = info.get("name", "").lower()
        # Check if this input device is sensor-related
        sensor_keywords = [
            "accel", "gyro", "magnet", "compass", "proximity",
            "light", "als", "baro", "pressure", "sensor",
            "imu", "motion", "step",
        ]
        if any(kw in name for kw in sensor_keywords):
            sensor_input_blocks.append(info)

    # Cross-reference with detected sensors
    for input_info in sensor_input_blocks:
        input_name = input_info.get("name", "").lower()
        for sensor in sensors:
            sensor_name_lower = sensor.name.lower()
            # Check for partial match
            if (sensor_name_lower and sensor_name_lower in input_name) or \
               (input_name and input_name in sensor_name_lower):
                if "sysfs" in input_info:
                    sensor.raw_data["input_sysfs_path"] = input_info["sysfs"]
                if "handlers" in input_info:
                    sensor.raw_data["input_handlers"] = input_info["handlers"]
                break


# ---------------------------------------------------------------------------
#  Step 4 -- Identify sensor ICs
# ---------------------------------------------------------------------------

def _identify_sensor_ics(
    callback: ProgressCallback,
    sensors: List[SensorInfo],
) -> List[SensorInfo]:
    """Match detected sensors against the KNOWN_SENSOR_ICS database."""
    _notify(callback, 50.0, "Identifying sensor ICs against knowledge database...")

    for sensor in sensors:
        # Build a search string from the sensor's name and vendor
        search_text = f"{sensor.name} {sensor.vendor}".lower()

        best_match: Optional[str] = None
        best_score: int = 0

        for ic_name, ic_info in KNOWN_SENSOR_ICS.items():
            score = 0
            ic_lower = ic_name.lower().replace("-", "").replace("_", "")
            search_normalised = search_text.replace("-", "").replace("_", "")

            # Exact IC name match in sensor name
            if ic_lower in search_normalised:
                score += 100
            # Partial match -- check manufacturer + type
            elif ic_info["manufacturer"].lower() in search_normalised:
                score += 30
                # Check if type matches
                ic_types = ic_info["type"].split("+")
                for ic_type in ic_types:
                    if ic_type in sensor.sensor_type:
                        score += 40
                        break

            # Vendor name match
            if ic_info["manufacturer"].lower() in sensor.vendor.lower():
                score += 20

            # Type compatibility check
            ic_types = ic_info["type"].split("+")
            sensor_type_normalised = sensor.sensor_type.lower()
            for ic_type in ic_types:
                if ic_type in sensor_type_normalised:
                    score += 10
                    break
            # proximity+light ICs should also match "light" or "proximity" types
            if "proximity" in ic_info["type"] and "proximity" in sensor_type_normalised:
                score += 10
            if "light" in ic_info["type"] and "light" in sensor_type_normalised:
                score += 10

            if score > best_score:
                best_score = score
                best_match = ic_name

        # Only accept matches with a reasonable confidence
        if best_match and best_score >= 50:
            ic_data = KNOWN_SENSOR_ICS[best_match]
            sensor.ic_name = best_match
            sensor.ic_manufacturer = ic_data["manufacturer"]
            sensor.common_failures = list(ic_data.get("common_failures", []))
            logger.debug(
                "Matched sensor '%s' -> IC %s (%s) score=%d",
                sensor.name, best_match, ic_data["manufacturer"], best_score,
            )
        elif best_match and best_score >= 30:
            # Tentative match, mark as possible
            ic_data = KNOWN_SENSOR_ICS[best_match]
            sensor.ic_name = f"{best_match} (probable)"
            sensor.ic_manufacturer = ic_data["manufacturer"]
            sensor.common_failures = list(ic_data.get("common_failures", []))
            logger.debug(
                "Tentative match sensor '%s' -> IC %s score=%d",
                sensor.name, best_match, best_score,
            )

    # Second pass: try to identify ICs from the full sensorservice dump
    # by checking for IC name patterns not yet matched
    _try_secondary_ic_identification(sensors)

    _notify(callback, 60.0, f"IC identification complete -- "
                            f"{sum(1 for s in sensors if s.ic_name)} ICs matched")
    return sensors


def _try_secondary_ic_identification(sensors: List[SensorInfo]) -> None:
    """Second-pass identification using hardware property and driver names."""
    # Try getprop for sensor HAL hints
    sensor_hal = _adb("getprop ro.hardware.sensors")
    sensor_lib = _adb("getprop persist.vendor.sensors.hal_trigger_ssr")
    all_props = _adb("getprop | grep -i sensor 2>/dev/null")

    combined_props = f"{sensor_hal} {sensor_lib} {all_props}".lower()

    for sensor in sensors:
        if sensor.ic_name:
            continue  # already identified

        # Check IC names against combined property output
        for ic_name in KNOWN_SENSOR_ICS:
            ic_lower = ic_name.lower().replace("-", "")
            if ic_lower in combined_props.replace("-", ""):
                ic_data = KNOWN_SENSOR_ICS[ic_name]
                # Verify type compatibility
                ic_types = ic_data["type"].split("+")
                type_match = any(
                    t in sensor.sensor_type for t in ic_types
                ) or sensor.sensor_type == "unknown"
                if type_match:
                    sensor.ic_name = f"{ic_name} (from props)"
                    sensor.ic_manufacturer = ic_data["manufacturer"]
                    sensor.common_failures = list(ic_data.get("common_failures", []))
                    break


# ---------------------------------------------------------------------------
#  Step 5 -- Test sensor status / responsiveness
# ---------------------------------------------------------------------------

def _test_sensor_status(
    callback: ProgressCallback,
    sensors: List[SensorInfo],
    sensorservice_dump: str,
) -> List[SensorInfo]:
    """Check whether each sensor is responding and assess its status."""
    _notify(callback, 70.0, "Testing sensor responsiveness...")

    # Parse recent events from sensorservice dump to find sensors that have
    # produced data recently
    recent_events = _parse_recent_events(sensorservice_dump)

    # Try dumpsys activity service SensorService for additional status
    service_dump = _adb("dumpsys activity service SensorService 2>/dev/null")

    for sensor in sensors:
        # Check if sensor has produced recent events
        sensor_name_lower = sensor.name.lower()
        has_recent_data = False

        for event_name, event_data in recent_events.items():
            if sensor_name_lower in event_name.lower() or \
               event_name.lower() in sensor_name_lower:
                has_recent_data = True
                sensor.raw_data["last_event"] = event_data
                break

        # Check registration status in service dump
        is_registered = False
        if service_dump and sensor.name:
            if sensor.name.lower() in service_dump.lower():
                is_registered = True

        # Determine status
        if has_recent_data and sensor.is_active:
            sensor.status = "OK"
        elif has_recent_data:
            sensor.status = "OK"
            sensor.is_active = True
        elif sensor.is_active:
            sensor.status = "OK"
        elif is_registered:
            sensor.status = "OK"
        else:
            # Sensor listed but no recent data -- could be idle or faulty
            sensor.status = "Warning"

    # Validate sensor readings where possible
    _validate_sensor_readings(sensors, sensorservice_dump)

    _notify(callback, 80.0, f"Status check complete -- "
                            f"{sum(1 for s in sensors if s.status == 'OK')} OK, "
                            f"{sum(1 for s in sensors if s.status == 'Warning')} warnings, "
                            f"{sum(1 for s in sensors if s.status == 'Fault')} faults")
    return sensors


def _parse_recent_events(dump: str) -> Dict[str, str]:
    """Extract recent event data from sensorservice dump.

    Looks for sections like:
        Recent events logged for sensor "Accelerometer":
          timestamp=12345 data=[1.23, -0.45, 9.81]
    """
    events: Dict[str, str] = {}
    if not dump:
        return events

    # Pattern: recent events for a named sensor
    event_section_pattern = re.compile(
        r"[Rr]ecent\s+(?:events?\s+)?(?:logged\s+)?for\s+"
        r"(?:sensor\s+)?[\"']?(.+?)[\"']?\s*:\s*\n((?:.*?\n)*?)(?:\n\n|\Z)",
        re.MULTILINE,
    )

    for match in event_section_pattern.finditer(dump):
        sensor_name = match.group(1).strip()
        event_lines = match.group(2).strip()
        if event_lines:
            events[sensor_name] = event_lines[:500]  # cap for memory

    # Also look for simpler "last event" lines
    last_event_pattern = re.compile(
        r"(?:last\s+)?event\s*[:=]\s*(?:timestamp\s*=\s*\d+\s+)?"
        r"data\s*=\s*\[([^\]]+)\].*?(?:sensor\s*=\s*)?[\"']?(\w[^\"'\n]*)",
        re.IGNORECASE,
    )
    for match in last_event_pattern.finditer(dump):
        data = match.group(1).strip()
        name = match.group(2).strip()
        if name and data:
            events.setdefault(name, f"data=[{data}]")

    return events


def _validate_sensor_readings(
    sensors: List[SensorInfo],
    dump: str,
) -> None:
    """Validate sensor readings for anomalies that indicate hardware faults."""
    if not dump:
        return

    dump_lower = dump.lower()

    for sensor in sensors:
        stype = sensor.sensor_type

        # Check for error keywords near the sensor name
        name_lower = sensor.name.lower()
        if name_lower:
            # Find context around the sensor name in the dump
            idx = dump_lower.find(name_lower)
            if idx >= 0:
                context = dump_lower[max(0, idx - 100):idx + 300]
                error_keywords = [
                    "error", "fail", "fault", "timeout", "not found",
                    "disabled", "broken", "stuck", "nan", "inf",
                ]
                for keyword in error_keywords:
                    if keyword in context:
                        sensor.status = "Fault"
                        sensor.raw_data["fault_indicator"] = keyword
                        break

        # Type-specific validation
        if stype == "accelerometer":
            _validate_accelerometer(sensor, dump)
        elif stype == "gyroscope":
            _validate_gyroscope(sensor, dump)
        elif stype == "magnetometer":
            _validate_magnetometer(sensor, dump)
        elif stype == "proximity":
            _validate_proximity(sensor, dump)
        elif stype == "light":
            _validate_light_sensor(sensor, dump)
        elif stype == "barometer":
            _validate_barometer(sensor, dump)


def _validate_accelerometer(sensor: SensorInfo, dump: str) -> None:
    """Check accelerometer readings for physical plausibility."""
    # Look for data values near this sensor in the dump
    data_pattern = re.compile(
        r"data\s*=\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]",
    )
    # Search near the sensor name
    idx = dump.lower().find(sensor.name.lower())
    if idx < 0:
        return
    context = dump[idx:idx + 1000]
    match = data_pattern.search(context)
    if not match:
        return

    try:
        x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
        magnitude = (x ** 2 + y ** 2 + z ** 2) ** 0.5
        # Gravity should give ~9.81 m/s^2 when stationary
        if magnitude < 1.0 or magnitude > 50.0:
            sensor.status = "Fault"
            sensor.raw_data["validation"] = (
                f"Accel magnitude {magnitude:.2f} m/s^2 out of expected range"
            )
        elif abs(magnitude - 9.81) > 3.0:
            if sensor.status != "Fault":
                sensor.status = "Warning"
            sensor.raw_data["validation"] = (
                f"Accel magnitude {magnitude:.2f} m/s^2, expected ~9.81 at rest"
            )
    except (ValueError, ZeroDivisionError):
        pass


def _validate_gyroscope(sensor: SensorInfo, dump: str) -> None:
    """Check gyroscope readings for zero-rate offset anomalies."""
    data_pattern = re.compile(
        r"data\s*=\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]",
    )
    idx = dump.lower().find(sensor.name.lower())
    if idx < 0:
        return
    context = dump[idx:idx + 1000]
    match = data_pattern.search(context)
    if not match:
        return

    try:
        x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
        # At rest, gyro should read near zero (< 0.5 rad/s typically)
        max_val = max(abs(x), abs(y), abs(z))
        if max_val > 10.0:
            sensor.status = "Fault"
            sensor.raw_data["validation"] = (
                f"Gyro reading {max_val:.2f} rad/s at rest -- excessive drift"
            )
        elif max_val > 1.0:
            if sensor.status != "Fault":
                sensor.status = "Warning"
            sensor.raw_data["validation"] = (
                f"Gyro zero-rate offset {max_val:.2f} rad/s slightly high"
            )
    except (ValueError, ZeroDivisionError):
        pass


def _validate_magnetometer(sensor: SensorInfo, dump: str) -> None:
    """Check magnetometer readings for plausibility."""
    data_pattern = re.compile(
        r"data\s*=\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]",
    )
    idx = dump.lower().find(sensor.name.lower())
    if idx < 0:
        return
    context = dump[idx:idx + 1000]
    match = data_pattern.search(context)
    if not match:
        return

    try:
        x, y, z = float(match.group(1)), float(match.group(2)), float(match.group(3))
        magnitude = (x ** 2 + y ** 2 + z ** 2) ** 0.5
        # Earth magnetic field is ~25-65 uT.  Sensor reports in uT.
        if magnitude < 1.0 and magnitude != 0.0:
            if sensor.status != "Fault":
                sensor.status = "Warning"
            sensor.raw_data["validation"] = (
                f"Magnetic field magnitude {magnitude:.2f} uT very low"
            )
        elif magnitude > 200.0:
            sensor.status = "Fault"
            sensor.raw_data["validation"] = (
                f"Magnetic field magnitude {magnitude:.2f} uT -- interference or stuck"
            )
        elif magnitude > 100.0:
            if sensor.status != "Fault":
                sensor.status = "Warning"
            sensor.raw_data["validation"] = (
                f"Magnetic field {magnitude:.2f} uT -- possible nearby magnet"
            )
    except (ValueError, ZeroDivisionError):
        pass


def _validate_proximity(sensor: SensorInfo, dump: str) -> None:
    """Check proximity sensor for stuck readings."""
    data_pattern = re.compile(
        r"data\s*=\s*\[\s*([-\d.]+)",
    )
    idx = dump.lower().find(sensor.name.lower())
    if idx < 0:
        return
    context = dump[idx:idx + 1000]

    # Check for multiple identical readings (stuck sensor)
    readings: List[float] = []
    for m in data_pattern.finditer(context):
        try:
            readings.append(float(m.group(1)))
        except ValueError:
            pass

    if len(readings) >= 3:
        # If all readings are identical, sensor may be stuck
        if len(set(readings)) == 1:
            val = readings[0]
            if sensor.status != "Fault":
                sensor.status = "Warning"
            sensor.raw_data["validation"] = (
                f"Proximity all readings identical ({val}) -- may be stuck"
            )


def _validate_light_sensor(sensor: SensorInfo, dump: str) -> None:
    """Check light sensor for plausibility."""
    data_pattern = re.compile(
        r"data\s*=\s*\[\s*([-\d.]+)",
    )
    idx = dump.lower().find(sensor.name.lower())
    if idx < 0:
        return
    context = dump[idx:idx + 1000]
    match = data_pattern.search(context)
    if not match:
        return

    try:
        lux = float(match.group(1))
        if lux < 0:
            sensor.status = "Fault"
            sensor.raw_data["validation"] = f"Light sensor reading negative ({lux} lux)"
        elif lux > 200000:
            if sensor.status != "Fault":
                sensor.status = "Warning"
            sensor.raw_data["validation"] = (
                f"Light sensor reading extremely high ({lux} lux) -- may be saturated"
            )
    except ValueError:
        pass


def _validate_barometer(sensor: SensorInfo, dump: str) -> None:
    """Check barometer readings for plausibility."""
    data_pattern = re.compile(
        r"data\s*=\s*\[\s*([-\d.]+)",
    )
    idx = dump.lower().find(sensor.name.lower())
    if idx < 0:
        return
    context = dump[idx:idx + 1000]
    match = data_pattern.search(context)
    if not match:
        return

    try:
        pressure_hpa = float(match.group(1))
        # Sea level ~1013.25 hPa, reasonable range: 300 (high altitude) - 1100
        if pressure_hpa < 200 or pressure_hpa > 1200:
            sensor.status = "Fault"
            sensor.raw_data["validation"] = (
                f"Barometer reading {pressure_hpa} hPa out of physical range"
            )
        elif pressure_hpa < 500 or pressure_hpa > 1085:
            if sensor.status != "Fault":
                sensor.status = "Warning"
            sensor.raw_data["validation"] = (
                f"Barometer reading {pressure_hpa} hPa unusual -- check vent hole"
            )
    except ValueError:
        pass


# ---------------------------------------------------------------------------
#  Step 6 -- Health analysis and scoring
# ---------------------------------------------------------------------------

# Expected sensors on a typical modern smartphone
EXPECTED_SENSORS: Dict[str, Dict[str, Any]] = {
    "accelerometer": {
        "critical": True,
        "weight": 20,
        "description": "Required for screen rotation, motion sensing, gaming",
        "missing_impact": "Screen auto-rotation will not work; motion-based features disabled",
    },
    "gyroscope": {
        "critical": True,
        "weight": 18,
        "description": "Required for AR, VR, advanced gaming, image stabilization",
        "missing_impact": "AR apps, VR mode, and gyro-based games will not function",
    },
    "magnetometer": {
        "critical": False,
        "weight": 12,
        "description": "Required for compass, map orientation, metal detection apps",
        "missing_impact": "Compass and map heading will not work; navigation degraded",
    },
    "proximity": {
        "critical": True,
        "weight": 18,
        "description": "Required for screen-off during calls, pocket detection",
        "missing_impact": "Screen stays on during calls causing accidental touches",
    },
    "light": {
        "critical": False,
        "weight": 14,
        "description": "Required for auto-brightness, adaptive display",
        "missing_impact": "Auto-brightness will not work; manual brightness only",
    },
    "barometer": {
        "critical": False,
        "weight": 6,
        "description": "Used for altitude, weather apps, indoor floor detection",
        "missing_impact": "Floor detection and altitude features unavailable",
    },
    "gravity": {
        "critical": False,
        "weight": 6,
        "description": "Virtual sensor derived from accelerometer, used by apps",
        "missing_impact": "Some physics-based apps may behave incorrectly",
    },
    "step_counter": {
        "critical": False,
        "weight": 6,
        "description": "Used for fitness tracking, health apps, Google Fit",
        "missing_impact": "Pedometer and fitness tracking will not function",
    },
}


def _analyze_health(
    callback: ProgressCallback,
    sensors: List[SensorInfo],
) -> Tuple[int, str, List[str]]:
    """Compute overall health score (0-100) and generate warnings.

    Returns (score, health_label, warnings).
    """
    _notify(callback, 85.0, "Analyzing sensor health and computing score...")

    warnings: List[str] = []
    total_weight = sum(info["weight"] for info in EXPECTED_SENSORS.values())
    earned_points = 0.0

    # Build a map of detected sensor types
    detected_types: Dict[str, List[SensorInfo]] = {}
    for sensor in sensors:
        stype = sensor.sensor_type
        if stype not in detected_types:
            detected_types[stype] = []
        detected_types[stype].append(sensor)

    # Score each expected sensor
    for stype, config in EXPECTED_SENSORS.items():
        weight = config["weight"]

        if stype not in detected_types:
            # Sensor not found
            if config["critical"]:
                warnings.append(
                    f"CRITICAL: {SENSOR_TYPE_LABELS.get(stype, stype)} NOT DETECTED. "
                    f"{config['missing_impact']}"
                )
            else:
                warnings.append(
                    f"Missing: {SENSOR_TYPE_LABELS.get(stype, stype)} not found. "
                    f"{config['missing_impact']}"
                )
            # No points earned for missing sensor
            continue

        # Sensor found -- evaluate its condition
        best_sensor = detected_types[stype][0]
        # Prefer the one with the best status
        for s in detected_types[stype]:
            if s.status == "OK":
                best_sensor = s
                break
            elif s.status == "Warning" and best_sensor.status != "OK":
                best_sensor = s

        if best_sensor.status == "OK":
            earned_points += weight
        elif best_sensor.status == "Warning":
            earned_points += weight * 0.6
            warnings.append(
                f"Warning: {SENSOR_TYPE_LABELS.get(stype, stype)} ({best_sensor.name}) "
                f"may have issues -- {best_sensor.raw_data.get('validation', 'no recent data')}"
            )
        elif best_sensor.status == "Fault":
            earned_points += weight * 0.1
            warnings.append(
                f"FAULT: {SENSOR_TYPE_LABELS.get(stype, stype)} ({best_sensor.name}) "
                f"appears faulty -- {best_sensor.raw_data.get('validation', best_sensor.raw_data.get('fault_indicator', 'unknown issue'))}"
            )
        else:
            # Unknown status -- give partial credit
            earned_points += weight * 0.4
            warnings.append(
                f"Unknown: {SENSOR_TYPE_LABELS.get(stype, stype)} ({best_sensor.name}) "
                f"status could not be determined"
            )

    # Bonus for extra sensors beyond expected
    extra_types = set(detected_types.keys()) - set(EXPECTED_SENSORS.keys())
    if extra_types:
        bonus = min(5.0, len(extra_types) * 1.0)
        earned_points += bonus

    # Compute final score
    score = int(round((earned_points / total_weight) * 100))
    score = max(0, min(100, score))

    # Add informational warnings
    if len(sensors) == 0:
        warnings.insert(0, "No sensors detected at all -- ADB may lack permissions or "
                           "device does not expose sensor data")

    # Count fault and warning sensors
    fault_count = sum(1 for s in sensors if s.status == "Fault")
    warning_count = sum(1 for s in sensors if s.status == "Warning")
    if fault_count > 0:
        warnings.append(f"Total sensors with faults: {fault_count}")
    if warning_count > 0:
        warnings.append(f"Total sensors with warnings: {warning_count}")

    # Health label
    if score >= 90:
        health_label = "EXCELLENT"
    elif score >= 75:
        health_label = "GOOD"
    elif score >= 55:
        health_label = "FAIR"
    elif score >= 35:
        health_label = "POOR"
    else:
        health_label = "CRITICAL"

    _notify(callback, 95.0, f"Health analysis complete -- {health_label} ({score}/100)")
    return score, health_label, warnings


# ---------------------------------------------------------------------------
#  Overall assessment generation
# ---------------------------------------------------------------------------

def _generate_overall_assessment(
    result: "SensorTestResult",
) -> str:
    """Generate a human-readable overall sensor health assessment string.

    Returns a multi-line string suitable for display to a repair technician.
    """
    lines: List[str] = []

    # --- Header ---
    lines.append(f"Sensor Health: {result.overall_health} ({result.health_score}/100)")
    lines.append("")

    # --- Summary ---
    lines.append(f"Total Sensors Found: {result.sensors_found}")
    ok_count = sum(1 for s in result.sensors if s.status == "OK")
    warn_count = sum(1 for s in result.sensors if s.status == "Warning")
    fault_count = sum(1 for s in result.sensors if s.status == "Fault")
    lines.append(f"  OK      : {ok_count}")
    lines.append(f"  Warning : {warn_count}")
    lines.append(f"  Fault   : {fault_count}")
    lines.append(f"  Unknown : {result.sensors_found - ok_count - warn_count - fault_count}")
    lines.append("")

    # --- Primary sensors ---
    primary_sensors = [
        ("Accelerometer", result.accelerometer),
        ("Gyroscope", result.gyroscope),
        ("Magnetometer", result.magnetometer),
        ("Proximity", result.proximity),
        ("Light Sensor", result.light_sensor),
        ("Barometer", result.barometer),
        ("Gravity", result.gravity),
        ("Step Counter", result.step_counter),
    ]

    lines.append("Primary Sensors:")
    for label, sensor in primary_sensors:
        if sensor:
            ic_str = f" [{sensor.ic_name}]" if sensor.ic_name else ""
            lines.append(f"  {label:18s}: {sensor.status:8s} -- {sensor.name}{ic_str}")
            if sensor.vendor:
                lines.append(f"  {'':18s}  Vendor: {sensor.vendor}")
            if sensor.ic_manufacturer:
                lines.append(f"  {'':18s}  IC Mfr: {sensor.ic_manufacturer}")
            if sensor.resolution:
                lines.append(f"  {'':18s}  Resolution: {sensor.resolution}")
            if sensor.max_range:
                lines.append(f"  {'':18s}  Max Range: {sensor.max_range}")
            if sensor.power_consumption:
                lines.append(f"  {'':18s}  Power: {sensor.power_consumption} mA")
        else:
            lines.append(f"  {label:18s}: NOT FOUND")
    lines.append("")

    # --- All detected sensors ---
    if result.sensors:
        lines.append("All Detected Sensors:")
        for i, sensor in enumerate(result.sensors, 1):
            type_label = SENSOR_TYPE_LABELS.get(sensor.sensor_type, sensor.sensor_type)
            ic_str = f" [{sensor.ic_name}]" if sensor.ic_name else ""
            active_str = " (active)" if sensor.is_active else ""
            lines.append(
                f"  {i:2d}. {sensor.name:40s} {type_label:30s} "
                f"{sensor.status:8s}{ic_str}{active_str}"
            )
        lines.append("")

    # --- Warnings ---
    if result.warnings:
        lines.append("WARNINGS:")
        for w in result.warnings:
            lines.append(f"  - {w}")
    else:
        lines.append("No warnings.")
    lines.append("")

    # --- Common failure modes for detected ICs ---
    ics_with_failures = [
        s for s in result.sensors if s.common_failures and s.ic_name
    ]
    if ics_with_failures:
        lines.append("Known Failure Modes for Detected ICs:")
        seen_ics: set = set()
        for sensor in ics_with_failures:
            # Remove tentative markers for display
            clean_ic = sensor.ic_name.split(" (")[0]
            if clean_ic in seen_ics:
                continue
            seen_ics.add(clean_ic)
            lines.append(f"  {clean_ic} ({sensor.ic_manufacturer}):")
            for failure in sensor.common_failures:
                lines.append(f"    - {failure}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_sensor_status(
    callback: ProgressCallback = None,
) -> SensorTestResult:
    """Run the full sensor diagnostic sequence.

    Parameters
    ----------
    callback : optional
        A callable ``(pct: float, msg: str) -> None`` invoked with progress
        updates.  *pct* ranges from 0 to 100.

    Returns
    -------
    SensorTestResult
        Populated result dataclass with all sub-results, per-sensor status,
        health score, and an overall health assessment string.
    """
    result = SensorTestResult()
    logger.info("Starting advanced sensor test sequence")

    # -- Step 1: ADB connection --
    _notify(callback, 0.0, "Checking ADB connection...")
    connected, err = _check_adb_connection(callback)
    if not connected:
        result.connected = False
        result.error = err
        result.overall_health = f"UNABLE TO TEST -- {err}"
        _notify(callback, 100.0, f"Test aborted: {err}")
        return result
    result.connected = True

    try:
        # -- Step 2: Enumerate sensors via sensorservice --
        _notify(callback, 10.0, "Enumerating sensors via sensorservice...")
        ok, sensorservice_dump = _adb_shell("dumpsys sensorservice", timeout=15)
        if not ok:
            logger.warning("dumpsys sensorservice failed: %s", sensorservice_dump)
            sensorservice_dump = ""

        sensors = _parse_sensorservice_dump(sensorservice_dump)
        logger.info("Parsed %d sensors from sensorservice dump", len(sensors))

        _notify(callback, 20.0, f"Found {len(sensors)} sensors in sensorservice dump")

        # -- Step 3: Read additional sensor details from sysfs --
        sensors = _read_sysfs_sensor_details(callback, sensors)

        # -- Step 4: Identify sensor ICs --
        sensors = _identify_sensor_ics(callback, sensors)

        # -- Step 5: Test sensor status --
        sensors = _test_sensor_status(callback, sensors, sensorservice_dump)

        # Populate result fields
        result.sensors = sensors
        result.sensors_found = len(sensors)

        # Assign primary sensor slots (pick best of each type)
        _assign_primary_sensors(result, sensors)

        # -- Step 6: Analyze health --
        score, health_label, warnings = _analyze_health(callback, sensors)
        result.health_score = score
        result.overall_health = health_label
        result.warnings = warnings

        # Generate detailed assessment text (overwrite health label with full report)
        result.overall_health = _generate_overall_assessment(result)

    except Exception as exc:
        logger.exception("Sensor test sequence failed")
        result.error = str(exc)
        result.overall_health = f"TEST ERROR -- {exc}"

    _notify(callback, 100.0, "Sensor testing complete")
    logger.info("Sensor test sequence finished")
    return result


def _assign_primary_sensors(
    result: SensorTestResult,
    sensors: List[SensorInfo],
) -> None:
    """Assign the best sensor of each primary type to the result slots."""
    type_map = {
        "accelerometer": "accelerometer",
        "gyroscope": "gyroscope",
        "magnetometer": "magnetometer",
        "proximity": "proximity",
        "light": "light_sensor",
        "barometer": "barometer",
        "gravity": "gravity",
        "step_counter": "step_counter",
    }

    # Group sensors by type
    by_type: Dict[str, List[SensorInfo]] = {}
    for sensor in sensors:
        stype = sensor.sensor_type
        # Normalise compound types (proximity+light ICs report multiple)
        if stype in type_map:
            by_type.setdefault(stype, []).append(sensor)
        # Also check for proximity+light compound sensors
        elif stype == "proximity+light":
            by_type.setdefault("proximity", []).append(sensor)
            by_type.setdefault("light", []).append(sensor)

    # Select the best sensor for each slot (prefer OK > Warning > Fault > Unknown)
    status_priority = {"OK": 0, "Warning": 1, "Fault": 2, "Unknown": 3}

    for sensor_type, attr_name in type_map.items():
        candidates = by_type.get(sensor_type, [])
        if not candidates:
            continue
        # Sort by status (best first), then by whether IC was identified
        candidates.sort(key=lambda s: (
            status_priority.get(s.status, 3),
            0 if s.ic_name else 1,
        ))
        setattr(result, attr_name, candidates[0])


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
    print("  Advanced Sensor Tester -- Mooxy AI Fault Detector")
    print("=" * 70)
    print()

    test_result = detect_sensor_status(callback=_cli_callback)

    print()
    print("-" * 70)
    print(test_result.overall_health)
    print("-" * 70)

    if "--json" in sys.argv:
        print()
        print(json.dumps(asdict(test_result), indent=2, default=str))
