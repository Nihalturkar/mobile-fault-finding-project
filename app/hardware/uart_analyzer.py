"""
UART Boot Log Analyzer for Mooxy AI Fault Detector.

Captures and analyzes UART boot logs from Android phone motherboards via
serial port (TX/RX/GND), similar to the LUOWEI LW-FAT tool (gzlw.top).
Uses pyserial for UART communication and performs intelligent pattern-based
log analysis against 80+ known error signatures spanning all major phone
subsystems (PMIC, CPU, storage, display, modem, WiFi, audio, camera, etc.).

The module connects to the UART test pads on a phone motherboard, captures
the full boot sequence in real time, then matches every line against a
knowledge base of failure patterns.  Each match produces a structured
FaultDetection with component identification, severity, repair guidance,
and related IC part numbers.

Requires: pyserial (``pip install pyserial``).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
    PYSERIAL_AVAILABLE = True
except ImportError:
    serial = None  # type: ignore[assignment]
    PYSERIAL_AVAILABLE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Progress callback type alias
# ---------------------------------------------------------------------------
ProgressCallback = Optional[Callable[[float, str], None]]

# ---------------------------------------------------------------------------
#  Default serial parameters
# ---------------------------------------------------------------------------
DEFAULT_BAUD_RATE = 115200
DEFAULT_DATA_BITS = 8
DEFAULT_STOP_BITS = 1
DEFAULT_PARITY = "N"
DEFAULT_TIMEOUT = 0.1  # seconds per read attempt
CAPTURE_READ_SIZE = 4096  # bytes per serial read
MAX_CAPTURE_LINES = 50_000  # safety cap

# Boot-stage markers — the *first* match wins so they are ordered early→late.
BOOT_STAGE_MARKERS = [
    (r"Format: Log Type", "PBL"),
    (r"PBL.*start|pbl_main", "PBL"),
    (r"SBL1|sbl1_main_ctl", "SBL"),
    (r"XBL.*start|xbl_loader", "XBL"),
    (r"QSEE|TZ.*loaded|trustzone", "TrustZone"),
    (r"DEVCFG|devcfg.*loaded", "DEVCFG"),
    (r"ABL.*start|aboot|android.*bootloader", "ABL"),
    (r"Linux version|Booting Linux", "Kernel"),
    (r"init: starting|Zygote|SystemServer", "Android"),
    (r"Boot completed|sys\.boot_completed", "Boot OK"),
]

# =========================================================================== #
#   BOOT ERROR PATTERN DATABASE  (80+ entries)                                #
# =========================================================================== #

BOOT_ERROR_PATTERNS: Dict[str, Dict[str, Any]] = {

    # -----------------------------------------------------------------------
    #  1. PMIC / Power Management (patterns 1-10)
    # -----------------------------------------------------------------------
    "PMIC_INIT_FAIL": {
        "patterns": [
            r"pmic.*init.*fail",
            r"pm8150.*error",
            r"pm8350.*fail",
            r"SPMI.*error",
            r"pmic.*not.*respond",
        ],
        "component": "PMIC (Power Management IC)",
        "severity": "critical",
        "description": "PMIC initialization failure - power management IC not responding",
        "repair_suggestion": (
            "Check PMIC solder joints under microscope. Reball or replace PMIC IC. "
            "Verify VIN supply voltage (battery connector). Inspect SPMI bus lines for breaks."
        ),
        "related_ics": ["PM8150", "PM8350", "PM8550", "S2MPS25", "MT6359"],
    },
    "VOLTAGE_RAIL_FAIL": {
        "patterns": [
            r"vdd.*fail",
            r"vreg.*error",
            r"regulator.*fail",
            r"ldo.*fault",
            r"buck.*error",
        ],
        "component": "Voltage Regulator",
        "severity": "critical",
        "description": "Voltage rail regulation failure — one or more power rails out of spec",
        "repair_suggestion": (
            "Measure each voltage rail at PMIC output with multimeter. "
            "Check decoupling capacitors around PMIC for shorts. "
            "Look for shorted tantalum caps (common after liquid damage)."
        ),
        "related_ics": ["PMIC", "Buck Converter", "LDO"],
    },
    "SPMI_BUS_ERROR": {
        "patterns": [
            r"spmi.*bus.*error",
            r"spmi.*transaction.*fail",
            r"spmi_read.*fail",
            r"spmi_write.*fail",
            r"qpnp.*err",
        ],
        "component": "SPMI Bus / PMIC Communication",
        "severity": "critical",
        "description": "SPMI bus communication failure between SoC and PMIC",
        "repair_suggestion": (
            "Check SPMI CLK and DATA lines between CPU and PMIC for continuity. "
            "Inspect for cold solder joints on PMIC or CPU BGA pads. "
            "May require CPU or PMIC reballing."
        ),
        "related_ics": ["PM8150", "PM8350", "SDM845", "SM8150"],
    },
    "BATTERY_DETECT_FAIL": {
        "patterns": [
            r"battery.*not.*detect",
            r"batt_id.*fail",
            r"fg_batt.*absent",
            r"charger.*no.*batt",
            r"bms.*batt.*missing",
        ],
        "component": "Battery Detection Circuit",
        "severity": "high",
        "description": "Battery detection failure — phone cannot identify connected battery",
        "repair_suggestion": (
            "Check battery connector pins for corrosion or damage. "
            "Verify BSI/BATT_ID resistor on battery flex. "
            "Test battery thermistor (NTC) — should read ~10k at 25C."
        ),
        "related_ics": ["Fuel Gauge IC", "BQ27541", "MAX17048", "SM5714"],
    },
    "POWER_ON_REASON_ERR": {
        "patterns": [
            r"pon.*reason.*err",
            r"power_on.*abnormal",
            r"unexpected.*reset.*reason",
            r"pon_reason.*unknown",
        ],
        "component": "Power-On Sequence Logic",
        "severity": "medium",
        "description": "Abnormal power-on reason detected — device reset unexpectedly",
        "repair_suggestion": (
            "Check power button flex cable. Inspect PMIC PON (power-on) pins. "
            "Verify KPDPWR_N line. May indicate power button stuck or PMIC PON fault."
        ),
        "related_ics": ["PMIC", "Power Button Flex"],
    },
    "OVER_VOLTAGE_PROTECT": {
        "patterns": [
            r"ovp.*triggered",
            r"over.?voltage.*protect",
            r"vbus.*ovp",
            r"battery.*over.?volt",
        ],
        "component": "Over-Voltage Protection Circuit",
        "severity": "high",
        "description": "Over-voltage protection triggered on a power rail or VBUS",
        "repair_suggestion": (
            "Check charging IC and protection MOSFETs. "
            "Verify charger output voltage. Inspect for wrong-voltage charger use. "
            "Test battery voltage — should not exceed 4.4 V for standard Li-ion."
        ),
        "related_ics": ["Charging IC", "Protection MOSFET", "BQ25890", "SM5714"],
    },
    "UNDER_VOLTAGE_LOCKOUT": {
        "patterns": [
            r"uvlo.*detect",
            r"under.?voltage.*lock",
            r"vbat.*too.*low",
            r"pmic.*uvlo",
        ],
        "component": "Battery / PMIC Under-Voltage",
        "severity": "high",
        "description": "Battery voltage below minimum threshold — PMIC refusing to boot",
        "repair_suggestion": (
            "Charge battery externally to > 3.2 V before retrying. "
            "Check battery connector and protection circuit. "
            "If battery is good, check for excessive standby drain (shorted rail)."
        ),
        "related_ics": ["PMIC", "Battery Protection PCB"],
    },
    "PMIC_WATCHDOG_BITE": {
        "patterns": [
            r"pmic.*wdog.*bite",
            r"pmic.*watchdog.*expire",
            r"pon_s2.*timer.*expire",
        ],
        "component": "PMIC Watchdog",
        "severity": "critical",
        "description": "PMIC watchdog timer expired — forced hard reset",
        "repair_suggestion": (
            "May indicate CPU hang during early boot. "
            "Check CPU clock and power rails. Verify SoC is not stuck in boot loop."
        ),
        "related_ics": ["PMIC", "CPU/SoC"],
    },
    "LDO_OVER_CURRENT": {
        "patterns": [
            r"ldo.*over.?current",
            r"ldo.*ocp",
            r"regulator.*over.?current",
            r"vreg.*ocp.*trigger",
        ],
        "component": "LDO Regulator (Over-Current)",
        "severity": "high",
        "description": "LDO over-current protection triggered — downstream short suspected",
        "repair_suggestion": (
            "Identify which LDO tripped from the log. Map it to the schematic. "
            "Disconnect downstream load ICs one at a time to isolate the short. "
            "Common culprits: shorted bypass capacitors, damaged peripheral ICs."
        ),
        "related_ics": ["PMIC LDO", "Downstream IC"],
    },
    "SMPS_FAULT": {
        "patterns": [
            r"smps.*fault",
            r"buck.*over.?current",
            r"smps.*ilim",
            r"vreg_bob.*fail",
        ],
        "component": "Switched-Mode Power Supply",
        "severity": "critical",
        "description": "SMPS/Buck converter fault — main power supply rail failure",
        "repair_suggestion": (
            "Check inductor and output capacitor of the affected SMPS rail. "
            "Look for shorted inductors or blown capacitors. "
            "Verify the load connected to the SMPS rail for shorts."
        ),
        "related_ics": ["PMIC SMPS", "BOB Regulator"],
    },

    # -----------------------------------------------------------------------
    #  2. Storage — UFS / eMMC / NAND (patterns 11-18)
    # -----------------------------------------------------------------------
    "UFS_INIT_FAIL": {
        "patterns": [
            r"ufs.*init.*fail",
            r"ufshcd.*error",
            r"scsi.*timeout",
            r"ufs.*link.*fail",
            r"ufshcd.*fatal",
        ],
        "component": "UFS Storage Controller",
        "severity": "critical",
        "description": "UFS storage initialization failure — cannot access main storage",
        "repair_suggestion": (
            "Check UFS IC solder balls (BGA). Verify reference clock signal to UFS. "
            "May need UFS reballing or replacement. Attempt data recovery first if possible."
        ),
        "related_ics": ["Samsung UFS", "SK Hynix UFS", "Micron UFS", "KIOXIA UFS"],
    },
    "EMMC_FAIL": {
        "patterns": [
            r"emmc.*error",
            r"mmc0.*timeout",
            r"mmcblk0.*fail",
            r"mmc.*cmd.*error",
            r"emmc.*crc.*error",
        ],
        "component": "eMMC Storage",
        "severity": "critical",
        "description": "eMMC storage failure — read/write or initialization error",
        "repair_suggestion": (
            "eMMC may need reballing. Check solder connections under microscope. "
            "Attempt data recovery with UFI Box or Medusa before replacing. "
            "Verify CMD, CLK, and DAT lines for continuity."
        ),
        "related_ics": ["Samsung eMMC", "SK Hynix eMMC", "Micron eMMC"],
    },
    "UFS_LINK_STARTUP_FAIL": {
        "patterns": [
            r"ufs.*link.*startup.*fail",
            r"ufshcd.*link.*is.*down",
            r"ufshcd.*hibern8.*fail",
        ],
        "component": "UFS PHY Link",
        "severity": "critical",
        "description": "UFS physical link could not be established between SoC and storage",
        "repair_suggestion": (
            "Check MPHY TX/RX differential pairs for continuity. "
            "Verify reference clock (19.2 MHz or 26 MHz). "
            "If UFS IC was recently replaced, verify correct orientation and alignment."
        ),
        "related_ics": ["UFS PHY", "SoC UFS Controller"],
    },
    "NAND_ECC_ERROR": {
        "patterns": [
            r"nand.*ecc.*error",
            r"nand.*uncorrectable",
            r"mtd.*ecc.*fail",
            r"nand.*bad.*block",
        ],
        "component": "NAND Flash",
        "severity": "high",
        "description": "NAND flash ECC (error correction) failure — data corruption risk",
        "repair_suggestion": (
            "NAND flash may be wearing out. Check bad block count. "
            "If excessive bad blocks, NAND replacement required. "
            "Back up data immediately if device is partially bootable."
        ),
        "related_ics": ["NAND Flash IC"],
    },
    "STORAGE_PARTITION_CORRUPT": {
        "patterns": [
            r"partition.*table.*corrupt",
            r"gpt.*error",
            r"cannot.*mount.*system",
            r"superblock.*invalid",
            r"ext4.*error.*remounting",
        ],
        "component": "Storage Partition Table",
        "severity": "high",
        "description": "Partition table or filesystem corruption detected",
        "repair_suggestion": (
            "May be fixable via EDL mode partition restore or re-flashing. "
            "Use Qualcomm QFIL or MediaTek SP Flash Tool to rewrite partition table. "
            "If hardware is fine, a full firmware re-flash should fix this."
        ),
        "related_ics": ["eMMC/UFS Storage"],
    },
    "FW_LOAD_STORAGE_FAIL": {
        "patterns": [
            r"firmware.*load.*from.*partition.*fail",
            r"cannot.*read.*modem.*partition",
            r"tz.*image.*not.*found",
        ],
        "component": "Firmware Partition Read",
        "severity": "critical",
        "description": "Failed to load firmware image from storage partition",
        "repair_suggestion": (
            "Re-flash affected partition via EDL/Download mode. "
            "If storage IC is faulty, partition re-flash will also fail. "
            "Check storage IC health with JTAG/ISP tools."
        ),
        "related_ics": ["eMMC/UFS", "SoC Boot ROM"],
    },
    "RPMB_ERROR": {
        "patterns": [
            r"rpmb.*error",
            r"rpmb.*auth.*fail",
            r"rpmb.*write.*fail",
        ],
        "component": "RPMB (Replay Protected Memory Block)",
        "severity": "high",
        "description": "RPMB authentication or access failure",
        "repair_suggestion": (
            "RPMB key mismatch — often after storage IC replacement without key programming. "
            "May require vendor service tool to re-provision RPMB. "
            "Cannot be fixed by simple re-flash."
        ),
        "related_ics": ["eMMC/UFS RPMB Partition"],
    },
    "STORAGE_TIMEOUT": {
        "patterns": [
            r"mmc.*request.*timeout",
            r"ufs.*query.*timeout",
            r"block.*device.*timeout",
            r"scsi.*cmd.*timeout",
        ],
        "component": "Storage Controller Timeout",
        "severity": "critical",
        "description": "Storage device not responding to commands within timeout period",
        "repair_suggestion": (
            "Check storage IC power rails (VCCQ, VCC). "
            "Verify clock signal. Inspect solder joints. "
            "If intermittent, storage IC may be failing and need replacement."
        ),
        "related_ics": ["eMMC/UFS IC", "PMIC Storage Rails"],
    },

    # -----------------------------------------------------------------------
    #  3. CPU / SoC (patterns 19-28)
    # -----------------------------------------------------------------------
    "CPU_THERMAL_FAIL": {
        "patterns": [
            r"thermal.*critical",
            r"cpu.*overheat",
            r"tsens.*threshold",
            r"thermal.*shutdown",
        ],
        "component": "CPU/SoC Thermal",
        "severity": "high",
        "description": "CPU thermal threshold exceeded — emergency thermal shutdown",
        "repair_suggestion": (
            "Check thermal paste/pad between SoC and heat spreader. "
            "Verify cooling path and thermal pad contact. "
            "May indicate a short circuit on a power rail causing excess current draw."
        ),
        "related_ics": ["SoC", "Thermal Pad", "Heat Spreader"],
    },
    "CPU_CLOCK_FAIL": {
        "patterns": [
            r"clk.*enable.*fail",
            r"pll.*lock.*fail",
            r"clock.*source.*error",
            r"xo.*not.*ready",
            r"gcc_.*clk.*fail",
        ],
        "component": "CPU Clock Subsystem",
        "severity": "critical",
        "description": "Clock PLL or oscillator failure — CPU cannot reach target frequency",
        "repair_suggestion": (
            "Check 19.2 MHz crystal oscillator (XO) for continuity and output. "
            "Verify PLL supply voltage. Inspect clock buffer ICs. "
            "XO replacement may be needed if no oscillation is detected."
        ),
        "related_ics": ["Crystal Oscillator (XO)", "PLL", "Clock Buffer IC"],
    },
    "CPU_SUBSYSTEM_CRASH": {
        "patterns": [
            r"subsys.*crash",
            r"subsystem.*restart",
            r"ssr.*triggered",
            r"PIL.*fail.*load",
        ],
        "component": "CPU Subsystem (DSP/GPU/Modem)",
        "severity": "high",
        "description": "A processor subsystem crashed and triggered SSR (Subsystem Restart)",
        "repair_suggestion": (
            "Identify which subsystem crashed (ADSP, CDSP, SLPI, modem). "
            "Re-flash firmware for that subsystem. If hardware, check the "
            "corresponding IC power rail and clock."
        ),
        "related_ics": ["SoC", "DSP", "GPU", "Modem"],
    },
    "CPU_BOOT_FAIL": {
        "patterns": [
            r"cpu.*boot.*fail",
            r"cpu.*stuck",
            r"secondary.*cpu.*fail",
            r"cpu.*online.*fail",
        ],
        "component": "CPU Core Boot",
        "severity": "critical",
        "description": "One or more CPU cores failed to come online during boot",
        "repair_suggestion": (
            "May indicate SoC damage. Check VDD_CX and VDD_MX power rails. "
            "If secondary cores fail, CPU die damage is likely — board replacement needed."
        ),
        "related_ics": ["SoC", "PMIC VDD_CX", "PMIC VDD_MX"],
    },
    "CACHE_ERROR": {
        "patterns": [
            r"cache.*parity.*error",
            r"l[12].*cache.*error",
            r"cache.*ecc.*fail",
        ],
        "component": "CPU Cache (L1/L2)",
        "severity": "critical",
        "description": "CPU cache memory error — parity or ECC failure",
        "repair_suggestion": (
            "CPU silicon damage — cannot be repaired. "
            "Board replacement or CPU swap (BGA rework) required. "
            "May be caused by prior overheating or voltage spike."
        ),
        "related_ics": ["SoC"],
    },
    "APPS_WATCHDOG_RESET": {
        "patterns": [
            r"apps.*wdog.*bite",
            r"apps.*watchdog.*reset",
            r"msm.*wdog.*bark",
        ],
        "component": "Application Processor Watchdog",
        "severity": "critical",
        "description": "Application processor watchdog timer expired — CPU hung during boot",
        "repair_suggestion": (
            "CPU is hanging during boot. Check firmware, power rails (VDD_CX). "
            "Attempt full firmware re-flash. If persists, SoC or PMIC fault likely."
        ),
        "related_ics": ["SoC", "PMIC"],
    },
    "SECURE_BOOT_FAIL": {
        "patterns": [
            r"secure.*boot.*fail",
            r"image.*auth.*fail",
            r"cert.*chain.*fail",
            r"hash.*mismatch",
            r"anti.*rollback.*fail",
        ],
        "component": "Secure Boot / TrustZone",
        "severity": "critical",
        "description": "Secure boot authentication failure — firmware signature invalid",
        "repair_suggestion": (
            "Firmware images may be corrupt or mismatched to device. "
            "Re-flash with correct signed firmware for this exact model/variant. "
            "Anti-rollback failure means firmware is older than fuse-programmed minimum."
        ),
        "related_ics": ["SoC eFuse", "TrustZone"],
    },
    "TRUSTZONE_ERROR": {
        "patterns": [
            r"tz.*error",
            r"trustzone.*fail",
            r"qsee.*error",
            r"tee.*init.*fail",
            r"secure.*world.*crash",
        ],
        "component": "TrustZone / TEE",
        "severity": "critical",
        "description": "TrustZone Secure World error during initialization",
        "repair_suggestion": (
            "Re-flash TZ firmware. If persists, RPMB or eFuse mismatch. "
            "May occur after storage IC replacement if RPMB key was not migrated."
        ),
        "related_ics": ["SoC TZ", "RPMB"],
    },
    "RPM_CRASH": {
        "patterns": [
            r"rpm.*crash",
            r"rpm.*wdog",
            r"rpm.*err.*fatal",
            r"rpmh.*timeout",
        ],
        "component": "RPM (Resource Power Manager)",
        "severity": "critical",
        "description": "RPM processor crash — low-level power management failed",
        "repair_suggestion": (
            "RPM handles all voltage rail sequencing. A crash here usually means "
            "PMIC communication failure or RPM firmware corruption. Re-flash RPM image. "
            "If persists, check SPMI bus and PMIC."
        ),
        "related_ics": ["SoC RPM", "PMIC"],
    },
    "DDR_TRAINING_FAIL": {
        "patterns": [
            r"ddr.*training.*fail",
            r"ddr.*init.*fail",
            r"mem.*init.*error",
            r"dram.*not.*detected",
            r"bimc.*error",
        ],
        "component": "DDR / RAM",
        "severity": "critical",
        "description": "DDR memory training or initialization failure",
        "repair_suggestion": (
            "RAM IC may have bad solder joints or be defective. "
            "Reball RAM IC. Check VDDQ and VDD2 power rails to RAM. "
            "If PoP (Package-on-Package), CPU+RAM assembly may need replacement."
        ),
        "related_ics": ["LPDDR4/5 RAM", "SoC Memory Controller"],
    },

    # -----------------------------------------------------------------------
    #  4. Display / Panel / Backlight (patterns 29-36)
    # -----------------------------------------------------------------------
    "DISPLAY_PANEL_INIT_FAIL": {
        "patterns": [
            r"panel.*init.*fail",
            r"dsi.*panel.*not.*found",
            r"display.*init.*error",
            r"mdss.*panel.*off",
        ],
        "component": "Display Panel",
        "severity": "high",
        "description": "Display panel initialization failed — no panel detected",
        "repair_suggestion": (
            "Check display FPC (flex cable) connection. Re-seat display connector. "
            "Verify display power rails (VDDIO, VCI). "
            "Try a known-good display to rule out panel vs. board fault."
        ),
        "related_ics": ["Display Panel", "Display Connector"],
    },
    "BACKLIGHT_FAIL": {
        "patterns": [
            r"backlight.*fail",
            r"wled.*error",
            r"bl_driver.*fail",
            r"backlight.*i2c.*err",
            r"lm36274.*error",
        ],
        "component": "Backlight Driver IC",
        "severity": "medium",
        "description": "Backlight driver failure — screen may be completely dark",
        "repair_suggestion": (
            "Check backlight driver IC (often LM36274 or similar). "
            "Verify LED anode/cathode connections. Measure VLED voltage rail. "
            "Inspect for burned-out backlight LEDs (older LCD models)."
        ),
        "related_ics": ["LM36274", "TPS65132", "Backlight IC"],
    },
    "MIPI_DSI_ERROR": {
        "patterns": [
            r"dsi.*error",
            r"mipi.*dsi.*fail",
            r"dsi.*phy.*error",
            r"dsi.*cmd.*timeout",
            r"dsi.*fifo.*underflow",
        ],
        "component": "MIPI DSI Interface",
        "severity": "high",
        "description": "MIPI DSI communication error between SoC and display panel",
        "repair_suggestion": (
            "Check MIPI DSI data lanes for continuity. Inspect display connector pins. "
            "Verify DSI clock and data line impedances. "
            "May be a display IC fault or SoC output issue."
        ),
        "related_ics": ["SoC DSI Controller", "Display Driver IC"],
    },
    "TOUCH_CONTROLLER_FAIL": {
        "patterns": [
            r"touch.*init.*fail",
            r"touchscreen.*not.*found",
            r"synaptics.*error",
            r"goodix.*fail",
            r"fts.*i2c.*err",
            r"atmel_mxt.*fail",
        ],
        "component": "Touch Controller IC",
        "severity": "medium",
        "description": "Touchscreen controller initialization failure",
        "repair_suggestion": (
            "Check touch IC I2C connection (SDA/SCL). Verify AVDD and DVDD power rails. "
            "Re-seat display flex if touch IC is on the display assembly. "
            "May need touch IC replacement if I2C address responds but init fails."
        ),
        "related_ics": ["Synaptics S3706", "Goodix GT9XX", "FocalTech FT5X46"],
    },
    "DISPLAY_POWER_FAIL": {
        "patterns": [
            r"display.*power.*fail",
            r"lcm.*bias.*fail",
            r"vsp.*vsn.*error",
            r"display.*regulator.*fail",
        ],
        "component": "Display Power Supply",
        "severity": "high",
        "description": "Display power rail (VSP/VSN bias or VDDIO) failure",
        "repair_suggestion": (
            "Check display bias IC (TPS65132 or similar). "
            "Measure VSP (+5.5 V) and VSN (-5.5 V) at display connector. "
            "Verify VDDIO (1.8 V) to display. Inspect for shorted bias capacitors."
        ),
        "related_ics": ["TPS65132", "LCD Bias IC", "PMIC Display LDO"],
    },
    "HDMI_MHL_ERROR": {
        "patterns": [
            r"hdmi.*init.*fail",
            r"mhl.*error",
            r"dp.*link.*fail",
            r"edid.*read.*fail",
        ],
        "component": "HDMI / MHL / DisplayPort Output",
        "severity": "low",
        "description": "External display output initialization error",
        "repair_suggestion": (
            "Check HDMI/DP connector and ESD protection ICs. "
            "Verify level-shifter IC if present. May be firmware issue."
        ),
        "related_ics": ["HDMI Switch IC", "USB-C Mux"],
    },
    "DISPLAY_ESD_DETECT": {
        "patterns": [
            r"esd.*check.*fail",
            r"panel.*esd.*detect",
            r"display.*esd.*recover",
        ],
        "component": "Display ESD Protection",
        "severity": "medium",
        "description": "Display panel ESD event detected — panel may be damaged",
        "repair_suggestion": (
            "Panel may have electrostatic damage. Try power cycling. "
            "If recurring, display assembly replacement recommended."
        ),
        "related_ics": ["Display Panel", "ESD Protection Diodes"],
    },
    "FRAMEBUFFER_ERROR": {
        "patterns": [
            r"fb.*error",
            r"framebuffer.*fail",
            r"mdss.*fb.*err",
            r"drm.*error",
        ],
        "component": "Framebuffer / GPU Display Pipeline",
        "severity": "medium",
        "description": "Framebuffer or display pipeline error in kernel/driver",
        "repair_suggestion": (
            "Usually a software/firmware issue. Re-flash firmware. "
            "If persists after re-flash, may indicate GPU or display controller fault."
        ),
        "related_ics": ["SoC GPU", "Display Controller"],
    },

    # -----------------------------------------------------------------------
    #  5. Modem / Baseband / RF (patterns 37-44)
    # -----------------------------------------------------------------------
    "MODEM_CRASH": {
        "patterns": [
            r"modem.*crash",
            r"mpss.*crash",
            r"modem.*subsystem.*fail",
            r"baseband.*error",
            r"modem.*assert",
        ],
        "component": "Modem / Baseband Processor",
        "severity": "high",
        "description": "Modem subsystem crashed — no cellular connectivity",
        "repair_suggestion": (
            "Re-flash modem firmware. If hardware fault, check modem "
            "power rails and clock. On Qualcomm, check SDX55/X60 modem IC. "
            "May need baseband IC reballing or replacement."
        ),
        "related_ics": ["SDX55", "SDX65", "Samsung Exynos Modem", "MT6362"],
    },
    "MODEM_FIRMWARE_FAIL": {
        "patterns": [
            r"modem.*fw.*fail",
            r"mpss.*load.*fail",
            r"mba.*auth.*fail",
            r"modem.*image.*error",
        ],
        "component": "Modem Firmware",
        "severity": "high",
        "description": "Modem firmware loading or authentication failure",
        "repair_suggestion": (
            "Re-flash modem firmware (NON-HLOS.bin / modem.img). "
            "Ensure correct firmware version for carrier/region. "
            "If auth failure, secure boot mismatch — use correct signed image."
        ),
        "related_ics": ["Modem Processor", "SoC"],
    },
    "RF_CALIBRATION_FAIL": {
        "patterns": [
            r"rf.*cal.*fail",
            r"rfcal.*error",
            r"nv.*calibration.*miss",
            r"rf.*nv.*corrupt",
        ],
        "component": "RF Calibration Data",
        "severity": "high",
        "description": "RF calibration data missing or corrupt — poor signal quality",
        "repair_suggestion": (
            "RF calibration NV data may be lost. Restore from backup if available. "
            "Full RF calibration requires factory equipment. "
            "Check EFS partition integrity."
        ),
        "related_ics": ["RF Transceiver", "EFS Partition"],
    },
    "RF_TRANSCEIVER_FAIL": {
        "patterns": [
            r"wtr.*error",
            r"rf.*transceiver.*fail",
            r"qfe.*error",
            r"rf.*init.*fail",
        ],
        "component": "RF Transceiver IC",
        "severity": "high",
        "description": "RF transceiver IC initialization failure",
        "repair_suggestion": (
            "Check RF transceiver IC (WTR/SDR series) solder joints. "
            "Verify RF power rails. Inspect antenna switch and filter ICs. "
            "May need RF front-end rework."
        ),
        "related_ics": ["WTR2965", "SDR865", "QTC410S"],
    },
    "SIM_DETECT_FAIL": {
        "patterns": [
            r"sim.*not.*detect",
            r"sim.*card.*absent",
            r"uim.*error",
            r"sim.*voltage.*fail",
        ],
        "component": "SIM Card Interface",
        "severity": "medium",
        "description": "SIM card not detected or communication failure",
        "repair_suggestion": (
            "Check SIM tray and connector pins for damage. "
            "Verify SIM_VDD, SIM_CLK, SIM_DATA, SIM_RST lines. "
            "Clean SIM contacts. Check SIM ESD protection diodes."
        ),
        "related_ics": ["PMIC SIM Interface", "SIM ESD IC"],
    },
    "ANTENNA_MISMATCH": {
        "patterns": [
            r"antenna.*mismatch",
            r"vswr.*high",
            r"antenna.*detect.*fail",
        ],
        "component": "Antenna / RF Path",
        "severity": "medium",
        "description": "Antenna impedance mismatch or detection failure",
        "repair_suggestion": (
            "Check antenna contact springs. Verify antenna flex cable connection. "
            "Inspect antenna tuner IC. May be broken antenna feed line."
        ),
        "related_ics": ["Antenna Tuner IC", "QAT3555"],
    },
    "IMEI_INVALID": {
        "patterns": [
            r"imei.*invalid",
            r"imei.*null",
            r"imei.*00000",
            r"nv_read.*imei.*fail",
        ],
        "component": "IMEI / NV Data",
        "severity": "high",
        "description": "IMEI number is missing, null, or invalid",
        "repair_suggestion": (
            "IMEI stored in EFS or RPMB partition. Attempt NV restore from backup. "
            "If eMMC/UFS was replaced, IMEI must be re-programmed via JTAG/ISP. "
            "Warning: IMEI tampering may be illegal in some jurisdictions."
        ),
        "related_ics": ["eMMC/UFS EFS Partition", "RPMB"],
    },
    "GPS_INIT_FAIL": {
        "patterns": [
            r"gps.*init.*fail",
            r"gnss.*error",
            r"gps.*firmware.*fail",
            r"loc.*mq.*error",
        ],
        "component": "GPS / GNSS Module",
        "severity": "low",
        "description": "GPS/GNSS subsystem initialization failure",
        "repair_suggestion": (
            "Check GPS antenna connection (usually a small coax). "
            "Verify GPS LNA (Low Noise Amplifier) IC. "
            "Re-flash GNSS firmware. Check clock input to GPS module."
        ),
        "related_ics": ["GNSS Module", "GPS LNA"],
    },

    # -----------------------------------------------------------------------
    #  6. WiFi / Bluetooth (patterns 45-52)
    # -----------------------------------------------------------------------
    "WIFI_FIRMWARE_FAIL": {
        "patterns": [
            r"wifi.*firmware.*fail",
            r"wcn.*fw.*load.*fail",
            r"wlan.*firmware.*error",
            r"ath.*fw.*crash",
            r"wcnss.*error",
        ],
        "component": "WiFi Firmware",
        "severity": "high",
        "description": "WiFi firmware loading failure",
        "repair_suggestion": (
            "Re-flash WiFi firmware. Check WiFi IC power rails. "
            "If WCN3990/WCN6856 chip, verify VDDA and VDDIO supply. "
            "May need WiFi IC replacement if firmware load repeatedly fails."
        ),
        "related_ics": ["WCN3990", "WCN6856", "WCN7850", "MT7921"],
    },
    "WIFI_INIT_FAIL": {
        "patterns": [
            r"wlan.*init.*fail",
            r"wifi.*driver.*fail",
            r"wlan.*probe.*fail",
            r"wifi.*chip.*not.*respond",
        ],
        "component": "WiFi IC",
        "severity": "high",
        "description": "WiFi hardware initialization failure — chip not responding",
        "repair_suggestion": (
            "Check WiFi IC solder joints. Verify WiFi IC power supply. "
            "Check PCIe or SDIO interface to WiFi chip. "
            "Inspect for liquid damage corrosion around WiFi IC."
        ),
        "related_ics": ["WCN3990", "WCN6856", "QCA6390"],
    },
    "BT_INIT_FAIL": {
        "patterns": [
            r"bluetooth.*init.*fail",
            r"bt.*firmware.*fail",
            r"hci.*timeout",
            r"bt.*power.*on.*fail",
            r"btusb.*fail",
        ],
        "component": "Bluetooth Controller",
        "severity": "medium",
        "description": "Bluetooth initialization or firmware load failure",
        "repair_suggestion": (
            "Bluetooth often shares IC with WiFi (combo chip). "
            "Check BT firmware partition. Verify UART/PCM lines between SoC and BT chip. "
            "If combo chip, fixing WiFi issue may also fix BT."
        ),
        "related_ics": ["WCN3990", "WCN6856", "BCM4389"],
    },
    "WIFI_MAC_ERROR": {
        "patterns": [
            r"wifi.*mac.*error",
            r"wlan.*mac.*invalid",
            r"wifi.*mac.*00:00:00",
        ],
        "component": "WiFi MAC Address",
        "severity": "medium",
        "description": "WiFi MAC address missing or invalid",
        "repair_suggestion": (
            "MAC address stored in NV area. Restore from backup or re-program. "
            "Check NV/persist partition integrity."
        ),
        "related_ics": ["WiFi IC", "NV Storage"],
    },
    "NFC_INIT_FAIL": {
        "patterns": [
            r"nfc.*init.*fail",
            r"nxp.*nfc.*error",
            r"pn553.*fail",
            r"nfc.*i2c.*err",
            r"ese.*error",
        ],
        "component": "NFC Controller",
        "severity": "low",
        "description": "NFC controller initialization failure",
        "repair_suggestion": (
            "Check NFC IC I2C connection. Verify VEN and IRQ lines. "
            "Inspect NFC antenna coil for damage. Check NFC IC power supply (1.8 V). "
            "Common ICs: NXP PN553, ST21NFC."
        ),
        "related_ics": ["NXP PN553", "NXP SN220", "ST21NFC"],
    },
    "WIFI_PCIE_ERROR": {
        "patterns": [
            r"pcie.*wlan.*fail",
            r"wifi.*pcie.*link.*down",
            r"wlan.*pci.*error",
        ],
        "component": "WiFi PCIe Link",
        "severity": "high",
        "description": "PCIe link to WiFi chip failed — bus-level communication error",
        "repair_suggestion": (
            "Check PCIe differential pairs between SoC and WiFi IC. "
            "Verify PERST# signal. May need WiFi IC reballing."
        ),
        "related_ics": ["WiFi IC", "SoC PCIe Controller"],
    },
    "WIFI_THERMAL_THROTTLE": {
        "patterns": [
            r"wlan.*thermal.*throttl",
            r"wifi.*temp.*high",
        ],
        "component": "WiFi IC Thermal",
        "severity": "low",
        "description": "WiFi chip is throttling due to high temperature",
        "repair_suggestion": (
            "Check for shorted components near WiFi IC generating heat. "
            "Ensure thermal pad contact. May be normal under heavy load."
        ),
        "related_ics": ["WiFi IC"],
    },
    "BT_SCO_ERROR": {
        "patterns": [
            r"bt.*sco.*error",
            r"hfp.*audio.*fail",
            r"bt.*pcm.*error",
        ],
        "component": "Bluetooth Audio (SCO/HFP)",
        "severity": "low",
        "description": "Bluetooth SCO audio path error",
        "repair_suggestion": (
            "Check PCM/I2S lines between BT chip and audio codec. "
            "May be firmware issue — re-flash BT firmware."
        ),
        "related_ics": ["BT Combo IC", "Audio Codec"],
    },

    # -----------------------------------------------------------------------
    #  7. Audio Codec (patterns 53-58)
    # -----------------------------------------------------------------------
    "AUDIO_CODEC_FAIL": {
        "patterns": [
            r"codec.*init.*fail",
            r"wcd.*error",
            r"audio.*codec.*fail",
            r"wcd938.*not.*respond",
            r"cs35l41.*error",
        ],
        "component": "Audio Codec IC",
        "severity": "medium",
        "description": "Audio codec IC initialization failure",
        "repair_suggestion": (
            "Check audio codec IC (WCD9380/WCD9385 or CS35L41). "
            "Verify I2S/SLIMbus connection. Check codec power rail (VDD). "
            "May need codec IC replacement or reballing."
        ),
        "related_ics": ["WCD9380", "WCD9385", "CS35L41", "ALC5682"],
    },
    "SPEAKER_AMP_FAIL": {
        "patterns": [
            r"speaker.*amp.*fail",
            r"amp.*i2c.*error",
            r"smart.*amp.*fail",
            r"cs35l41.*i2c.*err",
            r"tas2562.*error",
        ],
        "component": "Speaker Amplifier IC",
        "severity": "medium",
        "description": "Speaker amplifier IC initialization or I2C failure",
        "repair_suggestion": (
            "Check speaker amp IC (CS35L41, TAS2562, MAX98390). "
            "Verify I2C address and bus. Check amp power supply. "
            "Inspect speaker connector and speaker coil resistance (should be 6-8 ohm)."
        ),
        "related_ics": ["CS35L41", "TAS2562", "MAX98390"],
    },
    "MIC_DETECT_FAIL": {
        "patterns": [
            r"mic.*detect.*fail",
            r"headset.*detect.*error",
            r"mbhc.*error",
            r"jack.*detect.*fail",
        ],
        "component": "Microphone / Headset Detection",
        "severity": "low",
        "description": "Microphone or headset jack detection failure",
        "repair_suggestion": (
            "Check microphone bias voltage (MICBIAS). "
            "Verify headset jack connector. Inspect MBHC (Microphone Bias and "
            "Headset Controller) circuit on audio codec."
        ),
        "related_ics": ["Audio Codec MBHC", "Headset Jack"],
    },
    "AUDIO_DSP_ERROR": {
        "patterns": [
            r"adsp.*error",
            r"audio.*dsp.*fail",
            r"afe.*error",
            r"adsp.*crash",
        ],
        "component": "Audio DSP (ADSP)",
        "severity": "medium",
        "description": "Audio DSP subsystem error or crash",
        "repair_suggestion": (
            "Re-flash ADSP firmware. Check ADSP power rails (VDD_CX). "
            "If hardware fault, SoC ADSP block may be damaged."
        ),
        "related_ics": ["SoC ADSP", "Audio Codec"],
    },
    "HAPTIC_DRIVER_FAIL": {
        "patterns": [
            r"haptic.*fail",
            r"vibrator.*error",
            r"drv2624.*error",
            r"aw869.*fail",
        ],
        "component": "Haptic / Vibration Motor Driver",
        "severity": "low",
        "description": "Haptic feedback driver IC failure",
        "repair_suggestion": (
            "Check haptic driver IC (DRV2624, AW8697). Verify I2C bus. "
            "Check vibration motor connector and motor coil resistance."
        ),
        "related_ics": ["DRV2624", "AW8697", "AW8692"],
    },
    "SLIMBUS_ERROR": {
        "patterns": [
            r"slimbus.*error",
            r"slim.*bus.*fail",
            r"ngd.*slim.*err",
        ],
        "component": "SLIMbus (Audio Bus)",
        "severity": "medium",
        "description": "SLIMbus communication error between SoC and audio codec",
        "repair_suggestion": (
            "Check SLIMbus CLK and DATA lines. "
            "Verify audio codec power supply is stable. "
            "May indicate audio codec IC failure."
        ),
        "related_ics": ["SoC SLIMbus", "Audio Codec"],
    },

    # -----------------------------------------------------------------------
    #  8. Camera Subsystem (patterns 59-64)
    # -----------------------------------------------------------------------
    "CAMERA_PROBE_FAIL": {
        "patterns": [
            r"camera.*probe.*fail",
            r"cam.*sensor.*not.*found",
            r"imx.*error",
            r"ov.*sensor.*fail",
            r"s5k.*detect.*fail",
        ],
        "component": "Camera Sensor",
        "severity": "medium",
        "description": "Camera sensor not detected during probe",
        "repair_suggestion": (
            "Check camera FPC connector. Verify MCLK, SDA, SCL signals. "
            "Check camera AVDD, DVDD, IOVDD power rails (usually 2.8 V, 1.05 V, 1.8 V). "
            "Try a known-good camera module."
        ),
        "related_ics": ["Sony IMX686", "Samsung S5K3M5", "OmniVision OV48C"],
    },
    "CAMERA_CCI_ERROR": {
        "patterns": [
            r"cci.*error",
            r"cci.*timeout",
            r"camera.*i2c.*fail",
            r"cam.*cci.*bus.*err",
        ],
        "component": "Camera CCI (I2C) Bus",
        "severity": "medium",
        "description": "Camera I2C (CCI) bus communication error",
        "repair_suggestion": (
            "Check CCI SDA/SCL lines for continuity. "
            "Verify camera connector pin alignment. Check pull-up resistors. "
            "CCI bus address conflict is possible with multiple cameras."
        ),
        "related_ics": ["Camera Sensor", "SoC CCI Controller"],
    },
    "CAMERA_ISP_FAIL": {
        "patterns": [
            r"isp.*error",
            r"isp.*init.*fail",
            r"vfe.*error",
            r"csid.*error",
            r"csiphy.*error",
        ],
        "component": "Camera ISP (Image Signal Processor)",
        "severity": "medium",
        "description": "Camera ISP or MIPI CSI interface error",
        "repair_suggestion": (
            "Check MIPI CSI data lanes between camera and SoC. "
            "Verify camera module is correct variant for this board. "
            "May be firmware issue — re-flash camera firmware blobs."
        ),
        "related_ics": ["SoC ISP", "Camera Sensor"],
    },
    "CAMERA_ACTUATOR_FAIL": {
        "patterns": [
            r"actuator.*fail",
            r"ois.*error",
            r"af.*driver.*fail",
            r"vcm.*error",
        ],
        "component": "Camera Autofocus / OIS Actuator",
        "severity": "low",
        "description": "Camera autofocus or optical image stabilization actuator failure",
        "repair_suggestion": (
            "Check VCM (Voice Coil Motor) driver. Verify I2C connection to AF actuator. "
            "OIS IC may need re-initialization. Replace camera module if actuator is stuck."
        ),
        "related_ics": ["AF Actuator IC", "OIS Controller"],
    },
    "CAMERA_FLASH_FAIL": {
        "patterns": [
            r"flash.*led.*fail",
            r"flash.*driver.*error",
            r"torch.*error",
            r"lm3644.*fail",
        ],
        "component": "Camera Flash LED Driver",
        "severity": "low",
        "description": "Camera flash LED driver initialization failure",
        "repair_suggestion": (
            "Check flash driver IC (LM3644 or similar). Verify I2C bus. "
            "Check flash LED anode/cathode connections. "
            "Measure LED forward voltage and current limit."
        ),
        "related_ics": ["LM3644", "AW36518", "Flash LED"],
    },
    "CAMERA_EEPROM_FAIL": {
        "patterns": [
            r"eeprom.*read.*fail",
            r"cam.*eeprom.*error",
            r"otp.*read.*fail",
            r"cam.*calibration.*miss",
        ],
        "component": "Camera EEPROM / OTP Calibration",
        "severity": "medium",
        "description": "Camera EEPROM or OTP calibration data read failure",
        "repair_suggestion": (
            "Camera calibration data in EEPROM/OTP is per-module. "
            "If camera module was replaced, new calibration may be needed. "
            "Check EEPROM I2C access. Corrupt EEPROM degrades image quality."
        ),
        "related_ics": ["Camera EEPROM", "OTP Memory"],
    },

    # -----------------------------------------------------------------------
    #  9. USB / Charging (patterns 65-72)
    # -----------------------------------------------------------------------
    "USB_CONTROLLER_ERROR": {
        "patterns": [
            r"usb.*error",
            r"dwc3.*error",
            r"xhci.*fail",
            r"usb.*phy.*fail",
            r"usb.*init.*fail",
        ],
        "component": "USB Controller",
        "severity": "high",
        "description": "USB controller or PHY initialization failure",
        "repair_suggestion": (
            "Check USB connector and flex cable. Verify USB PHY power rail. "
            "Inspect for bent or corroded USB-C connector pins. "
            "USB PHY in SoC may be damaged — check SS (SuperSpeed) lines."
        ),
        "related_ics": ["SoC USB PHY", "USB-C Connector", "USB Mux IC"],
    },
    "CHARGING_IC_FAIL": {
        "patterns": [
            r"charger.*error",
            r"smb.*fail",
            r"bq25.*error",
            r"charging.*ic.*fail",
            r"sm5714.*error",
        ],
        "component": "Charging IC",
        "severity": "high",
        "description": "Charging IC initialization or communication failure",
        "repair_suggestion": (
            "Check charging IC (SMB1390, BQ25898, SM5714). "
            "Verify VBUS input from USB connector. Check I2C bus. "
            "Inspect for thermal damage to charging IC (overheating is common)."
        ),
        "related_ics": ["SMB1390", "BQ25898", "SM5714", "S2MU106"],
    },
    "FAST_CHARGE_FAIL": {
        "patterns": [
            r"pd.*negotiation.*fail",
            r"qc.*handshake.*fail",
            r"vooc.*error",
            r"fast.*charge.*fail",
            r"pd.*contract.*fail",
        ],
        "component": "Fast Charging Protocol",
        "severity": "medium",
        "description": "Fast charge protocol negotiation failure (PD/QC/VOOC)",
        "repair_suggestion": (
            "Check USB-C CC lines for continuity. Verify PD controller IC. "
            "Check for damaged VBUS path components (MOSFETs, fuses). "
            "Try different cable and charger to isolate issue."
        ),
        "related_ics": ["PD Controller", "FUSB302", "VOOC IC"],
    },
    "USB_CC_ERROR": {
        "patterns": [
            r"cc.*detect.*fail",
            r"typec.*error",
            r"cc.*line.*error",
            r"usb.*orientation.*fail",
        ],
        "component": "USB Type-C CC Detection",
        "severity": "medium",
        "description": "USB Type-C CC pin detection failure — cannot determine cable orientation",
        "repair_suggestion": (
            "Check CC1/CC2 pins on USB-C connector for damage. "
            "Verify pull-up/pull-down resistors. Check USB mux IC (FUSB302 or similar). "
            "Clean USB connector thoroughly."
        ),
        "related_ics": ["FUSB302", "USB-C Connector", "CC Logic IC"],
    },
    "WIRELESS_CHARGE_FAIL": {
        "patterns": [
            r"wireless.*charge.*fail",
            r"wpc.*error",
            r"qi.*init.*fail",
            r"idtp9220.*error",
        ],
        "component": "Wireless Charging IC",
        "severity": "low",
        "description": "Wireless charging (Qi/WPC) IC initialization failure",
        "repair_suggestion": (
            "Check wireless charging coil connector. Verify WPC IC (IDTP9220/P9415). "
            "Check for damage to the charging coil. Inspect solder joints on WPC IC."
        ),
        "related_ics": ["IDTP9220", "P9415", "Qi Coil"],
    },
    "BATTERY_AUTH_FAIL": {
        "patterns": [
            r"batt.*auth.*fail",
            r"battery.*genuine.*fail",
            r"batt_id.*mismatch",
        ],
        "component": "Battery Authentication",
        "severity": "medium",
        "description": "Battery authentication failure — non-genuine battery detected",
        "repair_suggestion": (
            "Third-party battery may not have correct authentication chip. "
            "Use OEM battery or one with correct auth IC. "
            "Some phones can be patched to bypass auth via firmware."
        ),
        "related_ics": ["Battery Auth IC", "BSI Resistor"],
    },
    "OTG_FAIL": {
        "patterns": [
            r"otg.*fail",
            r"vbus.*boost.*fail",
            r"otg.*overcurrent",
            r"usb.*host.*fail",
        ],
        "component": "USB OTG (On-The-Go)",
        "severity": "low",
        "description": "USB OTG power delivery or host mode failure",
        "repair_suggestion": (
            "Check OTG VBUS boost converter. Verify OTG ID detection circuit. "
            "Inspect for USB connector damage affecting ID pin."
        ),
        "related_ics": ["OTG Boost IC", "USB Mux IC"],
    },
    "FUEL_GAUGE_ERROR": {
        "patterns": [
            r"fuel.*gauge.*error",
            r"fg_gen.*error",
            r"bq27.*fail",
            r"max17.*error",
        ],
        "component": "Fuel Gauge IC",
        "severity": "medium",
        "description": "Battery fuel gauge IC communication or reading error",
        "repair_suggestion": (
            "Check fuel gauge IC I2C connection. Verify sense resistor. "
            "Fuel gauge may need profile re-learning (full discharge/charge cycle). "
            "Replace fuel gauge IC if I2C communication fails completely."
        ),
        "related_ics": ["BQ27541", "MAX17048", "Fuel Gauge IC"],
    },

    # -----------------------------------------------------------------------
    #  10. Kernel / System-level (patterns 73-80)
    # -----------------------------------------------------------------------
    "KERNEL_PANIC": {
        "patterns": [
            r"Kernel panic",
            r"kernel.*panic.*not.*syncing",
            r"Unable to handle kernel",
            r"BUG:.*kernel.*null.*pointer",
        ],
        "component": "Linux Kernel",
        "severity": "critical",
        "description": "Kernel panic — Linux kernel crashed with fatal error",
        "repair_suggestion": (
            "Capture full panic dump for analysis. Check the call trace for driver name. "
            "Often caused by faulty hardware driver interaction. "
            "Re-flash firmware. If persists, suspect RAM or storage corruption."
        ),
        "related_ics": ["SoC", "RAM", "Storage"],
    },
    "KERNEL_OOPS": {
        "patterns": [
            r"Oops:.*\[#",
            r"kernel.*oops",
            r"Internal error:.*Oops",
        ],
        "component": "Linux Kernel (Non-Fatal)",
        "severity": "high",
        "description": "Kernel oops — non-fatal kernel error that may cause instability",
        "repair_suggestion": (
            "Check driver associated with the oops. "
            "May be a firmware bug — re-flash. "
            "If recurring, likely hardware interaction issue."
        ),
        "related_ics": ["SoC", "Associated Peripheral"],
    },
    "WATCHDOG_TIMEOUT": {
        "patterns": [
            r"watchdog.*timeout",
            r"wdt.*expire",
            r"wdog.*bark",
            r"hung_task.*blocked",
        ],
        "component": "System Watchdog",
        "severity": "critical",
        "description": "Hardware or software watchdog timer expired — system hung",
        "repair_suggestion": (
            "System hung during boot. Common causes: storage timeout, "
            "PMIC communication hang, damaged RAM. "
            "Check all critical power rails and clock signals."
        ),
        "related_ics": ["SoC WDT", "PMIC", "Storage IC"],
    },
    "I2C_BUS_ERROR": {
        "patterns": [
            r"i2c.*error",
            r"i2c.*transfer.*fail",
            r"i2c.*timeout",
            r"i2c.*nack",
            r"i2c.*bus.*stuck",
        ],
        "component": "I2C Bus",
        "severity": "medium",
        "description": "I2C bus communication error — a peripheral IC not responding",
        "repair_suggestion": (
            "Identify the I2C bus number and device address from the log. "
            "Check SDA/SCL lines for continuity and proper pull-ups. "
            "Inspect the peripheral IC on that bus for solder joint issues."
        ),
        "related_ics": ["I2C Peripheral IC", "Pull-up Resistors"],
    },
    "SPI_BUS_ERROR": {
        "patterns": [
            r"spi.*error",
            r"spi.*transfer.*fail",
            r"spi.*timeout",
            r"spi_master.*fail",
        ],
        "component": "SPI Bus",
        "severity": "medium",
        "description": "SPI bus communication error",
        "repair_suggestion": (
            "Check MOSI, MISO, CLK, CS lines for continuity. "
            "Verify SPI slave IC power supply. "
            "Common SPI slaves: fingerprint sensor, NFC, display."
        ),
        "related_ics": ["SPI Peripheral IC"],
    },
    "GPIO_ERROR": {
        "patterns": [
            r"gpio.*request.*fail",
            r"gpio.*interrupt.*error",
            r"tlmm.*error",
            r"pinctrl.*fail",
        ],
        "component": "GPIO / Pin Control",
        "severity": "low",
        "description": "GPIO pin configuration or interrupt error",
        "repair_suggestion": (
            "Usually a firmware configuration issue. May indicate a shorted GPIO pin. "
            "Check the device tree overlay for correct pin mapping."
        ),
        "related_ics": ["SoC GPIO"],
    },
    "PCIE_ERROR": {
        "patterns": [
            r"pcie.*error",
            r"pcie.*link.*fail",
            r"pci.*bus.*error",
            r"pcie.*timeout",
        ],
        "component": "PCIe Bus",
        "severity": "high",
        "description": "PCIe bus error — link to a peripheral (WiFi, modem) failed",
        "repair_suggestion": (
            "Check PCIe lanes for continuity. Verify reference clock. "
            "Inspect the peripheral IC connected via PCIe. "
            "Common PCIe devices: WiFi chip, external modem."
        ),
        "related_ics": ["WiFi IC", "Modem IC", "SoC PCIe PHY"],
    },
    "FINGERPRINT_FAIL": {
        "patterns": [
            r"fingerprint.*init.*fail",
            r"fpc.*error",
            r"goodix_fp.*fail",
            r"fingerprint.*spi.*err",
            r"egis.*fail",
        ],
        "component": "Fingerprint Sensor",
        "severity": "low",
        "description": "Fingerprint sensor initialization failure",
        "repair_suggestion": (
            "Check fingerprint sensor FPC connector. Verify SPI bus connection. "
            "Check sensor power supply (typically 1.8 V and 3.3 V). "
            "May need sensor flex cable replacement."
        ),
        "related_ics": ["FPC1028", "Goodix GF3208", "Egistec"],
    },

    # -----------------------------------------------------------------------
    #  11. Additional subsystem patterns (81-88)
    # -----------------------------------------------------------------------
    "SENSOR_HUB_FAIL": {
        "patterns": [
            r"sensor.*hub.*fail",
            r"sensorhub.*error",
            r"nanohub.*error",
            r"ssp.*error",
        ],
        "component": "Sensor Hub IC",
        "severity": "low",
        "description": "Sensor hub (accelerometer, gyro, proximity) initialization failure",
        "repair_suggestion": (
            "Check sensor hub IC (STM LSM6DSO, Bosch BMI260). "
            "Verify I2C/SPI connection to SoC. May need firmware re-flash for sensor hub."
        ),
        "related_ics": ["STM LSM6DSO", "Bosch BMI260", "Sensor Hub MCU"],
    },
    "PROXIMITY_SENSOR_FAIL": {
        "patterns": [
            r"proximity.*fail",
            r"als.*error",
            r"stk3x.*error",
            r"tmd2725.*fail",
        ],
        "component": "Proximity / Ambient Light Sensor",
        "severity": "low",
        "description": "Proximity or ambient light sensor initialization failure",
        "repair_suggestion": (
            "Check proximity sensor I2C bus. Verify sensor window is clean and unblocked. "
            "Inspect sensor IC (STK3338, TMD2725) and its power supply."
        ),
        "related_ics": ["STK3338", "TMD2725", "LTR559"],
    },
    "UWB_FAIL": {
        "patterns": [
            r"uwb.*init.*fail",
            r"uwb.*firmware.*fail",
            r"dwm3000.*error",
            r"sr1.*init.*fail",
        ],
        "component": "UWB (Ultra-Wideband) Module",
        "severity": "low",
        "description": "UWB module initialization or firmware load failure",
        "repair_suggestion": (
            "Check UWB IC SPI connection. Verify firmware partition. "
            "Inspect UWB antenna. Power cycle may resolve firmware hang."
        ),
        "related_ics": ["Apple U1", "NXP SR150", "Qorvo DW3000"],
    },
    "IOEXPANDER_FAIL": {
        "patterns": [
            r"ioexpander.*fail",
            r"tca64.*error",
            r"gpio.*expander.*fail",
        ],
        "component": "I/O Expander IC",
        "severity": "medium",
        "description": "I/O expander IC initialization failure",
        "repair_suggestion": (
            "Check I/O expander I2C bus. Verify IC power supply. "
            "May affect multiple peripherals controlled by this expander."
        ),
        "related_ics": ["TCA6424A", "PCA9535"],
    },
    "FASTBOOT_FAIL": {
        "patterns": [
            r"fastboot.*fail",
            r"cannot.*enter.*fastboot",
            r"fastboot.*usb.*err",
        ],
        "component": "Fastboot Mode",
        "severity": "medium",
        "description": "Device cannot enter or operate in fastboot mode",
        "repair_suggestion": (
            "Check USB connection. Verify bootloader is unlockable. "
            "May indicate ABL (Android Bootloader) corruption — use EDL mode."
        ),
        "related_ics": ["SoC", "USB Controller"],
    },
    "EDL_MODE_ERROR": {
        "patterns": [
            r"edl.*error",
            r"sahara.*fail",
            r"firehose.*error",
            r"emergency.*download.*fail",
        ],
        "component": "EDL (Emergency Download) Mode",
        "severity": "critical",
        "description": "Emergency Download mode communication failure",
        "repair_suggestion": (
            "Check EDL mode test point connections. Verify Sahara/Firehose protocol. "
            "Ensure correct programmer file (.elf/.mbn) for the chipset. "
            "If EDL itself fails, SoC boot ROM may be damaged."
        ),
        "related_ics": ["SoC Boot ROM", "eMMC/UFS"],
    },
    "FUSE_BLOW_ERROR": {
        "patterns": [
            r"fuse.*blow.*error",
            r"qfprom.*error",
            r"efuse.*fail",
            r"otp.*write.*fail",
        ],
        "component": "eFuse / QFPROM",
        "severity": "critical",
        "description": "eFuse programming error — security fuse state unexpected",
        "repair_suggestion": (
            "eFuse errors are usually fatal. Blown fuses cannot be reversed. "
            "If anti-rollback fuse is wrong, matching firmware must be found. "
            "Consult chipset-specific documentation."
        ),
        "related_ics": ["SoC QFPROM", "eFuse Bank"],
    },
    "RAMDUMP_TRIGGERED": {
        "patterns": [
            r"ramdump.*mode",
            r"upload.*mode.*enter",
            r"debug.*dump.*collect",
            r"ramdump.*triggered",
        ],
        "component": "RAM Dump / Crash Recovery",
        "severity": "critical",
        "description": "Device entered RAM dump mode due to fatal crash",
        "repair_suggestion": (
            "Collect and analyze the RAM dump for crash cause. "
            "Force reboot and check if issue is reproducible. "
            "May indicate underlying hardware fault causing repeated crashes."
        ),
        "related_ics": ["SoC", "RAM", "Storage"],
    },
}


# =========================================================================== #
#   Severity ranking (for sorting)                                            #
# =========================================================================== #
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


# =========================================================================== #
#   Dataclasses                                                               #
# =========================================================================== #

@dataclass
class FaultDetection:
    """A single fault found by matching a boot log line against a known pattern."""

    fault_id: str = ""
    component: str = ""
    severity: str = ""            # critical, high, medium, low
    description: str = ""
    matched_line: str = ""
    line_number: int = 0
    repair_suggestion: str = ""
    related_ics: List[str] = field(default_factory=list)
    confidence: float = 0.0       # 0.0 – 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fault_id": self.fault_id,
            "component": self.component,
            "severity": self.severity,
            "description": self.description,
            "matched_line": self.matched_line,
            "line_number": self.line_number,
            "repair_suggestion": self.repair_suggestion,
            "related_ics": self.related_ics,
            "confidence": self.confidence,
        }


@dataclass
class BootLogAnalysis:
    """Complete analysis result for a captured boot log."""

    total_lines: int = 0
    capture_duration: float = 0.0
    faults: List[FaultDetection] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    boot_stage_reached: str = ""   # PBL, SBL, XBL, TrustZone, ABL, Kernel, Android, Boot OK
    primary_fault: Optional[FaultDetection] = None
    repair_summary: str = ""
    overall_status: str = "Unknown"  # Boot OK, Boot Fail, Partial Boot
    warnings: List[str] = field(default_factory=list)

    # -- helpers -----------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_lines": self.total_lines,
            "capture_duration": self.capture_duration,
            "faults": [f.to_dict() for f in self.faults],
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "boot_stage_reached": self.boot_stage_reached,
            "primary_fault": self.primary_fault.to_dict() if self.primary_fault else None,
            "repair_summary": self.repair_summary,
            "overall_status": self.overall_status,
            "warnings": self.warnings,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @property
    def has_critical(self) -> bool:
        return self.critical_count > 0

    @property
    def total_faults(self) -> int:
        return len(self.faults)


@dataclass
class SerialPortInfo:
    """Metadata about an available serial port."""

    device: str = ""
    description: str = ""
    hwid: str = ""
    manufacturer: str = ""
    vid: Optional[int] = None
    pid: Optional[int] = None


# =========================================================================== #
#   UARTConnection — serial port capture                                      #
# =========================================================================== #

class UARTConnection:
    """Manages a serial UART connection to a phone motherboard for boot-log capture.

    Typical usage::

        conn = UARTConnection("COM3", baud_rate=115200)
        conn.connect()
        conn.start_capture()
        # ... power on phone ...
        time.sleep(15)
        lines = conn.stop_capture()
        conn.disconnect()
        result = analyze_boot_log(lines)
    """

    def __init__(
        self,
        port: str,
        baud_rate: int = DEFAULT_BAUD_RATE,
        data_bits: int = DEFAULT_DATA_BITS,
        stop_bits: int = DEFAULT_STOP_BITS,
        parity: str = DEFAULT_PARITY,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.data_bits = data_bits
        self.stop_bits = stop_bits
        self.parity = parity
        self.timeout = timeout

        self.serial_conn: Any = None  # serial.Serial or None
        self.is_capturing: bool = False
        self.captured_lines: List[str] = []
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._capture_start_time: float = 0.0
        self._capture_callback: Optional[Callable[[str], None]] = None

    # -- connection management ---------------------------------------------

    def connect(self) -> bool:
        """Open the serial port. Returns True on success."""
        if not PYSERIAL_AVAILABLE:
            logger.error("pyserial is not installed. Run: pip install pyserial")
            return False
        if self.serial_conn is not None and self.serial_conn.is_open:
            logger.warning("Already connected to %s", self.port)
            return True
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                bytesize=self.data_bits,
                stopbits=self.stop_bits,
                parity=self.parity,
                timeout=self.timeout,
            )
            logger.info(
                "UART connected: %s @ %d baud", self.port, self.baud_rate,
            )
            return True
        except serial.SerialException as exc:
            logger.error("Failed to open %s: %s", self.port, exc)
            self.serial_conn = None
            return False

    def disconnect(self) -> None:
        """Close the serial port and stop any running capture."""
        if self.is_capturing:
            self.stop_capture()
        if self.serial_conn is not None:
            try:
                self.serial_conn.close()
            except Exception:  # noqa: BLE001
                pass
            self.serial_conn = None
            logger.info("UART disconnected from %s", self.port)

    @property
    def is_connected(self) -> bool:
        return self.serial_conn is not None and self.serial_conn.is_open

    # -- capture control ---------------------------------------------------

    def start_capture(
        self,
        callback: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Start capturing UART data in a background thread.

        Parameters
        ----------
        callback:
            Optional callable invoked with each line received (for live UI
            updates).  Called from the capture thread so it must be
            thread-safe.

        Returns True if the capture thread was started.
        """
        if not self.is_connected:
            logger.error("Cannot start capture — not connected")
            return False
        if self.is_capturing:
            logger.warning("Capture already running")
            return False

        self.captured_lines.clear()
        self._stop_event.clear()
        self._capture_callback = callback
        self._capture_start_time = time.monotonic()
        self.is_capturing = True

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="uart-capture",
            daemon=True,
        )
        self._capture_thread.start()
        logger.info("UART capture started on %s", self.port)
        return True

    def stop_capture(self) -> List[str]:
        """Signal the capture thread to stop and wait for it.

        Returns the list of captured lines.
        """
        if not self.is_capturing:
            return list(self.captured_lines)

        self._stop_event.set()
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=5.0)
        self.is_capturing = False

        elapsed = time.monotonic() - self._capture_start_time
        logger.info(
            "UART capture stopped. %d lines in %.1f s",
            len(self.captured_lines),
            elapsed,
        )
        return list(self.captured_lines)

    def get_capture_duration(self) -> float:
        """Return elapsed seconds since capture started (or 0)."""
        if not self.is_capturing:
            return 0.0
        return time.monotonic() - self._capture_start_time

    # -- background read loop ----------------------------------------------

    def _capture_loop(self) -> None:
        """Read lines from serial in a loop until stop_event is set."""
        buf = b""
        while not self._stop_event.is_set():
            try:
                chunk = self.serial_conn.read(CAPTURE_READ_SIZE)  # type: ignore[union-attr]
                if not chunk:
                    continue
                buf += chunk
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")
                    with self._lock:
                        if len(self.captured_lines) < MAX_CAPTURE_LINES:
                            self.captured_lines.append(line)
                    if self._capture_callback is not None:
                        try:
                            self._capture_callback(line)
                        except Exception:  # noqa: BLE001
                            pass
            except serial.SerialException as exc:  # type: ignore[union-attr]
                logger.error("Serial read error: %s", exc)
                break
            except Exception:  # noqa: BLE001
                if self._stop_event.is_set():
                    break

        # flush remaining buffer
        if buf:
            line = buf.decode("utf-8", errors="replace").rstrip("\r")
            if line:
                with self._lock:
                    if len(self.captured_lines) < MAX_CAPTURE_LINES:
                        self.captured_lines.append(line)

    # -- port enumeration --------------------------------------------------

    @staticmethod
    def get_available_ports() -> List[SerialPortInfo]:
        """Return a list of serial ports visible on this system."""
        if not PYSERIAL_AVAILABLE:
            logger.error("pyserial not available — cannot list ports")
            return []
        ports: List[SerialPortInfo] = []
        for p in serial.tools.list_ports.comports():
            info = SerialPortInfo(
                device=p.device,
                description=p.description or "",
                hwid=p.hwid or "",
                manufacturer=p.manufacturer or "",
                vid=p.vid,
                pid=p.pid,
            )
            ports.append(info)
        ports.sort(key=lambda x: x.device)
        return ports

    # -- convenience -------------------------------------------------------

    def send_command(self, cmd: str) -> bool:
        """Send a raw command string over UART (used by some LUOWEI protocols).

        Appends ``\\r\\n`` automatically.
        """
        if not self.is_connected:
            logger.error("Cannot send — not connected")
            return False
        try:
            self.serial_conn.write((cmd + "\r\n").encode("utf-8"))  # type: ignore[union-attr]
            self.serial_conn.flush()  # type: ignore[union-attr]
            return True
        except serial.SerialException as exc:  # type: ignore[union-attr]
            logger.error("Send failed: %s", exc)
            return False

    def __repr__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return (
            f"UARTConnection(port={self.port!r}, baud={self.baud_rate}, "
            f"status={status})"
        )


