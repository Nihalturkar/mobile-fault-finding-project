"""
Power / Voltage Testing Module for Mobile Repair Technicians.

Reads PMIC registers, buck/LDO regulator states, power-rail voltages,
and performs short-circuit analysis on Android devices via ADB shell
commands.  All sysfs paths are probed non-destructively (read-only);
root/su is attempted but gracefully degraded when unavailable.

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
          Root access recommended for full SPMI register visibility.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ADB_CMD = "adb"
ADB_TIMEOUT = 10  # seconds per shell command

# SPMI debug paths (require root / debugfs mounted)
SPMI_DEBUG_BASE = "/sys/kernel/debug/spmi"
SPMI_BUS_BASE = "/sys/bus/spmi/devices"
REGULATOR_CLASS_PATH = "/sys/class/regulator"
REGULATOR_DEBUG_PATH = "/sys/kernel/debug/regulator"
POWER_SUPPLY_PATH = "/sys/class/power_supply"
THERMAL_ZONE_PATH = "/sys/class/thermal"

# Voltage tolerance percentage for short-circuit analysis
VOLTAGE_TOLERANCE_PCT = 15.0
# Resistance below this (ohms) is considered a short
SHORT_CIRCUIT_RESISTANCE_THRESHOLD = 1.0
# Current above this (mA) on a single rail is suspicious
OVERCURRENT_THRESHOLD_MA = 2500.0

# ---------------------------------------------------------------------------
# Known PMIC models and expected register maps (all vendors)
# ---------------------------------------------------------------------------

PMIC_DATABASE: Dict[str, Dict[str, Any]] = {
    "PM8998": {
        "manufacturer": "Qualcomm",
        "description": "Primary PMIC for Snapdragon 845",
        "compatible_chipsets": ["SDM845"],
        "num_bucks": 13,
        "num_ldos": 28,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x03,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),  # mV
            "ldo": (312, 3312),
        },
    },
    "PM8150": {
        "manufacturer": "Qualcomm",
        "description": "Primary PMIC for Snapdragon 855",
        "compatible_chipsets": ["SM8150"],
        "num_bucks": 10,
        "num_ldos": 18,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x02,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM8150A": {
        "manufacturer": "Qualcomm",
        "description": "Secondary PMIC for Snapdragon 855",
        "compatible_chipsets": ["SM8150"],
        "num_bucks": 8,
        "num_ldos": 11,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x02,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM8150L": {
        "manufacturer": "Qualcomm",
        "description": "Tertiary PMIC for Snapdragon 855",
        "compatible_chipsets": ["SM8150"],
        "num_bucks": 6,
        "num_ldos": 11,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x02,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM8350": {
        "manufacturer": "Qualcomm",
        "description": "Primary PMIC for Snapdragon 888 / 8 Gen 1",
        "compatible_chipsets": ["SM8350", "SM8450"],
        "num_bucks": 10,
        "num_ldos": 7,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 3544),
        },
    },
    "PM8350C": {
        "manufacturer": "Qualcomm",
        "description": "Companion PMIC for Snapdragon 888",
        "compatible_chipsets": ["SM8350", "SM8450"],
        "num_bucks": 10,
        "num_ldos": 12,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 3544),
        },
    },
    "PMK8350": {
        "manufacturer": "Qualcomm",
        "description": "Always-on PMIC for Snapdragon 888 / 8 Gen 1",
        "compatible_chipsets": ["SM8350", "SM8450"],
        "num_bucks": 0,
        "num_ldos": 0,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x0000",
        "ldo_base": "0x0000",
        "voltage_ranges": {
            "smps": (0, 0),
            "ldo": (0, 0),
        },
    },
    "PMR735A": {
        "manufacturer": "Qualcomm",
        "description": "Auxiliary PMIC for Snapdragon 888 / 8 Gen 1",
        "compatible_chipsets": ["SM8350", "SM8450"],
        "num_bucks": 4,
        "num_ldos": 3,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 880),
        },
    },
    "PMR735B": {
        "manufacturer": "Qualcomm",
        "description": "Auxiliary PMIC for Snapdragon 8 Gen 1 / Gen 2",
        "compatible_chipsets": ["SM8450", "SM8550"],
        "num_bucks": 4,
        "num_ldos": 3,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x02,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 880),
        },
    },
    "PM7250": {
        "manufacturer": "Qualcomm",
        "description": "Primary PMIC for Snapdragon 765 / 7-series",
        "compatible_chipsets": ["SM7250", "SM7325"],
        "num_bucks": 8,
        "num_ldos": 19,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM7250B": {
        "manufacturer": "Qualcomm",
        "description": "Secondary PMIC for Snapdragon 765",
        "compatible_chipsets": ["SM7250"],
        "num_bucks": 6,
        "num_ldos": 5,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM6150": {
        "manufacturer": "Qualcomm",
        "description": "PMIC for Snapdragon 730 / 6-series",
        "compatible_chipsets": ["SM7150", "SM6350"],
        "num_bucks": 6,
        "num_ldos": 19,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM6150L": {
        "manufacturer": "Qualcomm",
        "description": "Secondary PMIC for Snapdragon 730",
        "compatible_chipsets": ["SM7150", "SM6350"],
        "num_bucks": 5,
        "num_ldos": 11,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM6125": {
        "manufacturer": "Qualcomm",
        "description": "PMIC for Snapdragon 662 / 4-series",
        "compatible_chipsets": ["SM6115", "SM4250"],
        "num_bucks": 5,
        "num_ldos": 22,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (320, 1352),
            "ldo": (312, 3312),
        },
    },
    "PM8550": {
        "manufacturer": "Qualcomm",
        "description": "Primary PMIC for Snapdragon 8 Gen 2",
        "compatible_chipsets": ["SM8550"],
        "num_bucks": 12,
        "num_ldos": 8,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 3544),
        },
    },
    "PM8550VS": {
        "manufacturer": "Qualcomm",
        "description": "Companion PMIC for Snapdragon 8 Gen 2",
        "compatible_chipsets": ["SM8550"],
        "num_bucks": 6,
        "num_ldos": 3,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 880),
        },
    },
    "PM8550VE": {
        "manufacturer": "Qualcomm",
        "description": "Extended companion PMIC for Snapdragon 8 Gen 2",
        "compatible_chipsets": ["SM8550"],
        "num_bucks": 6,
        "num_ldos": 3,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 880),
        },
    },
    "PMK8550": {
        "manufacturer": "Qualcomm",
        "description": "Always-on PMIC for Snapdragon 8 Gen 2 / 8 Gen 3",
        "compatible_chipsets": ["SM8550", "SM8650"],
        "num_bucks": 0,
        "num_ldos": 0,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x0000",
        "ldo_base": "0x0000",
        "voltage_ranges": {
            "smps": (0, 0),
            "ldo": (0, 0),
        },
    },
    "PM8650": {
        "manufacturer": "Qualcomm",
        "description": "Primary PMIC for Snapdragon 8 Gen 3",
        "compatible_chipsets": ["SM8650"],
        "num_bucks": 12,
        "num_ldos": 8,
        "die_revision_reg": "0x0101",
        "subtype_reg": "0x0105",
        "expected_revid": 0x01,
        "smps_base": "0x1400",
        "ldo_base": "0x4000",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (312, 3544),
        },
    },
    # --- Samsung Exynos PMICs ---
    "S2MPS25": {
        "manufacturer": "Samsung LSI",
        "description": "Samsung S2MPS25 PMIC for Exynos 2400",
        "compatible_chipsets": ["EXYNOS2400"],
        "num_bucks": 12,
        "num_ldos": 25,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1400),
            "ldo": (700, 3300),
        },
    },
    "S2MPS23": {
        "manufacturer": "Samsung LSI",
        "description": "Samsung S2MPS23 PMIC for Exynos 2200",
        "compatible_chipsets": ["EXYNOS2200"],
        "num_bucks": 10,
        "num_ldos": 22,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1350),
            "ldo": (700, 3300),
        },
    },
    "S2MPA01": {
        "manufacturer": "Samsung LSI",
        "description": "Samsung S2MPA01 PMIC for older Exynos",
        "compatible_chipsets": ["EXYNOS1380", "EXYNOS1080"],
        "num_bucks": 8,
        "num_ldos": 18,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1300),
            "ldo": (800, 3300),
        },
    },
    # --- Unisoc PMICs ---
    "SC2730": {
        "manufacturer": "Unisoc",
        "description": "Unisoc SC2730 integrated PMIC (T820/T760)",
        "compatible_chipsets": ["T820", "T760"],
        "num_bucks": 6,
        "num_ldos": 16,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1300),
            "ldo": (600, 3300),
        },
    },
    "SC2721": {
        "manufacturer": "Unisoc",
        "description": "Unisoc SC2721 integrated PMIC (T616/T612)",
        "compatible_chipsets": ["T616", "T612"],
        "num_bucks": 5,
        "num_ldos": 14,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1200),
            "ldo": (600, 3300),
        },
    },
    # --- HiSilicon Kirin PMICs ---
    "Hi6421": {
        "manufacturer": "HiSilicon",
        "description": "HiSilicon Hi6421 PMIC for Kirin 9000/990",
        "compatible_chipsets": ["KIRIN9000", "KIRIN990"],
        "num_bucks": 8,
        "num_ldos": 24,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1300),
            "ldo": (700, 3300),
        },
    },
    "Hi6422": {
        "manufacturer": "HiSilicon",
        "description": "HiSilicon Hi6422 PMIC for Kirin 990/810",
        "compatible_chipsets": ["KIRIN990", "KIRIN810"],
        "num_bucks": 7,
        "num_ldos": 20,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1300),
            "ldo": (700, 3300),
        },
    },
    "Hi6555": {
        "manufacturer": "HiSilicon",
        "description": "HiSilicon Hi6555 PMIC for Kirin 810/mid-range",
        "compatible_chipsets": ["KIRIN810"],
        "num_bucks": 5,
        "num_ldos": 16,
        "die_revision_reg": "0x00",
        "subtype_reg": "0x01",
        "expected_revid": 0x01,
        "smps_base": "0x0100",
        "ldo_base": "0x0200",
        "voltage_ranges": {
            "smps": (300, 1200),
            "ldo": (700, 3300),
        },
    },
}

# ---------------------------------------------------------------------------
# Known power-rail configurations per chipset platform (all vendors)
# ---------------------------------------------------------------------------

CHIPSET_POWER_RAILS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "SDM845": {
        "VDD_CX": {
            "description": "Logic / CPU complex supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 800,
            "regulator": "pm8998_s9",
        },
        "VDD_MX": {
            "description": "Memory array supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 400,
            "regulator": "pm8998_s6",
        },
        "VDD_GFX": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1050,
            "typical_current_ma": 1200,
            "regulator": "pm8998_s5",
        },
        "VDD_MSS": {
            "description": "Modem subsystem supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 300,
            "regulator": "pm8998_s7",
        },
        "VDD_EBI": {
            "description": "External bus interface (LPDDR)",
            "expected_voltage_mv": 1100,
            "min_voltage_mv": 900,
            "max_voltage_mv": 1300,
            "typical_current_ma": 600,
            "regulator": "pm8998_s3",
        },
        "VDD_LPI_CX": {
            "description": "Low-power island CX",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 50,
            "regulator": "pm8998_l26",
        },
        "VDD_LPI_MX": {
            "description": "Low-power island MX",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 50,
            "regulator": "pm8998_l8",
        },
    },
    "SM8150": {
        "VDD_CX": {
            "description": "Logic / CPU complex supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 900,
            "regulator": "pm8150_s5",
        },
        "VDD_MX": {
            "description": "Memory array supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 500,
            "regulator": "pm8150_s4",
        },
        "VDD_GFX": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 400,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1400,
            "regulator": "pm8150_s8",
        },
        "VDD_MMCX": {
            "description": "Multimedia CX supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 600,
            "regulator": "pm8150a_s6",
        },
        "VDD_MSS": {
            "description": "Modem subsystem supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 350,
            "regulator": "pm8150_s7",
        },
        "VDD_EBI": {
            "description": "External bus interface (LPDDR)",
            "expected_voltage_mv": 1100,
            "min_voltage_mv": 900,
            "max_voltage_mv": 1300,
            "typical_current_ma": 700,
            "regulator": "pm8150_s3",
        },
    },
    "SM8250": {
        "VDD_CX": {
            "description": "Logic / CPU complex supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 1000,
            "regulator": "pm8150_s5",
        },
        "VDD_MX": {
            "description": "Memory array supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 500,
            "regulator": "pm8150_s4",
        },
        "VDD_GFX": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 400,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1600,
            "regulator": "pm8150_s8",
        },
        "VDD_MMCX": {
            "description": "Multimedia CX supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 600,
            "regulator": "pm8150a_s6",
        },
        "VDD_MSS": {
            "description": "Modem subsystem supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 350,
            "regulator": "pm8150_s7",
        },
        "VDD_EBI": {
            "description": "External bus interface (LPDDR)",
            "expected_voltage_mv": 1100,
            "min_voltage_mv": 900,
            "max_voltage_mv": 1300,
            "typical_current_ma": 700,
            "regulator": "pm8150_s3",
        },
    },
    "SM8350": {
        "VDD_CX": {
            "description": "Logic / CPU complex supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 1100,
            "regulator": "pm8350_s9",
        },
        "VDD_MX": {
            "description": "Memory array supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 600,
            "regulator": "pm8350_s6",
        },
        "VDD_GFX": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 400,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1800,
            "regulator": "pm8350c_s2",
        },
        "VDD_MMCX": {
            "description": "Multimedia CX supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 700,
            "regulator": "pm8350c_s4",
        },
        "VDD_MSS": {
            "description": "Modem subsystem supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 400,
            "regulator": "pm8350_s7",
        },
        "VDD_EBI": {
            "description": "External bus interface (LPDDR)",
            "expected_voltage_mv": 1100,
            "min_voltage_mv": 900,
            "max_voltage_mv": 1300,
            "typical_current_ma": 800,
            "regulator": "pm8350_s3",
        },
        "VDD_NSP": {
            "description": "Neural signal processor supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 300,
            "regulator": "pm8350c_s5",
        },
    },
    "SM8450": {
        "VDD_CX": {
            "description": "Logic / CPU complex supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 1200,
            "regulator": "pm8350_s9",
        },
        "VDD_MX": {
            "description": "Memory array supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 600,
            "regulator": "pm8350_s6",
        },
        "VDD_GFX": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 400,
            "max_voltage_mv": 1100,
            "typical_current_ma": 2000,
            "regulator": "pm8350c_s2",
        },
        "VDD_MMCX": {
            "description": "Multimedia CX supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 750,
            "regulator": "pm8350c_s4",
        },
        "VDD_MSS": {
            "description": "Modem subsystem supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 400,
            "regulator": "pm8350_s7",
        },
        "VDD_EBI": {
            "description": "External bus interface (LPDDR5)",
            "expected_voltage_mv": 1100,
            "min_voltage_mv": 900,
            "max_voltage_mv": 1300,
            "typical_current_ma": 900,
            "regulator": "pm8350_s3",
        },
        "VDD_NSP": {
            "description": "Neural signal processor supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 350,
            "regulator": "pm8350c_s5",
        },
    },
    "SM8550": {
        "VDD_CX": {
            "description": "Logic / CPU complex supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 1300,
            "regulator": "pm8550_s9",
        },
        "VDD_MX": {
            "description": "Memory array supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 700,
            "regulator": "pm8550_s6",
        },
        "VDD_GFX": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 400,
            "max_voltage_mv": 1100,
            "typical_current_ma": 2200,
            "regulator": "pm8550vs_s2",
        },
        "VDD_MMCX": {
            "description": "Multimedia CX supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 800,
            "regulator": "pm8550vs_s4",
        },
        "VDD_MSS": {
            "description": "Modem subsystem supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 450,
            "regulator": "pm8550_s7",
        },
        "VDD_EBI": {
            "description": "External bus interface (LPDDR5X)",
            "expected_voltage_mv": 1100,
            "min_voltage_mv": 900,
            "max_voltage_mv": 1300,
            "typical_current_ma": 1000,
            "regulator": "pm8550_s3",
        },
        "VDD_NSP": {
            "description": "Neural signal processor supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 400,
            "regulator": "pm8550vs_s5",
        },
    },
    "SM8650": {
        "VDD_CX": {
            "description": "Logic / CPU complex supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 1400,
            "regulator": "pm8650_s9",
        },
        "VDD_MX": {
            "description": "Memory array supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 750,
            "regulator": "pm8650_s6",
        },
        "VDD_GFX": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 400,
            "max_voltage_mv": 1100,
            "typical_current_ma": 2500,
            "regulator": "pm8650_s2",
        },
        "VDD_MMCX": {
            "description": "Multimedia CX supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 900,
            "regulator": "pm8650_s4",
        },
        "VDD_MSS": {
            "description": "Modem subsystem supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 500,
            "regulator": "pm8650_s7",
        },
        "VDD_EBI": {
            "description": "External bus interface (LPDDR5X)",
            "expected_voltage_mv": 1100,
            "min_voltage_mv": 900,
            "max_voltage_mv": 1300,
            "typical_current_ma": 1100,
            "regulator": "pm8650_s3",
        },
        "VDD_NSP": {
            "description": "Neural signal processor supply",
            "expected_voltage_mv": 752,
            "min_voltage_mv": 500,
            "max_voltage_mv": 952,
            "typical_current_ma": 450,
            "regulator": "pm8650_s5",
        },
    },
    # -----------------------------------------------------------------------
    # MediaTek Dimensity platforms
    # -----------------------------------------------------------------------
    "MT6989": {  # Dimensity 9300
        "VCORE": {
            "description": "CPU core supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 850,
            "typical_current_ma": 1200,
            "regulator": "vcore",
        },
        "VPROC": {
            "description": "Processor supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1500,
            "regulator": "vproc",
        },
        "VGPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 950,
            "typical_current_ma": 1800,
            "regulator": "vgpu",
        },
        "VMODEM": {
            "description": "Modem supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 400,
            "regulator": "vmodem",
        },
        "VSRAM_CORE": {
            "description": "SRAM core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1000,
            "typical_current_ma": 200,
            "regulator": "vsram_core",
        },
        "VSRAM_PROC": {
            "description": "SRAM processor supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1100,
            "typical_current_ma": 200,
            "regulator": "vsram_proc",
        },
        "VIO18": {
            "description": "IO 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 300,
            "regulator": "vio18",
        },
        "VRF": {
            "description": "RF supply",
            "expected_voltage_mv": 1500,
            "min_voltage_mv": 1200,
            "max_voltage_mv": 1800,
            "typical_current_ma": 250,
            "regulator": "vrf",
        },
    },
    "MT6985": {  # Dimensity 9200
        "VCORE": {
            "description": "CPU core supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 850,
            "typical_current_ma": 1100,
            "regulator": "vcore",
        },
        "VPROC": {
            "description": "Processor supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1400,
            "regulator": "vproc",
        },
        "VGPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 950,
            "typical_current_ma": 1600,
            "regulator": "vgpu",
        },
        "VMODEM": {
            "description": "Modem supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 350,
            "regulator": "vmodem",
        },
        "VSRAM_CORE": {
            "description": "SRAM core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1000,
            "typical_current_ma": 180,
            "regulator": "vsram_core",
        },
        "VSRAM_PROC": {
            "description": "SRAM processor supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1100,
            "typical_current_ma": 180,
            "regulator": "vsram_proc",
        },
        "VIO18": {
            "description": "IO 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 300,
            "regulator": "vio18",
        },
        "VRF": {
            "description": "RF supply",
            "expected_voltage_mv": 1500,
            "min_voltage_mv": 1200,
            "max_voltage_mv": 1800,
            "typical_current_ma": 250,
            "regulator": "vrf",
        },
    },
    "MT6897": {  # Dimensity 8300
        "VCORE": {
            "description": "CPU core supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 850,
            "typical_current_ma": 900,
            "regulator": "vcore",
        },
        "VPROC": {
            "description": "Processor supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1100,
            "regulator": "vproc",
        },
        "VGPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 950,
            "typical_current_ma": 1200,
            "regulator": "vgpu",
        },
        "VMODEM": {
            "description": "Modem supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 300,
            "regulator": "vmodem",
        },
        "VSRAM_CORE": {
            "description": "SRAM core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1000,
            "typical_current_ma": 150,
            "regulator": "vsram_core",
        },
        "VSRAM_PROC": {
            "description": "SRAM processor supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1100,
            "typical_current_ma": 150,
            "regulator": "vsram_proc",
        },
        "VIO18": {
            "description": "IO 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 250,
            "regulator": "vio18",
        },
        "VRF": {
            "description": "RF supply",
            "expected_voltage_mv": 1500,
            "min_voltage_mv": 1200,
            "max_voltage_mv": 1800,
            "typical_current_ma": 200,
            "regulator": "vrf",
        },
    },
    "MT6878": {  # Dimensity 7050
        "VCORE": {
            "description": "CPU core supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 850,
            "typical_current_ma": 700,
            "regulator": "vcore",
        },
        "VPROC": {
            "description": "Processor supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 900,
            "regulator": "vproc",
        },
        "VGPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 950,
            "typical_current_ma": 800,
            "regulator": "vgpu",
        },
        "VMODEM": {
            "description": "Modem supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 250,
            "regulator": "vmodem",
        },
        "VSRAM_CORE": {
            "description": "SRAM core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1000,
            "typical_current_ma": 120,
            "regulator": "vsram_core",
        },
        "VSRAM_PROC": {
            "description": "SRAM processor supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1100,
            "typical_current_ma": 120,
            "regulator": "vsram_proc",
        },
        "VIO18": {
            "description": "IO 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 200,
            "regulator": "vio18",
        },
        "VRF": {
            "description": "RF supply",
            "expected_voltage_mv": 1500,
            "min_voltage_mv": 1200,
            "max_voltage_mv": 1800,
            "typical_current_ma": 180,
            "regulator": "vrf",
        },
    },
    "MT6893": {  # Dimensity 1200
        "VCORE": {
            "description": "CPU core supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 850,
            "typical_current_ma": 800,
            "regulator": "vcore",
        },
        "VPROC": {
            "description": "Processor supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1000,
            "regulator": "vproc",
        },
        "VGPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 950,
            "typical_current_ma": 1000,
            "regulator": "vgpu",
        },
        "VMODEM": {
            "description": "Modem supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 300,
            "regulator": "vmodem",
        },
        "VSRAM_CORE": {
            "description": "SRAM core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1000,
            "typical_current_ma": 150,
            "regulator": "vsram_core",
        },
        "VSRAM_PROC": {
            "description": "SRAM processor supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 650,
            "max_voltage_mv": 1100,
            "typical_current_ma": 150,
            "regulator": "vsram_proc",
        },
        "VIO18": {
            "description": "IO 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 250,
            "regulator": "vio18",
        },
        "VRF": {
            "description": "RF supply",
            "expected_voltage_mv": 1500,
            "min_voltage_mv": 1200,
            "max_voltage_mv": 1800,
            "typical_current_ma": 200,
            "regulator": "vrf",
        },
    },
    # -----------------------------------------------------------------------
    # Samsung Exynos platforms
    # -----------------------------------------------------------------------
    "EXYNOS2400": {
        "VDD_CPUCL0": {
            "description": "Little CPU cluster supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1200,
            "typical_current_ma": 600,
            "regulator": "vdd_cpucl0",
        },
        "VDD_CPUCL1": {
            "description": "Big CPU cluster supply",
            "expected_voltage_mv": 900,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1300,
            "typical_current_ma": 1500,
            "regulator": "vdd_cpucl1",
        },
        "VDD_G3D": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 2000,
            "regulator": "vdd_g3d",
        },
        "VDD_MIF": {
            "description": "Memory interface supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 500,
            "regulator": "vdd_mif",
        },
        "VDD_INT": {
            "description": "Internal logic supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 400,
            "regulator": "vdd_int",
        },
        "VDD_CAM": {
            "description": "Camera subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 300,
            "regulator": "vdd_cam",
        },
        "VDD_DISP": {
            "description": "Display subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 350,
            "regulator": "vdd_disp",
        },
    },
    "EXYNOS2200": {
        "VDD_CPUCL0": {
            "description": "Little CPU cluster supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1200,
            "typical_current_ma": 500,
            "regulator": "vdd_cpucl0",
        },
        "VDD_CPUCL1": {
            "description": "Big CPU cluster supply",
            "expected_voltage_mv": 900,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1300,
            "typical_current_ma": 1400,
            "regulator": "vdd_cpucl1",
        },
        "VDD_G3D": {
            "description": "GPU supply (Xclipse 920 / RDNA2)",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 1800,
            "regulator": "vdd_g3d",
        },
        "VDD_MIF": {
            "description": "Memory interface supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 450,
            "regulator": "vdd_mif",
        },
        "VDD_INT": {
            "description": "Internal logic supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 350,
            "regulator": "vdd_int",
        },
        "VDD_CAM": {
            "description": "Camera subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 250,
            "regulator": "vdd_cam",
        },
        "VDD_DISP": {
            "description": "Display subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 300,
            "regulator": "vdd_disp",
        },
    },
    "EXYNOS1380": {
        "VDD_CPUCL0": {
            "description": "Little CPU cluster supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1200,
            "typical_current_ma": 400,
            "regulator": "vdd_cpucl0",
        },
        "VDD_CPUCL1": {
            "description": "Big CPU cluster supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1300,
            "typical_current_ma": 800,
            "regulator": "vdd_cpucl1",
        },
        "VDD_G3D": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 600,
            "regulator": "vdd_g3d",
        },
        "VDD_MIF": {
            "description": "Memory interface supply",
            "expected_voltage_mv": 650,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 300,
            "regulator": "vdd_mif",
        },
        "VDD_INT": {
            "description": "Internal logic supply",
            "expected_voltage_mv": 650,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 250,
            "regulator": "vdd_int",
        },
        "VDD_CAM": {
            "description": "Camera subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 200,
            "regulator": "vdd_cam",
        },
        "VDD_DISP": {
            "description": "Display subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 200,
            "regulator": "vdd_disp",
        },
    },
    "EXYNOS1080": {
        "VDD_CPUCL0": {
            "description": "Little CPU cluster supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1200,
            "typical_current_ma": 400,
            "regulator": "vdd_cpucl0",
        },
        "VDD_CPUCL1": {
            "description": "Big CPU cluster supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1300,
            "typical_current_ma": 800,
            "regulator": "vdd_cpucl1",
        },
        "VDD_G3D": {
            "description": "GPU supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 600,
            "regulator": "vdd_g3d",
        },
        "VDD_MIF": {
            "description": "Memory interface supply",
            "expected_voltage_mv": 650,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 300,
            "regulator": "vdd_mif",
        },
        "VDD_INT": {
            "description": "Internal logic supply",
            "expected_voltage_mv": 650,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 250,
            "regulator": "vdd_int",
        },
        "VDD_CAM": {
            "description": "Camera subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 200,
            "regulator": "vdd_cam",
        },
        "VDD_DISP": {
            "description": "Display subsystem supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 200,
            "regulator": "vdd_disp",
        },
    },
    # -----------------------------------------------------------------------
    # Google Tensor platforms (Samsung-designed)
    # -----------------------------------------------------------------------
    "TENSOR_G4": {
        "VDD_TPU": {
            "description": "TPU (Tensor Processing Unit) supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 600,
            "regulator": "vdd_tpu",
        },
        "VDD_CPUCL0": {
            "description": "Little CPU cluster supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1200,
            "typical_current_ma": 600,
            "regulator": "vdd_cpucl0",
        },
        "VDD_CPUCL1": {
            "description": "Big CPU cluster supply",
            "expected_voltage_mv": 900,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1300,
            "typical_current_ma": 1400,
            "regulator": "vdd_cpucl1",
        },
        "VDD_G3D": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 1800,
            "regulator": "vdd_g3d",
        },
        "VDD_MIF": {
            "description": "Memory interface supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 500,
            "regulator": "vdd_mif",
        },
    },
    "TENSOR_G3": {
        "VDD_TPU": {
            "description": "TPU (Tensor Processing Unit) supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 500,
            "regulator": "vdd_tpu",
        },
        "VDD_CPUCL0": {
            "description": "Little CPU cluster supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1200,
            "typical_current_ma": 500,
            "regulator": "vdd_cpucl0",
        },
        "VDD_CPUCL1": {
            "description": "Big CPU cluster supply",
            "expected_voltage_mv": 900,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1300,
            "typical_current_ma": 1300,
            "regulator": "vdd_cpucl1",
        },
        "VDD_G3D": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 1600,
            "regulator": "vdd_g3d",
        },
        "VDD_MIF": {
            "description": "Memory interface supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 450,
            "regulator": "vdd_mif",
        },
    },
    "TENSOR_G2": {
        "VDD_TPU": {
            "description": "TPU (Tensor Processing Unit) supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1100,
            "typical_current_ma": 450,
            "regulator": "vdd_tpu",
        },
        "VDD_CPUCL0": {
            "description": "Little CPU cluster supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1200,
            "typical_current_ma": 450,
            "regulator": "vdd_cpucl0",
        },
        "VDD_CPUCL1": {
            "description": "Big CPU cluster supply",
            "expected_voltage_mv": 900,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1300,
            "typical_current_ma": 1200,
            "regulator": "vdd_cpucl1",
        },
        "VDD_G3D": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 1400,
            "regulator": "vdd_g3d",
        },
        "VDD_MIF": {
            "description": "Memory interface supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 800,
            "typical_current_ma": 400,
            "regulator": "vdd_mif",
        },
    },
    # -----------------------------------------------------------------------
    # Unisoc platforms
    # -----------------------------------------------------------------------
    "T820": {
        "VDDCORE": {
            "description": "Core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 800,
            "regulator": "vddcore",
        },
        "VDDRF": {
            "description": "RF transceiver supply",
            "expected_voltage_mv": 1200,
            "min_voltage_mv": 1100,
            "max_voltage_mv": 1300,
            "typical_current_ma": 300,
            "regulator": "vddrf",
        },
        "VDDMEM": {
            "description": "Memory supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 600,
            "max_voltage_mv": 800,
            "typical_current_ma": 400,
            "regulator": "vddmem",
        },
        "VDDGEN": {
            "description": "General purpose 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 200,
            "regulator": "vddgen",
        },
    },
    "T760": {
        "VDDCORE": {
            "description": "Core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 700,
            "regulator": "vddcore",
        },
        "VDDRF": {
            "description": "RF transceiver supply",
            "expected_voltage_mv": 1200,
            "min_voltage_mv": 1100,
            "max_voltage_mv": 1300,
            "typical_current_ma": 280,
            "regulator": "vddrf",
        },
        "VDDMEM": {
            "description": "Memory supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 600,
            "max_voltage_mv": 800,
            "typical_current_ma": 350,
            "regulator": "vddmem",
        },
        "VDDGEN": {
            "description": "General purpose 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 180,
            "regulator": "vddgen",
        },
    },
    "T616": {
        "VDDCORE": {
            "description": "Core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 500,
            "regulator": "vddcore",
        },
        "VDDRF": {
            "description": "RF transceiver supply",
            "expected_voltage_mv": 1200,
            "min_voltage_mv": 1100,
            "max_voltage_mv": 1300,
            "typical_current_ma": 200,
            "regulator": "vddrf",
        },
        "VDDMEM": {
            "description": "Memory supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 600,
            "max_voltage_mv": 800,
            "typical_current_ma": 250,
            "regulator": "vddmem",
        },
        "VDDGEN": {
            "description": "General purpose 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 150,
            "regulator": "vddgen",
        },
    },
    "T612": {
        "VDDCORE": {
            "description": "Core supply",
            "expected_voltage_mv": 800,
            "min_voltage_mv": 700,
            "max_voltage_mv": 900,
            "typical_current_ma": 450,
            "regulator": "vddcore",
        },
        "VDDRF": {
            "description": "RF transceiver supply",
            "expected_voltage_mv": 1200,
            "min_voltage_mv": 1100,
            "max_voltage_mv": 1300,
            "typical_current_ma": 180,
            "regulator": "vddrf",
        },
        "VDDMEM": {
            "description": "Memory supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 600,
            "max_voltage_mv": 800,
            "typical_current_ma": 220,
            "regulator": "vddmem",
        },
        "VDDGEN": {
            "description": "General purpose 1.8V supply",
            "expected_voltage_mv": 1800,
            "min_voltage_mv": 1700,
            "max_voltage_mv": 1900,
            "typical_current_ma": 130,
            "regulator": "vddgen",
        },
    },
    # -----------------------------------------------------------------------
    # HiSilicon Kirin platforms
    # -----------------------------------------------------------------------
    "KIRIN9000": {
        "VDD_CPU_BIG": {
            "description": "Big CPU core supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 600,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1500,
            "regulator": "vdd_cpu_big",
        },
        "VDD_CPU_LITTLE": {
            "description": "Little CPU core supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 500,
            "regulator": "vdd_cpu_little",
        },
        "VDD_GPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 1800,
            "regulator": "vdd_gpu",
        },
        "VDD_NPU": {
            "description": "NPU (Neural Processing Unit) supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 600,
            "max_voltage_mv": 900,
            "typical_current_ma": 400,
            "regulator": "vdd_npu",
        },
    },
    "KIRIN990": {
        "VDD_CPU_BIG": {
            "description": "Big CPU core supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 600,
            "max_voltage_mv": 1100,
            "typical_current_ma": 1300,
            "regulator": "vdd_cpu_big",
        },
        "VDD_CPU_LITTLE": {
            "description": "Little CPU core supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 450,
            "regulator": "vdd_cpu_little",
        },
        "VDD_GPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 1500,
            "regulator": "vdd_gpu",
        },
        "VDD_NPU": {
            "description": "NPU (Neural Processing Unit) supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 600,
            "max_voltage_mv": 900,
            "typical_current_ma": 350,
            "regulator": "vdd_npu",
        },
    },
    "KIRIN810": {
        "VDD_CPU_BIG": {
            "description": "Big CPU core supply",
            "expected_voltage_mv": 850,
            "min_voltage_mv": 600,
            "max_voltage_mv": 1100,
            "typical_current_ma": 900,
            "regulator": "vdd_cpu_big",
        },
        "VDD_CPU_LITTLE": {
            "description": "Little CPU core supply",
            "expected_voltage_mv": 700,
            "min_voltage_mv": 500,
            "max_voltage_mv": 900,
            "typical_current_ma": 350,
            "regulator": "vdd_cpu_little",
        },
        "VDD_GPU": {
            "description": "GPU supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 500,
            "max_voltage_mv": 1000,
            "typical_current_ma": 800,
            "regulator": "vdd_gpu",
        },
        "VDD_NPU": {
            "description": "NPU (Neural Processing Unit) supply",
            "expected_voltage_mv": 750,
            "min_voltage_mv": 600,
            "max_voltage_mv": 900,
            "typical_current_ma": 250,
            "regulator": "vdd_npu",
        },
    },
}

# Map friendly chipset names to internal keys
CHIPSET_ALIASES: Dict[str, str] = {
    # Qualcomm Snapdragon
    "Snapdragon 845": "SDM845",
    "Snapdragon 855": "SM8150",
    "Snapdragon 865": "SM8250",
    "Snapdragon 888": "SM8350",
    "Snapdragon 8 Gen 1": "SM8450",
    "Snapdragon 8 Gen 2": "SM8550",
    "Snapdragon 8 Gen 3": "SM8650",
    # MediaTek Dimensity / Helio
    "Dimensity 9300": "MT6989",
    "Dimensity 9200": "MT6985",
    "Dimensity 8300": "MT6897",
    "Dimensity 7050": "MT6878",
    "Dimensity 1200": "MT6893",
    "Dimensity 700": "MT6833",
    "Helio G99": "MT6789",
    "Helio G96": "MT6781",
    # Samsung Exynos
    "Exynos 2400": "EXYNOS2400",
    "Exynos 2200": "EXYNOS2200",
    "Exynos 1380": "EXYNOS1380",
    "Exynos 1080": "EXYNOS1080",
    # Google Tensor
    "Tensor G4": "TENSOR_G4",
    "Tensor G3": "TENSOR_G3",
    "Tensor G2": "TENSOR_G2",
    # HiSilicon Kirin
    "Kirin 9000": "KIRIN9000",
    "Kirin 990": "KIRIN990",
    "Kirin 810": "KIRIN810",
    # Unisoc
    "Unisoc T820": "T820",
    "Unisoc T760": "T760",
    "Unisoc T616": "T616",
    "Unisoc T612": "T612",
}

# ---------------------------------------------------------------------------
# Regulator type classification patterns
# ---------------------------------------------------------------------------

REGULATOR_TYPE_PATTERNS: List[Tuple[str, str]] = [
    # Qualcomm patterns
    (r"(?i)\bsmps\b|_s\d+$", "Buck (SMPS)"),
    (r"(?i)\bbob\b", "Buck-Or-Boost (BOB)"),
    (r"(?i)\bbuck\b", "Buck"),
    (r"(?i)\bldo\b|_l\d+$", "LDO"),
    (r"(?i)\bboost\b", "Boost"),
    (r"(?i)\bvsense\b", "Voltage Sense"),
    # MediaTek patterns — MT6359P, MT6363, MT6368 regulators
    (r"(?i)\bvs\d+\b|VS\d+", "Buck (VS)"),         # MT63xx VS1, VS2 = Buck
    (r"(?i)\bvbuck\b|VBUCK", "Buck"),                # vbuck1, vbuck2
    (r"(?i)\bvm\d+\b|VM\d+", "Buck (VM)"),           # VM18 = buck
    (r"(?i)\bvpa\b|VPA", "Buck (PA)"),               # VPA = power amplifier buck
    (r"(?i)\bvcore\b|VCORE", "Buck (Core)"),         # VCORE = CPU core buck
    (r"(?i)\bvproc\b|VPROC", "Buck (Proc)"),         # VPROC = processor buck
    (r"(?i)\bvgpu\b|VGPU", "Buck (GPU)"),            # VGPU = GPU buck
    (r"(?i)\bvmodem\b|VMODEM", "Buck (Modem)"),      # VMODEM = modem buck
    (r"(?i)\bvsram\b|VSRAM", "LDO (SRAM)"),          # VSRAM = SRAM LDO
    (r"(?i)\bvldo\b|VLDO|VRF|VIBR|VMC|VMCH", "LDO"),  # MT63xx LDOs
    (r"(?i)\bvaud\b|VAUD", "LDO (Audio)"),           # Audio LDO
    (r"(?i)\bvio\b|VIO", "LDO (IO)"),                # IO LDO
    (r"(?i)\bvusb\b|VUSB", "LDO (USB)"),             # USB LDO
    (r"(?i)\bvfe\b|VFE", "LDO (Frontend)"),          # RF frontend LDO
    (r"(?i)\bvcn\b|VCN", "LDO (Connectivity)"),      # WiFi/BT/GPS LDO
    (r"(?i)\bvcama\b|VCAMA", "LDO (Camera A)"),      # Camera analog LDO
    (r"(?i)\bvcamd\b|VCAMD", "LDO (Camera D)"),      # Camera digital LDO
    # Voltage-based classification (fallback)
    (r"(?i)regulator\.\d+", "Regulator"),             # Generic regulator.N
]

# MediaTek PMIC database
MEDIATEK_PMIC_DATABASE: Dict[str, Dict[str, Any]] = {
    "MT6359P": {
        "description": "MediaTek MT6359P PMIC (Dimensity 700/800/900 series)",
        "manufacturer": "MediaTek",
        "num_bucks": 8,
        "num_ldos": 18,
    },
    "MT6363": {
        "description": "MediaTek MT6363 PMIC (Dimensity 7000/8000/9000 series)",
        "manufacturer": "MediaTek",
        "num_bucks": 10,
        "num_ldos": 16,
    },
    "MT6368": {
        "description": "MediaTek MT6368 companion PMIC",
        "manufacturer": "MediaTek",
        "num_bucks": 4,
        "num_ldos": 8,
    },
    "MT6369": {
        "description": "MediaTek MT6369 companion PMIC",
        "manufacturer": "MediaTek",
        "num_bucks": 3,
        "num_ldos": 10,
    },
    "MT6358": {
        "description": "MediaTek MT6358 PMIC (Helio G series)",
        "manufacturer": "MediaTek",
        "num_bucks": 6,
        "num_ldos": 16,
    },
    "MT6357": {
        "description": "MediaTek MT6357 PMIC (Helio A/P series)",
        "manufacturer": "MediaTek",
        "num_bucks": 4,
        "num_ldos": 14,
    },
    "MT6366": {
        "description": "MediaTek MT6366 PMIC (Dimensity 700/720)",
        "manufacturer": "MediaTek",
        "num_bucks": 8,
        "num_ldos": 16,
    },
}

# MediaTek PMIC sysfs paths
MTK_PMIC_PATHS = [
    "/sys/devices/platform/pmic_wrapper",
    "/sys/devices/platform/mt-pmic",
    "/sys/devices/platform/mt6359p-regulator",
    "/sys/devices/platform/mt6363-regulator",
    "/proc/device-tree/pmic",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RegulatorInfo:
    """Information about a single voltage regulator."""
    name: str = ""
    regulator_type: str = ""  # Buck, LDO, Boost, etc.
    voltage_mv: float = 0.0
    status: str = "unknown"  # enabled, disabled, unknown
    min_uv: int = 0
    max_uv: int = 0
    microvolts: int = 0
    num_users: int = 0
    state: str = ""
    suspend_state: str = ""


@dataclass
class PowerRailInfo:
    """Information about a power rail."""
    name: str = ""
    voltage_mv: float = 0.0
    status: str = "unknown"  # OK, LOW, HIGH, OFF, UNKNOWN
    current_ma: float = 0.0
    expected_voltage_mv: float = 0.0
    description: str = ""
    regulator_name: str = ""


@dataclass
class ShortCircuitResult:
    """Result of short-circuit analysis on a power rail."""
    rail_name: str = ""
    status: str = "UNKNOWN"  # OK, SHORT, LEAKY, OPEN, UNKNOWN
    resistance_ohm: float = -1.0
    verdict: str = ""
    voltage_drop_mv: float = 0.0
    measured_current_ma: float = 0.0


@dataclass
class PowerTestResult:
    """Complete result from power/voltage testing."""

    # Connection state
    connected: bool = False
    error: Optional[str] = None

    # PMIC information
    pmic_info: Dict[str, Any] = field(default_factory=dict)

    # Regulator readings
    regulators: List[RegulatorInfo] = field(default_factory=list)

    # Power rail status
    power_rails: List[PowerRailInfo] = field(default_factory=list)

    # Short circuit analysis
    short_circuit_results: List[ShortCircuitResult] = field(default_factory=list)

    # Thermal / power consumption
    thermal_power: Dict[str, Any] = field(default_factory=dict)

    # Overall assessment
    overall_health: str = "UNKNOWN"

    # Detection metadata
    log: List[str] = field(default_factory=list)
    detection_duration_s: float = 0.0


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------


def _adb_shell(cmd: str, timeout: int = ADB_TIMEOUT) -> Tuple[bool, str]:
    """
    Run ``adb shell <cmd>`` and return (success, output).

    Returns (False, error_message) on any failure.
    """
    full_cmd = [ADB_CMD, "shell", cmd]
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = proc.stdout.strip()
        if proc.returncode != 0:
            err = proc.stderr.strip() or output
            return False, err
        return True, output
    except FileNotFoundError:
        return False, "adb not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"adb shell timed out after {timeout}s"
    except Exception as exc:
        return False, f"adb error: {type(exc).__name__}: {exc}"


def _adb_shell_root(cmd: str, timeout: int = ADB_TIMEOUT) -> Tuple[bool, str]:
    """
    Try command with root first (su -c), fall back to normal shell.
    """
    ok, out = _adb_shell(f"su -c '{cmd}'", timeout=timeout)
    if ok and "not found" not in out.lower() and "permission denied" not in out.lower():
        return True, out
    # Fallback without root
    return _adb_shell(cmd, timeout=timeout)


def _adb_check_connection() -> Tuple[bool, str]:
    """Check if an ADB device is connected and authorised."""
    try:
        proc = subprocess.run(
            [ADB_CMD, "devices"],
            capture_output=True,
            text=True,
            timeout=ADB_TIMEOUT,
        )
        output = proc.stdout.strip()
        for line in output.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                serial, state = parts[0], parts[1]
                if state == "device":
                    return True, serial
                if state == "unauthorized":
                    return False, f"Device {serial} unauthorized - accept USB debugging prompt"
        return False, "No ADB device connected"
    except FileNotFoundError:
        return False, "adb not found on PATH"
    except Exception as exc:
        return False, f"ADB check failed: {exc}"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_microvolts(raw: str) -> int:
    """Parse a sysfs microvolts string, return 0 on failure."""
    raw = raw.strip()
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def _uv_to_mv(uv: int) -> float:
    """Convert microvolts to millivolts."""
    return uv / 1000.0


def _classify_regulator_type(name: str) -> str:
    """Determine regulator type (Buck/LDO/etc.) from its name."""
    for pattern, rtype in REGULATOR_TYPE_PATTERNS:
        if re.search(pattern, name):
            return rtype
    return "Unknown"


def _match_chipset(platform_str: str) -> Optional[str]:
    """
    Attempt to match a platform/hardware string to a known chipset key.
    Returns the key into CHIPSET_POWER_RAILS or None.
    """
    upper = platform_str.upper()
    # Direct match
    if upper in CHIPSET_POWER_RAILS:
        return upper
    # Strip vendor prefixes (Qualcomm, MediaTek, Samsung, etc.)
    for key in CHIPSET_POWER_RAILS:
        if key in upper:
            return key
    # Alias lookup (friendly names -> internal keys)
    for alias, key in CHIPSET_ALIASES.items():
        if alias.upper() in upper:
            return key
    return None


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------


def _step_check_adb(result: PowerTestResult, log_fn: Callable, progress_fn: Callable) -> bool:
    """Step 1: verify ADB connectivity. Returns True if connected."""
    progress_fn(0.02, "Checking ADB connection...")
    log_fn("[1/6] Checking ADB connection...")

    connected, info = _adb_check_connection()
    if not connected:
        log_fn(f"  FAIL: {info}")
        result.connected = False
        result.error = info
        result.overall_health = "NO CONNECTION"
        return False

    result.connected = True
    log_fn(f"  OK: device {info} connected")

    # Grab platform info for chipset matching
    ok, platform = _adb_shell("getprop ro.board.platform")
    if ok and platform:
        result.pmic_info["platform"] = platform
        log_fn(f"  Platform: {platform}")
    ok, hardware = _adb_shell("getprop ro.hardware")
    if ok and hardware:
        result.pmic_info["hardware"] = hardware
        log_fn(f"  Hardware: {hardware}")
    ok, chipset = _adb_shell("getprop ro.hardware.chipname")
    if ok and chipset:
        result.pmic_info["chipname"] = chipset
        log_fn(f"  Chipset name: {chipset}")

    return True


def _step_read_pmic(result: PowerTestResult, log_fn: Callable, progress_fn: Callable) -> None:
    """Step 2: read PMIC information via SPMI debug / bus sysfs."""
    progress_fn(0.10, "Reading PMIC registers via SPMI...")
    log_fn("")
    log_fn("[2/6] Reading PMIC information...")

    pmic_info = result.pmic_info
    pmic_info.setdefault("version", "unknown")
    pmic_info.setdefault("manufacturer", "unknown")
    pmic_info.setdefault("bus_status", "unknown")
    pmic_info.setdefault("registers", {})
    pmic_info.setdefault("detected_pmics", [])

    # --- Try SPMI debugfs ---
    ok, spmi_listing = _adb_shell_root(f"ls {SPMI_DEBUG_BASE}/")
    if ok and spmi_listing and "No such file" not in spmi_listing:
        log_fn(f"  SPMI debug available: {spmi_listing.replace(chr(10), ', ')}")
        pmic_info["bus_status"] = "accessible"

        # Enumerate each SPMI controller (spmi-0, spmi-1, ...)
        for controller in spmi_listing.split():
            controller = controller.strip()
            if not controller:
                continue
            ctrl_path = f"{SPMI_DEBUG_BASE}/{controller}"

            # Read the address file to enumerate register addresses
            ok_addr, addr_data = _adb_shell_root(f"cat {ctrl_path}/address")
            if ok_addr and addr_data:
                pmic_info["registers"][controller] = {
                    "address_raw": addr_data[:500],  # truncate for sanity
                }
                log_fn(f"  {controller}: address register read OK ({len(addr_data)} bytes)")

            # Read the data file for register content
            ok_data, data_val = _adb_shell_root(f"cat {ctrl_path}/data")
            if ok_data and data_val:
                pmic_info["registers"].setdefault(controller, {})["data_raw"] = data_val[:500]
                log_fn(f"  {controller}: data register read OK ({len(data_val)} bytes)")
    else:
        log_fn("  SPMI debugfs not available (requires root + debugfs mounted)")

    # --- Try SPMI bus devices ---
    ok, bus_listing = _adb_shell(f"ls {SPMI_BUS_BASE}/")
    if ok and bus_listing and "No such file" not in bus_listing:
        for dev in bus_listing.split():
            dev = dev.strip()
            if not dev:
                continue
            dev_path = f"{SPMI_BUS_BASE}/{dev}"
            ok_compat, compat = _adb_shell(f"cat {dev_path}/of_node/compatible 2>/dev/null")
            if ok_compat and compat:
                log_fn(f"  SPMI device {dev}: compatible = {compat}")
                pmic_info["detected_pmics"].append({
                    "bus_id": dev,
                    "compatible": compat,
                })
    else:
        log_fn("  SPMI bus listing not available")

    # --- Try regulator debugfs for PMIC identification ---
    ok, reg_debug = _adb_shell_root(f"ls {REGULATOR_DEBUG_PATH}/")
    if ok and reg_debug and "No such file" not in reg_debug:
        pmic_names_seen: set = set()
        for entry in reg_debug.split():
            entry = entry.strip()
            if not entry:
                continue
            # Qualcomm: pm8350_s1 -> PM8350
            m = re.match(r"(pm\w+?)_", entry, re.IGNORECASE)
            if m:
                pmic_names_seen.add(m.group(1).upper())
            # Samsung Exynos: s2mps25_buck1 -> S2MPS25
            m_sam = re.match(r"(s2mp[a-z]+\d+)", entry, re.IGNORECASE)
            if m_sam:
                pmic_names_seen.add(m_sam.group(1).upper())
            # MediaTek: mt6359p_vcore -> MT6359P
            m_mtk = re.match(r"(mt\d{4}[a-z]?)[-_]", entry, re.IGNORECASE)
            if m_mtk:
                pmic_names_seen.add(m_mtk.group(1).upper())
            # HiSilicon: hi6421_ldo1 -> Hi6421
            m_hi = re.match(r"(hi\d{4})", entry, re.IGNORECASE)
            if m_hi:
                pmic_names_seen.add(m_hi.group(1).upper().replace("HI", "Hi"))
            # Unisoc: sc2730_buck1 -> SC2730
            m_sc = re.match(r"(sc\d{4})", entry, re.IGNORECASE)
            if m_sc:
                pmic_names_seen.add(m_sc.group(1).upper())
        for pmic_name in sorted(pmic_names_seen):
            # Check both main and MediaTek PMIC databases
            db_entry = PMIC_DATABASE.get(pmic_name) or MEDIATEK_PMIC_DATABASE.get(pmic_name)
            if db_entry:
                log_fn(f"  Identified PMIC: {pmic_name} - {db_entry['description']}")
                pmic_info["detected_pmics"].append({
                    "name": pmic_name,
                    "description": db_entry["description"],
                    "manufacturer": db_entry["manufacturer"],
                    "num_bucks": db_entry["num_bucks"],
                    "num_ldos": db_entry["num_ldos"],
                })
                pmic_info["manufacturer"] = db_entry["manufacturer"]
            else:
                log_fn(f"  PMIC pattern found: {pmic_name} (not in database)")
                pmic_info["detected_pmics"].append({
                    "name": pmic_name,
                    "description": "Unknown PMIC model",
                    "manufacturer": "Unknown",
                })
    else:
        log_fn("  Regulator debugfs not available")

    # --- MediaTek PMIC detection (PMIC_WRAP, device-tree, sysfs) ---
    platform = result.pmic_info.get("platform", pmic_info.get("platform", ""))
    is_mtk = "mt" in platform.lower() or "mediatek" in platform.lower()

    if is_mtk or pmic_info["version"] == "unknown":
        log_fn("  Checking MediaTek PMIC paths...")

        # Try MediaTek-specific sysfs paths
        for mtk_path in MTK_PMIC_PATHS:
            ok_mtk, mtk_out = _adb_shell(f"ls {mtk_path} 2>/dev/null")
            if ok_mtk and mtk_out and "No such file" not in mtk_out:
                log_fn(f"  MediaTek PMIC sysfs found: {mtk_path}")
                pmic_info["bus_status"] = "accessible (MTK)"
                break

        # Try device-tree for PMIC model
        ok_dt, dt_pmic = _adb_shell("cat /proc/device-tree/pmic/compatible 2>/dev/null")
        if ok_dt and dt_pmic:
            log_fn(f"  Device-tree PMIC: {dt_pmic}")
            for mtk_model, mtk_db in MEDIATEK_PMIC_DATABASE.items():
                if mtk_model.lower() in dt_pmic.lower():
                    log_fn(f"  Identified PMIC: {mtk_model} - {mtk_db['description']}")
                    pmic_info["detected_pmics"].append({
                        "name": mtk_model,
                        "description": mtk_db["description"],
                        "manufacturer": mtk_db["manufacturer"],
                        "num_bucks": mtk_db["num_bucks"],
                        "num_ldos": mtk_db["num_ldos"],
                    })
                    pmic_info["manufacturer"] = mtk_db["manufacturer"]
                    pmic_info["version"] = mtk_model

        # Try getprop for PMIC hints
        if pmic_info["version"] == "unknown":
            ok_hw, hw = _adb_shell("getprop ro.hardware.chipname 2>/dev/null")
            if ok_hw and hw:
                pmic_info["platform"] = hw.strip()

            # MediaTek regulator name patterns in regulator listing
            ok_regs, reg_names = _adb_shell(
                f"ls {REGULATOR_CLASS_PATH}/ 2>/dev/null"
            )
            if ok_regs and reg_names:
                mtk_pmic_hints = set()
                for rname in reg_names.split():
                    rname_lower = rname.lower()
                    # MediaTek regulator names: vcore, vproc, vgpu, vsram, etc.
                    if any(kw in rname_lower for kw in
                           ["vcore", "vproc", "vgpu", "vmodem", "vsram",
                            "vaud", "vibr", "vmc", "vmch", "vcama", "vcamd",
                            "vcn", "vio", "vfe", "vrf", "vusb", "vpa"]):
                        mtk_pmic_hints.add("MediaTek PMIC")

                if mtk_pmic_hints:
                    pmic_info["manufacturer"] = "MediaTek"
                    pmic_info["bus_status"] = "accessible (MTK regulators detected)"
                    if pmic_info["version"] == "unknown":
                        pmic_info["version"] = "MediaTek PMIC (model auto-detected from regulators)"
                    log_fn(f"  MediaTek PMIC confirmed via regulator names")

        # Classify regulators by voltage range if type is still Unknown
        # MediaTek regulators often have generic names like regulator.0
        # but we can infer type from voltage: Buck < 2V, LDO >= 1.2V & <= 3.3V
        if is_mtk:
            log_fn("  Classifying regulators by voltage range (MediaTek)...")

    # --- Samsung Exynos / Google Tensor PMIC detection ---
    hardware = result.pmic_info.get("hardware", pmic_info.get("hardware", ""))
    chipname = result.pmic_info.get("chipname", pmic_info.get("chipname", ""))
    _all_hw = (platform + " " + hardware + " " + chipname).lower()
    is_exynos = "exynos" in _all_hw
    is_tensor = "tensor" in _all_hw or "gs101" in _all_hw or "gs201" in _all_hw or "gs301" in _all_hw
    is_unisoc = "unisoc" in _all_hw or "sprd" in _all_hw or "ums" in _all_hw
    is_kirin = "kirin" in _all_hw or "hisilicon" in _all_hw

    if is_exynos or is_tensor or pmic_info["version"] == "unknown":
        log_fn("  Checking Samsung Exynos / Google Tensor PMIC paths...")

        # Check I2C bus for Samsung S2MPS PMICs
        ok_i2c, i2c_listing = _adb_shell("ls /sys/bus/i2c/devices/ 2>/dev/null")
        if ok_i2c and i2c_listing:
            for i2c_dev in i2c_listing.split():
                i2c_dev = i2c_dev.strip()
                if not i2c_dev:
                    continue
                ok_name, dev_name = _adb_shell(
                    f"cat /sys/bus/i2c/devices/{i2c_dev}/name 2>/dev/null"
                )
                if ok_name and dev_name:
                    m_s2m = re.search(r"(s2mp[a-z]\d+)", dev_name, re.IGNORECASE)
                    if m_s2m:
                        s2m_name = m_s2m.group(1).upper()
                        db_entry = PMIC_DATABASE.get(s2m_name)
                        if db_entry:
                            log_fn(f"  Identified Samsung PMIC: {s2m_name} - {db_entry['description']}")
                            pmic_info["detected_pmics"].append({
                                "name": s2m_name,
                                "description": db_entry["description"],
                                "manufacturer": db_entry["manufacturer"],
                                "num_bucks": db_entry["num_bucks"],
                                "num_ldos": db_entry["num_ldos"],
                            })
                            pmic_info["manufacturer"] = db_entry["manufacturer"]
                            pmic_info["version"] = s2m_name
                        else:
                            log_fn(f"  Samsung PMIC pattern found: {s2m_name} (not in database)")

        # Check device-tree for Exynos/Tensor/Unisoc/Kirin identifiers
        for dt_path in [
            "/proc/device-tree/compatible",
            "/proc/device-tree/model",
            "/proc/device-tree/soc/compatible",
        ]:
            ok_dt, dt_content = _adb_shell(f"cat {dt_path} 2>/dev/null")
            if ok_dt and dt_content:
                dt_lower = dt_content.lower()
                if "exynos" in dt_lower and pmic_info["manufacturer"] == "unknown":
                    pmic_info["manufacturer"] = "Samsung LSI"
                    log_fn(f"  Device-tree identifies Exynos platform: {dt_content}")
                elif "tensor" in dt_lower or "gs101" in dt_lower or "gs201" in dt_lower:
                    if pmic_info["manufacturer"] == "unknown":
                        pmic_info["manufacturer"] = "Google (Samsung LSI)"
                    log_fn(f"  Device-tree identifies Tensor platform: {dt_content}")
                elif "unisoc" in dt_lower or "sprd" in dt_lower:
                    if pmic_info["manufacturer"] == "unknown":
                        pmic_info["manufacturer"] = "Unisoc"
                    log_fn(f"  Device-tree identifies Unisoc platform: {dt_content}")
                elif "kirin" in dt_lower or "hisilicon" in dt_lower:
                    if pmic_info["manufacturer"] == "unknown":
                        pmic_info["manufacturer"] = "HiSilicon"
                    log_fn(f"  Device-tree identifies Kirin/HiSilicon platform: {dt_content}")

    # --- Unisoc PMIC detection ---
    if is_unisoc or pmic_info["version"] == "unknown":
        log_fn("  Checking Unisoc PMIC paths...")
        for unisoc_path in [
            "/sys/devices/platform/sc2730-regulator",
            "/sys/devices/platform/sc2721-regulator",
            "/sys/bus/spi/devices",
        ]:
            ok_u, u_out = _adb_shell(f"ls {unisoc_path} 2>/dev/null")
            if ok_u and u_out and "No such file" not in u_out:
                for u_model in ["SC2730", "SC2721"]:
                    if u_model.lower() in unisoc_path.lower() or u_model.lower() in u_out.lower():
                        db_entry = PMIC_DATABASE.get(u_model)
                        if db_entry:
                            log_fn(f"  Identified Unisoc PMIC: {u_model} - {db_entry['description']}")
                            pmic_info["detected_pmics"].append({
                                "name": u_model,
                                "description": db_entry["description"],
                                "manufacturer": db_entry["manufacturer"],
                                "num_bucks": db_entry["num_bucks"],
                                "num_ldos": db_entry["num_ldos"],
                            })
                            pmic_info["manufacturer"] = db_entry["manufacturer"]
                            pmic_info["version"] = u_model

    # --- HiSilicon Kirin PMIC detection ---
    if is_kirin or pmic_info["version"] == "unknown":
        log_fn("  Checking HiSilicon Kirin PMIC paths...")
        for hisi_path in [
            "/sys/devices/platform/hi6421-regulator",
            "/sys/devices/platform/hi6422-regulator",
            "/sys/devices/platform/hi6555-regulator",
        ]:
            ok_h, h_out = _adb_shell(f"ls {hisi_path} 2>/dev/null")
            if ok_h and h_out and "No such file" not in h_out:
                for h_model in ["Hi6421", "Hi6422", "Hi6555"]:
                    if h_model.lower() in hisi_path.lower():
                        db_entry = PMIC_DATABASE.get(h_model)
                        if db_entry:
                            log_fn(f"  Identified HiSilicon PMIC: {h_model} - {db_entry['description']}")
                            pmic_info["detected_pmics"].append({
                                "name": h_model,
                                "description": db_entry["description"],
                                "manufacturer": db_entry["manufacturer"],
                                "num_bucks": db_entry["num_bucks"],
                                "num_ldos": db_entry["num_ldos"],
                            })
                            pmic_info["manufacturer"] = db_entry["manufacturer"]
                            pmic_info["version"] = h_model

    # --- Power supply info (battery PMIC data) ---
    ok, ps_list = _adb_shell(f"ls {POWER_SUPPLY_PATH}/")
    if ok and ps_list:
        for ps in ps_list.split():
            ps = ps.strip()
            if not ps:
                continue
            ps_path = f"{POWER_SUPPLY_PATH}/{ps}"
            ok_type, ps_type = _adb_shell(f"cat {ps_path}/type 2>/dev/null")
            if ok_type and ps_type:
                pmic_info.setdefault("power_supplies", {})[ps] = {"type": ps_type}
                # Read voltage for batteries/chargers
                ok_v, v_now = _adb_shell(f"cat {ps_path}/voltage_now 2>/dev/null")
                if ok_v and v_now:
                    try:
                        v_uv = int(v_now)
                        pmic_info["power_supplies"][ps]["voltage_uv"] = v_uv
                        pmic_info["power_supplies"][ps]["voltage_mv"] = v_uv / 1000.0
                    except ValueError:
                        pass
                ok_c, c_now = _adb_shell(f"cat {ps_path}/current_now 2>/dev/null")
                if ok_c and c_now:
                    try:
                        c_ua = int(c_now)
                        pmic_info["power_supplies"][ps]["current_ua"] = c_ua
                        pmic_info["power_supplies"][ps]["current_ma"] = c_ua / 1000.0
                    except ValueError:
                        pass
        log_fn(f"  Power supplies: {', '.join(ps_list.split())}")

    # Determine PMIC version string
    if pmic_info["detected_pmics"]:
        names = [p.get("name", p.get("bus_id", "?")) for p in pmic_info["detected_pmics"]]
        pmic_info["version"] = " + ".join(sorted(set(names)))
    log_fn(f"  PMIC version summary: {pmic_info.get('version', 'unknown')}")


def _step_read_regulators(result: PowerTestResult, log_fn: Callable, progress_fn: Callable) -> None:
    """Step 3: enumerate all regulators from /sys/class/regulator/."""
    progress_fn(0.30, "Reading regulator voltages...")
    log_fn("")
    log_fn("[3/6] Reading regulator information...")

    ok, reg_list = _adb_shell(f"ls {REGULATOR_CLASS_PATH}/")
    if not ok or not reg_list or "No such file" in reg_list:
        log_fn("  /sys/class/regulator/ not available")
        # Try debugfs as fallback
        ok2, reg_list2 = _adb_shell_root(f"ls {REGULATOR_DEBUG_PATH}/")
        if ok2 and reg_list2 and "No such file" not in reg_list2:
            log_fn(f"  Falling back to debugfs ({len(reg_list2.split())} regulators)")
            _read_regulators_from_debugfs(reg_list2, result, log_fn)
        else:
            log_fn("  No regulator information available")
        return

    entries = [e.strip() for e in reg_list.split() if e.strip()]
    log_fn(f"  Found {len(entries)} regulator entries")

    count = 0
    for entry in entries:
        reg_path = f"{REGULATOR_CLASS_PATH}/{entry}"

        info = RegulatorInfo()

        # Read the regulator name
        ok_name, name = _adb_shell(f"cat {reg_path}/name 2>/dev/null")
        if ok_name and name:
            info.name = name
        else:
            info.name = entry

        # Classify type by name pattern
        info.regulator_type = _classify_regulator_type(info.name)

        # Read voltage
        ok_v, v_str = _adb_shell(f"cat {reg_path}/microvolts 2>/dev/null")
        if ok_v and v_str:
            info.microvolts = _parse_microvolts(v_str)
            info.voltage_mv = _uv_to_mv(info.microvolts)

        # If type still Unknown and we have voltage, classify by voltage range
        if (info.regulator_type in ("Unknown", "Regulator", "")
                and info.voltage_mv > 0):
            if info.voltage_mv <= 1100:
                info.regulator_type = "Buck (low-voltage)"
            elif info.voltage_mv <= 2000:
                info.regulator_type = "LDO (mid-voltage)"
            else:
                info.regulator_type = "LDO (high-voltage)"

        # Read status (state)
        ok_st, state = _adb_shell(f"cat {reg_path}/state 2>/dev/null")
        if ok_st and state:
            info.state = state
            if "enabled" in state.lower():
                info.status = "enabled"
            elif "disabled" in state.lower():
                info.status = "disabled"
            else:
                info.status = state

        # Read status file directly
        ok_status, status_str = _adb_shell(f"cat {reg_path}/status 2>/dev/null")
        if ok_status and status_str and status_str != info.status:
            if info.status == "unknown":
                info.status = status_str

        # Min / max voltage range
        ok_min, min_str = _adb_shell(f"cat {reg_path}/min_microvolts 2>/dev/null")
        if ok_min and min_str:
            info.min_uv = _parse_microvolts(min_str)

        ok_max, max_str = _adb_shell(f"cat {reg_path}/max_microvolts 2>/dev/null")
        if ok_max and max_str:
            info.max_uv = _parse_microvolts(max_str)

        # Number of consumers
        ok_users, users_str = _adb_shell(f"cat {reg_path}/num_users 2>/dev/null")
        if ok_users and users_str:
            try:
                info.num_users = int(users_str)
                # If status is still unknown, infer from num_users
                if info.status == "unknown" and info.num_users > 0:
                    info.status = "enabled"
                elif info.status == "unknown" and info.num_users == 0:
                    info.status = "disabled"
            except ValueError:
                pass

        # Suspend state
        ok_susp, susp = _adb_shell(f"cat {reg_path}/suspend_state 2>/dev/null")
        if ok_susp and susp:
            info.suspend_state = susp

        result.regulators.append(info)
        count += 1

        # Log a few notable ones
        if info.voltage_mv > 0:
            logger.debug(
                "Regulator %s: %.1f mV [%s] (%s)",
                info.name, info.voltage_mv, info.status, info.regulator_type,
            )

    log_fn(f"  Read {count} regulators successfully")

    # Summarise
    enabled = sum(1 for r in result.regulators if r.status == "enabled")
    disabled = sum(1 for r in result.regulators if r.status == "disabled")
    bucks = sum(1 for r in result.regulators if "Buck" in r.regulator_type)
    ldos = sum(1 for r in result.regulators if "LDO" in r.regulator_type)
    log_fn(f"  Enabled: {enabled}, Disabled: {disabled}")
    log_fn(f"  Bucks/SMPS: {bucks}, LDOs: {ldos}")


def _read_regulators_from_debugfs(
    listing: str,
    result: PowerTestResult,
    log_fn: Callable,
) -> None:
    """Fallback: read regulators from debugfs when /sys/class/regulator is empty."""
    entries = [e.strip() for e in listing.split() if e.strip()]
    for entry in entries:
        reg_path = f"{REGULATOR_DEBUG_PATH}/{entry}"
        info = RegulatorInfo(name=entry)
        info.regulator_type = _classify_regulator_type(entry)

        # Debugfs usually has a flat file with key=value or multi-line text
        ok, content = _adb_shell_root(f"cat {reg_path}/enable 2>/dev/null")
        if ok and content:
            info.status = "enabled" if content.strip() == "1" else "disabled"

        ok, content = _adb_shell_root(f"cat {reg_path}/voltage 2>/dev/null")
        if ok and content:
            info.microvolts = _parse_microvolts(content)
            info.voltage_mv = _uv_to_mv(info.microvolts)

        ok, content = _adb_shell_root(f"cat {reg_path}/min_uv 2>/dev/null")
        if ok and content:
            info.min_uv = _parse_microvolts(content)

        ok, content = _adb_shell_root(f"cat {reg_path}/max_uv 2>/dev/null")
        if ok and content:
            info.max_uv = _parse_microvolts(content)

        result.regulators.append(info)

    log_fn(f"  Read {len(entries)} regulators from debugfs")


def _step_read_power_rails(
    result: PowerTestResult,
    log_fn: Callable,
    progress_fn: Callable,
) -> None:
    """Step 4: read power rail voltages and match against known chipset rails."""
    progress_fn(0.50, "Monitoring power rails...")
    log_fn("")
    log_fn("[4/6] Reading power rail voltages...")

    # Determine chipset
    platform = result.pmic_info.get("platform", "")
    hardware = result.pmic_info.get("hardware", "")
    chipname = result.pmic_info.get("chipname", "")
    chipset_key = (
        _match_chipset(chipname)
        or _match_chipset(platform)
        or _match_chipset(hardware)
    )

    known_rails: Dict[str, Dict[str, Any]] = {}
    if chipset_key:
        known_rails = CHIPSET_POWER_RAILS.get(chipset_key, {})
        log_fn(f"  Matched chipset: {chipset_key} ({len(known_rails)} known rails)")
    else:
        log_fn(f"  Chipset not matched (platform={platform}, hw={hardware})")
        log_fn("  Will report raw regulator data without expected-voltage comparison")

    # Build a lookup from regulator name -> RegulatorInfo
    reg_by_name: Dict[str, RegulatorInfo] = {}
    for r in result.regulators:
        reg_by_name[r.name.lower()] = r

    # Read known rails
    for rail_name, rail_spec in known_rails.items():
        rail = PowerRailInfo(
            name=rail_name,
            description=rail_spec.get("description", ""),
            expected_voltage_mv=rail_spec.get("expected_voltage_mv", 0),
            regulator_name=rail_spec.get("regulator", ""),
        )

        # Try to find the regulator in our readings
        reg_key = rail_spec.get("regulator", "").lower()
        matched_reg = reg_by_name.get(reg_key)
        if matched_reg and matched_reg.voltage_mv > 0:
            rail.voltage_mv = matched_reg.voltage_mv
        else:
            # Try to read the voltage via ADB directly
            ok, vout = _adb_shell_root(
                f"cat {REGULATOR_DEBUG_PATH}/{rail_spec.get('regulator', '')}/voltage 2>/dev/null"
            )
            if ok and vout:
                uv = _parse_microvolts(vout)
                rail.voltage_mv = _uv_to_mv(uv)

        # Read current if available
        ok_curr, curr_str = _adb_shell_root(
            f"cat {REGULATOR_DEBUG_PATH}/{rail_spec.get('regulator', '')}/current 2>/dev/null"
        )
        if ok_curr and curr_str:
            try:
                rail.current_ma = int(curr_str.strip()) / 1000.0
            except ValueError:
                pass

        # Determine rail status
        expected = rail_spec.get("expected_voltage_mv", 0)
        rail_min = rail_spec.get("min_voltage_mv", 0)
        rail_max = rail_spec.get("max_voltage_mv", 0)

        if rail.voltage_mv <= 0:
            rail.status = "OFF"
        elif rail_min <= rail.voltage_mv <= rail_max:
            rail.status = "OK"
        elif rail.voltage_mv < rail_min:
            rail.status = "LOW"
        elif rail.voltage_mv > rail_max:
            rail.status = "HIGH"
        else:
            rail.status = "UNKNOWN"

        result.power_rails.append(rail)
        log_fn(
            f"  {rail_name}: {rail.voltage_mv:.1f} mV "
            f"(expected {expected} mV, range {rail_min}-{rail_max} mV) "
            f"-> {rail.status}"
        )

    # Also add rails from regulators that are not in the known-rails DB
    known_reg_names = {spec.get("regulator", "").lower() for spec in known_rails.values()}
    extra_count = 0
    for reg in result.regulators:
        if reg.name.lower() in known_reg_names:
            continue
        if reg.voltage_mv <= 0 and reg.status != "enabled":
            continue
        rail = PowerRailInfo(
            name=reg.name,
            voltage_mv=reg.voltage_mv,
            status="OK" if reg.status == "enabled" and reg.voltage_mv > 0 else "OFF",
            regulator_name=reg.name,
        )
        result.power_rails.append(rail)
        extra_count += 1

    if extra_count:
        log_fn(f"  Added {extra_count} additional rails from regulator scan")
    log_fn(f"  Total rails monitored: {len(result.power_rails)}")


def _step_short_circuit_analysis(
    result: PowerTestResult,
    log_fn: Callable,
    progress_fn: Callable,
) -> None:
    """Step 5: analyse voltage drops and overcurrent for short-circuit detection."""
    progress_fn(0.70, "Analysing for short circuits...")
    log_fn("")
    log_fn("[5/6] Short circuit / fault analysis...")

    if not result.power_rails:
        log_fn("  No power rails available for analysis")
        return

    faults = 0

    for rail in result.power_rails:
        sc = ShortCircuitResult(rail_name=rail.name)

        # --- Voltage-based analysis ---
        if rail.expected_voltage_mv > 0 and rail.voltage_mv > 0:
            drop = rail.expected_voltage_mv - rail.voltage_mv
            sc.voltage_drop_mv = drop
            tolerance = rail.expected_voltage_mv * (VOLTAGE_TOLERANCE_PCT / 100.0)

            if abs(drop) <= tolerance:
                # Voltage within tolerance
                sc.status = "OK"
                sc.verdict = (
                    f"Voltage {rail.voltage_mv:.1f} mV within "
                    f"{VOLTAGE_TOLERANCE_PCT:.0f}% of expected {rail.expected_voltage_mv:.1f} mV"
                )
            elif drop > tolerance:
                # Voltage too low -- possible short pulling rail down
                sc.status = "SHORT"
                sc.verdict = (
                    f"Voltage {rail.voltage_mv:.1f} mV is {drop:.1f} mV BELOW expected "
                    f"{rail.expected_voltage_mv:.1f} mV -- possible short to ground"
                )
                faults += 1
            elif drop < -tolerance:
                # Voltage too high -- possible open or feedback fault
                sc.status = "OPEN"
                sc.verdict = (
                    f"Voltage {rail.voltage_mv:.1f} mV is {abs(drop):.1f} mV ABOVE expected "
                    f"{rail.expected_voltage_mv:.1f} mV -- possible open-loop / feedback fault"
                )
                faults += 1
        elif rail.voltage_mv <= 0 and rail.expected_voltage_mv > 0:
            # Rail is off when it should be on
            sc.status = "SHORT"
            sc.voltage_drop_mv = rail.expected_voltage_mv
            sc.verdict = (
                f"Rail reads 0 mV but expected {rail.expected_voltage_mv:.1f} mV "
                "-- rail may be shorted to ground or PMIC output is disabled/blown"
            )
            faults += 1
        elif rail.expected_voltage_mv <= 0:
            # No expected voltage to compare -- just check it is reasonable
            if rail.voltage_mv > 0:
                sc.status = "OK"
                sc.verdict = f"Rail active at {rail.voltage_mv:.1f} mV (no baseline to compare)"
            else:
                sc.status = "UNKNOWN"
                sc.verdict = "Rail inactive, no expected voltage data available"

        # --- Current-based analysis ---
        if rail.current_ma > 0:
            sc.measured_current_ma = rail.current_ma
            if rail.current_ma > OVERCURRENT_THRESHOLD_MA:
                if sc.status == "OK":
                    sc.status = "LEAKY"
                sc.verdict += (
                    f" | OVERCURRENT: {rail.current_ma:.1f} mA exceeds "
                    f"threshold {OVERCURRENT_THRESHOLD_MA:.0f} mA"
                )
                faults += 1

            # Estimate resistance from voltage and current (R = V / I)
            if rail.voltage_mv > 0 and rail.current_ma > 0:
                sc.resistance_ohm = rail.voltage_mv / rail.current_ma
                if sc.resistance_ohm < SHORT_CIRCUIT_RESISTANCE_THRESHOLD:
                    if sc.status == "OK":
                        sc.status = "SHORT"
                    sc.verdict += (
                        f" | LOW RESISTANCE: {sc.resistance_ohm:.3f} ohm "
                        f"(< {SHORT_CIRCUIT_RESISTANCE_THRESHOLD} ohm threshold)"
                    )
                    faults += 1

        result.short_circuit_results.append(sc)
        if sc.status not in ("OK", "UNKNOWN"):
            log_fn(f"  ** {rail.name}: {sc.status} -- {sc.verdict}")
        else:
            log_fn(f"  {rail.name}: {sc.status}")

    log_fn(f"  Analysis complete: {faults} fault(s) detected across {len(result.power_rails)} rails")


def _step_thermal_power(
    result: PowerTestResult,
    log_fn: Callable,
    progress_fn: Callable,
) -> None:
    """Step 6: gather thermal data and estimate power consumption."""
    progress_fn(0.85, "Reading thermal and power data...")
    log_fn("")
    log_fn("[6/6] Thermal and power consumption estimates...")

    thermal: Dict[str, Any] = {
        "zones": {},
        "battery_power_mw": 0.0,
        "usb_power_mw": 0.0,
        "estimated_total_mw": 0.0,
    }

    # --- Thermal zones ---
    ok, tz_list = _adb_shell(f"ls {THERMAL_ZONE_PATH}/")
    if ok and tz_list:
        for tz in tz_list.split():
            tz = tz.strip()
            if not tz.startswith("thermal_zone"):
                continue
            tz_path = f"{THERMAL_ZONE_PATH}/{tz}"
            ok_type, tz_type = _adb_shell(f"cat {tz_path}/type 2>/dev/null")
            ok_temp, tz_temp = _adb_shell(f"cat {tz_path}/temp 2>/dev/null")
            if ok_type and ok_temp:
                try:
                    temp_raw = int(tz_temp.strip())
                    # Temperatures are usually in millidegrees C
                    temp_c = temp_raw / 1000.0 if temp_raw > 200 else float(temp_raw)
                    thermal["zones"][tz_type.strip()] = temp_c
                except ValueError:
                    pass
        log_fn(f"  Thermal zones read: {len(thermal['zones'])}")
        # Report notable temperatures
        for zone_name, temp_c in sorted(thermal["zones"].items()):
            if temp_c > 50.0:
                log_fn(f"  ** HOT: {zone_name} = {temp_c:.1f} C")
            elif temp_c > 0:
                logger.debug("Thermal %s: %.1f C", zone_name, temp_c)

    # --- Battery power ---
    ps_data = result.pmic_info.get("power_supplies", {})
    for ps_name, ps_info in ps_data.items():
        v_mv = ps_info.get("voltage_mv", 0)
        c_ma = ps_info.get("current_ma", 0)
        if v_mv > 0 and c_ma != 0:
            power_mw = abs(v_mv * c_ma) / 1000.0
            ps_type = ps_info.get("type", "")
            if "battery" in ps_name.lower() or "battery" in ps_type.lower():
                thermal["battery_power_mw"] = power_mw
                log_fn(f"  Battery power: {power_mw:.1f} mW ({v_mv:.0f} mV x {abs(c_ma):.1f} mA)")
            elif "usb" in ps_name.lower() or "usb" in ps_type.lower():
                thermal["usb_power_mw"] = power_mw
                log_fn(f"  USB power: {power_mw:.1f} mW")

    # --- Estimate total power from active regulators ---
    total_estimated_mw = 0.0
    for rail in result.power_rails:
        if rail.current_ma > 0 and rail.voltage_mv > 0:
            total_estimated_mw += (rail.voltage_mv * rail.current_ma) / 1000.0
    if total_estimated_mw > 0:
        thermal["estimated_total_mw"] = total_estimated_mw
        log_fn(f"  Estimated rail power: {total_estimated_mw:.1f} mW")
    elif thermal["battery_power_mw"] > 0:
        thermal["estimated_total_mw"] = thermal["battery_power_mw"]

    result.thermal_power = thermal


def _compute_overall_health(result: PowerTestResult, log_fn: Callable) -> None:
    """Compute the overall_health string from all gathered data."""
    if not result.connected:
        result.overall_health = "NO CONNECTION"
        return

    fault_count = sum(
        1 for sc in result.short_circuit_results if sc.status in ("SHORT", "LEAKY")
    )
    open_count = sum(
        1 for sc in result.short_circuit_results if sc.status == "OPEN"
    )
    off_rails = sum(
        1 for r in result.power_rails
        if r.status == "OFF" and r.expected_voltage_mv > 0
    )
    hot_zones = sum(
        1 for t in result.thermal_power.get("zones", {}).values()
        if t > 65.0
    )

    issues: List[str] = []
    if fault_count > 0:
        issues.append(f"{fault_count} short/leak fault(s)")
    if open_count > 0:
        issues.append(f"{open_count} open-circuit indication(s)")
    if off_rails > 0:
        issues.append(f"{off_rails} expected rail(s) OFF")
    if hot_zones > 0:
        issues.append(f"{hot_zones} thermal hotspot(s) > 65 C")

    if fault_count > 0:
        result.overall_health = "CRITICAL"
    elif open_count > 0 or off_rails > 0:
        result.overall_health = "WARNING"
    elif hot_zones > 0:
        result.overall_health = "WARNING"
    elif len(result.regulators) == 0 and len(result.power_rails) == 0:
        result.overall_health = "INCOMPLETE"
    else:
        result.overall_health = "GOOD"

    log_fn("")
    log_fn("-" * 60)
    if issues:
        log_fn(f"Overall health: {result.overall_health} ({'; '.join(issues)})")
    else:
        log_fn(f"Overall health: {result.overall_health}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def detect_power_status(callback: Optional[Callable[[float, str], None]] = None) -> PowerTestResult:
    """
    Full power/voltage testing pipeline:

    1. Check ADB connection
    2. Read PMIC information via SPMI debug and bus sysfs
    3. Enumerate all regulators (Buck / LDO / Boost)
    4. Read power rail voltages and match against known chipset rails
    5. Analyse for short circuits (voltage drops, overcurrent)
    6. Gather thermal data and estimate power consumption

    Parameters
    ----------
    callback : callable, optional
        Progress callback with signature ``callback(pct, msg)``
        where *pct* is 0.0 .. 1.0 and *msg* is a human-readable step label.

    Returns
    -------
    PowerTestResult
        Populated result dataclass.
    """
    result = PowerTestResult()
    start_time = time.monotonic()

    def _log(msg: str) -> None:
        result.log.append(msg)
        logger.info(msg)

    def _progress(frac: float, msg: str) -> None:
        if callback:
            try:
                callback(frac, msg)
            except Exception:
                pass

    _log("=" * 60)
    _log("  Power / Voltage Testing Report")
    _log("=" * 60)
    _log("")

    # Step 1: ADB connection
    if not _step_check_adb(result, _log, _progress):
        _progress(1.0, "Power test aborted -- no ADB connection")
        result.detection_duration_s = time.monotonic() - start_time
        return result

    # Step 2: PMIC
    try:
        _step_read_pmic(result, _log, _progress)
    except Exception as exc:
        _log(f"  PMIC step failed: {type(exc).__name__}: {exc}")
        logger.exception("PMIC step error")

    # Step 3: Regulators
    try:
        _step_read_regulators(result, _log, _progress)
    except Exception as exc:
        _log(f"  Regulator step failed: {type(exc).__name__}: {exc}")
        logger.exception("Regulator step error")

    # Step 4: Power rails
    try:
        _step_read_power_rails(result, _log, _progress)
    except Exception as exc:
        _log(f"  Power rail step failed: {type(exc).__name__}: {exc}")
        logger.exception("Power rail step error")

    # Step 5: Short circuit analysis
    try:
        _step_short_circuit_analysis(result, _log, _progress)
    except Exception as exc:
        _log(f"  Short circuit analysis failed: {type(exc).__name__}: {exc}")
        logger.exception("Short circuit analysis error")

    # Step 6: Thermal / power
    try:
        _step_thermal_power(result, _log, _progress)
    except Exception as exc:
        _log(f"  Thermal step failed: {type(exc).__name__}: {exc}")
        logger.exception("Thermal step error")

    # Overall health
    _compute_overall_health(result, _log)

    result.detection_duration_s = time.monotonic() - start_time
    _log(f"  Detection time: {result.detection_duration_s:.1f}s")
    _log("=" * 60)

    _progress(1.0, "Power test complete")
    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_power_report(result: PowerTestResult) -> str:
    """
    Generate a formatted text report from a power test result.

    Parameters
    ----------
    result : PowerTestResult
        The power test result to format.

    Returns
    -------
    str
        Multi-line human-readable report string.
    """
    lines: List[str] = []

    def section(title: str) -> None:
        lines.append("")
        lines.append(f"--- {title} ---")

    lines.append("=" * 60)
    lines.append("  POWER / VOLTAGE TEST REPORT")
    lines.append("=" * 60)

    # Connection
    section("Connection")
    if result.connected:
        lines.append("  Status     : CONNECTED")
        platform = result.pmic_info.get("platform", "N/A")
        hardware = result.pmic_info.get("hardware", "N/A")
        lines.append(f"  Platform   : {platform}")
        lines.append(f"  Hardware   : {hardware}")
    else:
        lines.append("  Status     : NOT CONNECTED")
        if result.error:
            lines.append(f"  Error      : {result.error}")
        return "\n".join(lines)

    # PMIC
    if result.pmic_info:
        section("PMIC Information")
        lines.append(f"  Version      : {result.pmic_info.get('version', 'unknown')}")
        lines.append(f"  Manufacturer : {result.pmic_info.get('manufacturer', 'unknown')}")
        lines.append(f"  Bus status   : {result.pmic_info.get('bus_status', 'unknown')}")
        detected = result.pmic_info.get("detected_pmics", [])
        if detected:
            lines.append(f"  Detected PMICs ({len(detected)}):")
            for p in detected:
                name = p.get("name", p.get("bus_id", "?"))
                desc = p.get("description", "")
                lines.append(f"    - {name}: {desc}")
        # Power supplies
        ps = result.pmic_info.get("power_supplies", {})
        if ps:
            lines.append(f"  Power supplies ({len(ps)}):")
            for ps_name, ps_info in ps.items():
                v = ps_info.get("voltage_mv", 0)
                c = ps_info.get("current_ma", 0)
                lines.append(f"    - {ps_name}: {v:.0f} mV, {c:.1f} mA ({ps_info.get('type', '')})")

    # Regulators
    if result.regulators:
        section(f"Regulators ({len(result.regulators)} total)")
        enabled = [r for r in result.regulators if r.status == "enabled"]
        disabled = [r for r in result.regulators if r.status == "disabled"]
        lines.append(f"  Enabled: {len(enabled)}, Disabled: {len(disabled)}")

        # Show enabled regulators with voltages
        if enabled:
            lines.append("")
            lines.append("  Enabled regulators:")
            lines.append(f"  {'Name':<30s} {'Type':<16s} {'Voltage (mV)':>14s}  {'Range (uV)'}")
            lines.append("  " + "-" * 80)
            for r in sorted(enabled, key=lambda x: x.name):
                v_str = f"{r.voltage_mv:.1f}" if r.voltage_mv > 0 else "N/A"
                range_str = ""
                if r.min_uv > 0 or r.max_uv > 0:
                    range_str = f"{r.min_uv} - {r.max_uv}"
                lines.append(f"  {r.name:<30s} {r.regulator_type:<16s} {v_str:>14s}  {range_str}")

    # Power rails
    if result.power_rails:
        section(f"Power Rails ({len(result.power_rails)} monitored)")
        lines.append(
            f"  {'Rail':<20s} {'Voltage':>10s} {'Expected':>10s} {'Status':<8s} {'Current':>10s}"
        )
        lines.append("  " + "-" * 65)
        for rail in result.power_rails:
            v_str = f"{rail.voltage_mv:.1f}" if rail.voltage_mv > 0 else "OFF"
            e_str = f"{rail.expected_voltage_mv:.0f}" if rail.expected_voltage_mv > 0 else "N/A"
            c_str = f"{rail.current_ma:.1f}" if rail.current_ma > 0 else "-"
            lines.append(
                f"  {rail.name:<20s} {v_str:>10s} {e_str:>10s} {rail.status:<8s} {c_str:>10s}"
            )

    # Short circuit results
    faults = [sc for sc in result.short_circuit_results if sc.status not in ("OK", "UNKNOWN")]
    if faults:
        section(f"FAULT ANALYSIS ({len(faults)} issue(s))")
        for sc in faults:
            lines.append(f"  [{sc.status}] {sc.rail_name}")
            lines.append(f"    {sc.verdict}")
            if sc.resistance_ohm > 0:
                lines.append(f"    Estimated resistance: {sc.resistance_ohm:.3f} ohm")
            if sc.voltage_drop_mv != 0:
                lines.append(f"    Voltage drop: {sc.voltage_drop_mv:.1f} mV")
    elif result.short_circuit_results:
        section("Short Circuit Analysis")
        ok_count = sum(1 for sc in result.short_circuit_results if sc.status == "OK")
        lines.append(f"  All {ok_count} checked rails within tolerance. No faults detected.")

    # Thermal / power
    if result.thermal_power:
        section("Thermal / Power")
        tp = result.thermal_power
        if tp.get("battery_power_mw"):
            lines.append(f"  Battery power  : {tp['battery_power_mw']:.1f} mW")
        if tp.get("usb_power_mw"):
            lines.append(f"  USB power      : {tp['usb_power_mw']:.1f} mW")
        if tp.get("estimated_total_mw"):
            lines.append(f"  Est. total     : {tp['estimated_total_mw']:.1f} mW")
        zones = tp.get("zones", {})
        if zones:
            hot = {k: v for k, v in zones.items() if v > 45.0}
            if hot:
                lines.append(f"  Hot zones (> 45 C):")
                for zn, zt in sorted(hot.items(), key=lambda x: -x[1]):
                    lines.append(f"    {zn}: {zt:.1f} C")

    # Overall health
    section("Overall Health")
    lines.append(f"  {result.overall_health}")

    # Footer
    lines.append("")
    lines.append("-" * 60)
    lines.append(f"  Detection time: {result.detection_duration_s:.1f}s")
    lines.append("=" * 60)

    return "\n".join(lines)
