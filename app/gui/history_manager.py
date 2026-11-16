"""
Persistent Repair & Detection History Manager.

Stores all repair records and detection results in JSON files
so history survives across app restarts.

Detection history: config/detection_history.json
Repair history:    config/repair_history.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_HISTORY_FILE = _CONFIG_DIR / "repair_history.json"
_DETECTION_HISTORY_FILE = _CONFIG_DIR / "detection_history.json"


# ═══════════════════════════════════════════════════════════════
#  REPAIR HISTORY  (repair_history.json)
# ═══════════════════════════════════════════════════════════════

def _load_raw() -> Dict[str, Any]:
    """Load raw history data from repair_history.json."""
    try:
        if _HISTORY_FILE.exists():
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[HistoryManager] Load error: {e}")
    return {"repairs": [], "detections": []}


def _save_raw(data: Dict[str, Any]) -> None:
    """Save raw history data to repair_history.json."""
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[HistoryManager] Save error: {e}")


def load_repairs() -> List[Dict[str, Any]]:
    """Load all repair records."""
    return _load_raw().get("repairs", [])


def save_repairs(repairs: List[Dict[str, Any]]) -> None:
    """Save all repair records (full overwrite)."""
    data = _load_raw()
    data["repairs"] = repairs
    _save_raw(data)


def add_repair(entry: Dict[str, Any]) -> None:
    """Add a single repair record."""
    data = _load_raw()
    data["repairs"].append(entry)
    _save_raw(data)


# ═══════════════════════════════════════════════════════════════
#  DETECTION HISTORY  (detection_history.json)
# ═══════════════════════════════════════════════════════════════

def _load_detection_history() -> List[Dict[str, Any]]:
    """Load detection history from detection_history.json."""
    try:
        if _DETECTION_HISTORY_FILE.exists():
            with open(_DETECTION_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return data.get("detections", [])
    except Exception as e:
        print(f"[HistoryManager] Detection history load error: {e}")
    return []


def _save_detection_history(detections: List[Dict[str, Any]]) -> None:
    """Save detection history to detection_history.json."""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_DETECTION_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"detections": detections}, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[HistoryManager] Detection history save error: {e}")


def load_detections() -> List[Dict[str, Any]]:
    """Load all detection records (from both files, merged)."""
    # Primary source: detection_history.json
    det = _load_detection_history()
    # Also include legacy detections from repair_history.json
    legacy = _load_raw().get("detections", [])
    # Merge by id (avoid duplicates)
    seen_ids = {d.get("id") for d in det}
    for entry in legacy:
        if entry.get("id") not in seen_ids:
            det.append(entry)
            seen_ids.add(entry.get("id"))
    return det


def add_detection(detection_type: str,
                  device_name: str = "",
                  summary: str = "",
                  faults_count: int = 0,
                  faults_summary: str = "",
                  report_file: str = "",
                  extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Add a detection record to history.

    detection_type: 'UART', 'ADB', 'EDL', 'JTAG', 'Manual'
    Returns the saved entry dict.
    """
    entry = {
        "id": int(datetime.now().timestamp() * 1000),
        "type": detection_type,
        "device_name": device_name or "Unknown Device",
        "summary": summary,
        "faults_count": faults_count,
        "faults_summary": faults_summary,
        "report_file": report_file,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "Completed",
    }
    if extra:
        entry.update(extra)

    # Save to detection_history.json (primary)
    det = _load_detection_history()
    det.append(entry)
    _save_detection_history(det)

    # Also save to repair_history.json (legacy compatibility)
    data = _load_raw()
    data["detections"].append(entry)
    _save_raw(data)

    return entry


def delete_detection(detection_id: int) -> None:
    """Delete a detection record by id from both files."""
    # Remove from detection_history.json
    det = _load_detection_history()
    det = [d for d in det if d.get("id") != detection_id]
    _save_detection_history(det)

    # Remove from repair_history.json
    data = _load_raw()
    data["detections"] = [d for d in data["detections"] if d.get("id") != detection_id]
    _save_raw(data)


# ═══════════════════════════════════════════════════════════════
#  SIMPLE API (used by history_page.py)
# ═══════════════════════════════════════════════════════════════

def get_history() -> list:
    """Read all past detections, sorted newest first."""
    detections = load_detections()
    detections.sort(key=lambda d: d.get("date", ""), reverse=True)
    return detections


def clear_history() -> None:
    """Clear all detection history from both files."""
    _save_detection_history([])
    data = _load_raw()
    data["detections"] = []
    _save_raw(data)


# ═══════════════════════════════════════════════════════════════
#  UNIQUE LOG FILE PATHS  (saves to config/logs/)
# ═══════════════════════════════════════════════════════════════

_LOGS_DIR = _CONFIG_DIR / "logs"


def get_unique_log_path(prefix: str, ext: str = ".txt") -> Path:
    """Return a unique log file path like config/logs/adb_log_20260706_143022.txt.

    Ensures logs are never overwritten — each scan gets its own file.
    """
    _LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _LOGS_DIR / f"{prefix}_{timestamp}{ext}"
