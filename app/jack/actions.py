"""
Section 3 — Action tools (part 1: read-only device awareness).

Lets Jack answer "kaunsa device connected hai?", "last scan mein kya mila?",
"UART pe data aa raha hai?" by talking to the same hardware the app uses.

Nothing here writes to a phone. Anything that would (flash, FRP, IMEI, unlock)
must be added with risky=True so the brain asks Boss for confirmation first.
"""

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from app.jack.config import CONFIG_DIR
from app.jack.tools import Tool, ToolRegistry, _obj, _s

FTDI_IDS = ("0403:6001", "0403:6015", "0403:6010")       # FTDI USB-UART adapters
OTHER_UART_IDS = ("10C4:EA60", "1A86:7523", "067B:2303")  # CP210x, CH340, PL2303


def _run(cmd: List[str], timeout: int = 6) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip()
    except FileNotFoundError:
        return "NOT_INSTALLED"
    except Exception:
        return ""


def _adb_devices() -> List[Dict[str, str]]:
    out = _run(["adb", "devices", "-l"])
    if out == "NOT_INSTALLED":
        return [{"error": "adb installed nahi hai / PATH mein nahi hai"}]
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            info = {"serial": parts[0], "state": parts[1]}   # device | unauthorized | offline | recovery | sideload
            for p in parts[2:]:
                if ":" in p:
                    k, v = p.split(":", 1)
                    info[k] = v
            devices.append(info)
    return devices


def _adb_props(serial: str) -> Dict[str, str]:
    keys = {
        "brand": "ro.product.brand", "model": "ro.product.model", "device": "ro.product.device",
        "manufacturer": "ro.product.manufacturer", "android": "ro.build.version.release",
        "platform": "ro.board.platform", "hardware": "ro.hardware", "chipname": "ro.hardware.chipname",
        "soc_model": "ro.soc.model", "build": "ro.build.display.id", "security_patch": "ro.build.version.security_patch",
    }
    raw = _run(["adb", "-s", serial, "shell", "getprop"], timeout=8)
    props = dict(re.findall(r"\[(.+?)\]:\s*\[(.*?)\]", raw))
    return {name: props.get(key, "") for name, key in keys.items() if props.get(key)}


def _adb_battery(serial: str) -> Dict[str, Any]:
    raw = _run(["adb", "-s", serial, "shell", "dumpsys", "battery"], timeout=8)
    vals = dict(re.findall(r"^\s*([A-Za-z ]+):\s*(.+)$", raw, flags=re.MULTILINE))
    out: Dict[str, Any] = {}
    for k in ("level", "status", "health", "voltage", "temperature", "AC powered", "USB powered", "technology"):
        if k in vals:
            out[k.lower().replace(" ", "_")] = vals[k].strip()
    status_map = {"1": "unknown", "2": "charging", "3": "discharging", "4": "not charging", "5": "full"}
    health_map = {"1": "unknown", "2": "good", "3": "overheat", "4": "dead", "5": "over voltage",
                  "6": "failure", "7": "cold"}
    if "status" in out:
        out["status"] = status_map.get(out["status"], out["status"])
    if "health" in out:
        out["health"] = health_map.get(out["health"], out["health"])
    if "temperature" in out:
        try:
            out["temperature_c"] = int(out.pop("temperature")) / 10
        except ValueError:
            pass
    if "voltage" in out:
        out["voltage_mv"] = out.pop("voltage")
    return out


def check_connected_devices() -> Dict[str, Any]:
    """Everything plugged in right now: UART adapters, ADB, fastboot, EDL 9008."""
    result: Dict[str, Any] = {}

    # Serial ports
    uart, edl_ports, other = [], [], []
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            hwid = p.hwid.upper()
            entry = {"port": p.device, "description": p.description}
            if any(i in hwid for i in FTDI_IDS):
                uart.append({**entry, "adapter": "FTDI USB-UART"})
            elif any(i in hwid for i in OTHER_UART_IDS):
                uart.append({**entry, "adapter": "USB-UART (CP210x/CH340/PL2303)"})
            elif "05C6:9008" in hwid or "9008" in p.description.lower():
                edl_ports.append(entry)
            elif "USB" in hwid:
                other.append(entry)
    except Exception as e:
        result["serial_error"] = str(e)
    result["uart_adapters"] = uart
    if uart:
        result["uart_note"] = ("UART adapter connected hone ka matlab sirf adapter PC se juda hai. Phone ka "
                               "model/chipset tabhi pata chalega jab Fault Analyzer/HW Detect se boot log scan ho. "
                               "read_uart_live se check kar sakte ho ki phone se data aa raha hai ya nahi.")
    if other:
        result["other_usb_serial"] = other

    # ADB
    adb = _adb_devices()
    for d in adb:
        if d.get("state") == "device":
            d.update(_adb_props(d["serial"]))
            d["battery"] = _adb_battery(d["serial"])
        elif d.get("state") == "unauthorized":
            d["hint"] = "Phone screen pe 'Allow USB debugging' popup accept karo"
    result["adb_devices"] = adb

    # Fastboot
    fb = _run(["fastboot", "devices"], timeout=5)
    result["fastboot_devices"] = ([] if fb in ("", "NOT_INSTALLED") else
                                  [{"serial": l.split()[0], "mode": "fastboot"} for l in fb.splitlines() if l.strip()])

    # EDL 9008 (COM port, or WinUSB-bound without a COM port)
    edl = bool(edl_ports)
    if not edl:
        try:
            from app.hardware.edl_detector import find_edl_usb
            edl = find_edl_usb() is not None
        except Exception:
            pass
    result["edl_9008"] = {"connected": edl, "ports": edl_ports}

    result["summary"] = _summary(result)
    return result


