"""
AI Log Analyzer — Groq-powered intelligent boot log analysis.

Sends boot logs (UART, Apple crash, Android logcat, kernel dmesg) to Groq LLM
and returns structured diagnostic results.

Usage:
    analyzer = AILogAnalyzer(api_key="gsk_...")
    result = analyzer.analyze(log_text, mode="boot")
"""

import json
import re
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

# Groq API via their REST endpoint (no heavy SDK needed)
import urllib.request
import urllib.error

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
MAX_LOG_LENGTH = 15000  # ~3750 tokens input; leaves room for system prompt + 4096 output tokens

# Config file for persisting API key
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_API_KEY_FILE = _CONFIG_DIR / "groq_api_key.txt"


def save_api_key(key: str) -> None:
    """Save Groq API key to config file."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _API_KEY_FILE.write_text(key.strip(), encoding="utf-8")


def load_api_key() -> str:
    """Load saved Groq API key, or return empty string."""
    if _API_KEY_FILE.exists():
        return _API_KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


# ── Log type auto-detection ──────────────────────────────────────────────

APPLE_LOG_PATTERN = re.compile(
    r"Incident Identifier|Exception Type|Termination Reason|"
    r"Last Exception Backtrace|panicString|bug_type|panic-full|"
    r"Binary Images:|Process:\s|Thread \d+ Crashed:",
    re.IGNORECASE,
)

ANDROID_LOG_PATTERN = re.compile(
    r"Build fingerprint:|FATAL EXCEPTION:|E/AndroidRuntime|"
    r"ANR in |tombstone|SYSTEM_TOMBSTONE|WATCHDOG KILL|last_kmsg|"
    r"beginning of (main|system|crash)|signal \d+ \(SIG|"
    r"Abort message:|pid:\s*\d+,\s*tid:\s*\d+",
    re.IGNORECASE,
)

APPLE_FILE_PATTERN = re.compile(r"\.(ips|panic|crash|spin)$", re.IGNORECASE)
ANDROID_FILE_PATTERN = re.compile(
    r"(tombstone|logcat|bugreport|last_kmsg|anr|dropbox|kernel).*?\.(txt|log)$",
    re.IGNORECASE,
)

# Kernel dmesg format: [  676.856170] <4>.(4)[1:init] ...
DMESG_LOG_PATTERN = re.compile(r"\[\s*\d+\.\d+\]\s*<\d+>")


def detect_log_type(text: str, filename: str = "") -> str:
    """Auto-detect log type from content and/or filename.

    Returns: 'apple', 'android', 'dmesg', or 'boot'
    """
    if filename:
        if APPLE_FILE_PATTERN.search(filename):
            return "apple"
        if ANDROID_FILE_PATTERN.search(filename):
            return "android"
    if APPLE_LOG_PATTERN.search(text[:5000]):
        return "apple"
    if ANDROID_LOG_PATTERN.search(text[:5000]):
        return "android"
    # Detect kernel dmesg output (booted phone, UART gives kernel ring buffer)
    # Check before falling back to "boot" — dmesg has kernel timestamps like [  676.856170] <4>
    if DMESG_LOG_PATTERN.search(text[:5000]):
        return "dmesg"
    return "boot"


# ── System prompts (inspired by LUOWEI, customized for repair tool) ──────

SYSTEM_PROMPTS = {
    "boot": """You are an expert mobile phone repair technician analyzing UART boot logs from phone motherboards. Return JSON only, no markdown.

YOUR JOB: Extract EVERY piece of useful information from this boot log. A technician is paying for this analysis — give them detailed, specific information they can use. Do NOT give a lazy generic "everything is fine" response.

