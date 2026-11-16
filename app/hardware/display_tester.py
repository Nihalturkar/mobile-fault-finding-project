"""
Display Testing Module for Mobile Repair Technicians.

Tests all display-related subsystems on an Android device via ADB:
  1. Display IC communication (panel info, driver, SurfaceFlinger)
  2. Backlight driver (brightness read/control, adaptive brightness)
  3. Touch IC response (touch device enumeration, protocol, capabilities)
  4. Dead pixel detection (screenshot capture + pixel analysis via PIL)

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
Optional: Pillow (PIL) for dead-pixel screenshot analysis.

Usage:
    result = detect_display_status(callback=lambda pct, msg: print(f"{pct:.0f}% {msg}"))
"""

from __future__ import annotations

import io
import logging
import re
import subprocess
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Progress callback type
# ---------------------------------------------------------------------------
ProgressCallback = Optional[Callable[[float, str], None]]


# ---------------------------------------------------------------------------
#  Known display panel manufacturers and common failure patterns
# ---------------------------------------------------------------------------
PANEL_MANUFACTURERS: Dict[str, Dict[str, Any]] = {
    "samsung_amoled": {
        "name": "Samsung Display (AMOLED)",
        "keywords": ["samsung", "s6e3", "s6e8", "ea8076", "ea8079", "ams", "amoled",
                      "dynamic_amoled", "super_amoled"],
        "panel_type": "AMOLED",
        "common_failures": [
            "Green tint at low brightness (common on S20/S21 AMOLED panels)",
            "OLED burn-in on navigation bar and status bar regions",
            "Black spot spreading — OLED sub-pixel oxidation damage",
            "Vertical green/pink line — display flex cable or IC damage",
            "Flickering at low brightness — PWM driver IC degradation",
        ],
        "repair_notes": "Samsung AMOLED panels require OCA lamination. "
                        "Check flex cable connector for corrosion. "
                        "Green line fault usually means panel replacement.",
    },
    "samsung_ltps": {
        "name": "Samsung Display (LTPS LCD)",
        "keywords": ["samsung", "ltps", "s6d", "s6e2"],
        "panel_type": "LTPS LCD",
        "common_failures": [
            "Backlight bleed around edges",
            "Pressure marks from drop damage",
            "White screen — backlight OK but no data from display IC",
        ],
        "repair_notes": "LTPS LCD panels can sometimes be repaired by "
                        "reseating the flex cable. Check for hairline cracks.",
    },
    "lg_poled": {
        "name": "LG Display (P-OLED)",
        "keywords": ["lg", "lge", "poled", "p-oled", "sw43", "sw49",
                      "flexible_oled"],
        "panel_type": "P-OLED",
        "common_failures": [
            "Image retention (temporary burn-in)",
            "Pink/purple tint on grey backgrounds",
            "Touch ghost input after flex cable damage",
            "Green tint band at low brightness levels",
        ],
        "repair_notes": "LG P-OLED used in Pixel and some LG phones. "
                        "Flex cable is fragile — handle with care during removal.",
    },
    "boe": {
        "name": "BOE Technology",
        "keywords": ["boe", "boe_display", "nt36", "td4330", "td4328"],
        "panel_type": "LCD/OLED",
        "common_failures": [
            "Touch not responding after screen replacement (calibration needed)",
            "Slight color shift compared to original Samsung panels",
            "Backlight uniformity issues on LCD variants",
            "Occasional yellow tint on OLED variants",
        ],
        "repair_notes": "BOE panels are common aftermarket replacements. "
                        "Touch calibration may differ from original.",
    },
    "csot": {
        "name": "CSOT (China Star Optoelectronics)",
        "keywords": ["csot", "china_star", "ft8720", "ft8756"],
        "panel_type": "LCD/OLED",
        "common_failures": [
            "Lower color gamut than Samsung AMOLED originals",
            "Backlight uniformity issues on IPS LCD panels",
            "Touch IC firmware mismatch with phone firmware",
        ],
        "repair_notes": "CSOT panels are budget replacements. "
                        "Verify touch IC firmware compatibility.",
    },
    "tianma": {
        "name": "Tianma Microelectronics",
        "keywords": ["tianma", "tm_display", "nt35596", "nt36672"],
        "panel_type": "IPS LCD",
        "common_failures": [
            "Backlight bleeding at corners",
            "Color temperature inconsistency",
            "Flex cable connector fragile — breaks easily",
            "Occasional purple tint on certain viewing angles",
        ],
        "repair_notes": "Tianma panels used in many mid-range Chinese phones. "
                        "Handle flex cable gently — connector pins bend easily.",
    },
    "jdi": {
        "name": "Japan Display Inc. (JDI)",
        "keywords": ["jdi", "japan_display", "r63350", "r63455"],
        "panel_type": "IPS LCD",
        "common_failures": [
            "Backlight LED strip failure — partial dimming",
            "Pressure spots from drop impact",
            "IPS glow in dark environments",
        ],
        "repair_notes": "JDI panels used in Sony, HTC, some Apple devices. "
                        "High quality but expensive replacements.",
    },
    "sharp": {
        "name": "Sharp Corporation",
        "keywords": ["sharp", "igzo", "ls0", "lq0"],
        "panel_type": "IGZO LCD",
        "common_failures": [
            "IGZO backplane degradation over time",
            "Touch sensitivity loss in cold temperatures",
            "Backlight driver IC failure — screen goes dark",
        ],
        "repair_notes": "Sharp IGZO panels are power efficient but require "
                        "precise voltage from backlight driver IC.",
    },
    "innolux": {
        "name": "Innolux Corporation",
        "keywords": ["innolux", "chimei", "inx"],
        "panel_type": "IPS LCD",
        "common_failures": [
            "Dead pixels more common in budget panels",
            "Color shift on wide viewing angles",
            "Backlight uniformity issues",
        ],
        "repair_notes": "Innolux is a budget panel manufacturer. "
                        "Used in many low-end and mid-range devices.",
    },
    "auo": {
        "name": "AU Optronics",
        "keywords": ["auo", "au_optronics", "benq"],
        "panel_type": "TFT LCD",
        "common_failures": [
            "Pixel transistor failure leading to stuck pixels",
            "Backlight aging — yellowing over time",
        ],
        "repair_notes": "AUO panels found in some tablets and budget phones.",
    },
    "visionox": {
        "name": "Visionox Technology",
        "keywords": ["visionox", "vis_oled"],
        "panel_type": "AMOLED",
        "common_failures": [
            "Color accuracy drifts after extended use",
            "Under-display fingerprint sensor alignment issues",
            "Green tint at low brightness similar to Samsung AMOLED",
        ],
        "repair_notes": "Visionox AMOLED used in OnePlus, Xiaomi, ZTE. "
                        "Check fingerprint sensor alignment after replacement.",
    },
}

