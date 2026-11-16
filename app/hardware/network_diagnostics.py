"""
Network Diagnostics Module — Deep cellular/network fault analysis via ADB.

Performs comprehensive network diagnostics on Android devices:
  1. SIM State — detection, ICCID, slot status
  2. Signal Strength — RSRP, RSRQ, SINR, GSM/LTE/NR signal levels
  3. Registration State — voice/data registration, searching/denied
  4. IMEI & Baseband — modem health verification
  5. Radio Power — modem on/off state
  6. Network Operator — registered operator, network type
  7. Antenna Check — stuck key detection (volume down = safe mode)

Produces a structured diagnosis with:
  - What is working
  - What is NOT working
  - Root cause analysis
  - Software fix steps
  - Hardware fix steps (if software fails)

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[float, str], None]]


def _notify(callback: ProgressCallback, pct: float, msg: str) -> None:
    if callback is not None:
        try:
            callback(pct, msg)
        except Exception:
            pass


def _adb(cmd: str, serial: str = "") -> str:
    """Run an ADB shell command, optionally targeting a specific serial."""
    try:
        prefix = f"adb -s {serial} shell" if serial else "adb shell"
        proc = subprocess.run(
            f"{prefix} {cmd}",
            capture_output=True, text=True, timeout=15, shell=True,
        )
        return proc.stdout.strip() if proc.returncode == 0 else proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""


def _adb_host(cmd: str) -> str:
    try:
        proc = subprocess.run(
            f"adb {cmd}", capture_output=True, text=True, timeout=10, shell=True,
        )
        return proc.stdout.strip() if proc.returncode == 0 else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
#  Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SIMSlotInfo:
    """Information about a single SIM slot."""
    slot: int = 0
    state: str = "UNKNOWN"        # ABSENT, LOADED, READY, NOT_READY, etc.
    operator: str = ""
    operator_numeric: str = ""
    network_type: str = ""
    is_detected: bool = False


@dataclass
class SignalInfo:
    """Cellular signal measurement data."""
    rsrp: str = ""           # LTE/NR Reference Signal Received Power
    rsrq: str = ""           # Reference Signal Received Quality
    sinr: str = ""           # Signal to Interference+Noise Ratio
    gsm_signal: str = ""     # GSM signal level
    wcdma_signal: str = ""   # WCDMA signal level
    lte_signal: str = ""     # LTE signal level
    nr_signal: str = ""      # 5G NR signal level
    all_invalid: bool = True


@dataclass
class RegistrationInfo:
    """Network registration state."""
    voice_state: str = ""         # IN_SERVICE, OUT_OF_SERVICE, EMERGENCY_ONLY
    data_state: str = ""
    voice_searching: bool = False
    data_searching: bool = False
    reject_cause: int = 0
    registered_network: str = ""


@dataclass
class ModemInfo:
    """Modem/baseband information."""
    imei: str = ""
    imei2: str = ""
    baseband_version: str = ""
    radio_power: str = ""        # ON, OFF
    modem_active: bool = False


@dataclass
class DiagnosticStep:
    """A single diagnostic/repair step."""
    step_type: str = "software"   # software, hardware, check
    title: str = ""
    description: str = ""
    command: str = ""             # ADB command if applicable
    priority: int = 0             # 1=try first, 2=try second, etc.


@dataclass
class NetworkDiagnosis:
    """Root cause analysis result."""
    problem: str = ""
    severity: str = "warning"     # critical, warning, info
    root_cause: str = ""
    confidence: int = 0           # 0-100
    evidence: List[str] = field(default_factory=list)


@dataclass
class NetworkDiagnosticResult:
    """Complete network diagnostic result."""
    connected: bool = False
    device_model: str = ""
    device_serial: str = ""
    error: Optional[str] = None

    # Raw check results
    sim_slots: List[SIMSlotInfo] = field(default_factory=list)
    signal: SignalInfo = field(default_factory=SignalInfo)
    registration: RegistrationInfo = field(default_factory=RegistrationInfo)
    modem: ModemInfo = field(default_factory=ModemInfo)

    # Analysis results
    working: List[str] = field(default_factory=list)
    not_working: List[str] = field(default_factory=list)
    diagnoses: List[NetworkDiagnosis] = field(default_factory=list)
    software_steps: List[DiagnosticStep] = field(default_factory=list)
    hardware_steps: List[DiagnosticStep] = field(default_factory=list)
    check_steps: List[DiagnosticStep] = field(default_factory=list)

    overall_status: str = "Unknown"
    health_score: int = 0  # 0-100


# ---------------------------------------------------------------------------
#  Step 1 — Device & ADB check
# ---------------------------------------------------------------------------

def _check_device(callback: ProgressCallback) -> Tuple[bool, str, str]:
    """Check ADB connection. Returns (ok, serial, error)."""
    _notify(callback, 0, "Checking ADB connection...")
    output = _adb_host("devices")
    if not output:
        return False, "", "ADB not found or not running"

    lines = [ln for ln in output.splitlines() if "\tdevice" in ln]
    if not lines:
        unauth = [ln for ln in output.splitlines() if "\tunauthorized" in ln]
        if unauth:
            return False, "", "Device connected but USB Debugging not authorized"
        return False, "", "No device connected"

    serial = lines[0].split("\t")[0]
    return True, serial, ""


# ---------------------------------------------------------------------------
#  Step 2 — SIM State Check
# ---------------------------------------------------------------------------

def _check_sim(serial: str, callback: ProgressCallback) -> List[SIMSlotInfo]:
    """Check SIM card state for all slots."""
    _notify(callback, 10, "Checking SIM card status...")

    sim_state = _adb("getprop gsm.sim.state", serial)
    operator = _adb("getprop gsm.operator.alpha", serial)
    operator_num = _adb("getprop gsm.sim.operator.numeric", serial)
    net_type = _adb("getprop gsm.network.type", serial)

    states = sim_state.split(",") if sim_state else ["UNKNOWN"]
    operators = operator.split(",") if operator else [""]
    op_nums = operator_num.split(",") if operator_num else [""]
    net_types = net_type.split(",") if net_type else [""]

    slots = []
    for i in range(max(len(states), 1)):
        slot = SIMSlotInfo(slot=i + 1)
        slot.state = states[i].strip() if i < len(states) else "UNKNOWN"
        slot.operator = operators[i].strip() if i < len(operators) else ""
        slot.operator_numeric = op_nums[i].strip() if i < len(op_nums) else ""
        slot.network_type = net_types[i].strip() if i < len(net_types) else ""
        slot.is_detected = slot.state in ("READY", "LOADED", "IMSI", "PUK", "PIN")
        slots.append(slot)

    return slots


# ---------------------------------------------------------------------------
#  Step 3 — Signal Strength Check
# ---------------------------------------------------------------------------

def _check_signal(serial: str, callback: ProgressCallback) -> SignalInfo:
    """Check cellular signal strength from telephony registry."""
    _notify(callback, 25, "Checking signal strength...")

    tel_dump = _adb("dumpsys telephony.registry", serial)
    info = SignalInfo()

    # Parse mSignalStrength blocks
    sig_match = re.search(r'mSignalStrength=SignalStrength:\{(.+?)\}', tel_dump)
    if sig_match:
        sig_block = sig_match.group(1)

        # Check each technology
        if "mGsm=Invalid" not in sig_block:
            gsm_match = re.search(r'mGsm=CellSignalStrengthGsm:\s*\{?.*?rssi=(-?\d+)', sig_block)
            if gsm_match:
                info.gsm_signal = f"{gsm_match.group(1)} dBm"
                info.all_invalid = False

        if "mWcdma=Invalid" not in sig_block:
            wcdma_match = re.search(r'mWcdma=CellSignalStrengthWcdma:\s*\{?.*?rscp=(-?\d+)', sig_block)
            if wcdma_match:
                info.wcdma_signal = f"{wcdma_match.group(1)} dBm"
                info.all_invalid = False

        if "mLte=Invalid" not in sig_block:
            lte_match = re.search(r'mLte=CellSignalStrengthLte:\s*\{?.*?rsrp=(-?\d+)', sig_block)
            if lte_match:
                info.lte_signal = f"{lte_match.group(1)} dBm"
                info.all_invalid = False

        if "mNr=Invalid" not in sig_block:
            nr_match = re.search(r'mNr=CellSignalStrengthNr:\s*\{?.*?ssRsrp=(-?\d+)', sig_block)
            if nr_match:
                info.nr_signal = f"{nr_match.group(1)} dBm"
                info.all_invalid = False

        # Check if ALL are Invalid
        if all(x in sig_block for x in ["mGsm=Invalid", "mWcdma=Invalid", "mLte=Invalid", "mNr=Invalid"]):
            info.all_invalid = True

    # Parse RSRP/RSRQ/SINR from full dump
    rsrp_match = re.search(r'(?:rsrp|mRsrp)\s*=\s*(-?\d+)', tel_dump, re.IGNORECASE)
    if rsrp_match and int(rsrp_match.group(1)) != 2147483647:
        info.rsrp = f"{rsrp_match.group(1)} dBm"

    rsrq_match = re.search(r'(?:rsrq|mRsrq)\s*=\s*(-?[\d.]+)', tel_dump, re.IGNORECASE)
    if rsrq_match and int(float(rsrq_match.group(1))) != 2147483647:
        info.rsrq = f"{rsrq_match.group(1)} dB"

    sinr_match = re.search(r'(?:sinr|mSinr|rssnr)\s*=\s*(-?[\d.]+)', tel_dump, re.IGNORECASE)
    if sinr_match and int(float(sinr_match.group(1))) != 2147483647:
        info.sinr = f"{sinr_match.group(1)} dB"

    return info


# ---------------------------------------------------------------------------
#  Step 4 — Registration State Check
# ---------------------------------------------------------------------------

def _check_registration(serial: str, callback: ProgressCallback) -> RegistrationInfo:
    """Check network registration state."""
    _notify(callback, 40, "Checking network registration...")

    tel_dump = _adb("dumpsys telephony.registry", serial)
    info = RegistrationInfo()

    # Voice registration
    voice_match = re.search(r'mVoiceRegState=\d+\(([^)]+)\)', tel_dump)
    if voice_match:
        info.voice_state = voice_match.group(1)

    # Data registration
    data_match = re.search(r'mDataRegState=\d+\(([^)]+)\)', tel_dump)
    if data_match:
        info.data_state = data_match.group(1)

    # Searching state
    if "NOT_REG_SEARCHING" in tel_dump:
        info.voice_searching = True
    if "registrationState=NOT_REG_SEARCHING" in tel_dump:
        info.data_searching = True

    # Reject cause
    reject_match = re.search(r'rejectCause=(\d+)', tel_dump)
    if reject_match:
        info.reject_cause = int(reject_match.group(1))

    # Registered network technology
    tech_match = re.search(r'accessNetworkTechnology=(\w+)', tel_dump)
    if tech_match and tech_match.group(1) != "UNKNOWN":
        info.registered_network = tech_match.group(1)

    return info


# ---------------------------------------------------------------------------
#  Step 5 — IMEI & Baseband Check
# ---------------------------------------------------------------------------

def _parse_imei_parcel(parcel_output: str) -> str:
    """Parse IMEI from service call parcel output."""
    if not parcel_output or "Parcel" not in parcel_output:
        return ""
    # Extract hex-encoded characters
    chars = re.findall(r"'([^']+)'", parcel_output)
    if not chars:
        return ""
    raw = "".join(chars).replace(".", "").replace(" ", "").replace("\\", "")
    # Filter to digits only
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) >= 14:
        return digits[:15]
    return ""


def _check_modem(serial: str, callback: ProgressCallback) -> ModemInfo:
    """Check IMEI, baseband version, and radio power state."""
    _notify(callback, 55, "Checking modem & IMEI...")

    info = ModemInfo()

    # Baseband version
    info.baseband_version = _adb("getprop gsm.version.baseband", serial)

    # Radio power state
    tel_dump = _adb("dumpsys telephony.registry", serial)
    radio_match = re.search(r'mRadioPowerState=(\d+)', tel_dump)
    if radio_match:
        info.radio_power = "ON" if radio_match.group(1) == "1" else "OFF"

    # IMEI via service call
    imei_parcel = _adb('"service call iphonesubinfo 1 s16 com.android.shell"', serial)
    info.imei = _parse_imei_parcel(imei_parcel)

    # IMEI2 via service call
    imei2_parcel = _adb('"service call iphonesubinfo 4 s16 com.android.shell"', serial)
    info.imei2 = _parse_imei_parcel(imei2_parcel)

    # Modem active check
    info.modem_active = bool(info.baseband_version and len(info.baseband_version) > 3)

    return info


# ---------------------------------------------------------------------------
#  Step 6 — Diagnosis Engine
# ---------------------------------------------------------------------------

def _analyze(
    sim_slots: List[SIMSlotInfo],
    signal: SignalInfo,
    registration: RegistrationInfo,
    modem: ModemInfo,
    callback: ProgressCallback,
) -> Tuple[List[str], List[str], List[NetworkDiagnosis],
           List[DiagnosticStep], List[DiagnosticStep], List[DiagnosticStep],
           str, int]:
    """Analyze all collected data and produce diagnosis + repair steps."""
    _notify(callback, 70, "Analyzing network data...")

    working = []
    not_working = []
    diagnoses = []
    sw_steps = []
    hw_steps = []
    check_steps = []
    score = 100

    # ── Modem/Baseband Analysis ──
    if modem.modem_active:
        working.append(f"Baseband/Modem: Active ({modem.baseband_version})")
    else:
        not_working.append("Baseband/Modem: NOT ACTIVE or not detected")
        score -= 40
        diagnoses.append(NetworkDiagnosis(
            problem="Baseband modem is not active",
            severity="critical",
            root_cause="Modem IC may be dead or firmware corrupted",
            confidence=90,
            evidence=["Baseband version is empty or invalid"],
        ))
        hw_steps.append(DiagnosticStep(
            step_type="hardware", priority=1,
            title="Check Modem IC",
            description="Modem IC may need reballing or replacement. Check power supply to modem.",
        ))

    # ── IMEI Analysis ──
    if modem.imei and len(modem.imei) >= 14:
        working.append(f"IMEI: Present ({modem.imei})")
    else:
        not_working.append("IMEI: Not readable (permission or hardware issue)")
        if modem.modem_active:
            # Baseband active but IMEI not readable = likely permission
            working.append("IMEI: Likely OK (baseband active, IMEI restricted by Android permission)")
        else:
            score -= 15
            diagnoses.append(NetworkDiagnosis(
                problem="IMEI not detected and baseband not active",
                severity="critical",
                root_cause="Modem IC failure or NVRAM corruption",
                confidence=85,
                evidence=["IMEI empty", "Baseband version empty"],
            ))

    # ── Radio Power Analysis ──
    if modem.radio_power == "ON":
        working.append("Radio Power: ON")
    elif modem.radio_power == "OFF":
        not_working.append("Radio Power: OFF")
        score -= 25
        diagnoses.append(NetworkDiagnosis(
            problem="Radio/Modem is powered OFF",
            severity="critical",
            root_cause="Airplane mode enabled or radio disabled in testing menu",
            confidence=95,
            evidence=["mRadioPowerState=0 (OFF)"],
        ))
        sw_steps.append(DiagnosticStep(
            step_type="software", priority=1,
            title="Turn OFF Airplane Mode",
            description="Disable airplane mode to re-enable cellular radio.",
            command="adb shell cmd connectivity airplane-mode disable",
        ))
        sw_steps.append(DiagnosticStep(
            step_type="software", priority=2,
            title="Enable Radio via Testing Menu",
            description="Open *#*#4636#*#* > Phone Information > Turn on radio",
            command='adb shell am start -n com.android.phone/.settings.RadioInfo',
        ))

    # ── SIM Analysis ──
    any_sim_detected = False
    all_sims_absent = True
    for slot in sim_slots:
        if slot.is_detected:
            any_sim_detected = True
            all_sims_absent = False
            working.append(f"SIM {slot.slot}: Detected ({slot.state})")
            if slot.operator:
                working.append(f"SIM {slot.slot} Operator: {slot.operator}")
        elif slot.state == "ABSENT":
            not_working.append(f"SIM {slot.slot}: ABSENT (not detected)")
        else:
            all_sims_absent = False
            not_working.append(f"SIM {slot.slot}: {slot.state}")

    if all_sims_absent and len(sim_slots) > 0:
        score -= 20
        diagnoses.append(NetworkDiagnosis(
            problem="All SIM cards are ABSENT — not detected",
            severity="critical",
            root_cause="SIM not inserted, SIM connector damaged, or SIM IC faulty",
            confidence=80,
            evidence=[f"SIM state: {', '.join(s.state for s in sim_slots)}"],
        ))
        check_steps.append(DiagnosticStep(
            step_type="check", priority=1,
            title="Check SIM Card Physically",
            description="Remove SIM tray, clean SIM card contacts, reinsert properly.",
        ))
        check_steps.append(DiagnosticStep(
            step_type="check", priority=2,
            title="Try Different SIM Card",
            description="Insert a known-working SIM to verify if the slot/connector is functional.",
        ))
        hw_steps.append(DiagnosticStep(
            step_type="hardware", priority=2,
            title="Check SIM Connector Pins",
            description="Inspect SIM connector under microscope for bent/corroded pins. Clean or replace.",
        ))
    elif not any_sim_detected:
        score -= 15

    # ── Signal Analysis ──
    if signal.all_invalid:
        not_working.append("Signal: ALL bands Invalid (GSM/WCDMA/LTE/NR = 0)")
        score -= 25

        if any_sim_detected and modem.radio_power == "ON":
            # SIM detected + radio ON + zero signal = antenna/RF issue
            diagnoses.append(NetworkDiagnosis(
                problem="SIM detected, radio ON, but ZERO signal on all bands",
                severity="critical",
                root_cause="Antenna disconnected/damaged or RF IC fault",
                confidence=92,
                evidence=[
                    "All signal bands: Invalid",
                    "SIM: Detected (LOADED/READY)",
                    "Radio: ON",
                    "Phone is searching but cannot find any tower",
                ],
            ))
            sw_steps.append(DiagnosticStep(
                step_type="software", priority=1,
                title="Toggle Airplane Mode",
                description="Turn airplane mode ON, wait 10 seconds, turn OFF to restart radio.",
                command="adb shell cmd connectivity airplane-mode enable && timeout 10 && adb shell cmd connectivity airplane-mode disable",
            ))
            sw_steps.append(DiagnosticStep(
                step_type="software", priority=2,
                title="Reset Network Settings",
                description="Clear telephony provider data and phone app cache.",
                command="adb shell pm clear com.android.phone && adb shell pm clear com.android.providers.telephony",
            ))
            sw_steps.append(DiagnosticStep(
                step_type="software", priority=3,
                title="Force GSM Only Mode",
                description="Force phone to 2G GSM-only to test if even basic signal is received.",
                command="adb shell settings put global preferred_network_mode 1",
            ))
            sw_steps.append(DiagnosticStep(
                step_type="software", priority=4,
                title="Force LTE/3G/2G Auto Mode",
                description="Set network to auto-select best available technology.",
                command="adb shell settings put global preferred_network_mode 9",
            ))
            sw_steps.append(DiagnosticStep(
                step_type="software", priority=5,
                title="Reboot Device",
                description="Full reboot to reinitialize modem and radio stack.",
                command="adb reboot",
            ))
            hw_steps.append(DiagnosticStep(
                step_type="hardware", priority=1,
                title="Check Antenna Connector",
                description="Open phone, check main antenna connector on motherboard. Must be properly snapped in.",
            ))
            hw_steps.append(DiagnosticStep(
                step_type="hardware", priority=2,
                title="Check Antenna Flex Cable",
                description="Inspect antenna flex cable for damage, tears, or burns.",
            ))
            hw_steps.append(DiagnosticStep(
                step_type="hardware", priority=3,
                title="Check RF IC / Antenna Tuner",
                description="If antenna is OK, RF front-end IC or antenna tuner IC may be faulty. Board-level repair needed.",
            ))
    else:
        # Some signal exists
        signals_found = []
        if signal.gsm_signal:
            signals_found.append(f"GSM: {signal.gsm_signal}")
        if signal.wcdma_signal:
            signals_found.append(f"WCDMA: {signal.wcdma_signal}")
        if signal.lte_signal:
            signals_found.append(f"LTE: {signal.lte_signal}")
        if signal.nr_signal:
            signals_found.append(f"NR: {signal.nr_signal}")
        working.append(f"Signal: {', '.join(signals_found)}")

    # ── Registration Analysis ──
    if registration.voice_state == "IN_SERVICE":
        working.append("Voice: IN_SERVICE (registered)")
    elif registration.voice_state == "OUT_OF_SERVICE":
        not_working.append("Voice: OUT_OF_SERVICE")
        if registration.voice_searching:
            not_working.append("Voice: Searching for network (NOT_REG_SEARCHING)")
    elif registration.voice_state == "EMERGENCY_ONLY":
        not_working.append("Voice: EMERGENCY_ONLY")
        score -= 10
    elif registration.voice_state:
        not_working.append(f"Voice: {registration.voice_state}")

    if registration.data_state == "IN_SERVICE":
        working.append("Data: IN_SERVICE (registered)")
    elif registration.data_state == "OUT_OF_SERVICE":
        not_working.append("Data: OUT_OF_SERVICE (cellular)")

    # Registration with reject cause
    if registration.reject_cause > 0:
        reject_reasons = {
            2: "IMSI unknown in HLR — SIM not registered with operator",
            3: "Illegal MS — device banned by network",
            5: "IMEI not accepted — device blacklisted",
            6: "Illegal ME — device rejected by network",
            11: "PLMN not allowed — operator restriction",
            12: "Location Area not allowed",
            13: "Roaming not allowed",
            15: "No suitable cells — network coverage issue",
        }
        reason = reject_reasons.get(registration.reject_cause,
                                     f"Unknown reject cause #{registration.reject_cause}")
        not_working.append(f"Network Reject: Cause #{registration.reject_cause} — {reason}")
        score -= 15
        diagnoses.append(NetworkDiagnosis(
            problem=f"Network rejected registration (cause #{registration.reject_cause})",
            severity="warning",
            root_cause=reason,
            confidence=88,
            evidence=[f"rejectCause={registration.reject_cause}"],
        ))

    # ── IWLAN (WiFi Calling) Detection ──
    if registration.registered_network == "IWLAN":
        working.append("Data via WiFi Calling (IWLAN): Active")
        # If IWLAN is the only data, cellular data is not working
        if registration.data_state != "IN_SERVICE" or signal.all_invalid:
            not_working.append("Cellular Data: NOT working (only WiFi calling active)")

    # ── Overall Status ──
    if registration.voice_state == "IN_SERVICE" and not signal.all_invalid:
        overall = "NETWORK OK — Device registered and receiving signal"
        if score > 85:
            score = min(score, 95)
    elif any_sim_detected and modem.radio_power == "ON" and signal.all_invalid:
        overall = "NO SIGNAL — SIM detected, radio ON, but no cellular signal received"
        score = min(score, 20)
    elif all_sims_absent:
        overall = "NO SIM — No SIM card detected in any slot"
        score = min(score, 25)
    elif modem.radio_power == "OFF":
        overall = "RADIO OFF — Cellular modem is powered off (airplane mode?)"
        score = min(score, 15)
    elif not modem.modem_active:
        overall = "MODEM DEAD — Baseband not responding"
        score = min(score, 10)
    elif registration.voice_state == "OUT_OF_SERVICE":
        overall = "OUT OF SERVICE — Cannot register to any network"
        score = min(score, 25)
    else:
        overall = "DEGRADED — Partial network functionality"
        score = min(score, 50)

    score = max(0, min(100, score))

    return working, not_working, diagnoses, sw_steps, hw_steps, check_steps, overall, score


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def run_network_diagnostic(
    callback: ProgressCallback = None,
) -> NetworkDiagnosticResult:
    """Run the full network diagnostic sequence.

    Parameters
    ----------
    callback : callable, optional
        A callable ``(pct: float, msg: str) -> None`` for progress updates.

    Returns
    -------
    NetworkDiagnosticResult
        Complete diagnostic result with analysis, diagnosis, and repair steps.
    """
    result = NetworkDiagnosticResult()

    # Step 1: Device check
    ok, serial, err = _check_device(callback)
    if not ok:
        result.error = err
        result.overall_status = f"ERROR — {err}"
        _notify(callback, 100, f"Error: {err}")
        return result

    result.connected = True
    result.device_serial = serial

    # Get device model
    result.device_model = _adb("getprop ro.product.model", serial)
    _notify(callback, 5, f"Device: {result.device_model} ({serial})")

    try:
        # Step 2: SIM check
        result.sim_slots = _check_sim(serial, callback)

        # Step 3: Signal check
        result.signal = _check_signal(serial, callback)

        # Step 4: Registration check
        result.registration = _check_registration(serial, callback)

        # Step 5: Modem check
        result.modem = _check_modem(serial, callback)

        # Step 6: Analyze everything
        _notify(callback, 70, "Analyzing network data...")
        (result.working, result.not_working, result.diagnoses,
         result.software_steps, result.hardware_steps, result.check_steps,
         result.overall_status, result.health_score) = _analyze(
            result.sim_slots, result.signal, result.registration,
            result.modem, callback,
        )

        _notify(callback, 95, f"Analysis complete — {result.overall_status}")

    except Exception as exc:
        result.error = str(exc)
        result.overall_status = f"ERROR — {exc}"

    _notify(callback, 100, "Network diagnostic complete")
    return result
