"""
ADB-based Hardware Detector for Mobile Repair Technicians.

Runs every possible non-root ADB command to extract maximum hardware
information from a connected Android phone.  The results feed a
health-diagnosis engine that flags OK / WARNING / FAULT for each
component, helping a technician locate faults quickly.

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
"""

import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class SensorInfo:
    name: str = ""
    vendor: str = ""
    sensor_type: str = ""
    max_range: str = ""
    resolution: str = ""
    power: str = ""
    version: int = 0


@dataclass
class ThermalZone:
    name: str = ""
    temp_c: float = 0.0


@dataclass
class CpuCoreInfo:
    core_id: int = 0
    max_freq_mhz: int = 0
    cur_freq_mhz: int = 0
    online: bool = True


@dataclass
class ComponentDiagnosis:
    """Health diagnosis for a single component."""
    component: str = ""
    status: str = "UNKNOWN"          # OK, WARNING, FAULT, UNKNOWN
    summary: str = ""
    problems: List[str] = field(default_factory=list)
    causes: List[str] = field(default_factory=list)
    checks: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)
    parts_needed: List[str] = field(default_factory=list)


@dataclass
class ADBDetectionResult:
    """Complete result from ADB hardware detection."""

    # -- Connection --
    connected: bool = False
    authorized: bool = False
    device_serial: str = ""

    # -- Device Identity --
    brand: str = ""
    model: str = ""
    device_name: str = ""
    manufacturer: str = ""
    android_version: str = ""
    sdk_version: str = ""
    build_number: str = ""
    build_fingerprint: str = ""
    build_type: str = ""
    build_date: str = ""
    security_patch: str = ""
    baseband_version: str = ""
    kernel_version: str = ""
    serial_number: str = ""
    bootloader: str = ""
    hardware: str = ""
    board: str = ""
    platform: str = ""
    first_api_level: str = ""

    # -- IMEI --
    imei: str = ""
    imei2: str = ""

    # -- CPU --
    chipset: str = ""
    cpu_abi: str = ""
    cpu_hardware: str = ""
    cpu_cores_count: int = 0
    cpu_cores: List[CpuCoreInfo] = field(default_factory=list)
    cpuinfo_raw: str = ""

    # -- GPU --
    gpu_renderer: str = ""
    gpu_vendor: str = ""
    gpu_version: str = ""
    gpu_raw: str = ""

    # -- RAM --
    ram_total_kb: int = 0
    ram_available_kb: int = 0
    ram_free_kb: int = 0
    ram_buffers_kb: int = 0
    ram_cached_kb: int = 0
    ram_swap_total_kb: int = 0
    ram_swap_free_kb: int = 0
    ram_type: str = ""
    meminfo_raw: str = ""
    ram_total: str = ""           # human-readable e.g. "7476MB"
    ram_free: str = ""            # human-readable e.g. "2048MB"

    # -- Storage --
    storage_total_kb: int = 0
    storage_used_kb: int = 0
    storage_free_kb: int = 0
    storage_type: str = ""
    storage_total: str = ""       # human-readable e.g. "128GB"
    storage_free: str = ""        # human-readable e.g. "64GB"
    storage_model: str = ""
    storage_vendor: str = ""
    storage_revision: str = ""
    storage_firmware: str = ""
    storage_life_time_a: str = ""   # UFS health estimation
    storage_life_time_b: str = ""
    storage_pre_eol: str = ""       # End of life indicator
    storage_health_pct: float = -1  # Calculated health percentage
    storage_manfid: str = ""        # eMMC manufacturer ID
    storage_cid: str = ""           # eMMC CID
    storage_partitions: list = field(default_factory=list)
    df_raw: str = ""

    # -- Battery (very detailed) --
    battery_level: int = -1
    battery_health: str = ""
    battery_health_code: int = -1
    battery_status: str = ""
    battery_status_code: int = -1
    battery_plugged: str = ""
    battery_technology: str = ""
    battery_temp_c: float = 0.0
    battery_temp: str = ""        # human-readable e.g. "35.5°C"
    battery_voltage: str = ""     # human-readable e.g. "4050mV"
    battery_voltage_mv: int = 0
    battery_current_now_ua: int = 0
    battery_current_now_ma: float = 0.0
    battery_charge_counter_uah: int = 0
    battery_charge_full_uah: int = 0
    battery_charge_full_design_uah: int = 0
    battery_cycle_count: int = -1
    battery_capacity_level: str = ""
    battery_age: str = ""
    battery_wear_pct: float = -1.0
    battery_dumpsys_raw: str = ""
    battery_sysfs: Dict[str, str] = field(default_factory=dict)

    # -- Charging IC --
    charger_type: str = ""
    charger_usb_online: str = ""
    charger_usb_voltage_uv: int = 0
    charger_usb_current_max_ua: int = 0
    charger_charge_type: str = ""
    charger_input_current_limit_ua: int = 0
    charger_sysfs: Dict[str, str] = field(default_factory=dict)
    charging_current_samples: List[int] = field(default_factory=list)

    # -- Display --
    display_resolution: str = ""
    display_override_resolution: str = ""
    display_density: int = 0
    display_override_density: int = 0
    display_refresh_rate: str = ""
    display_panel_info: str = ""
    display_hdr_support: str = ""
    display_modes: List[str] = field(default_factory=list)
    display_device_info: str = ""

    # -- Connectivity: WiFi --
    wifi_mac: str = ""
    wifi_ip: str = ""
    wifi_state: str = ""
    wifi_ssid: str = ""
    wifi_link_speed: str = ""
    wifi_status: str = ""         # alias: human-readable e.g. "enabled" / "disabled"

    # -- Connectivity: Bluetooth --
    bt_mac: str = ""
    bt_state: str = ""
    bt_name: str = ""
    bluetooth_mac: str = ""       # alias for bt_mac
    bluetooth_status: str = ""    # alias: human-readable e.g. "enabled" / "disabled"

    # -- Connectivity: SIM / Telephony --
    sim_state: str = ""
    sim_operator: str = ""
    sim_operator_numeric: str = ""
    sim_country: str = ""
    network_type: str = ""
    signal_strength_dbm: str = ""
    phone_type: str = ""
    data_state: str = ""

    # -- Camera --
    camera_ids: List[str] = field(default_factory=list)
    camera_details: Dict[str, str] = field(default_factory=dict)
    camera_video_devices: List[str] = field(default_factory=list)
    camera_raw: str = ""
    camera_info: str = ""         # human-readable summary
    rear_camera: str = ""         # rear camera model/id
    front_camera: str = ""        # front camera model/id

    # -- Sensors --
    sensors: List[SensorInfo] = field(default_factory=list)
    sensors_raw: str = ""
    sensors_list: List[str] = field(default_factory=list)  # flat name list

    # -- Audio --
    audio_output_devices: List[str] = field(default_factory=list)
    audio_input_devices: List[str] = field(default_factory=list)
    audio_streams: List[str] = field(default_factory=list)
    audio_raw: str = ""
    audio_policy_raw: str = ""

    # -- Fingerprint --
    fingerprint_hardware_detected: bool = False
    fingerprint_enrolled_count: int = -1
    fingerprint_raw: str = ""
    fingerprint_status: str = ""  # human-readable e.g. "available" / "not available"

    # -- NFC --
    nfc_enabled: Optional[bool] = None
    nfc_raw: str = ""

    # -- GPS / Location --
    gps_providers: str = ""
    location_raw: str = ""

    # -- Thermal --
    thermal_zones: List[ThermalZone] = field(default_factory=list)
    thermal_service_raw: str = ""

    # -- USB --
    usb_config: str = ""
    usb_data_role: str = ""
    usb_power_role: str = ""

    # -- Logcat analysis --
    logcat_battery_events: List[str] = field(default_factory=list)
    logcat_fingerprint_events: List[str] = field(default_factory=list)
    logcat_display_events: List[str] = field(default_factory=list)
    logcat_touch_events: List[str] = field(default_factory=list)
    logcat_audio_events: List[str] = field(default_factory=list)
    logcat_camera_events: List[str] = field(default_factory=list)
    logcat_wifi_events: List[str] = field(default_factory=list)
    logcat_bluetooth_events: List[str] = field(default_factory=list)
    logcat_modem_events: List[str] = field(default_factory=list)
    logcat_sensors_events: List[str] = field(default_factory=list)
    logcat_hw_driver_lines: List[str] = field(default_factory=list)
    logcat_crash_events: List[str] = field(default_factory=list)
    logcat_errors: List[str] = field(default_factory=list)
    logcat_raw_lines: int = 0

    # -- dmesg / driver component analysis --
    dmesg_components: Dict[str, Dict] = field(default_factory=dict)

    # -- Hardware status summary (populated by diagnose_health) --
    hw_status: Dict[str, Dict] = field(default_factory=dict)

    # -- Diagnosis --
    diagnoses: List[ComponentDiagnosis] = field(default_factory=list)

    # -- All properties --
    all_props: Dict[str, str] = field(default_factory=dict)

    # -- Detection log --
    log: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ---------------------------------------------------------------------------
#  ADB command helpers
# ---------------------------------------------------------------------------

def _run_adb(cmd: str, timeout: int = 10) -> str:
    """Run an ADB command and return stdout. Never raises."""
    try:
        r = subprocess.run(
            f"adb {cmd}",
            capture_output=True, text=True, timeout=timeout,
            shell=True, errors="replace",
        )
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError:
        return "ADB_NOT_FOUND"
    except Exception:
        return ""


def _shell(cmd: str, timeout: int = 10) -> str:
    """Shortcut for adb shell with quoting."""
    return _run_adb(f'shell "{cmd}"', timeout)


def _shell_raw(cmd: str, timeout: int = 10) -> str:
    """Shell without quoting (for pipes/redirects)."""
    return _run_adb(f"shell {cmd}", timeout)


def _safe_int(s: str, default: int = 0) -> int:
    try:
        return int(s.strip())
    except (ValueError, AttributeError):
        return default


def _safe_float(s: str, default: float = 0.0) -> float:
    try:
        return float(s.strip())
    except (ValueError, AttributeError):
        return default


def _prop(props: Dict[str, str], *keys: str) -> str:
    """Return first non-empty property value for the given keys."""
    for k in keys:
        v = props.get(k, "")
        if v:
            return v
    return ""


# ---------------------------------------------------------------------------
#  Parsing helpers
# ---------------------------------------------------------------------------