def _summary(r: Dict[str, Any]) -> str:
    parts = []
    for u in r.get("uart_adapters", []):
        parts.append(f"{u['adapter']} on {u['port']}")
    for d in r.get("adb_devices", []):
        if d.get("state") == "device":
            parts.append(f"ADB phone: {d.get('brand', '')} {d.get('model', d['serial'])}".strip())
        elif "state" in d:
            parts.append(f"ADB device {d['serial']} ({d['state']})")
    for d in r.get("fastboot_devices", []):
        parts.append(f"Fastboot device {d['serial']}")
    if r.get("edl_9008", {}).get("connected"):
        parts.append("Qualcomm EDL 9008 device")
    return "; ".join(parts) if parts else "Kuch bhi connected nahi hai"


def _report_digest(path: str, max_chars: int = 2600) -> str:
    """Pull the useful part of a saved scan report (problems + device data), skipping banners."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    start = text.find("PHASE 1")
    text = text[start:] if start >= 0 else text
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or set(s) <= set("=─═-") or "BOOT THE PHONE NOW" in s:
            continue
        lines.append(s)
    return "\n".join(lines)[:max_chars]


def get_last_scan(scan_type: str = "") -> Dict[str, Any]:
    """Most recent scan from the app's history (optionally UART / ADB only) with report digest."""
    try:
        hist = json.loads((CONFIG_DIR / "repair_history.json").read_text(encoding="utf-8-sig"))
    except Exception as e:
        return {"found": False, "error": str(e)}
    records = hist.get("detections", []) + hist.get("repairs", [])
    st = scan_type.strip().upper()
    if st and st not in ("ANY", "LATEST", "ALL"):
        records = [r for r in records if st in str(r.get("type", "")).upper()]
    if not records:
        return {"found": False, "message": "Koi scan record nahi mila"}
    rec = max(records, key=lambda r: str(r.get("date", "")))
    out = {"found": True, **{k: v for k, v in rec.items() if k not in ("raw_log_file", "id")}}
    if rec.get("report_file"):
        out["report_digest"] = _report_digest(rec["report_file"])
        out.pop("report_file", None)
    return out


def read_uart_live(seconds: int = 5, port: str = "", baud: int = 115200) -> Dict[str, Any]:
    """Listen on the UART adapter for a few seconds — is the phone sending anything?"""
    seconds = max(1, min(int(seconds or 5), 15))
    try:
        import serial
        import serial.tools.list_ports
    except ImportError:
        return {"error": "pyserial installed nahi hai"}
    if not port:
        for p in serial.tools.list_ports.comports():
            if any(i in p.hwid.upper() for i in FTDI_IDS + OTHER_UART_IDS):
                port = p.device
                break
    if not port:
        return {"error": "Koi UART adapter connected nahi hai"}
    try:
        with serial.Serial(port, int(baud), timeout=0.3) as ser:
            buf = bytearray()
            end = time.time() + seconds
            while time.time() < end and len(buf) < 200_000:
                buf += ser.read(4096)
    except Exception as e:
        msg = str(e)
        if "Access is denied" in msg or "PermissionError" in msg:
            return {"port": port, "error": f"{port} busy hai — shayad koi scan page use kar raha hai. Scan rok ke try karo."}
        return {"port": port, "error": msg}
    text = buf.decode("utf-8", errors="replace")
    lines = [l for l in text.splitlines() if l.strip()]
    return {
        "port": port, "baud": baud, "listened_seconds": seconds,
        "bytes_received": len(buf), "lines": len(lines),
        "receiving_data": len(buf) > 0,
        "last_lines": lines[-25:],
        "hint": ("Phone se koi data nahi aaya — phone OFF hai, ya TX/RX/GND wiring check karo, ya phone ko power on/reboot karo."
                 if not buf else "Phone UART pe data bhej raha hai."),
    }


def _lines_digest(lines: List[str], max_chars: int = 3000) -> str:
    """Compact a scan report for the LLM: skip banners and giant raw dumps."""
    text = "\n".join(lines)
    start = text.find("PHASE 1")
    if start < 0:
        start = text.find("SCANNING DEVICE")
    text = text[start:] if start >= 0 else text
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if not s or set(s) <= set("=─═-") or "BOOT THE PHONE NOW" in s:
            continue
        if s.startswith(("Raw Text:", "Raw Hex:")):
            continue
        keep.append(s[:240])
    return "\n".join(keep)[:max_chars]


