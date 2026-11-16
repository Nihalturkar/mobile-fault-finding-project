"""
schematic_diagnosis.py — Fault-pattern → schematic test plan → diagnosis.

Bridges the two halves of the repair workflow:

  evidence layer      (ADB / UART / EDL logs, dumpsys, logcat)
         │  symptom keywords / fault pattern id
         ▼
  schematic layer     (BoardView flat-dump: components + pins + nets + image)
         │  test points (component.pin@net, board coords) + expected rail V
         ▼
  technician          probes each point with a multimeter, types the reading
         ▼
  verdict             OK / ZERO / LOW / HIGH per rail → probable broken part

The expected rail voltages come from `config/chipset_ic_database.json`
fault_patterns.<id>.test_points (per-IC net keywords + expected volts), with
fallback to a built-in table when a pattern has no test_points entry.

Typical flow:

    from app.hardware.boardview_loader import BoardView
    from app.hardware.schematic_diagnosis import SchematicDiagnoser

    bv   = BoardView.load("config/boardviews/POCO_M2_flat.json")
    diag = SchematicDiagnoser(bv)
    plan = diag.plan_for_pattern("camera_not_working")     # auto net matching
    diag.set_measurement(pt_index=0, volts=0.0)            # tech reading
    report = diag.generate_report()                        # text summary
    png = diag.render_plan("test_plan.png")                # one image per net
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.hardware.boardview_loader import BoardView, TestPoint

# ---------------------------------------------------------------------------
# Built-in expected rails (volts), used when the pattern JSON has no test_points
# ---------------------------------------------------------------------------

RAIL_VOLTAGE_HINTS: List[dict] = [
    # (net keywords, expected class)
    {"keywords": ["AVDD"], "v": 2.8, "label": "camera/analog rail"},
    {"keywords": ["DVDD", "VDD_FE"], "v": 1.2, "label": "digital core rail"},
    {"keywords": ["DOVDD", "VIO"], "v": 1.8, "label": "IO rail"},
    {"keywords": ["VCAMD"], "v": 1.1, "label": "camera module rail"},
    {"keywords": ["VDD_PA"], "v": 3.3, "label": "PA supply"},
    {"keywords": ["VBAT"], "v": 3.8, "label": "battery rail"},
    {"keywords": ["VSYS"], "v": 4.2, "label": "system rail"},
    {"keywords": ["VBUS"], "v": 5.0, "label": "USB/charging rail"},
    {"keywords": ["VIO28", "VDD28"], "v": 2.8, "label": "2.8V IO rail"},
    {"keywords": ["VDD18", "VDD_1V8"], "v": 1.8, "label": "1.8V rail"},
    {"keywords": ["VDD_1V2"], "v": 1.2, "label": "1.2V rail"},
]

PATTERN_TEST_POINTS: Dict[str, List[dict]] = {
    "camera_not_working": [
        {"ic": "Camera PMIC", "nets": ["AVDD", "DOVDD", "DVDD", "VCAMD"], "volts": 2.8},
        {"ic": "Camera connector", "nets": ["CAM_CLK", "MCLK", "CAM_RST", "SCL", "SDA"], "volts": None},
        {"ic": "Camera module", "nets": ["VIO28", "VDD28"], "volts": 2.8},
    ],
    "no_network_signal": [
        {"ic": "RF / PA", "nets": ["VDD_PA", "PA_OUT", "RF"], "volts": 3.3},
        {"ic": "Baseband/modem", "nets": ["VSYS", "VBAT", "VDD18"], "volts": None},
        {"ic": "SIM reader", "nets": ["SIM", "VIO"], "volts": 1.8},
    ],
    "no_display": [
        {"ic": "Display connector", "nets": ["LCD", "DSI", "MIPI", "BL", "BACKLIGHT"], "volts": None},
        {"ic": "Display rail", "nets": ["VDD18", "VDD28", "VIO"], "volts": 1.8},
    ],
    "no_wifi_bluetooth": [
        {"ic": "WiFi/BT combo", "nets": ["WIFI", "BT", "WL", "VDD_PA"], "volts": 3.3},
        {"ic": "WiFi rail", "nets": ["VDD18", "VIO"], "volts": 1.8},
    ],
    "no_audio": [
        {"ic": "Audio codec", "nets": ["AU", "HPH", "MIC", "SPK", "AMP"], "volts": None},
        {"ic": "Audio rail", "nets": ["VDD18", "VIO"], "volts": 1.8},
    ],
    "no_charging": [
        {"ic": "Charging IC", "nets": ["VBUS", "CHG", "PD"], "volts": 5.0},
        {"ic": "Battery path", "nets": ["VBAT", "VSYS"], "volts": None},
    ],
    "dead_phone_no_power": [
        {"ic": "PMIC input", "nets": ["VBAT", "VBAT_TEST"], "volts": 3.8},
        {"ic": "PMIC output", "nets": ["VSYS", "VDD18", "VDD_1V2"], "volts": None},
    ],
    "overheating": [
        {"ic": "Main rail", "nets": ["VSYS", "VBAT"], "volts": None},
        {"ic": "Charging path", "nets": ["VBUS", "CHG"], "volts": 5.0},
    ],
    "touch_not_working": [
        {"ic": "Touch IC", "nets": ["TP", "TOUCH", "I2C"], "volts": None},
        {"ic": "Touch rail", "nets": ["VDD18", "VIO28"], "volts": 1.8},
    ],
    "fast_battery_drain": [
        {"ic": "Battery path", "nets": ["VBAT", "VSYS"], "volts": None},
    ],
    "fingerprint_not_working": [
        {"ic": "Fingerprint IC", "nets": ["FPC", "FP", "I2C"], "volts": None},
        {"ic": "Fingerprint rail", "nets": ["VDD18", "VIO"], "volts": 1.8},
    ],
    "logo_stuck_boot_loop": [
        {"ic": "DRAM regulator", "nets": ["VDD_DRAM", "VDD2", "VDDQ"], "volts": 1.1},
        {"ic": "Storage/SoC", "nets": ["VDD_1V2", "VDD18", "VSYS"], "volts": None},
    ],
}


# ---------------------------------------------------------------------------
# Status logic
# ---------------------------------------------------------------------------

def classify_reading(measured_v: Optional[float], expected_v: Optional[float],
                     tol_ratio: float = 0.1) -> str:
    """Compare a multimeter reading with the expected rail voltage.

    Returns one of: OK / ZERO / LOW / HIGH / UNMEASURED / N/A.
    """
    if measured_v is None:
        return "UNMEASURED"
    if expected_v is None or expected_v <= 0:
        return "N/A"
    if measured_v == 0.0:
        return "ZERO"                      # rail dead — open/short
    if measured_v < 0.03:
        return "ZERO"
    if measured_v < expected_v * (1 - tol_ratio):
        return "LOW"
    if measured_v > expected_v * (1 + tol_ratio):
        return "HIGH"
    return "OK"


@dataclass
class MeasuredPoint:
    """One planned probe point plus the technician's reading."""
    point: TestPoint
    expected_v: Optional[float] = None
    measured_v: Optional[float] = None
    status: str = "UNMEASURED"
    ic_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "net": self.point.net,
            "component": self.point.component,
            "pin": self.point.pin,
            "x": round(self.point.x, 2),
            "y": round(self.point.y, 2),
            "expected_v": self.expected_v,
            "measured_v": self.measured_v,
            "status": self.status,
            "ic_hint": self.ic_hint,
            "label": self.point.label,
        }