# =========================================================================== #
#   Compiled patterns cache                                                   #
# =========================================================================== #

_COMPILED_PATTERNS: Dict[str, List[re.Pattern[str]]] = {}


def _ensure_compiled() -> None:
    """Compile all regex patterns once (lazy initialisation)."""
    if _COMPILED_PATTERNS:
        return
    for fault_id, info in BOOT_ERROR_PATTERNS.items():
        _COMPILED_PATTERNS[fault_id] = [
            re.compile(p, re.IGNORECASE) for p in info["patterns"]
        ]


# =========================================================================== #
#   Boot-stage detection                                                      #
# =========================================================================== #

_STAGE_RE: List[Tuple[re.Pattern[str], str]] = []


def _ensure_stage_re() -> None:
    if _STAGE_RE:
        return
    for pattern, stage in BOOT_STAGE_MARKERS:
        _STAGE_RE.append((re.compile(pattern, re.IGNORECASE), stage))


def _detect_boot_stage(line: str) -> Optional[str]:
    """Return the boot stage name if *line* matches a stage marker, else None."""
    _ensure_stage_re()
    for regex, stage in _STAGE_RE:
        if regex.search(line):
            return stage
    return None


# =========================================================================== #
#   Pattern matching engine                                                   #
# =========================================================================== #

