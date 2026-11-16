"""
Predictive Failure Scoring — Score component health and predict failures.

Analyzes battery health, storage SMART data, thermal patterns, and other
sensor data to calculate a predictive failure score for each component.

Each component gets a health score (0-100) and a risk level:
  - LOW (80-100): Component is healthy
  - MODERATE (50-79): Component is degrading, monitor closely
  - HIGH (20-49): Component likely to fail soon
  - CRITICAL (0-19): Component failure imminent or already failing

Output includes:
  - Per-component health scores
  - Overall device health score
  - Time-to-failure estimates
  - Proactive recommendations
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import time
import json
from pathlib import Path


_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_PREDICTIONS_DB = _CONFIG_DIR / "predictive_history.json"


@dataclass
class ComponentHealth:
    """Health assessment for a single component."""
    component: str = ""
    health_score: int = 100         # 0-100
    risk_level: str = "LOW"         # LOW, MODERATE, HIGH, CRITICAL
    risk_factors: List[str] = field(default_factory=list)
    positive_factors: List[str] = field(default_factory=list)
    predicted_failure: str = ""     # "6-12 months", "1-3 months", "< 1 month", "imminent"
    recommendation: str = ""
    data_points: Dict = field(default_factory=dict)  # Raw data used for scoring
    trend: str = "stable"           # improving, stable, degrading, rapid_degradation


@dataclass
class PredictiveReport:
    """Complete predictive failure analysis report."""
    device_info: str = ""
    overall_score: int = 100
    overall_risk: str = "LOW"
    components: List[ComponentHealth] = field(default_factory=list)
    top_risks: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    summary: str = ""
    analysis_date: str = ""


# ─── SCORING THRESHOLDS ───────────────────────────────────────────────────

BATTERY_THRESHOLDS = {
    "cycle_count": [
        (0, 200, 100, "Excellent — low cycle count"),
        (200, 400, 85, "Good — moderate usage"),
        (400, 600, 65, "Fair — battery degrading"),
        (600, 800, 40, "Poor — significant wear"),
        (800, 999999, 15, "Critical — battery needs replacement"),
    ],
    "health_percent": [
        (90, 101, 100, "Excellent battery health"),
        (80, 90, 80, "Good — minor capacity loss"),
        (70, 80, 55, "Fair — noticeable degradation"),
        (50, 70, 30, "Poor — significant capacity loss"),
        (0, 50, 10, "Critical — battery failing"),
    ],
    "temperature": [
        (0, 30, 100, "Normal operating temperature"),
        (30, 40, 80, "Warm — within limits"),
        (40, 45, 50, "Hot — elevated temperature"),
        (45, 55, 20, "Very hot — thermal stress"),
        (55, 999, 5, "Critical — dangerous temperature"),
    ],
    "voltage": [
        (3700, 4200, 100, "Normal voltage range"),
        (3500, 3700, 70, "Low voltage — needs charging"),
        (3300, 3500, 40, "Very low voltage"),
        (0, 3300, 10, "Critical — battery may be damaged"),
    ],
}

STORAGE_THRESHOLDS = {
    "life_used_pct": [
        (0, 10, 100, "Excellent — minimal wear"),
        (10, 30, 85, "Good — light usage"),
        (30, 50, 65, "Moderate — normal wear"),
        (50, 70, 40, "High usage — monitor closely"),
        (70, 90, 20, "Critical — approaching end of life"),
        (90, 100, 5, "Failure imminent — replace immediately"),
    ],
    "free_space_pct": [
        (30, 101, 100, "Adequate free space"),
        (15, 30, 70, "Getting full — clean up recommended"),
        (5, 15, 40, "Very low space — performance affected"),
        (0, 5, 15, "Critical — almost full, system instability risk"),
    ],
    "pre_eol": [
        (0, 1, 100, "Normal — not at end of life"),
        (1, 2, 50, "Warning — approaching end of life"),
        (2, 3, 20, "Urgent — replace storage soon"),
        (3, 999, 5, "End of life reached"),
    ],
}

THERMAL_THRESHOLDS = {
    "cpu_temp": [
        (0, 40, 100, "Normal CPU temperature"),
        (40, 55, 75, "Warm — CPU under load"),
        (55, 70, 45, "Hot — throttling likely"),
        (70, 85, 20, "Very hot — thermal damage risk"),
        (85, 999, 5, "Critical — immediate shutdown risk"),
    ],
    "battery_temp": [
        (0, 35, 100, "Normal battery temperature"),
        (35, 40, 70, "Warm — monitor"),
        (40, 45, 40, "Hot — battery stress"),
        (45, 55, 15, "Dangerous — swelling risk"),
        (55, 999, 5, "Critical — fire/explosion risk"),
    ],
    "throttle_percent": [
        (0, 5, 100, "No throttling"),
        (5, 20, 75, "Light throttling — normal under load"),
        (20, 40, 50, "Moderate throttling — thermal issue"),
        (40, 70, 25, "Heavy throttling — cooling problem"),
        (70, 101, 10, "Severe throttling — hardware issue"),
    ],
}


def _score_value(value: float, thresholds: list) -> tuple:
    """Score a value against threshold ranges. Returns (score, description)."""
    for low, high, score, desc in thresholds:
        if low <= value < high:
            return score, desc
    return 50, "Unknown range"


def _risk_from_score(score: int) -> str:
    """Convert health score to risk level."""
    if score >= 80:
        return "LOW"
    if score >= 50:
        return "MODERATE"
    if score >= 20:
        return "HIGH"
    return "CRITICAL"


def _failure_estimate(score: int) -> str:
    """Estimate time to failure from health score."""
    if score >= 80:
        return "> 12 months"
    if score >= 60:
        return "6-12 months"
    if score >= 40:
        return "3-6 months"
    if score >= 20:
        return "1-3 months"
    return "< 1 month (urgent)"


class PredictiveScorer:
    """Analyzes device data and predicts component failures."""

    def __init__(self):
        self._history = self._load_history()

    def _load_history(self) -> dict:
        """Load prediction history for trend analysis."""
        if _PREDICTIONS_DB.exists():
            try:
                with open(_PREDICTIONS_DB, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"predictions": []}

    def _save_history(self, device_id: str, report: PredictiveReport):
        """Save a prediction for trend tracking."""
        entry = {
            "device_id": device_id,
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "overall_score": report.overall_score,
            "components": {
                c.component: {
                    "score": c.health_score,
                    "risk": c.risk_level,
                }
                for c in report.components
            },
        }
        self._history["predictions"].append(entry)

        # Keep only last 100 predictions
        self._history["predictions"] = self._history["predictions"][-100:]

        try:
            with open(_PREDICTIONS_DB, 'w', encoding='utf-8') as f:
                json.dump(self._history, f, indent=2)
        except Exception:
            pass

    def _get_trend(self, device_id: str, component: str) -> str:
        """Get trend direction from historical data."""
        scores = []
        for pred in self._history.get("predictions", []):
            if pred.get("device_id") == device_id:
                comp_data = pred.get("components", {}).get(component)
                if comp_data:
                    scores.append(comp_data["score"])

        if len(scores) < 2:
            return "stable"

        recent = scores[-3:] if len(scores) >= 3 else scores
        avg_recent = sum(recent) / len(recent)
        avg_old = sum(scores[:-len(recent)]) / max(len(scores[:-len(recent)]), 1)

        diff = avg_recent - avg_old
        if diff > 10:
            return "improving"
        if diff < -20:
            return "rapid_degradation"
        if diff < -5:
            return "degrading"
        return "stable"

    def score_battery(self, battery_data: dict, device_id: str = "") -> ComponentHealth:
        """Score battery health from battery test data."""
        health = ComponentHealth(component="Battery")
        scores = []

        # Voltage
        voltage = battery_data.get("voltage_mv", 0)
        if voltage:
            if isinstance(voltage, str):
                try:
                    voltage = float(voltage.replace("mV", "").replace("V", "").strip())
                    if voltage < 10:
                        voltage *= 1000
                except ValueError:
                    voltage = 0
            if voltage > 0:
                s, desc = _score_value(voltage, BATTERY_THRESHOLDS["voltage"])
                scores.append(s)
                health.data_points["voltage_mv"] = voltage
                if s < 70:
                    health.risk_factors.append(f"Voltage: {voltage}mV — {desc}")
                else:
                    health.positive_factors.append(f"Voltage: {int(voltage)}mV — {desc}")

        # Temperature
        temp = battery_data.get("temperature_c", 0)
        if temp:
            if isinstance(temp, str):
                try:
                    temp = float(temp.replace("°C", "").strip())
                except ValueError:
                    temp = 0
            if temp > 0:
                s, desc = _score_value(temp, BATTERY_THRESHOLDS["temperature"])
                scores.append(s)
                health.data_points["temperature_c"] = temp
                if s < 70:
                    health.risk_factors.append(f"Temperature: {temp}°C — {desc}")
                else:
                    health.positive_factors.append(f"Temperature: {temp}°C — {desc}")

        # Cycle count
        cycles = battery_data.get("cycle_count", 0)
        if cycles:
            if isinstance(cycles, str):
                try:
                    cycles = int(cycles)
                except ValueError:
                    cycles = 0
            if cycles > 0:
                s, desc = _score_value(cycles, BATTERY_THRESHOLDS["cycle_count"])
                scores.append(s)
                health.data_points["cycle_count"] = cycles
                if s < 70:
                    health.risk_factors.append(f"Cycles: {cycles} — {desc}")
                else:
                    health.positive_factors.append(f"Cycles: {cycles} — {desc}")

        # Health percent
        health_pct = battery_data.get("health_percent", 0)
        if health_pct:
            if isinstance(health_pct, str):
                try:
                    health_pct = float(health_pct.replace("%", "").strip())
                except ValueError:
                    health_pct = 0
            if health_pct > 0:
                s, desc = _score_value(health_pct, BATTERY_THRESHOLDS["health_percent"])
                scores.append(s)
                health.data_points["health_percent"] = health_pct
                if s < 70:
                    health.risk_factors.append(f"Health: {health_pct}% — {desc}")
                else:
                    health.positive_factors.append(f"Health: {health_pct}% — {desc}")

        # Health status string
        health_status = battery_data.get("health_status", "")
        if isinstance(health_status, str) and health_status:
            status_lower = health_status.lower()
            if status_lower in ("dead", "unspecified failure"):
                scores.append(5)
                health.risk_factors.append(f"Health status: {health_status}")
            elif status_lower in ("overheat", "over voltage"):
                scores.append(20)
                health.risk_factors.append(f"Health status: {health_status}")
            elif status_lower not in ("good", "2", ""):
                scores.append(50)
                health.risk_factors.append(f"Health status: {health_status}")

        # Calculate final score
        if scores:
            health.health_score = int(sum(scores) / len(scores))
        else:
            health.health_score = -1  # No data
            health.recommendation = "No battery data available — connect device via ADB"
            return health

        health.risk_level = _risk_from_score(health.health_score)
        health.predicted_failure = _failure_estimate(health.health_score)
        health.trend = self._get_trend(device_id, "Battery")

        # Recommendation
        if health.health_score >= 80:
            health.recommendation = "Battery is healthy. No action needed."
        elif health.health_score >= 50:
            health.recommendation = "Battery showing signs of degradation. Consider replacement in the next few months."
        elif health.health_score >= 20:
            health.recommendation = "Battery is degraded. Replace soon to prevent unexpected shutdowns."
        else:
            health.recommendation = "URGENT: Battery needs immediate replacement. Risk of swelling or failure."

        return health

    def score_storage(self, storage_data: dict, device_id: str = "") -> ComponentHealth:
        """Score storage health from storage test data."""
        health = ComponentHealth(component="Storage (eMMC/UFS)")
        scores = []

        # Life used percentage
        life_a = storage_data.get("life_time_a", 0)
        life_b = storage_data.get("life_time_b", 0)
        life_used = max(
            self._parse_numeric(life_a),
            self._parse_numeric(life_b),
        )
        if life_used > 0:
            # Convert 0x0A format to percentage (each unit = 10%)
            if life_used <= 11:
                life_pct = life_used * 10
            else:
                life_pct = life_used
            s, desc = _score_value(life_pct, STORAGE_THRESHOLDS["life_used_pct"])
            scores.append(s)
            health.data_points["life_used_pct"] = life_pct
            if s < 70:
                health.risk_factors.append(f"Life used: {life_pct}% — {desc}")
            else:
                health.positive_factors.append(f"Life used: {life_pct}% — {desc}")

        # Free space
        free_pct = self._parse_numeric(storage_data.get("free_space_pct", 0))
        if free_pct > 0:
            s, desc = _score_value(free_pct, STORAGE_THRESHOLDS["free_space_pct"])
            scores.append(s)
            health.data_points["free_space_pct"] = free_pct
            if s < 70:
                health.risk_factors.append(f"Free space: {free_pct}% — {desc}")
            else:
                health.positive_factors.append(f"Free space: {free_pct}% — {desc}")

        # Pre-EOL indicator
        pre_eol = self._parse_numeric(storage_data.get("pre_eol_info", 0))
        if pre_eol >= 0:
            s, desc = _score_value(pre_eol, STORAGE_THRESHOLDS["pre_eol"])
            scores.append(s)
            health.data_points["pre_eol"] = pre_eol
            if s < 70:
                health.risk_factors.append(f"Pre-EOL: {pre_eol} — {desc}")
            else:
                health.positive_factors.append(f"Pre-EOL: {pre_eol} — {desc}")

        # Health status string
        health_status = storage_data.get("health_status", "")
        if isinstance(health_status, str) and health_status:
            if "bad" in health_status.lower() or "fail" in health_status.lower():
                scores.append(10)
                health.risk_factors.append(f"Health status: {health_status}")
            elif "warn" in health_status.lower() or "degrad" in health_status.lower():
                scores.append(40)
                health.risk_factors.append(f"Health status: {health_status}")

        if scores:
            health.health_score = int(sum(scores) / len(scores))
        else:
            health.health_score = -1
            health.recommendation = "No storage health data available"
            return health

        health.risk_level = _risk_from_score(health.health_score)
        health.predicted_failure = _failure_estimate(health.health_score)
        health.trend = self._get_trend(device_id, "Storage")

        if health.health_score >= 80:
            health.recommendation = "Storage is healthy. No action needed."
        elif health.health_score >= 50:
            health.recommendation = "Storage showing wear. Back up important data regularly."
        elif health.health_score >= 20:
            health.recommendation = "Storage is significantly worn. Back up data and plan replacement."
        else:
            health.recommendation = "URGENT: Storage failure imminent. Back up all data immediately and replace."

        return health

    def score_thermal(self, thermal_data: dict, device_id: str = "") -> ComponentHealth:
        """Score thermal health from thermal test data."""
        health = ComponentHealth(component="Thermal Management")
        scores = []

        # CPU temperature
        cpu_temp = self._parse_numeric(thermal_data.get("cpu_temp", 0))
        if cpu_temp > 0:
            s, desc = _score_value(cpu_temp, THERMAL_THRESHOLDS["cpu_temp"])
            scores.append(s)
            health.data_points["cpu_temp"] = cpu_temp
            if s < 70:
                health.risk_factors.append(f"CPU temp: {cpu_temp}°C — {desc}")
            else:
                health.positive_factors.append(f"CPU temp: {cpu_temp}°C — {desc}")

        # Battery temperature
        bat_temp = self._parse_numeric(thermal_data.get("battery_temp", 0))
        if bat_temp > 0:
            s, desc = _score_value(bat_temp, THERMAL_THRESHOLDS["battery_temp"])
            scores.append(s)
            health.data_points["battery_temp"] = bat_temp
            if s < 70:
                health.risk_factors.append(f"Battery temp: {bat_temp}°C — {desc}")
            else:
                health.positive_factors.append(f"Battery temp: {bat_temp}°C — {desc}")

        # CPU throttling
        throttle = self._parse_numeric(thermal_data.get("throttle_percent", 0))
        if throttle >= 0:
            s, desc = _score_value(throttle, THERMAL_THRESHOLDS["throttle_percent"])
            scores.append(s)
            health.data_points["throttle_percent"] = throttle
            if s < 70:
                health.risk_factors.append(f"Throttling: {throttle}% — {desc}")
            else:
                health.positive_factors.append(f"Throttling: {throttle}% — {desc}")

        if scores:
            health.health_score = int(sum(scores) / len(scores))
        else:
            health.health_score = -1
            health.recommendation = "No thermal data available"
            return health

        health.risk_level = _risk_from_score(health.health_score)
        health.predicted_failure = _failure_estimate(health.health_score)
        health.trend = self._get_trend(device_id, "Thermal")

        if health.health_score >= 80:
            health.recommendation = "Thermal management is normal. No issues."
        elif health.health_score >= 50:
            health.recommendation = "Device running warm. Ensure vents/cooling paths are clear."
        elif health.health_score >= 20:
            health.recommendation = "Thermal stress detected. Check for blocked vents, damaged thermal paste, or short circuits."
        else:
            health.recommendation = "CRITICAL thermal condition. Power off device. Check for short circuits or component damage."

        return health

    def score_from_adb(self, adb_result, device_id: str = "") -> PredictiveReport:
        """Generate a full predictive report from ADB detection data."""
        report = PredictiveReport()
        report.device_info = f"{adb_result.brand} {adb_result.model}"
        report.analysis_date = time.strftime("%Y-%m-%d %H:%M:%S")

        if not device_id:
            device_id = f"{adb_result.brand}_{adb_result.model}".replace(" ", "_").lower()

        # Score battery
        battery_data = {
            "voltage_mv": getattr(adb_result, 'battery_voltage', ''),
            "temperature_c": getattr(adb_result, 'battery_temp', ''),
            "health_status": getattr(adb_result, 'battery_health', ''),
            "health_percent": getattr(adb_result, 'battery_level', ''),
            "cycle_count": getattr(adb_result, 'battery_cycle_count', 0),
        }
        battery_health = self.score_battery(battery_data, device_id)
        if battery_health.health_score >= 0:
            report.components.append(battery_health)

        # Score storage
        storage_data = {
            "free_space_pct": 0,
            "health_status": "",
        }
        if adb_result.storage_total and adb_result.storage_free:
            try:
                total = float(adb_result.storage_total.replace("GB", "").strip())
                free = float(adb_result.storage_free.replace("GB", "").strip())
                if total > 0:
                    storage_data["free_space_pct"] = int(free / total * 100)
            except (ValueError, AttributeError):
                pass
        storage_health = self.score_storage(storage_data, device_id)
        if storage_health.health_score >= 0:
            report.components.append(storage_health)

        # Score thermal (from battery temp as proxy)
        thermal_data = {}
        if adb_result.battery_temp:
            try:
                t = float(adb_result.battery_temp.replace("°C", "").strip())
                thermal_data["battery_temp"] = t
            except (ValueError, AttributeError):
                pass
        thermal_health = self.score_thermal(thermal_data, device_id)
        if thermal_health.health_score >= 0:
            report.components.append(thermal_health)

        # Score RAM
        ram_health = self._score_ram_from_adb(adb_result, device_id)
        if ram_health.health_score >= 0:
            report.components.append(ram_health)

        # Score connectivity
        conn_health = self._score_connectivity_from_adb(adb_result, device_id)
        if conn_health.health_score >= 0:
            report.components.append(conn_health)

        # Calculate overall score
        valid_scores = [c.health_score for c in report.components if c.health_score >= 0]
        if valid_scores:
            # Weighted: battery and storage matter most
            weights = {
                "Battery": 2.0,
                "Storage (eMMC/UFS)": 2.0,
                "Thermal Management": 1.5,
                "RAM": 1.0,
                "Connectivity": 1.0,
            }
            total_weight = 0
            weighted_sum = 0
            for comp in report.components:
                w = weights.get(comp.component, 1.0)
                weighted_sum += comp.health_score * w
                total_weight += w
            report.overall_score = int(weighted_sum / total_weight) if total_weight else 50
        else:
            report.overall_score = -1

        report.overall_risk = _risk_from_score(report.overall_score)

        # Top risks
        for comp in sorted(report.components, key=lambda c: c.health_score):
            if comp.risk_level in ("HIGH", "CRITICAL"):
                report.top_risks.append(f"{comp.component}: {comp.risk_level} risk — {comp.predicted_failure}")

        # Recommended actions
        for comp in report.components:
            if comp.health_score < 50:
                report.recommended_actions.append(comp.recommendation)

        if not report.recommended_actions:
            report.recommended_actions.append("All components healthy. Continue regular monitoring.")

        # Summary
        if report.overall_score >= 80:
            report.summary = f"✅ Device is healthy (score: {report.overall_score}/100). No components at risk."
        elif report.overall_score >= 50:
            report.summary = f"🟡 Device has moderate wear (score: {report.overall_score}/100). {len(report.top_risks)} component(s) need attention."
        elif report.overall_score >= 20:
            report.summary = f"🟠 Device is degraded (score: {report.overall_score}/100). Proactive maintenance recommended."
        else:
            report.summary = f"🔴 Device at high risk of failure (score: {report.overall_score}/100). Immediate action required."

        # Save to history for trend tracking
        self._save_history(device_id, report)

        return report

    def score_from_test_results(self, battery_result=None, storage_result=None,
                                thermal_result=None, device_id: str = "") -> PredictiveReport:
        """Generate a predictive report from detailed test module results."""
        report = PredictiveReport()
        report.analysis_date = time.strftime("%Y-%m-%d %H:%M:%S")

        if battery_result:
            bat_data = {}
            if hasattr(battery_result, 'battery_info') and battery_result.battery_info:
                bi = battery_result.battery_info
                bat_data["voltage_mv"] = getattr(bi, 'voltage_mv', 0)
                bat_data["temperature_c"] = getattr(bi, 'temperature_c', 0)
                bat_data["cycle_count"] = getattr(bi, 'cycle_count', 0)
            if hasattr(battery_result, 'health_detail') and battery_result.health_detail:
                hd = battery_result.health_detail
                bat_data["health_percent"] = 100 - getattr(hd, 'capacity_fade_pct', 0)
            report.device_info = getattr(battery_result, 'device_model', 'Unknown')
            battery_health = self.score_battery(bat_data, device_id)
            if battery_health.health_score >= 0:
                report.components.append(battery_health)

        if storage_result:
            stor_data = {}
            if hasattr(storage_result, 'storage') and storage_result.storage:
                si = storage_result.storage
                stor_data["life_time_a"] = getattr(si, 'life_time_a', 0)
                stor_data["life_time_b"] = getattr(si, 'life_time_b', 0)
                stor_data["pre_eol_info"] = getattr(si, 'pre_eol_info', 0)
                stor_data["free_space_pct"] = 100 - getattr(si, 'usage_percent', 0)
                stor_data["health_status"] = getattr(si, 'health_status', '')
            storage_health = self.score_storage(stor_data, device_id)
            if storage_health.health_score >= 0:
                report.components.append(storage_health)

        if thermal_result:
            therm_data = {}
            if hasattr(thermal_result, 'temperatures') and thermal_result.temperatures:
                temps = thermal_result.temperatures
                therm_data["cpu_temp"] = temps.get("cpu", 0)
                therm_data["battery_temp"] = temps.get("battery", 0)
            if hasattr(thermal_result, 'cpu_throttle') and thermal_result.cpu_throttle:
                throttles = [ct.throttle_percent for ct in thermal_result.cpu_throttle if hasattr(ct, 'throttle_percent')]
                if throttles:
                    therm_data["throttle_percent"] = max(throttles)
            thermal_health = self.score_thermal(therm_data, device_id)
            if thermal_health.health_score >= 0:
                report.components.append(thermal_health)

        # Calculate overall
        valid_scores = [c.health_score for c in report.components if c.health_score >= 0]
        if valid_scores:
            report.overall_score = int(sum(valid_scores) / len(valid_scores))
        else:
            report.overall_score = -1

        report.overall_risk = _risk_from_score(report.overall_score)

        for comp in sorted(report.components, key=lambda c: c.health_score):
            if comp.risk_level in ("HIGH", "CRITICAL"):
                report.top_risks.append(f"{comp.component}: {comp.risk_level} risk")

        for comp in report.components:
            if comp.health_score < 50:
                report.recommended_actions.append(comp.recommendation)

        if not report.recommended_actions:
            report.recommended_actions.append("All tested components are healthy.")

        if report.overall_score >= 80:
            report.summary = f"✅ Healthy device (score: {report.overall_score}/100)."
        elif report.overall_score >= 50:
            report.summary = f"🟡 Moderate wear (score: {report.overall_score}/100)."
        elif report.overall_score >= 20:
            report.summary = f"🟠 Degraded (score: {report.overall_score}/100). Maintenance needed."
        else:
            report.summary = f"🔴 High risk (score: {report.overall_score}/100). Immediate action required."

        if device_id:
            self._save_history(device_id, report)

        return report

    def _score_ram_from_adb(self, adb_result, device_id: str) -> ComponentHealth:
        """Score RAM health from ADB data."""
        health = ComponentHealth(component="RAM")

        if not adb_result.ram_total or not adb_result.ram_free:
            health.health_score = -1
            return health

        try:
            total = float(adb_result.ram_total.replace("MB", "").replace("GB", "").strip())
            free = float(adb_result.ram_free.replace("MB", "").replace("GB", "").strip())
            if total < 32:
                total *= 1024
            if free < 32:
                free *= 1024

            free_pct = (free / total * 100) if total > 0 else 0
            health.data_points["total_mb"] = total
            health.data_points["free_mb"] = free
            health.data_points["free_pct"] = round(free_pct, 1)

            if free_pct > 20:
                health.health_score = 90
                health.positive_factors.append(f"Free RAM: {int(free)}MB ({free_pct:.0f}%)")
            elif free_pct > 10:
                health.health_score = 65
                health.risk_factors.append(f"Low free RAM: {int(free)}MB ({free_pct:.0f}%)")
            elif free_pct > 5:
                health.health_score = 40
                health.risk_factors.append(f"Very low RAM: {int(free)}MB ({free_pct:.0f}%)")
            else:
                health.health_score = 15
                health.risk_factors.append(f"Critical RAM: {int(free)}MB ({free_pct:.0f}%)")

        except (ValueError, AttributeError, ZeroDivisionError):
            health.health_score = -1
            return health

        health.risk_level = _risk_from_score(health.health_score)
        health.predicted_failure = _failure_estimate(health.health_score)
        health.trend = self._get_trend(device_id, "RAM")

        if health.health_score >= 80:
            health.recommendation = "RAM usage is normal."
        elif health.health_score >= 50:
            health.recommendation = "RAM is getting low. Close unused apps."
        else:
            health.recommendation = "RAM critically low. Restart device or reduce background apps. If persistent, may indicate RAM fault."

        return health

    def _score_connectivity_from_adb(self, adb_result, device_id: str) -> ComponentHealth:
        """Score connectivity components from ADB data."""
        health = ComponentHealth(component="Connectivity")
        checks = 0
        passed = 0

        # WiFi
        if hasattr(adb_result, 'wifi_mac'):
            checks += 1
            if adb_result.wifi_mac and adb_result.wifi_mac not in ["", "02:00:00:00:00:00"]:
                passed += 1
                health.positive_factors.append("WiFi: Working")
            else:
                health.risk_factors.append("WiFi: Not detected or MAC invalid")

        # Bluetooth
        if hasattr(adb_result, 'bluetooth_mac'):
            checks += 1
            if adb_result.bluetooth_mac and adb_result.bluetooth_mac not in ["", "null"]:
                passed += 1
                health.positive_factors.append("Bluetooth: Working")
            else:
                health.risk_factors.append("Bluetooth: Not detected")

        # SIM
        if hasattr(adb_result, 'sim_state'):
            checks += 1
            if adb_result.sim_state and adb_result.sim_state not in ["ABSENT", "NOT_READY", ""]:
                passed += 1
                health.positive_factors.append("SIM: Detected")
            else:
                health.risk_factors.append("SIM: Not detected")

        if checks > 0:
            health.health_score = int(passed / checks * 100)
        else:
            health.health_score = -1
            return health

        health.risk_level = _risk_from_score(health.health_score)
        health.predicted_failure = "N/A" if health.health_score >= 80 else _failure_estimate(health.health_score)
        health.trend = self._get_trend(device_id, "Connectivity")

        if health.health_score >= 80:
            health.recommendation = "All connectivity modules working."
        elif health.health_score >= 50:
            health.recommendation = "Some connectivity issues. Check individual modules."
        else:
            health.recommendation = "Multiple connectivity failures. Check combo IC and antennas."

        return health

    @staticmethod
    def _parse_numeric(value) -> float:
        """Parse a potentially string numeric value."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace("%", "").replace("°C", "").replace("mV", "").replace("GB", "").replace("MB", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                # Try hex
                if cleaned.startswith("0x"):
                    try:
                        return float(int(cleaned, 16))
                    except ValueError:
                        pass
        return 0


