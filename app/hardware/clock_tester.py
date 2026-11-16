"""
Oscillator / Clock Testing Module for Mobile Repair Technicians.

Reads clock sources, PLL status, RTC accuracy, and XO calibration
data from a connected Android device via ADB.  Compares measured
values against known-good databases for Qualcomm Snapdragon,
MediaTek Dimensity, and Samsung Exynos chipsets, then produces a
per-subsystem health verdict.

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
          Root/engineering builds give best results (debugfs access).
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class ClockSourceInfo:
    """Single entry from the kernel clock tree."""
    name: str = ""
    frequency_hz: float = 0.0
    enabled: bool = False
    parent: str = ""
    rate_hz: float = 0.0
    type: str = "UNKNOWN"               # XTAL / PLL / RCXO / DCXO / TCXO


@dataclass
class RTCInfo:
    """Real-Time Clock subsystem data."""
    device_name: str = ""
    time_str: str = ""
    alarm_str: str = ""
    drift_ms: float = 0.0
    accuracy_ppm: float = 0.0
    status: str = "UNKNOWN"             # OK / WARNING / FAULT / UNKNOWN


@dataclass
class PLLInfo:
    """Phase-Locked Loop status."""
    name: str = ""
    frequency_hz: float = 0.0
    locked: bool = False
    source: str = ""
    status: str = "UNKNOWN"


@dataclass
class XOCalibration:
    """Crystal Oscillator calibration state."""
    type: str = ""                      # DCXO / TCXO / XO
    frequency_hz: float = 0.0
    trim_value: int = 0
    calibrated: bool = False
    temperature_comp: bool = False
    status: str = "UNKNOWN"


@dataclass
class ClockTestResult:
    """Aggregated result from the full clock-subsystem test."""
    connected: bool = False
    error: Optional[str] = None
    clock_sources: List[ClockSourceInfo] = field(default_factory=list)
    rtc_info: RTCInfo = field(default_factory=RTCInfo)
    pll_status: List[PLLInfo] = field(default_factory=list)
    xo_calibration: XOCalibration = field(default_factory=XOCalibration)
    overall_health: str = "UNKNOWN"
    faults: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
#  Known-good frequency databases
# ---------------------------------------------------------------------------

# Common reference-clock frequencies (Hz) used by major SoC vendors.
COMMON_XO_FREQUENCIES: Dict[str, float] = {
    "qualcomm_xo":      19_200_000.0,      # 19.2 MHz — Snapdragon primary XO
    "qualcomm_sleep":       32_768.0,       # 32.768 kHz — sleep clock
    "mediatek_xo":      26_000_000.0,       # 26 MHz — MediaTek primary XO
    "mediatek_xo_alt":  19_200_000.0,       # 19.2 MHz — some MTK designs
    "mediatek_rtc":         32_768.0,
    "samsung_xo":       26_000_000.0,       # 26 MHz — Exynos primary
    "samsung_xo_alt":   19_200_000.0,
    "samsung_rtc":          32_768.0,
    "rtc_standard":         32_768.0,       # universal 32.768 kHz RTC crystal
    "tcxo_standard":    19_200_000.0,
    "dcxo_standard":    38_400_000.0,       # doubled XO seen on some SDM845+
}

# Expected XO frequency per SoC family (pattern → Hz).
SOC_XO_MAP: Dict[str, float] = {
    "sdm845":    19_200_000.0,
    "sm8150":    19_200_000.0,
    "sm8250":    19_200_000.0,
    "sm8350":    19_200_000.0,
    "sm8450":    19_200_000.0,
    "sm8550":    19_200_000.0,
    "sm8650":    19_200_000.0,
    "sm7150":    19_200_000.0,
    "sm7250":    19_200_000.0,
    "sm7325":    19_200_000.0,
    "sm6150":    19_200_000.0,
    "sm6350":    19_200_000.0,
    "sm6375":    19_200_000.0,
    "sdm660":    19_200_000.0,
    "sdm710":    19_200_000.0,
    "msm8998":   19_200_000.0,
    "msm8996":   19_200_000.0,
    "msm8953":   19_200_000.0,
    "mt6893":    26_000_000.0,
    "mt6895":    26_000_000.0,
    "mt6983":    26_000_000.0,
    "mt6985":    26_000_000.0,
    "mt6789":    26_000_000.0,
    "mt6833":    26_000_000.0,
    "mt6877":    26_000_000.0,
    "exynos2100": 26_000_000.0,
    "exynos2200": 26_000_000.0,
    "exynos1380": 26_000_000.0,
    # --- Unisoc ---
    "t820":     26_000_000.0,
    "t760":     26_000_000.0,
    "t618":     26_000_000.0,
    "t616":     26_000_000.0,
    "t612":     26_000_000.0,
    "t606":     26_000_000.0,
    "sc9863a":  26_000_000.0,
    # --- Google Tensor (Samsung-designed) ---
    "g4":       19_200_000.0,
    "g3":       19_200_000.0,
    "g2":       19_200_000.0,
    # --- HiSilicon Kirin ---
    "kirin9000": 19_200_000.0,
    "kirin990":  19_200_000.0,
    "kirin980":  19_200_000.0,
    "kirin810":  19_200_000.0,
    "kirin710":  19_200_000.0,
}

# Known PLL configurations for Snapdragon chipsets.
# name_pattern → (expected_source, min_freq_hz, max_freq_hz)
KNOWN_PLL_CONFIGS: Dict[str, Tuple[str, float, float]] = {
    "gpll0":      ("xo",   600_000_000.0,   600_000_000.0),
    "gpll1":      ("xo",   480_000_000.0,   480_000_000.0),
    "gpll2":      ("xo",   930_000_000.0,  1_000_000_000.0),
    "gpll3":      ("xo",   930_000_000.0,  1_000_000_000.0),
    "gpll4":      ("xo",   800_000_000.0,   810_000_000.0),
    "gpll6":      ("xo",  1_080_000_000.0, 1_200_000_000.0),
    "cpu_pll":    ("xo",  1_000_000_000.0, 3_200_000_000.0),
    "perfcl_pll": ("xo",  1_500_000_000.0, 3_200_000_000.0),
    "pwrcl_pll":  ("xo",   800_000_000.0, 2_200_000_000.0),
    "nss_crypto_pll": ("xo", 600_000_000.0, 800_000_000.0),
    "gpu_cc_pll0": ("xo",  500_000_000.0,  900_000_000.0),
    "gpu_cc_pll1": ("xo",  500_000_000.0,  900_000_000.0),
    "disp_cc_pll0": ("xo", 600_000_000.0, 1_500_000_000.0),
    "cam_cc_pll0":  ("xo", 600_000_000.0, 1_200_000_000.0),
    "cam_cc_pll1":  ("xo", 600_000_000.0, 1_200_000_000.0),
    "video_cc_pll0": ("xo", 400_000_000.0, 800_000_000.0),
    # --- MediaTek PLLs ---
    "mainpll":   ("xo", 1_000_000_000.0, 2_200_000_000.0),
    "univpll":   ("xo", 1_200_000_000.0, 2_500_000_000.0),
    "msdcpll":   ("xo",   300_000_000.0,   500_000_000.0),
    "mmpll":     ("xo",   400_000_000.0, 1_500_000_000.0),
    "tvdpll":    ("xo",   300_000_000.0,   600_000_000.0),
    "apll1":     ("xo",   180_000_000.0,   200_000_000.0),
    "apll2":     ("xo",   190_000_000.0,   210_000_000.0),
    "armpll_ll": ("xo",   500_000_000.0, 2_400_000_000.0),
    "armpll_bl": ("xo",   500_000_000.0, 3_200_000_000.0),
    "ccipll":    ("xo",   500_000_000.0, 1_600_000_000.0),
    "gpupll":    ("xo",   200_000_000.0, 1_300_000_000.0),
    # --- Samsung Exynos PLLs ---
    "fout_shared0_pll": ("xo", 1_000_000_000.0, 2_400_000_000.0),
    "fout_shared1_pll": ("xo",   800_000_000.0, 2_000_000_000.0),
    "fout_mphy_pll":    ("xo", 1_400_000_000.0, 1_600_000_000.0),
    "fout_cpucl0_pll":  ("xo",   500_000_000.0, 2_400_000_000.0),
    "fout_cpucl1_pll":  ("xo",   500_000_000.0, 3_200_000_000.0),
    "fout_cpucl2_pll":  ("xo",   500_000_000.0, 3_600_000_000.0),
    "fout_g3d_pll":     ("xo",   200_000_000.0, 1_300_000_000.0),
    "fout_disp_pll":    ("xo",   100_000_000.0,   600_000_000.0),
    # --- Unisoc PLLs ---
    "twpll": ("xo", 1_500_000_000.0, 1_600_000_000.0),
    "rpll":  ("xo",   900_000_000.0, 1_000_000_000.0),
    "gpll":  ("xo",   700_000_000.0,   800_000_000.0),
    "mpll":  ("xo", 1_200_000_000.0, 1_400_000_000.0),
    "dpll":  ("xo",   900_000_000.0, 1_100_000_000.0),
}

# Expected clock-tree hierarchies (child → expected parent pattern).
CLOCK_TREE_HIERARCHY: Dict[str, str] = {
    "gcc_usb30_master_clk":   "gpll0",
    "gcc_sdcc1_apps_clk":     "gpll0",
    "gcc_sdcc2_apps_clk":     "gpll0",
    "gcc_ufs_phy_axi_clk":   "gpll0",
    "gcc_pcie_0_aux_clk":    "xo",
    "gcc_pcie_1_aux_clk":    "xo",
    "gcc_qupv3_wrap0_s0_clk": "gpll0",
    "gcc_qupv3_wrap1_s0_clk": "gpll0",
    "gpu_cc_gx_gfx3d_clk":  "gpu_cc_pll",
    "disp_cc_mdss_mdp_clk":  "disp_cc_pll",
    "cam_cc_ife_0_clk":      "cam_cc_pll",
    "video_cc_mvs0_clk":     "video_cc_pll",
    # --- MediaTek clock tree ---
    "infra_ao_clk": "mainpll",
    "mmsys_clk":    "mmpll",
    "vdec_clk":     "univpll",
    "venc_clk":     "univpll",
    "cam_clk":      "univpll",
    "img_clk":      "univpll",
    "msdc_clk":     "msdcpll",
    "audio_clk":    "apll1",
    "aud_i2s_clk":  "apll2",
    # --- Samsung Exynos clock tree ---
    "aclk_mif":   "fout_shared0_pll",
    "sclk_mfc":   "fout_shared1_pll",
    "aclk_g3d":   "fout_g3d_pll",
    "sclk_decon":  "fout_disp_pll",
}

# Tolerance thresholds.
XO_FREQUENCY_TOLERANCE_PPM: float = 25.0       # ±25 ppm for XO
TCXO_FREQUENCY_TOLERANCE_PPM: float = 2.5      # ±2.5 ppm for TCXO
RTC_DRIFT_WARNING_MS: float = 500.0             # warn above 500 ms drift
RTC_DRIFT_FAULT_MS: float = 5_000.0             # fault above 5 s drift
RTC_ACCURACY_GOOD_PPM: float = 20.0
RTC_ACCURACY_WARNING_PPM: float = 100.0
RTC_DRIFT_MEASUREMENT_SEC: float = 5.0          # measurement window


# ---------------------------------------------------------------------------
#  Low-level ADB helpers
# ---------------------------------------------------------------------------

def _run_adb(cmd: str, timeout: int = 10) -> str:
    """Run an ADB command and return stdout.  Never raises."""
    try:
        r = subprocess.run(
            f"adb {cmd}",
            capture_output=True, text=True, timeout=timeout,
            shell=True, errors="replace",
        )
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.warning("ADB command timed out: adb %s", cmd)
        return ""
    except FileNotFoundError:
        return "ADB_NOT_FOUND"
    except Exception:
        logger.exception("ADB command failed: adb %s", cmd)
        return ""


def _shell(cmd: str, timeout: int = 10) -> str:
    """Shortcut for ``adb shell "<cmd>"``."""
    return _run_adb(f'shell "{cmd}"', timeout)


def _shell_raw(cmd: str, timeout: int = 10) -> str:
    """Shell without extra quoting (for pipes / redirects)."""
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


# ---------------------------------------------------------------------------
#  Progress helper
# ---------------------------------------------------------------------------

def _progress(callback: Optional[Callable[[float, str], None]],
              pct: float, msg: str) -> None:
    """Fire the UI callback if one was provided."""
    if callback:
        callback(pct, msg)
    logger.info("[%3.0f%%] %s", pct * 100, msg)


# ---------------------------------------------------------------------------
#  Step 1 — ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection(callback: Optional[Callable[[float, str], None]],
                          ) -> Tuple[bool, Optional[str]]:
    """Return (connected, error_or_none)."""
    _progress(callback, 0.0, "Checking ADB connection …")

    raw = _run_adb("devices")
    if raw == "ADB_NOT_FOUND":
        return False, "ADB executable not found on PATH"

    lines = [ln for ln in raw.splitlines() if "\tdevice" in ln]
    if not lines:
        return False, "No ADB device connected (or not authorized)"

    serial = lines[0].split("\t")[0]
    logger.info("ADB device detected: %s", serial)
    return True, None


# ---------------------------------------------------------------------------
#  Step 2 — Read clock sources from debugfs
# ---------------------------------------------------------------------------

_CLK_TYPE_PATTERNS: Dict[str, str] = {
    r"xo|cxo|xtal|crystal":   "XTAL",
    r"pll":                    "PLL",
    r"rcxo":                   "RCXO",
    r"dcxo":                   "DCXO",
    r"tcxo":                   "TCXO",
    r"rco|rc_osc":             "RCXO",
    r"div|divider":            "PLL",
    r"mux|rcg":                "PLL",
}


def _classify_clock_type(name: str) -> str:
    """Heuristically classify a clock name into a type category."""
    lower = name.lower()
    for pat, ctype in _CLK_TYPE_PATTERNS.items():
        if re.search(pat, lower):
            return ctype
    return "UNKNOWN"


def _read_clock_sources(
    callback: Optional[Callable[[float, str], None]],
) -> List[ClockSourceInfo]:
    """Read available clock sources from ``/sys/kernel/debug/clk/``."""
    _progress(callback, 0.10, "Reading clock tree from debugfs …")

    clocks: List[ClockSourceInfo] = []

    # --- Method A: list clk directory entries ---------------------------
    listing = _shell("ls /sys/kernel/debug/clk/ 2>/dev/null")
    if not listing or "No such file" in listing or "Permission denied" in listing:
        # Fallback: try clk_summary (available on many 5.x+ kernels).
        listing = ""

    clk_names: List[str] = []
    if listing:
        clk_names = [n.strip() for n in listing.splitlines() if n.strip()]

    # --- Method B: clk_summary -----------------------------------------
    summary_raw = _shell("cat /sys/kernel/debug/clk/clk_summary 2>/dev/null")
    summary_entries: Dict[str, Dict[str, Any]] = {}
    if summary_raw and "Permission denied" not in summary_raw:
        summary_entries = _parse_clk_summary(summary_raw)

    # --- Method C: /proc/clocks (some MediaTek kernels) ----------------
    proc_clk = _shell("cat /proc/clocks 2>/dev/null")
    if proc_clk and "No such file" not in proc_clk:
        _parse_proc_clocks(proc_clk, summary_entries)

    # Merge directory listing with summary data.
    all_names = set(clk_names) | set(summary_entries.keys())

    _progress(callback, 0.18, f"Parsing {len(all_names)} clock entries …")

    for name in sorted(all_names):
        info = ClockSourceInfo(name=name, type=_classify_clock_type(name))

        if name in summary_entries:
            entry = summary_entries[name]
            info.enabled = entry.get("enable_count", 0) > 0
            info.rate_hz = entry.get("rate", 0.0)
            info.frequency_hz = info.rate_hz
            info.parent = entry.get("parent", "")
        else:
            # Try reading individual sysfs nodes for this clock.
            rate_str = _shell(
                f"cat /sys/kernel/debug/clk/{name}/clk_rate 2>/dev/null")
            if rate_str and rate_str.isdigit():
                info.rate_hz = float(rate_str)
                info.frequency_hz = info.rate_hz

            enable_str = _shell(
                f"cat /sys/kernel/debug/clk/{name}/clk_enable_count 2>/dev/null")
            if enable_str and enable_str.isdigit():
                info.enabled = int(enable_str) > 0

            parent_str = _shell(
                f"cat /sys/kernel/debug/clk/{name}/clk_parent 2>/dev/null")
            if parent_str and "No such" not in parent_str:
                info.parent = parent_str.strip()

        clocks.append(info)

    # If we got nothing from debugfs, try the dumpstate approach.
    if not clocks:
        clocks = _read_clocks_from_dumpsys(callback)

    return clocks


def _parse_clk_summary(raw: str) -> Dict[str, Dict[str, Any]]:
    """Parse the kernel ``clk_summary`` pseudo-file.

    Typical format (whitespace-aligned columns)::

        enable  prepare  protect                                duty  hardware
        clock            count    count    count       rate      cycle enable
        -----------------------------------------------------------------------
        xo_board             1        1        0   19200000          0     Y
           gcc_gpll0_out_main  1      1        0  600000000          0     Y
    """
    entries: Dict[str, Dict[str, Any]] = {}
    parent_stack: List[Tuple[int, str]] = []

    for line in raw.splitlines():
        # Skip header lines.
        if not line.strip() or line.strip().startswith(("-", "enable",
                                                         "clock", "cycle")):
            continue

        # Determine indentation level for parent tracking.
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        parts = stripped.split()
        if len(parts) < 2:
            continue

        name = parts[0]

        # Walk parent_stack to find immediate parent.
        while parent_stack and parent_stack[-1][0] >= indent:
            parent_stack.pop()
        parent = parent_stack[-1][1] if parent_stack else ""
        parent_stack.append((indent, name))

        # Parse numeric columns.
        enable_count = _safe_int(parts[1]) if len(parts) > 1 else 0
        rate = _safe_float(parts[4]) if len(parts) > 4 else 0.0
        # Sometimes rate is in column 3 on older kernels.
        if rate == 0.0 and len(parts) > 3:
            rate = _safe_float(parts[3])

        entries[name] = {
            "enable_count": enable_count,
            "rate": rate,
            "parent": parent,
        }

    return entries


def _parse_proc_clocks(raw: str,
                       out: Dict[str, Dict[str, Any]]) -> None:
    """Parse MediaTek ``/proc/clocks`` into *out* dict (mutates)."""
    for line in raw.splitlines():
        # Typical: "[CG]  mainpll_d2 - 1092000000, 1"
        m = re.match(r"\[(\w+)]\s+(\S+)\s*-\s*(\d+)", line)
        if m:
            ctype, name, rate = m.group(1), m.group(2), m.group(3)
            if name not in out:
                out[name] = {
                    "enable_count": 1,
                    "rate": float(rate),
                    "parent": "",
                }


def _read_clocks_from_dumpsys(
    callback: Optional[Callable[[float, str], None]],
) -> List[ClockSourceInfo]:
    """Last-resort: try ``dumpsys`` or ``getprop`` to glean clock info."""
    _progress(callback, 0.20, "Falling back to dumpsys for clock data …")

    clocks: List[ClockSourceInfo] = []

    # CPU frequencies give an indirect view of active PLLs.
    raw = _shell("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null")
    if raw and raw.isdigit():
        freq_hz = int(raw) * 1_000  # kHz → Hz
        clocks.append(ClockSourceInfo(
            name="cpu0_cur_freq", frequency_hz=freq_hz, rate_hz=freq_hz,
            enabled=True, type="PLL",
        ))

    # Try to read SoC identifier for XO guess.
    soc = _shell("getprop ro.hardware.chipname 2>/dev/null").lower()
    if not soc:
        soc = _shell("getprop ro.board.platform 2>/dev/null").lower()
    expected_xo = SOC_XO_MAP.get(soc, 0.0)
    if expected_xo > 0:
        clocks.append(ClockSourceInfo(
            name=f"expected_xo_{soc}", frequency_hz=expected_xo,
            rate_hz=expected_xo, enabled=True, type="XTAL",
        ))

    return clocks


# ---------------------------------------------------------------------------
#  Step 3 — Read RTC info
# ---------------------------------------------------------------------------

def _read_rtc_info(
    callback: Optional[Callable[[float, str], None]],
) -> RTCInfo:
    """Read RTC subsystem from ``/sys/class/rtc/rtc0/``."""
    _progress(callback, 0.30, "Reading RTC subsystem …")

    info = RTCInfo(device_name="rtc0")

    # Device name / hctosys.
    name = _shell("cat /sys/class/rtc/rtc0/name 2>/dev/null")
    if name and "No such" not in name:
        info.device_name = name.strip()

    # Current RTC time.
    rtc_time = _shell("cat /sys/class/rtc/rtc0/time 2>/dev/null")
    rtc_date = _shell("cat /sys/class/rtc/rtc0/date 2>/dev/null")
    if rtc_time and rtc_date:
        info.time_str = f"{rtc_date.strip()} {rtc_time.strip()}"

    # Alarm.
    alarm_raw = _shell("cat /sys/class/rtc/rtc0/wakealarm 2>/dev/null")
    if alarm_raw and alarm_raw.isdigit():
        info.alarm_str = alarm_raw.strip()
    else:
        alarm_raw2 = _shell("cat /sys/class/rtc/rtc0/since_epoch 2>/dev/null")
        if alarm_raw2:
            info.alarm_str = alarm_raw2.strip()

    # Max user frequency (useful diagnostic for drift issues).
    max_freq = _shell(
        "cat /sys/class/rtc/rtc0/max_user_freq 2>/dev/null")
    if max_freq:
        logger.debug("RTC max_user_freq: %s", max_freq)

    info.status = "OK" if info.time_str else "UNKNOWN"
    return info


# ---------------------------------------------------------------------------
#  Step 4 — PLL status from debug nodes
# ---------------------------------------------------------------------------

_PLL_NAME_RE = re.compile(r"(g?pll\d+|cpu_pll|perfcl_pll|pwrcl_pll|"
                          r"gpu_cc_pll\d*|disp_cc_pll\d*|cam_cc_pll\d*|"
                          r"video_cc_pll\d*|nss_crypto_pll|"
                          # MediaTek PLLs
                          r"mainpll|univpll|msdcpll|mmpll|tvdpll|"
                          r"apll\d+|armpll_\w+|ccipll|gpupll|"
                          # Samsung Exynos PLLs
                          r"fout_\w+_pll|"
                          # Unisoc PLLs
                          r"twpll|rpll|mpll|dpll)", re.I)


def _read_pll_status(
    callback: Optional[Callable[[float, str], None]],
    clock_sources: List[ClockSourceInfo],
) -> List[PLLInfo]:
    """Derive PLL status from already-read clock sources and debug nodes."""
    _progress(callback, 0.40, "Analysing PLL status …")

    plls: List[PLLInfo] = []
    seen: set[str] = set()

    # First pass: extract PLLs from the clock tree we already have.
    for clk in clock_sources:
        if clk.type == "PLL" or _PLL_NAME_RE.search(clk.name):
            if clk.name in seen:
                continue
            seen.add(clk.name)
            locked = clk.enabled and clk.rate_hz > 0
            plls.append(PLLInfo(
                name=clk.name,
                frequency_hz=clk.rate_hz,
                locked=locked,
                source=clk.parent,
                status="LOCKED" if locked else "UNLOCKED",
            ))

    # Second pass: try reading PLL-specific debug nodes.
    pll_list_raw = _shell("ls /sys/kernel/debug/clk/ 2>/dev/null | grep -i pll")
    if pll_list_raw and "Permission denied" not in pll_list_raw:
        for name in pll_list_raw.splitlines():
            name = name.strip()
            if not name or name in seen:
                continue
            seen.add(name)

            rate_str = _shell(
                f"cat /sys/kernel/debug/clk/{name}/clk_rate 2>/dev/null")
            rate = _safe_float(rate_str) if rate_str else 0.0

            enable_str = _shell(
                f"cat /sys/kernel/debug/clk/{name}/clk_enable_count 2>/dev/null")
            enabled = _safe_int(enable_str) > 0 if enable_str else False

            locked = enabled and rate > 0
            plls.append(PLLInfo(
                name=name, frequency_hz=rate, locked=locked,
                source="xo", status="LOCKED" if locked else "UNLOCKED",
            ))

    # Validate against known configurations.
    for pll in plls:
        base_name = pll.name.lower().split("_out")[0]
        cfg = KNOWN_PLL_CONFIGS.get(base_name)
        if cfg:
            _, min_f, max_f = cfg
            if pll.frequency_hz < min_f or pll.frequency_hz > max_f:
                pll.status = "OUT_OF_RANGE"
                logger.warning("PLL %s freq %.0f Hz outside expected "
                               "[%.0f, %.0f]",
                               pll.name, pll.frequency_hz, min_f, max_f)

    return plls


# ---------------------------------------------------------------------------
#  Step 5 — XO / DCXO / TCXO calibration
# ---------------------------------------------------------------------------

def _read_xo_calibration(
    callback: Optional[Callable[[float, str], None]],
    clock_sources: List[ClockSourceInfo],
) -> XOCalibration:
    """Check crystal-oscillator calibration data from sysfs."""
    _progress(callback, 0.55, "Checking XO calibration …")

    cal = XOCalibration()

    # Determine the SoC to guess expected XO.
    soc = _shell("getprop ro.board.platform 2>/dev/null").lower().strip()
    if not soc:
        soc = _shell("getprop ro.hardware.chipname 2>/dev/null").lower().strip()

    expected_freq = SOC_XO_MAP.get(soc, 0.0)

    # --- Identify the reference XO from the clock tree ------------------
    xo_clk: Optional[ClockSourceInfo] = None
    for clk in clock_sources:
        lname = clk.name.lower()
        if lname in ("xo_board", "xo", "bi_tcxo", "cxo", "xo_a",
                      "rf_clk1", "ln_bb_clk1"):
            xo_clk = clk
            break
    # Broader fallback.
    if xo_clk is None:
        for clk in clock_sources:
            if clk.type in ("XTAL", "TCXO", "DCXO"):
                xo_clk = clk
                break

    if xo_clk:
        cal.frequency_hz = xo_clk.rate_hz
        cal.type = xo_clk.type if xo_clk.type != "UNKNOWN" else "XO"
    elif expected_freq > 0:
        cal.frequency_hz = expected_freq
        cal.type = "XO"

    # --- Try reading trim / calibration registers ----------------------
    trim_paths = [
        "/sys/devices/platform/soc/soc:tcxo/trim",
        "/sys/devices/platform/soc/soc:dcxo/trim",
        "/sys/kernel/debug/clk/xo_board/trim",
        "/sys/kernel/debug/regmap/spmi0-00/registers",
    ]
    for path in trim_paths:
        raw = _shell(f"cat {path} 2>/dev/null")
        if raw and "No such" not in raw and "Permission" not in raw:
            # Try to extract a numeric trim value.
            nums = re.findall(r"\b(0x[0-9a-fA-F]+|\d+)\b", raw)
            if nums:
                val = nums[0]
                cal.trim_value = int(val, 16) if val.startswith("0x") else int(val)
                cal.calibrated = True
                logger.info("XO trim value from %s: %d", path, cal.trim_value)
                break

    # --- Temperature compensation detection ----------------------------
    temp_comp_indicators = [
        "/sys/devices/platform/soc/soc:tcxo",
        "/sys/devices/platform/soc/soc:dcxo",
    ]
    for path in temp_comp_indicators:
        raw = _shell(f"ls {path} 2>/dev/null")
        if raw and "No such" not in raw:
            cal.temperature_comp = True
            if "tcxo" in path:
                cal.type = "TCXO"
            elif "dcxo" in path:
                cal.type = "DCXO"
            break

    # --- Validate frequency against expected ----------------------------
    if expected_freq > 0 and cal.frequency_hz > 0:
        deviation_ppm = abs(cal.frequency_hz - expected_freq) / expected_freq * 1e6
        tolerance = (TCXO_FREQUENCY_TOLERANCE_PPM if cal.type == "TCXO"
                     else XO_FREQUENCY_TOLERANCE_PPM)
        if deviation_ppm <= tolerance:
            cal.status = "OK"
        elif deviation_ppm <= tolerance * 4:
            cal.status = "WARNING"
            logger.warning("XO deviation %.1f ppm exceeds nominal tolerance "
                           "%.1f ppm", deviation_ppm, tolerance)
        else:
            cal.status = "FAULT"
            logger.error("XO deviation %.1f ppm — likely crystal failure",
                         deviation_ppm)
    elif cal.calibrated:
        cal.status = "OK"
    else:
        cal.status = "UNKNOWN"

    return cal


# ---------------------------------------------------------------------------
#  Step 6 — RTC drift measurement
# ---------------------------------------------------------------------------

def _measure_rtc_drift(
    callback: Optional[Callable[[float, str], None]],
    rtc_info: RTCInfo,
) -> RTCInfo:
    """Compare device time with host time over a short interval to
    estimate RTC drift and accuracy in ppm."""
    _progress(callback, 0.65, "Measuring RTC drift (this takes a few seconds) …")

    # Get device epoch + host epoch at roughly the same instant.
    dev_epoch_1 = _shell("date +%s%N 2>/dev/null")   # nanosecond epoch
    host_time_1 = time.time()

    if not dev_epoch_1 or not dev_epoch_1.replace("-", "").isdigit():
        # Fallback: try seconds only.
        dev_epoch_1 = _shell("date +%s 2>/dev/null")
        host_time_1 = time.time()
        if not dev_epoch_1:
            logger.warning("Cannot read device time for drift measurement")
            return rtc_info

    # Convert device timestamp to float seconds.
    dev_t1 = _device_epoch_to_seconds(dev_epoch_1)
    if dev_t1 is None:
        return rtc_info

    # Wait for the measurement window.
    _progress(callback, 0.70,
              f"Waiting {RTC_DRIFT_MEASUREMENT_SEC:.0f}s for drift sample …")
    time.sleep(RTC_DRIFT_MEASUREMENT_SEC)

    dev_epoch_2 = _shell("date +%s%N 2>/dev/null")
    host_time_2 = time.time()
    if not dev_epoch_2:
        dev_epoch_2 = _shell("date +%s 2>/dev/null")
        host_time_2 = time.time()
    dev_t2 = _device_epoch_to_seconds(dev_epoch_2)
    if dev_t2 is None:
        return rtc_info

    # Calculate drift.
    host_elapsed = host_time_2 - host_time_1
    dev_elapsed = dev_t2 - dev_t1

    if host_elapsed <= 0:
        return rtc_info

    drift_sec = dev_elapsed - host_elapsed
    rtc_info.drift_ms = drift_sec * 1_000.0

    # Parts-per-million (positive = device runs fast).
    rtc_info.accuracy_ppm = (drift_sec / host_elapsed) * 1e6

    logger.info("RTC drift: %.3f ms over %.1f s → %.2f ppm",
                rtc_info.drift_ms, host_elapsed, rtc_info.accuracy_ppm)

    # Status verdict.
    abs_drift = abs(rtc_info.drift_ms)
    abs_ppm = abs(rtc_info.accuracy_ppm)
    if abs_drift > RTC_DRIFT_FAULT_MS or abs_ppm > RTC_ACCURACY_WARNING_PPM:
        rtc_info.status = "FAULT"
    elif abs_drift > RTC_DRIFT_WARNING_MS or abs_ppm > RTC_ACCURACY_GOOD_PPM:
        rtc_info.status = "WARNING"
    else:
        rtc_info.status = "OK"

    return rtc_info


def _device_epoch_to_seconds(raw: str) -> Optional[float]:
    """Convert a device ``date +%s%N`` or ``date +%s`` string to float
    seconds."""
    raw = raw.strip().lstrip("-")
    if not raw:
        return None
    try:
        if len(raw) > 12:
            # Nanosecond epoch (e.g. "1700000000123456789").
            return int(raw) / 1e9
        else:
            return float(raw)
    except (ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
#  Step 7 — Overall health assessment
# ---------------------------------------------------------------------------

def _assess_health(
    result: ClockTestResult,
    callback: Optional[Callable[[float, str], None]],
) -> str:
    """Generate a single-word overall health verdict plus log details."""
    _progress(callback, 0.90, "Generating clock health assessment …")

    issues: List[str] = []
    warnings: List[str] = []

    # --- XO health ------------------------------------------------------
    if result.xo_calibration.status == "FAULT":
        issues.append(
            f"Crystal oscillator FAULT — {result.xo_calibration.type} "
            f"at {result.xo_calibration.frequency_hz/1e6:.3f} MHz is out of "
            f"tolerance.  Replace crystal/TCXO component."
        )
    elif result.xo_calibration.status == "WARNING":
        warnings.append(
            f"XO frequency marginal — check solder joints on "
            f"{result.xo_calibration.type} and nearby decoupling caps."
        )

    # --- PLL health -----------------------------------------------------
    unlocked = [p for p in result.pll_status if not p.locked and p.frequency_hz > 0]
    oor = [p for p in result.pll_status if p.status == "OUT_OF_RANGE"]

    if unlocked:
        names = ", ".join(p.name for p in unlocked)
        issues.append(f"PLL(s) unlocked: {names}.  May indicate XO failure "
                      f"or PMIC power-rail issue.")
    if oor:
        names = ", ".join(p.name for p in oor)
        warnings.append(f"PLL(s) out of expected range: {names}.")

    # --- RTC health -----------------------------------------------------
    if result.rtc_info.status == "FAULT":
        issues.append(
            f"RTC drift {result.rtc_info.drift_ms:.1f} ms / "
            f"{result.rtc_info.accuracy_ppm:.1f} ppm — 32.768 kHz crystal or "
            f"RTC IC may be defective."
        )
    elif result.rtc_info.status == "WARNING":
        warnings.append(
            f"RTC drift {result.rtc_info.drift_ms:.1f} ms — marginal.  "
            f"Check 32.768 kHz crystal load capacitors."
        )

    # --- Clock tree hierarchy checks ------------------------------------
    clk_map: Dict[str, ClockSourceInfo] = {c.name: c for c in result.clock_sources}
    for child_name, expected_parent_pat in CLOCK_TREE_HIERARCHY.items():
        if child_name in clk_map:
            actual_parent = clk_map[child_name].parent.lower()
            if (actual_parent and
                    expected_parent_pat not in actual_parent):
                warnings.append(
                    f"Clock {child_name} parent is '{actual_parent}', "
                    f"expected '*{expected_parent_pat}*'."
                )

    # --- Missing critical clocks ----------------------------------------
    critical_patterns = ["xo", "pll0", "rtc"]
    found_any = {p: False for p in critical_patterns}
    for clk in result.clock_sources:
        for p in critical_patterns:
            if p in clk.name.lower():
                found_any[p] = True
    missing = [p for p, found in found_any.items() if not found]
    if missing and result.clock_sources:
        warnings.append(
            f"Could not locate critical clock(s): {', '.join(missing)}.  "
            f"May require root access to inspect debugfs."
        )

    # --- Verdict --------------------------------------------------------
    for issue in issues:
        logger.error("CLOCK ISSUE: %s", issue)
    for warn in warnings:
        logger.warning("CLOCK WARNING: %s", warn)

    result.faults = issues
    result.warnings = warnings

    if issues:
        return "FAULT"
    if warnings:
        return "WARNING"
    if (not result.clock_sources and not result.pll_status
            and result.rtc_info.status == "UNKNOWN"
            and result.xo_calibration.status == "UNKNOWN"):
        return "UNKNOWN"
    return "OK"


# ---------------------------------------------------------------------------
#  Chipset identification helpers
# ---------------------------------------------------------------------------

def _detect_chipset() -> str:
    """Return a lower-case SoC identifier string (best effort)."""
    for prop in ("ro.board.platform",
                 "ro.hardware.chipname",
                 "ro.hardware",
                 "ro.soc.model"):
        val = _shell(f"getprop {prop} 2>/dev/null").strip().lower()
        if val:
            return val
    return ""


def _expected_xo_for_chipset(chipset: str) -> float:
    """Return the expected XO frequency for a chipset, or 0."""
    for prefix, freq in SOC_XO_MAP.items():
        if prefix in chipset:
            return freq
    # Broad heuristics.
    if any(q in chipset for q in ("sdm", "sm", "msm", "qcom")):
        return 19_200_000.0
    if any(m in chipset for m in ("mt", "mediatek")):
        return 26_000_000.0
    if "exynos" in chipset:
        return 26_000_000.0
    if any(u in chipset for u in ("unisoc", "sc", "t6", "t7", "t8")):
        return 26_000_000.0
    if "tensor" in chipset or chipset.startswith("g"):
        return 19_200_000.0
    if "kirin" in chipset or "hisilicon" in chipset:
        return 19_200_000.0
    return 0.0


# ---------------------------------------------------------------------------
#  Supplementary diagnostics
# ---------------------------------------------------------------------------

def _read_clock_rates_from_sysfs(
    callback: Optional[Callable[[float, str], None]],
) -> Dict[str, float]:
    """Read additional clock rates from sysfs power/clock nodes."""
    rates: Dict[str, float] = {}

    paths = [
        ("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq", "cpu0_max"),
        ("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_min_freq", "cpu0_min"),
        ("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", "cpu0_cur"),
    ]

    # Discover all online CPUs for a fuller picture.
    online_raw = _shell("cat /sys/devices/system/cpu/online 2>/dev/null")
    if online_raw and re.match(r"[\d,\-]+$", online_raw.strip()):
        for rng in online_raw.strip().split(","):
            parts = rng.split("-")
            lo = _safe_int(parts[0])
            hi = _safe_int(parts[-1])
            for cpu_id in range(lo, hi + 1):
                base = f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq"
                paths.append((f"{base}/scaling_cur_freq", f"cpu{cpu_id}_cur"))

    for path, label in paths:
        raw = _shell(f"cat {path} 2>/dev/null")
        if raw and raw.strip().isdigit():
            rates[label] = float(raw.strip()) * 1_000  # kHz → Hz

    return rates


def _check_clock_gating(
    callback: Optional[Callable[[float, str], None]],
    clock_sources: List[ClockSourceInfo],
) -> List[str]:
    """Check for clocks that should be gated but are still enabled."""
    _progress(callback, 0.85, "Checking clock gating …")

    anomalies: List[str] = []

    # Clocks that should normally be disabled when the screen is on and
    # no special peripheral is active.
    normally_gated = {
        "cam_cc_ife_0_clk", "cam_cc_ife_1_clk",
        "cam_cc_jpeg_clk",
        "video_cc_mvs0_clk", "video_cc_mvs1_clk",
        "npu_cc_npu_core_clk",
    }

    for clk in clock_sources:
        if clk.name in normally_gated and clk.enabled:
            anomalies.append(
                f"Clock '{clk.name}' is enabled unexpectedly — "
                f"possible stuck peripheral or driver leak."
            )

    return anomalies


def _read_sleep_clock_info() -> Dict[str, Any]:
    """Read the 32.768 kHz sleep-clock configuration."""
    info: Dict[str, Any] = {}

    # Some Qualcomm devices expose this via sysfs.
    raw = _shell("cat /sys/kernel/debug/clk/sleep_clk/clk_rate 2>/dev/null")
    if raw and raw.strip().isdigit():
        info["sleep_clk_rate"] = int(raw.strip())

    # Also try reading from the PMU / PMIC debug nodes.
    raw = _shell(
        "cat /sys/kernel/debug/regmap/spmi0-00/registers 2>/dev/null"
        " | head -20")
    if raw and "Permission" not in raw:
        info["pmic_registers_sample"] = raw[:200]

    return info


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_clock_status(
    callback: Optional[Callable[[float, str], None]] = None,
) -> ClockTestResult:
    """Run the full oscillator / clock-subsystem diagnostic.

    Parameters
    ----------
    callback : callable, optional
        ``callback(pct: float, msg: str)`` is called periodically so a
        UI can display progress.  *pct* ranges from 0.0 to 1.0.

    Returns
    -------
    ClockTestResult
        Aggregated test data with per-subsystem verdicts and an
        ``overall_health`` of ``OK``, ``WARNING``, ``FAULT``, or
        ``UNKNOWN``.
    """
    result = ClockTestResult()

    # 1. Check ADB connection.
    connected, err = _check_adb_connection(callback)
    result.connected = connected
    if not connected:
        result.error = err
        result.overall_health = "UNKNOWN"
        _progress(callback, 1.0, "Clock test aborted — no device.")
        return result

    chipset = _detect_chipset()
    logger.info("Detected chipset: %s", chipset or "(unknown)")

    try:
        # 2. Read clock sources from debugfs / sysfs.
        result.clock_sources = _read_clock_sources(callback)

        # 3. Read RTC info.
        result.rtc_info = _read_rtc_info(callback)

        # 4. Read PLL status.
        result.pll_status = _read_pll_status(callback, result.clock_sources)

        # 5. Check XO calibration.
        result.xo_calibration = _read_xo_calibration(
            callback, result.clock_sources)

        # 6. Measure RTC drift.
        result.rtc_info = _measure_rtc_drift(callback, result.rtc_info)

        # 7. Clock gating check (informational).
        gating_issues = _check_clock_gating(callback, result.clock_sources)
        for issue in gating_issues:
            logger.warning(issue)

        # 8. Overall health verdict.
        result.overall_health = _assess_health(result, callback)

    except Exception as exc:
        logger.exception("Unhandled error during clock testing")
        result.error = str(exc)
        result.overall_health = "FAULT"

    _progress(callback, 1.0,
              f"Clock test complete — {result.overall_health}")
    return result


# ---------------------------------------------------------------------------
#  CLI entry point
# ---------------------------------------------------------------------------

def _print_report(result: ClockTestResult) -> None:
    """Pretty-print a ClockTestResult to stdout."""
    sep = "=" * 72
    print(f"\n{sep}")
    print("  OSCILLATOR / CLOCK TEST REPORT")
    print(sep)

    print(f"\n  Connected      : {result.connected}")
    if result.error:
        print(f"  Error          : {result.error}")
    print(f"  Overall Health : {result.overall_health}")

    # XO / Crystal.
    print(f"\n{'─' * 72}")
    print("  CRYSTAL OSCILLATOR (XO)")
    print(f"{'─' * 72}")
    xo = result.xo_calibration
    print(f"  Type           : {xo.type or 'N/A'}")
    print(f"  Frequency      : {xo.frequency_hz / 1e6:.6f} MHz"
          if xo.frequency_hz else "  Frequency      : N/A")
    print(f"  Trim Value     : {xo.trim_value}")
    print(f"  Calibrated     : {xo.calibrated}")
    print(f"  Temp Comp      : {xo.temperature_comp}")
    print(f"  Status         : {xo.status}")

    # RTC.
    print(f"\n{'─' * 72}")
    print("  REAL-TIME CLOCK (RTC)")
    print(f"{'─' * 72}")
    rtc = result.rtc_info
    print(f"  Device         : {rtc.device_name}")
    print(f"  Time           : {rtc.time_str or 'N/A'}")
    print(f"  Alarm          : {rtc.alarm_str or 'N/A'}")
    print(f"  Drift          : {rtc.drift_ms:+.3f} ms")
    print(f"  Accuracy       : {rtc.accuracy_ppm:+.2f} ppm")
    print(f"  Status         : {rtc.status}")

    # PLLs.
    print(f"\n{'─' * 72}")
    print("  PHASE-LOCKED LOOPS (PLLs)")
    print(f"{'─' * 72}")
    if result.pll_status:
        print(f"  {'Name':<30s} {'Freq (MHz)':>12s}  {'Locked':>6s}  "
              f"{'Source':<16s} {'Status'}")
        print(f"  {'─' * 30} {'─' * 12}  {'─' * 6}  {'─' * 16} {'─' * 12}")
        for pll in result.pll_status:
            freq_str = f"{pll.frequency_hz / 1e6:.3f}" if pll.frequency_hz else "—"
            print(f"  {pll.name:<30s} {freq_str:>12s}  "
                  f"{'Yes' if pll.locked else 'No':>6s}  "
                  f"{pll.source:<16s} {pll.status}")
    else:
        print("  No PLL data available (may need root).")

    # Clock sources.
    print(f"\n{'─' * 72}")
    print("  CLOCK SOURCES")
    print(f"{'─' * 72}")
    if result.clock_sources:
        shown = result.clock_sources[:40]
        print(f"  {'Name':<36s} {'Rate (Hz)':>14s}  {'On':>3s}  "
              f"{'Type':<6s}  {'Parent'}")
        print(f"  {'─' * 36} {'─' * 14}  {'─' * 3}  {'─' * 6}  {'─' * 20}")
        for clk in shown:
            rate_str = f"{clk.rate_hz:.0f}" if clk.rate_hz else "—"
            en = "Y" if clk.enabled else "N"
            print(f"  {clk.name:<36s} {rate_str:>14s}  {en:>3s}  "
                  f"{clk.type:<6s}  {clk.parent}")
        if len(result.clock_sources) > 40:
            print(f"  … and {len(result.clock_sources) - 40} more entries.")
    else:
        print("  No clock source data available.")

    print(f"\n{sep}\n")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    def _cli_callback(pct: float, msg: str) -> None:
        bar_len = 30
        filled = int(bar_len * pct)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r  [{bar}] {pct*100:5.1f}%  {msg}", end="", flush=True)
        if pct >= 1.0:
            print()

    result = detect_clock_status(callback=_cli_callback)
    _print_report(result)