def _match_line(
    line: str,
    line_number: int,
) -> List[FaultDetection]:
    """Match a single log line against all known error patterns.

    Returns zero or more FaultDetection instances (a single line *can*
    match multiple independent fault patterns).
    """
    _ensure_compiled()
    results: List[FaultDetection] = []
    for fault_id, compiled_list in _COMPILED_PATTERNS.items():
        for regex in compiled_list:
            m = regex.search(line)
            if m:
                info = BOOT_ERROR_PATTERNS[fault_id]
                detection = FaultDetection(
                    fault_id=fault_id,
                    component=info["component"],
                    severity=info["severity"],
                    description=info["description"],
                    matched_line=line.strip(),
                    line_number=line_number,
                    repair_suggestion=info["repair_suggestion"],
                    related_ics=list(info.get("related_ics", [])),
                    confidence=_compute_confidence(line, m, info),
                )
                results.append(detection)
                break  # only need first match within this fault_id
    return results


def _compute_confidence(
    line: str,
    match: re.Match,  # type: ignore[type-arg]
    info: Dict[str, Any],
) -> float:
    """Heuristic confidence score (0–1) for a pattern match.

    Factors:
    - Match length vs line length (longer match -> higher confidence)
    - Presence of related IC names in the same line boosts confidence
    - Severity weight (critical patterns treated with higher base)
    """
    base = 0.60
    # Longer relative match is more trustworthy
    match_len = match.end() - match.start()
    line_len = max(len(line.strip()), 1)
    length_bonus = min(match_len / line_len, 0.20)

    # Check if any related IC name appears in the line
    ic_bonus = 0.0
    for ic in info.get("related_ics", []):
        if ic.lower() in line.lower():
            ic_bonus = 0.15
            break

    # Severity bonus
    sev_map = {"critical": 0.05, "high": 0.03, "medium": 0.01, "low": 0.0}
    sev_bonus = sev_map.get(info.get("severity", "low"), 0.0)

    return min(round(base + length_bonus + ic_bonus + sev_bonus, 2), 1.0)