def _find_uart_port() -> str:
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            if any(i in p.hwid.upper() for i in FTDI_IDS + OTHER_UART_IDS):
                return p.device
    except Exception:
        pass
    return ""


def run_hw_detect(port: str = "", baud: int = 921600, duration: int = 90,
                  _emit=None, _progress=None, _stop=None) -> Dict[str, Any]:
    """Same scan as the HW Detect page (UART boot-log capture + full hardware report)."""
    from app.hardware.scan_runners import run_uart_scan
    port = port or _find_uart_port()
    if not port:
        return {"error": "Koi UART adapter (FTDI/CH340/CP210x) connected nahi hai"}
    duration = max(20, min(int(duration or 90), 240))
    res = run_uart_scan(port, int(baud or 921600), duration, emit=_emit or (lambda l: None),
                        progress=_progress, stop_event=_stop)
    if res.get("stopped"):
        return {"stopped": True, "message": "Boss ne scan rok diya"}
    return {"scan": "HW Detect (UART)", "port": port, "detected": res.get("detected"),
            "device": res.get("device_name"), "faults_count": res.get("faults_count"),
            "summary": res.get("summary_text"), "saved_report": res.get("log_path"),
            "report_digest": _lines_digest(res["lines"])}


def run_adb_detect(_emit=None, _progress=None, _stop=None) -> Dict[str, Any]:
    """Same scan as the ADB Detect page (full ADB diagnosis + smart report)."""
    from app.hardware.scan_runners import run_adb_scan
    res = run_adb_scan(emit=_emit or (lambda l: None), progress=_progress)
    if res.get("error"):
        return {"scan": "ADB Detect", "error": res["error"]}
    return {"scan": "ADB Detect", "device": res.get("device_name"), "faults_count": res.get("faults_count"),
            "summary": res.get("summary_text"), "saved_report": res.get("log_path"),
            "report_digest": _lines_digest(res["lines"])}


def build_action_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.add(Tool(
        name="check_connected_devices",
        description="Check what is physically connected to this PC RIGHT NOW: UART adapters (FTDI on COM ports), "
                    "ADB phones (with brand, model, chipset, Android version, battery), fastboot devices, and "
                    "Qualcomm EDL 9008. Use whenever Boss asks about the connected/current device.",
        parameters=_obj({}, []),
        handler=check_connected_devices,
        label="Connected devices check kar raha hoon",
    ))
    reg.add(Tool(
        name="get_last_scan",
        description="Get the most recent scan done in the app (UART boot-log scan, ADB scan, etc.) with its "
                    "report digest: chipset detected, problems found, PMIC reset reasons, voltage rails, "
                    "healthy components. Use for 'last scan', 'abhi wale phone mein kya mila', or to identify "
                    "a phone connected over UART.",
        parameters=_obj({"scan_type": _s("Optional filter: UART, ADB, POWER, BATTERY. Empty = latest of any type")}, []),
        handler=get_last_scan,
        label="Last scan report padh raha hoon",
    ))
    reg.add(Tool(
        name="read_uart_live",
        description="Listen to the UART adapter for a few seconds to see whether the phone is sending boot/kernel "
                    "logs right now (read-only). Useful to check wiring or whether the phone is alive.",
        parameters=_obj({
            "seconds": {"type": "integer", "description": "How long to listen, 1-15 (default 5)"},
            "port": _s("Optional COM port, e.g. COM3. Auto-detected if empty"),
        }, []),
        handler=read_uart_live,
        label="UART pe sun raha hoon",
    ))
    reg.add(Tool(
        name="run_hw_detect",
        description="Run the full HW Detect scan (same as the HW Detect page): listens on the UART adapter while "
                    "Boss boots the phone, then reports chipset, PMIC, RAM/storage, voltage rails, boot stage and "
                    "faults. Read-only. Takes 'duration' seconds — tell Boss to boot the phone. Use when Boss asks "
                    "to run HW detect / UART scan / boot log scan.",
        parameters=_obj({
            "duration": {"type": "integer", "description": "Listen time in seconds, 45-240 (default 90)"},
            "port": _s("Optional COM port. Auto-detected if empty"),
            "baud": {"type": "integer", "description": "Optional baud, 115200 or 921600 (default 921600)"},
        }, []),
        handler=run_hw_detect,
        label="HW Detect chal raha hai — phone boot karo",
        streams=True,
    ))
    reg.add(Tool(
        name="run_adb_detect",
        description="Run the full ADB Detect scan (same as the ADB Detect page) on the phone connected over ADB: "
                    "battery, sensors, display, audio, connectivity, storage, logcat errors and faults. Read-only.",
        parameters=_obj({}, []),
        handler=run_adb_detect,
        label="ADB Detect chal raha hai",
        streams=True,
    ))
    return reg
