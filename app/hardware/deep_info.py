"""
Deep device info + health report (ADB, software-only).

The main ADB detector already pulls a lot. This adds the *extra* identity /
health fields a technician asks for — IMEI, SIM, bootloader/root state, display
panel, and a clean **Battery + Storage health** verdict (wear %, life left,
replace-or-not) — without touching the big detector.

Needs: phone booted + USB debugging ON. Every read fails soft to "N/A".
"""

from typing import Callable, Dict, List, Optional

from app.hardware.adb_detector import _run_adb, _shell, _safe_int, _safe_float


def _p(cb, pct, msg):
    if cb:
        try:
            cb(pct, msg)
        except Exception:
            pass


def _getprop(name: str) -> str:
    v = _shell(f"getprop {name}").strip()
    return v if v and v.lower() != "null" else ""


def _cat(path: str) -> str:
    v = _shell(f"cat {path} 2>/dev/null").strip()
    return v if v and "No such" not in v else ""


# ── identity / system ────────────────────────────────────────────────────────

def _imei() -> str:
    """IMEI via service call (often blocked on Android 10+ without privilege)."""
    for slot in ("1", "2"):
        out = _shell(f"service call iphonesubinfo {slot}")
        digits = ""
        # parcel dump: pull ASCII digits from the quoted columns
        import re
        for m in re.findall(r"'([0-9. ]+)'", out):
            digits += re.sub(r"[^0-9]", "", m)
        if len(digits) >= 14:
            return digits[:15]
    tele = _shell("dumpsys iphonesubinfo")
    import re
    m = re.search(r"Device ID[ =]*([0-9]{14,16})", tele)
    return m.group(1) if m else ""


def collect_identity(cb=None) -> Dict[str, str]:
    _p(cb, 0.1, "Identity / build…")
    locked = _getprop("ro.boot.flash.locked")
    vbstate = _getprop("ro.boot.verifiedbootstate")
    vbmeta = _getprop("ro.boot.vbmeta.device_state")
    rooted = bool(_shell("which su || ls /sbin/su /system/xbin/su 2>/dev/null").strip())
    return {
        "Brand / Model": f"{_getprop('ro.product.brand')} {_getprop('ro.product.model')}".strip() or "N/A",
        "Marketing name": _getprop("ro.product.marketname") or _getprop("ro.config.marketing_name") or "N/A",
        "Android": f"{_getprop('ro.build.version.release')} (SDK {_getprop('ro.build.version.sdk')})",
        "Security patch": _getprop("ro.build.version.security_patch") or "N/A",
        "Build": _getprop("ro.build.fingerprint") or "N/A",
        "Serial": _getprop("ro.serialno") or "N/A",
        "IMEI": _imei() or "N/A (locked/permission)",
        "Chipset": _getprop("ro.board.platform") or _getprop("ro.hardware") or "N/A",
        "Baseband / modem": _getprop("gsm.version.baseband") or "N/A",
        "Bootloader": _getprop("ro.bootloader") or "N/A",
        "Bootloader locked": {"1": "LOCKED", "0": "UNLOCKED"}.get(locked, locked or "N/A"),
        "Verified boot": vbstate or vbmeta or "N/A",
        "Root (su)": "YES" if rooted else "no",
    }


def collect_sim_network(cb=None) -> Dict[str, str]:
    _p(cb, 0.35, "SIM / network…")
    sim = _getprop("gsm.sim.state")
    return {
        "SIM state": sim or "N/A",
        "Operator": _getprop("gsm.operator.alpha") or _getprop("gsm.sim.operator.alpha") or "N/A",
        "Network type": _getprop("gsm.network.type") or "N/A",
        "Data registration": _getprop("gsm.operator.iso-country").upper() or "N/A",
        "Phone radio": "on" if _getprop("ril.radiostate") in ("", "RADIO_ON") else _getprop("ril.radiostate"),
    }


def collect_display(cb=None) -> Dict[str, str]:
    _p(cb, 0.55, "Display panel…")
    import re
    disp = _shell("dumpsys display")
    res = re.search(r"(\d{3,4} x \d{3,4})", disp)
    dens = re.search(r"density (\d+)", disp)
    fps = re.search(r"fps=([\d.]+)", disp) or re.search(r"(\d{2,3}\.\d+) fps", disp)
    panel = (_cat("/sys/class/lcd/panel/panel_name") or _cat("/sys/class/graphics/fb0/lcd_type")
             or _getprop("vendor.display.lcd_model") or _getprop("ro.boot.ddr_size"))
    return {
        "Resolution": res.group(1) if res else "N/A",
        "Density (dpi)": dens.group(1) if dens else "N/A",
        "Refresh rate": (fps.group(1) + " Hz") if fps else "N/A",
        "Panel ID": panel or "N/A",
    }


def collect_memory(cb=None) -> Dict[str, str]:
    _p(cb, 0.7, "RAM / memory…")
    mem = _shell("cat /proc/meminfo")
    import re
    tot = re.search(r"MemTotal:\s+(\d+)", mem)
    total_mb = int(tot.group(1)) // 1024 if tot else 0
    # round up to the marketed size (e.g. 3760MB -> 4GB)
    gb = 0
    for g in (1, 2, 3, 4, 6, 8, 12, 16, 18, 24):
        if total_mb <= g * 1024:
            gb = g
            break
    ddr = _getprop("ro.boot.ddr_type") or _getprop("vendor.ddr.type")
    return {
        "RAM total": (f"{gb} GB ({total_mb} MB)" if gb else f"{total_mb} MB") if total_mb else "N/A",
        "RAM type": ddr or "N/A (phone reports nahi karta)",
    }