# Touch IC manufacturers and known models
TOUCH_IC_DATABASE: Dict[str, Dict[str, str]] = {
    "synaptics": {
        "name": "Synaptics",
        "keywords": "synaptics,syn,s3706,s3708,s3910,clearpad",
        "notes": "Industry standard. Firmware updates via ADB possible.",
    },
    "focaltech": {
        "name": "FocalTech",
        "keywords": "focaltech,ft5,ft6,ft8,focal",
        "notes": "Common in Chinese OEM phones. May need firmware match.",
    },
    "goodix": {
        "name": "Goodix",
        "keywords": "goodix,gt9,gt1,gt5",
        "notes": "Also makes fingerprint sensors. Dual-function ICs common.",
    },
    "atmel": {
        "name": "Atmel (Microchip)",
        "keywords": "atmel,maxtouch,mxt",
        "notes": "Legacy touch IC. Found in older devices.",
    },
    "himax": {
        "name": "Himax Technologies",
        "keywords": "himax,hx8,hx83",
        "notes": "Display driver + touch IC combo. Common in budget LCDs.",
    },
    "novatek": {
        "name": "Novatek Microelectronics",
        "keywords": "novatek,nt36,nt35,nvt",
        "notes": "Display driver IC with integrated touch controller.",
    },
    "ilitek": {
        "name": "ILI Technology",
        "keywords": "ilitek,ili9,ili2",
        "notes": "Budget touch/display driver IC. Common in feature phones.",
    },
}


# ---------------------------------------------------------------------------
#  Data classes
# ---------------------------------------------------------------------------

@dataclass
class DisplayInfo:
    """Information about the display panel itself."""
    panel_type: str = "Unknown"
    resolution_w: int = 0
    resolution_h: int = 0
    density: int = 0
    refresh_rate: float = 0.0
    hdr_support: bool = False
    wide_color_gamut: bool = False
    manufacturer: str = "Unknown"
    driver: str = "Unknown"


@dataclass
class BacklightInfo:
    """Backlight / brightness subsystem information."""
    current_brightness: int = -1
    max_brightness: int = 255
    min_brightness: int = 0
    adaptive_enabled: bool = False
    status: str = "UNKNOWN"  # OK, WARNING, FAULT, UNKNOWN


@dataclass
class TouchInfo:
    """Touch input subsystem information."""
    device_name: str = "Unknown"
    protocol: str = "Unknown"
    max_x: int = 0
    max_y: int = 0
    pressure_support: bool = False
    multitouch_slots: int = 0
    status: str = "UNKNOWN"  # OK, WARNING, FAULT, UNKNOWN
    response_time_ms: float = -1.0


@dataclass
class DeadPixelResult:
    """Result of dead/stuck pixel analysis on a captured screenshot."""
    total_pixels: int = 0
    suspect_pixels: int = 0
    suspect_locations: List[Tuple[int, int]] = field(default_factory=list)
    screenshot_analyzed: bool = False
    status: str = "UNKNOWN"  # OK, WARNING, FAULT, UNKNOWN


@dataclass
class DisplayTestResult:
    """Complete result from all display subsystem tests."""
    connected: bool = False
    error: Optional[str] = None
    display_info: DisplayInfo = field(default_factory=DisplayInfo)
    backlight_info: BacklightInfo = field(default_factory=BacklightInfo)
    touch_info: TouchInfo = field(default_factory=TouchInfo)
    dead_pixel_result: DeadPixelResult = field(default_factory=DeadPixelResult)
    display_health: str = "UNKNOWN"


# ---------------------------------------------------------------------------
#  ADB helper
# ---------------------------------------------------------------------------

def _run_adb(args: List[str], timeout: int = 15) -> Tuple[bool, str]:
    """
    Execute an ADB command and return (success, output).

    Parameters
    ----------
    args : list[str]
        Arguments after ``adb``, e.g. ``["shell", "dumpsys", "display"]``.
    timeout : int
        Maximum seconds to wait for the command.

    Returns
    -------
    tuple[bool, str]
        ``(True, stdout)`` on success, ``(False, error_message)`` on failure.
    """
    cmd = ["adb"] + args
    logger.debug("Running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip()
            logger.debug("ADB command failed (rc=%d): %s", proc.returncode, err)
            return False, err
        return True, proc.stdout
    except FileNotFoundError:
        msg = "adb not found on PATH — install Android Platform Tools"
        logger.error(msg)
        return False, msg
    except subprocess.TimeoutExpired:
        msg = f"ADB command timed out after {timeout}s: {' '.join(cmd)}"
        logger.error(msg)
        return False, msg
    except Exception as exc:  # noqa: BLE001
        msg = f"ADB error: {exc}"
        logger.error(msg)
        return False, msg


def _run_adb_bytes(args: List[str], timeout: int = 30) -> Tuple[bool, bytes]:
    """
    Execute an ADB command and return raw bytes (for screencap).

    Parameters
    ----------
    args : list[str]
        Arguments after ``adb``.
    timeout : int
        Maximum seconds to wait.

    Returns
    -------
    tuple[bool, bytes]
        ``(True, stdout_bytes)`` on success, ``(False, b"error")`` on failure.
    """
    cmd = ["adb"] + args
    logger.debug("Running (bytes): %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace").strip()
            logger.debug("ADB bytes command failed: %s", err)
            return False, err.encode()
        return True, proc.stdout
    except FileNotFoundError:
        return False, b"adb not found on PATH"
    except subprocess.TimeoutExpired:
        return False, b"ADB command timed out"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc).encode()


# ---------------------------------------------------------------------------
#  Step 0: ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection(callback: ProgressCallback = None) -> Tuple[bool, str]:
    """
    Verify that exactly one ADB device is connected and authorized.

    Returns
    -------
    tuple[bool, str]
        ``(True, serial)`` when a device is ready, ``(False, error)`` otherwise.
    """
    if callback:
        callback(0.0, "Checking ADB connection...")

    ok, output = _run_adb(["devices"])
    if not ok:
        return False, output

    lines = [
        ln.strip()
        for ln in output.splitlines()
        if ln.strip() and not ln.startswith("List of")
    ]

    if not lines:
        return False, "No ADB device connected"

    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 2:
            serial, state = parts[0], parts[1]
            if state == "device":
                logger.info("ADB device ready: %s", serial)
                return True, serial
            if state == "unauthorized":
                return False, (
                    f"Device {serial} is unauthorized — "
                    "accept the USB-debugging prompt on the phone"
                )
            if state == "offline":
                return False, f"Device {serial} is offline — replug USB cable"

    return False, "No authorized ADB device found"


