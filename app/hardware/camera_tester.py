"""
camera_tester.py — Camera functional evidence collection over ADB.

Collects software evidence for a "camera not working" complaint:

  - which cameras are enumerated (dumpsys media.camera / cameraservice)
  - HAL / provider status per camera id
  - live logcat camera events (CameraService, seninf, camX, ois...)
  - /dev/video nodes + V4L2 devices
  - props relevant to camera HAL

Then hands the evidence to `SchematicDiagnoser` so the technician can go
straight to probing the schematic test points (AVDD / DOVDD / DVDD / VCAMD /
MCLK / I2C nets) instead of guessing.

Does not require root. Won't touch the phone — read-only commands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Evidence model
# ---------------------------------------------------------------------------

@dataclass
class CameraEvidence:
    serial: str = ""
    camera_raw: str = ""                     # dumpsys media.camera / cameraservice
    camera_ids: List[str] = field(default_factory=list)
    provider_status: List[str] = field(default_factory=list)   # per camera id lines
    logcat_lines: List[str] = field(default_factory=list)
    video_devices: List[str] = field(default_factory=list)
    hal_props: dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    summary: str = ""

    # -- helpers -----------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "serial": self.serial,
            "camera_ids": self.camera_ids,
            "provider_status": self.provider_status[:8],
            "logcat_camera_lines": self.logcat_lines[:50],
            "video_devices": self.video_devices,
            "hal_props": self.hal_props,
            "errors": self.errors,
            "summary": self.summary,
        }


_CAMERA_ERROR_PATTERNS = [
    (re.compile(r"(?i)provider.*fail|fail.*provider|service.*crash|died", re.I),
     "Camera provider crashed / not running"),
    (re.compile(r"(?i)no camera|0 camera|camera.*not found|no.*device", re.I),
     "No camera devices enumerated"),
    (re.compile(r"(?i)hal.*error|error.*hal|bringup|init.*fail", re.I),
     "Camera HAL error"),
    (re.compile(r"(?i)seninf|cci|i2c.*fail|timeout", re.I),
     "Sensor interface (CIS/CCI) failure"),
    (re.compile(r"(?i)ois|actuator|focus.*fail", re.I),
     "OIS/actuator/focus issue"),
    (re.compile(r"(?i)fpga|avdd|dvdd|dovdd|regulator|pmic.*fail", re.I),
     "Camera power rail (AVDD/DOVDD/DVDD) fault"),
    (re.compile(r"(?i)eeprom|flash|torch.*fail", re.I),
     "EEPROM / flash failure"),
]


def _run_adb(args: List[str], timeout: int = 12) -> str:
    """Run an adb command without shell=True (see security review)."""
    import subprocess
    try:
        r = subprocess.run(["adb"] + args, capture_output=True, text=True,
                           timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def collect_camera_evidence(serial: str = "") -> CameraEvidence:
    """Gather camera evidence from a connected device (read-only)."""
    ev = CameraEvidence(serial=serial)
    prefix = ["-s", serial] if serial else []

    raw = _run_adb(prefix + ["shell", "dumpsys", "media.camera"], timeout=15)
    if not raw or len(raw) < 20:
        raw = _run_adb(prefix + ["shell", "dumpsys", "cameraservice"], timeout=15)
    ev.camera_raw = raw

    # Camera ids — try several shapes
    ids = re.findall(r"(?i)(?:Camera|CAM)\s*(?:id|ID)?\s*[:#]\s*(\d+)", raw)
    ids += re.findall(r"(?i)CameraId\s*[:=]\s*(\d+)", raw)
    ev.camera_ids = sorted(set(ids), key=lambda x: int(x))

    for i, cid in enumerate(ev.camera_ids[:8]):
        m = re.search(rf"(?s).{{200}}Camera\s*{re.escape(cid)}.{{400}}", raw)
        if m:
            snippet = re.sub(r"\s+", " ", m.group(0)).strip()
            status = ""
            for pat, label in _CAMERA_ERROR_PATTERNS:
                if pat.search(snippet):
                    status = label
                    break
            ev.provider_status.append(f"cam {cid}: {status or 'enumerated (no obvious error)'}")

    # Live logcat camera events (last 3000 main-buffer lines, filtered client-side)
    lc = _run_adb(prefix + ["logcat", "-d", "-b", "main", "-t", "3000"], timeout=25)
    if lc:
        for line in lc.splitlines():
            low = line.lower()
            if any(k in low for k in ("camera", "camsvc", "seninf", "camx", "ois",
                                      "provider", "cameraicp", "cci.", "mclk")):
                ev.logcat_lines.append(line[:220])
        ev.logcat_lines = ev.logcat_lines[:120]

    # /dev/video nodes
    vd = _run_adb(prefix + ["shell", "ls", "-l", "/dev/video*"], timeout=8)
    ev.video_devices = [ln.strip() for ln in vd.splitlines() if "video" in ln][:15]

    # HAL-relevant props
    props = _run_adb(prefix + ["shell", "getprop"], timeout=10)
    for ln in props.splitlines():
        if any(k in ln.lower() for k in ("camera", "camsvc", "vendor.camera")):
            if "=" in ln:
                k, _, v = ln.partition("=")
                ev.hal_props[k.strip()] = v.strip().strip('"')

    ev.errors = _analyze_errors(ev)
    ev.summary = _summarize(ev)
    return ev


def _analyze_errors(ev: CameraEvidence) -> List[str]:
    errors: List[str] = []
    blob = "\n".join([ev.camera_raw[:6000], "\n".join(ev.logcat_lines)])
    for pat, label in _CAMERA_ERROR_PATTERNS:
        if pat.search(blob):
            errors.append(label)
    return errors


def _summarize(ev: CameraEvidence) -> str:
    if not ev.camera_ids:
        if ev.camera_raw and ev.errors:
            return "Camera HAL responds but NO cameras enumerated → service/panel-level fault"
        return "No camera service output — HAL may be down / device in unsupported state"
    if ev.errors:
        return f"Cameras found ({len(ev.camera_ids)}) but errors seen: {ev.errors[0]}"
    return f"Cameras enumerated OK ({', '.join(ev.camera_ids)}) — software layer looks healthy"


def diagnose_camera(serial: str = "", boardview_path: Optional[str] = None,
                    pattern_id: str = "camera_not_working") -> dict:
    """
    Full camera diagnosis: ADB evidence + schematic test plan (if board loaded).

    Returns {"evidence": {...}, "test_plan": [...], "report": "...", "image": "..."}
    """
    from app.hardware.boardview_loader import BoardView
    from app.hardware.schematic_diagnosis import SchematicDiagnoser

    ev = collect_camera_evidence(serial)
    out: dict = {"evidence": ev.to_dict(), "test_plan": [], "report": "", "image": "",
                 "verdict": ""}

    out["verdict"] = ev.summary
    if ev.errors:
        out["verdict"] += f" — {ev.errors[0]}"

    if boardview_path:
        bv = BoardView.load(boardview_path)
        diag = SchematicDiagnoser(bv)
        diag.plan_for_pattern(pattern_id)
        out["test_plan"] = [mp.to_dict() for mp in diag.plan]
        out["report"] = diag.generate_report()
        if out["test_plan"]:
            out["report"] += f"\n\nADB camera evidence:\n  {ev.summary}\n"
            out["image"] = diag.render_plan("camera_test_plan.png")
    else:
        out["report"] = (
            f"Camera evidence summary:\n  {ev.summary}\n"
            "No boardview loaded — pass boardview_path (flat-dump JSON) to get "
            "schematic test points."
        )
    return out


if __name__ == "__main__":
    import sys
    import json
    res = diagnose_camera(sys.argv[1] if len(sys.argv) > 1 else "",
                          sys.argv[2] if len(sys.argv) > 2 else None)
    print(json.dumps(res, indent=2, ensure_ascii=False)[:4000])