# =========================================================================== #
#   Analysis helpers                                                          #
# =========================================================================== #

def _determine_overall_status(
    boot_stage: str,
    critical_count: int,
) -> str:
    """Return 'Boot OK', 'Boot Fail', or 'Partial Boot'."""
    if boot_stage == "Boot OK":
        return "Boot OK" if critical_count == 0 else "Partial Boot"
    if boot_stage in ("Android", "Kernel"):
        return "Partial Boot"
    if critical_count > 0:
        return "Boot Fail"
    if boot_stage:
        return "Partial Boot"
    return "Unknown"


def _build_repair_summary(faults: List[FaultDetection]) -> str:
    """Generate a human-readable repair summary from the list of faults."""
    if not faults:
        return "No faults detected. Boot sequence appears normal."

    # Group by component
    component_map: Dict[str, List[FaultDetection]] = {}
    for f in faults:
        component_map.setdefault(f.component, []).append(f)

    lines: List[str] = []
    lines.append(f"Detected {len(faults)} fault(s) across {len(component_map)} component(s).")
    lines.append("")

    # Sort components by worst severity
    sorted_components = sorted(
        component_map.items(),
        key=lambda kv: min(SEVERITY_RANK.get(f.severity, 99) for f in kv[1]),
    )

    for idx, (component, comp_faults) in enumerate(sorted_components, 1):
        worst = min(comp_faults, key=lambda f: SEVERITY_RANK.get(f.severity, 99))
        lines.append(f"{idx}. [{worst.severity.upper()}] {component}")
        lines.append(f"   {worst.description}")
        lines.append(f"   Repair: {worst.repair_suggestion}")
        if worst.related_ics:
            lines.append(f"   Related ICs: {', '.join(worst.related_ics)}")
        lines.append("")

    return "\n".join(lines)