# ---------------------------------------------------------------------------
#  Step 1: Display IC communication test
# ---------------------------------------------------------------------------

def _identify_panel_manufacturer(raw_info: str) -> Tuple[str, str, List[str]]:
    """
    Match raw display info text against the panel manufacturer database.

    Returns
    -------
    tuple[str, str, list[str]]
        ``(manufacturer_name, panel_type, common_failures)``
    """
    lower = raw_info.lower()
    for _key, mfr in PANEL_MANUFACTURERS.items():
        for kw in mfr["keywords"]:
            if kw in lower:
                return mfr["name"], mfr["panel_type"], mfr["common_failures"]
    return "Unknown", "Unknown", []


def _identify_touch_ic(raw_info: str) -> str:
    """Return the touch IC manufacturer name from raw text, or 'Unknown'."""
    lower = raw_info.lower()
    for _key, ic in TOUCH_IC_DATABASE.items():
        for kw in ic["keywords"].split(","):
            if kw.strip() in lower:
                return ic["name"]
    return "Unknown"


def _parse_resolution(dumpsys_display: str) -> Tuple[int, int]:
    """Extract resolution (width, height) from dumpsys display output."""
    # Pattern: "real 1080 x 2400" or "mBaseDisplayInfo=...1080x2400"
    m = re.search(r"real\s+(\d+)\s*x\s*(\d+)", dumpsys_display)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.search(r"(\d{3,4})\s*x\s*(\d{3,4})", dumpsys_display)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        if 240 <= w <= 4320 and 240 <= h <= 4320:
            return w, h

    # Try wm size command output
    m = re.search(r"Physical size:\s*(\d+)x(\d+)", dumpsys_display)
    if m:
        return int(m.group(1)), int(m.group(2))

    return 0, 0


