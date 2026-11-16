"""
Known-Good Baseline Comparison — Store golden snapshots and diff against them.

Stores "golden" baselines from known-working devices and compares
a device under test against its matching baseline to spot anomalies.

Baseline types:
  - UART boot log baseline (key boot phases, timings, messages)
  - ADB hardware snapshot (battery, storage, sensors, thermal)
  - Component health baseline (expected values per model)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import json
import re
import time


# ─── DATA DIR ──────────────────────────────────────────────────────────────

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_BASELINE_DIR = _CONFIG_DIR / "baselines"
_BASELINE_DB = _CONFIG_DIR / "baselines_database.json"


@dataclass
class BaselineEntry:
    """A single measurable data point in a baseline."""
    key: str = ""               # e.g. "battery_voltage", "cpu_freq_max", "boot_time_ms"
    category: str = ""          # battery, storage, thermal, cpu, ram, sensor, boot, network
    expected_value: str = ""    # The "golden" value
    unit: str = ""              # mV, MHz, °C, GB, ms, etc.
    tolerance: float = 0.15     # 15% tolerance by default
    min_value: float = 0.0      # Hard minimum (below = fault)
    max_value: float = 0.0      # Hard maximum (above = fault)
    is_numeric: bool = True     # If false, do exact string match
    description: str = ""


@dataclass
class Baseline:
    """A complete known-good baseline for a device model."""
    baseline_id: str = ""
    device_model: str = ""      # e.g. "Samsung Galaxy S24 Ultra"
    brand: str = ""
    chipset: str = ""
    android_version: str = ""
    created_date: str = ""
    source: str = ""            # "auto_captured" or "manual" or "community"
    entries: List[BaselineEntry] = field(default_factory=list)
    boot_log_patterns: List[str] = field(default_factory=list)  # Expected patterns in boot log
    boot_log_absent: List[str] = field(default_factory=list)    # Patterns that should NOT appear
    metadata: Dict = field(default_factory=dict)


@dataclass
class DiffResult:
    """A single difference between baseline and device under test."""
    key: str = ""
    category: str = ""
    baseline_value: str = ""
    actual_value: str = ""
    deviation_percent: float = 0.0
    severity: str = "info"       # critical, warning, info
    description: str = ""
    recommendation: str = ""


@dataclass
class BaselineComparisonReport:
    """Full comparison report between baseline and device under test."""
    device_info: str = ""
    baseline_used: str = ""
    total_checks: int = 0
    passed: int = 0
    warnings: int = 0
    failures: int = 0
    health_score: int = 100      # 0-100
    diffs: List[DiffResult] = field(default_factory=list)
    matched_components: List[str] = field(default_factory=list)
    boot_log_anomalies: List[str] = field(default_factory=list)
    summary: str = ""


# ─── DEFAULT BASELINES (built-in for common models) ───────────────────────

# Generic baselines by chipset family — used when no model-specific baseline exists
GENERIC_BASELINES = {
    "mediatek_generic": Baseline(
        baseline_id="generic_mtk",
        device_model="Generic MediaTek Device",
        brand="Generic",
        chipset="MediaTek",
        entries=[
            BaselineEntry("battery_voltage", "battery", "3900", "mV", 0.15, 3400, 4400, True, "Battery voltage"),
            BaselineEntry("battery_temp", "battery", "28", "°C", 0.30, 10, 45, True, "Battery temperature"),
            BaselineEntry("battery_health", "battery", "Good", "", 0, 0, 0, False, "Battery health status"),
            BaselineEntry("cpu_cores", "cpu", "8", "cores", 0, 4, 12, True, "CPU core count"),
            BaselineEntry("ram_total", "ram", "4096", "MB", 0.5, 1024, 16384, True, "Total RAM"),
            BaselineEntry("ram_free_pct", "ram", "30", "%", 0.5, 5, 100, True, "Free RAM percentage"),
            BaselineEntry("storage_free_pct", "storage", "40", "%", 0.5, 2, 100, True, "Free storage percentage"),
            BaselineEntry("thermal_cpu", "thermal", "35", "°C", 0.20, 15, 65, True, "CPU temperature"),
            BaselineEntry("thermal_battery", "thermal", "30", "°C", 0.25, 10, 50, True, "Battery thermal zone"),
            BaselineEntry("wifi_status", "network", "enabled", "", 0, 0, 0, False, "WiFi enabled"),
            BaselineEntry("bluetooth_status", "network", "enabled", "", 0, 0, 0, False, "Bluetooth enabled"),
            BaselineEntry("sensor_count", "sensor", "10", "sensors", 0.5, 3, 30, True, "Number of sensors"),
        ],
        boot_log_patterns=[
            r"preloader",
            r"DRAM|EMI|dram_init",
            r"Jump to Bootloader|LK|ABL",
        ],
        boot_log_absent=[
            r"DRAM.*fail|EMI.*error",
            r"PMIC.*fault|power.*fail",
            r"eMMC.*error|UFS.*fail",
            r"panic|oops|watchdog.*reset",
        ],
    ),

    "qualcomm_generic": Baseline(
        baseline_id="generic_qcom",
        device_model="Generic Qualcomm Device",
        brand="Generic",
        chipset="Qualcomm",
        entries=[
            BaselineEntry("battery_voltage", "battery", "3900", "mV", 0.15, 3400, 4400, True, "Battery voltage"),
            BaselineEntry("battery_temp", "battery", "28", "°C", 0.30, 10, 45, True, "Battery temperature"),
            BaselineEntry("battery_health", "battery", "Good", "", 0, 0, 0, False, "Battery health status"),
            BaselineEntry("cpu_cores", "cpu", "8", "cores", 0, 4, 12, True, "CPU core count"),
            BaselineEntry("ram_total", "ram", "6144", "MB", 0.5, 1024, 16384, True, "Total RAM"),
            BaselineEntry("ram_free_pct", "ram", "30", "%", 0.5, 5, 100, True, "Free RAM percentage"),
            BaselineEntry("storage_free_pct", "storage", "40", "%", 0.5, 2, 100, True, "Free storage percentage"),
            BaselineEntry("thermal_cpu", "thermal", "38", "°C", 0.20, 15, 70, True, "CPU temperature"),
            BaselineEntry("thermal_battery", "thermal", "30", "°C", 0.25, 10, 50, True, "Battery thermal zone"),
            BaselineEntry("wifi_status", "network", "enabled", "", 0, 0, 0, False, "WiFi enabled"),
            BaselineEntry("bluetooth_status", "network", "enabled", "", 0, 0, 0, False, "Bluetooth enabled"),
            BaselineEntry("sensor_count", "sensor", "12", "sensors", 0.5, 3, 30, True, "Number of sensors"),
        ],
        boot_log_patterns=[
            r"SBL|XBL|ABL",
            r"UEFI|ABOOT|sbl1",
            r"Kernel|linux",
        ],
        boot_log_absent=[
            r"DRAM.*fail|DDR.*error",
            r"PMIC.*fault|PON.*fail",
            r"UFS.*error|storage.*fail",
            r"panic|oops|watchdog.*bite",
        ],
    ),
}


class BaselineComparator:
    """Compares device data against known-good baselines."""

    def __init__(self):
        self._baselines: Dict[str, Baseline] = {}
        self._load_baselines()

    def _load_baselines(self):
        """Load baselines from disk + built-in defaults."""
        # Load built-in generic baselines
        for key, baseline in GENERIC_BASELINES.items():
            self._baselines[key] = baseline

        # Load saved baselines from disk
        if _BASELINE_DB.exists():
            try:
                with open(_BASELINE_DB, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for bl_data in data.get("baselines", []):
                    bl = self._dict_to_baseline(bl_data)
                    self._baselines[bl.baseline_id] = bl
            except Exception as e:
                print(f"[BaselineComparator] Error loading baselines: {e}")

    def _dict_to_baseline(self, d: dict) -> Baseline:
        """Convert a dictionary to a Baseline object."""
        entries = []
        for e in d.get("entries", []):
            entries.append(BaselineEntry(
                key=e.get("key", ""),
                category=e.get("category", ""),
                expected_value=str(e.get("expected_value", "")),
                unit=e.get("unit", ""),
                tolerance=e.get("tolerance", 0.15),
                min_value=e.get("min_value", 0),
                max_value=e.get("max_value", 0),
                is_numeric=e.get("is_numeric", True),
                description=e.get("description", ""),
            ))
        return Baseline(
            baseline_id=d.get("baseline_id", ""),
            device_model=d.get("device_model", ""),
            brand=d.get("brand", ""),
            chipset=d.get("chipset", ""),
            android_version=d.get("android_version", ""),
            created_date=d.get("created_date", ""),
            source=d.get("source", "manual"),
            entries=entries,
            boot_log_patterns=d.get("boot_log_patterns", []),
            boot_log_absent=d.get("boot_log_absent", []),
            metadata=d.get("metadata", {}),
        )

    def _baseline_to_dict(self, bl: Baseline) -> dict:
        """Convert a Baseline to a JSON-serializable dict."""
        return {
            "baseline_id": bl.baseline_id,
            "device_model": bl.device_model,
            "brand": bl.brand,
            "chipset": bl.chipset,
            "android_version": bl.android_version,
            "created_date": bl.created_date,
            "source": bl.source,
            "entries": [
                {
                    "key": e.key, "category": e.category,
                    "expected_value": e.expected_value, "unit": e.unit,
                    "tolerance": e.tolerance, "min_value": e.min_value,
                    "max_value": e.max_value, "is_numeric": e.is_numeric,
                    "description": e.description,
                }
                for e in bl.entries
            ],
            "boot_log_patterns": bl.boot_log_patterns,
            "boot_log_absent": bl.boot_log_absent,
            "metadata": bl.metadata,
        }

    def save_baselines(self):
        """Save all custom baselines to disk."""
        _BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        custom = [
            self._baseline_to_dict(bl)
            for bl in self._baselines.values()
            if bl.source != "builtin"
        ]
        data = {"_info": "Mooxy AI — Known-Good Baselines", "baselines": custom}
        with open(_BASELINE_DB, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_all_baselines(self) -> List[Baseline]:
        """Return all available baselines."""
        return list(self._baselines.values())

    def find_baseline(self, model: str = "", chipset: str = "", brand: str = "") -> Optional[Baseline]:
        """Find the best matching baseline for a device."""
        # Try exact model match first
        model_lower = model.lower()
        for bl in self._baselines.values():
            if bl.device_model.lower() == model_lower:
                return bl

        # Try partial model match
        for bl in self._baselines.values():
            if model_lower and model_lower in bl.device_model.lower():
                return bl

        # Try brand + chipset match
        for bl in self._baselines.values():
            if (brand and brand.lower() in bl.brand.lower() and
                    chipset and chipset.lower() in bl.chipset.lower()):
                return bl

        # Fall back to generic chipset baseline
        chipset_lower = chipset.lower() if chipset else ""
        if "mediatek" in chipset_lower or "mt6" in chipset_lower or "helio" in chipset_lower:
            return self._baselines.get("mediatek_generic")
        if "qualcomm" in chipset_lower or "snapdragon" in chipset_lower or "sm" in chipset_lower:
            return self._baselines.get("qualcomm_generic")

        return None

    def capture_baseline_from_adb(self, adb_result) -> Baseline:
        """Create a baseline from an ADB detection result (known-good device)."""
        entries = []

        # Battery
        if adb_result.battery_voltage:
            try:
                v = float(adb_result.battery_voltage.replace("mV", "").replace("V", "").strip())
                if v < 10:
                    v *= 1000  # Convert V to mV
                entries.append(BaselineEntry("battery_voltage", "battery", str(int(v)), "mV", 0.15, 3400, 4400))
            except (ValueError, AttributeError):
                pass

        if adb_result.battery_temp:
            try:
                t = float(adb_result.battery_temp.replace("°C", "").strip())
                entries.append(BaselineEntry("battery_temp", "battery", str(int(t)), "°C", 0.30, 10, 45))
            except (ValueError, AttributeError):
                pass

        if adb_result.battery_health:
            entries.append(BaselineEntry("battery_health", "battery", adb_result.battery_health, "", 0, 0, 0, False))

        # CPU
        if hasattr(adb_result, 'cpu_cores') and adb_result.cpu_cores:
            entries.append(BaselineEntry("cpu_cores", "cpu", str(adb_result.cpu_cores), "cores", 0, 1, 16))

        if hasattr(adb_result, 'cpu_freq_max') and adb_result.cpu_freq_max:
            try:
                freq = int(adb_result.cpu_freq_max)
                entries.append(BaselineEntry("cpu_freq_max", "cpu", str(freq), "MHz", 0.10, 500, 4000))
            except (ValueError, AttributeError):
                pass

        # RAM
        if adb_result.ram_total:
            try:
                ram = int(adb_result.ram_total.replace("MB", "").replace("GB", "").strip())
                if ram < 32:
                    ram *= 1024  # GB to MB
                entries.append(BaselineEntry("ram_total", "ram", str(ram), "MB", 0.05, 512, 24576))
            except (ValueError, AttributeError):
                pass

        # Storage
        if adb_result.storage_total:
            try:
                s = int(adb_result.storage_total.replace("GB", "").strip())
                entries.append(BaselineEntry("storage_total", "storage", str(s), "GB", 0.05, 8, 2048))
            except (ValueError, AttributeError):
                pass

        # Sensors
        if adb_result.sensors_list:
            count = len(adb_result.sensors_list) if isinstance(adb_result.sensors_list, list) else 0
            if count > 0:
                entries.append(BaselineEntry("sensor_count", "sensor", str(count), "sensors", 0.3, 1, 50))

        # WiFi / BT
        if adb_result.wifi_mac and adb_result.wifi_mac not in ["", "02:00:00:00:00:00"]:
            entries.append(BaselineEntry("wifi_status", "network", "enabled", "", 0, 0, 0, False))
        if adb_result.bluetooth_mac and adb_result.bluetooth_mac not in ["", "null"]:
            entries.append(BaselineEntry("bluetooth_status", "network", "enabled", "", 0, 0, 0, False))

        model = f"{adb_result.brand} {adb_result.model}"
        baseline_id = f"auto_{model.replace(' ', '_').lower()}_{int(time.time())}"

        return Baseline(
            baseline_id=baseline_id,
            device_model=model,
            brand=adb_result.brand,
            chipset=getattr(adb_result, 'chipset', ''),
            android_version=getattr(adb_result, 'android_version', ''),
            created_date=time.strftime("%Y-%m-%d %H:%M:%S"),
            source="auto_captured",
            entries=entries,
        )

    def save_new_baseline(self, baseline: Baseline):
        """Save a new baseline to the database."""
        self._baselines[baseline.baseline_id] = baseline
        self.save_baselines()

    def compare_adb(self, adb_result, baseline: Optional[Baseline] = None) -> BaselineComparisonReport:
        """Compare an ADB result against its baseline."""
        report = BaselineComparisonReport()
        report.device_info = f"{adb_result.brand} {adb_result.model}"

        # Find baseline
        if baseline is None:
            baseline = self.find_baseline(
                model=f"{adb_result.brand} {adb_result.model}",
                chipset=getattr(adb_result, 'chipset', ''),
                brand=adb_result.brand,
            )

        if baseline is None:
            report.summary = "⚠️ No matching baseline found. Save a known-good device as baseline first."
            return report

        report.baseline_used = f"{baseline.device_model} ({baseline.source})"

        # Extract actual values from ADB result
        actual_values = self._extract_adb_values(adb_result)

        # Compare each baseline entry
        for entry in baseline.entries:
            report.total_checks += 1
            actual = actual_values.get(entry.key, None)

            if actual is None:
                report.diffs.append(DiffResult(
                    key=entry.key,
                    category=entry.category,
                    baseline_value=f"{entry.expected_value} {entry.unit}",
                    actual_value="NOT AVAILABLE",
                    severity="info",
                    description=f"{entry.description} — could not read from device",
                    recommendation="Check if this component is accessible via ADB",
                ))
                continue

            if entry.is_numeric:
                diff = self._compare_numeric(entry, actual)
            else:
                diff = self._compare_string(entry, actual)

            if diff:
                report.diffs.append(diff)
                if diff.severity == "critical":
                    report.failures += 1
                elif diff.severity == "warning":
                    report.warnings += 1
                else:
                    report.passed += 1
            else:
                report.passed += 1
                report.matched_components.append(f"{entry.description}: ✅ {actual} {entry.unit}")

        # Calculate health score
        if report.total_checks > 0:
            penalty = (report.failures * 20) + (report.warnings * 8)
            report.health_score = max(0, 100 - penalty)

        # Summary
        if report.failures == 0 and report.warnings == 0:
            report.summary = f"✅ Device matches baseline perfectly. {report.passed}/{report.total_checks} checks passed."
        elif report.failures == 0:
            report.summary = f"🟡 {report.warnings} deviation(s) from baseline. {report.passed}/{report.total_checks} within range."
        else:
            report.summary = f"🔴 {report.failures} critical deviation(s) and {report.warnings} warning(s). Health: {report.health_score}%"

        return report

    def compare_boot_log(self, boot_log: str, baseline: Optional[Baseline] = None,
                         chipset: str = "") -> BaselineComparisonReport:
        """Compare a UART boot log against baseline expected patterns."""
        report = BaselineComparisonReport()
        report.device_info = f"Boot log analysis ({chipset or 'Unknown chipset'})"

        if baseline is None:
            baseline = self.find_baseline(chipset=chipset)

        if baseline is None:
            report.summary = "⚠️ No matching baseline found for boot log comparison."
            return report

        report.baseline_used = f"{baseline.device_model} ({baseline.source})"

        # Check expected patterns (should be present)
        for pattern_str in baseline.boot_log_patterns:
            report.total_checks += 1
            try:
                if re.search(pattern_str, boot_log, re.IGNORECASE):
                    report.passed += 1
                    report.matched_components.append(f"Boot pattern found: {pattern_str}")
                else:
                    report.warnings += 1
                    report.boot_log_anomalies.append(f"Expected pattern NOT found: {pattern_str}")
                    report.diffs.append(DiffResult(
                        key=f"boot_pattern_{pattern_str[:30]}",
                        category="boot",
                        baseline_value=f"Pattern should exist: {pattern_str}",
                        actual_value="NOT FOUND",
                        severity="warning",
                        description=f"Expected boot pattern missing: {pattern_str}",
                        recommendation="This boot phase may have failed — check hardware",
                    ))
            except re.error:
                pass

        # Check absent patterns (should NOT be present)
        for pattern_str in baseline.boot_log_absent:
            report.total_checks += 1
            try:
                match = re.search(pattern_str, boot_log, re.IGNORECASE)
                if match:
                    report.failures += 1
                    report.boot_log_anomalies.append(f"ERROR pattern detected: {match.group()}")
                    report.diffs.append(DiffResult(
                        key=f"boot_error_{pattern_str[:30]}",
                        category="boot",
                        baseline_value="Pattern should NOT exist",
                        actual_value=f"FOUND: {match.group()[:80]}",
                        severity="critical",
                        description=f"Error pattern detected in boot log: {match.group()[:80]}",
                        recommendation="This error indicates a hardware fault — investigate",
                    ))
                else:
                    report.passed += 1
            except re.error:
                pass

        # Health score
        if report.total_checks > 0:
            penalty = (report.failures * 25) + (report.warnings * 10)
            report.health_score = max(0, 100 - penalty)

        # Summary
        if report.failures == 0 and report.warnings == 0:
            report.summary = f"✅ Boot log matches baseline. {report.passed}/{report.total_checks} patterns verified."
        elif report.failures > 0:
            report.summary = f"🔴 {report.failures} error pattern(s) found in boot log. Health: {report.health_score}%"
        else:
            report.summary = f"🟡 {report.warnings} expected pattern(s) missing. Health: {report.health_score}%"

        return report

    def _extract_adb_values(self, adb_result) -> Dict[str, str]:
        """Extract comparable values from an ADB result object."""
        values = {}

        # Battery
        if adb_result.battery_voltage:
            try:
                v = adb_result.battery_voltage.replace("mV", "").replace("V", "").strip()
                v_float = float(v)
                if v_float < 10:
                    v_float *= 1000
                values["battery_voltage"] = str(int(v_float))
            except (ValueError, AttributeError):
                pass

        if adb_result.battery_temp:
            try:
                values["battery_temp"] = adb_result.battery_temp.replace("°C", "").strip()
            except (AttributeError):
                pass

        if adb_result.battery_health:
            values["battery_health"] = adb_result.battery_health

        # CPU
        if hasattr(adb_result, 'cpu_cores') and adb_result.cpu_cores:
            values["cpu_cores"] = str(adb_result.cpu_cores)
        if hasattr(adb_result, 'cpu_freq_max') and adb_result.cpu_freq_max:
            values["cpu_freq_max"] = str(adb_result.cpu_freq_max)

        # RAM
        if adb_result.ram_total:
            try:
                ram = adb_result.ram_total.replace("MB", "").replace("GB", "").strip()
                r = float(ram)
                if r < 32:
                    r *= 1024
                values["ram_total"] = str(int(r))
            except (ValueError, AttributeError):
                pass
        if adb_result.ram_free:
            try:
                total_str = values.get("ram_total", "0")
                total = float(total_str) if total_str else 0
                free = float(adb_result.ram_free.replace("MB", "").replace("GB", "").strip())
                if free < 32:
                    free *= 1024
                if total > 0:
                    values["ram_free_pct"] = str(int(free / total * 100))
            except (ValueError, AttributeError, ZeroDivisionError):
                pass

        # Storage
        if adb_result.storage_total:
            try:
                values["storage_total"] = adb_result.storage_total.replace("GB", "").strip()
            except (AttributeError):
                pass
        if adb_result.storage_free and adb_result.storage_total:
            try:
                total = float(adb_result.storage_total.replace("GB", "").strip())
                free = float(adb_result.storage_free.replace("GB", "").strip())
                if total > 0:
                    values["storage_free_pct"] = str(int(free / total * 100))
            except (ValueError, AttributeError, ZeroDivisionError):
                pass

        # Sensors
        if adb_result.sensors_list:
            if isinstance(adb_result.sensors_list, list):
                values["sensor_count"] = str(len(adb_result.sensors_list))

        # WiFi / BT
        if adb_result.wifi_mac and adb_result.wifi_mac not in ["", "02:00:00:00:00:00"]:
            values["wifi_status"] = "enabled"
        else:
            values["wifi_status"] = "disabled"

        if adb_result.bluetooth_mac and adb_result.bluetooth_mac not in ["", "null"]:
            values["bluetooth_status"] = "enabled"
        else:
            values["bluetooth_status"] = "disabled"

        return values

    def _compare_numeric(self, entry: BaselineEntry, actual_str: str) -> Optional[DiffResult]:
        """Compare a numeric value against baseline."""
        try:
            actual = float(actual_str)
            expected = float(entry.expected_value)
        except (ValueError, TypeError):
            return None

        # Check hard limits first
        if entry.max_value > 0 and actual > entry.max_value:
            return DiffResult(
                key=entry.key,
                category=entry.category,
                baseline_value=f"{entry.expected_value} {entry.unit}",
                actual_value=f"{actual_str} {entry.unit}",
                deviation_percent=((actual - expected) / expected * 100) if expected else 0,
                severity="critical",
                description=f"{entry.description} exceeds maximum ({entry.max_value} {entry.unit})",
                recommendation=f"Value {actual_str} {entry.unit} is above safe limit. Investigate component.",
            )

        if entry.min_value > 0 and actual < entry.min_value:
            return DiffResult(
                key=entry.key,
                category=entry.category,
                baseline_value=f"{entry.expected_value} {entry.unit}",
                actual_value=f"{actual_str} {entry.unit}",
                deviation_percent=((expected - actual) / expected * 100) if expected else 0,
                severity="critical",
                description=f"{entry.description} below minimum ({entry.min_value} {entry.unit})",
                recommendation=f"Value {actual_str} {entry.unit} is below safe limit. Investigate component.",
            )

        # Check tolerance
        if expected > 0:
            deviation = abs(actual - expected) / expected
            if deviation > entry.tolerance:
                severity = "critical" if deviation > entry.tolerance * 2 else "warning"
                return DiffResult(
                    key=entry.key,
                    category=entry.category,
                    baseline_value=f"{entry.expected_value} {entry.unit}",
                    actual_value=f"{actual_str} {entry.unit}",
                    deviation_percent=round(deviation * 100, 1),
                    severity=severity,
                    description=f"{entry.description} deviates {round(deviation * 100, 1)}% from baseline",
                    recommendation=f"Expected ~{entry.expected_value} {entry.unit}, got {actual_str} {entry.unit}.",
                )

        return None

    def _compare_string(self, entry: BaselineEntry, actual: str) -> Optional[DiffResult]:
        """Compare a string value against baseline."""
        if actual.lower().strip() != entry.expected_value.lower().strip():
            # Determine severity based on category
            severity = "warning"
            if entry.category in ("battery",) and entry.key == "battery_health":
                if actual.lower() in ("dead", "overheat", "unspecified failure"):
                    severity = "critical"
            if entry.category == "network":
                if actual.lower() == "disabled" and entry.expected_value.lower() == "enabled":
                    severity = "warning"

            return DiffResult(
                key=entry.key,
                category=entry.category,
                baseline_value=entry.expected_value,
                actual_value=actual,
                severity=severity,
                description=f"{entry.description} differs from baseline",
                recommendation=f"Expected '{entry.expected_value}', got '{actual}'.",
            )
        return None

    def delete_baseline(self, baseline_id: str):
        """Remove a baseline."""
        if baseline_id in self._baselines:
            del self._baselines[baseline_id]
            self.save_baselines()


def generate_comparison_report(report: BaselineComparisonReport) -> str:
    """Generate formatted text report of baseline comparison."""
    lines = [
        "═══════════════════════════════════════════════════════════",
        "        KNOWN-GOOD BASELINE COMPARISON REPORT",
        "═══════════════════════════════════════════════════════════",
        "",
        f"Device:    {report.device_info}",
        f"Baseline:  {report.baseline_used}",
        f"Health:    {report.health_score}%",
        f"Checks:    {report.total_checks} total — {report.passed} ✅  {report.warnings} ⚠️  {report.failures} ❌",
        "",
    ]

    if report.diffs:
        lines.append("─── DEVIATIONS FROM BASELINE ───────────────────────────")
        lines.append("")
        for diff in report.diffs:
            icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(diff.severity, "⚪")
            lines.append(f"  {icon} {diff.key} [{diff.category}]")
            lines.append(f"     Baseline: {diff.baseline_value}")
            lines.append(f"     Actual:   {diff.actual_value}")
            if diff.deviation_percent:
                lines.append(f"     Deviation: {diff.deviation_percent}%")
            lines.append(f"     → {diff.recommendation}")
            lines.append("")

    if report.matched_components:
        lines.append("─── MATCHING COMPONENTS ────────────────────────────────")
        for comp in report.matched_components:
            lines.append(f"  {comp}")
        lines.append("")

    if report.boot_log_anomalies:
        lines.append("─── BOOT LOG ANOMALIES ────────────────────────────────")
        for anomaly in report.boot_log_anomalies:
            lines.append(f"  ⚠️ {anomaly}")
        lines.append("")

    lines.append(f"Summary: {report.summary}")
    lines.append("═══════════════════════════════════════════════════════════")

    return "\n".join(lines)