# ---------------------------------------------------------------------------
# The diagnoser
# ---------------------------------------------------------------------------

class SchematicDiagnoser:
    def __init__(self, board: BoardView, patterns: Optional[dict] = None):
        self.board = board
        self.patterns = patterns or self._load_default_patterns()
        self.plan: List[MeasuredPoint] = []
        self.pattern_id: str = ""
        self.pattern_symptom: str = ""
        self.report_extra: List[str] = []

    # -- pattern data ------------------------------------------------------

    @staticmethod
    def _load_default_patterns() -> dict:
        """Load fault_patterns from chipset_ic_database.json (built-in fallback)."""
        p = Path(__file__).resolve().parent.parent.parent / "config" / "chipset_ic_database.json"
        try:
            with open(p, "r", encoding="utf-8") as f:
                return (json.load(f).get("fault_patterns") or {})
        except Exception:
            return {}

    def pattern_ids(self) -> List[str]:
        return sorted(set(self.patterns) | set(PATTERN_TEST_POINTS))

    # -- planning ----------------------------------------------------------

    def _match_expected_v(self, net: str) -> Optional[float]:
        upper = net.upper()
        for hint in RAIL_VOLTAGE_HINTS:
            if any(k.upper() in upper for k in hint["keywords"]):
                return float(hint["v"])
        return None

    def plan_for_pattern(self, pattern_id: str, max_per_group: int = 2) -> List[MeasuredPoint]:
        """Build a test plan for a fault pattern by matching net keywords on the board."""
        self.pattern_id = pattern_id
        pat = (self.patterns or {}).get(pattern_id, {})
        self.pattern_symptom = str(pat.get("symptom", ""))
        self.report_extra = [c.get("reason", "") for c in pat.get("possible_causes", [])]

        groups = PATTERN_TEST_POINTS.get(pattern_id, [])
        if pat.get("test_points"):
            groups = pat["test_points"] if isinstance(pat["test_points"], list) else groups

        self.plan = []
        seen: set = set()
        for group in groups:
            ic = str(group.get("ic", "?"))
            for kw in group.get("nets", []):
                nets = self.board.search_nets(kw, limit=8)
                for net in nets:
                    if net in seen:
                        continue
                    seen.add(net)
                    expected = group.get("volts")
                    if expected is None:
                        expected = self._match_expected_v(net)
                    for tp in self.board.test_points_for_net(net, max_points=max_per_group):
                        self.plan.append(MeasuredPoint(
                            point=tp,
                            expected_v=float(expected) if expected is not None else None,
                            ic_hint=ic,
                        ))
        return self.plan

    def plan_from_keywords(self, symptoms: List[str]) -> str:
        """Pick the fault pattern that best matches symptom keywords (evidence-driven)."""
        best_id, best_score = "", 0
        text = " ".join(symptoms).upper()
        for pid in self.pattern_ids():
            pat = (self.patterns or {}).get(pid, {})
            score = 0
            for token in (str(pat.get("symptom", "")) + " " + " ".join(str(x) for x in pat.get("indicators", []))).upper().split():
                if token in text and len(token) > 3:
                    score += 1
            for kw in _SYMPTOM_KEYWORDS.get(pid, []):
                if kw.upper() in text:
                    score += 2
            if score > best_score:
                best_id, best_score = pid, score
        if best_id:
            self.plan_for_pattern(best_id)
        return best_id

    # -- measurements ------------------------------------------------------

    def set_measurement(self, index: int, volts: Optional[float]) -> None:
        if not (0 <= index < len(self.plan)):
            return
        mp = self.plan[index]
        mp.measured_v = volts
        mp.status = classify_reading(volts, mp.expected_v)

    def set_measurement_by_label(self, label: str, volts: Optional[float]) -> bool:
        for i, mp in enumerate(self.plan):
            if mp.point.label == label:
                self.set_measurement(i, volts)
                return True
        return False

    def summary_status(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for mp in self.plan:
            out[mp.status] = out.get(mp.status, 0) + 1
        return out

    def likely_faults(self) -> List[str]:
        """Nets that read ZERO/LOW/HIGH → probable break/short candidates."""
        bad = [mp for mp in self.plan if mp.status in ("ZERO", "LOW", "HIGH")]
        out = []
        for mp in bad:
            hint = mp.ic_hint or "?"
            if mp.status == "ZERO":
                out.append(f"{mp.point.net} is DEAD (0V) — {hint} rail open or short")
            elif mp.status == "LOW":
                out.append(f"{mp.point.net} is LOW ({mp.measured_v}V vs {mp.expected_v}V) — {hint} weak/dropped rail")
            else:
                out.append(f"{mp.point.net} is HIGH ({mp.measured_v}V vs {mp.expected_v}V) — {hint} check short")
        return out

    # -- output ------------------------------------------------------------

    def generate_report(self) -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("  SCHEMATIC DIAGNOSIS REPORT")
        lines.append("=" * 72)
        lines.append(f"  Board      : {self.board.source_path or 'in-memory'}")
        lines.append(f"  Pattern    : {self.pattern_id}")
        lines.append(f"  Symptom    : {self.pattern_symptom}")
        s = self.board.summary()
        lines.append(f"  Data       : {s['components']} comps, {s['pins']} pins, {s['nets_named']} named nets")
        lines.append("-" * 72)
        if self.report_extra:
            lines.append("  Possible causes (knowledge base):")
            for r in self.report_extra[:6]:
                lines.append(f"    • {r}")
            lines.append("-" * 72)
        lines.append(f"  {'NET':24s} {'POINT':22s} {'EXP':>6s} {'MEAS':>6s}  STATUS")
        for mp in self.plan:
            lines.append(
                f"  {mp.point.net[:24]:24s} {mp.point.label[:22]:22s} "
                f"{str(mp.expected_v if mp.expected_v is not None else '-'):>6s} "
                f"{str(mp.measured_v if mp.measured_v is not None else '-'):>6s}  {mp.status}"
            )
        lines.append("-" * 72)
        faults = self.likely_faults()
        lines.append("  Verdict:")
        if not self.plan:
            lines.append("    No test points on this board for this pattern.")
        elif not faults:
            lines.append("    All measured rails nominal — re-check connectors/module (seated? corroded?).")
        else:
            for f in faults:
                lines.append(f"    [X] {f}")
        lines.append("=" * 72)
        return "\n".join(lines)

    def render_plan(self, out_png: str | Path, net_keyword: Optional[str] = None) -> str:
        """Highlight plan points on the board image (optionally only one net group)."""
        pts = [mp.point for mp in self.plan]
        if net_keyword:
            pts = [tp for tp in pts if net_keyword.upper() in tp.net.upper()]
        return self.board.render_highlight(pts, out_png)


_SYMPTOM_KEYWORDS: Dict[str, List[str]] = {
    "camera_not_working": ["camera", "black screen", "no camera"],
    "no_network_signal": ["network", "signal", "no service", "sim not", "baseband", "imei"],
    "no_display": ["display", "screen black", "no image", "backlight"],
    "no_wifi_bluetooth": ["wifi", "bluetooth", "bt not"],
    "no_audio": ["audio", "speaker", "mic", "earpiece", "no sound"],
    "no_charging": ["charging", "chg", "no charge", "not charging"],
    "dead_phone_no_power": ["dead", "no power", "not turning", "no response"],
    "overheating": ["overheat", "hot", "heating"],
    "touch_not_working": ["touch", "ghost touch", "screen not responding"],
    "fast_battery_drain": ["battery drain", "fast drain"],
    "fingerprint_not_working": ["fingerprint", "fp"],
    "logo_stuck_boot_loop": ["boot loop", "logo stuck", "restart", "bootloop"],
}


def main_cli() -> None:
    """python schematic_diagnosis.py <flat.json> <pattern_id> [measure csv net=volts,...]"""
    import sys
    from app.hardware.boardview_loader import BoardView
    bv = BoardView.load(sys.argv[1])
    pid = sys.argv[2] if len(sys.argv) > 2 else "camera_not_working"
    diag = SchematicDiagnoser(bv)
    diag.plan_for_pattern(pid)
    if len(sys.argv) > 3:
        for item in sys.argv[3].split(","):
            net, v = item.split("=")
            for mp in diag.plan:
                if mp.point.net.upper() == net.strip().upper():
                    diag.set_measurement(diag.plan.index(mp), float(v))
    print(diag.generate_report())
    if diag.plan:
        png = diag.render_plan("schematic_plan.png")
        print(f"\nplan image -> {png}")


if __name__ == "__main__":
    main_cli()