def _generate_warnings(
    faults: List[FaultDetection],
    total_lines: int,
    boot_stage: str,
) -> List[str]:
    """Generate additional warning messages."""
    warnings: List[str] = []

    if total_lines == 0:
        warnings.append(
            "No log lines captured. Verify UART connection: TX->RX, RX->TX, GND->GND."
        )
    elif total_lines < 10:
        warnings.append(
            "Very few log lines captured. Check baud rate (try 115200, 921600) "
            "and verify TX/RX are not swapped."
        )

    if not boot_stage:
        warnings.append(
            "Could not determine boot stage. Device may not have powered on, "
            "or UART output is not from the application processor."
        )

    # Check for repeated faults (same fault_id many times)
    fault_counts: Dict[str, int] = {}
    for f in faults:
        fault_counts[f.fault_id] = fault_counts.get(f.fault_id, 0) + 1
    for fid, count in fault_counts.items():
        if count >= 5:
            warnings.append(
                f"Fault '{fid}' triggered {count} times — persistent hardware issue likely."
            )

    # Multiple critical faults suggest cascading failure
    critical_ids = {f.fault_id for f in faults if f.severity == "critical"}
    if len(critical_ids) >= 3:
        warnings.append(
            "Multiple critical subsystems failing — suspect primary power (PMIC) or "
            "main SoC failure causing cascading errors."
        )

    return warnings


