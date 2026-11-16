"""
Cross-Fault Correlation Engine — Chains multiple fault signals into root causes.

Instead of reporting individual symptoms, this engine correlates multiple faults
to find the REAL root cause. For example:
  "Dead phone + no VBAT + PMIC not responding" → Battery connector or PMIC failure

Architecture:
  1. CorrelationRule — defines a pattern of faults that point to a root cause
  2. CorrelationEngine — takes a list of Fault objects and finds root causes
  3. RootCause — the output: what's actually broken and how to fix it
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import re


@dataclass
class RootCause:
    """A correlated root cause derived from multiple fault signals."""
    root_cause_id: str = ""
    name: str = ""
    confidence: int = 0                     # 0-100, boosted by how many signals matched
    severity: str = "critical"              # critical, warning, info
    component: str = ""                     # The actual failing component
    description: str = ""                   # Human-readable explanation
    contributing_faults: List[str] = field(default_factory=list)   # Which faults led here
    signal_count: int = 0                   # How many of the expected signals matched
    total_signals: int = 0                  # How many signals the rule expects
    repair_path: List[str] = field(default_factory=list)
    parts_needed: List[str] = field(default_factory=list)
    estimated_difficulty: str = "expert"
    estimated_time: str = ""                # e.g. "30-60 min"
    related_ics: List[str] = field(default_factory=list)
    voltage_checks: List[Dict] = field(default_factory=list)  # [{rail, expected, pin}]


@dataclass
class CorrelationRule:
    """Defines a pattern: if these faults co-occur, the root cause is X."""
    rule_id: str
    name: str
    severity: str
    root_component: str
    description: str
    # Each signal is a dict: {component_pattern, problem_pattern, severity_filter}
    # component_pattern and problem_pattern are regex matched against Fault fields
    required_signals: List[Dict] = field(default_factory=list)    # ALL must match
    optional_signals: List[Dict] = field(default_factory=list)    # Boost confidence
    min_required: int = 2       # Minimum required signals that must match
    base_confidence: int = 70
    confidence_per_signal: int = 10   # Bonus per additional signal matched
    repair_path: List[str] = field(default_factory=list)
    parts_needed: List[str] = field(default_factory=list)
    difficulty: str = "expert"
    estimated_time: str = ""
    related_ics: List[str] = field(default_factory=list)
    voltage_checks: List[Dict] = field(default_factory=list)
    chipset_filter: str = "any"  # "any", "mediatek", "qualcomm", etc.


# ─── CORRELATION RULES DATABASE ────────────────────────────────────────────

CORRELATION_RULES: List[CorrelationRule] = [

    # ── POWER / PMIC CORRELATIONS ──────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-001",
        name="PMIC Total Failure — No Power Output",
        severity="critical",
        root_component="PMIC (Power Management IC)",
        description="Multiple power-dependent subsystems are failing simultaneously. "
                    "This pattern strongly indicates the PMIC is not producing output voltages, "
                    "or a catastrophic short is pulling all rails down.",
        required_signals=[
            {"component_pattern": r"CPU|SoC", "problem_pattern": r"not responding|dead|no boot"},
            {"component_pattern": r"RAM|DRAM", "problem_pattern": r"fail|not accessible|dead"},
        ],
        optional_signals=[
            {"component_pattern": r"Storage|eMMC|UFS", "problem_pattern": r"not loading|fail|fault"},
            {"component_pattern": r"Display", "problem_pattern": r"no display|blank|dead"},
            {"component_pattern": r"Battery", "problem_pattern": r"dead|not charg"},
            {"component_pattern": r"WiFi|Bluetooth|Combo", "problem_pattern": r"not found|fail|fault"},
        ],
        min_required=2,
        base_confidence=75,
        confidence_per_signal=8,
        repair_path=[
            "1. Check battery voltage at connector (should be 3.7-4.2V)",
            "2. Check PMIC input voltage (VBAT pin)",
            "3. Measure all PMIC output rails with multimeter:",
            "   - VDD_CORE: 0.8-1.0V",
            "   - VDD_DRAM: 1.1V (LPDDR4X) or 0.5V (LPDDR5)",
            "   - VDD_IO: 1.8V",
            "   - VDD_33: 3.3V",
            "4. If no output: check PMIC power-on sequence (PWRKEY, PMIC_EN)",
            "5. If PMIC gets input but no output: PMIC is dead — replace",
            "6. If outputs are low: check for short circuits on each rail",
        ],
        parts_needed=["PMIC IC (model-specific)", "BGA reball stencil"],
        difficulty="expert",
        estimated_time="60-120 min",
        related_ics=["MT6357", "MT6358", "MT6359", "PM6125", "PM6150", "PM8150", "S2MPU09"],
        voltage_checks=[
            {"rail": "VBAT", "expected": "3.7-4.2V", "pin": "PMIC VBAT input"},
            {"rail": "VDD_CORE", "expected": "0.8-1.0V", "pin": "CPU core supply"},
            {"rail": "VDD_DRAM", "expected": "1.1V", "pin": "RAM supply"},
            {"rail": "VDD_IO", "expected": "1.8V", "pin": "I/O supply"},
        ],
    ),

    CorrelationRule(
        rule_id="COR-002",
        name="Battery / Power Connector Failure",
        severity="critical",
        root_component="Battery Connector / Battery",
        description="Phone is completely dead with no boot activity. PMIC isn't receiving "
                    "input power, pointing to battery or battery connector issue.",
        required_signals=[
            {"component_pattern": r"CPU|SoC", "problem_pattern": r"not responding|dead|no boot"},
        ],
        optional_signals=[
            {"component_pattern": r"Battery", "problem_pattern": r"dead|not detected|voltage|health"},
            {"component_pattern": r"PMIC|Power", "problem_pattern": r"not respond|no output|fail"},
            {"component_pattern": r"Charging", "problem_pattern": r"not charg|fail"},
            {"component_pattern": r"RAM|DRAM", "problem_pattern": r"fail|not accessible"},
        ],
        min_required=1,
        base_confidence=60,
        confidence_per_signal=12,
        repair_path=[
            "1. Check battery voltage with multimeter (should be 3.7-4.2V)",
            "2. If battery < 3.0V: battery is dead, replace it",
            "3. If battery OK: check battery connector on motherboard",
            "4. Clean battery connector pins with IPA",
            "5. Check for broken traces from connector to PMIC",
            "6. Try known-good battery",
        ],
        parts_needed=["Battery (model-specific)", "Battery connector (FPC)"],
        difficulty="easy",
        estimated_time="15-30 min",
        voltage_checks=[
            {"rail": "Battery", "expected": "3.7-4.2V", "pin": "Battery connector B+/B-"},
        ],
    ),

    CorrelationRule(
        rule_id="COR-003",
        name="Charging IC Failure Chain",
        severity="critical",
        root_component="Charging IC",
        description="Battery not charging combined with thermal issues or USB detection failure. "
                    "The charging IC is likely shorted or dead, potentially causing thermal damage.",
        required_signals=[
            {"component_pattern": r"Battery|Charging", "problem_pattern": r"not charg|health|dead"},
        ],
        optional_signals=[
            {"component_pattern": r"Battery|Motherboard|Thermal", "problem_pattern": r"temperature|hot|thermal|heat"},
            {"component_pattern": r"USB", "problem_pattern": r"not detect|fail|not recogn"},
            {"component_pattern": r"PMIC|Power", "problem_pattern": r"fail|fault"},
        ],
        min_required=1,
        base_confidence=55,
        confidence_per_signal=15,
        repair_path=[
            "1. Feel the board for hot spots (or use thermal camera)",
            "2. Check charging IC temperature",
            "3. Measure USB VBUS voltage (should be 5V when plugged in)",
            "4. Check charging IC input/output voltages",
            "5. If charging IC is hot: likely shorted — replace it",
            "6. Check for shorted capacitors near charging IC",
        ],
        parts_needed=["Charging IC (BQ25890/BQ25601/MT6370/SM5714)", "USB connector"],
        difficulty="hard",
        estimated_time="45-90 min",
        related_ics=["BQ25890", "BQ25601", "MT6370", "SM5714", "SGM41516"],
    ),

    # ── STORAGE CORRELATIONS ───────────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-004",
        name="Storage Subsystem Total Failure",
        severity="critical",
        root_component="eMMC/UFS Storage IC",
        description="Storage is not initializing and phone is stuck at bootloader. "
                    "Combined with preloader not loading, this strongly indicates dead or "
                    "corrupted storage IC.",
        required_signals=[
            {"component_pattern": r"Storage|eMMC|UFS", "problem_pattern": r"not loading|fail|fault|stuck"},
        ],
        optional_signals=[
            {"component_pattern": r"System|Software", "problem_pattern": r"crash|abnormal|corrupt"},
            {"component_pattern": r"CPU|SoC", "problem_pattern": r"BROM|boot.*stop|stuck"},
            {"component_pattern": r"Storage", "problem_pattern": r"full|space|capacity"},
        ],
        min_required=1,
        base_confidence=65,
        confidence_per_signal=12,
        repair_path=[
            "1. Try flashing firmware via SP Flash Tool / QFIL (BROM/EDL mode)",
            "2. If flash succeeds: storage was corrupted, not dead",
            "3. If flash fails: check eMMC/UFS power supply voltages",
            "   - VCCQ: 1.8V (eMMC) or 1.2V (UFS)",
            "   - VCC: 2.95V (eMMC) or 2.7V (UFS)",
            "4. Check eMMC/UFS data lines with oscilloscope",
            "5. If no communication: reball eMMC/UFS IC",
            "6. If still dead: replace eMMC/UFS IC (requires NAND programmer)",
        ],
        parts_needed=["eMMC/UFS IC (matching capacity)", "BGA stencil", "NAND programmer"],
        difficulty="expert",
        estimated_time="90-180 min",
        voltage_checks=[
            {"rail": "VCCQ", "expected": "1.8V (eMMC) / 1.2V (UFS)", "pin": "Storage power"},
            {"rail": "VCC", "expected": "2.95V (eMMC) / 2.7V (UFS)", "pin": "Storage main supply"},
        ],
    ),

    # ── CONNECTIVITY CORRELATIONS ──────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-005",
        name="Combo IC Failure (WiFi + Bluetooth)",
        severity="warning",
        root_component="WiFi/BT Combo IC",
        description="Both WiFi and Bluetooth are failing together. Since they share the same "
                    "combo IC chip, this is almost certainly a combo IC failure, not two "
                    "separate issues.",
        required_signals=[
            {"component_pattern": r"WiFi", "problem_pattern": r"not found|fail|fault|not work|MAC"},
            {"component_pattern": r"Bluetooth|BT|Combo", "problem_pattern": r"not detect|fail|fault|not work|MAC"},
        ],
        optional_signals=[
            {"component_pattern": r"GPS|NFC", "problem_pattern": r"not found|fail"},
        ],
        min_required=2,
        base_confidence=90,
        confidence_per_signal=5,
        repair_path=[
            "1. Check combo IC power supply voltage (typically 1.8V or 3.3V)",
            "2. Check WiFi/BT antenna connectors (both)",
            "3. Try toggling airplane mode on/off",
            "4. Flash WiFi/BT calibration data (NVRAM)",
            "5. If software fix fails: reball combo IC",
            "6. Replace combo IC if reball fails",
        ],
        parts_needed=["WiFi/BT Combo IC (MT6631/WCN3988/BCM4375)", "Antenna flex cable"],
        difficulty="hard",
        estimated_time="45-90 min",
        related_ics=["MT6631", "WCN3988", "WCN3990", "WCN6856", "BCM4375", "BCM4389"],
    ),

    CorrelationRule(
        rule_id="COR-006",
        name="Modem / Baseband Failure Chain",
        severity="critical",
        root_component="Baseband / Modem IC",
        description="IMEI missing AND SIM not detected AND no network. Multiple modem-related "
                    "subsystems are down, pointing to dead modem IC or corrupted modem firmware.",
        required_signals=[
            {"component_pattern": r"IMEI|Baseband|Modem", "problem_pattern": r"not detect|empty|missing|fault"},
        ],
        optional_signals=[
            {"component_pattern": r"SIM", "problem_pattern": r"not detect|absent|not ready"},
            {"component_pattern": r"Network|Signal", "problem_pattern": r"no signal|no service|fail"},
            {"component_pattern": r"IMEI", "problem_pattern": r"null|0000|invalid"},
        ],
        min_required=1,
        base_confidence=60,
        confidence_per_signal=15,
        repair_path=[
            "1. Check baseband version (Settings > About Phone)",
            "2. If baseband is empty/null: modem IC is not initializing",
            "3. Try flashing modem firmware separately",
            "4. Write IMEI via engineering mode or SP Flash Tool",
            "5. If firmware flash fails: check modem IC power supply",
            "6. Reball/replace modem IC (on MediaTek: integrated in SoC)",
        ],
        parts_needed=["Modem firmware file", "RF IC (if separate from SoC)"],
        difficulty="hard",
        estimated_time="30-60 min",
    ),

    # ── DISPLAY CORRELATIONS ───────────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-007",
        name="Display Subsystem Failure",
        severity="critical",
        root_component="Display / Display IC",
        description="Display not working with touch also failing. Since modern phones use "
                    "integrated display+touch panels, both failing together means the display "
                    "assembly or its flex cable is the issue, not the motherboard.",
        required_signals=[
            {"component_pattern": r"Display|LCD|OLED|Screen", "problem_pattern": r"no display|blank|dead|not work|fail"},
        ],
        optional_signals=[
            {"component_pattern": r"Touch|Touchscreen", "problem_pattern": r"not respond|fail|not work|dead"},
            {"component_pattern": r"Backlight", "problem_pattern": r"no backlight|dark|dim"},
        ],
        min_required=1,
        base_confidence=60,
        confidence_per_signal=15,
        repair_path=[
            "1. Check display flex cable connection on motherboard",
            "2. Clean display connector with IPA",
            "3. Try a known-good display assembly",
            "4. If known-good display also fails: check display power rails on board:",
            "   - VDDI (display I/O): 1.8V",
            "   - VCI (display analog): 3.0-3.3V",
            "   - Backlight boost: 15-25V (for LCD)",
            "5. Check display driver IC on motherboard (if separate)",
            "6. Check for damaged flex cable connector pins",
        ],
        parts_needed=["Display assembly (LCD+Touch+Frame)", "Display flex cable"],
        difficulty="easy",
        estimated_time="15-30 min",
    ),

    # ── SENSOR CORRELATIONS ────────────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-008",
        name="Sensor Hub / Flex Cable Failure",
        severity="warning",
        root_component="Sensor Hub IC / Sensor Flex Cable",
        description="Multiple sensors failing together. Accelerometer, gyroscope, proximity, "
                    "and light sensor are usually on the same flex cable or controlled by the "
                    "same sensor hub IC. All failing = flex cable or hub issue.",
        required_signals=[
            {"component_pattern": r"Sensor", "problem_pattern": r"no sensor|not detect|fail"},
        ],
        optional_signals=[
            {"component_pattern": r"Fingerprint", "problem_pattern": r"not detect|fail|not avail"},
            {"component_pattern": r"Proximity|Light|Accel|Gyro", "problem_pattern": r"fail|not found"},
        ],
        min_required=1,
        base_confidence=55,
        confidence_per_signal=15,
        repair_path=[
            "1. Check sensor flex cable connection",
            "2. Reseat sensor flex on motherboard",
            "3. Check sensor hub IC power supply (1.8V typical)",
            "4. Check I2C bus lines (SDA/SCL) for shorts",
            "5. Replace sensor flex cable if damaged",
            "6. Replace sensor hub IC if flex cable is OK",
        ],
        parts_needed=["Sensor flex cable", "Sensor hub IC"],
        difficulty="medium",
        estimated_time="20-45 min",
    ),

    # ── CAMERA CORRELATIONS ────────────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-009",
        name="Camera Subsystem Failure",
        severity="warning",
        root_component="Camera Module / Camera IC",
        description="Both front and rear cameras failing together. If both cameras are dead "
                    "simultaneously, the issue is likely the camera power supply IC on the "
                    "motherboard, not the camera modules themselves.",
        required_signals=[
            {"component_pattern": r"Camera", "problem_pattern": r"not detect|not access|fail|dead|no camera"},
        ],
        optional_signals=[
            {"component_pattern": r"Camera.*front|Front.*camera", "problem_pattern": r"fail|not detect"},
            {"component_pattern": r"Camera.*rear|Rear.*camera", "problem_pattern": r"fail|not detect"},
        ],
        min_required=1,
        base_confidence=55,
        confidence_per_signal=15,
        repair_path=[
            "1. Reseat camera flex cables (both front and rear)",
            "2. Clean camera connectors with IPA",
            "3. Try known-good camera modules one at a time",
            "4. If both known-good cameras also fail: motherboard issue",
            "5. Check camera power supply IC output voltages:",
            "   - VCAM_IO: 1.8V",
            "   - VCAM_A: 2.8V",
            "   - VCAM_D: 1.0-1.2V",
            "6. Check/replace camera power supply IC",
        ],
        parts_needed=["Camera module (front)", "Camera module (rear)", "Camera power IC"],
        difficulty="medium",
        estimated_time="20-45 min",
    ),

    # ── THERMAL / SHORT CIRCUIT CORRELATIONS ───────────────────────────────

    CorrelationRule(
        rule_id="COR-010",
        name="Short Circuit — Thermal Overload",
        severity="critical",
        root_component="Motherboard (Short Circuit)",
        description="Device overheating combined with multiple component failures. A short "
                    "circuit on the motherboard is causing excessive current draw and heat, "
                    "which can cascade into multiple subsystem failures.",
        required_signals=[
            {"component_pattern": r"Battery|Motherboard|Thermal", "problem_pattern": r"temperature|hot|thermal|heat|overtemp"},
        ],
        optional_signals=[
            {"component_pattern": r"Battery", "problem_pattern": r"not charg|drain|health|dead"},
            {"component_pattern": r"CPU|SoC", "problem_pattern": r"throttl|slow|overheat"},
            {"component_pattern": r"Display", "problem_pattern": r"fail|flicker|artifact"},
            {"component_pattern": r"Charging", "problem_pattern": r"slow|not charg|fail"},
        ],
        min_required=1,
        base_confidence=50,
        confidence_per_signal=15,
        repair_path=[
            "1. DO NOT keep phone powered on — risk of further damage",
            "2. Use thermal camera to locate hot spot on board",
            "3. Measure current draw at boot (normal: 200-500mA, short: >1A)",
            "4. If hot spot found: check capacitors near hot area",
            "5. Remove shorted capacitor and re-test",
            "6. Use rosin/flux method to visually find short",
            "7. If short is under IC: reball/replace the IC",
        ],
        parts_needed=["Replacement capacitors (0201/0402)", "Thermal camera/paste"],
        difficulty="expert",
        estimated_time="60-180 min",
    ),

    # ── RAM + CPU CORRELATIONS ─────────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-011",
        name="CPU/RAM BGA Failure (PoP Package)",
        severity="critical",
        root_component="CPU+RAM Package (PoP)",
        description="CPU partially responding but RAM failing. On most phones, RAM sits on top "
                    "of the CPU in a Package-on-Package (PoP) design. RAM failure with CPU "
                    "issues suggests cracked BGA solder joints from drop damage.",
        required_signals=[
            {"component_pattern": r"RAM|DRAM", "problem_pattern": r"fail|not accessible|init.*fail"},
        ],
        optional_signals=[
            {"component_pattern": r"CPU|SoC", "problem_pattern": r"crash|unstable|random|reboot"},
            {"component_pattern": r"System|Software", "problem_pattern": r"crash|abnormal|random.*reboot"},
            {"component_pattern": r"Storage", "problem_pattern": r"fail|corrupt|error"},
        ],
        min_required=1,
        base_confidence=60,
        confidence_per_signal=12,
        repair_path=[
            "1. Check for signs of drop damage on the phone",
            "2. Check RAM voltage rails (VDDQ, VDD2)",
            "3. If voltages OK but RAM still fails: BGA solder joint issue",
            "4. Reball CPU+RAM PoP package (high-skill operation)",
            "5. If reball fails: replace CPU+RAM assembly",
            "6. ⚠️ This is one of the hardest repairs — often not cost-effective",
        ],
        parts_needed=["CPU+RAM PoP IC", "BGA reball stencil", "Reballing station"],
        difficulty="expert",
        estimated_time="120-240 min",
    ),

    # ── AUDIO CORRELATIONS ─────────────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-012",
        name="Audio Codec IC Failure",
        severity="warning",
        root_component="Audio Codec IC",
        description="Multiple audio functions failing (speaker, mic, earpiece). The audio "
                    "codec IC processes all audio I/O. If multiple audio paths fail, "
                    "the codec IC is the likely root cause.",
        required_signals=[
            {"component_pattern": r"Audio|Speaker|Mic|Earpiece", "problem_pattern": r"not work|fail|no sound|no audio|mute"},
        ],
        optional_signals=[
            {"component_pattern": r"Audio|Speaker", "problem_pattern": r"distort|crackling|noise"},
            {"component_pattern": r"Mic|Microphone", "problem_pattern": r"not work|fail|no input"},
            {"component_pattern": r"Headphone|Jack|Earphone", "problem_pattern": r"not detect|fail"},
        ],
        min_required=1,
        base_confidence=55,
        confidence_per_signal=15,
        repair_path=[
            "1. Test speaker, earpiece, and mic separately",
            "2. If only one fails: likely that specific component",
            "3. If multiple fail: audio codec IC is the issue",
            "4. Check audio codec IC power supply (1.8V typical)",
            "5. Check I2S/TDM data lines between SoC and codec",
            "6. Replace audio codec IC if confirmed faulty",
        ],
        parts_needed=["Audio codec IC (AW88266/RT5509/WCD9385/CS35L41)"],
        difficulty="hard",
        estimated_time="45-90 min",
        related_ics=["AW88266", "RT5509", "WCD9385", "CS35L41", "AK4376"],
    ),

    # ── SOFTWARE + HARDWARE MIX ────────────────────────────────────────────

    CorrelationRule(
        rule_id="COR-013",
        name="Boot Loop — Software vs Hardware",
        severity="warning",
        root_component="System (Software or Hardware)",
        description="Phone is boot looping with crash evidence. This could be software "
                    "(corrupted firmware) or hardware (failing storage, bad RAM). "
                    "The correlation helps narrow down which.",
        required_signals=[
            {"component_pattern": r"System|Software", "problem_pattern": r"crash|abnormal|boot.*loop|reboot"},
        ],
        optional_signals=[
            {"component_pattern": r"Storage|eMMC|UFS", "problem_pattern": r"fail|corrupt|error"},
            {"component_pattern": r"RAM|DRAM", "problem_pattern": r"fail|error|not accessible"},
            {"component_pattern": r"Battery", "problem_pattern": r"drain|low|voltage"},
            {"component_pattern": r"Thermal", "problem_pattern": r"hot|overheat|thermal"},
        ],
        min_required=1,
        base_confidence=45,
        confidence_per_signal=15,
        repair_path=[
            "1. Check if phone enters recovery/fastboot mode",
            "2. If recovery works: likely software — try factory reset or reflash",
            "3. If recovery also crashes: likely hardware",
            "4. Check storage health (eMMC/UFS SMART data if accessible)",
            "5. Check for signs of overheating (hot spots on board)",
            "6. If hardware-related: see specific component fault",
        ],
        parts_needed=[],
        difficulty="medium",
        estimated_time="15-60 min",
    ),

    CorrelationRule(
        rule_id="COR-014",
        name="USB / Charging Port Failure Chain",
        severity="warning",
        root_component="USB Port / Charging Sub-board",
        description="USB not detected AND charging not working. Since both go through the "
                    "same USB-C/micro-USB port and sub-board, this is likely a port or "
                    "sub-board issue rather than a motherboard problem.",
        required_signals=[
            {"component_pattern": r"USB|Charging|Battery", "problem_pattern": r"not charg|not detect|not recogn|fail"},
        ],
        optional_signals=[
            {"component_pattern": r"USB", "problem_pattern": r"fail|not detect"},
            {"component_pattern": r"OTG|Data", "problem_pattern": r"not work|fail"},
        ],
        min_required=1,
        base_confidence=55,
        confidence_per_signal=15,
        repair_path=[
            "1. Inspect USB port for debris, bent pins, or corrosion",
            "2. Clean USB port with IPA and air blower",
            "3. Try a different cable (must support data + charging)",
            "4. Check USB port sub-board flex cable connection",
            "5. Replace USB port sub-board / charging board",
            "6. If new sub-board doesn't fix it: check charging IC on motherboard",
        ],
        parts_needed=["USB sub-board / charging flex", "USB-C port connector"],
        difficulty="easy",
        estimated_time="15-30 min",
    ),

    CorrelationRule(
        rule_id="COR-015",
        name="Water Damage Pattern",
        severity="critical",
        root_component="Motherboard (Water/Liquid Damage)",
        description="Multiple unrelated subsystems failing simultaneously (e.g., WiFi + Camera + "
                    "Sensors + Charging). This pattern of seemingly random multi-system failure "
                    "is characteristic of liquid/water damage causing corrosion across the board.",
        required_signals=[
            {"component_pattern": r"WiFi|Bluetooth|Combo", "problem_pattern": r"fail|not found|not work"},
            {"component_pattern": r"Camera|Sensor|Touch|Display", "problem_pattern": r"fail|not found|not work|not detect"},
        ],
        optional_signals=[
            {"component_pattern": r"Charging|Battery", "problem_pattern": r"fail|not charg|drain"},
            {"component_pattern": r"Speaker|Mic|Audio", "problem_pattern": r"fail|not work|distort"},
            {"component_pattern": r"Fingerprint", "problem_pattern": r"fail|not detect"},
            {"component_pattern": r"SIM|Network", "problem_pattern": r"fail|not detect|no signal"},
        ],
        min_required=2,
        base_confidence=65,
        confidence_per_signal=10,
        repair_path=[
            "1. Open phone and inspect for water damage indicators (LDI strips)",
            "2. Look for corrosion on motherboard (green/white deposits)",
            "3. Ultrasonic clean the motherboard in IPA / cleaning solution",
            "4. Dry thoroughly and re-test each component",
            "5. Replace any components that still fail after cleaning",
            "6. ⚠️ Water damage can cause delayed failures — components may die later",
        ],
        parts_needed=["Ultrasonic cleaner", "IPA (isopropyl alcohol)", "Replacement components as needed"],
        difficulty="hard",
        estimated_time="60-120 min",
    ),
]


class CorrelationEngine:
    """Analyzes multiple faults to find correlated root causes."""

    def __init__(self):
        self.rules = CORRELATION_RULES
        self._compiled = {}
        for rule in self.rules:
            self._compiled[rule.rule_id] = {
                "required": [
                    {
                        "comp": re.compile(s["component_pattern"], re.IGNORECASE),
                        "prob": re.compile(s["problem_pattern"], re.IGNORECASE),
                    }
                    for s in rule.required_signals
                ],
                "optional": [
                    {
                        "comp": re.compile(s.get("component_pattern", ""), re.IGNORECASE),
                        "prob": re.compile(s.get("problem_pattern", ""), re.IGNORECASE),
                    }
                    for s in rule.optional_signals
                ],
            }

    def analyze(self, faults: list, chipset: str = "any") -> List[RootCause]:
        """
        Analyze a list of Fault objects and find correlated root causes.

        Args:
            faults: List of Fault objects from fault_analyzer or rule_engine
            chipset: Optional chipset family filter ("mediatek", "qualcomm", etc.)

        Returns:
            List of RootCause objects sorted by confidence (highest first)
        """
        if not faults:
            return []

        root_causes = []

        for rule in self.rules:
            # Skip rules that don't match the chipset
            if rule.chipset_filter != "any" and chipset != "any":
                if rule.chipset_filter.lower() not in chipset.lower():
                    continue

            compiled = self._compiled[rule.rule_id]
            matched_required = []
            matched_optional = []

            # Check required signals
            for sig in compiled["required"]:
                for fault in faults:
                    comp_text = fault.component if hasattr(fault, 'component') else str(fault)
                    prob_text = fault.problem if hasattr(fault, 'problem') else str(fault)
                    if sig["comp"].search(comp_text) and sig["prob"].search(prob_text):
                        matched_required.append(f"{comp_text}: {prob_text}")
                        break

            # Check optional signals
            for sig in compiled["optional"]:
                for fault in faults:
                    comp_text = fault.component if hasattr(fault, 'component') else str(fault)
                    prob_text = fault.problem if hasattr(fault, 'problem') else str(fault)
                    if sig["comp"].search(comp_text) and sig["prob"].search(prob_text):
                        matched_optional.append(f"{comp_text}: {prob_text}")
                        break

            total_matched = len(matched_required) + len(matched_optional)

            # Must meet minimum required signals
            if len(matched_required) < min(rule.min_required, len(rule.required_signals)):
                continue

            if total_matched < rule.min_required:
                continue

            # Calculate confidence
            confidence = rule.base_confidence + (total_matched * rule.confidence_per_signal)
            confidence = min(confidence, 99)  # Cap at 99%

            root_causes.append(RootCause(
                root_cause_id=rule.rule_id,
                name=rule.name,
                confidence=confidence,
                severity=rule.severity,
                component=rule.root_component,
                description=rule.description,
                contributing_faults=matched_required + matched_optional,
                signal_count=total_matched,
                total_signals=len(rule.required_signals) + len(rule.optional_signals),
                repair_path=rule.repair_path,
                parts_needed=rule.parts_needed,
                estimated_difficulty=rule.difficulty,
                estimated_time=rule.estimated_time,
                related_ics=rule.related_ics,
                voltage_checks=rule.voltage_checks,
            ))

        # Sort by confidence (highest first), then by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        root_causes.sort(key=lambda x: (-x.confidence, severity_order.get(x.severity, 2)))

        return root_causes

    def analyze_from_report(self, fault_report, chipset: str = "any") -> List[RootCause]:
        """Convenience: analyze directly from a FaultReport object."""
        return self.analyze(fault_report.faults, chipset)

    def analyze_from_matched_faults(self, matched_faults: list, chipset: str = "any") -> List[RootCause]:
        """Convenience: analyze from RuleEngine MatchedFault objects."""
        from app.hardware.fault_analyzer import Fault

        # Convert MatchedFault to Fault for uniform processing
        converted = []
        for mf in matched_faults:
            converted.append(Fault(
                severity=mf.rule.severity,
                component=mf.rule.component,
                problem=mf.rule.fault_name,
                evidence=mf.matched_text,
                confidence=int(mf.confidence * 100),
            ))
        return self.analyze(converted, chipset)


def generate_correlation_report(root_causes: List[RootCause]) -> str:
    """Generate a formatted text report of correlation analysis."""
    if not root_causes:
        return "✅ No correlated root causes found. Individual faults may be unrelated."

    lines = [
        "═══════════════════════════════════════════════════════════",
        "       CROSS-FAULT CORRELATION ANALYSIS REPORT",
        "═══════════════════════════════════════════════════════════",
        "",
        f"Root Causes Found: {len(root_causes)}",
        "",
    ]

    for i, rc in enumerate(root_causes, 1):
        severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(rc.severity, "⚪")
        lines.append(f"{'─' * 55}")
        lines.append(f"{severity_icon} ROOT CAUSE #{i}: {rc.name}")
        lines.append(f"{'─' * 55}")
        lines.append(f"  Component:   {rc.component}")
        lines.append(f"  Confidence:  {rc.confidence}%")
        lines.append(f"  Severity:    {rc.severity.upper()}")
        lines.append(f"  Difficulty:  {rc.estimated_difficulty}")
        if rc.estimated_time:
            lines.append(f"  Est. Time:   {rc.estimated_time}")
        lines.append(f"  Signals:     {rc.signal_count}/{rc.total_signals} matched")
        lines.append("")
        lines.append(f"  Description:")
        lines.append(f"    {rc.description}")
        lines.append("")

        if rc.contributing_faults:
            lines.append(f"  Contributing Faults:")
            for fault in rc.contributing_faults:
                lines.append(f"    → {fault}")
            lines.append("")

        if rc.voltage_checks:
            lines.append(f"  Voltage Checks:")
            for vc in rc.voltage_checks:
                lines.append(f"    📏 {vc['rail']}: {vc['expected']} ({vc.get('pin', '')})")
            lines.append("")

        if rc.repair_path:
            lines.append(f"  Repair Steps:")
            for step in rc.repair_path:
                lines.append(f"    {step}")
            lines.append("")

        if rc.parts_needed:
            lines.append(f"  Parts Needed:")
            for part in rc.parts_needed:
                lines.append(f"    🔧 {part}")
            lines.append("")

        if rc.related_ics:
            lines.append(f"  Related ICs: {', '.join(rc.related_ics)}")
            lines.append("")

    lines.append("═══════════════════════════════════════════════════════════")

    return "\n".join(lines)