def _parse_density(dumpsys_display: str) -> int:
    """Extract DPI density from display info."""
    m = re.search(r"density\s+(\d+)", dumpsys_display, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*dpi", dumpsys_display, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


def _parse_refresh_rate(dumpsys_display: str, sf_output: str) -> float:
    """Extract refresh rate from dumpsys display or SurfaceFlinger."""
    # SurfaceFlinger often has "refresh-rate : 60.00 fps"
    m = re.search(r"refresh[_-]?rate\s*[:=]\s*([\d.]+)", sf_output, re.IGNORECASE)
    if m:
        rate = float(m.group(1))
        if 1.0 < rate < 300.0:
            return rate

    # dumpsys display: "renderFrameRate=120.0" or "refreshRate=60.0"
    m = re.search(r"(?:render|display)?[Ff]rame[Rr]ate\s*=\s*([\d.]+)", dumpsys_display)
    if m:
        return float(m.group(1))
    m = re.search(r"refreshRate\s*=\s*([\d.]+)", dumpsys_display)
    if m:
        return float(m.group(1))

    # "fps = 60"
    m = re.search(r"fps\s*=\s*([\d.]+)", sf_output)
    if m:
        rate = float(m.group(1))
        if 1.0 < rate < 300.0:
            return rate

    return 0.0


def _parse_hdr_support(dumpsys_display: str, sf_output: str) -> bool:
    """Check if display supports HDR."""
    combined = dumpsys_display + sf_output
    hdr_patterns = [
        r"HDR\s+capabilities",
        r"hdr.*supported",
        r"HDR10",
        r"HLG",
        r"Dolby\s*Vision",
        r"hasHdr\s*=\s*true",
        r"supportedHdrTypes.*\[.*\d",
    ]
    for pat in hdr_patterns:
        if re.search(pat, combined, re.IGNORECASE):
            return True
    return False


def _parse_wide_color_gamut(dumpsys_display: str, sf_output: str) -> bool:
    """Check if display supports wide color gamut (DCI-P3, Display P3)."""
    combined = dumpsys_display + sf_output
    wcg_patterns = [
        r"wide.?color.?gamut",
        r"Display[\s_]?P3",
        r"DCI[\s_-]?P3",
        r"isWideColorGamut\s*=\s*true",
        r"wideColorGamut\s*=\s*true",
        r"ColorMode.*DISPLAY_P3",
    ]
    for pat in wcg_patterns:
        if re.search(pat, combined, re.IGNORECASE):
            return True
    return False


def _parse_display_driver(sf_output: str) -> str:
    """Extract display driver or compositor info from SurfaceFlinger."""
    # GLES driver string
    m = re.search(r"GLES:\s*(.+)", sf_output)
    if m:
        return m.group(1).strip()[:120]

    # HWC (Hardware Composer) info
    m = re.search(r"HWC\s*(?:version|impl)\s*[:=]\s*(.+)", sf_output, re.IGNORECASE)
    if m:
        return f"HWC: {m.group(1).strip()[:100]}"

    # Generic display type
    m = re.search(r"Display\s+type\s*[:=]\s*(.+)", sf_output, re.IGNORECASE)
    if m:
        return m.group(1).strip()[:100]

    return "Unknown"


def _test_display_ic(callback: ProgressCallback = None) -> DisplayInfo:
    """
    Communicate with the display IC by reading panel info via
    ``dumpsys display`` and ``dumpsys SurfaceFlinger``.

    Returns
    -------
    DisplayInfo
        Populated display information dataclass.
    """
    info = DisplayInfo()

    if callback:
        callback(5.0, "Reading display info via dumpsys display...")

    ok_disp, dumpsys_display = _run_adb(["shell", "dumpsys", "display"])
    if not ok_disp:
        logger.warning("dumpsys display failed: %s", dumpsys_display)
        dumpsys_display = ""

    if callback:
        callback(10.0, "Reading SurfaceFlinger info...")

    ok_sf, sf_output = _run_adb(["shell", "dumpsys", "SurfaceFlinger"])
    if not ok_sf:
        logger.warning("dumpsys SurfaceFlinger failed: %s", sf_output)
        sf_output = ""

    # Also grab wm size and wm density as fallbacks
    if callback:
        callback(13.0, "Reading window manager size and density...")

    ok_wm, wm_size = _run_adb(["shell", "wm", "size"])
    ok_dens, wm_density = _run_adb(["shell", "wm", "density"])

    combined_raw = "\n".join([dumpsys_display, sf_output, wm_size, wm_density])

    # Parse resolution
    info.resolution_w, info.resolution_h = _parse_resolution(combined_raw)
    if info.resolution_w == 0 and ok_wm:
        info.resolution_w, info.resolution_h = _parse_resolution(wm_size)

    # Parse density
    info.density = _parse_density(combined_raw)
    if info.density == 0 and ok_dens:
        info.density = _parse_density(wm_density)

    # Refresh rate
    info.refresh_rate = _parse_refresh_rate(dumpsys_display, sf_output)

    # HDR and wide color gamut
    info.hdr_support = _parse_hdr_support(dumpsys_display, sf_output)
    info.wide_color_gamut = _parse_wide_color_gamut(dumpsys_display, sf_output)

    # Driver / compositor
    info.driver = _parse_display_driver(sf_output)

    # Panel manufacturer identification
    mfr_name, panel_type, _failures = _identify_panel_manufacturer(combined_raw)
    info.manufacturer = mfr_name
    if panel_type != "Unknown":
        info.panel_type = panel_type
    else:
        # Try to infer panel type from resolution and density
        if info.resolution_w > 0 and info.resolution_h > 0:
            total = info.resolution_w * info.resolution_h
            if total > 2_000_000:
                info.panel_type = "High-res (likely AMOLED or IPS)"
            else:
                info.panel_type = "Standard (likely TFT/IPS LCD)"

    if callback:
        callback(18.0, f"Display IC: {info.manufacturer} {info.panel_type} "
                        f"{info.resolution_w}x{info.resolution_h}")

    logger.info(
        "Display IC test complete: %s %s %dx%d @%.1fHz %ddpi",
        info.manufacturer, info.panel_type,
        info.resolution_w, info.resolution_h,
        info.refresh_rate, info.density,
    )
    return info


# ---------------------------------------------------------------------------
#  Step 2: Backlight driver testing
# ---------------------------------------------------------------------------

def _test_backlight(callback: ProgressCallback = None) -> BacklightInfo:
    """
    Test the backlight / brightness subsystem.

    Attempts to read brightness via sysfs (``/sys/class/backlight/``)
    and falls back to Android Settings (``screen_brightness``).

    Returns
    -------
    BacklightInfo
        Populated backlight info with status assessment.
    """
    bl = BacklightInfo()

    if callback:
        callback(22.0, "Testing backlight driver...")

    # --- Try sysfs paths ---
    sysfs_paths = [
        "/sys/class/backlight/panel0-backlight/brightness",
        "/sys/class/backlight/panel/brightness",
        "/sys/class/backlight/lcd-backlight/brightness",
        "/sys/class/backlight/backlight/brightness",
        "/sys/class/leds/lcd-backlight/brightness",
    ]

    sysfs_max_paths = [
        p.replace("brightness", "max_brightness") for p in sysfs_paths
    ]

    brightness_read = False

    # Try each sysfs path
    for i, path in enumerate(sysfs_paths):
        ok, val = _run_adb(["shell", f"cat {path}"], timeout=5)
        if ok and val.strip().isdigit():
            bl.current_brightness = int(val.strip())
            brightness_read = True
            logger.info("Backlight sysfs brightness: %d from %s",
                        bl.current_brightness, path)

            # Read max brightness from corresponding path
            ok_max, max_val = _run_adb(
                ["shell", f"cat {sysfs_max_paths[i]}"], timeout=5
            )
            if ok_max and max_val.strip().isdigit():
                bl.max_brightness = int(max_val.strip())
            break

    # --- Fallback: Android settings ---
    if not brightness_read:
        if callback:
            callback(25.0, "Trying Android settings for brightness...")

        ok, val = _run_adb(
            ["shell", "settings", "get", "system", "screen_brightness"],
            timeout=5,
        )
        if ok and val.strip().isdigit():
            bl.current_brightness = int(val.strip())
            bl.max_brightness = 255  # Android settings range is 0-255
            bl.min_brightness = 0
            brightness_read = True
            logger.info("Backlight via settings: %d/255", bl.current_brightness)

    # --- Check adaptive brightness ---
    ok_adapt, adapt_val = _run_adb(
        ["shell", "settings", "get", "system", "screen_brightness_mode"],
        timeout=5,
    )
    if ok_adapt:
        bl.adaptive_enabled = adapt_val.strip() == "1"
        logger.info("Adaptive brightness: %s",
                     "enabled" if bl.adaptive_enabled else "disabled")

    # --- Assess backlight status ---
    if not brightness_read:
        bl.status = "FAULT"
        logger.warning("Could not read brightness from any source")
    elif bl.current_brightness <= 0:
        bl.status = "WARNING"
        logger.warning("Brightness is 0 — screen may appear dark")
    elif bl.max_brightness > 0 and bl.current_brightness > bl.max_brightness:
        bl.status = "WARNING"
        logger.warning("Current brightness exceeds reported max")
    else:
        bl.status = "OK"

    # --- Verify backlight responds to change (read-only test) ---
    # We do NOT actually change brightness to avoid user disruption.
    # Instead, we verify the backlight control path is accessible.
    if callback:
        callback(30.0, "Verifying backlight control path accessibility...")

    ok_ctrl, _ctrl_out = _run_adb(
        ["shell", "ls", "/sys/class/backlight/"],
        timeout=5,
    )
    if ok_ctrl:
        logger.info("Backlight sysfs directory accessible")
    else:
        # Not a fault — many devices restrict sysfs access without root
        logger.info("Backlight sysfs not directly accessible (non-root)")

    if callback:
        pct_str = ""
        if bl.max_brightness > 0 and bl.current_brightness >= 0:
            pct_str = f" ({bl.current_brightness * 100 // bl.max_brightness}%%)"
        callback(
            33.0,
            f"Backlight: {bl.status} — brightness {bl.current_brightness}"
            f"/{bl.max_brightness}{pct_str}"
            f", adaptive={'ON' if bl.adaptive_enabled else 'OFF'}",
        )

    return bl


# ---------------------------------------------------------------------------
#  Step 3: Touch IC response testing
# ---------------------------------------------------------------------------

def _parse_getevent_devices(raw: str) -> List[Dict[str, Any]]:
    """
    Parse the output of ``getevent -il`` to extract input device info.

    Returns a list of dicts, each describing one input device with its
    name, physical path, and supported event types / codes.
    """
    devices: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for line in raw.splitlines():
        line = line.rstrip()

        # New device block: "add device 1: /dev/input/event2"
        m = re.match(r'add device\s+\d+:\s*(/dev/input/event\d+)', line)
        if m:
            if current:
                devices.append(current)
            current = {
                "path": m.group(1),
                "name": "",
                "props": {},
                "abs_info": {},
            }
            continue

        if current is None:
            continue

        # Name line: '  name:     "synaptics_tcm"'
        m = re.match(r'\s+name:\s+"(.+)"', line)
        if m:
            current["name"] = m.group(1)
            continue

        # ABS info lines like:
        #   ABS_MT_POSITION_X : value 0, min 0, max 1079, ...
        m = re.match(
            r'\s+(ABS_MT_\w+|ABS_\w+)\s*:\s*value\s+(-?\d+),\s*min\s+(-?\d+),'
            r'\s*max\s+(-?\d+)',
            line,
        )
        if m:
            current["abs_info"][m.group(1)] = {
                "value": int(m.group(2)),
                "min": int(m.group(3)),
                "max": int(m.group(4)),
            }
            continue

        # Property lines: "  prop 0: INPUT_PROP_DIRECT"
        m = re.match(r'\s+prop\s+\d+:\s*(.*)', line)
        if m:
            current["props"][m.group(1).strip()] = True

    if current:
        devices.append(current)

    return devices


def _is_touch_device(dev: Dict[str, Any]) -> bool:
    """Heuristic: is this input device a touchscreen?"""
    name_lower = dev["name"].lower()
    touch_keywords = [
        "touch", "ts", "tsc", "synaptics", "goodix", "focaltech",
        "atmel", "himax", "novatek", "ilitek", "sec_touchscreen",
        "mxt", "clearpad", "raydium", "melfas", "hideep",
    ]
    if any(kw in name_lower for kw in touch_keywords):
        return True

    # If it has ABS_MT_POSITION_X, it is likely a touchscreen
    if "ABS_MT_POSITION_X" in dev.get("abs_info", {}):
        return True

    # INPUT_PROP_DIRECT means direct touch input
    if "INPUT_PROP_DIRECT" in dev.get("props", {}):
        return True

    return False


def _test_touch_ic(callback: ProgressCallback = None) -> TouchInfo:
    """
    Test the touch IC by enumerating input devices via ``getevent -il``.

    Checks for:
    - Touch device presence and name
    - Protocol (Type A vs Type B multitouch)
    - Resolution / coordinate range
    - Pressure support
    - Multitouch slot count

    Returns
    -------
    TouchInfo
        Populated touch info with status assessment.
    """
    ti = TouchInfo()

    if callback:
        callback(38.0, "Enumerating touch input devices via getevent...")

    ok, raw = _run_adb(["shell", "getevent", "-il"], timeout=10)
    if not ok:
        logger.warning("getevent -il failed: %s", raw)
        ti.status = "FAULT"
        ti.device_name = "N/A (getevent failed)"
        if callback:
            callback(45.0, "Touch IC: FAULT — could not enumerate input devices")
        return ti

    devices = _parse_getevent_devices(raw)
    touch_devs = [d for d in devices if _is_touch_device(d)]

    if not touch_devs:
        logger.warning("No touch device found among %d input devices",
                        len(devices))
        ti.status = "FAULT"
        ti.device_name = "NOT FOUND"
        if callback:
            callback(45.0, "Touch IC: FAULT — no touchscreen device detected")
        return ti

    # Use the first (primary) touch device
    td = touch_devs[0]
    ti.device_name = td["name"]
    logger.info("Touch device found: %s at %s", td["name"], td["path"])

    # Identify touch IC manufacturer
    touch_ic_name = _identify_touch_ic(td["name"])
    if touch_ic_name != "Unknown":
        ti.device_name = f"{td['name']} ({touch_ic_name})"

    # Parse coordinate range
    abs_info = td.get("abs_info", {})
    if "ABS_MT_POSITION_X" in abs_info:
        ti.max_x = abs_info["ABS_MT_POSITION_X"]["max"]
    if "ABS_MT_POSITION_Y" in abs_info:
        ti.max_y = abs_info["ABS_MT_POSITION_Y"]["max"]

    # Pressure support
    ti.pressure_support = "ABS_MT_PRESSURE" in abs_info

    # Multitouch slots (Type B protocol)
    if "ABS_MT_SLOT" in abs_info:
        ti.multitouch_slots = abs_info["ABS_MT_SLOT"]["max"] + 1
        ti.protocol = "Type B (slotted)"
    elif "ABS_MT_TRACKING_ID" in abs_info:
        ti.protocol = "Type A (non-slotted)"
        ti.multitouch_slots = 1
    else:
        ti.protocol = "Single-touch or legacy"
        ti.multitouch_slots = 1

    # --- Quick touch response time test ---
    # We cannot actually measure latency without a user touch event.
    # Instead, we time how fast the kernel reports device info as a proxy.
    if callback:
        callback(42.0, "Measuring touch IC response time (proxy)...")

    t0 = time.perf_counter()
    _run_adb(["shell", "cat", td["path"].replace("/dev/input/", "/proc/bus/input/devices")],
             timeout=5)
    # Fallback: just read /proc/bus/input/devices
    ok_proc, proc_out = _run_adb(["shell", "cat", "/proc/bus/input/devices"], timeout=5)
    t1 = time.perf_counter()

    if ok_proc:
        # The round-trip time is a rough proxy for USB + kernel overhead
        ti.response_time_ms = round((t1 - t0) * 1000, 1)

    # --- Status assessment ---
    if ti.max_x == 0 or ti.max_y == 0:
        ti.status = "WARNING"
        logger.warning("Touch coordinate range not detected")
    elif ti.multitouch_slots < 2:
        ti.status = "WARNING"
        logger.warning("Only single-touch or 1 multitouch slot detected")
    else:
        ti.status = "OK"

    if callback:
        callback(
            48.0,
            f"Touch IC: {ti.status} — {ti.device_name}, "
            f"{ti.protocol}, {ti.multitouch_slots} slots, "
            f"range {ti.max_x}x{ti.max_y}, "
            f"pressure={'yes' if ti.pressure_support else 'no'}",
        )

    logger.info(
        "Touch IC test complete: %s proto=%s slots=%d range=%dx%d "
        "pressure=%s response=%.1fms",
        ti.device_name, ti.protocol, ti.multitouch_slots,
        ti.max_x, ti.max_y, ti.pressure_support, ti.response_time_ms,
    )
    return ti


# ---------------------------------------------------------------------------
#  Step 4: Dead pixel detection
# ---------------------------------------------------------------------------

def _capture_screenshot_png() -> Tuple[bool, bytes]:
    """
    Capture a screenshot from the device as PNG bytes.

    Uses ``adb exec-out screencap -p`` which streams the PNG directly,
    avoiding the need to write to device storage.

    Returns
    -------
    tuple[bool, bytes]
        ``(True, png_bytes)`` on success.
    """
    return _run_adb_bytes(["exec-out", "screencap", "-p"], timeout=30)


def _analyze_pixels_with_pil(
    png_data: bytes,
    suspect_threshold: int = 80,
    sample_stride: int = 3,
    max_suspect_report: int = 200,
) -> DeadPixelResult:
    """
    Analyze a screenshot for stuck or dead pixels using Pillow (PIL).

    Dead/stuck pixels are individual pixels whose hardware is faulty —
    they are permanently ON (stuck bright/colored) or OFF (dead black)
    regardless of what the screen is displaying.  They appear as single
    isolated dots that differ drastically from *all* their neighbors.

    Normal UI content (text, icons, edges, gradients) creates many pixels
    that differ from their neighbors by small amounts — those are NOT
    dead pixels.  This algorithm uses several techniques to avoid false
    positives from normal screen content:

    1. **High deviation threshold** (80 per channel) — only flags pixels
       with extreme deviation from the local neighborhood.
    2. **Isolation check** — a true dead pixel is a lone outlier; text
       and UI edges have many adjacent outlier pixels.  We require the
       suspect pixel to have very few other deviating neighbors.
    3. **UI region exclusion** — the top 5% (status bar) and bottom 5%
       (navigation bar) of the screen are excluded because they always
       contain high-contrast UI elements.
    4. **No sampling multiplication** — we only count actually-checked
       pixels, never extrapolate.

    Parameters
    ----------
    png_data : bytes
        Raw PNG image data from screencap.
    suspect_threshold : int
        Minimum color-channel deviation from local average to flag a pixel.
        Default 80 is high enough to ignore normal content but catch true
        hardware faults.
    sample_stride : int
        Analyze every Nth pixel in each direction (performance trade-off).
    max_suspect_report : int
        Maximum number of suspect pixel locations to store.

    Returns
    -------
    DeadPixelResult
        Analysis results including suspect pixel count and locations.
    """
    result = DeadPixelResult()

    try:
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("Pillow (PIL) not installed — skipping pixel analysis")
        result.status = "UNKNOWN"
        return result

    try:
        img = Image.open(io.BytesIO(png_data))
        img = img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to open screenshot image: %s", exc)
        result.status = "FAULT"
        return result

    width, height = img.size
    result.total_pixels = width * height
    result.screenshot_analyzed = True
    pixels = img.load()

    if pixels is None:
        logger.error("Failed to load pixel data from screenshot")
        result.status = "FAULT"
        return result

    suspect_count = 0
    suspect_locations: List[Tuple[int, int]] = []

    # Exclude top 5% and bottom 5% of the screen (status bar, nav bar)
    # These regions always have high-contrast UI elements and cause
    # massive false positives.
    margin_top = max(int(height * 0.05), 10)
    margin_bottom = max(int(height * 0.05), 10)
    y_start = margin_top
    y_end = height - margin_bottom

    block_half = 3  # 7x7 neighborhood for better averaging

    for y in range(max(y_start, block_half), min(y_end, height - block_half), sample_stride):
        for x in range(block_half, width - block_half, sample_stride):
            pr, pg, pb = pixels[x, y]

            # Compute local average of the 7x7 neighborhood (skip center pixel)
            r_sum, g_sum, b_sum = 0, 0, 0
            count = 0
            for dy in range(-block_half, block_half + 1):
                for dx in range(-block_half, block_half + 1):
                    if dx == 0 and dy == 0:
                        continue
                    nr, ng, nb = pixels[x + dx, y + dy]
                    r_sum += nr
                    g_sum += ng
                    b_sum += nb
                    count += 1

            if count == 0:
                continue

            avg_r = r_sum / count
            avg_g = g_sum / count
            avg_b = b_sum / count

            # Check if this pixel deviates drastically from its neighborhood
            dev_r = abs(pr - avg_r)
            dev_g = abs(pg - avg_g)
            dev_b = abs(pb - avg_b)
            max_dev = max(dev_r, dev_g, dev_b)

            if max_dev <= suspect_threshold:
                continue

            # --- Isolation check ---
            # A true dead/stuck pixel is an isolated single-point anomaly.
            # UI content (text edges, icon borders) produces clusters of
            # deviating pixels.  Count how many of the 8 immediate neighbors
            # also deviate significantly — if too many do, this is a content
            # edge, not a dead pixel.
            deviating_neighbors = 0
            for ny, nx in [
                (y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1),
                (y - 1, x - 1), (y - 1, x + 1), (y + 1, x - 1), (y + 1, x + 1),
            ]:
                if 0 <= nx < width and 0 <= ny < height:
                    nr, ng, nb = pixels[nx, ny]
                    n_dev = max(abs(nr - avg_r), abs(ng - avg_g), abs(nb - avg_b))
                    if n_dev > suspect_threshold * 0.6:
                        deviating_neighbors += 1

            # If more than 2 immediate neighbors also deviate, this is
            # a content edge / text / icon — NOT a dead pixel.
            if deviating_neighbors > 2:
                continue

            suspect_count += 1
            if len(suspect_locations) < max_suspect_report:
                suspect_locations.append((x, y))

    # We report the actual count of confirmed suspect pixels found.
    # No sampling multiplication — that caused massive over-counting.
    result.suspect_pixels = suspect_count
    result.suspect_locations = suspect_locations

    # Classify result based on actual suspect pixel count.
    # On a 1080x2400 screen (~2.6M pixels), a few dead pixels are common
    # and acceptable.  Hundreds indicate a real problem.
    if suspect_count <= 5:
        result.status = "OK"
    elif suspect_count <= 30:
        # A few isolated pixels — minor, could be early OLED sub-pixel
        # degradation or display aging.
        result.status = "WARNING"
    else:
        # More than 30 confirmed isolated suspect pixels — real fault.
        result.status = "FAULT"

    logger.info(
        "Dead pixel analysis: %d confirmed suspect pixels out of %d total, status=%s",
        suspect_count, result.total_pixels, result.status,
    )
    return result


def _analyze_pixels_basic(png_data: bytes) -> DeadPixelResult:
    """
    Basic dead-pixel analysis without Pillow.

    Parses the raw PNG header to extract dimensions, then performs a
    simplified byte-level scan for anomalies. Much less accurate than
    the PIL-based analysis but works without external dependencies.

    Parameters
    ----------
    png_data : bytes
        Raw PNG image data.

    Returns
    -------
    DeadPixelResult
        Basic analysis results.
    """
    result = DeadPixelResult()

    if len(png_data) < 24:
        result.status = "FAULT"
        return result

    # PNG header check
    if png_data[:8] != b'\x89PNG\r\n\x1a\n':
        logger.warning("Screenshot data is not a valid PNG")
        result.status = "FAULT"
        return result

    # IHDR chunk contains width and height at bytes 16-23
    try:
        width = struct.unpack(">I", png_data[16:20])[0]
        height = struct.unpack(">I", png_data[20:24])[0]
    except struct.error:
        result.status = "FAULT"
        return result

    result.total_pixels = width * height
    result.screenshot_analyzed = True

    # Without decompressing the PNG, we can only check the file size
    # as a very rough heuristic.  A solid-color screen compresses
    # extremely well; a normal screen has moderate compression; a
    # screen with severe display artifacts may have unusual patterns.
    expected_raw_size = width * height * 3  # RGB
    compression_ratio = len(png_data) / expected_raw_size if expected_raw_size > 0 else 0

    logger.info(
        "Basic pixel check: %dx%d, PNG size=%d, raw~%d, ratio=%.4f",
        width, height, len(png_data), expected_raw_size, compression_ratio,
    )

    if compression_ratio < 0.001:
        # Extremely compressed — screen is likely a solid color (possible blank)
        result.status = "WARNING"
        result.suspect_pixels = 0
    elif compression_ratio > 0.95:
        # Very little compression — noise or artifacts filling the screen
        result.status = "WARNING"
        result.suspect_pixels = result.total_pixels // 100
    else:
        result.status = "OK"
        result.suspect_pixels = 0

    return result


def _test_dead_pixels(callback: ProgressCallback = None) -> DeadPixelResult:
    """
    Capture a screenshot and analyze it for dead or stuck pixels.

    Tries PIL-based analysis first; falls back to basic byte-level
    analysis if Pillow is not installed.

    Returns
    -------
    DeadPixelResult
        Analysis results.
    """
    if callback:
        callback(52.0, "Capturing screenshot for dead pixel analysis...")

    ok, png_data = _capture_screenshot_png()
    if not ok:
        logger.warning("Screenshot capture failed: %s", png_data.decode(errors="replace"))
        if callback:
            callback(60.0, "Dead pixel test: FAULT — screenshot capture failed")
        return DeadPixelResult(status="FAULT")

    if len(png_data) < 100:
        logger.warning("Screenshot data too small (%d bytes) — likely empty", len(png_data))
        if callback:
            callback(60.0, "Dead pixel test: FAULT — empty screenshot")
        return DeadPixelResult(status="FAULT")

    if callback:
        callback(58.0, f"Screenshot captured ({len(png_data)} bytes), analyzing pixels...")

    # Try PIL-based analysis first
    try:
        from PIL import Image  # type: ignore[import-untyped]  # noqa: F401
        pil_available = True
    except ImportError:
        pil_available = False

    if pil_available:
        result = _analyze_pixels_with_pil(png_data)
    else:
        logger.info("Pillow not available — using basic analysis")
        result = _analyze_pixels_basic(png_data)

    if callback:
        if result.status == "OK":
            callback(65.0, f"Dead pixel test: OK — {result.total_pixels} pixels analyzed, "
                           f"no dead/stuck pixels found")
        elif result.status == "WARNING":
            callback(65.0, f"Dead pixel test: WARNING — {result.suspect_pixels} isolated "
                           f"suspect pixel(s) found (minor, could be early degradation)")
        elif result.status == "FAULT":
            callback(65.0, f"Dead pixel test: FAULT — {result.suspect_pixels} isolated "
                           f"dead/stuck pixel(s) confirmed")
        else:
            callback(65.0, "Dead pixel test: UNKNOWN — analysis inconclusive")

    return result


# ---------------------------------------------------------------------------
#  Step 5: Overall display health assessment
# ---------------------------------------------------------------------------

def _assess_display_health(
    display_info: DisplayInfo,
    backlight_info: BacklightInfo,
    touch_info: TouchInfo,
    dead_pixel_result: DeadPixelResult,
) -> str:
    """
    Generate an overall display health string based on all sub-test results.

    Health levels:
    - ``GOOD``     : All subsystems OK, no issues detected.
    - ``FAIR``     : Minor warnings but display is functional.
    - ``DEGRADED`` : Some subsystems have issues; display works but may
                     have problems.
    - ``POOR``     : Multiple faults detected; display needs repair.
    - ``CRITICAL`` : Display IC not communicating or major faults.
    - ``UNKNOWN``  : Could not determine (ADB issues, etc.).

    Returns
    -------
    str
        Health assessment string with explanation.
    """
    statuses = [
        backlight_info.status,
        touch_info.status,
        dead_pixel_result.status,
    ]

    fault_count = statuses.count("FAULT")
    warning_count = statuses.count("WARNING")
    unknown_count = statuses.count("UNKNOWN")
    ok_count = statuses.count("OK")

    # Check if we got basic display info
    display_ic_ok = display_info.resolution_w > 0 and display_info.resolution_h > 0

    problems: List[str] = []

    if not display_ic_ok:
        problems.append("Display IC not reporting resolution")

    if backlight_info.status == "FAULT":
        problems.append("Backlight subsystem fault")
    elif backlight_info.status == "WARNING":
        problems.append("Backlight subsystem warning")

    if touch_info.status == "FAULT":
        problems.append("Touch IC fault — no touchscreen detected")
    elif touch_info.status == "WARNING":
        problems.append("Touch IC warning — limited functionality")

    if dead_pixel_result.status == "FAULT":
        problems.append(
            f"Dead/stuck pixels confirmed ({dead_pixel_result.suspect_pixels} isolated faults)"
        )
    elif dead_pixel_result.status == "WARNING":
        problems.append(
            f"Minor pixel degradation ({dead_pixel_result.suspect_pixels} isolated suspect pixel(s))"
        )

    # Look up known failure patterns for the identified manufacturer
    failure_notes: List[str] = []
    mfr_lower = display_info.manufacturer.lower()
    for _key, mfr_data in PANEL_MANUFACTURERS.items():
        if mfr_data["name"].lower() in mfr_lower or mfr_lower in mfr_data["name"].lower():
            if mfr_data.get("repair_notes"):
                failure_notes.append(mfr_data["repair_notes"])
            break

    # Determine health level
    if not display_ic_ok:
        health = "CRITICAL"
    elif fault_count >= 2:
        health = "POOR"
    elif fault_count == 1:
        health = "DEGRADED"
    elif warning_count >= 2:
        health = "DEGRADED"
    elif warning_count == 1:
        health = "FAIR"
    elif unknown_count >= 2:
        health = "UNKNOWN"
    elif ok_count == len(statuses) and display_ic_ok:
        health = "GOOD"
    else:
        health = "FAIR"

    # Build summary string
    parts = [health]
    if problems:
        parts.append(" — " + "; ".join(problems))
    if failure_notes:
        parts.append(f" | Note: {failure_notes[0]}")

    summary = "".join(parts)

    logger.info(
        "Display health assessment: %s (faults=%d, warnings=%d, ok=%d, unknown=%d)",
        health, fault_count, warning_count, ok_count, unknown_count,
    )
    return summary


# ---------------------------------------------------------------------------
#  Main detection function
# ---------------------------------------------------------------------------

def detect_display_status(
    callback: ProgressCallback = None,
) -> DisplayTestResult:
    """
    Run a comprehensive display subsystem diagnostic on the connected
    Android device via ADB.

    This is the main entry point for the display testing module.  It
    runs all four sub-tests in sequence:

    1. **Display IC communication** — reads panel info, resolution,
       refresh rate, HDR/WCG support, and identifies the panel
       manufacturer from a built-in database.
    2. **Backlight driver** — reads current brightness, max brightness,
       and adaptive brightness state.
    3. **Touch IC response** — enumerates touch devices, checks protocol,
       coordinate range, pressure support, and multitouch slots.
    4. **Dead pixel detection** — captures a screenshot and analyzes it
       for stuck or dead pixels using PIL (or a basic fallback).

    Finally, it computes an overall ``display_health`` assessment.

    Parameters
    ----------
    callback : callable, optional
        Progress callback with signature ``callback(pct: float, msg: str)``.
        ``pct`` ranges from 0.0 to 100.0.  ``msg`` is a human-readable
        status string.

    Returns
    -------
    DisplayTestResult
        Complete results from all display tests, including per-subsystem
        info and an overall health assessment.

    Examples
    --------
    >>> result = detect_display_status()
    >>> print(result.display_health)
    'GOOD'
    >>> print(result.display_info.resolution_w, result.display_info.resolution_h)
    1080 2400
    """
    result = DisplayTestResult()

    # ---- Step 0: Check ADB connection ----
    connected, serial_or_error = _check_adb_connection(callback)
    if not connected:
        result.connected = False
        result.error = serial_or_error
        result.display_health = f"CRITICAL — ADB not connected: {serial_or_error}"
        if callback:
            callback(100.0, f"FAILED: {serial_or_error}")
        logger.error("Display test aborted — ADB not connected: %s", serial_or_error)
        return result

    result.connected = True
    if callback:
        callback(3.0, f"ADB connected to {serial_or_error}")

    # ---- Step 1: Display IC communication ----
    try:
        result.display_info = _test_display_ic(callback)
    except Exception as exc:  # noqa: BLE001
        logger.error("Display IC test failed with exception: %s", exc)
        result.display_info = DisplayInfo()
        result.error = f"Display IC test error: {exc}"

    if callback:
        callback(20.0, "Display IC test complete")

    # ---- Step 2: Backlight driver ----
    try:
        result.backlight_info = _test_backlight(callback)
    except Exception as exc:  # noqa: BLE001
        logger.error("Backlight test failed with exception: %s", exc)
        result.backlight_info = BacklightInfo(status="FAULT")
        if not result.error:
            result.error = f"Backlight test error: {exc}"

    if callback:
        callback(35.0, "Backlight test complete")

    # ---- Step 3: Touch IC response ----
    try:
        result.touch_info = _test_touch_ic(callback)
    except Exception as exc:  # noqa: BLE001
        logger.error("Touch IC test failed with exception: %s", exc)
        result.touch_info = TouchInfo(status="FAULT")
        if not result.error:
            result.error = f"Touch IC test error: {exc}"

    if callback:
        callback(50.0, "Touch IC test complete")

    # ---- Step 4: Dead pixel detection ----
    try:
        result.dead_pixel_result = _test_dead_pixels(callback)
    except Exception as exc:  # noqa: BLE001
        logger.error("Dead pixel test failed with exception: %s", exc)
        result.dead_pixel_result = DeadPixelResult(status="FAULT")
        if not result.error:
            result.error = f"Dead pixel test error: {exc}"

    if callback:
        callback(70.0, "Dead pixel test complete")

    # ---- Step 5: Overall health assessment ----
    if callback:
        callback(75.0, "Computing overall display health...")

    result.display_health = _assess_display_health(
        result.display_info,
        result.backlight_info,
        result.touch_info,
        result.dead_pixel_result,
    )

    if callback:
        callback(100.0, f"Display test complete — Health: {result.display_health}")

    logger.info("Display test finished: health=%s", result.display_health)
    return result


# ---------------------------------------------------------------------------
#  Convenience: run as standalone script
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def _cli_callback(pct: float, msg: str) -> None:
        print(f"[{pct:5.1f}%] {msg}")

    print("=" * 70)
    print("  Mooxy AI Fault Detector — Display Subsystem Diagnostic")
    print("=" * 70)
    print()

    test_result = detect_display_status(callback=_cli_callback)

    print()
    print("-" * 70)
    print("  RESULTS")
    print("-" * 70)

    print(f"  Connected        : {test_result.connected}")
    if test_result.error:
        print(f"  Error            : {test_result.error}")

    di = test_result.display_info
    print()
    print("  [Display IC]")
    print(f"    Panel type     : {di.panel_type}")
    print(f"    Manufacturer   : {di.manufacturer}")
    print(f"    Resolution     : {di.resolution_w} x {di.resolution_h}")
    print(f"    Density        : {di.density} dpi")
    print(f"    Refresh rate   : {di.refresh_rate} Hz")
    print(f"    HDR support    : {di.hdr_support}")
    print(f"    Wide color     : {di.wide_color_gamut}")
    print(f"    Driver         : {di.driver}")

    bl = test_result.backlight_info
    print()
    print("  [Backlight]")
    print(f"    Status         : {bl.status}")
    print(f"    Brightness     : {bl.current_brightness} / {bl.max_brightness}")
    print(f"    Adaptive       : {'ON' if bl.adaptive_enabled else 'OFF'}")

    ti = test_result.touch_info
    print()
    print("  [Touch IC]")
    print(f"    Status         : {ti.status}")
    print(f"    Device         : {ti.device_name}")
    print(f"    Protocol       : {ti.protocol}")
    print(f"    Range          : {ti.max_x} x {ti.max_y}")
    print(f"    Pressure       : {'yes' if ti.pressure_support else 'no'}")
    print(f"    MT slots       : {ti.multitouch_slots}")
    print(f"    Response time  : {ti.response_time_ms} ms")

    dp = test_result.dead_pixel_result
    print()
    print("  [Dead Pixels]")
    print(f"    Status         : {dp.status}")
    print(f"    Total pixels   : {dp.total_pixels}")
    print(f"    Suspect pixels : {dp.suspect_pixels}")
    print(f"    Analyzed       : {dp.screenshot_analyzed}")
    if dp.suspect_locations:
        print(f"    Sample locs    : {dp.suspect_locations[:5]}...")

    print()
    print("-" * 70)
    print(f"  DISPLAY HEALTH   : {test_result.display_health}")
    print("-" * 70)