# =========================================================================== #
#   Main analysis function                                                    #
# =========================================================================== #

def analyze_boot_log(
    log_lines: List[str],
    callback: ProgressCallback = None,
    capture_duration: float = 0.0,
) -> BootLogAnalysis:
    """Analyze UART boot log lines against the known-error pattern database.

    Parameters
    ----------
    log_lines:
        Lines captured from UART (one string per line).
    callback:
        Optional ``(progress_float, status_string)`` callback for UI updates.
        ``progress_float`` ranges from 0.0 to 1.0.
    capture_duration:
        Total seconds the capture lasted (informational).

    Returns
    -------
    BootLogAnalysis
        Structured result with faults, counts, repair summary, etc.
    """
    _ensure_compiled()

    analysis = BootLogAnalysis(
        total_lines=len(log_lines),
        capture_duration=capture_duration,
    )

    if not log_lines:
        analysis.warnings.append("Empty log — nothing to analyze.")
        analysis.overall_status = "Unknown"
        if callback:
            callback(1.0, "No log data")
        return analysis

    last_stage: str = ""
    seen_fault_ids: Dict[str, int] = {}  # fault_id -> first occurrence line
    total = len(log_lines)

    for idx, line in enumerate(log_lines):
        # -- progress reporting
        if callback and (idx % 100 == 0 or idx == total - 1):
            pct = (idx + 1) / total
            callback(pct, f"Analyzing line {idx + 1}/{total}")

        # -- boot stage detection
        stage = _detect_boot_stage(line)
        if stage is not None:
            last_stage = stage

        # -- fault pattern matching
        detections = _match_line(line, line_number=idx + 1)
        for det in detections:
            # De-duplicate: only keep the first hit per fault_id
            if det.fault_id not in seen_fault_ids:
                seen_fault_ids[det.fault_id] = idx + 1
                analysis.faults.append(det)
            else:
                # Optionally boost confidence of existing match
                pass

    # -- count severities
    for f in analysis.faults:
        if f.severity == "critical":
            analysis.critical_count += 1
        elif f.severity == "high":
            analysis.high_count += 1
        elif f.severity == "medium":
            analysis.medium_count += 1
        elif f.severity == "low":
            analysis.low_count += 1

    # -- sort faults: critical first, then by line number
    analysis.faults.sort(
        key=lambda f: (SEVERITY_RANK.get(f.severity, 99), f.line_number),
    )

    # -- boot stage and overall status
    analysis.boot_stage_reached = last_stage
    analysis.overall_status = _determine_overall_status(
        last_stage, analysis.critical_count,
    )

    # -- primary fault (first critical, else first high, else first)
    if analysis.faults:
        analysis.primary_fault = analysis.faults[0]

    # -- repair summary
    analysis.repair_summary = _build_repair_summary(analysis.faults)

    # -- warnings
    analysis.warnings = _generate_warnings(
        analysis.faults, analysis.total_lines, analysis.boot_stage_reached,
    )

    if callback:
        callback(1.0, "Analysis complete")

    logger.info(
        "Boot log analysis complete: %d lines, %d faults (%d critical), stage=%s, status=%s",
        analysis.total_lines,
        len(analysis.faults),
        analysis.critical_count,
        analysis.boot_stage_reached,
        analysis.overall_status,
    )

    return analysis