# ── health report (battery + storage) ────────────────────────────────────────

_UFS_LIFE = {  # life_time_estimation hex -> used band
    "0x01": "0–10% used", "0x02": "10–20% used", "0x03": "20–30% used",
    "0x04": "30–40% used", "0x05": "40–50% used", "0x06": "50–60% used",
    "0x07": "60–70% used", "0x08": "70–80% used", "0x09": "80–90% used",
    "0x0a": "90–100% used", "0x0b": "EXCEEDED — replace",
}
_EOL = {"0x01": "Normal", "0x02": "⚠ Warning (~80% life used)", "0x03": "🔴 Urgent — replace"}


def collect_health(cb=None) -> Dict[str, object]:
    _p(cb, 0.85, "Battery + storage health…")
    b = "/sys/class/power_supply/battery/"
    full = _safe_int(_cat(b + "charge_full"))
    design = _safe_int(_cat(b + "charge_full_design"))
    cycles = _safe_int(_cat(b + "cycle_count"))
    temp = _safe_float(_cat(b + "temp")) / 10.0
    volt = _safe_int(_cat(b + "voltage_now")) // 1000
    status = _cat(b + "status")
    health_pct = round(full / design * 100) if full and design else 0

    batt_verdict = "N/A"
    if health_pct:
        if health_pct >= 90:
            batt_verdict = f"✅ Achhi ({health_pct}%)"
        elif health_pct >= 80:
            batt_verdict = f"🟡 Theek ({health_pct}%) — nazar rakho"
        else:
            batt_verdict = f"🔴 Weak ({health_pct}%) — replace recommended"
    if cycles:
        batt_verdict += f" · {cycles} cycles"

    # storage: UFS (sda) + eMMC (mmcblk0)
    def dev(path):
        return _cat(f"/sys/class/block/{path}/device/")

    pre_eol = (_cat("/sys/class/block/sda/device/pre_eol_info")
               or _cat("/sys/block/mmcblk0/device/pre_eol_info")).lower()
    life_a = (_cat("/sys/class/block/sda/device/life_time_estimation_type_a")
              or _cat("/sys/block/mmcblk0/device/life_time")).lower()
    stor_model = (_cat("/sys/class/block/sda/device/model")
                  or _cat("/sys/block/mmcblk0/device/name") or "N/A")
    stor_type = "UFS" if _cat("/sys/class/block/sda/device/model") else (
        "eMMC" if _cat("/sys/block/mmcblk0/device/name") else "N/A")

    stor_verdict = "N/A"
    if pre_eol in _EOL or life_a in _UFS_LIFE:
        eol = _EOL.get(pre_eol, "")
        life = _UFS_LIFE.get(life_a, "")
        stor_verdict = " · ".join(x for x in (eol, life) if x) or "readable"

    return {
        "battery": {
            "Health": batt_verdict,
            "Capacity now / design": f"{full//1000 or '?'} / {design//1000 or '?'} mAh" if design else "N/A",
            "Cycles": str(cycles) if cycles else "N/A",
            "Voltage": f"{volt} mV" if volt else "N/A",
            "Temp": f"{temp:.1f} °C" if temp else "N/A",
            "Status": status or "N/A",
        },
        "storage": {
            "Type / model": f"{stor_type} · {stor_model}",
            "Health": stor_verdict,
        },
    }


# ── orchestrator + formatter ─────────────────────────────────────────────────

def collect_deep_info(callback: Optional[Callable] = None) -> Dict[str, object]:
    """Run every collector. Returns a nested dict (or {'error': ...})."""
    _p(callback, 0.02, "Checking ADB device…")
    dev = _run_adb("devices")
    lines = [l for l in dev.splitlines()[1:] if l.strip() and "\tdevice" in l]
    if not lines:
        if "unauthorized" in dev:
            return {"error": "Phone pe 'USB debugging allow' ka popup accept karo"}
        return {"error": "Koi ADB device nahi — USB debugging ON karke phone jodo"}
    info = {
        "Identity": collect_identity(callback),
        "SIM / Network": collect_sim_network(callback),
        "Display": collect_display(callback),
        "Memory": collect_memory(callback),
        "Health": collect_health(callback),
    }
    _p(callback, 1.0, "Deep info ready")
    return info


def format_deep_report(info: Dict[str, object]) -> str:
    if "error" in info:
        return f"❌ {info['error']}"
    L: List[str] = []
    L.append("═" * 46)
    L.append("  DEEP DEVICE INFO")
    L.append("═" * 46)
    for section in ("Identity", "SIM / Network", "Display", "Memory"):
        L.append("")
        L.append(f"── {section} ──")
        for k, v in info.get(section, {}).items():
            L.append(f"  {k:<22} : {v}")
    h = info.get("Health", {})
    L.append("")
    L.append("── 🔋 Battery health ──")
    for k, v in h.get("battery", {}).items():
        L.append(f"  {k:<22} : {v}")
    L.append("")
    L.append("── 💾 Storage health ──")
    for k, v in h.get("storage", {}).items():
        L.append(f"  {k:<22} : {v}")
    L.append("")
    L.append("═" * 46)
    return "\n".join(L)