WHAT TO EXTRACT AND REPORT (always fill these in from the log data):
- Exact chipset model (e.g. MT6771/Helio P60, not just "MediaTek")
- PMIC chip model (e.g. MT6357) and its register status (PONSTS, POFFSTS, OC status, thermal status)
- All voltage rail readings (vcore, vproc, vmodem, vsram values in uV)
- RAM/DDR info (type, voltage, DDR reserve mode status, recalibration data)
- Storage type and speed (eMMC/UFS, capacity in MB, clock speed)
- Boot timing (#T# timestamps — how long each phase took in ms)
- ATF/TrustZone version and build date
- Boot reason (power key, USB, watchdog, etc.)
- Every I2C error with bus ID and address (which IC failed to respond)
- Every WARNING and ERROR line from ATF
- PMIC watchdog/reset status (TOP_RST_STATUS register)
- Any cert verify failures, secure boot status
- All IC probes (rt5738, hl7593, fan53526 etc.) — which exist, which don't

SEVERITY RULES:
1. If phone BOOTS to kernel: RAM is working. Don't mark RAM fail just because type string missing.
2. WiFi/BT/Camera/Audio/NFC/GPS/Display/Fingerprint init AFTER Android boots — not visible in UART. Mark as "not_testable_via_uart", never as fail.
3. I2C errors: CRITICAL — identify the actual IC from the address. Known MediaTek I2C IC mapping:
   - bus 3 addr 0x60 = MT6691ZXP (fan53526 driver) = EMI VDDQ DRAM signal voltage regulator (0.6V). If this fails, phone will logo-stuck/boot-loop.
   - bus 3 addr 0x6B = RT5738 = EMI VDD2 DRAM core voltage regulator (1.125V)
   - addr 0x50 = MT6691ZXP alternate address / EEPROM
   If the tool has already identified the IC and root cause (in the "TOOL ALREADY DETECTED" section), DO NOT just say "I2C error" — explain the IC, what it does, and repair steps specific to that IC.
4. ATF "unknown SMC" = firmware version mismatch, severity "info" but STILL REPORT IT with the exact SMC ID.
5. Watchdog previous reset from power key = normal. From "exception" or "HWT" = warning.
6. Cert verify failures = report as "warning" with exact partition name.
7. PMIC OC (overcurrent) shutdown flags = "critical".

ALWAYS create issue_cards for: I2C errors, ATF warnings, cert failures, abnormal boot reasons, PMIC anomalies, DDR issues. Even if minor — the technician wants to see them.
ALWAYS fill hardware_health with ALL subsystems you can detect from the log (CPU, RAM, Storage, PMIC, PLL, I2C buses, ATF, SPM, Watchdog).
ALWAYS fill device_info with specific values from the log (chip code, PMIC model, storage size, voltage values).

Output format:
{"analysis_mode":"boot","conclusion":{"verdict":"specific title mentioning chipset","status":"healthy|minor_issues|needs_repair|critical","health_percent":0,"reasoning":"detailed explanation referencing specific log evidence"},"device_info":{"chip":"exact model from log","brand":"","memory":"voltage and type if found","storage":"type, size, speed from log","battery":"voltage if found"},"boot_reason":{"reason":"exact reason from log","mode":"normal/fastboot/recovery/charger"},"issue_cards":[{"title":"specific issue name","symptom":"what happens","evidence":"EXACT log line copied from input","status":"confirmed|likely|possible","severity":"critical|warning|minor|info","impact":"what the user will experience","repair_action":"specific repair step"}],"hardware_health":[{"item":"subsystem name","result":"specific detail from log","status":"ok|fail|minor_issue|not_testable_via_uart"}],"recommendations":[{"title":"","priority":"high|medium|low|info","steps":["specific step 1","specific step 2"]}],"warnings":[]}""",

    "apple": """You are an expert Apple device repair technician analyzing iOS/macOS crash logs, panic logs, and diagnostic reports. Return JSON only, no markdown.

YOUR JOB: Extract EVERY piece of useful information from this Apple crash/panic log. A technician is paying for this analysis — give them detailed, specific information they can use to diagnose and repair the device. Do NOT give a lazy generic "everything is fine" response. If you see crash data, REPORT IT ALL.

WHAT TO EXTRACT FROM APPLE CRASH LOGS:
- Device model (iPhone12,1 = iPhone 11, etc.) and exact iOS/macOS version
- Process name that crashed, PID, parent process, crash time and uptime
- Exception Type: EXC_BAD_ACCESS (SIGSEGV/SIGBUS) = memory violation, EXC_CRASH (SIGABRT) = software abort, EXC_BREAKPOINT = assertion, EXC_RESOURCE = resource limit
- Termination Reason: exact namespace and code (e.g., SIGNAL 11, Watchdog, 0xdead10cc for background resource violation)
- Crash thread number and its full backtrace — report the key frames (which library/framework crashed)
- Binary images involved in the crash thread — system frameworks vs third-party dylibs
- VM Region info near the fault address — helps identify NULL deref vs wild pointer vs stack overflow
- Jetsam memory data: pageins, memory pressure level, footprint vs limit

HARDWARE vs SOFTWARE CRASH DISTINCTION (critical for repair techs):
1. EXC_BAD_ACCESS (SIGSEGV) in kernel/IOKit/driver code → LIKELY HARDWARE: bad RAM, failing NAND, GPU fault
2. EXC_BAD_ACCESS in user-space app code → SOFTWARE: app bug, corrupted install
3. Kernel panic with "NAND" or "AppleANS" in panic string → NAND FAILURE (needs board-level repair)
4. Panic with "baseband" / "CommCenter" / "AppleBCMWLAN" → BASEBAND/WIFI IC failure (hardware)
5. Panic with "gpu" / "AGX" / "IOGPU" / "AppleM2" → GPU FAILURE (logic board issue)
6. Panic with "AppleSMC" / "thermal" / "TMP" → THERMAL/SENSOR issue (check thermal paste, sensor flex)
7. Panic with "AppleCredentialManager" / "SEP" → SECURE ENCLAVE issue (Touch ID/Face ID related)
8. Watchdog timeout (0x8badf00d) → process hung too long — check for storage I/O bottleneck (dying NAND)
9. 0xdead10cc = backgrounded app holding file lock — software issue
10. 0xc00010ff = thermal kill — device overheating, check battery/thermal system
11. Repeated jetsam kills → possible RAM issue if across many apps, software if just one app

SPECIFIC THINGS TO LOOK FOR:
- panicString field in .ips panic logs — the MOST important line, extract it fully
- "SEP" or "Secure Enclave" errors → Face ID / Touch ID hardware
- "AppleUSBHostController" errors → Lightning/USB-C port issue
- "IOAudio" / "AppleHDAController" errors → audio IC failure
- "AppleBCMWLAN" / "IO80211" errors → WiFi/BT combo chip failure
- "CORESIGHT" / "CPUDBG" → CPU core failure
- "battery" / "AppleSmartBattery" / "charger" data → battery health info
- Repeated kernel panics with same panic string → consistent hardware fault
- "spin_lock" / "deadlock" in panic → possible hardware-induced hang
- Crashlog "bug_type" field: 210 = kernel panic, 109 = crash, 298 = jetsam

ALWAYS create issue_cards for: every crash/panic found, exception details, termination reasons, hardware-implicated frames, thermal events, NAND errors, baseband issues. Even minor — the technician wants the full picture.
ALWAYS fill hardware_health with subsystems you can assess: CPU, RAM, NAND/Storage, GPU, Baseband/Modem, WiFi/BT, Audio IC, Sensors, Battery, Secure Enclave, USB/Lightning port.
ALWAYS fill apple_context with specific values extracted from the log.
NEVER say "healthy" if there is a panic or crash in the log — at minimum it is "minor_issues".

Output format:
{"analysis_mode":"apple","conclusion":{"verdict":"specific title mentioning device and crash type","status":"healthy|minor_issues|needs_repair|critical","health_percent":0,"reasoning":"detailed explanation referencing specific log evidence"},"apple_context":{"log_type":"crash|panic|jetsam|spin|hang","device":"model identifier","os_version":"exact iOS/macOS version","process":"crashed process name and PID","crash_time":"timestamp from log"},"evidence_cards":[{"title":"specific finding name","excerpt":"EXACT log line copied from input","meaning":"what this means for hardware diagnosis","status":"confirmed|likely|possible"}],"issue_cards":[{"title":"specific issue name","category":"hardware|software|driver|thermal|storage|baseband|sensor","confidence":"confirmed|likely|possible","severity":"critical|warning|minor|info","symptom":"what the user experiences","evidence":"EXACT log line or panic string from input","impact":"user-visible effect","repair_action":"specific repair step for technician"}],"hardware_health":[{"item":"subsystem name","result":"specific detail from log","status":"ok|fail|minor_issue|not_testable"}],"recommendations":[{"title":"","priority":"high|medium|low|info","steps":["specific step 1","specific step 2"]}],"warnings":[]}""",

    "android": """You are an expert Android repair technician analyzing logcat, tombstone, ANR, and kernel logs from Android devices. Return JSON only, no markdown.

YOUR JOB: Extract EVERY piece of useful information from this Android log. A technician is paying for this analysis — give them detailed, specific information they can use to diagnose and repair the device. Do NOT give a lazy generic "everything is fine" response. If you see crashes, errors, or anomalies, REPORT THEM ALL with exact evidence.

WHAT TO EXTRACT FROM ANDROID LOGS:

From Tombstone/Native Crash Logs:
- Process name and PID/TID that crashed
- Signal number and name: SIGSEGV (11) = segfault/memory violation, SIGABRT (6) = abort/assertion, SIGBUS (7) = bus error/alignment, SIGFPE (8) = floating point, SIGILL (4) = illegal instruction
- Fault address (addr 0x0 = NULL deref, addr in code range = code corruption, addr in heap = heap corruption)
- Backtrace summary — report the key frames (which .so library crashed, which function)
- Build fingerprint (gives device model and Android version)
- Abort message (if SIGABRT — the exact abort reason string)
- Register dump highlights (PC, LR — what code was executing)

From Logcat Logs:
- FATAL EXCEPTION entries with full stack trace — extract exception class, message, and top frames
- E/AndroidRuntime crash blocks — the complete crash reason
- System.err and crash-related tags
- Battery stats: voltage, temperature, current, SOC (state of charge), health status
- Thermal data: CPU/GPU/battery temperatures, thermal throttling events, thermal shutdown warnings
- Memory pressure: "lowmemorykiller" kills, OOM adjustments, kswapd activity, "am_meminfo" entries
- GPU driver errors: "Adreno", "Mali", "PVR_K", "KGSL" errors (GPU hardware failure indicators)
- Audio errors: "AudioFlinger", "audio_hw", "tinymix" failures (audio IC or codec issues)
- Sensor failures: "SensorService", "accelerometer", "gyroscope" errors (sensor IC or flex cable)
- Camera errors: "CameraService", "camera_metadata", "mm-camera" failures
- Display/touchscreen: "HWComposer", "SurfaceFlinger" crashes, "input" service failures
- Modem/baseband: "RILJ", "RILC", "Telephony", "ims" errors, "radio" log entries
- WiFi/BT: "wlan", "WifiHAL", "bluetooth", "Bluetooth" errors
- Storage: "mmc", "f2fs", "ext4" errors, I/O errors (dying eMMC/UFS indicators)

From ANR Logs:
- ANR reason (Input dispatching timed out, Broadcast timeout, Service timeout)
- Process that ANR'd and what it was waiting for
- CPU usage at time of ANR (if CPU usage is very high → software; if I/O wait is very high → storage issue)
- Lock contention — which thread holds the lock

HARDWARE vs SOFTWARE CRASH DISTINCTION (critical for repair techs):
1. App crash (SIGABRT in Java/app code) → SOFTWARE: app bug, reinstall app
2. Native crash in system .so with SIGSEGV → LIKELY HARDWARE if repeated: bad RAM, eMMC corruption
3. system_server crash/restart → CRITICAL: if repeated, indicates hardware instability (RAM, eMMC, CPU)
4. zygote crash → CRITICAL: system-wide instability, often hardware if persistent
5. surfaceflinger crash → GPU or display driver issue, possibly hardware
6. mediaserver/audioserver crash → media codec or audio IC issue
7. Kernel panic in dmesg/last_kmsg → hardware failure (RAM, storage, power)
8. Watchdog kill of system_server → system hung, check for storage I/O or RAM issues
9. GPU driver crash (Adreno/Mali/PVR) → GPU hardware failure
10. "EXT4-fs error" or "mmc" errors → eMMC/UFS dying (storage hardware failure)
11. Repeated "lowmemorykiller" → if killing system processes, possible RAM hardware issue
12. Thermal shutdown → overheating, check battery/thermal paste/IC shielding
13. Baseband crash (modem reset, RILC crash) → baseband IC failure

PATTERN ANALYSIS (look for these patterns across the whole log):
- Same process crashing repeatedly → persistent fault (hardware if system process, software if app)
- Kernel panics in dmesg section → hardware instability
- Watchdog kills → system hang, often storage or RAM
- Escalating OOM kills → memory leak (software) or failing RAM (hardware)
- I/O errors followed by crashes → storage hardware failing
- Thermal throttling followed by crashes → overheating causing instability

ALWAYS create issue_cards for: every crash/tombstone, every ANR, system_server restarts, driver errors, thermal warnings, storage errors, GPU errors, sensor failures, audio errors, battery anomalies. Even minor items — the technician needs the full picture.
ALWAYS fill hardware_health with ALL subsystems you can assess from the log: CPU, RAM, Storage (eMMC/UFS), GPU, Display, Touchscreen, Audio, Camera, Sensors, WiFi, Bluetooth, Modem/Baseband, Battery, USB port.
ALWAYS fill android_context with specific values extracted from the log (device model from build fingerprint, Android version, crashed process).
NEVER say "healthy" if there are crashes, tombstones, or ANRs in the log — at minimum it is "minor_issues".

Output format:
{"analysis_mode":"android","conclusion":{"verdict":"specific title mentioning device and primary issue","status":"healthy|minor_issues|needs_repair|critical","health_percent":0,"reasoning":"detailed explanation referencing specific log evidence"},"android_context":{"log_type":"logcat|tombstone|anr|bugreport|kernel","device":"model from build fingerprint","os_version":"Android version and build ID","process":"primary crashed process and PID","crash_time":"timestamp from log"},"evidence_cards":[{"title":"specific finding name","excerpt":"EXACT log line copied from input","meaning":"what this means for hardware diagnosis","status":"confirmed|likely|possible"}],"issue_cards":[{"title":"specific issue name","category":"hardware|software|driver|thermal|storage|baseband|sensor|memory|gpu|audio","confidence":"confirmed|likely|possible","severity":"critical|warning|minor|info","symptom":"what the user experiences","evidence":"EXACT log line or crash signature from input","impact":"user-visible effect","repair_action":"specific repair step for technician"}],"hardware_health":[{"item":"subsystem name","result":"specific detail from log","status":"ok|fail|minor_issue|not_testable"}],"recommendations":[{"title":"","priority":"high|medium|low|info","steps":["specific step 1","specific step 2"]}],"warnings":[]}""",

    "dmesg": """You are an expert mobile phone repair technician analyzing kernel dmesg logs from Android devices. This is kernel ring buffer output, NOT preloader boot log — the phone is already booted and running. Return JSON only, no markdown.

YOUR JOB: Extract EVERY piece of useful information from this kernel dmesg log. A technician is paying for this analysis — give them detailed, specific information they can use to diagnose and repair the device. Do NOT give a lazy generic "everything is fine" response. If you see errors, driver failures, or hardware anomalies, REPORT THEM ALL with exact evidence.

UNDERSTANDING DMESG FORMAT:
- Lines look like: [  676.856170] <4>.(4)[1:init] message here
- [timestamp] = seconds since boot
- <N> = kernel log level (0=emergency, 3=error, 4=warning, 6=info, 7=debug)
- (N)[pid:name] = CPU core, process ID and name that generated the message

WHAT TO EXTRACT FROM KERNEL DMESG:

GPU Driver Errors (hardware failure indicators):
- "PVR_K" errors (PowerVR/MediaTek GPU) — report exact error code and message
- "mali" errors (ARM Mali GPU) — GPU job failures, page faults, register timeouts
- "adreno" / "kgsl" errors (Qualcomm GPU) — GPU hang, pagefault, CP errors
- "gpu" fault, timeout, or reset messages
- Any GPU "hang" or "recovery" messages indicate GPU IC problems

Sensor Service Failures:
- "scp" (Sensor Co-Processor) errors or timeouts — sensor hub IC failure
- "accelerometer", "gyroscope", "als_ps" (ambient light/proximity) init failures
- "mag" (magnetometer) errors
- I2C/SPI errors to sensor addresses — sensor flex cable or IC failure

Audio Errors:
- "mt6359" / "mt6358" (MediaTek audio codec PMIC) errors
- "sound" / "soc-audio" / "asoc" errors — audio codec failure
- "accdet" (accessory detect / headphone jack) errors
- "smartpa" / "speaker" amp errors (speaker IC failure)

Thermal Data (extract ALL values):
- CPU temperature readings (e.g., "thermal_zone" entries with temp values)
- Battery temperature
- PMIC temperature
- GPU temperature
- Thermal throttling events ("trip_point", "cooling_device")
- Thermal shutdown warnings (CRITICAL — overheating)

Battery and Charging Data (extract ALL values):
- Battery voltage (mV), current (mA), SOC (%), temperature
- Charger type, charging current, input current limit
- "battery" health status, cycle count
- "gauge" or "fuel_gauge" readings
- "pmic" / "mt6357" / "mt6358" / "mt6359" charging IC status
- OVP (over-voltage protection) or OCP (over-current protection) events

Modem/Baseband Status:
- "ccci" (Cross Core Communication Interface) errors — modem communication with AP
- "ccmni" network interface errors
- Modem reset/crash events
- "md1" (modem) status changes, exceptions
- SIM card detection status

Storage Health:
- "mmc" errors (eMMC) — block read/write failures indicate dying storage
- "ufs" errors — UFS storage failures
- "f2fs" / "ext4" filesystem errors — corruption from bad storage
- I/O errors, command timeouts, CRC errors

Memory Issues:
- OOM (Out Of Memory) killer events — what processes were killed, memory stats
- "lowmemorykiller" activity
- kswapd excessive activity
- Memory pressure warnings
- Slab allocation failures

Watchdog Events:
- "watchdog" bark or bite — system hang detected
- "wdt" (watchdog timer) resets
- "hang_detect" triggers
- "SWT" (software watchdog timeout)

SELinux/Permission (configuration issues):
- "avc: denied" messages — SELinux blocking access (may explain app failures)
- Report the source process, target, and permission denied

Process Crashes:
- Kernel oops, BUG, WARNING messages with call traces
- "Unable to handle kernel" errors — kernel crash (hardware likely)
- "Call trace:" blocks — extract the key function names
- Segfaults in userspace reported by kernel

SEVERITY AND DIAGNOSIS RULES:
1. GPU driver crash/timeout/pagefault → LIKELY HARDWARE: GPU IC failure, needs reballing or IC replacement
2. Sensor I2C/SPI errors → LIKELY HARDWARE: sensor IC or flex cable failure
3. Audio codec errors → LIKELY HARDWARE: audio IC or PMIC audio section failure
4. Storage I/O errors, mmc/ufs errors → CRITICAL HARDWARE: dying eMMC/UFS, needs storage replacement
5. Modem (ccci) crash → LIKELY HARDWARE: baseband IC failure
6. Repeated kernel oops/BUG at same location → HARDWARE: RAM or CPU issue
7. OOM kills of system processes → SOFTWARE if isolated, HARDWARE if RAM is abnormally small
8. SELinux denials → CONFIG/SOFTWARE: not hardware, but may explain user-reported issues
9. Thermal shutdown → HARDWARE CONCERN: check battery, thermal paste, IC shielding
10. Battery OVP/OCP → HARDWARE: charging IC or battery failure
11. Watchdog kills → system instability, correlate with other errors for root cause

ALWAYS create issue_cards for: GPU errors, sensor failures, audio errors, storage errors, thermal warnings, battery anomalies, modem crashes, kernel crashes, watchdog events, OOM kills. Even minor items — the technician needs the full picture.
ALWAYS fill hardware_health with ALL subsystems detectable from dmesg: CPU, RAM, GPU, Storage (eMMC/UFS), Display, Audio, Sensors, WiFi/BT, Modem/Baseband, Battery/Charging, Thermal, USB.
ALWAYS extract and report: CPU temperatures, battery voltage/current/SOC, memory stats, process crashes.
NEVER say "healthy" if there are errors, driver crashes, or hardware anomalies in the log — at minimum it is "minor_issues".

Output format:
{"analysis_mode":"dmesg","conclusion":{"verdict":"specific title mentioning chipset and primary issue","status":"healthy|minor_issues|needs_repair|critical","health_percent":0,"reasoning":"detailed explanation referencing specific log evidence"},"device_info":{"chip":"chipset from log if detectable","brand":"","memory":"RAM info if found","storage":"storage type/errors if found","battery":"voltage/current/SOC/temp if found"},"thermal_data":{"cpu_temp":"value if found","battery_temp":"value if found","gpu_temp":"value if found","pmic_temp":"value if found","throttling":"yes/no and details"},"evidence_cards":[{"title":"specific finding name","excerpt":"EXACT log line copied from input","meaning":"what this means for hardware diagnosis","status":"confirmed|likely|possible"}],"issue_cards":[{"title":"specific issue name","category":"hardware|software|driver|thermal|storage|baseband|sensor|memory|gpu|audio|config","confidence":"confirmed|likely|possible","severity":"critical|warning|minor|info","symptom":"what the user experiences","evidence":"EXACT log line from input","impact":"user-visible effect","repair_action":"specific repair step for technician"}],"hardware_health":[{"item":"subsystem name","result":"specific detail from log","status":"ok|fail|minor_issue|not_testable"}],"recommendations":[{"title":"","priority":"high|medium|low|info","steps":["specific step 1","specific step 2"]}],"warnings":[]}""",
}


# ── Analysis Result ──────────────────────────────────────────────────────

@dataclass
class AIAnalysisResult:
    """Result from AI log analysis."""
    success: bool = False
    mode: str = "boot"
    raw_response: str = ""
    parsed: Optional[Dict] = None
    error: str = ""
    tokens_used: int = 0


# ── Smart log extraction (strip filler, keep diagnostic data) ────────────

# Lines starting with these are filler — scanning status, UI emojis, etc.
_SKIP_PREFIXES = (
    "  🔍 ", "  🧠 ", "═══ SCANNING", "=== SCANNING",
    "  Checking", "  Reading", "  Sampling", "  Running",
    "  Detection complete",
)

# Report-specific lines to skip (tool output, not actual device data)
_REPORT_FILLER = (
    "MOOXY AI FAULT DETECTOR", "HARDWARE DETECTION REPORT",
    "BOOT THE PHONE NOW", "Opening FTDI", "Connected!",
    "Listening for", "This captures preloader",
    ">>> BOOT THE PHONE", "Report generated by",
    "bytes captured", "bytes received", "Analyzing boot data",
    "Running AI Rule Engine", "fault rules",
    "No known fault patterns", "Detection complete",
    "DETAILED COMPONENT REPORT", "═══ PHASE",
    "AI FAULT PATTERN MATCHING", "UART BOOT LOG ANALYSIS",
    "FAULT ANALYSIS", "FAULT CLASSIFICATION",
    "Problem #", "── Problem", "LIVE UART CAPTURE",
    "Two modes available", "UART Wiring",
    "Fault Detection Covers", "Boot Stage Progress",
    "BOOT STAGE PROGRESS", "FAULT REPORT",
    "RAW ERROR LINES FROM LOG",
)

# Section headers that contain useful diagnostic data
_IMPORTANT_SECTIONS = {
    "DEVICE IDENTIFIED", "DIAGNOSIS", "BATTERY", "THERMAL",
    "DISPLAY", "CAMERA", "SENSOR", "WIFI", "BLUETOOTH",
    "SIM", "IMEI", "MODEM", "AUDIO", "FINGERPRINT",
    "NFC", "GPS", "USB", "STORAGE", "MEMORY", "CPU",
    "GPU", "LOGCAT", "FAULT", "ERROR", "WARNING",
    "HEALTH", "POWER", "BOOT", "CRASH", "PANIC",
    "Incident Identifier", "Exception Type", "Thread",
    "Build fingerprint", "tombstone", "ANR",
}


def _is_tool_report(text: str) -> bool:
    """Detect if text is a processed report from Mooxy AI Fault Detector rather
    than raw boot/crash log data."""
    markers = [
        "MOOXY AI FAULT DETECTOR", "HARDWARE DETECTION REPORT",
        "═══ PHASE", "BOOT THE PHONE NOW", "Report generated by",
        "Hardware Health Check", "DETAILED COMPONENT REPORT",
        "UART BOOT LOG ANALYSIS",
    ]
    return sum(1 for m in markers if m in text[:4000]) >= 2


def _extract_diagnostic_from_report(text: str) -> str:
    """Extract actual device diagnostic data from a tool report.

    When the AI receives a processed report instead of raw boot log, this
    function pulls out only the lines that contain real device evidence:
    boot log error lines, hardware status, register values, component data.
    """
    lines = text.split("\n")
    extracted = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip purely decorative
        if all(c in "═─━─=─-_*● " for c in stripped):
            continue

        # Skip report filler
        if any(f in stripped for f in _REPORT_FILLER):
            continue

        # Skip emoji-only status lines without data
        if stripped in ("✅", "❌", "⚠️", "⚪", "🔴", "🟡"):
            continue

        # Keep lines with actual boot log evidence
        if any(marker in stripped for marker in (
            "[I2C]", "[ATF]", "[SEC_POLICY]", "[SBC]", "[PART]", "[RGU]",
            "[LOG]", "Boot Log Error", "PL fatal", "transfer error",
            "fails,ret=", "cert verify", "cert chain", "recalibration",
            "dvfsrc", "error mode",
        )):
            # Extract the actual error text from "[LOG] Boot Log Error = ..." format
            if "=" in stripped and "Boot Log Error" in stripped:
                error_part = stripped.split("=", 1)[-1].strip()
                if error_part:
                    extracted.append(error_part)
                    continue
            # Extract from "→ Error found in boot log: ..." format
            if "→" in stripped and "boot log:" in stripped.lower():
                error_part = stripped.split(":", 1)[-1].strip()
                if error_part:
                    extracted.append(error_part)
                    continue
            extracted.append(stripped)
            continue

        # Keep device info lines (Chipset, Brand, Boot Stage, etc.)
        if any(k in stripped for k in (
            "Chipset:", "Brand:", "Boot Stage:", "Storage:", "Board:",
            "CPU Cores:", "Boot Reason:", "Kernel Entry:", "Abnormal Boot:",
            "RAM:", "Version:", "MTK Chip",
        )):
            extracted.append(stripped)
            continue

        # Keep hardware status lines (✅ RAM: OK, ❌ Display: FAIL)
        if stripped.startswith(("✅", "❌", "⚠️")) and ":" in stripped:
            extracted.append(stripped)
            continue

        # Keep register/PMIC evidence data
        if any(k in stripped for k in (
            "Evidence:", "PWRAP", "rdata=", "PASS", "FAIL",
            "PLL", "SPM", "PMIC", "EMI", "DRAM", "MTEST",
            "ATF", "BL31", "Watchdog", "WDT", "Reset Status",
        )):
            extracted.append(stripped)
            continue

    if not extracted:
        # Fallback: return original but stripped of heavy filler
        return text

    # Add context header for AI
    header = "UART Boot Log Data (extracted from detection report):"
    return header + "\n" + "\n".join(extracted)


def _normalize_log_line(line: str) -> str:
    """Normalize a log line for deduplication (strip timestamps, PIDs, etc.)."""
    import re
    # Strip kernel dmesg timestamps: [  676.856170]
    s = re.sub(r"^\[\s*[\d.]+\]\s*", "", line)
    # Strip CPU/thread markers: <4>.(4)[1:init]
    s = re.sub(r"<\d+>[.-]?\(\d+\)\[\d+:[^\]]*\]", "", s)
    # Strip PID/TID numbers
    s = re.sub(r"\bpid[:= ]*\d+", "pid:N", s)
    s = re.sub(r"\btid[:= ]*\d+", "tid:N", s)
    # Strip transaction IDs
    s = re.sub(r"\btransaction \d+", "transaction N", s)
    # Strip audit timestamps
    s = re.sub(r"audit\(\d+\.\d+:\d+\)", "audit(N)", s)
    return s.strip()


def _smart_extract(text: str, max_chars: int) -> str:
    """Extract only diagnostically useful lines from a log.

    Strips filler (scanning messages, decorative lines, repeated separators),
    binary garbage from UART byte decoding, and deduplicates repeated messages.
    Also detects when input is a processed report and extracts real data.
    """
    # If this is a processed report, extract the real diagnostic data first
    if _is_tool_report(text):
        text = _extract_diagnostic_from_report(text)

    lines = text.split("\n")

    kept = []
    total = 0
    skip_decorative_run = 0  # count consecutive decorative lines
    seen_normalized = {}  # normalized_line -> count (for deduplication)

    for line in lines:
        stripped = line.strip()

        # Skip empty-ish and purely decorative lines entirely
        if not stripped or all(c in "═─━─=─-_*" for c in stripped):
            skip_decorative_run += 1
            continue
        # After 3+ consecutive blanks, insert one separator for readability
        if skip_decorative_run >= 3 and kept and kept[-1] != "":
            kept.append("")
        skip_decorative_run = 0

        # Skip scanning/progress filler
        if any(stripped.startswith(p.strip()) for p in _SKIP_PREFIXES):
            continue

        # Strip binary garbage from UART byte decoding
        # Lines with mostly replacement chars (U+FFFD) or non-printable bytes
        replacement_count = stripped.count("\ufffd")
        non_printable = sum(1 for c in stripped if not c.isprintable() and c not in "\t ")
        garbage_count = replacement_count + non_printable
        if garbage_count > 0:
            if garbage_count > len(stripped) * 0.3:
                # Mostly garbage — skip entire line
                continue
            # Partially garbage — strip the non-printable prefix/suffix, keep printable
            cleaned = "".join(c for c in stripped if c.isprintable() or c in "\t ")
            cleaned = cleaned.strip()
            if len(cleaned) < 4:
                continue
            stripped = cleaned
            line = cleaned

        # Deduplicate repeated messages (common in dmesg/kernel logs)
        # Keep first occurrence, count repeats, add summary at end
        norm = _normalize_log_line(stripped)
        if norm in seen_normalized:
            seen_normalized[norm] += 1
            continue  # skip duplicate
        seen_normalized[norm] = 1

        # Keep the line
        kept.append(stripped)
        total += len(stripped) + 1

        # Hard limit
        if total > max_chars:
            kept.append("[... REMAINING LOG TRIMMED ...]")
            break

    # Append dedup summary for heavily repeated messages
    repeats = [(norm, count) for norm, count in seen_normalized.items() if count > 2]
    if repeats:
        repeats.sort(key=lambda x: -x[1])
        kept.append("")
        kept.append("[REPEATED MESSAGES SUMMARY]")
        for norm, count in repeats[:15]:
            kept.append(f"  ({count}x) {norm[:120]}")

    result = "\n".join(kept)

    # Final safety — if still too big, hard truncate head+tail
    if len(result) > max_chars:
        half = max_chars // 2
        result = (
            result[:half]
            + "\n\n[... MIDDLE TRIMMED ...]\n\n"
            + result[-half:]
        )

    return result


# ── Analyzer ─────────────────────────────────────────────────────────────

class AILogAnalyzer:
    """Sends logs to Groq API and parses structured results."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or load_api_key()

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("gsk_"))

    def is_available(self) -> bool:
        """Check if Groq API is reachable (quick connectivity test)."""
        if not self.is_configured():
            return False
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "MobileRepairTool/1.0",
                },
            )
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    def analyze(self, log_text: str, mode: str = "boot",
                callback=None, detected_context: str = "") -> AIAnalysisResult:
        """Analyze a log using Groq LLM.

        Args:
            log_text: The raw log content.
            mode: 'boot', 'apple', 'android', or 'dmesg'.
            callback: Optional callable(status_msg) for progress updates.

        Returns:
            AIAnalysisResult with parsed JSON or error.
        """
        result = AIAnalysisResult(mode=mode)

        if not self.is_configured():
            result.error = "Groq API key not configured. Enter your key in Settings."
            return result

        if not log_text or not log_text.strip():
            result.error = "No log content to analyze."
            return result

        # Smart extraction — strip filler, keep only diagnostic data
        # Reserve space for detected_context if provided
        log_budget = MAX_LOG_LENGTH
        if detected_context:
            log_budget = MAX_LOG_LENGTH - min(len(detected_context), 3000)

        context_logs = _smart_extract(log_text.strip(), max(log_budget, 8000))

        # Prepend tool's already-detected findings so AI doesn't duplicate
        if detected_context:
            user_content = (
                "=== TOOL ALREADY DETECTED (use this as context, expand on it) ===\n"
                + detected_context[:3000]
                + "\n\n=== RAW BOOT LOG ===\n"
                + context_logs
            )
        else:
            user_content = context_logs

        system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["boot"])

        if callback:
            callback("Sending log to Groq AI for analysis...")

        # Build request
        payload = json.dumps({
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }).encode("utf-8")

        req = urllib.request.Request(
            GROQ_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "MobileRepairTool/1.0",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            if callback:
                callback("Waiting for AI response...")

            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            # Extract response
            choices = body.get("choices", [])
            if not choices:
                result.error = "AI returned empty response."
                return result

            ai_message = choices[0].get("message", {}).get("content", "")
            result.raw_response = ai_message
            result.tokens_used = body.get("usage", {}).get("total_tokens", 0)

            if callback:
                callback("Parsing AI analysis results...")

            # Parse JSON from response
            result.parsed = self._extract_json(ai_message)
            if result.parsed:
                result.success = True
            else:
                result.error = "Could not parse structured JSON from AI response."

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8", errors="replace")
                error_data = json.loads(error_body)
                error_body = error_data.get("error", {}).get("message", error_body)
            except Exception:
                pass
            if e.code == 401:
                result.error = "Invalid Groq API key. Check config/groq_api_key.txt"
            elif e.code == 429 or (e.code == 413 and "rate_limit" in error_body.lower()):
                result.error = "Rate limit hit — wait 60 seconds and retry. Groq free tier: 12K tokens/min."
            elif e.code == 413:
                result.error = "Log too large for API. Try a shorter log or paste only the relevant section."
            else:
                result.error = f"API Error (HTTP {e.code}): {error_body or str(e)}"
        except urllib.error.URLError as e:
            result.error = f"Network error: {e.reason}. Check your internet connection."
        except TimeoutError:
            result.error = "Request timed out. The log may be too large — try a shorter one."
        except Exception as e:
            result.error = f"Unexpected error: {str(e)}"

        return result

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract and parse JSON from AI response text."""
        cleaned = text.strip()

        # Try to extract from markdown code block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()
        elif "{" in cleaned and "}" in cleaned:
            # Find the outermost JSON object
            start = cleaned.index("{")
            end = cleaned.rindex("}") + 1
            cleaned = cleaned[start:end]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try fixing common issues: trailing commas
            fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return None


# ── Ollama (Local LLM) Analyzer ─────────────────────────────────────────

OLLAMA_API_URL = "http://localhost:11434/api/chat"
OLLAMA_MODELS_URL = "http://localhost:11434/api/tags"
OLLAMA_DEFAULT_MODEL = "llama3"  # Works with llama3, llama3.1, mistral, gemma2, etc.

# Simplified system prompt for local models (smaller context window)
OLLAMA_SYSTEM_PROMPT = """You are an expert mobile phone repair technician analyzing device logs. Return JSON only, no markdown.

Analyze the log and return this JSON format:
{"analysis_mode":"boot","conclusion":{"verdict":"short title","status":"healthy|minor_issues|needs_repair|critical","health_percent":0,"reasoning":"explanation"},"device_info":{"chip":"","brand":"","memory":"","storage":"","battery":""},"issue_cards":[{"title":"issue name","symptom":"what happens","evidence":"exact log line","status":"confirmed|likely|possible","severity":"critical|warning|minor|info","impact":"user effect","repair_action":"specific fix"}],"hardware_health":[{"item":"component","result":"detail","status":"ok|fail|minor_issue|not_testable_via_uart"}],"recommendations":[{"title":"","priority":"high|medium|low","steps":["step 1","step 2"]}],"warnings":[]}

RULES:
1. If phone boots to kernel: RAM is working, don't mark fail.
2. WiFi/BT/Camera/Audio init happens after Android boots — not visible in UART. Mark as "not_testable_via_uart".
3. I2C errors are CRITICAL — identify the IC from address.
4. PMIC overcurrent/thermal flags are CRITICAL.
5. Always report every error, warning, and anomaly you find.
6. Be specific — exact chipset, exact voltage values, exact error lines."""


class OllamaAnalyzer:
    """Sends logs to locally-running Ollama for offline AI analysis."""

    def __init__(self, model: str = ""):
        self.model = model or OLLAMA_DEFAULT_MODEL

    @staticmethod
    def is_available() -> bool:
        """Check if Ollama is running locally."""
        try:
            req = urllib.request.Request(OLLAMA_MODELS_URL)
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    @staticmethod
    def get_available_models() -> list:
        """Get list of models installed in Ollama."""
        try:
            req = urllib.request.Request(OLLAMA_MODELS_URL)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    def analyze(self, log_text: str, mode: str = "boot",
                callback=None, detected_context: str = "") -> AIAnalysisResult:
        """Analyze a log using local Ollama LLM."""
        result = AIAnalysisResult(mode=mode)

        if not self.is_available():
            result.error = ("Ollama is not running. Install from https://ollama.com "
                           "and run: ollama pull llama3")
            return result

        if not log_text or not log_text.strip():
            result.error = "No log content to analyze."
            return result

        # Use smaller context for local models
        context_logs = _smart_extract(log_text.strip(), 8000)

        if detected_context:
            user_content = (
                "=== TOOL DETECTED ===\n"
                + detected_context[:2000]
                + "\n\n=== RAW LOG ===\n"
                + context_logs
            )
        else:
            user_content = context_logs

        if callback:
            callback(f"Sending to local Ollama ({self.model})...")

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 4096,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_API_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            if callback:
                callback(f"Waiting for Ollama response ({self.model})... this may take a minute")

            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            ai_message = body.get("message", {}).get("content", "")
            result.raw_response = ai_message

            eval_data = body.get("eval_count", 0)
            prompt_data = body.get("prompt_eval_count", 0)
            result.tokens_used = eval_data + prompt_data

            if callback:
                callback("Parsing Ollama results...")

            result.parsed = self._extract_json(ai_message)
            if result.parsed:
                result.success = True
            else:
                result.error = "Could not parse JSON from Ollama response."

        except urllib.error.URLError as e:
            result.error = f"Cannot connect to Ollama: {e.reason}. Is Ollama running?"
        except TimeoutError:
            result.error = "Ollama timed out (5 min). Try a smaller log or faster model."
        except Exception as e:
            result.error = f"Ollama error: {str(e)}"

        return result

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """Extract JSON from Ollama response."""
        cleaned = text.strip()

        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()
        elif "{" in cleaned and "}" in cleaned:
            start = cleaned.index("{")
            end = cleaned.rindex("}") + 1
            cleaned = cleaned[start:end]

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            fixed = re.sub(r",\s*([}\]])", r"\1", cleaned)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return None