# =========================================================================== #
#   Convenience: capture + analyze in one call                                #
# =========================================================================== #

def capture_and_analyze(
    port: str,
    baud_rate: int = DEFAULT_BAUD_RATE,
    capture_seconds: float = 15.0,
    callback: ProgressCallback = None,
) -> Tuple[BootLogAnalysis, List[str]]:
    """Open UART, capture for *capture_seconds*, then analyze.

    Parameters
    ----------
    port:
        Serial port name, e.g. ``"COM3"`` or ``"/dev/ttyUSB0"``.
    baud_rate:
        UART baud rate (default 115200).
    capture_seconds:
        How long to capture (seconds).  Phone should be powered on shortly
        after capture starts.
    callback:
        Progress callback ``(float, str)``.

    Returns
    -------
    tuple of (BootLogAnalysis, raw_lines)
    """
    conn = UARTConnection(port, baud_rate=baud_rate)

    if callback:
        callback(0.0, f"Connecting to {port}...")

    if not conn.connect():
        analysis = BootLogAnalysis()
        analysis.warnings.append(f"Could not open serial port {port}.")
        analysis.overall_status = "Connection Error"
        return analysis, []

    if callback:
        callback(0.05, "Connected. Starting capture...")

    conn.start_capture()
    start_ts = time.monotonic()

    # Wait for the requested duration, reporting progress
    while True:
        elapsed = time.monotonic() - start_ts
        if elapsed >= capture_seconds:
            break
        if callback:
            pct = 0.05 + 0.45 * min(elapsed / capture_seconds, 1.0)
            callback(pct, f"Capturing... {elapsed:.1f}/{capture_seconds:.0f}s ({len(conn.captured_lines)} lines)")
        time.sleep(0.5)

    raw_lines = conn.stop_capture()
    duration = time.monotonic() - start_ts
    conn.disconnect()

    if callback:
        callback(0.55, f"Capture done ({len(raw_lines)} lines). Analyzing...")

    # Wrap the analyze callback to fit within the 0.55–1.0 progress range
    def _analyze_cb(pct: float, msg: str) -> None:
        if callback:
            callback(0.55 + pct * 0.45, msg)

    analysis = analyze_boot_log(raw_lines, callback=_analyze_cb, capture_duration=duration)
    return analysis, raw_lines


# =========================================================================== #
#   File-based log analysis (load log from file)                              #
# =========================================================================== #

def analyze_log_file(
    file_path: str,
    callback: ProgressCallback = None,
) -> BootLogAnalysis:
    """Read a saved UART log file and analyze it.

    Supports plain-text files with one log line per line.  Lines starting
    with common timestamp formats are accepted as-is.
    """
    if callback:
        callback(0.0, f"Loading {file_path}...")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [l.rstrip("\n\r") for l in fh if l.strip()]
    except OSError as exc:
        logger.error("Cannot read log file %s: %s", file_path, exc)
        analysis = BootLogAnalysis()
        analysis.warnings.append(f"Failed to read file: {exc}")
        analysis.overall_status = "File Error"
        return analysis

    if callback:
        callback(0.05, f"Loaded {len(lines)} lines. Analyzing...")

    def _inner_cb(pct: float, msg: str) -> None:
        if callback:
            callback(0.05 + pct * 0.95, msg)

    return analyze_boot_log(lines, callback=_inner_cb)


# =========================================================================== #
#   Utility: export analysis to JSON                                          #
# =========================================================================== #

def export_analysis_json(
    analysis: BootLogAnalysis,
    file_path: str,
) -> bool:
    """Write the analysis result to a JSON file."""
    try:
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(analysis.to_json(indent=2))
        logger.info("Analysis exported to %s", file_path)
        return True
    except OSError as exc:
        logger.error("Failed to export analysis: %s", exc)
        return False


# =========================================================================== #
#   Utility: get pattern database summary                                     #
# =========================================================================== #

def get_pattern_summary() -> Dict[str, Any]:
    """Return a summary of the built-in pattern database.

    Useful for showing the user how many patterns and subsystems are covered.
    """
    subsystem_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    total_regex = 0

    for info in BOOT_ERROR_PATTERNS.values():
        component = info["component"]
        severity = info["severity"]
        num_patterns = len(info["patterns"])

        # Group by simplified subsystem name
        subsystem = component.split("/")[0].split("(")[0].strip()
        subsystem_counts[subsystem] = subsystem_counts.get(subsystem, 0) + 1
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
        total_regex += num_patterns

    return {
        "total_fault_ids": len(BOOT_ERROR_PATTERNS),
        "total_regex_patterns": total_regex,
        "by_subsystem": dict(sorted(subsystem_counts.items())),
        "by_severity": dict(sorted(severity_counts.items())),
    }


# =========================================================================== #
#   Utility: search patterns by keyword                                       #
# =========================================================================== #

def search_patterns(keyword: str) -> List[Dict[str, Any]]:
    """Search the pattern database by keyword (component, description, IC).

    Returns a list of matching pattern info dicts.
    """
    keyword_lower = keyword.lower()
    results: List[Dict[str, Any]] = []
    for fault_id, info in BOOT_ERROR_PATTERNS.items():
        searchable = " ".join([
            fault_id,
            info["component"],
            info["description"],
            info["repair_suggestion"],
            " ".join(info.get("related_ics", [])),
        ]).lower()
        if keyword_lower in searchable:
            results.append({"fault_id": fault_id, **info})
    return results


# =========================================================================== #
#   Device Identification from UART Boot Log                                  #
# =========================================================================== #

# Chipset identification patterns — extracted from real UART boot logs
_CHIPSET_LOG_PATTERNS: List[Tuple[str, str]] = [
    # MediaTek patterns
    (r"mt(\d{4}[a-zA-Z]?)", "MT{0}"),
    (r"MT(\d{4}[a-zA-Z]?)", "MT{0}"),
    (r"mediatek[,/\s]+mt(\d{4})", "MT{0}"),
    (r"chip\s*(?:id|ver).*mt(\d{4})", "MT{0}"),
    (r"mtkfb.*mt(\d{4})", "MT{0}"),
    (r"platform\s*=?\s*mt(\d{4})", "MT{0}"),
    (r"\[PMIC\].*MT(\d{4})", "MT{0}"),
    (r"preloader.*MT(\d{4})", "MT{0}"),
    (r"lk.*mt(\d{4})", "MT{0}"),
    # Qualcomm patterns
    (r"SM(\d{4})", "SM{0}"),
    (r"sm(\d{4})", "SM{0}"),
    (r"SDM(\d{3,4})", "SDM{0}"),
    (r"sdm(\d{3,4})", "SDM{0}"),
    (r"MSM(\d{4})", "MSM{0}"),
    (r"msm(\d{4})", "MSM{0}"),
    (r"qualcomm.*sm(\d{4})", "SM{0}"),
    (r"qcom.*sm(\d{4})", "SM{0}"),
    # Exynos patterns
    (r"[Ee]xynos\s*(\d{3,4})", "Exynos{0}"),
    (r"S5E(\d{4})", "Exynos_S5E{0}"),
    (r"exynos(\d{4})", "Exynos{0}"),
    # Unisoc/Spreadtrum patterns
    (r"SC(\d{4}[A-Z]?)", "SC{0}"),
    (r"sc(\d{4}[a-zA-Z]?)", "SC{0}"),
    (r"[Tt]iger\s*[Tt]?(\d{3,4})", "T{0}"),
    (r"ums(\d{3,4})", "UMS{0}"),
    # Tensor (Google)
    (r"[Tt]ensor\s*[Gg]?(\d?)", "Tensor G{0}"),
    # PMIC identification (helps narrow down chipset)
    (r"PM(\d{4}[A-Z]?)", "PM{0}"),
    (r"pm(\d{4}[a-zA-Z]?)", "PM{0}"),
    (r"MT6359", "PMIC_MT6359"),
    (r"MT6357", "PMIC_MT6357"),
    (r"MT6358", "PMIC_MT6358"),
]

# Brand/device patterns in boot log
_BRAND_LOG_PATTERNS: List[Tuple[str, str]] = [
    (r"ro\.product\.brand\s*=\s*(\w+)", "brand"),
    (r"ro\.product\.model\s*=\s*(.+?)[\s\n]", "model"),
    (r"ro\.product\.device\s*=\s*(\w+)", "codename"),
    (r"ro\.product\.board\s*=\s*(\w+)", "board"),
    (r"ro\.hardware\s*=\s*(\w+)", "hardware"),
    (r"ro\.build\.display\.id\s*=\s*(.+?)[\s\n]", "firmware"),
    (r"androidboot\.hardware\s*=\s*(\w+)", "hardware"),
    (r"Samsung|SAMSUNG|samsung", "brand:samsung"),
    (r"OnePlus|oneplus|ONEPLUS", "brand:oneplus"),
    (r"Xiaomi|xiaomi|XIAOMI|Redmi|redmi|POCO|poco", "brand:xiaomi"),
    (r"realme|Realme|REALME", "brand:realme"),
    (r"OPPO|oppo|Oppo", "brand:oppo"),
    (r"vivo|Vivo|VIVO|iQOO|iqoo", "brand:vivo"),
    (r"motorola|Motorola|MOTOROLA", "brand:motorola"),
    (r"Nothing|nothing", "brand:nothing"),
    (r"Google|google|Pixel|pixel", "brand:google"),
]


@dataclass
class DeviceIdentification:
    """Device identified from UART boot log analysis."""
    chipset: str = ""
    chipset_name: str = ""
    brand: str = ""
    model: str = ""
    codename: str = ""
    board: str = ""
    hardware: str = ""
    firmware: str = ""
    pmic: str = ""
    # From phone_database.json lookup
    db_match: bool = False
    db_device_name: str = ""
    db_brand: str = ""
    db_info: Dict[str, Any] = field(default_factory=dict)
    # From chipset_ic_database.json lookup
    chipset_info: Dict[str, Any] = field(default_factory=dict)
    common_faults: List[str] = field(default_factory=list)
    related_ics: Dict[str, str] = field(default_factory=dict)
    repair_tips: List[str] = field(default_factory=list)
    confidence: float = 0.0