def generate_predictive_report(report: PredictiveReport) -> str:
    """Generate formatted text report."""
    lines = [
        "═══════════════════════════════════════════════════════════",
        "         PREDICTIVE FAILURE ANALYSIS REPORT",
        "═══════════════════════════════════════════════════════════",
        "",
        f"Device:     {report.device_info}",
        f"Date:       {report.analysis_date}",
        f"Overall:    {report.overall_score}/100 ({report.overall_risk} risk)",
        "",
    ]

    # Risk meter visualization
    score = report.overall_score
    filled = score // 5
    bar = "█" * filled + "░" * (20 - filled)
    lines.append(f"  Health: [{bar}] {score}%")
    lines.append("")

    # Component details
    lines.append("─── COMPONENT HEALTH SCORES ────────────────────────────")
    lines.append("")

    for comp in sorted(report.components, key=lambda c: c.health_score):
        risk_icon = {
            "LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"
        }.get(comp.risk_level, "⚪")
        trend_icon = {
            "improving": "📈", "stable": "➡️", "degrading": "📉", "rapid_degradation": "⚠️📉"
        }.get(comp.trend, "")

        c_filled = comp.health_score // 5
        c_bar = "█" * c_filled + "░" * (20 - c_filled)

        lines.append(f"  {risk_icon} {comp.component}")
        lines.append(f"     Score: [{c_bar}] {comp.health_score}%")
        lines.append(f"     Risk: {comp.risk_level} | Trend: {comp.trend} {trend_icon}")
        lines.append(f"     Predicted failure: {comp.predicted_failure}")

        if comp.risk_factors:
            lines.append(f"     Risk factors:")
            for rf in comp.risk_factors:
                lines.append(f"       ⚠️ {rf}")

        if comp.positive_factors:
            lines.append(f"     Positive:")
            for pf in comp.positive_factors:
                lines.append(f"       ✅ {pf}")

        lines.append(f"     → {comp.recommendation}")
        lines.append("")

    # Top risks
    if report.top_risks:
        lines.append("─── TOP RISKS ─────────────────────────────────────────")
        for risk in report.top_risks:
            lines.append(f"  🔴 {risk}")
        lines.append("")

    # Recommendations
    lines.append("─── RECOMMENDED ACTIONS ────────────────────────────────")
    for i, action in enumerate(report.recommended_actions, 1):
        lines.append(f"  {i}. {action}")
    lines.append("")

    lines.append(f"Summary: {report.summary}")
    lines.append("═══════════════════════════════════════════════════════════")

    return "\n".join(lines)