def _parse_getprop(raw: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for line in raw.splitlines():
        m = re.match(r"\[(.+?)\]:\s*\[(.*)?\]", line)
        if m:
            props[m.group(1)] = m.group(2) or ""
    return props


def _parse_battery_dumpsys(raw: str) -> Dict[str, str]:
    d: Dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            d[k.strip().lower()] = v.strip()
    return d


def _parse_meminfo(raw: str) -> Dict[str, int]:
    d: Dict[str, int] = {}
    for line in raw.splitlines():
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            d[m.group(1)] = int(m.group(2))
    return d


def _parse_df_line(raw: str) -> Tuple[int, int, int]:
    """Return (total_kb, used_kb, free_kb) from df output."""
    lines = raw.strip().splitlines()
    if len(lines) < 2:
        return 0, 0, 0
    parts = lines[-1].split()
    if len(parts) >= 4:
        nums = [p for p in parts if p.replace("K", "").replace("G", "").replace("M", "").isdigit()]
        if len(nums) >= 3:
            return _safe_int(nums[0]), _safe_int(nums[1]), _safe_int(nums[2])
        return _safe_int(parts[1]), _safe_int(parts[2]), _safe_int(parts[3])
    return 0, 0, 0


def _parse_sensors(raw: str) -> List[SensorInfo]:
    """Parse dumpsys sensorservice output into structured sensor list."""
    sensors: List[SensorInfo] = []
    for line in raw.splitlines():
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                s = SensorInfo()
                name_part = parts[0]
                idx_match = re.match(r"(?:0x[\da-fA-F]+|\d+)\)\s*(.*)", name_part)
                s.name = idx_match.group(1).strip() if idx_match else name_part.strip()
                if not s.name:
                    continue
                s.vendor = parts[1] if len(parts) > 1 else ""
                remainder = " ".join(parts[2:]) if len(parts) > 2 else ""
                rng = re.search(r"maxRange=([\d.]+)", remainder)
                res = re.search(r"resolution=([\d.]+)", remainder)
                pwr = re.search(r"power=([\d.]+)", remainder)
                typ = re.search(r"type=(\d+)", remainder)
                ver = re.search(r"ver(?:sion)?=(\d+)", remainder)
                if rng:
                    s.max_range = rng.group(1)
                if res:
                    s.resolution = res.group(1)
                if pwr:
                    s.power = pwr.group(1)
                if typ:
                    s.sensor_type = typ.group(1)
                if ver:
                    s.version = _safe_int(ver.group(1))
                sensors.append(s)
    if not sensors:
        for m in re.finditer(r"(?:Sensor|name)[:\s]+(.+)", raw, re.IGNORECASE):
            name = m.group(1).strip()[:80]
            if name:
                sensors.append(SensorInfo(name=name))
    return sensors


# ---------------------------------------------------------------------------
#  Logcat parser
# ---------------------------------------------------------------------------

_LOGCAT_PATTERNS: Dict[str, List[str]] = {
    "battery": [
        r"battery", r"uevent.*power_supply", r"charge_full", r"cycle_count",
        r"BatteryService", r"health.*battery", r"CHARGE_COUNTER",
        r"VOLTAGE_NOW", r"CURRENT_NOW", r"POWER_WATT", r"charge_rate",
    ],
    "fingerprint": [
        r"fingerprint", r"biometric", r"match.*score",
        r"fpc\d+", r"fpc.*probe", r"fpc.*init", r"fpc.*detect",
        r"goodix.*fp", r"goodix_fp", r"GF_HAL", r"Goodix.*Fingerprint",
        r"egis.*init", r"egis.*probe", r"egis.*detect",
        r"silead", r"cdfinger",
        r"UdfpsController", r"udfps",
    ],
    "display": [
        r"lcm", r"dsi", r"panel", r"backlight", r"disp",
        r"panel.*mode", r"refresh.*rate", r"DisplayManager",
        r"SurfaceFlinger.*display", r"hwc|HWComposer",
        r"DisplayPanel", r"HBM", r"DC.*mode", r"brightness",
        r"drm.*init", r"mtk_drm", r"MIPI",
        r"display.*config", r"activeConfig",
    ],
    "touch": [
        r"touch.*hal", r"input.*touch", r"TouchHwService",
        r"goodix", r"goodix_ts", r"goodix.*touch",
        r"focaltech", r"fts_ts", r"focaltech.*probe",
        r"synaptics", r"synaptics.*probe",
        r"ili", r"ilitek", r"ili\d+", r"ili.*probe",
        r"himax", r"himax.*probe",
        r"novatek", r"nvt.*ts", r"novatek.*probe",
        r"MotTouch", r"tpd",
    ],
    "audio": [
        r"aw882xx", r"aw882xx.*init", r"aw882xx.*probe",
        r"tfa98xx", r"tfa98xx.*init", r"tfa98xx.*probe",
        r"smartpa", r"smartpa.*init",
        r"AudioFlinger", r"AudioPolicyService", r"AudioALSA",
        r"ALSA", r"audio_hw", r"tinyalsa", r"AudioSystem",
        r"codec.*init", r"speaker", r"headset", r"jack.*detect",
        r"ACCDET", r"mt6358.*codec", r"mt6359.*codec",
    ],
    "camera": [
        r"cam.*probe", r"cam.*init", r"cam.*open",
        r"imgsensor", r"imgsensor.*probe", r"imgsensor.*detect",
        r"ois.*init", r"ois.*probe", r"ois.*ready",
        r"eeprom.*init", r"eeprom.*probe", r"eeprom.*read",
        r"seninf", r"camera.*service", r"CameraService",
        r"imx\d+", r"ov\d+", r"s5k\d+", r"hi\d+", r"gc\d+",
    ],
    "wifi": [
        r"wlan", r"wlan.*init", r"wlan.*probe", r"wlan.*ready",
        r"wmt", r"wmt.*init", r"wmt.*probe", r"WMT",
        r"conninfra", r"conninfra.*init", r"conninfra.*probe",
        r"connac", r"wifi.*init", r"wifi.*probe",
        r"mt76\d+", r"wcn\d+",
    ],
    "bluetooth": [
        r"btif", r"btif.*init", r"btif.*probe",
        r"btmtk", r"btmtk.*init", r"btmtk.*probe",
        r"bluetooth.*init", r"BT.*init", r"hci.*init",
        r"conninfra.*bt", r"wmt.*bt",
        r"BTAudioHw", r"BTService",
    ],
    "modem": [
        r"ccci", r"ccci.*init", r"ccci.*probe", r"ccci.*ready",
        r"md.*init", r"md.*ready", r"MD.*init",
        r"modem", r"modem.*init", r"modem.*ready",
        r"CLDMA", r"baseband", r"RF.*init",
    ],
    "sensors": [
        r"sensorservice", r"sensorhub", r"nanohub",
        r"accel.*init", r"gyro.*init", r"proximity.*init",
        r"lis2hh", r"bmi\d+", r"lsm\d+", r"icm\d+",
        r"stk\d+", r"cm36\d+", r"apds\d+", r"mmc\d+.*mag",
        r"alsps", r"sar_unify",
    ],
    "crash": [
        r"FATAL", r"ANR", r"tombstone", r"native crash",
        r"kernel panic", r"SIGABRT", r"SIGSEGV",
        r"force.*close", r"app.*died", r"process.*died",
    ],
    "error": [
        r"^E/", r"\bERROR\b", r"\bFAIL\b",
    ],
}


def _parse_logcat(raw: str, result: ADBDetectionResult) -> None:
    """Classify logcat lines into result buckets."""
    lines = raw.splitlines()
    result.logcat_raw_lines = len(lines)
    buckets = {
        "battery": result.logcat_battery_events,
        "fingerprint": result.logcat_fingerprint_events,
        "display": result.logcat_display_events,
        "touch": result.logcat_touch_events,
        "audio": result.logcat_audio_events,
        "camera": result.logcat_camera_events,
        "wifi": result.logcat_wifi_events,
        "bluetooth": result.logcat_bluetooth_events,
        "modem": result.logcat_modem_events,
        "sensors": result.logcat_sensors_events,
        "crash": result.logcat_crash_events,
        "error": result.logcat_errors,
    }
    compiled: Dict[str, list] = {}
    for cat, pats in _LOGCAT_PATTERNS.items():
        compiled[cat] = [re.compile(p, re.IGNORECASE) for p in pats]

    for line in lines:
        for cat, pats in compiled.items():
            for pat in pats:
                if pat.search(line):
                    bucket = buckets[cat]
                    if len(bucket) < 200:
                        bucket.append(line.strip()[:300])
                    break


# ---------------------------------------------------------------------------
#  Main detection
# ---------------------------------------------------------------------------

def detect_via_adb(callback: Optional[Callable] = None) -> ADBDetectionResult:
    """
    Full ADB detection pipeline.

    Runs every possible non-root ADB command, parses all output,
    builds component list, runs diagnosis, returns everything.

    *callback(progress_float, message_str)* is called periodically for UI.
    """
    r = ADBDetectionResult()
    r.log = []

    def _cb(pct: float, msg: str) -> None:
        r.log.append(msg)
        if callback:
            callback(pct, msg)

    # ------------------------------------------------------------------
    # 1. ADB availability
    # ------------------------------------------------------------------
    _cb(0.01, "Checking ADB installation...")
    ver = _run_adb("version")
    if "ADB_NOT_FOUND" in ver:
        r.error = "ADB not found. Install Android Platform Tools and add to PATH."
        r.log.append("  [FAIL] ADB not installed")
        return r
    r.log.append("  [OK] ADB found")

    # ------------------------------------------------------------------
    # 2. Device connection
    # ------------------------------------------------------------------
    _cb(0.03, "Checking for connected devices...")
    dev_out = _run_adb("devices")
    if not dev_out:
        r.error = "No output from 'adb devices'. Check ADB installation."
        return r

    for line in dev_out.splitlines()[1:]:
        parts = line.strip().split("\t")
        if len(parts) >= 2:
            r.device_serial = parts[0]
            if parts[1] == "device":
                r.connected = True
                r.authorized = True
            elif parts[1] == "unauthorized":
                r.connected = True
                r.authorized = False
                r.error = "Device unauthorized. Accept USB debugging prompt on phone."
                return r
            break

    if not r.connected:
        r.error = "No device detected. Check: 1) USB cable 2) USB Debugging ON 3) Authorize PC on phone"
        return r
    r.log.append(f"  [OK] Device: {r.device_serial}")

    # ------------------------------------------------------------------
    # 3. getprop (all properties)
    # ------------------------------------------------------------------
    _cb(0.05, "Reading all device properties (getprop)...")
    props_raw = _shell_raw("getprop", timeout=15)
    r.all_props = _parse_getprop(props_raw)
    r.log.append(f"  [OK] {len(r.all_props)} properties loaded")

    # Extract identity
    r.brand = _prop(r.all_props, "ro.product.brand", "ro.product.system.brand")
    r.model = _prop(r.all_props, "ro.product.model", "ro.product.system.model")
    r.device_name = _prop(r.all_props, "ro.product.device", "ro.product.system.device")
    r.manufacturer = _prop(r.all_props, "ro.product.manufacturer")
    r.android_version = _prop(r.all_props, "ro.build.version.release")
    r.sdk_version = _prop(r.all_props, "ro.build.version.sdk")
    r.build_number = _prop(r.all_props, "ro.build.display.id")
    r.build_fingerprint = _prop(r.all_props, "ro.build.fingerprint")
    r.build_type = _prop(r.all_props, "ro.build.type")
    r.build_date = _prop(r.all_props, "ro.build.date")
    r.security_patch = _prop(r.all_props, "ro.build.version.security_patch")
    r.baseband_version = _prop(r.all_props, "gsm.version.baseband")
    r.serial_number = _prop(r.all_props, "ro.serialno") or r.device_serial
    r.bootloader = _prop(r.all_props, "ro.bootloader")
    r.hardware = _prop(r.all_props, "ro.hardware")
    r.board = _prop(r.all_props, "ro.product.board")
    r.platform = _prop(r.all_props, "ro.board.platform", "ro.hardware.chipname")
    r.chipset = _prop(r.all_props, "ro.hardware.chipname", "ro.board.platform", "ro.hardware")
    r.first_api_level = _prop(r.all_props, "ro.product.first_api_level")

    r.log.append(f"  Brand={r.brand}  Model={r.model}  Android={r.android_version}")

    # ------------------------------------------------------------------
    # 4. Kernel version
    # ------------------------------------------------------------------
    r.kernel_version = _shell_raw("uname -a")

    # ------------------------------------------------------------------
    # 5. CPU
    # ------------------------------------------------------------------
    _cb(0.10, "Reading CPU info...")
    r.cpuinfo_raw = _shell_raw("cat /proc/cpuinfo", timeout=10)
    procs = re.findall(r"^processor\s*:\s*(\d+)", r.cpuinfo_raw, re.MULTILINE)
    r.cpu_cores_count = len(procs) if procs else 0
    hw = re.search(r"^Hardware\s*:\s*(.+)", r.cpuinfo_raw, re.MULTILINE)
    r.cpu_hardware = hw.group(1).strip() if hw else ""
    r.cpu_abi = _prop(r.all_props, "ro.product.cpu.abi")

    # Per-core frequencies
    for i in range(max(r.cpu_cores_count, 8)):
        max_f = _shell_raw(f"cat /sys/devices/system/cpu/cpu{i}/cpufreq/cpuinfo_max_freq 2>/dev/null")
        cur_f = _shell_raw(f"cat /sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq 2>/dev/null")
        if not max_f and not cur_f:
            if i >= r.cpu_cores_count:
                break
            r.cpu_cores.append(CpuCoreInfo(core_id=i, online=True))
            continue
        c = CpuCoreInfo(
            core_id=i,
            max_freq_mhz=_safe_int(max_f) // 1000 if max_f else 0,
            cur_freq_mhz=_safe_int(cur_f) // 1000 if cur_f else 0,
            online=True,
        )
        r.cpu_cores.append(c)

    if not r.cpu_cores_count and r.cpu_cores:
        r.cpu_cores_count = len(r.cpu_cores)

    r.log.append(f"  CPU: {r.chipset or r.cpu_hardware}, {r.cpu_cores_count} cores, ABI={r.cpu_abi}")
    for c in r.cpu_cores:
        r.log.append(f"    core{c.core_id}: max={c.max_freq_mhz}MHz cur={c.cur_freq_mhz}MHz")

    # ------------------------------------------------------------------
    # 6. GPU
    # ------------------------------------------------------------------
    _cb(0.15, "Reading GPU info...")
    gles_raw = _shell_raw("dumpsys SurfaceFlinger | grep GLES")
    if gles_raw:
        r.gpu_raw = gles_raw.strip()
        parts = gles_raw.split(",")
        if len(parts) >= 3:
            r.gpu_vendor = parts[0].replace("GLES:", "").strip()
            r.gpu_renderer = parts[1].strip()
            r.gpu_version = ",".join(parts[2:]).strip()[:100]
        else:
            r.gpu_renderer = gles_raw.strip()[:150]
    if not r.gpu_renderer:
        r.gpu_renderer = _prop(r.all_props, "ro.hardware.egl")
    r.log.append(f"  GPU: {r.gpu_vendor} {r.gpu_renderer}")

    # ------------------------------------------------------------------
    # 7. RAM
    # ------------------------------------------------------------------
    _cb(0.18, "Reading memory info...")
    r.meminfo_raw = _shell_raw("cat /proc/meminfo", timeout=10)
    mi = _parse_meminfo(r.meminfo_raw)
    r.ram_total_kb = mi.get("MemTotal", 0)
    r.ram_available_kb = mi.get("MemAvailable", 0)
    r.ram_free_kb = mi.get("MemFree", 0)
    r.ram_buffers_kb = mi.get("Buffers", 0)
    r.ram_cached_kb = mi.get("Cached", 0)
    r.ram_swap_total_kb = mi.get("SwapTotal", 0)
    r.ram_swap_free_kb = mi.get("SwapFree", 0)
    r.ram_type = _prop(r.all_props, "ro.boot.hardware.ddr")
    r.ram_total = f"{r.ram_total_kb // 1024}MB"
    r.ram_free = f"{r.ram_free_kb // 1024}MB"
    r.log.append(f"  RAM: {r.ram_total_kb // 1024}MB total, {r.ram_available_kb // 1024}MB available")

    # ------------------------------------------------------------------
    # 8. Storage
    # ------------------------------------------------------------------
    _cb(0.22, "Reading storage info...")
    df_data = _shell_raw("df /data", timeout=10)
    r.df_raw = df_data
    total, used, free = _parse_df_line(df_data)
    r.storage_total_kb = total
    r.storage_used_kb = used
    r.storage_free_kb = free
    r.storage_total = f"{total // (1024 * 1024)}GB"
    r.storage_free = f"{free // (1024 * 1024)}GB"

    # Storage manufacturer ID mapping
    _storage_manfid_map = {
        "0x15": "Samsung", "0x0015": "Samsung",
        "0xad": "SK Hynix", "0x00ad": "SK Hynix",
        "0x2c": "Micron", "0x002c": "Micron",
        "0x45": "SanDisk", "0x0045": "SanDisk",
        "0x98": "Toshiba/Kioxia", "0x0098": "Toshiba/Kioxia",
        "0xfe": "Micron", "0x00fe": "Micron",
        "0x13": "Micron", "0x0013": "Micron",
    }

    def _valid_sysfs(val: str) -> bool:
        return bool(val) and "No such" not in val and "Permission" not in val

    stor_model = _shell_raw("cat /sys/class/block/sda/device/model 2>/dev/null")
    if _valid_sysfs(stor_model):
        r.storage_type = "UFS"
        r.storage_model = stor_model.strip()

        # UFS vendor info
        ufs_vendor = _shell_raw("cat /sys/class/block/sda/device/vendor 2>/dev/null")
        if _valid_sysfs(ufs_vendor):
            r.storage_vendor = ufs_vendor.strip()
        ufs_rev = _shell_raw("cat /sys/class/block/sda/device/rev 2>/dev/null")
        if _valid_sysfs(ufs_rev):
            r.storage_revision = ufs_rev.strip()
        ufs_sector = _shell_raw("cat /sys/class/block/sda/queue/hw_sector_size 2>/dev/null")
        if _valid_sysfs(ufs_sector):
            r.storage_firmware = f"sector_size={ufs_sector.strip()}"

        # UFS health / life time estimation
        lta = _shell_raw("cat /sys/class/block/sda/device/life_time_estimation_type_a 2>/dev/null")
        if _valid_sysfs(lta):
            r.storage_life_time_a = lta.strip()
        ltb = _shell_raw("cat /sys/class/block/sda/device/life_time_estimation_type_b 2>/dev/null")
        if _valid_sysfs(ltb):
            r.storage_life_time_b = ltb.strip()
        pre_eol = _shell_raw("cat /sys/class/block/sda/device/pre_eol_info 2>/dev/null")
        if _valid_sysfs(pre_eol):
            r.storage_pre_eol = pre_eol.strip()
    else:
        emmc_name = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/name 2>/dev/null")
        if _valid_sysfs(emmc_name):
            r.storage_type = "eMMC"
            r.storage_model = emmc_name.strip()

            # eMMC detailed info
            emmc_manfid = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/manfid 2>/dev/null")
            if _valid_sysfs(emmc_manfid):
                r.storage_manfid = emmc_manfid.strip()
                r.storage_vendor = _storage_manfid_map.get(
                    r.storage_manfid.lower(), r.storage_manfid)
            emmc_oemid = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/oemid 2>/dev/null")
            if _valid_sysfs(emmc_oemid):
                r.storage_firmware = f"oemid={emmc_oemid.strip()}"
            emmc_fwrev = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/fwrev 2>/dev/null")
            if _valid_sysfs(emmc_fwrev):
                r.storage_revision = emmc_fwrev.strip()
            emmc_hwrev = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/hwrev 2>/dev/null")
            if _valid_sysfs(emmc_hwrev):
                fw_str = r.storage_firmware
                r.storage_firmware = f"{fw_str}, hwrev={emmc_hwrev.strip()}" if fw_str else f"hwrev={emmc_hwrev.strip()}"
            emmc_cid = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/cid 2>/dev/null")
            if _valid_sysfs(emmc_cid):
                r.storage_cid = emmc_cid.strip()

            # eMMC health
            emmc_lt = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/life_time 2>/dev/null")
            if _valid_sysfs(emmc_lt):
                # life_time may contain two hex values like "0x02 0x02"
                parts = emmc_lt.strip().split()
                if len(parts) >= 1:
                    r.storage_life_time_a = parts[0]
                if len(parts) >= 2:
                    r.storage_life_time_b = parts[1]
            emmc_eol = _shell_raw("cat /sys/class/mmc_host/mmc0/mmc0:0001/pre_eol_info 2>/dev/null")
            if _valid_sysfs(emmc_eol):
                r.storage_pre_eol = emmc_eol.strip()
        else:
            r.storage_type = _prop(r.all_props, "ro.boot.hardware.storage") or "Unknown"

    # Parse partition table
    part_raw = _shell_raw("cat /proc/partitions 2>/dev/null")
    if _valid_sysfs(part_raw):
        for line in part_raw.strip().splitlines()[2:]:  # skip header lines
            parts = line.split()
            if len(parts) >= 4:
                r.storage_partitions.append({
                    "major": parts[0], "minor": parts[1],
                    "blocks": _safe_int(parts[2]), "name": parts[3],
                })

    # Calculate storage health percentage from life_time_estimation
    # life_time values: 0x01=0-10% used, 0x02=10-20%, ..., 0x0A=90-100%, 0x0B=exceeded
    def _parse_life_time(val: str) -> float:
        """Convert life_time hex to estimated % used.  Returns -1 if unparseable."""
        if not val:
            return -1
        try:
            v = int(val, 0)  # handles 0x prefix
        except (ValueError, TypeError):
            return -1
        if v < 1 or v > 0x0B:
            return -1
        if v == 0x0B:
            return 100.0  # exceeded lifetime
        return (v - 1) * 10 + 5  # midpoint of the range

    lt_a_pct = _parse_life_time(r.storage_life_time_a)
    lt_b_pct = _parse_life_time(r.storage_life_time_b)
    if lt_a_pct >= 0 and lt_b_pct >= 0:
        used_pct = max(lt_a_pct, lt_b_pct)
        r.storage_health_pct = round(100.0 - used_pct, 1)
    elif lt_a_pct >= 0:
        r.storage_health_pct = round(100.0 - lt_a_pct, 1)
    elif lt_b_pct >= 0:
        r.storage_health_pct = round(100.0 - lt_b_pct, 1)

    # pre_eol_info: 0x01=Normal, 0x02=Warning, 0x03=Urgent
    _pre_eol_map = {"0x01": "Normal", "0x02": "Warning", "0x03": "Urgent",
                    "1": "Normal", "2": "Warning", "3": "Urgent"}
    r.log.append(f"  Storage: {r.storage_total_kb // (1024*1024)}GB total, "
                 f"{r.storage_free_kb // (1024*1024)}GB free, type={r.storage_type} {r.storage_model}")
    r.log.append(f"  Storage vendor={r.storage_vendor}, rev={r.storage_revision}, "
                 f"life_a={r.storage_life_time_a}, life_b={r.storage_life_time_b}, "
                 f"pre_eol={r.storage_pre_eol}, health={r.storage_health_pct}%")

    # ------------------------------------------------------------------
    # 9. Battery (very detailed)
    # ------------------------------------------------------------------
    _cb(0.28, "Reading battery info (detailed)...")
    r.battery_dumpsys_raw = _shell_raw("dumpsys battery", timeout=10)
    bd = _parse_battery_dumpsys(r.battery_dumpsys_raw)

    r.battery_level = _safe_int(bd.get("level", "-1"), -1)
    r.battery_health_code = _safe_int(bd.get("health", "-1"), -1)
    health_map = {1: "Unknown", 2: "Good", 3: "Overheat", 4: "Dead",
                  5: "Over voltage", 6: "Failure", 7: "Cold"}
    r.battery_health = health_map.get(r.battery_health_code, str(r.battery_health_code))
    r.battery_status_code = _safe_int(bd.get("status", "-1"), -1)
    status_map = {1: "Unknown", 2: "Charging", 3: "Discharging",
                  4: "Not charging", 5: "Full"}
    r.battery_status = status_map.get(r.battery_status_code, str(r.battery_status_code))
    plugged_map = {"0": "Unplugged", "1": "AC", "2": "USB", "4": "Wireless"}
    r.battery_plugged = plugged_map.get(bd.get("plugged", ""), bd.get("plugged", ""))
    r.battery_technology = bd.get("technology", "")
    temp_raw = bd.get("temperature", "0")
    r.battery_temp_c = _safe_int(temp_raw) / 10.0
    r.battery_temp = f"{r.battery_temp_c}°C"
    r.battery_voltage_mv = _safe_int(bd.get("voltage", "0"))
    r.battery_voltage = f"{r.battery_voltage_mv}mV"

    # sysfs battery files
    sysfs_keys = [
        "current_now", "voltage_now", "charge_full", "charge_full_design",
        "charge_counter", "cycle_count", "capacity_level", "health",
        "status", "technology", "temp", "age",
    ]
    for key in sysfs_keys:
        val = _shell_raw(f"cat /sys/class/power_supply/battery/{key} 2>/dev/null")
        if val and "No such" not in val and "Permission" not in val:
            r.battery_sysfs[key] = val.strip()

    # Parse sysfs values
    r.battery_current_now_ua = _safe_int(r.battery_sysfs.get("current_now", "0"))
    r.battery_current_now_ma = r.battery_current_now_ua / 1000.0
    r.battery_charge_counter_uah = _safe_int(r.battery_sysfs.get("charge_counter", "0"))
    r.battery_charge_full_uah = _safe_int(r.battery_sysfs.get("charge_full", "0"))
    r.battery_charge_full_design_uah = _safe_int(r.battery_sysfs.get("charge_full_design", "0"))
    r.battery_cycle_count = _safe_int(r.battery_sysfs.get("cycle_count", "-1"), -1)
    r.battery_capacity_level = r.battery_sysfs.get("capacity_level", "")
    r.battery_age = r.battery_sysfs.get("age", "")

    # Calculate wear percentage
    if r.battery_charge_full_uah > 0 and r.battery_charge_full_design_uah > 0:
        r.battery_wear_pct = round(
            (1.0 - r.battery_charge_full_uah / r.battery_charge_full_design_uah) * 100.0, 1
        )

    r.log.append(f"  Battery: {r.battery_level}%, health={r.battery_health}, "
                 f"temp={r.battery_temp_c}C, status={r.battery_status}")
    r.log.append(f"  Battery wear: {r.battery_wear_pct}%, cycles={r.battery_cycle_count}, "
                 f"charge_full={r.battery_charge_full_uah}uAh, "
                 f"design={r.battery_charge_full_design_uah}uAh")

    # Charging IC / USB power supply sysfs
    _cb(0.38, "Reading charging IC info...")
    charging_sysfs_keys = {
        "/sys/class/power_supply/usb/type": "usb_type",
        "/sys/class/power_supply/usb/online": "usb_online",
        "/sys/class/power_supply/usb/voltage_now": "usb_voltage_now",
        "/sys/class/power_supply/usb/current_max": "usb_current_max",
        "/sys/class/power_supply/usb/current_now": "usb_current_now",
        "/sys/class/power_supply/battery/charge_type": "charge_type",
        "/sys/class/power_supply/battery/input_current_limit": "input_current_limit",
        "/sys/class/power_supply/battery/constant_charge_current": "constant_charge_current",
        "/sys/class/power_supply/battery/constant_charge_voltage": "constant_charge_voltage",
        "/sys/class/power_supply/usb/pd_active": "pd_active",
        "/sys/class/power_supply/usb/real_type": "usb_real_type",
        "/sys/class/power_supply/battery/charge_rate": "charge_rate",
        "/sys/class/power_supply/battery/power_watt": "power_watt",
        "/sys/class/power_supply/battery/input_voltage_limit": "input_voltage_limit",
    }

    for path, key in charging_sysfs_keys.items():
        val = _shell_raw(f"cat {path} 2>/dev/null")
        if val and "No such" not in val and "Permission" not in val:
            r.charger_sysfs[key] = val.strip()

    r.charger_type = r.charger_sysfs.get("usb_type", r.charger_sysfs.get("usb_real_type", ""))
    r.charger_usb_online = r.charger_sysfs.get("usb_online", "")
    r.charger_usb_voltage_uv = _safe_int(r.charger_sysfs.get("usb_voltage_now", "0"))
    r.charger_usb_current_max_ua = _safe_int(r.charger_sysfs.get("usb_current_max", "0"))
    r.charger_charge_type = r.charger_sysfs.get("charge_type", r.charger_sysfs.get("charge_rate", ""))
    r.charger_input_current_limit_ua = _safe_int(r.charger_sysfs.get("input_current_limit", "0"))

    r.log.append(f"  Charger: type={r.charger_type}, online={r.charger_usb_online}")
    r.log.append(f"  USB voltage={r.charger_usb_voltage_uv}uV, current_max={r.charger_usb_current_max_ua}uA")
    r.log.append(f"  Charge type={r.charger_charge_type}, input_limit={r.charger_input_current_limit_ua}uA")

    # Current sampling (5 samples, 1 sec apart) for current graph
    _cb(0.40, "Sampling charging current (5 readings)...")
    for i in range(5):
        cur_val = _shell_raw("cat /sys/class/power_supply/battery/current_now 2>/dev/null")
        if cur_val and cur_val.lstrip("-").isdigit():
            r.charging_current_samples.append(int(cur_val))
        else:
            r.charging_current_samples.append(0)
        if i < 4:
            import time as _time
            _time.sleep(1)

    if r.charging_current_samples:
        avg_ua = sum(r.charging_current_samples) / len(r.charging_current_samples)
        r.log.append(f"  Current samples (uA): {r.charging_current_samples}")
        r.log.append(f"  Average current: {avg_ua/1000:.1f} mA")

    # ------------------------------------------------------------------
    # 10. Display
    # ------------------------------------------------------------------
    _cb(0.35, "Reading display info...")
    wm_size = _shell_raw("wm size")
    for line in wm_size.splitlines():
        if "Physical" in line:
            r.display_resolution = line.split(":")[-1].strip()
        elif "Override" in line:
            r.display_override_resolution = line.split(":")[-1].strip()

    wm_dens = _shell_raw("wm density")
    for line in wm_dens.splitlines():
        if "Physical" in line:
            r.display_density = _safe_int(line.split(":")[-1].strip())
        elif "Override" in line:
            r.display_override_density = _safe_int(line.split(":")[-1].strip())

    refresh = _shell_raw("settings get system peak_refresh_rate")
    if refresh and refresh != "null":
        r.display_refresh_rate = refresh.strip()

    disp_dump = _shell_raw("dumpsys display | grep -iE 'mPhys|DisplayDeviceInfo'", timeout=10)
    if disp_dump:
        r.display_device_info = disp_dump.strip()[:500]

    sf_disp = _shell_raw(
        "dumpsys SurfaceFlinger | grep -iE 'display|panel|mode|hdr'",
        timeout=10,
    )
    if sf_disp:
        for line in sf_disp.strip().splitlines()[:30]:
            stripped = line.strip()
            if stripped:
                r.display_modes.append(stripped[:200])
            if "hdr" in stripped.lower():
                r.display_hdr_support = stripped[:200]

    r.log.append(f"  Display: {r.display_resolution}, density={r.display_density}, "
                 f"refresh={r.display_refresh_rate}")

    # ------------------------------------------------------------------
    # 11. WiFi
    # ------------------------------------------------------------------
    _cb(0.40, "Reading WiFi info...")
    wifi_ip_raw = _shell_raw("ip addr show wlan0 2>/dev/null")
    mac_m = re.search(r"link/ether\s+([0-9a-fA-F:]+)", wifi_ip_raw)
    if mac_m:
        r.wifi_mac = mac_m.group(1)
    ip_m = re.search(r"inet\s+([\d.]+)/", wifi_ip_raw)
    if ip_m:
        r.wifi_ip = ip_m.group(1)
    r.wifi_state = _prop(r.all_props, "wlan.driver.status", "init.svc.wpa_supplicant")
    r.wifi_ssid = _prop(r.all_props, "wifi.interface.ssid")
    r.wifi_status = "enabled" if (r.wifi_mac and r.wifi_mac != "02:00:00:00:00:00") else "disabled"
    r.log.append(f"  WiFi: mac={r.wifi_mac}, ip={r.wifi_ip}, state={r.wifi_state}")

    # ------------------------------------------------------------------
    # 12. Bluetooth
    # ------------------------------------------------------------------
    _cb(0.43, "Reading Bluetooth info...")
    r.bt_mac = _shell_raw("settings get secure bluetooth_address")
    if not r.bt_mac or r.bt_mac == "null":
        r.bt_mac = _prop(r.all_props, "persist.bluetooth.bluetoothaddr",
                         "ro.boot.btmacaddr")
    r.bt_state = _prop(r.all_props, "init.svc.bluetooth")
    r.bt_name = _prop(r.all_props, "persist.bluetooth.bluetooth_name", "net.bt.name")
    r.bluetooth_mac = r.bt_mac
    r.bluetooth_status = "enabled" if r.bt_mac and r.bt_mac not in ["", "null"] else "disabled"
    r.log.append(f"  Bluetooth: mac={r.bt_mac}, state={r.bt_state}")

    # ------------------------------------------------------------------
    # 13. SIM / Telephony
    # ------------------------------------------------------------------
    _cb(0.46, "Reading SIM/telephony info...")
    r.sim_state = _prop(r.all_props, "gsm.sim.state")
    r.sim_operator = _prop(r.all_props, "gsm.sim.operator.alpha", "gsm.operator.alpha")
    r.sim_operator_numeric = _prop(r.all_props, "gsm.sim.operator.numeric")
    r.sim_country = _prop(r.all_props, "gsm.sim.operator.iso-country")
    r.network_type = _prop(r.all_props, "gsm.network.type")
    r.phone_type = _prop(r.all_props, "gsm.current.phone-type")
    r.data_state = _prop(r.all_props, "gsm.nitz.time")

    sig_raw = _shell_raw(
        "dumpsys telephony.registry | grep -iE 'signal|level|dbm'",
        timeout=10,
    )
    if sig_raw:
        dbm_m = re.search(r"(-?\d+)\s*dBm", sig_raw)
        if dbm_m:
            r.signal_strength_dbm = dbm_m.group(1) + " dBm"
        else:
            for line in sig_raw.splitlines():
                stripped = line.strip()
                if stripped and len(stripped) > 5:
                    r.signal_strength_dbm = stripped[:150]
                    break

    r.log.append(f"  SIM: state={r.sim_state}, op={r.sim_operator}, "
                 f"net={r.network_type}, signal={r.signal_strength_dbm}")

    # ------------------------------------------------------------------
    # 14. IMEI (hex-based parcel parser — fixes last 3 digits loss)
    # ------------------------------------------------------------------
    _cb(0.48, "Reading IMEI...")

    def _parse_parcel_imei(parcel_out: str) -> str:
        """Parse IMEI from service call parcel output using hex words directly."""
        data_words = []
        for line in parcel_out.splitlines():
            m = re.match(r"\s*0x[0-9a-fA-F]+:\s+(.+?)(?:'|$)", line)
            if not m:
                continue
            words = re.findall(r'[0-9a-fA-F]{8}', m.group(1))
            data_words.extend(words)
        if len(data_words) >= 3:
            chars = []
            str_len = int(data_words[1], 16) if len(data_words) > 1 else 0
            for wh in data_words[2:]:
                wv = int(wh, 16)
                c1, c2 = wv & 0xFFFF, (wv >> 16) & 0xFFFF
                if c1: chars.append(chr(c1))
                if c2: chars.append(chr(c2))
            if 0 < str_len < len(chars):
                chars = chars[:str_len]
            digits = re.sub(r"[^0-9]", "", "".join(chars))
            if len(digits) >= 15:
                return digits[:15]
        # Fallback: old quote-based method
        qdigits = re.findall(r"'([\d.]+)'", parcel_out)
        if qdigits:
            return "".join(qdigits).replace(".", "").strip()[:15]
        return ""

    imei_raw = _shell_raw("service call iphonesubinfo 1 s16 com.android.shell")
    r.imei = _parse_parcel_imei(imei_raw)
    if not r.imei:
        imei_raw = _shell_raw("service call iphonesubinfo 1")
        r.imei = _parse_parcel_imei(imei_raw)
    if not r.imei:
        r.imei = _prop(r.all_props, "persist.radio.imei", "gsm.imei")

    imei2_raw = _shell_raw("service call iphonesubinfo 3 s16 com.android.shell")
    r.imei2 = _parse_parcel_imei(imei2_raw)
    if not r.imei2:
        imei2_raw = _shell_raw("service call iphonesubinfo 3")
        r.imei2 = _parse_parcel_imei(imei2_raw)

    r.log.append(f"  IMEI: {r.imei}")

    # ------------------------------------------------------------------
    # 15. Camera
    # ------------------------------------------------------------------
    _cb(0.52, "Reading camera info...")
    r.camera_raw = _shell_raw("dumpsys media.camera", timeout=15)
    if not r.camera_raw or len(r.camera_raw) < 20:
        r.camera_raw = _shell_raw("dumpsys cameraservice", timeout=15)

    cam_ids = re.findall(r"(?:Camera|camera)\s*(?:id|ID)?[:\s]*(\d+)", r.camera_raw)
    r.camera_ids = sorted(set(cam_ids))

    for cid in r.camera_ids:
        pat = re.search(rf"id\s*{cid}.*?facing[:\s]*(\w+)", r.camera_raw, re.IGNORECASE | re.DOTALL)
        facing = pat.group(1) if pat else "unknown"
        r.camera_details[cid] = facing

    vid_devs = _shell_raw("ls /dev/video* 2>/dev/null")
    if vid_devs and "No such" not in vid_devs:
        r.camera_video_devices = [d.strip() for d in vid_devs.splitlines() if d.strip()]

    cam_count_prop = _prop(r.all_props, "ro.camera.cnt", "camera.cnt")
    if not r.camera_ids and cam_count_prop:
        r.camera_details["prop_count"] = cam_count_prop

    # Populate human-readable camera aliases
    facing_map = {v: k for k, v in r.camera_details.items()}
    for cid, facing in r.camera_details.items():
        if "back" in facing.lower() or "rear" in facing.lower():
            r.rear_camera = f"Camera {cid}"
        elif "front" in facing.lower():
            r.front_camera = f"Camera {cid}"
    r.camera_info = f"{len(r.camera_ids)} camera(s): " + ", ".join(
        f"id={cid}({v})" for cid, v in r.camera_details.items()
    ) if r.camera_ids else ""
    r.log.append(f"  Camera: {len(r.camera_ids)} cameras, /dev/video devices={len(r.camera_video_devices)}")

    # ------------------------------------------------------------------
    # 16. Sensors
    # ------------------------------------------------------------------
    _cb(0.56, "Reading sensor info...")
    r.sensors_raw = _shell_raw("dumpsys sensorservice", timeout=15)
    r.sensors = _parse_sensors(r.sensors_raw)
    r.sensors_list = [s.name for s in r.sensors if hasattr(s, "name")]
    r.log.append(f"  Sensors: {len(r.sensors)} detected")

    # ------------------------------------------------------------------
    # 17. Audio
    # ------------------------------------------------------------------
    _cb(0.60, "Reading audio info...")
    r.audio_raw = _shell_raw(
        "dumpsys audio | grep -iE 'stream|device|speaker|mic|output|input'",
        timeout=10,
    )
    r.audio_policy_raw = _shell_raw("dumpsys media.audio_policy | head -100", timeout=10)

    for line in (r.audio_raw + "\n" + r.audio_policy_raw).splitlines():
        low = line.lower().strip()
        if ("output" in low or "speaker" in low) and low not in r.audio_output_devices:
            r.audio_output_devices.append(line.strip()[:150])
        elif ("input" in low or "mic" in low) and low not in r.audio_input_devices:
            r.audio_input_devices.append(line.strip()[:150])
        elif "stream" in low:
            r.audio_streams.append(line.strip()[:150])

    r.audio_output_devices = r.audio_output_devices[:30]
    r.audio_input_devices = r.audio_input_devices[:30]
    r.audio_streams = r.audio_streams[:30]
    r.log.append(f"  Audio: {len(r.audio_output_devices)} outputs, "
                 f"{len(r.audio_input_devices)} inputs")

    # ------------------------------------------------------------------
    # 18. Fingerprint
    # ------------------------------------------------------------------
    _cb(0.64, "Reading fingerprint info...")
    r.fingerprint_raw = _shell_raw("dumpsys fingerprint", timeout=10)
    if "isHardwareDetected=true" in r.fingerprint_raw:
        r.fingerprint_hardware_detected = True
    elif "hasEnrolledFingerprints" in r.fingerprint_raw:
        r.fingerprint_hardware_detected = True
    enrolled_m = re.search(r"numFingerprints=(\d+)", r.fingerprint_raw)
    if enrolled_m:
        r.fingerprint_enrolled_count = _safe_int(enrolled_m.group(1))
    r.fingerprint_status = "available" if r.fingerprint_hardware_detected else "not available"
    r.log.append(f"  Fingerprint: hw={r.fingerprint_hardware_detected}, "
                 f"enrolled={r.fingerprint_enrolled_count}")

    # ------------------------------------------------------------------
    # 19. NFC
    # ------------------------------------------------------------------
    _cb(0.67, "Reading NFC info...")
    r.nfc_raw = _shell_raw("dumpsys nfc", timeout=10)
    if "mState=on" in r.nfc_raw.lower() or "enabled" in r.nfc_raw.lower():
        r.nfc_enabled = True
    elif "mState=off" in r.nfc_raw.lower() or "disabled" in r.nfc_raw.lower():
        r.nfc_enabled = False
    r.log.append(f"  NFC: {r.nfc_enabled}")

    # ------------------------------------------------------------------
    # 20. GPS / Location
    # ------------------------------------------------------------------
    _cb(0.70, "Reading GPS/location info...")
    r.gps_providers = _shell_raw("settings get secure location_providers_allowed")
    r.location_raw = _shell_raw("dumpsys location | head -60", timeout=10)
    r.log.append(f"  GPS providers: {r.gps_providers}")

    # ------------------------------------------------------------------
    # 21. Thermal
    # ------------------------------------------------------------------
    _cb(0.73, "Reading thermal info...")
    r.thermal_service_raw = _shell_raw("dumpsys thermalservice", timeout=10)

    for i in range(30):
        tz_type = _shell_raw(f"cat /sys/class/thermal/thermal_zone{i}/type 2>/dev/null")
        tz_temp = _shell_raw(f"cat /sys/class/thermal/thermal_zone{i}/temp 2>/dev/null")
        if not tz_type and not tz_temp:
            break
        if tz_type and "No such" in tz_type:
            break
        if tz_temp:
            t = _safe_int(tz_temp)
            if t > 1000:
                t = t // 1000
            elif t > 200:
                t = t // 10
            r.thermal_zones.append(ThermalZone(
                name=tz_type.strip() if tz_type else f"zone{i}",
                temp_c=float(t),
            ))

    if not r.thermal_zones and r.thermal_service_raw:
        # Parse Android thermalservice format:
        # Temperature{mValue=36.695, mType=0, mName=CPU, mStatus=0}
        # IMPORTANT: Use "Current temperatures from HAL" section, NOT "Cached temperatures"
        # Cached temps can be stale/old, current temps are real-time

        thermal_text = r.thermal_service_raw
        # Prefer current readings over cached
        current_section = ""
        if "Current temperatures from HAL:" in thermal_text:
            current_section = thermal_text.split("Current temperatures from HAL:")[-1]
            # Stop at next section
            for marker in ["Current cooling devices", "Temperature static thresholds"]:
                if marker in current_section:
                    current_section = current_section.split(marker)[0]
        # Use current section if available, otherwise full text
        parse_text = current_section if current_section.strip() else thermal_text

        for m in re.finditer(
            r"Temperature\{mValue[=:]\s*([\d.]+).*?mType[=:]\s*(\d+)(?:.*?mName[=:]\s*(\w+))?",
            parse_text, re.DOTALL
        ):
            t = _safe_float(m.group(1))
            mtype = m.group(2)
            mname = m.group(3) if m.group(3) else ""

            # Map mType to component name
            type_names = {
                "0": "CPU", "1": "GPU", "2": "BATTERY", "3": "SKIN",
                "4": "Skin", "5": "POWER_AMPLIFIER", "9": "NPU", "10": "BCL",
                "13": "SOC",
            }
            name = mname or type_names.get(mtype, f"type_{mtype}")

            if 0 < t < 120:
                r.thermal_zones.append(ThermalZone(name=name, temp_c=t))

        # Fallback: simple regex if no Temperature{ entries found
        if not r.thermal_zones:
            for m in re.finditer(r"(\w[\w\s-]+\w)\s*[:=]\s*([\d.]+)\s*(?:C|mC)", r.thermal_service_raw):
                t = _safe_float(m.group(2))
                if t > 200:
                    t /= 1000
                if 0 < t < 120:
                    r.thermal_zones.append(ThermalZone(name=m.group(1).strip(), temp_c=t))

    r.log.append(f"  Thermal: {len(r.thermal_zones)} zones")

    # ------------------------------------------------------------------
    # 22. USB
    # ------------------------------------------------------------------
    _cb(0.76, "Reading USB info...")
    r.usb_config = _prop(r.all_props, "sys.usb.config", "persist.sys.usb.config")
    r.usb_data_role = _shell_raw("cat /sys/class/typec/port0/data_role 2>/dev/null")
    r.usb_power_role = _shell_raw("cat /sys/class/typec/port0/power_role 2>/dev/null")
    r.log.append(f"  USB: config={r.usb_config}, data_role={r.usb_data_role}")

    # ------------------------------------------------------------------
    # 23. Logcat analysis (critical for no-root hardware info)
    # ------------------------------------------------------------------
    _cb(0.80, "Reading logcat (last 5000 lines from main+system+crash)...")
    logcat_raw = _shell_raw(
        "logcat -d -b main -b system -b crash -t 5000",
        timeout=30,
    )
    if logcat_raw and len(logcat_raw) > 50:
        _parse_logcat(logcat_raw, r)
        r.log.append(f"  Logcat: {r.logcat_raw_lines} lines analysed")
        r.log.append(f"    battery={len(r.logcat_battery_events)}, "
                     f"fingerprint={len(r.logcat_fingerprint_events)}, "
                     f"display={len(r.logcat_display_events)}, "
                     f"touch={len(r.logcat_touch_events)}, "
                     f"audio={len(r.logcat_audio_events)}, "
                     f"camera={len(r.logcat_camera_events)}, "
                     f"wifi={len(r.logcat_wifi_events)}, "
                     f"bt={len(r.logcat_bluetooth_events)}, "
                     f"modem={len(r.logcat_modem_events)}, "
                     f"sensors={len(r.logcat_sensors_events)}, "
                     f"crashes={len(r.logcat_crash_events)}, "
                     f"errors={len(r.logcat_errors)}")
    else:
        r.log.append("  Logcat: could not read or empty")

    # ------------------------------------------------------------------
    # 23b. Targeted hardware driver logcat grep
    # ------------------------------------------------------------------
    _cb(0.85, "Reading hardware driver logs (display/touch/camera/thermal)...")

    hw_grep_keywords = (
        "display|dsi|lcm|panel|backlight|disp|drm|"
        "touch|tp|fts|goodix|ili|synaptics|focaltech|novatek|himax|"
        "camera|imgsensor|ois|eeprom|seninf|"
        "thermal|overheat|throttle|"
        "fingerprint|fpc|egis|goodix_fp|"
        "aw882xx|tfa98xx|smartpa|audio|codec|ALSA|ACCDET|"
        "wlan|wmt|conninfra|wifi|"
        "btif|btmtk|bluetooth|"
        "ccci|modem|md_init|"
        "charger|charging|CHG|PMIC|mt6370|mt6360|bq25|sgm|"
        "sensor|accel|gyro|proximity|alsps|"
        "nfc|gps|gnss|"
        "usb|typec|otg"
    )

    hw_driver_raw = _shell_raw(
        f'logcat -d | grep -iE "{hw_grep_keywords}"',
        timeout=30,
    )

    if hw_driver_raw and len(hw_driver_raw) > 10:
        hw_lines = hw_driver_raw.splitlines()
        r.logcat_hw_driver_lines = [l.strip()[:250] for l in hw_lines if len(l.strip()) > 10][:500]
        r.log.append(f"  HW Driver Logs: {len(r.logcat_hw_driver_lines)} lines captured")

        # Extract specific IC/driver names from these lines
        hw_text = hw_driver_raw.lower()
        detected_ics = set()

        # Display panel/driver
        for pat in [r"(nt\d{5}\w*)", r"(ili\d{4}\w*)", r"(hx\d{4}\w*)", r"(ft\d{4}\w*)",
                    r"(td4\d{3}\w*)", r"(icn\d{4}\w*)", r"(r6\d{4}\w*)", r"(s6e\w+)"]:
            for m in re.finditer(pat, hw_text):
                detected_ics.add(f"Display: {m.group(1).upper()}")

        # Touch IC
        for pat in [r"(goodix[\w-]*)", r"(focaltech[\w-]*)", r"(fts\d\w*)", r"(ili\d{4}\w*)",
                    r"(synaptics[\w-]*)", r"(himax[\w-]*)", r"(novatek[\w-]*)", r"(nvt[\w-]*)"]:
            for m in re.finditer(pat, hw_text):
                detected_ics.add(f"Touch: {m.group(1)}")

        # Camera sensor
        for pat in [r"(imx\d{3}\w*)", r"(ov\d{4,5}\w*)", r"(s5k\w+)", r"(hi\d{3,4}\w*)",
                    r"(gc\d{4}\w*)", r"(ov\d{2}[a-z]\d\w*)"]:
            for m in re.finditer(pat, hw_text):
                detected_ics.add(f"Camera: {m.group(1).upper()}")

        # Audio IC
        for pat in [r"(aw\d{4,5}\w*)", r"(tfa\d{4,5}\w*)", r"(mt\d{4}[\w-]*codec)",
                    r"(wcd\d{4}\w*)", r"(alc\d{4}\w*)"]:
            for m in re.finditer(pat, hw_text):
                detected_ics.add(f"Audio: {m.group(1).upper()}")

        # Fingerprint
        for pat in [r"(fpc\d{4}\w*)", r"(goodix[\w]*fp\w*)", r"(egis[\w-]*)", r"(silead[\w-]*)"]:
            for m in re.finditer(pat, hw_text):
                detected_ics.add(f"Fingerprint: {m.group(1)}")

        # Charging IC
        for pat in [r"(bq\d{5}\w*)", r"(mt6370\w*)", r"(mt6360\w*)", r"(sgm\d{4}\w*)",
                    r"(eta\d{4}\w*)", r"(rt\d{4}\w*)"]:
            for m in re.finditer(pat, hw_text):
                detected_ics.add(f"Charging: {m.group(1).upper()}")

        # WiFi/BT
        for pat in [r"(mt76\d{2}\w*)", r"(wcn\d{4}\w*)", r"(qca\d{4}\w*)"]:
            for m in re.finditer(pat, hw_text):
                detected_ics.add(f"WiFi/BT: {m.group(1).upper()}")

        if detected_ics:
            r.log.append(f"  Detected IC/Driver Names:")
            for ic in sorted(detected_ics):
                r.log.append(f"    → {ic}")
                # Populate dmesg_components dict: category → {driver: ..., loaded: True}
                parts = ic.split(":", 1)
                if len(parts) == 2:
                    cat = parts[0].strip().lower()
                    drv = parts[1].strip()
                    r.dmesg_components[cat] = {"driver": drv, "loaded": True}
    else:
        r.log.append("  HW Driver Logs: no data from grep")

    # ------------------------------------------------------------------
    # 24. Diagnosis
    # ------------------------------------------------------------------
    _cb(0.90, "Running health diagnosis...")
    r.diagnoses = _run_diagnosis(r)
    r.log.append(f"  Diagnosis complete: {len(r.diagnoses)} components checked")
    for d in r.diagnoses:
        r.log.append(f"    [{d.status}] {d.component}: {d.summary}")
        # Populate hw_status dict from diagnosis results
        r.hw_status[d.component] = {
            "status": d.status,
            "summary": d.summary,
            "confidence": getattr(d, "confidence", 0),
        }

    _cb(1.0, "Detection complete!")
    r.log.append(f"[DONE] ADB detection complete: {r.brand} {r.model}")
    return r


# ---------------------------------------------------------------------------
#  Health diagnosis engine
# ---------------------------------------------------------------------------

def _run_diagnosis(r: ADBDetectionResult) -> List[ComponentDiagnosis]:
    """Analyse all collected data and produce a diagnosis per component."""
    diags: List[ComponentDiagnosis] = []

    # --- Battery ---
    bd = ComponentDiagnosis(component="Battery")
    if r.battery_level < 0:
        bd.status = "UNKNOWN"
        bd.summary = "Could not read battery info"
    else:
        issues = []
        # Wear
        if r.battery_wear_pct >= 0:
            if r.battery_wear_pct > 30:
                issues.append(f"Battery worn {r.battery_wear_pct}% (>30% is bad)")
                bd.causes.append("Normal ageing / excessive charge cycles")
                bd.fixes.append("Replace battery")
                bd.parts_needed.append(f"OEM battery for {r.brand} {r.model}")
            elif r.battery_wear_pct > 15:
                issues.append(f"Battery wear {r.battery_wear_pct}% (moderate)")
        # Cycle count
        if r.battery_cycle_count > 0:
            if r.battery_cycle_count > 800:
                issues.append(f"High cycle count: {r.battery_cycle_count}")
                bd.causes.append("Heavy usage over time")
            elif r.battery_cycle_count > 500:
                issues.append(f"Moderate cycle count: {r.battery_cycle_count}")
        # Temperature
        if r.battery_temp_c > 45:
            issues.append(f"Battery overheating: {r.battery_temp_c}C")
            bd.causes.append("Faulty battery, heavy load, or charging IC issue")
            bd.checks.append("Check if phone is hot to touch near battery")
            bd.checks.append("Check charging IC and battery connector")
            bd.fixes.append("Replace battery; if persists, check charging IC")
        elif r.battery_temp_c > 38:
            issues.append(f"Battery warm: {r.battery_temp_c}C")
        # Health code
        if r.battery_health_code not in (2, -1):
            issues.append(f"Battery health: {r.battery_health}")
            bd.fixes.append("Replace battery")
            bd.parts_needed.append(f"OEM battery for {r.brand} {r.model}")
        # Voltage
        if 0 < r.battery_voltage_mv < 3400 and r.battery_status != "Charging":
            issues.append(f"Low voltage: {r.battery_voltage_mv}mV")
            bd.causes.append("Deeply discharged or degraded cell")

        if issues:
            bd.status = "FAULT" if any("overheating" in i.lower() or "worn" in i.lower()
                                       or r.battery_health_code not in (2, -1, 1) for i in issues) else "WARNING"
            bd.problems = issues
            bd.summary = "; ".join(issues)
        else:
            bd.status = "OK"
            bd.summary = (f"{r.battery_level}%, health={r.battery_health}, "
                          f"temp={r.battery_temp_c}C, wear={r.battery_wear_pct}%")
    diags.append(bd)

    # --- CPU ---
    cd = ComponentDiagnosis(component="CPU / Processor")
    if r.cpu_cores_count == 0:
        cd.status = "UNKNOWN"
        cd.summary = "Could not read CPU info"
    else:
        issues = []
        readable_cores = [c for c in r.cpu_cores if c.max_freq_mhz > 0]
        throttled_cores = 0
        for c in readable_cores:
            if c.cur_freq_mhz > 0:
                ratio = c.cur_freq_mhz / c.max_freq_mhz
                if ratio < 0.4:
                    throttled_cores += 1
        if throttled_cores > 0 and throttled_cores >= len(readable_cores) * 0.5:
            issues.append(f"{throttled_cores}/{len(readable_cores)} cores heavily throttled")
            cd.causes.append("Thermal throttling due to overheating or thermal paste degradation")
            cd.checks.append("Check thermal zones for high temps")
            cd.fixes.append("Clean internals, reapply thermal paste/pad")

        # NOTE: On non-rooted phones, CPU freq is often not readable.
        # This is a PERMISSION issue, NOT a hardware fault.
        # Only flag as issue if we could read SOME cores but not others.
        unreadable_cores = sum(1 for c in r.cpu_cores if c.max_freq_mhz == 0)
        if unreadable_cores > 0 and len(readable_cores) > 0:
            # Some readable, some not — might be real issue
            issues.append(f"{unreadable_cores} core(s) not responding (others readable)")
        # If ALL cores unreadable — it's just permission, not a fault
        # Don't add as issue

        if issues:
            cd.status = "WARNING"
            cd.problems = issues
            cd.summary = "; ".join(issues)
        else:
            max_freq = max((c.max_freq_mhz for c in r.cpu_cores), default=0)
            cd.status = "OK"
            freq_str = f", max {max_freq}MHz" if max_freq > 0 else " (freq not readable without root)"
            cd.summary = f"{r.chipset or r.cpu_hardware}, {r.cpu_cores_count} cores{freq_str}"
    diags.append(cd)

    # --- RAM ---
    rd = ComponentDiagnosis(component="RAM / Memory")
    if r.ram_total_kb == 0:
        rd.status = "UNKNOWN"
        rd.summary = "Could not read memory info"
    else:
        total_mb = r.ram_total_kb // 1024
        avail_mb = r.ram_available_kb // 1024
        pct_used = ((r.ram_total_kb - r.ram_available_kb) / r.ram_total_kb * 100) if r.ram_total_kb > 0 else 0
        issues = []
        if avail_mb < 300:
            issues.append(f"Critically low free RAM: {avail_mb}MB")
            rd.causes.append("Too many apps running or RAM-hungry malware")
            rd.fixes.append("Factory reset if issue persists, check for malware")
        elif avail_mb < 500:
            issues.append(f"Low available RAM: {avail_mb}MB")
            rd.checks.append("Check running processes for bloatware")

        if total_mb < 1800:
            issues.append(f"Very low total RAM: {total_mb}MB - device may be slow")

        if issues:
            rd.status = "WARNING" if avail_mb >= 300 else "FAULT"
            rd.problems = issues
            rd.summary = "; ".join(issues)
        else:
            rd.status = "OK"
            rd.summary = f"{total_mb}MB total, {avail_mb}MB available ({pct_used:.0f}% used)"
    diags.append(rd)

    # --- Storage ---
    sd = ComponentDiagnosis(component="Storage")
    if r.storage_total_kb == 0:
        sd.status = "UNKNOWN"
        sd.summary = "Could not read storage info"
    else:
        total_gb = r.storage_total_kb / (1024 * 1024)
        free_gb = r.storage_free_kb / (1024 * 1024)
        pct_used = ((r.storage_total_kb - r.storage_free_kb) / r.storage_total_kb * 100) if r.storage_total_kb > 0 else 0
        issues = []
        if free_gb < 1:
            issues.append(f"Critically low storage: {free_gb:.1f}GB free")
            sd.causes.append("Storage full - apps, photos, cache")
            sd.fixes.append("Clear cache, delete unused apps/files")
        elif pct_used > 90:
            issues.append(f"Storage almost full: {pct_used:.0f}% used ({free_gb:.1f}GB free)")
            sd.checks.append("Check large files and app cache")

        # Storage health from NAND wear indicators
        if r.storage_health_pct >= 0:
            if r.storage_health_pct <= 10:
                issues.append(f"NAND critically worn: {r.storage_health_pct}% health remaining")
                sd.causes.append("Flash storage NAND cells near end of life")
                sd.fixes.append("Replace storage IC / motherboard - imminent failure risk")
            elif r.storage_health_pct <= 30:
                issues.append(f"NAND significantly worn: {r.storage_health_pct}% health remaining")
                sd.causes.append("Heavy write usage has degraded flash storage")
                sd.fixes.append("Plan storage IC replacement; backup all data")

        # Pre-EOL indicator
        _pre_eol_diag_map = {"0x02": "Warning", "0x03": "Urgent", "2": "Warning", "3": "Urgent"}
        eol_label = _pre_eol_diag_map.get(r.storage_pre_eol, "")
        if eol_label == "Urgent":
            issues.append(f"Storage pre-EOL status: URGENT - replacement needed")
            sd.causes.append("Storage firmware reports end-of-life is imminent")
            sd.fixes.append("Replace storage IC immediately; backup data now")
        elif eol_label == "Warning":
            issues.append(f"Storage pre-EOL status: WARNING - approaching end of life")
            sd.checks.append("Monitor storage health; plan replacement")

        if issues:
            # Escalate to FAULT if NAND health is critical or EOL urgent
            if r.storage_health_pct >= 0 and r.storage_health_pct <= 10:
                sd.status = "FAULT"
            elif eol_label == "Urgent":
                sd.status = "FAULT"
            else:
                sd.status = "WARNING" if free_gb >= 1 else "FAULT"
            sd.problems = issues
            sd.summary = "; ".join(issues)
        else:
            health_str = f", health={r.storage_health_pct}%" if r.storage_health_pct >= 0 else ""
            sd.status = "OK"
            sd.summary = f"{total_gb:.0f}GB total, {free_gb:.1f}GB free, {r.storage_type} {r.storage_model}{health_str}"
    diags.append(sd)

    # --- Display ---
    dd = ComponentDiagnosis(component="Display")
    if not r.display_resolution:
        dd.status = "UNKNOWN"
        dd.summary = "Could not read display info"
    else:
        # ONLY flag as error if there are REAL panel/DSI/backlight failures
        # NOT normal HWC operations, buffer allocations, mode switches, etc.
        real_display_errors = []
        for e in r.logcat_display_events:
            e_lower = e.lower()
            # Must be a REAL panel/hardware error — very specific patterns only
            is_real = bool(re.search(
                r"panel.*not.*found|panel.*dead|panel.*no.*response|"
                r"dsi.*transfer.*fail|dsi.*timeout|dsi.*link.*fail|"
                r"lcm.*fail|lcm.*not.*found|lcm.*error|"
                r"backlight.*fail|backlight.*error|backlight.*short|"
                r"esd.*detected|esd.*recovery|"
                r"display.*blank.*fail|fb.*error|framebuffer.*fail|"
                r"mipi.*lane.*error|mipi.*phy.*fail",
                e_lower
            ))
            if is_real:
                real_display_errors.append(e)

        if real_display_errors:
            dd.status = "WARNING"
            dd.problems = [f"{len(real_display_errors)} display hardware errors"]
            dd.summary = f"{len(real_display_errors)} real panel/DSI errors detected"
            dd.causes.append("Panel driver error, loose FPC connector, or damaged panel")
            dd.fixes.append("Reseat display connector; replace display assembly if needed")
        else:
            dd.status = "OK"
            dd.summary = f"{r.display_resolution}, {r.display_density}dpi, {r.display_refresh_rate or 'default'}Hz"
    diags.append(dd)

    # --- Touch ---
    td = ComponentDiagnosis(component="Touchscreen")
    # ONLY flag if there are REAL touch IC hardware errors
    # NOT "notifyAppState error = NULL" (that's normal), NOT Telephony, NOT system timing
    touch_errors = []
    for e in r.logcat_touch_events:
        e_lower = e.lower()
        # Must be a REAL touch IC failure — very specific
        is_real = bool(re.search(
            r"goodix.*i2c.*error|goodix.*probe.*fail|goodix.*fw.*fail|goodix.*timeout|"
            r"focaltech.*i2c.*error|focaltech.*probe.*fail|fts.*fail|fts.*error|"
            r"synaptics.*i2c.*error|synaptics.*probe.*fail|"
            r"ili.*i2c.*error|ili.*probe.*fail|ilitek.*fail|"
            r"himax.*i2c.*error|himax.*probe.*fail|"
            r"novatek.*fail|nvt.*i2c.*error|"
            r"touch.*not.*respond|touch.*dead|tpd.*probe.*fail|"
            r"touch.*i2c.*error|touch.*fw.*corrupt",
            e_lower
        ))
        if is_real:
            touch_errors.append(e)

    if touch_errors:
        td.status = "WARNING"
        td.problems = [f"{len(touch_errors)} touch IC hardware errors"]
        td.summary = f"{len(touch_errors)} real touch IC errors (I2C/probe failures)"
        td.causes.append("Faulty touch IC, loose FPC connector, cracked digitizer")
        td.checks.append("Test touch in all screen areas")
        td.fixes.append("Reseat touch connector; replace digitizer if needed")
        td.parts_needed.append(f"Touch digitizer for {r.brand} {r.model}")
    else:
        td.status = "OK"
        td.summary = "Touch working normally"
    diags.append(td)

    # --- WiFi ---
    wd = ComponentDiagnosis(component="WiFi")
    wifi_state_lower = (r.wifi_state or "").lower()
    if r.wifi_mac and r.wifi_mac != "02:00:00:00:00:00":
        wd.status = "OK"
        wd.summary = f"MAC={r.wifi_mac}, IP={r.wifi_ip or 'none'}, state={r.wifi_state}"
    elif r.wifi_mac == "02:00:00:00:00:00":
        # Randomized MAC is normal on Android 10+
        wd.status = "OK"
        wd.summary = "WiFi present (MAC randomized — normal on Android 10+)"
    elif wifi_state_lower in ("stopped", "disabled"):
        # WiFi is just turned off — not a fault
        wd.status = "OK"
        wd.summary = f"WiFi OFF (user disabled) — turn on WiFi to fully test"
    elif wifi_state_lower == "running":
        wd.status = "OK"
        wd.summary = f"WiFi running, MAC not readable (privacy protection)"
    else:
        wd.status = "OK"
        wd.summary = f"WiFi status: {r.wifi_state or 'not readable'} — enable WiFi to fully test"
    diags.append(wd)

    # --- Bluetooth ---
    btd = ComponentDiagnosis(component="Bluetooth")
    if r.bt_mac and r.bt_mac != "null":
        btd.status = "OK"
        btd.summary = f"MAC={r.bt_mac}, state={r.bt_state}"
    else:
        btd.status = "UNKNOWN"
        btd.summary = "Bluetooth address not readable"
        btd.checks.append("Enable Bluetooth and retry")
    diags.append(btd)

    # --- SIM / Network ---
    nd = ComponentDiagnosis(component="SIM / Network")
    sim_upper = r.sim_state.upper()
    # Handle dual SIM: "LOADED,LOADED" or "READY,READY" etc.
    sim_states = [s.strip() for s in sim_upper.split(",")]
    any_loaded = any(s in ("READY", "LOADED") for s in sim_states)
    all_absent = all(s == "ABSENT" for s in sim_states)

    if any_loaded:
        nd.status = "OK"
        dual = f" (Dual SIM)" if len(sim_states) > 1 else ""
        nd.summary = (f"SIM={r.sim_state}{dual}, op={r.sim_operator}, "
                      f"net={r.network_type}, signal={r.signal_strength_dbm}")
    elif all_absent:
        nd.status = "WARNING"
        nd.summary = "No SIM card inserted"
        nd.checks.append("Insert SIM card to test telephony")
    elif not r.sim_state:
        nd.status = "UNKNOWN"
        nd.summary = "SIM state not readable"
    else:
        nd.status = "WARNING"
        nd.summary = f"SIM state: {r.sim_state}"
        nd.checks.append("Check SIM tray and card for damage")
        nd.checks.append("Try another SIM card")
        nd.causes.append("Dirty SIM contacts, damaged SIM slot, baseband issue")
        nd.fixes.append("Clean SIM contacts, try different SIM, check baseband version")
    if r.signal_strength_dbm:
        dbm_val = re.search(r"(-?\d+)", r.signal_strength_dbm)
        if dbm_val:
            dbm = int(dbm_val.group(1))
            if dbm < -110:
                nd.problems.append(f"Very weak signal: {dbm}dBm")
                nd.checks.append("Check antenna connections inside phone")
    diags.append(nd)

    # --- Camera ---
    cam_d = ComponentDiagnosis(component="Camera")
    if r.camera_ids:
        cam_d.status = "OK"
        cam_d.summary = f"{len(r.camera_ids)} camera(s) detected: IDs {', '.join(r.camera_ids)}"
    elif r.camera_video_devices:
        cam_d.status = "OK"
        cam_d.summary = f"{len(r.camera_video_devices)} video devices in /dev"
    else:
        cam_d.status = "UNKNOWN"
        cam_d.summary = "Camera info not accessible (may need app-level test)"
        cam_d.checks.append("Open camera app to verify cameras work")
        cam_d.checks.append("Check camera FPC connectors")
    diags.append(cam_d)

    # --- Sensors ---
    sen_d = ComponentDiagnosis(component="Sensors")
    if r.sensors:
        sen_d.status = "OK"
        sen_d.summary = f"{len(r.sensors)} sensors detected"
    else:
        sen_d.status = "UNKNOWN"
        sen_d.summary = "Could not read sensor list"
        sen_d.checks.append("Use a sensor test app to verify")
    diags.append(sen_d)

    # --- Audio ---
    aud_d = ComponentDiagnosis(component="Audio")
    # Filter REAL audio errors — exclude normal thread scheduling, permissions, etc.
    real_audio_errors = []
    for e in r.logcat_audio_events:
        e_lower = e.lower()
        has_real_error = bool(re.search(
            r"codec.*fail|codec.*error|speaker.*fail|mic.*fail|"
            r"aw882xx.*error|tfa98xx.*error|smartpa.*fail|"
            r"audio.*hal.*died|no.*audio.*output|"
            r"accdet.*error|headset.*detect.*fail",
            e_lower
        ))
        # Exclude normal/benign errors
        is_benign = any(fp in e_lower for fp in [
            "push2rtgroup", "function not implemented", "set_microphone_direction",
            "set_microphone_field", "createrecord uid", "tried to pass itself",
            "btaudiohw", "screen_state",
        ])
        if has_real_error and not is_benign:
            real_audio_errors.append(e)

    if real_audio_errors:
        aud_d.status = "WARNING"
        aud_d.problems = [f"{len(real_audio_errors)} real audio hardware errors"]
        aud_d.summary = f"{len(real_audio_errors)} audio IC/hardware errors detected"
        aud_d.causes.append("Faulty speaker/mic, loose connector, audio IC issue")
        aud_d.checks.append("Test speaker, earpiece, and microphone")
        aud_d.fixes.append("Check speaker/mic connectors; replace if hardware fault")
    elif r.audio_raw or r.logcat_audio_events:
        aud_d.status = "OK"
        aud_d.summary = "Audio system running normally"
    else:
        aud_d.status = "OK"
        aud_d.summary = "Audio info not fully accessible (normal without root)"
    diags.append(aud_d)

    # --- Fingerprint ---
    fp_d = ComponentDiagnosis(component="Fingerprint")
    # Filter real FP errors — exclude SELinux denials, permission issues
    real_fp_errors = []
    for e in r.logcat_fingerprint_events:
        e_lower = e.lower()
        has_real_error = bool(re.search(
            r"sensor.*not.*found|sensor.*fail|fpc.*error|goodix.*fail|"
            r"egis.*error|fingerprint.*hal.*died|calibration.*fail",
            e_lower
        ))
        is_benign = any(fp in e_lower for fp in [
            "selinux", "access denied", "permission", "adbd service",
            "isdeclared", "udfpslocalh", "biometricutils",
        ])
        if has_real_error and not is_benign:
            real_fp_errors.append(e)

    if r.fingerprint_hardware_detected:
        if real_fp_errors:
            fp_d.status = "WARNING"
            fp_d.problems = [f"{len(real_fp_errors)} fingerprint hardware errors"]
            fp_d.summary = f"Hardware detected but {len(real_fp_errors)} sensor errors"
            fp_d.causes.append("Dirty sensor, flex cable issue, sensor degradation")
            fp_d.checks.append("Clean fingerprint sensor, check FPC connector")
            fp_d.fixes.append("Clean sensor, reseat connector, replace if needed")
        else:
            fp_d.status = "OK"
            fp_d.summary = f"Fingerprint working (enrolled={r.fingerprint_enrolled_count})"
    elif r.fingerprint_raw or r.logcat_fingerprint_events:
        # Service exists, logcat shows activity — likely working
        fp_d.status = "OK"
        fp_d.summary = "Fingerprint service active (hardware status not directly readable)"
    else:
        fp_d.status = "OK"
        fp_d.summary = "No fingerprint hardware (may not be equipped)"
    diags.append(fp_d)

    # Add SIM details to diagnosis
    if any_loaded:
        sim_details = []
        operators = [s.strip() for s in r.sim_operator.split(",")] if r.sim_operator else []
        net_types = [s.strip() for s in r.network_type.split(",")] if r.network_type else []
        countries = [s.strip() for s in r.sim_country.split(",")] if r.sim_country else []
        numerics = [s.strip() for s in r.sim_operator_numeric.split(",")] if r.sim_operator_numeric else []

        for i, state in enumerate(sim_states):
            slot = f"SIM {i+1}"
            op = operators[i] if i < len(operators) else "Unknown"
            net = net_types[i] if i < len(net_types) else "Unknown"
            country = countries[i] if i < len(countries) else ""
            numeric = numerics[i] if i < len(numerics) else ""

            if state in ("READY", "LOADED"):
                sim_details.append(f"{slot}: {op} ({net}) [{country}] MCC/MNC={numeric}")
            elif state == "ABSENT":
                sim_details.append(f"{slot}: No SIM")
            else:
                sim_details.append(f"{slot}: {state}")

        nd.problems = sim_details  # Not really problems, reusing for details

    # --- NFC ---
    nfc_d = ComponentDiagnosis(component="NFC")
    if r.nfc_enabled is True:
        nfc_d.status = "OK"
        nfc_d.summary = "NFC enabled"
    elif r.nfc_enabled is False:
        nfc_d.status = "OK"
        nfc_d.summary = "NFC present but disabled"
    else:
        nfc_d.status = "OK"
        nfc_d.summary = "NFC not present or not accessible"
    diags.append(nfc_d)

    # --- GPS ---
    gps_d = ComponentDiagnosis(component="GPS / Location")
    if r.gps_providers and "gps" in r.gps_providers.lower():
        gps_d.status = "OK"
        gps_d.summary = f"GPS enabled, providers: {r.gps_providers}"
    elif r.gps_providers and r.gps_providers.lower() not in ("null", "", "none"):
        gps_d.status = "OK"
        gps_d.summary = f"Location on but GPS not primary: {r.gps_providers}"
    else:
        # GPS/Location turned off — this is user setting, NOT a hardware fault
        gps_d.status = "OK"
        gps_d.summary = "GPS/Location OFF (user setting — enable to test GPS hardware)"
    diags.append(gps_d)

    # --- Thermal ---
    therm_d = ComponentDiagnosis(component="Thermal")
    if r.thermal_zones:
        # REALISTIC thresholds — phones get warm during charging/gaming, that's NORMAL
        # Only flag as FAULT when temperatures are genuinely dangerous
        is_charging = r.battery_status and "charging" in r.battery_status.lower()
        real_hot = []
        for z in r.thermal_zones:
            name_lower = z.name.lower()
            # CPU/SOC/NPU — up to 90°C is normal under heavy load
            if any(k in name_lower for k in ["cpu", "soc", "npu", "bcl"]):
                if z.temp_c > 95:  # >95°C = real danger
                    real_hot.append(z)
            # Battery — >50°C is concerning (>55°C danger)
            elif "batter" in name_lower:
                if z.temp_c > 55:
                    real_hot.append(z)
            # Skin — while charging 50°C is warm but OK. >55°C without charging = issue
            elif "skin" in name_lower:
                threshold = 55 if is_charging else 50
                if z.temp_c > threshold:
                    real_hot.append(z)
            # GPU — up to 90°C under load is normal
            elif "gpu" in name_lower:
                if z.temp_c > 95:
                    real_hot.append(z)
            # Power Amplifier — can get hot during calls/data
            elif "power" in name_lower or "pa" in name_lower:
                if z.temp_c > 65:
                    real_hot.append(z)
            # USB Port — >65°C while charging = check cable/adapter
            elif "usb" in name_lower:
                if z.temp_c > 65:
                    real_hot.append(z)
            # Default — high threshold to avoid false positives
            else:
                if z.temp_c > 90:
                    real_hot.append(z)

        warm_zones = [z for z in r.thermal_zones
                      if 45 < z.temp_c <= 70
                      and z.name.lower() not in ["cpu", "soc", "npu", "gpu"]]

        # Build summary
        all_temps = [(z.name, z.temp_c) for z in r.thermal_zones]
        temp_str = ", ".join(f"{n}={t}°C" for n, t in all_temps[:8])

        if real_hot:
            therm_d.status = "FAULT"
            therm_d.problems = [f"{z.name}: {z.temp_c}°C (DANGER)" for z in real_hot]
            therm_d.summary = f"OVERHEATING: {', '.join(f'{z.name}={z.temp_c}°C' for z in real_hot)}"
            therm_d.causes.append("Short circuit, degraded thermal paste, heavy load, blocked ventilation")
            therm_d.checks.append("Open phone and check which area is hot")
            therm_d.checks.append("Use thermal camera to find hot spot")
            therm_d.fixes.append("Replace thermal paste/pad on CPU")
            therm_d.fixes.append("Check for short circuit near hot area")
        elif warm_zones:
            therm_d.status = "WARNING"
            therm_d.problems = [f"{z.name}: {z.temp_c}°C (warm)" for z in warm_zones]
            therm_d.summary = f"Slightly warm: {temp_str}"
        else:
            max_t = max(z.temp_c for z in r.thermal_zones) if r.thermal_zones else 0
            therm_d.status = "OK"
            therm_d.summary = f"All temps normal. {temp_str}"
    else:
        therm_d.status = "UNKNOWN"
        therm_d.summary = "Could not read thermal zones"
    diags.append(therm_d)

    # --- USB ---
    usb_d = ComponentDiagnosis(component="USB")
    usb_d.status = "OK"
    usb_d.summary = f"ADB connected, config={r.usb_config}, data_role={r.usb_data_role or 'N/A'}"
    diags.append(usb_d)

    # --- Crashes ---
    crash_d = ComponentDiagnosis(component="System Stability")
    # Filter REAL crashes — exclude app updates (dex2oat), BLE scans, etc.
    real_crashes = []
    for e in r.logcat_crash_events:
        e_lower = e.lower()
        is_real_crash = bool(re.search(
            r"\bFATAL\b|\bANR\b.*system|tombstone|native crash|kernel panic|"
            r"SIGSEGV|SIGABRT|system_server.*died|zygote.*died",
            e, re.IGNORECASE
        ))
        is_false = any(fp in e_lower for fp in [
            "dex2oat", "artd", "artservice", "dexopt",  # App optimization, not crash
            "ble_scan", "appscanstats",  # BLE scan results
            "update.*package", "chrome",  # App updates
        ])
        if is_real_crash and not is_false:
            real_crashes.append(e)

    if len(real_crashes) > 5:
        crash_d.status = "WARNING"
        crash_d.problems = [f"{len(real_crashes)} real system crash/ANR events"]
        crash_d.summary = f"{len(real_crashes)} system crashes detected"
        crash_d.checks.append("Check which system processes are crashing")
        crash_d.checks.append("May indicate hardware issue if persistent")
    elif real_crashes:
        crash_d.status = "OK"
        crash_d.summary = f"Minor: {len(real_crashes)} crash event(s) — likely app-level, not hardware"
    else:
        crash_d.status = "OK"
        crash_d.summary = "System stable — no real crashes detected"
    diags.append(crash_d)

    return diags


# ---------------------------------------------------------------------------
#  Full text report generator
# ---------------------------------------------------------------------------

def generate_full_report(result: ADBDetectionResult) -> str:
    """
    Generate a complete text report suitable for display and copy/paste.
    Covers ALL detected data with headers, tables, and diagnosis.
    """
    W = 72
    lines: List[str] = []

    def header(title: str) -> None:
        lines.append("")
        lines.append("=" * W)
        lines.append(f"  {title.upper()}")
        lines.append("=" * W)

    def subheader(title: str) -> None:
        lines.append("")
        lines.append(f"--- {title} ---")

    def kv(key: str, value: Any, indent: int = 2) -> None:
        prefix = " " * indent
        lines.append(f"{prefix}{key:.<36s} {value}")

    def kv_if(key: str, value: Any, indent: int = 2) -> None:
        if value and str(value) not in ("", "0", "-1", "-1.0", "0.0", "None"):
            kv(key, value, indent)

    # Title
    lines.append("=" * W)
    lines.append("  MOBILE HARDWARE DIAGNOSTIC REPORT")
    lines.append(f"  {result.brand} {result.model}")
    lines.append(f"  Serial: {result.serial_number}")
    lines.append("=" * W)

    # ---- DIAGNOSIS SUMMARY ----
    header("DIAGNOSIS SUMMARY")
    faults = [d for d in result.diagnoses if d.status == "FAULT"]
    warnings = [d for d in result.diagnoses if d.status == "WARNING"]
    oks = [d for d in result.diagnoses if d.status == "OK"]
    unknowns = [d for d in result.diagnoses if d.status == "UNKNOWN"]

    lines.append(f"  FAULT: {len(faults)}  |  WARNING: {len(warnings)}  |  "
                 f"OK: {len(oks)}  |  UNKNOWN: {len(unknowns)}")
    lines.append("")

    for d in result.diagnoses:
        icon = {"OK": "[OK]", "WARNING": "[!!]", "FAULT": "[XX]", "UNKNOWN": "[??]"}.get(d.status, "[??]")
        lines.append(f"  {icon} {d.component:.<30s} {d.summary}")

    problem_diags = [d for d in result.diagnoses if d.status in ("FAULT", "WARNING")]
    if problem_diags:
        subheader("DETAILED ISSUES")
        for d in problem_diags:
            lines.append(f"")
            lines.append(f"  >> {d.component} [{d.status}]")
            if d.problems:
                for p in d.problems:
                    lines.append(f"     Problem:  {p}")
            if d.causes:
                for c in d.causes:
                    lines.append(f"     Cause:    {c}")
            if d.checks:
                for c in d.checks:
                    lines.append(f"     Check:    {c}")
            if d.fixes:
                for f in d.fixes:
                    lines.append(f"     Fix:      {f}")
            if d.parts_needed:
                for p in d.parts_needed:
                    lines.append(f"     Part:     {p}")

    # ---- DEVICE IDENTITY ----
    header("DEVICE IDENTITY")
    kv("Brand", result.brand)
    kv("Model", result.model)
    kv("Device Name", result.device_name)
    kv("Manufacturer", result.manufacturer)
    kv("Serial Number", result.serial_number)
    kv_if("IMEI", result.imei)
    kv_if("IMEI2", result.imei2)
    kv("Android Version", result.android_version)
    kv("SDK / API Level", result.sdk_version)
    kv_if("First API Level", result.first_api_level)
    kv("Build Number", result.build_number)
    kv_if("Build Fingerprint", result.build_fingerprint)
    kv_if("Build Type", result.build_type)
    kv_if("Build Date", result.build_date)
    kv("Security Patch", result.security_patch)
    kv("Baseband Version", result.baseband_version)
    kv("Kernel", result.kernel_version)
    kv_if("Bootloader", result.bootloader)
    kv("Hardware", result.hardware)
    kv_if("Board", result.board)
    kv("Platform / Chipset", result.chipset)

    # ---- CPU ----
    header("CPU / PROCESSOR")
    kv("Chipset", result.chipset or result.cpu_hardware)
    kv("CPU ABI", result.cpu_abi)
    kv("Cores", result.cpu_cores_count)
    if result.cpu_cores:
        subheader("Per-core Frequencies")
        lines.append(f"  {'Core':<8} {'Max MHz':>10} {'Cur MHz':>10} {'Load %':>8}")
        lines.append(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*8}")
        for c in result.cpu_cores:
            load = ""
            if c.max_freq_mhz > 0 and c.cur_freq_mhz > 0:
                load = f"{c.cur_freq_mhz / c.max_freq_mhz * 100:.0f}%"
            lines.append(f"  core{c.core_id:<3} {c.max_freq_mhz:>10} {c.cur_freq_mhz:>10} {load:>8}")

    # ---- GPU ----
    header("GPU")
    kv_if("Vendor", result.gpu_vendor)
    kv_if("Renderer", result.gpu_renderer)
    kv_if("Version", result.gpu_version)

    # ---- RAM ----
    header("RAM / MEMORY")
    total_mb = result.ram_total_kb // 1024
    avail_mb = result.ram_available_kb // 1024
    kv("Total", f"{total_mb} MB ({total_mb // 1024} GB)")
    kv("Available", f"{avail_mb} MB")
    kv("Free", f"{result.ram_free_kb // 1024} MB")
    kv("Buffers", f"{result.ram_buffers_kb // 1024} MB")
    kv("Cached", f"{result.ram_cached_kb // 1024} MB")
    kv_if("Swap Total", f"{result.ram_swap_total_kb // 1024} MB")
    kv_if("Swap Free", f"{result.ram_swap_free_kb // 1024} MB")
    kv_if("RAM Type", result.ram_type)

    # ---- STORAGE ----
    header("STORAGE")
    total_gb = result.storage_total_kb / (1024 * 1024)
    free_gb = result.storage_free_kb / (1024 * 1024)
    kv("Total", f"{total_gb:.1f} GB")
    kv("Used", f"{(result.storage_total_kb - result.storage_free_kb) / (1024*1024):.1f} GB")
    kv("Free", f"{free_gb:.1f} GB")
    kv("Storage Type", result.storage_type)
    kv_if("Storage Model", result.storage_model)
    kv_if("Storage Vendor", result.storage_vendor)
    kv_if("Revision", result.storage_revision)
    kv_if("Firmware Info", result.storage_firmware)
    kv_if("Manufacturer ID", result.storage_manfid)
    kv_if("CID", result.storage_cid)
    if result.storage_life_time_a:
        kv("Life Time Est. A", result.storage_life_time_a)
    if result.storage_life_time_b:
        kv("Life Time Est. B", result.storage_life_time_b)
    if result.storage_pre_eol:
        _pre_eol_report_map = {"0x01": "Normal", "0x02": "Warning", "0x03": "Urgent",
                               "1": "Normal", "2": "Warning", "3": "Urgent"}
        eol_str = _pre_eol_report_map.get(result.storage_pre_eol, result.storage_pre_eol)
        kv("Pre-EOL Info", f"{result.storage_pre_eol} ({eol_str})")
    if result.storage_health_pct >= 0:
        kv("STORAGE HEALTH", f"{result.storage_health_pct}%")
    if result.storage_partitions:
        subheader("Partitions (from /proc/partitions)")
        for p in result.storage_partitions[:20]:  # limit output
            size_mb = p.get("blocks", 0) // 1024
            kv(f"  {p.get('name', '?')}", f"{size_mb} MB", indent=4)

    # ---- BATTERY ----
    header("BATTERY (DETAILED)")
    kv("Level", f"{result.battery_level}%")
    kv("Health", f"{result.battery_health} (code {result.battery_health_code})")
    kv("Status", f"{result.battery_status} (code {result.battery_status_code})")
    kv("Plugged", result.battery_plugged)
    kv("Technology", result.battery_technology)
    kv("Temperature", f"{result.battery_temp_c} C")
    kv("Voltage", f"{result.battery_voltage_mv} mV ({result.battery_voltage_mv / 1000:.2f} V)")
    kv("Current Now", f"{result.battery_current_now_ua} uA ({result.battery_current_now_ma:.1f} mA)")
    kv_if("Charge Counter", f"{result.battery_charge_counter_uah} uAh "
          f"({result.battery_charge_counter_uah / 1000:.0f} mAh)")
    kv_if("Charge Full", f"{result.battery_charge_full_uah} uAh "
          f"({result.battery_charge_full_uah / 1000:.0f} mAh)")
    kv_if("Charge Full Design", f"{result.battery_charge_full_design_uah} uAh "
          f"({result.battery_charge_full_design_uah / 1000:.0f} mAh)")
    kv_if("Cycle Count", result.battery_cycle_count)
    kv_if("Capacity Level", result.battery_capacity_level)
    kv_if("Age", result.battery_age)
    if result.battery_wear_pct >= 0:
        kv("WEAR PERCENTAGE", f"{result.battery_wear_pct}%")
    if result.battery_sysfs:
        subheader("Battery sysfs raw values")
        for k, v in result.battery_sysfs.items():
            kv(f"sysfs/{k}", v, indent=4)

    # ---- CHARGING IC ----
    header("CHARGING IC / USB POWER")
    kv("Charger Type", result.charger_type or "N/A")
    kv("USB Online", result.charger_usb_online or "N/A")
    if result.charger_usb_voltage_uv > 0:
        kv("USB Input Voltage", f"{result.charger_usb_voltage_uv} uV ({result.charger_usb_voltage_uv / 1000000:.2f} V)")
    else:
        kv("USB Input Voltage", "N/A")
    if result.charger_usb_current_max_ua > 0:
        kv("USB Max Current", f"{result.charger_usb_current_max_ua} uA ({result.charger_usb_current_max_ua / 1000:.0f} mA)")
    else:
        kv("USB Max Current", "N/A")
    kv("Charge Type", result.charger_charge_type or "N/A")
    if result.charger_input_current_limit_ua > 0:
        kv("Input Current Limit", f"{result.charger_input_current_limit_ua} uA ({result.charger_input_current_limit_ua / 1000:.0f} mA)")
    else:
        kv("Input Current Limit", "N/A")

    if result.charger_sysfs:
        subheader("Charging IC sysfs values")
        for k, v in result.charger_sysfs.items():
            kv(f"charging/{k}", v, indent=4)

    # Current graph (ASCII)
    if result.charging_current_samples and any(s != 0 for s in result.charging_current_samples):
        subheader("Charging Current Graph (5 samples, 1 sec apart)")
        samples_ma = [s / 1000.0 for s in result.charging_current_samples]
        max_abs = max(abs(s) for s in samples_ma) if samples_ma else 1
        if max_abs == 0:
            max_abs = 1

        # ASCII bar chart
        lines.append(f"  {'Sample':>8s}  {'mA':>10s}  {'Graph':s}")
        lines.append(f"  {'------':>8s}  {'------':>10s}  {'-----':s}")
        for i, ma in enumerate(samples_ma):
            bar_len = int(abs(ma) / max_abs * 40)
            bar_char = "█" if ma < 0 else "▓"  # Negative = discharging, positive = charging
            direction = "← discharge" if ma > 0 else "→ charging" if ma < 0 else ""
            bar = bar_char * bar_len
            lines.append(f"  {f't+{i}s':>8s}  {ma:>10.1f}  {bar} {direction}")

        avg = sum(samples_ma) / len(samples_ma)
        lines.append(f"")
        lines.append(f"  Average: {avg:.1f} mA")
        if avg < 0:
            lines.append(f"  Status: CHARGING at ~{abs(avg):.0f} mA")
        elif avg > 0:
            lines.append(f"  Status: DISCHARGING at ~{avg:.0f} mA")
        else:
            lines.append(f"  Status: IDLE / NOT MEASURABLE")

        # Charging health analysis
        if avg < 0:  # Charging
            if abs(avg) < 100:
                lines.append(f"  ⚠️ Very slow charging ({abs(avg):.0f}mA) — check charging IC, cable, adapter")
            elif abs(avg) < 500:
                lines.append(f"  ℹ️ Slow charging ({abs(avg):.0f}mA) — may be USB 2.0 or slow adapter")
            elif abs(avg) < 1500:
                lines.append(f"  ✅ Normal charging ({abs(avg):.0f}mA)")
            elif abs(avg) < 3000:
                lines.append(f"  ✅ Fast charging ({abs(avg):.0f}mA)")
            else:
                lines.append(f"  ✅ Super fast charging ({abs(avg):.0f}mA)")

    # ---- DISPLAY ----
    header("DISPLAY")
    kv("Resolution", result.display_resolution)
    kv_if("Override Resolution", result.display_override_resolution)
    kv("Density", f"{result.display_density} dpi")
    kv_if("Override Density", f"{result.display_override_density} dpi")
    kv_if("Refresh Rate", f"{result.display_refresh_rate} Hz")
    kv_if("HDR Support", result.display_hdr_support)
    if result.display_device_info:
        subheader("Display Device Info")
        for dline in result.display_device_info.splitlines()[:10]:
            lines.append(f"    {dline.strip()}")
    if result.display_modes:
        subheader("Display Modes (from SurfaceFlinger)")
        for mode in result.display_modes[:15]:
            lines.append(f"    {mode}")

    # ---- CONNECTIVITY ----
    header("CONNECTIVITY")
    subheader("WiFi")
    kv("MAC Address", result.wifi_mac or "Not available")
    kv_if("IP Address", result.wifi_ip)
    kv("State", result.wifi_state or "Unknown")
    kv_if("SSID", result.wifi_ssid)

    subheader("Bluetooth")
    kv("MAC Address", result.bt_mac or "Not available")
    kv("State", result.bt_state or "Unknown")
    kv_if("Name", result.bt_name)

    subheader("SIM / Telephony (Detailed)")

    # Parse dual SIM info
    sim_states = [s.strip() for s in result.sim_state.split(",")] if result.sim_state else []
    operators = [s.strip() for s in result.sim_operator.split(",")] if result.sim_operator else []
    net_types = [s.strip() for s in result.network_type.split(",")] if result.network_type else []
    countries = [s.strip() for s in result.sim_country.split(",")] if result.sim_country else []
    numerics = [s.strip() for s in result.sim_operator_numeric.split(",")] if result.sim_operator_numeric else []
    phone_types = [s.strip() for s in result.phone_type.split(",")] if result.phone_type else []

    kv("Total SIM Slots", str(len(sim_states)) if sim_states else "Unknown")

    for i in range(max(len(sim_states), 1)):
        lines.append("")
        slot_name = f"--- SIM Slot {i+1} ---"
        lines.append(f"  {slot_name}")
        state = sim_states[i] if i < len(sim_states) else "Unknown"
        kv(f"  State", state, indent=4)
        if i < len(operators) and operators[i]:
            kv(f"  Operator", operators[i], indent=4)
        if i < len(net_types) and net_types[i]:
            net = net_types[i]
            # Explain network type
            net_explain = {"LTE": "4G LTE", "NR_SA": "5G SA (Standalone)", "NR_NSA": "5G NSA",
                          "HSPA": "3G HSPA", "UMTS": "3G", "EDGE": "2G EDGE",
                          "IWLAN": "WiFi Calling", "GPRS": "2G GPRS"}
            net_full = net_explain.get(net, net)
            kv(f"  Network Type", f"{net} ({net_full})", indent=4)
        if i < len(countries) and countries[i]:
            kv(f"  Country", countries[i].upper(), indent=4)
        if i < len(numerics) and numerics[i]:
            kv(f"  MCC/MNC", numerics[i], indent=4)
        if i < len(phone_types) and phone_types[i]:
            ptype = {"1": "GSM", "2": "CDMA", "3": "SIP"}.get(phone_types[i], phone_types[i])
            kv(f"  Phone Type", ptype, indent=4)

    lines.append("")
    kv_if("Signal Strength", result.signal_strength_dbm)
    if result.signal_strength_dbm:
        dbm_match = re.search(r"(-?\d+)", result.signal_strength_dbm)
        if dbm_match:
            dbm = int(dbm_match.group(1))
            if dbm > -70:
                kv("Signal Quality", "Excellent (strong signal)")
            elif dbm > -85:
                kv("Signal Quality", "Good")
            elif dbm > -100:
                kv("Signal Quality", "Fair (may have call drops)")
            elif dbm > -110:
                kv("Signal Quality", "Poor (frequent drops likely)")
            else:
                kv("Signal Quality", "Very Poor / No signal")
    kv("Baseband Version", result.baseband_version or "Unknown")
    kv_if("Data State", result.data_state)

    # ---- CAMERA ----
    header("CAMERA")
    kv("Camera IDs", ", ".join(result.camera_ids) if result.camera_ids else "Not detected")
    for cid, facing in result.camera_details.items():
        kv(f"Camera {cid}", facing)
    if result.camera_video_devices:
        kv("Video Devices", ", ".join(result.camera_video_devices))

    # ---- SENSORS ----
    header("SENSORS")
    if result.sensors:
        lines.append(f"  {'#':<4} {'Name':<30} {'Vendor':<20} {'Range':<10} {'Res':<10}")
        lines.append(f"  {'-'*4} {'-'*30} {'-'*20} {'-'*10} {'-'*10}")
        for i, s in enumerate(result.sensors, 1):
            lines.append(f"  {i:<4} {s.name[:30]:<30} {s.vendor[:20]:<20} "
                         f"{s.max_range[:10]:<10} {s.resolution[:10]:<10}")
    else:
        lines.append("  No sensors detected")

    # ---- AUDIO ----
    header("AUDIO")
    kv("Output Devices", len(result.audio_output_devices))
    kv("Input Devices", len(result.audio_input_devices))
    if result.audio_output_devices:
        subheader("Output Devices")
        for d in result.audio_output_devices[:10]:
            lines.append(f"    {d}")
    if result.audio_input_devices:
        subheader("Input Devices")
        for d in result.audio_input_devices[:10]:
            lines.append(f"    {d}")

    # ---- FINGERPRINT ----
    header("FINGERPRINT")
    kv("Hardware Detected", result.fingerprint_hardware_detected)
    kv_if("Enrolled Count", result.fingerprint_enrolled_count)

    # ---- NFC ----
    header("NFC")
    if result.nfc_enabled is True:
        kv("Status", "Enabled")
    elif result.nfc_enabled is False:
        kv("Status", "Disabled")
    else:
        kv("Status", "Not present / not accessible")

    # ---- GPS ----
    header("GPS / LOCATION")
    kv("Providers", result.gps_providers or "Not available")

    # ---- THERMAL ----
    header("THERMAL ZONES")
    if result.thermal_zones:
        lines.append(f"  {'Zone Name':<30} {'Temp (C)':>10}")
        lines.append(f"  {'-'*30} {'-'*10}")
        for z in result.thermal_zones:
            marker = " **HOT**" if z.temp_c > 55 else (" *warm*" if z.temp_c > 45 else "")
            lines.append(f"  {z.name[:30]:<30} {z.temp_c:>10.1f}{marker}")
    else:
        lines.append("  No thermal zone data available")

    # ---- USB ----
    header("USB")
    kv("Config", result.usb_config)
    kv_if("Data Role", result.usb_data_role)
    kv_if("Power Role", result.usb_power_role)

    # ---- LOGCAT ANALYSIS ----
    header("LOGCAT ANALYSIS")
    kv("Total Lines Analyzed", result.logcat_raw_lines)

    logcat_cats = [
        ("Battery", result.logcat_battery_events),
        ("Fingerprint", result.logcat_fingerprint_events),
        ("Display/Panel/Backlight", result.logcat_display_events),
        ("Touch (Goodix/FocalTech/Synaptics/ILI)", result.logcat_touch_events),
        ("Audio (AW882xx/TFA98xx/SmartPA/ALSA)", result.logcat_audio_events),
        ("Camera (ImgSensor/OIS/EEPROM)", result.logcat_camera_events),
        ("WiFi (WLAN/WMT/ConnInfra)", result.logcat_wifi_events),
        ("Bluetooth (BTIF/BTMTK)", result.logcat_bluetooth_events),
        ("Modem (CCCI/MD)", result.logcat_modem_events),
        ("Sensors", result.logcat_sensors_events),
        ("Crash/ANR", result.logcat_crash_events),
        ("Errors", result.logcat_errors),
    ]

    for cat_name, cat_events in logcat_cats:
        kv(cat_name, f"{len(cat_events)} events")

    # Show detailed events for each category
    for cat_name, cat_events in logcat_cats:
        if cat_events and cat_name not in ["Errors"]:
            subheader(f"{cat_name} — Recent Events (max 15)")
            for ev in cat_events[:15]:
                lines.append(f"    {ev[:150]}")
            lines.append("")

    if result.logcat_crash_events:
        subheader("Recent Crashes / ANRs")
        for ev in result.logcat_crash_events[:20]:
            lines.append(f"    {ev[:150]}")

    if result.logcat_errors:
        subheader("Recent Errors (sample)")
        for ev in result.logcat_errors[:15]:
            lines.append(f"    {ev[:150]}")

    # ---- HW DRIVER LOGS ----
    if result.logcat_hw_driver_lines:
        header("HARDWARE DRIVER LOGS (logcat grep)")
        kv("Total HW Driver Lines", len(result.logcat_hw_driver_lines))
        lines.append("")

        # Group by category
        hw_categories = {
            "Display/DSI/Panel/Backlight": [],
            "Touch (Goodix/FocalTech/ILI/Synaptics)": [],
            "Camera/ImgSensor/OIS/EEPROM": [],
            "Audio (AW882xx/TFA98xx/SmartPA/ALSA)": [],
            "Fingerprint (FPC/Goodix_FP/Egis)": [],
            "WiFi/WLAN/WMT/ConnInfra": [],
            "Bluetooth (BTIF/BTMTK)": [],
            "Modem (CCCI/MD)": [],
            "Charging/CHG/PMIC": [],
            "Thermal": [],
            "Sensors": [],
            "USB/TypeC": [],
            "Other HW": [],
        }

        cat_patterns = {
            "Display/DSI/Panel/Backlight": r"display|dsi|lcm|panel|backlight|disp|drm|HBM|brightness",
            "Touch (Goodix/FocalTech/ILI/Synaptics)": r"touch|tp|fts|goodix|ili|synaptics|focaltech|novatek|himax|MotTouch",
            "Camera/ImgSensor/OIS/EEPROM": r"camera|imgsensor|ois|eeprom|seninf|CameraService",
            "Audio (AW882xx/TFA98xx/SmartPA/ALSA)": r"aw882|tfa98|smartpa|audio|ALSA|codec|ACCDET|speaker|headset",
            "Fingerprint (FPC/Goodix_FP/Egis)": r"fingerprint|fpc|egis|goodix.*fp|biometric|udfps",
            "WiFi/WLAN/WMT/ConnInfra": r"wlan|wmt|conninfra|wifi",
            "Bluetooth (BTIF/BTMTK)": r"btif|btmtk|bluetooth|BTAudio",
            "Modem (CCCI/MD)": r"ccci|modem|md_init",
            "Charging/CHG/PMIC": r"charger|charging|CHG|PMIC|mt637|mt636|bq25|sgm",
            "Thermal": r"thermal|overheat|throttle",
            "Sensors": r"sensor|accel|gyro|proximity|alsps",
            "USB/TypeC": r"usb|typec|otg",
        }

        for line in result.logcat_hw_driver_lines:
            categorized = False
            for cat_name, pattern in cat_patterns.items():
                if re.search(pattern, line, re.IGNORECASE):
                    hw_categories[cat_name].append(line)
                    categorized = True
                    break
            if not categorized:
                hw_categories["Other HW"].append(line)

        for cat_name, cat_lines in hw_categories.items():
            if cat_lines:
                subheader(f"{cat_name} ({len(cat_lines)} lines)")
                for cl in cat_lines[:20]:
                    lines.append(f"    {cl[:180]}")
                if len(cat_lines) > 20:
                    lines.append(f"    ... and {len(cat_lines) - 20} more lines")
                lines.append("")

    # ---- END ----
    lines.append("")
    lines.append("=" * W)
    lines.append("  END OF REPORT")
    lines.append("=" * W)

    return "\n".join(lines)