def identify_device_from_log(
    log_lines: List[str],
    callback: ProgressCallback = None,
) -> DeviceIdentification:
    """
    Extract device identity from UART boot log lines.

    Scans boot log for chipset identifiers (MT6762, SM8350, etc.),
    brand/model properties, and PMIC references, then matches against
    phone_database.json and chipset_ic_database.json for full repair info.

    Args:
        log_lines: Captured UART boot log lines.
        callback:  Optional progress callback.

    Returns:
        Populated DeviceIdentification with chipset, brand, model,
        matched database info, common faults, and repair tips.
    """
    result = DeviceIdentification()

    if not log_lines:
        return result

    if callback:
        callback(0.0, "Identifying device from boot log...")

    # --- Phase 1: Extract chipset and brand from log lines ---
    chipset_hits: Dict[str, int] = {}
    pmic_hits: Dict[str, int] = {}
    brands_found: List[str] = []

    total = len(log_lines)
    for idx, line in enumerate(log_lines):
        if callback and idx % 500 == 0:
            callback(idx / total * 0.4, f"Scanning line {idx}/{total} for device ID...")

        # Chipset patterns
        for pattern, fmt in _CHIPSET_LOG_PATTERNS:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                if fmt and "{0}" in fmt:
                    chip_id = fmt.format(m.group(1).upper())
                elif fmt:
                    chip_id = fmt
                else:
                    chip_id = m.group(1).upper()

                if chip_id.startswith("PM") or chip_id.startswith("PMIC"):
                    pmic_clean = chip_id.replace("PMIC_", "")
                    pmic_hits[pmic_clean] = pmic_hits.get(pmic_clean, 0) + 1
                else:
                    chipset_hits[chip_id] = chipset_hits.get(chip_id, 0) + 1

        # Brand/device patterns
        for pattern, field_name in _BRAND_LOG_PATTERNS:
            m = re.search(pattern, line)
            if m:
                if field_name == "brand" and m.group(1):
                    result.brand = m.group(1).strip().lower()
                elif field_name == "model" and m.group(1):
                    result.model = m.group(1).strip()
                elif field_name == "codename" and m.group(1):
                    result.codename = m.group(1).strip().lower()
                elif field_name == "board" and m.group(1):
                    result.board = m.group(1).strip()
                elif field_name == "hardware" and m.group(1):
                    result.hardware = m.group(1).strip()
                elif field_name == "firmware" and m.group(1):
                    result.firmware = m.group(1).strip()
                elif field_name.startswith("brand:"):
                    brand = field_name.split(":")[1]
                    if brand not in brands_found:
                        brands_found.append(brand)

    if callback:
        callback(0.4, "Chipset scan complete, matching database...")

    # --- Determine best chipset match ---
    if chipset_hits:
        # Sort by frequency, pick most common
        sorted_chips = sorted(chipset_hits.items(), key=lambda x: -x[1])
        result.chipset = sorted_chips[0][0]
        result.confidence = min(1.0, sorted_chips[0][1] / 10.0)

    if pmic_hits:
        sorted_pmics = sorted(pmic_hits.items(), key=lambda x: -x[1])
        result.pmic = sorted_pmics[0][0]

    if not result.brand and brands_found:
        result.brand = brands_found[0]

    # --- Phase 2: Match against phone_database.json ---
    if callback:
        callback(0.5, "Looking up phone database...")

    _match_phone_database(result)

    # --- Phase 3: Match against chipset_ic_database.json ---
    if callback:
        callback(0.7, "Looking up chipset IC database...")

    _match_chipset_database(result)

    # --- Phase 4: Build repair tips ---
    if callback:
        callback(0.9, "Building repair recommendations...")

    _build_repair_tips(result)

    result.confidence = max(result.confidence, 0.3 if result.chipset else 0.0)
    if result.db_match:
        result.confidence = max(result.confidence, 0.85)

    if callback:
        callback(1.0, f"Device identified: {result.chipset_name or result.chipset} "
                       f"({result.brand} {result.model or result.db_device_name})")

    return result


def _match_phone_database(result: DeviceIdentification) -> None:
    """Look up the identified chipset/codename in phone_database.json."""
    from pathlib import Path

    db_path = Path(__file__).parent.parent.parent / "config" / "phone_database.json"
    if not db_path.exists():
        return

    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return

    devices = db.get("devices", {})
    chipset_upper = result.chipset.upper() if result.chipset else ""
    codename_lower = result.codename.lower() if result.codename else ""
    brand_lower = result.brand.lower() if result.brand else ""

    best_match = None
    best_brand = ""
    best_name = ""

    for brand_key, models in devices.items():
        for model_name, info in models.items():
            # Match by codename first (most accurate)
            db_codename = info.get("codename", "").lower()
            if codename_lower and db_codename and codename_lower == db_codename:
                best_match = info
                best_brand = brand_key
                best_name = model_name
                break

            # Match by chipset + brand
            db_chipset = info.get("chipset", "").upper()
            if chipset_upper and db_chipset == chipset_upper:
                # If brand also matches, strong match
                if brand_lower and brand_lower in brand_key.lower():
                    best_match = info
                    best_brand = brand_key
                    best_name = model_name
                    break
                # Chipset match without brand — weaker but still useful
                if not best_match:
                    best_match = info
                    best_brand = brand_key
                    best_name = model_name

        if best_match and best_brand and brand_lower in best_brand.lower():
            break  # Found exact brand+chipset match

    if best_match:
        result.db_match = True
        result.db_brand = best_brand
        result.db_device_name = best_name
        result.db_info = best_match
        result.chipset_name = best_match.get("chipset_name", result.chipset_name)
        result.common_faults = best_match.get("common_faults", [])

        if not result.brand:
            result.brand = best_brand.split("_")[0]
        if not result.model:
            result.model = best_name

    # Also check brand-specific tools
    brand_tools = db.get("brand_specific_tools", {})
    for tool_brand, tool_info in brand_tools.items():
        if brand_lower and brand_lower in tool_brand.lower():
            result.repair_tips.append(f"Flash tool: {tool_info.get('flash_tool', 'N/A')}")
            if tool_info.get("frp_bypass_notes"):
                result.repair_tips.append(f"FRP: {tool_info['frp_bypass_notes']}")
            break

    # Check EDL test points
    edl_points = db.get("edl_test_points", {})
    for tp_brand, tp_info in edl_points.items():
        if brand_lower and brand_lower in tp_brand.lower():
            if isinstance(tp_info, dict):
                for tp_model, tp_desc in tp_info.items():
                    if isinstance(tp_desc, str):
                        model_lower = result.model.lower() if result.model else ""
                        if model_lower and tp_model.lower() in model_lower:
                            result.repair_tips.append(f"EDL test point: {tp_desc}")
                            break
                        elif tp_model == "general":
                            result.repair_tips.append(f"EDL (general): {tp_desc}")
            break


def _match_chipset_database(result: DeviceIdentification) -> None:
    """Look up chipset in chipset_ic_database.json for IC details."""
    from pathlib import Path

    db_path = Path(__file__).parent.parent.parent / "config" / "chipset_ic_database.json"
    if not db_path.exists():
        return

    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return

    chipset = result.chipset
    if not chipset:
        return

    # Search in all vendor sections
    for vendor in ("mediatek", "qualcomm", "samsung_exynos", "unisoc"):
        vendor_data = db.get(vendor, {})
        if chipset in vendor_data:
            info = vendor_data[chipset]
            result.chipset_info = info
            if not result.chipset_name:
                result.chipset_name = info.get("marketing_name", chipset)
            if not result.pmic:
                result.pmic = info.get("pmic", "")

            # Extract companion ICs
            companions = info.get("companion_ics", {})
            for ic_name, ic_info in companions.items():
                if isinstance(ic_info, dict):
                    result.related_ics[ic_name] = ic_info.get("function", "")
                else:
                    result.related_ics[ic_name] = str(ic_info)

            # Check known faults from chipset database
            known_faults = info.get("known_faults", {})
            for fault_id, fault_info in known_faults.items():
                if isinstance(fault_info, dict):
                    symptom = fault_info.get("symptom", "")
                    if symptom:
                        result.common_faults.append(f"[Chipset] {symptom}")
                    repair_steps = fault_info.get("repair_steps", [])
                    for step in repair_steps:
                        result.repair_tips.append(step)
            return

    # Try matching PMIC to find chipset indirectly
    common_ics = db.get("common_ics", {})
    pmic_data = common_ics.get("pmic", {})
    if result.pmic and result.pmic in pmic_data:
        pmic_info = pmic_data[result.pmic]
        used_with = pmic_info.get("used_with", [])
        if used_with:
            for chip in used_with:
                for vendor in ("mediatek", "qualcomm", "samsung_exynos", "unisoc"):
                    vendor_data = db.get(vendor, {})
                    if chip in vendor_data:
                        result.chipset = chip
                        result.chipset_info = vendor_data[chip]
                        result.chipset_name = vendor_data[chip].get("marketing_name", chip)
                        result.repair_tips.append(
                            f"Chipset identified via PMIC {result.pmic} → {chip}"
                        )
                        return


def _build_repair_tips(result: DeviceIdentification) -> None:
    """Add context-aware repair tips based on identified device."""
    if result.db_info:
        info = result.db_info
        if info.get("charging_speed"):
            result.repair_tips.append(f"Charging: {info['charging_speed']}")
        if info.get("battery"):
            result.repair_tips.append(f"Battery: {info['battery']}")
        if info.get("display"):
            result.repair_tips.append(f"Display: {info['display']}")
        if info.get("test_point"):
            result.repair_tips.append(f"Test point: {info['test_point']}")
        if info.get("fastboot_key"):
            result.repair_tips.append(f"Fastboot key: {info['fastboot_key']}")
        if info.get("recovery_key"):
            result.repair_tips.append(f"Recovery key: {info['recovery_key']}")

    if result.chipset_info:
        info = result.chipset_info
        if info.get("pmic"):
            result.repair_tips.append(f"PMIC: {info['pmic']}")
        if info.get("charger_ic"):
            result.repair_tips.append(f"Charger IC: {info['charger_ic']}")
        if info.get("wifi_bt"):
            result.repair_tips.append(f"WiFi/BT: {info['wifi_bt']}")
        if info.get("audio_codec"):
            result.repair_tips.append(f"Audio codec: {info['audio_codec']}")


def format_device_identification(result: DeviceIdentification) -> str:
    """Format DeviceIdentification into a human-readable report."""
    lines: List[str] = []
    lines.append("=" * 65)
    lines.append("  DEVICE IDENTIFICATION FROM UART BOOT LOG")
    lines.append("=" * 65)

    if not result.chipset and not result.brand:
        lines.append("  No device identified from boot log.")
        lines.append("  Ensure UART TX/RX/GND are properly connected.")
        lines.append("=" * 65)
        return "\n".join(lines)

    lines.append(f"  Chipset:       {result.chipset}")
    lines.append(f"  Chipset Name:  {result.chipset_name or 'Unknown'}")
    lines.append(f"  Brand:         {result.brand or 'Unknown'}")
    lines.append(f"  Model:         {result.model or result.db_device_name or 'Unknown'}")
    lines.append(f"  Codename:      {result.codename or 'N/A'}")
    lines.append(f"  PMIC:          {result.pmic or 'N/A'}")
    lines.append(f"  Board:         {result.board or 'N/A'}")
    lines.append(f"  Firmware:      {result.firmware or 'N/A'}")
    lines.append(f"  Confidence:    {result.confidence:.0%}")
    lines.append(f"  DB Match:      {'Yes' if result.db_match else 'No'}")

    if result.db_match:
        lines.append("")
        lines.append("-" * 65)
        lines.append("  MATCHED DEVICE INFO")
        lines.append("-" * 65)
        lines.append(f"  Device:        {result.db_device_name}")
        info = result.db_info
        if info.get("display"):
            lines.append(f"  Display:       {info['display']}")
        if info.get("battery"):
            lines.append(f"  Battery:       {info['battery']}")
        if info.get("charging_speed"):
            lines.append(f"  Charging:      {info['charging_speed']}")

    if result.related_ics:
        lines.append("")
        lines.append("-" * 65)
        lines.append("  COMPANION ICs")
        lines.append("-" * 65)
        for ic, func in result.related_ics.items():
            lines.append(f"  {ic:16s} {func}")

    if result.common_faults:
        lines.append("")
        lines.append("-" * 65)
        lines.append("  COMMON FAULTS")
        lines.append("-" * 65)
        for fault in result.common_faults:
            lines.append(f"  - {fault}")

    if result.repair_tips:
        lines.append("")
        lines.append("-" * 65)
        lines.append("  REPAIR TIPS")
        lines.append("-" * 65)
        for tip in result.repair_tips:
            lines.append(f"  - {tip}")

    lines.append("")
    lines.append("=" * 65)
    return "\n".join(lines)
