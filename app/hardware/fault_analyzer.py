"""
Fault Analyzer — Analyzes detected data and identifies exact problems.

Takes detection results from UART, ADB, or JTAG and produces:
1. What is the problem
2. Which component is faulty
3. What to check (test points, voltages)
4. How to fix it (repair steps)
5. Replacement parts needed
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Fault:
    """A single detected fault/problem."""
    severity: str = "warning"           # critical, warning, info
    component: str = ""                 # Which component (RAM, Display, WiFi IC, etc.)
    problem: str = ""                   # What is the problem
    evidence: str = ""                  # What data showed this problem
    possible_causes: List[str] = field(default_factory=list)
    what_to_check: List[str] = field(default_factory=list)
    repair_steps: List[str] = field(default_factory=list)
    parts_needed: List[str] = field(default_factory=list)
    estimated_difficulty: str = "medium"  # easy, medium, hard, expert
    confidence: int = 70                # 0-100 confidence score (default 70)


@dataclass
class FaultReport:
    """Complete fault analysis report."""
    device_info: str = ""
    total_faults: int = 0
    critical_count: int = 0
    warning_count: int = 0
    faults: List[Fault] = field(default_factory=list)
    healthy_components: List[str] = field(default_factory=list)
    summary: str = ""


def analyze_uart_result(result) -> FaultReport:
    """Analyze UART detection result for faults."""
    report = FaultReport()
    report.device_info = f"{result.chipset} device"

    # Check boot registers for errors
    if hasattr(result, 'raw_responses'):
        responses = result.raw_responses

        # EC register (Error Code)
        ec_val = ""
        for line in result.uart_log:
            if "EC" in line and "Error Code" in line:
                if "0000 0000" not in line:
                    ec_val = line

        if ec_val:
            report.faults.append(Fault(
                severity="critical",
                component="CPU / Motherboard",
                problem="Hardware Error Code detected in boot registers",
                evidence=ec_val,
                possible_causes=[
                    "CPU internal fault",
                    "Power supply issue to SoC",
                    "Motherboard damaged (drop/water)",
                ],
                what_to_check=[
                    "Check all power rails with multimeter",
                    "Check for short circuits around CPU",
                    "Look for physical damage on motherboard",
                    "Check CPU BGA solder joints under microscope",
                ],
                repair_steps=[
                    "Reball/reflow CPU if solder joints are cracked",
                    "Replace faulty power management IC if power rails abnormal",
                    "If CPU dead — motherboard replacement needed",
                ],
                estimated_difficulty="expert",
            ))

        # No chip detected
        # raw_data is hex-encoded (2 chars per byte), so 200 hex chars = 100 bytes
        if result.chipset == "Unknown" and hasattr(result, 'raw_data') and len(result.raw_data) < 200:
            report.faults.append(Fault(
                severity="critical",
                component="CPU / SoC",
                problem="CPU not responding — no boot data received",
                evidence="UART received no readable boot data",
                possible_causes=[
                    "CPU/SoC is dead",
                    "Power Management IC (PMIC) not providing power",
                    "Battery not connected or dead",
                    "UART test points wrong or not connected",
                ],
                what_to_check=[
                    "Check battery voltage (should be 3.7-4.2V)",
                    "Check PMIC output voltages",
                    "Verify UART TX/RX connections",
                    "Check for short circuit on power rails",
                ],
                repair_steps=[
                    "If battery dead: replace battery",
                    "If PMIC not outputting: replace PMIC",
                    "If CPU dead: motherboard replacement needed",
                ],
                estimated_difficulty="expert",
            ))

        # Boot stops at BROM (no preloader)
        boot_stage = responses.get("boot_stage", "")
        if "Jump to Bootloader" in boot_stage:
            # Check if preloader data was received
            data_size = responses.get("data_received", "0")
            if "bytes" in data_size:
                size = int(data_size.split()[0])
                if size < 5000:
                    report.faults.append(Fault(
                        severity="warning",
                        component="Storage (eMMC/UFS)",
                        problem="Phone stuck at BROM — Preloader not loading from storage",
                        evidence=f"Boot reached BROM but only {size} bytes of data (preloader should produce 15KB+)",
                        possible_causes=[
                            "eMMC/UFS storage chip faulty or corrupted",
                            "Preloader partition corrupted",
                            "Storage connection (BGA solder) broken",
                        ],
                        what_to_check=[
                            "Check eMMC/UFS power supply voltages",
                            "Try flashing preloader via SP Flash Tool",
                            "Check storage IC solder joints under microscope",
                        ],
                        repair_steps=[
                            "Flash stock firmware via SP Flash Tool (BROM mode)",
                            "If flash fails: reball/reflow eMMC/UFS chip",
                            "If still fails: replace eMMC/UFS chip",
                        ],
                        parts_needed=["eMMC/UFS chip (matching capacity)", "BGA stencil"],
                        estimated_difficulty="hard",
                    ))

        # RAM issues — only flag if kernel did NOT boot (if kernel boots, RAM works)
        ram_type = responses.get("ram_type", "")
        kernel_ok = responses.get("kernel_entry", "")
        boot_stage = responses.get("boot_stage", "")
        emi_detected = any(k in responses.get("readable_boot_log", "").lower()
                           for k in ("emi", "dram", "mtest", "memory"))
        phone_booted = ("kernel" in str(kernel_ok).lower() or
                        "ok" in str(kernel_ok).lower() or
                        boot_stage in ("XBL/ABL", "Kernel", "Android"))

        if not ram_type and result.chipset != "Unknown" and not phone_booted and not emi_detected:
            # RAM genuinely failed — phone can't boot without RAM
            report.faults.append(Fault(
                severity="critical",
                component="RAM (DRAM)",
                problem="RAM initialization failed — phone cannot boot",
                evidence="DRAM init not found and kernel did not start",
                possible_causes=[
                    "RAM chip faulty or dead",
                    "RAM solder joints broken (BGA issue)",
                    "VDD_DRAM voltage rail shorted or missing",
                ],
                what_to_check=[
                    "Check DRAM voltage rails (VDD_DRAM typically 1.1V for LPDDR4X)",
                    "Check RAM IC solder joints under microscope",
                    "Look for 'DRAM' or 'EMI' error messages in boot log",
                ],
                repair_steps=[
                    "Reball RAM chip",
                    "Replace RAM chip if reball fails",
                ],
                parts_needed=["LPDDR4X/LPDDR5 RAM IC (matching spec)"],
                estimated_difficulty="expert",
            ))
        elif not ram_type and result.chipset != "Unknown" and phone_booted:
            # Phone boots fine, just DRAM type not printed — this is NORMAL
            report.healthy_components.append(
                "RAM (DRAM): Working (phone boots successfully, type not printed in boot log)"
            )

        # Abnormal boot / crash
        abnormal = responses.get("abnormal_boot", "")
        if "Yes" in abnormal or "crash" in abnormal.lower():
            report.faults.append(Fault(
                severity="warning",
                component="System Software",
                problem="Previous boot was abnormal (crash detected)",
                evidence=abnormal,
                possible_causes=[
                    "Software crash / kernel panic",
                    "Hardware causing repeated crashes",
                    "Corrupted system partition",
                ],
                what_to_check=[
                    "Check if phone was recently dropped or water damaged",
                    "Check crash log in boot data",
                    "Try factory reset",
                ],
                repair_steps=[
                    "Flash stock firmware",
                    "If crashes continue: check hardware (RAM, storage, power)",
                ],
                estimated_difficulty="medium",
            ))

    # Healthy components
    if result.chipset != "Unknown":
        report.healthy_components.append(f"CPU/SoC: {result.chipset} — Working")
    if hasattr(result, 'hw_status') and result.hw_status:
        for key, info in result.hw_status.items():
            if isinstance(info, dict) and info.get("status") == "ok":
                report.healthy_components.append(f"{key}: OK")

    # Count faults
    report.total_faults = len(report.faults)
    report.critical_count = sum(1 for f in report.faults if f.severity == "critical")
    report.warning_count = sum(1 for f in report.faults if f.severity == "warning")

    if report.total_faults == 0:
        report.summary = "✅ No faults detected from UART boot log. All detected hardware is functioning normally."
    else:
        report.summary =    f"🚨 {report.total_faults} issue(s) found: {report.critical_count} critical, {report.warning_count} warnings"

    return report


def analyze_adb_result(result) -> FaultReport:
    """Analyze ADB detection result for faults.

    Design principles:
    - NEVER report Android permission restrictions as hardware faults
    - Only report confirmed hardware issues with solid evidence
    - Separate "confirmed" (high confidence) from "needs verification" (low confidence)
    - When in doubt, mark as "info" not "warning" or "critical"
    """
    report = FaultReport()
    report.device_info = f"{result.brand} {result.model}"

    # Helper: safely get dmesg component info
    dmesg = getattr(result, "dmesg_components", None) or {}

    # ── Battery Health ──────────────────────────────────────────────
    if result.battery_level >= 0 and result.battery_health and result.battery_health not in ["Good", "2", ""]:
        is_dead = result.battery_health in ["Dead", "4"]
        report.faults.append(Fault(
            severity="critical" if is_dead else "warning",
            component="Battery",
            problem=f"Battery health reported as: {result.battery_health}",
            evidence=f"Level: {result.battery_level}%, Health: {result.battery_health}, Temp: {result.battery_temp}, Voltage: {result.battery_voltage}",
            possible_causes=[
                "Battery degraded from age/usage cycles",
                "Battery may be swollen",
                "Charging IC overcharging the battery",
            ],
            what_to_check=[
                "Physically inspect battery for swelling",
                "Check battery voltage with multimeter (normal: 3.7-4.2V)",
                "Check charging IC output voltage",
            ],
            repair_steps=[
                "Replace battery with OEM or compatible battery",
                "Calibrate new battery (full charge > full discharge > full charge)",
            ],
            parts_needed=[f"Battery for {result.brand} {result.model}"],
            estimated_difficulty="easy",
            confidence=90 if is_dead else 75,
        ))

    # ── Battery Temperature ─────────────────────────────────────────
    if result.battery_temp:
        try:
            temp_val = float(result.battery_temp.replace("\u00b0C", "").strip())
            if temp_val > 50:
                # Only flag truly dangerous temps (>50C), not warm temps during charging
                report.faults.append(Fault(
                    severity="warning",
                    component="Battery / Motherboard",
                    problem=f"Battery temperature dangerously high: {result.battery_temp}",
                    evidence=f"Battery temp {result.battery_temp} (danger zone: >50C, normal: 25-40C)",
                    possible_causes=[
                        "Short circuit on motherboard",
                        "Faulty charging IC",
                        "Battery internal short",
                    ],
                    what_to_check=[
                        "Check for short circuits with thermal camera",
                        "Check charging IC temperature",
                        "Note which area of phone heats up",
                    ],
                    repair_steps=[
                        "Identify and fix short circuit",
                        "Replace charging IC if overheating",
                        "Replace battery if battery itself is hot",
                    ],
                    estimated_difficulty="medium",
                    confidence=80,
                ))
            elif temp_val > 45:
                # Warm — informational only, not a fault during charging/heavy use
                report.faults.append(Fault(
                    severity="info",
                    component="Battery Temperature",
                    problem=f"Battery is warm: {result.battery_temp}",
                    evidence=f"Battery temp {result.battery_temp} (slightly above normal 25-40C range)",
                    possible_causes=[
                        "Phone is charging (normal during fast charge)",
                        "Heavy CPU usage (gaming/benchmark)",
                        "Warm environment",
                    ],
                    what_to_check=[
                        "Monitor if temp drops after stopping charge/use",
                        "If temp stays >45C at idle: investigate further",
                    ],
                    repair_steps=[
                        "Usually no repair needed — monitor during idle",
                    ],
                    estimated_difficulty="easy",
                    confidence=30,
                ))
        except (ValueError, AttributeError):
            pass

    # ── IMEI / Baseband ─────────────────────────────────────────────
    if not result.imei or result.imei in ["Not accessible", ""]:
        bb = getattr(result, "baseband_version", "") or ""
        if bb and len(bb) > 3 and bb.lower() not in ["unknown", "null"]:
            # Baseband present = modem working, IMEI unreadable = permission issue
            report.faults.append(Fault(
                severity="info",
                component="IMEI (Permission Issue)",
                problem="IMEI not readable via ADB — this is an Android permission restriction, NOT a hardware fault",
                evidence=f"IMEI: not readable, Baseband: {bb} (modem is working)",
                possible_causes=[
                    "Android 10+ restricts IMEI access without carrier privilege",
                ],
                what_to_check=[
                    "Dial *#06# on phone to verify IMEI exists",
                ],
                repair_steps=[
                    "No repair needed — modem is working",
                ],
                estimated_difficulty="easy",
                confidence=15,
            ))
        else:
            # Baseband also empty — likely real modem issue
            report.faults.append(Fault(
                severity="critical",
                component="Baseband / Modem IC",
                problem="Baseband version empty — Modem firmware may be corrupt or IC faulty",
                evidence=f"IMEI: {result.imei or 'empty'}, Baseband: {bb or 'EMPTY'}",
                possible_causes=[
                    "Modem firmware corrupted",
                    "NVRAM modem data lost/corrupted",
                    "Modem IC hardware failure",
                    "Android permission restriction (less likely if baseband also empty)",
                ],
                what_to_check=[
                    "Check if phone shows network/signal bars",
                    "Dial *#06# — if IMEI shows, it's permission issue only",
                    "If no IMEI on screen either: modem firmware or IC fault",
                ],
                repair_steps=[
                    "Try Fix Baseband in IMEI Repair tab first (restarts modem services)",
                    "If that fails: flash modem firmware via SP Flash Tool / Odin",
                    "Last resort: reball/replace modem IC",
                ],
                estimated_difficulty="hard",
                confidence=70,
            ))

    # ── WiFi ────────────────────────────────────────────────────────
    # 02:00:00:00:00:00 is Android 10+ privacy MAC — NOT a hardware fault
    wifi_mac = result.wifi_mac or ""
    if not wifi_mac or wifi_mac == "":
        # Truly empty MAC — check wifi_state before blaming hardware
        wifi_state = getattr(result, "wifi_state", "") or ""
        if wifi_state.lower() in ["enabled", "running", "ok"]:
            # WiFi is running but MAC not readable — permission issue
            report.faults.append(Fault(
                severity="info",
                component="WiFi (Permission Issue)",
                problem="WiFi MAC not readable via ADB, but WiFi service is running",
                evidence=f"WiFi MAC: '{wifi_mac}', State: {wifi_state}",
                possible_causes=["Android restricts MAC address reading"],
                what_to_check=["Check WiFi works in Settings > WiFi"],
                repair_steps=["No repair needed"],
                estimated_difficulty="easy",
                confidence=10,
            ))
        else:
            # WiFi state also bad — could be real issue
            has_wifi_driver = dmesg.get("wifi/bt", {}).get("loaded", False)
            report.faults.append(Fault(
                severity="warning" if not has_wifi_driver else "info",
                component="WiFi IC / Module",
                problem="WiFi MAC empty and WiFi service not active",
                evidence=f"WiFi MAC: empty, State: {wifi_state}, Driver loaded: {has_wifi_driver}",
                possible_causes=[
                    "WiFi turned off by user (check Settings)",
                    "WiFi/Combo IC issue" if not has_wifi_driver else "WiFi disabled in settings",
                ],
                what_to_check=[
                    "Turn on WiFi in phone Settings first",
                    "If WiFi won't turn on: check combo IC",
                ],
                repair_steps=[
                    "Enable WiFi in Settings",
                    "If fails: reball WiFi/Combo IC",
                ],
                estimated_difficulty="easy" if has_wifi_driver else "hard",
                confidence=55 if not has_wifi_driver else 15,
            ))
    elif wifi_mac == "02:00:00:00:00:00":
        # Privacy MAC — WiFi is working, just randomized address
        pass  # No fault — this is normal Android 10+ behavior

    # ── Bluetooth ───────────────────────────────────────────────────
    bt_mac = result.bluetooth_mac or ""
    bt_state = getattr(result, "bt_state", "") or ""
    if not bt_mac or bt_mac in ["null"]:
        if bt_state.lower() in ["running", "on"]:
            pass  # BT running but MAC not readable — normal permission issue
        else:
            report.faults.append(Fault(
                severity="info",
                component="Bluetooth",
                problem="Bluetooth MAC not detected — may be turned off or permission issue",
                evidence=f"BT MAC: '{bt_mac}', State: {bt_state}",
                possible_causes=[
                    "Bluetooth turned off by user",
                    "Android permission restriction on BT MAC",
                    "Combo IC issue (if WiFi also not working)",
                ],
                what_to_check=[
                    "Turn on Bluetooth in Settings",
                    "If both WiFi and BT are dead: combo IC fault",
                ],
                repair_steps=[
                    "Enable Bluetooth in Settings",
                    "If fails and WiFi also dead: reball combo IC",
                ],
                estimated_difficulty="easy",
                confidence=30,
            ))

    # ── Camera ──────────────────────────────────────────────────────
    if not result.rear_camera and not result.front_camera:
        camera_info = (result.camera_info or "").lower()
        has_camera_driver = dmesg.get("camera", {}).get("loaded", False)
        camera_ids = getattr(result, "camera_ids", []) or []

        if camera_ids:
            # Camera IDs detected but rear/front not mapped — camera is present
            pass  # Not a fault, just facing info not parsed
        elif has_camera_driver:
            report.faults.append(Fault(
                severity="info",
                component="Camera (Permission Issue)",
                problem="Camera driver loaded in kernel but camera service not accessible via ADB",
                evidence=f"Camera info: {result.camera_info}, Driver: loaded",
                possible_causes=["Android permission restriction on camera service"],
                what_to_check=["Open camera app on phone to verify it works"],
                repair_steps=["No repair needed — test camera app directly"],
                estimated_difficulty="easy",
                confidence=15,
            ))
        elif "not accessible" in camera_info or not camera_info:
            report.faults.append(Fault(
                severity="info",
                component="Camera",
                problem="Camera info not accessible — likely Android permission restriction",
                evidence=f"Camera info: '{result.camera_info or 'empty'}'",
                possible_causes=[
                    "Android 10+ restricts camera service access via ADB (most common)",
                    "Camera module disconnected (less common)",
                ],
                what_to_check=[
                    "Open camera app on phone — if it works, this is just a permission issue",
                    "If camera app fails: check camera connector",
                ],
                repair_steps=[
                    "Test camera app first before any hardware repair",
                    "If camera app crashes: reseat camera flex cable",
                ],
                estimated_difficulty="easy",
                confidence=30,
            ))

    # ── SIM Card ────────────────────────────────────────────────────
    sim_state = result.sim_state or ""
    if sim_state.upper() in ["ABSENT", "NOT_READY", ""]:
        # Check if SIM is simply not inserted vs hardware fault
        report.faults.append(Fault(
            severity="info",
            component="SIM Card",
            problem=f"SIM not detected (state: '{sim_state or 'empty'}')",
            evidence=f"SIM state: {sim_state}, Operator: {result.sim_operator}",
            possible_causes=[
                "No SIM card inserted (most common)",
                "SIM card not seated properly",
                "SIM tray/connector issue",
            ],
            what_to_check=[
                "Verify a SIM card is actually inserted",
                "Try re-seating the SIM card",
                "Try a known-good SIM card",
            ],
            repair_steps=[
                "Insert SIM card properly",
                "Clean SIM connector with IPA",
                "If still fails with known-good SIM: replace SIM connector",
            ],
            estimated_difficulty="easy",
            confidence=35,
        ))

    # ── Sensors ─────────────────────────────────────────────────────
    sensors_list = getattr(result, "sensors_list", None) or []
    sensors = getattr(result, "sensors", None) or []
    if not sensors_list and not sensors:
        report.faults.append(Fault(
            severity="info",
            component="Sensors",
            problem="Sensor list empty via ADB — may be permission restriction",
            evidence="dumpsys sensorservice returned no sensors",
            possible_causes=[
                "Android permission restriction on sensor service",
                "Sensor hub IC disconnected (less common)",
            ],
            what_to_check=[
                "Install a sensor test app (like Sensor Kinetics) to verify",
                "If sensors work in apps: this is just ADB permission issue",
            ],
            repair_steps=[
                "Test sensors via phone app first",
                "If genuinely dead: check sensor flex cable",
            ],
            estimated_difficulty="easy",
            confidence=25,
        ))

    # ── Fingerprint ─────────────────────────────────────────────────
    fp_status = getattr(result, "fingerprint_status", "") or ""
    if fp_status and "not available" in fp_status.lower():
        has_fp_driver = dmesg.get("fingerprint", {}).get("loaded", False)
        report.faults.append(Fault(
            severity="info",
            component="Fingerprint Sensor",
            problem="Fingerprint service reports 'not available'",
            evidence=f"Status: {fp_status}, Driver in dmesg: {has_fp_driver}",
            possible_causes=[
                "Phone model may not have fingerprint sensor",
                "Fingerprint sensor disconnected",
                "Android permission restriction on fingerprint service",
            ],
            what_to_check=[
                "Check if phone model has a fingerprint sensor",
                "Go to Settings > Security > Fingerprint to verify",
            ],
            repair_steps=[
                "If phone has FP sensor and Settings shows error: reseat FP flex cable",
                "Replace FP sensor module if flex is OK",
            ],
            parts_needed=["Fingerprint sensor module"],
            estimated_difficulty="easy",
            confidence=25 if not has_fp_driver else 15,
        ))

    # ── Storage ─────────────────────────────────────────────────────
    if result.storage_free:
        try:
            free_gb = int(result.storage_free.replace("GB", "").strip())
            if free_gb < 2:
                report.faults.append(Fault(
                    severity="warning",
                    component="Storage",
                    problem=f"Storage almost full — only {result.storage_free} free",
                    evidence=f"Total: {result.storage_total}, Free: {result.storage_free}",
                    possible_causes=["Too many apps/files", "Cache buildup"],
                    what_to_check=["Check large files and apps in Storage settings"],
                    repair_steps=["Clear cache", "Remove unused apps", "Move files to SD card/cloud"],
                    estimated_difficulty="easy",
                    confidence=90,
                ))
        except (ValueError, AttributeError):
            pass

    # ── RAM ──────────────────────────────────────────────────────────
    if result.ram_free:
        try:
            free_mb = int(result.ram_free.replace("MB", "").strip())
            if free_mb < 150:
                report.faults.append(Fault(
                    severity="info",
                    component="RAM",
                    problem=f"Very low free RAM: {result.ram_free}",
                    evidence=f"Total: {result.ram_total}, Free: {result.ram_free}",
                    possible_causes=["Too many background apps", "Memory-hungry apps running"],
                    what_to_check=["Restart phone to see if RAM frees up"],
                    repair_steps=["Restart phone", "Close background apps", "Factory reset if persistent"],
                    estimated_difficulty="easy",
                    confidence=50,
                ))
        except (ValueError, AttributeError):
            pass

    # ── Logcat Crashes ──────────────────────────────────────────────
    crash_events = getattr(result, "logcat_crash_events", []) or []
    if len(crash_events) > 5:
        report.faults.append(Fault(
            severity="info",
            component="System Stability",
            problem=f"{len(crash_events)} system crashes detected in logcat",
            evidence=f"Crash events: {len(crash_events)} entries",
            possible_causes=["App crashes (normal)", "System instability", "Storage full causing crashes"],
            what_to_check=["Check if specific app keeps crashing", "Check storage space"],
            repair_steps=["Clear problem app data", "Factory reset if widespread"],
            estimated_difficulty="easy",
            confidence=40,
        ))

    # ── Build Healthy Components List ───────────────────────────────
    _build_healthy_list(result, report)

    # ── Count and Summarize ─────────────────────────────────────────
    # Only count warnings and criticals as real faults (not "info" items)
    real_faults = [f for f in report.faults if f.severity in ("warning", "critical")]
    info_items = [f for f in report.faults if f.severity == "info"]

    report.total_faults = len(real_faults)
    report.critical_count = sum(1 for f in real_faults if f.severity == "critical")
    report.warning_count = sum(1 for f in real_faults if f.severity == "warning")

    if report.total_faults == 0:
        report.summary = f"No hardware faults detected on {result.brand} {result.model}. All tested hardware is working normally."
        if info_items:
            report.summary += f" ({len(info_items)} info items — likely Android permission restrictions, not hardware issues)"
    else:
        confirmed = sum(1 for f in real_faults if f.confidence >= 70)
        needs_verify = sum(1 for f in real_faults if f.confidence < 70)
        report.summary = (
            f"{report.total_faults} issue(s) found on {result.brand} {result.model}: "
            f"{report.critical_count} critical, {report.warning_count} warnings"
        )
        if needs_verify:
            report.summary += f" ({needs_verify} need manual verification)"

    return report


def _build_healthy_list(result, report: FaultReport) -> None:
    """Build the list of confirmed healthy components from detection data."""
    # CPU / SoC
    if result.chipset and result.chipset != "Unknown":
        report.healthy_components.append(f"CPU / Processor: {result.chipset}")

    # Battery
    if result.battery_level >= 0 and result.battery_health in ["Good", "2"]:
        report.healthy_components.append(f"Battery: {result.battery_level}% ({result.battery_health})")

    # RAM
    if result.ram_total_kb > 0:
        report.healthy_components.append(f"RAM / Memory: {result.ram_total_kb // 1024}MB")

    # Storage
    if result.storage_total_kb > 0:
        report.healthy_components.append(f"Storage: {result.storage_total_kb // (1024*1024)}GB")

    # Display
    if result.display_resolution:
        report.healthy_components.append(f"Display: {result.display_resolution}")

    # Touchscreen (if display works, touch likely works)
    if result.display_resolution:
        report.healthy_components.append("Touchscreen")

    # WiFi — check actual data, not just MAC
    wifi_mac = result.wifi_mac or ""
    wifi_state = getattr(result, "wifi_state", "") or ""
    if wifi_mac and wifi_mac != "" or wifi_state.lower() in ["enabled", "running", "ok"]:
        report.healthy_components.append("WiFi")

    # Bluetooth
    bt_mac = result.bluetooth_mac or ""
    bt_state = getattr(result, "bt_state", "") or ""
    if bt_mac and bt_mac not in ["", "null"] or bt_state.lower() in ["running", "on"]:
        report.healthy_components.append("Bluetooth")

    # Camera — report as OK if camera IDs detected
    camera_ids = getattr(result, "camera_ids", []) or []
    if camera_ids:
        report.healthy_components.append(f"Camera: {len(camera_ids)} camera(s)")

    # Sensors
    sensors = getattr(result, "sensors", []) or []
    if sensors:
        report.healthy_components.append(f"Sensors: {len(sensors)} detected")

    # Audio
    audio_out = getattr(result, "audio_output_devices", []) or []
    if audio_out:
        report.healthy_components.append("Audio")

    # Fingerprint
    if getattr(result, "fingerprint_hardware_detected", False):
        report.healthy_components.append("Fingerprint")

    # NFC
    nfc = getattr(result, "nfc_enabled", None)
    if nfc is not None:
        report.healthy_components.append("NFC")

    # GPS
    gps = getattr(result, "gps_providers", "") or ""
    if gps:
        report.healthy_components.append("GPS / Location")

    # Thermal
    thermal = getattr(result, "thermal_zones", []) or []
    if thermal:
        report.healthy_components.append("Thermal")

    # USB
    usb = getattr(result, "usb_config", "") or ""
    if usb:
        report.healthy_components.append("USB")

    # hw_status from diagnosis engine
    hw_status = getattr(result, "hw_status", {}) or {}
    if hw_status:
        for key, info in hw_status.items():
            if isinstance(info, dict) and info.get("status") == "ok":
                name = key.replace("_", " ").title()
                if not any(name.lower() in h.lower() for h in report.healthy_components):
                    report.healthy_components.append(name)


def analyze_jtag_result(result) -> FaultReport:
    """Analyze JTAG detection result for faults."""
    report = FaultReport()

    if not result.cpu_alive:
        report.faults.append(Fault(
            severity="critical",
            component="CPU / SoC",
            problem="CPU is DEAD — not responding to JTAG",
            evidence=f"JTAG IDCODE: {result.cpu_id or 'No response'}",
            possible_causes=[
                "CPU chip is dead (no clock/power)",
                "PMIC not providing core voltage",
                "Crystal oscillator faulty",
                "Motherboard has short circuit",
            ],
            what_to_check=[
                "Check VDD_CORE voltage (typically 0.8-1.0V)",
                "Check main clock crystal (26MHz/19.2MHz)",
                "Check PMIC output rails",
                "Check for short circuit on motherboard",
            ],
            repair_steps=[
                "Fix short circuit if found",
                "Replace PMIC if no output voltage",
                "Replace crystal oscillator",
                "If CPU dead: motherboard replacement or CPU reballing",
            ],
            parts_needed=["PMIC IC", "26MHz crystal", "CPU IC (last resort)"],
            estimated_difficulty="expert",
        ))

    if result.cpu_alive and not result.ram_readable:
        report.faults.append(Fault(
            severity="critical",
            component="RAM (DRAM)",
            problem="CPU alive but RAM not accessible — RAM fault",
            evidence=f"JTAG RAM read test: {result.ram_test}",
            possible_causes=[
                "RAM chip dead",
                "RAM BGA solder joints broken (cold solder/crack)",
                "RAM power supply missing",
                "EMI controller fault in CPU",
            ],
            what_to_check=[
                "Check RAM power supply (VDDQ typically 0.6V, VDD2 1.1V)",
                "Check RAM IC solder joints under microscope",
                "Check for physical damage near RAM area",
            ],
            repair_steps=[
                "Reball RAM chip with proper stencil",
                "If reball fails: replace RAM chip",
                "Check and fix RAM power supply rails",
            ],
            parts_needed=["RAM IC (LPDDR4X/5)", "BGA reball stencil"],
            estimated_difficulty="expert",
        ))

    if result.cpu_alive and result.ram_readable:
        report.healthy_components.append("CPU: Alive and responding")
        report.healthy_components.append("RAM: Accessible and working")

    report.total_faults = len(report.faults)
    report.critical_count = sum(1 for f in report.faults if f.severity == "critical")
    report.warning_count = sum(1 for f in report.faults if f.severity == "warning")

    if report.total_faults == 0:
        report.summary = "✅ JTAG: CPU and RAM both working. No hardware faults at chip level."
    else:
        report.summary = f"🚨 {report.total_faults} critical fault(s) found via JTAG"

    return report
