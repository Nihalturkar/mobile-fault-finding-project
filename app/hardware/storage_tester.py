"""
Storage & RAM Testing Module for Mobile Repair Technicians.

Performs comprehensive storage and RAM diagnostics on a connected Android
device via ADB.  Reads UFS/eMMC controller information, flash IC model
identification, SMART-like health attributes, partition layout, disk usage,
and RAM type/capacity.  Results are matched against a built-in knowledge
database of 30+ storage ICs and 20+ RAM ICs from Samsung, SK Hynix, Micron,
Kioxia/Toshiba, and Western Digital to provide technician-friendly
diagnostics and common-failure warnings.

Requires: Android Platform Tools (adb) on PATH, USB Debugging enabled.
          Root/engineering builds give best results (debugfs / sysfs access).
"""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Progress callback type alias
# ---------------------------------------------------------------------------
ProgressCallback = Optional[Callable[[float, str], None]]


# ---------------------------------------------------------------------------
#  Knowledge database — Storage Flash ICs (30+ entries)
# ---------------------------------------------------------------------------
STORAGE_IC_DATABASE: Dict[str, Dict[str, Any]] = {
    # ── Samsung UFS ──
    "KLUDG4UHDB-B0D1": {
        "manufacturer": "Samsung",
        "type": "UFS 3.1",
        "capacity": "256GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1200,
        "process_nm": 128,
        "nand_type": "V-NAND TLC",
        "common_failures": [
            "Firmware hang after prolonged heavy write — requires power cycle",
            "UFS link instability on certain Qualcomm SoCs at HS-G4 rate",
            "Sudden read-only mode when pre-EOL threshold reached",
        ],
    },
    "KLUEG8UHDB": {
        "manufacturer": "Samsung",
        "type": "UFS 3.1",
        "capacity": "512GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1200,
        "process_nm": 128,
        "nand_type": "V-NAND TLC",
        "common_failures": [
            "Write amplification degradation with heavy random-4K workloads",
            "Occasional UFS descriptor corruption after unexpected power-loss",
            "Thermal throttling above 65C junction temperature",
        ],
    },
    "KLUFG8RHDA": {
        "manufacturer": "Samsung",
        "type": "UFS 4.0",
        "capacity": "256GB",
        "interface": "UFS 4.0 (HS-G5, 2L)",
        "seq_read_mbps": 4200,
        "seq_write_mbps": 2800,
        "process_nm": 7,
        "nand_type": "V-NAND TLC 7th Gen",
        "common_failures": [
            "Link training failure on legacy UFS 3.x host controllers",
            "Higher power draw in sustained write — battery drain complaints",
            "Early firmware revisions have GC stall under fragmented writes",
        ],
    },
    "KLUFG8RHDB": {
        "manufacturer": "Samsung",
        "type": "UFS 4.0",
        "capacity": "512GB",
        "interface": "UFS 4.0 (HS-G5, 2L)",
        "seq_read_mbps": 4200,
        "seq_write_mbps": 2800,
        "process_nm": 7,
        "nand_type": "V-NAND TLC 7th Gen",
        "common_failures": [
            "UFS device reset required after firmware OTA in some builds",
            "Power-loss protection circuit sensitive to voltage droop",
        ],
    },
    "KLMAG1JETD": {
        "manufacturer": "Samsung",
        "type": "eMMC 5.1",
        "capacity": "32GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 300,
        "seq_write_mbps": 90,
        "process_nm": 19,
        "nand_type": "V-NAND TLC",
        "common_failures": [
            "eMMC boot partition corruption — device stuck at logo",
            "Slow degradation of write speed after 80% lifetime consumed",
            "CID register mismatch after reflash with incompatible firmware",
        ],
    },
    "KLMAG2GEND": {
        "manufacturer": "Samsung",
        "type": "eMMC 5.1",
        "capacity": "64GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 300,
        "seq_write_mbps": 150,
        "process_nm": 19,
        "nand_type": "V-NAND TLC",
        "common_failures": [
            "eMMC controller lockup after 50K+ P/E cycles",
            "Boot area wear-out in devices with frequent OTA updates",
        ],
    },
    "KLMCG2KETM": {
        "manufacturer": "Samsung",
        "type": "eMMC 5.1",
        "capacity": "128GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 300,
        "seq_write_mbps": 170,
        "process_nm": 19,
        "nand_type": "V-NAND TLC",
        "common_failures": [
            "Write protect flag inadvertently set after battery disconnect",
            "Slow random write performance degradation over time",
        ],
    },
    "KLUDG2UHDB": {
        "manufacturer": "Samsung",
        "type": "UFS 3.1",
        "capacity": "128GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1200,
        "process_nm": 128,
        "nand_type": "V-NAND TLC",
        "common_failures": [
            "UFS hibernate exit latency spikes after prolonged idle",
            "Data retention concern when stored unpowered > 6 months",
        ],
    },

    # ── SK Hynix UFS ──
    "H9HP52ACPMDAR": {
        "manufacturer": "SK Hynix",
        "type": "UFS 3.1",
        "capacity": "256GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1200,
        "process_nm": 176,
        "nand_type": "176L TLC NAND",
        "common_failures": [
            "Occasional UFS command timeout under heavy multitasking",
            "FW update required to fix garbage collection stutter",
            "Health descriptor values not exposed on some OEM kernels",
        ],
    },
    "H28U88301AMR": {
        "manufacturer": "SK Hynix",
        "type": "UFS 4.0",
        "capacity": "256GB",
        "interface": "UFS 4.0 (HS-G5, 2L)",
        "seq_read_mbps": 4200,
        "seq_write_mbps": 2800,
        "process_nm": 238,
        "nand_type": "238L TLC NAND",
        "common_failures": [
            "Early adopter firmware has write cache flush latency issue",
            "Link speed downshift under thermal throttling conditions",
            "RPMB authentication failures with certain TEE implementations",
        ],
    },
    "H9HKNNNFBMAU": {
        "manufacturer": "SK Hynix",
        "type": "UFS 3.1",
        "capacity": "128GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1100,
        "process_nm": 176,
        "nand_type": "176L TLC NAND",
        "common_failures": [
            "Random 4K read performance lower than Samsung equivalent",
            "Device descriptor sometimes reports incorrect LU size",
        ],
    },
    "H9HP32ACPMDARLGM": {
        "manufacturer": "SK Hynix",
        "type": "UFS 3.1",
        "capacity": "512GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1200,
        "process_nm": 176,
        "nand_type": "176L TLC NAND",
        "common_failures": [
            "Firmware bug causing device busy status under trim storm",
            "Sporadic CRC error on data-out phase at high temperatures",
        ],
    },
    "H26M64208EMR": {
        "manufacturer": "SK Hynix",
        "type": "eMMC 5.1",
        "capacity": "64GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 300,
        "seq_write_mbps": 140,
        "process_nm": 96,
        "nand_type": "96L TLC NAND",
        "common_failures": [
            "eMMC life_time estimation unreliable in early FW revisions",
            "Boot partition corruption from abrupt power-off during OTA",
        ],
    },

    # ── Micron UFS ──
    "MT29VZZZAD8GQFSL": {
        "manufacturer": "Micron",
        "type": "UFS 3.1",
        "capacity": "256GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1200,
        "process_nm": 176,
        "nand_type": "176L TLC NAND (B58R)",
        "common_failures": [
            "Vendor-specific UPIU command incompatibility with some hosts",
            "Write-booster SLC cache exhaustion causes severe performance dip",
            "Health report shows life_time_a != life_time_b discrepancy",
        ],
    },
    "MT29TDDHABETDL": {
        "manufacturer": "Micron",
        "type": "UFS 4.0",
        "capacity": "256GB",
        "interface": "UFS 4.0 (HS-G5, 2L)",
        "seq_read_mbps": 4300,
        "seq_write_mbps": 2900,
        "process_nm": 232,
        "nand_type": "232L TLC NAND",
        "common_failures": [
            "UFS 4.0 link negotiation failure on non-latest host drivers",
            "Elevated write amplification under mixed workload patterns",
            "Temperature sensor offset calibration drift over time",
        ],
    },
    "MT29VZZZBD9DQFSL": {
        "manufacturer": "Micron",
        "type": "UFS 3.1",
        "capacity": "512GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1200,
        "process_nm": 176,
        "nand_type": "176L TLC NAND (B58R)",
        "common_failures": [
            "SLC cache size shrinks as drive fills — user notices slowdown",
            "Rare data corruption after deep-sleep wake in certain SoCs",
        ],
    },
    "MTFC32GAZAQHD": {
        "manufacturer": "Micron",
        "type": "eMMC 5.1",
        "capacity": "32GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 300,
        "seq_write_mbps": 90,
        "process_nm": 96,
        "nand_type": "96L TLC NAND",
        "common_failures": [
            "eMMC CMD6 timeout under low-voltage conditions",
            "Boot sector write-protect latch after abnormal reset",
        ],
    },
    "MTFC64GAZAQHD": {
        "manufacturer": "Micron",
        "type": "eMMC 5.1",
        "capacity": "64GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 300,
        "seq_write_mbps": 140,
        "process_nm": 96,
        "nand_type": "96L TLC NAND",
        "common_failures": [
            "Extended CSD register corruption in power-loss events",
            "eMMC device entering BKOPS mode stalls I/O for 100+ms",
        ],
    },

    # ── Kioxia / Toshiba UFS ──
    "THGJFGT0T44BAIL": {
        "manufacturer": "Kioxia",
        "type": "UFS 3.1",
        "capacity": "256GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2050,
        "seq_write_mbps": 1100,
        "process_nm": 112,
        "nand_type": "BiCS5 TLC NAND",
        "common_failures": [
            "UFS QueryRequest handler occasionally drops RPMB requests",
            "Slightly lower sustained write speed vs Samsung/Hynix peers",
            "Device busy flag intermittent during background GC",
        ],
    },
    "THGAF4T0N8LBAIR": {
        "manufacturer": "Kioxia",
        "type": "UFS 3.1",
        "capacity": "512GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2050,
        "seq_write_mbps": 1150,
        "process_nm": 112,
        "nand_type": "BiCS5 TLC NAND",
        "common_failures": [
            "Hibernate enter/exit latency higher than UFS spec recommendation",
            "FW quirk: health descriptor not updated until 5% wear consumed",
        ],
    },
    "THGJFGT0T25BAIL": {
        "manufacturer": "Kioxia",
        "type": "UFS 3.1",
        "capacity": "128GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2050,
        "seq_write_mbps": 1000,
        "process_nm": 112,
        "nand_type": "BiCS5 TLC NAND",
        "common_failures": [
            "Trim completion latency exceeds 10ms threshold on large ranges",
            "Power-on initialization time slightly above JEDEC spec",
        ],
    },
    "THGBMHG6C1LBAIL": {
        "manufacturer": "Kioxia",
        "type": "eMMC 5.1",
        "capacity": "32GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 280,
        "seq_write_mbps": 80,
        "process_nm": 96,
        "nand_type": "BiCS3 TLC NAND",
        "common_failures": [
            "eMMC enhanced area configuration fails on some MediaTek hosts",
            "Life time estimation reports 0x00 until 10% wear consumed",
        ],
    },
    "THGJFGT0E61BAIL": {
        "manufacturer": "Kioxia",
        "type": "UFS 4.0",
        "capacity": "256GB",
        "interface": "UFS 4.0 (HS-G5, 2L)",
        "seq_read_mbps": 4200,
        "seq_write_mbps": 2700,
        "process_nm": 162,
        "nand_type": "BiCS6 TLC NAND",
        "common_failures": [
            "UFS 4.0 gear auto-negotiation may fail with older UFSHCI v3.0",
            "Write booster exhaustion wall more pronounced than UFS 3.1 parts",
        ],
    },

    # ── Western Digital UFS ──
    "SDINDDH4-64G": {
        "manufacturer": "Western Digital",
        "type": "UFS 3.1",
        "capacity": "64GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 1800,
        "seq_write_mbps": 800,
        "process_nm": 96,
        "nand_type": "BiCS4 TLC NAND",
        "common_failures": [
            "Lower sequential write speed than competing 64GB UFS parts",
            "Background operations latency occasionally exceeds spec",
            "Vendor-unique command set not supported by all UFS host drivers",
        ],
    },
    "SDINDDH4-128G": {
        "manufacturer": "Western Digital",
        "type": "UFS 3.1",
        "capacity": "128GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2000,
        "seq_write_mbps": 1000,
        "process_nm": 96,
        "nand_type": "BiCS4 TLC NAND",
        "common_failures": [
            "UFS well-known LU mapping differs from Samsung convention",
            "Device health descriptor not fully populated in early firmware",
        ],
    },
    "SDINBDD4-256G": {
        "manufacturer": "Western Digital",
        "type": "UFS 3.1",
        "capacity": "256GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1100,
        "process_nm": 112,
        "nand_type": "BiCS5 TLC NAND",
        "common_failures": [
            "RPMB counter rollback after firmware update on some platforms",
            "Thermal management triggers more aggressively than spec allows",
        ],
    },
    "SDINBDG4-512G": {
        "manufacturer": "Western Digital",
        "type": "UFS 4.0",
        "capacity": "512GB",
        "interface": "UFS 4.0 (HS-G5, 2L)",
        "seq_read_mbps": 4200,
        "seq_write_mbps": 2800,
        "process_nm": 162,
        "nand_type": "BiCS6 TLC NAND",
        "common_failures": [
            "UFS 4.0 HS-G5 rate unstable when host phy voltage drifts",
            "First-gen UFS 4.0 firmware has GC overhead spikes",
        ],
    },

    # ── Additional Samsung entries ──
    "KLUDG2UHDC-B0D1": {
        "manufacturer": "Samsung",
        "type": "UFS 3.1",
        "capacity": "128GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1100,
        "process_nm": 128,
        "nand_type": "V-NAND TLC 6th Gen",
        "common_failures": [
            "Write booster reclaim latency visible as UI stutter",
            "UFS clock scaling issues with certain PMIC configurations",
        ],
    },
    "KLMAG2UCTA": {
        "manufacturer": "Samsung",
        "type": "eMMC 5.1",
        "capacity": "16GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 250,
        "seq_write_mbps": 50,
        "process_nm": 21,
        "nand_type": "V-NAND TLC",
        "common_failures": [
            "Low capacity fills quickly — boot loops from full storage",
            "eMMC firmware does not report accurate life_time values",
        ],
    },

    # ── Additional Kioxia entry ──
    "THGBMHG7C2LBAIL": {
        "manufacturer": "Kioxia",
        "type": "eMMC 5.1",
        "capacity": "64GB",
        "interface": "eMMC 5.1 (HS400)",
        "seq_read_mbps": 280,
        "seq_write_mbps": 120,
        "process_nm": 96,
        "nand_type": "BiCS3 TLC NAND",
        "common_failures": [
            "eMMC BKOPS scheduling conflicts with MediaTek idle task",
            "CSD register version mismatch in counterfeit replacement parts",
        ],
    },

    # ── Additional Micron entry ──
    "MT29VZZZCD9GQFSL": {
        "manufacturer": "Micron",
        "type": "UFS 3.1",
        "capacity": "128GB",
        "interface": "UFS 3.1 (HS-G4, 2L)",
        "seq_read_mbps": 2100,
        "seq_write_mbps": 1100,
        "process_nm": 176,
        "nand_type": "176L TLC NAND (B58R)",
        "common_failures": [
            "SLC write cache bypass mode not supported by all host drivers",
            "Slightly higher idle power than Samsung equivalent",
        ],
    },
}


# ---------------------------------------------------------------------------
#  Knowledge database — RAM ICs (20+ entries)
# ---------------------------------------------------------------------------
RAM_IC_DATABASE: Dict[str, Dict[str, Any]] = {
    # ── Samsung LPDDR5 / LPDDR5X ──
    "K3LK4K40BM-BGCP": {
        "manufacturer": "Samsung",
        "type": "LPDDR5",
        "capacity": "12GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "Memory controller training failure at high frequency after reflow",
            "Data corruption in bank group interleave mode at elevated temp",
        ],
    },
    "K3LKBKB0BM-MGCP": {
        "manufacturer": "Samsung",
        "type": "LPDDR5X",
        "capacity": "16GB",
        "frequency_mhz": 4266,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 68.3,
        "voltage_v": 1.05,
        "common_failures": [
            "LPDDR5X link training sensitive to PCB impedance matching",
            "Self-refresh power slightly above spec in some silicon revisions",
        ],
    },
    "K3LK7K70BM-BGCP": {
        "manufacturer": "Samsung",
        "type": "LPDDR5",
        "capacity": "8GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "Marginal data eye at corner case voltage / temperature",
            "Occasional single-bit ECC errors after prolonged thermal stress",
        ],
    },
    "K4UBE3D4AA-MGCL": {
        "manufacturer": "Samsung",
        "type": "LPDDR4X",
        "capacity": "8GB",
        "frequency_mhz": 2133,
        "bus_width": 32,
        "channels": 2,
        "bandwidth_gbps": 34.1,
        "voltage_v": 0.6,
        "common_failures": [
            "LPDDR4X DQ bus contention after improper soldering reflow",
            "Reduced reliability at temperatures above 85C (server-class load)",
        ],
    },
    "K4UBE3D4AB-MGCL": {
        "manufacturer": "Samsung",
        "type": "LPDDR4X",
        "capacity": "6GB",
        "frequency_mhz": 2133,
        "bus_width": 32,
        "channels": 2,
        "bandwidth_gbps": 34.1,
        "voltage_v": 0.6,
        "common_failures": [
            "Memory training fail on cold boot below 0C",
            "Refresh rate adjustment needed for high-ambient deployments",
        ],
    },
    "K3LKCKC0BM-MGCP": {
        "manufacturer": "Samsung",
        "type": "LPDDR5X",
        "capacity": "12GB",
        "frequency_mhz": 4266,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 68.3,
        "voltage_v": 1.05,
        "common_failures": [
            "DFE training timeout on certain Dimensity 9300 platforms",
            "Higher idle leakage than LPDDR5 predecessor",
        ],
    },

    # ── SK Hynix LPDDR ──
    "H9HCNNNFBMMLXR": {
        "manufacturer": "SK Hynix",
        "type": "LPDDR5",
        "capacity": "12GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "Self-refresh exit time exceeds spec at high temperature corner",
            "Marginal hold timing on CA bus causes intermittent training fail",
        ],
    },
    "H54G56CYRBX247": {
        "manufacturer": "SK Hynix",
        "type": "LPDDR4X",
        "capacity": "8GB",
        "frequency_mhz": 2133,
        "bus_width": 32,
        "channels": 2,
        "bandwidth_gbps": 34.1,
        "voltage_v": 0.6,
        "common_failures": [
            "Row hammer vulnerability in pre-2022 silicon revisions",
            "Occasional bank conflict causing latency spikes in gaming",
        ],
    },
    "H9HCNNNCPMMLXR-NEE": {
        "manufacturer": "SK Hynix",
        "type": "LPDDR5",
        "capacity": "8GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "MR read/write latency higher than Samsung equivalent",
            "Power-down exit causes brief data bus glitch on some boards",
        ],
    },
    "H58G66BK7BX067": {
        "manufacturer": "SK Hynix",
        "type": "LPDDR5X",
        "capacity": "16GB",
        "frequency_mhz": 4266,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 68.3,
        "voltage_v": 1.05,
        "common_failures": [
            "Channel-to-channel skew in 4ch config requires PHY calibration",
            "Elevated standby current vs specification in first batch lots",
        ],
    },
    "H54G46CYRBX267": {
        "manufacturer": "SK Hynix",
        "type": "LPDDR4X",
        "capacity": "6GB",
        "frequency_mhz": 2133,
        "bus_width": 32,
        "channels": 2,
        "bandwidth_gbps": 34.1,
        "voltage_v": 0.6,
        "common_failures": [
            "Reduced write endurance in hot climates (>40C ambient)",
            "DQS drift under sustained memory-intensive workloads",
        ],
    },

    # ── Micron LPDDR ──
    "MT62F2G32D4DS": {
        "manufacturer": "Micron",
        "type": "LPDDR5",
        "capacity": "8GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "ZQ calibration timeout at 125C junction temperature",
            "Write leveling compensation drift requires periodic re-training",
        ],
    },
    "MT53E1G32D2FW": {
        "manufacturer": "Micron",
        "type": "LPDDR4X",
        "capacity": "4GB",
        "frequency_mhz": 2133,
        "bus_width": 32,
        "channels": 2,
        "bandwidth_gbps": 34.1,
        "voltage_v": 0.6,
        "common_failures": [
            "LPDDR4X read eye marginal on boards with long trace lengths",
            "Refresh overhead increases above 85C — visible as frame drops",
        ],
    },
    "MT62F1G64D4ZS": {
        "manufacturer": "Micron",
        "type": "LPDDR5",
        "capacity": "16GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "Multi-die stack thermal coupling causes throttling",
            "Vendor-specific MR registers need explicit init on some SoCs",
        ],
    },
    "MT62F2G32D8DR": {
        "manufacturer": "Micron",
        "type": "LPDDR5X",
        "capacity": "12GB",
        "frequency_mhz": 4266,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 68.3,
        "voltage_v": 1.05,
        "common_failures": [
            "LPDDR5X DQ VREF training range tighter than LPDDR5",
            "CKE power-down latency slightly above JEDEC maximum",
        ],
    },
    "MT53D512M64D4RQ": {
        "manufacturer": "Micron",
        "type": "LPDDR4X",
        "capacity": "6GB",
        "frequency_mhz": 2133,
        "bus_width": 32,
        "channels": 2,
        "bandwidth_gbps": 34.1,
        "voltage_v": 0.6,
        "common_failures": [
            "Bus turnaround delay slightly above JEDEC spec at 2133MHz",
            "Occasional correctable ECC events after 3+ years of use",
        ],
    },
    "MT62F4G32D8DV": {
        "manufacturer": "Micron",
        "type": "LPDDR5X",
        "capacity": "16GB",
        "frequency_mhz": 4800,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 76.8,
        "voltage_v": 1.05,
        "common_failures": [
            "Highest bandwidth tier — requires careful board design",
            "Thermal throttling at peak frequency without adequate heatsinking",
        ],
    },
    "MT53E2G32D4DE": {
        "manufacturer": "Micron",
        "type": "LPDDR4X",
        "capacity": "8GB",
        "frequency_mhz": 2133,
        "bus_width": 32,
        "channels": 2,
        "bandwidth_gbps": 34.1,
        "voltage_v": 0.6,
        "common_failures": [
            "Data retention weakens above 95C junction temperature",
            "Write-to-read turnaround penalty at max frequency",
        ],
    },

    # ── Additional Samsung RAM entries ──
    "K3LK8K80CM-BGCP": {
        "manufacturer": "Samsung",
        "type": "LPDDR5",
        "capacity": "16GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "Power-on self-test occasionally fails on cold start",
            "Requires updated PHY training sequence on Snapdragon 8 Gen 3",
        ],
    },
    "K4F6E3S4HM-MGCJ": {
        "manufacturer": "Samsung",
        "type": "LPDDR4X",
        "capacity": "4GB",
        "frequency_mhz": 2133,
        "bus_width": 16,
        "channels": 2,
        "bandwidth_gbps": 17.1,
        "voltage_v": 0.6,
        "common_failures": [
            "Budget-tier 4GB die limited to 2133 MHz max",
            "Higher row activation latency than 8GB stacked counterpart",
        ],
    },

    # ── Additional SK Hynix RAM entries ──
    "H9HCNNNCRMMLXR-NEE": {
        "manufacturer": "SK Hynix",
        "type": "LPDDR5",
        "capacity": "16GB",
        "frequency_mhz": 3200,
        "bus_width": 32,
        "channels": 4,
        "bandwidth_gbps": 51.2,
        "voltage_v": 1.05,
        "common_failures": [
            "Die-to-die variation causes timing margin spread",
            "Power-down exit glitch requires PHY workaround on Exynos",
        ],
    },
}


# ---------------------------------------------------------------------------
#  UFS Life Time Estimation interpretation table (JEDEC UFS Health)
# ---------------------------------------------------------------------------
UFS_LIFE_TIME_MAP: Dict[str, str] = {
    "0x00": "Not defined / information unavailable",
    "0x01": "0% - 10% device life time used (Excellent)",
    "0x02": "10% - 20% device life time used (Very Good)",
    "0x03": "20% - 30% device life time used (Good)",
    "0x04": "30% - 40% device life time used (Good)",
    "0x05": "40% - 50% device life time used (Moderate)",
    "0x06": "50% - 60% device life time used (Moderate)",
    "0x07": "60% - 70% device life time used (Worn)",
    "0x08": "70% - 80% device life time used (Worn)",
    "0x09": "80% - 90% device life time used (Heavily Worn)",
    "0x0A": "90% - 100% device life time used (Critical)",
    "0x0B": "Exceeded intended lifetime (End of Life)",
}

# Pre-EOL information interpretation (JEDEC)
PRE_EOL_MAP: Dict[str, str] = {
    "0x00": "Not defined",
    "0x01": "Normal — device is healthy",
    "0x02": "Warning — device approaching EOL, consider replacement",
    "0x03": "Urgent — device at or past EOL, replace immediately",
}


# ---------------------------------------------------------------------------
#  Storage vendor identification from sysfs strings
# ---------------------------------------------------------------------------
STORAGE_VENDOR_MAP: Dict[str, str] = {
    "samsung": "Samsung",
    "sec": "Samsung",
    "hynix": "SK Hynix",
    "skhynix": "SK Hynix",
    "micron": "Micron",
    "kioxia": "Kioxia",
    "toshiba": "Kioxia (Toshiba)",
    "sandisk": "Western Digital (SanDisk)",
    "westerndigital": "Western Digital",
    "wdc": "Western Digital",
    "kingston": "Kingston",
    "phison": "Phison",
    "silicon_motion": "Silicon Motion",
    "ymtc": "YMTC",
    "ssstc": "SSSTC (Solid State Storage Technology)",
    "foresee": "Longsys / FORESEE",
    "biwin": "BIWIN",
    "unic": "Unicore",
    "liteon": "Lite-On",
}


# ---------------------------------------------------------------------------
#  Data classes — test results
# ---------------------------------------------------------------------------

@dataclass
class StorageInfo:
    """Information about the primary storage (UFS or eMMC)."""
    storage_type: str = ""          # UFS 3.1, UFS 4.0, eMMC 5.1
    manufacturer: str = ""
    model: str = ""
    firmware_version: str = ""
    total_capacity: str = ""
    used_space: str = ""
    free_space: str = ""
    usage_percent: float = 0.0
    life_time_a: str = ""           # UFS life time estimation A
    life_time_b: str = ""           # UFS life time estimation B
    pre_eol_info: str = ""          # Pre End-Of-Life info
    health_status: str = "Unknown"
    read_speed: str = ""
    write_speed: str = ""
    partitions: List[Dict[str, str]] = field(default_factory=list)
    common_failures: List[str] = field(default_factory=list)


@dataclass
class RAMInfo:
    """Information about the device RAM."""
    ram_type: str = ""              # LPDDR4X, LPDDR5, LPDDR5X
    total_ram: str = ""
    available_ram: str = ""
    manufacturer: str = ""
    model: str = ""
    frequency: str = ""
    channels: str = ""
    status: str = "Unknown"


@dataclass
class StorageTestResult:
    """Top-level container returned by ``detect_storage_status``."""
    connected: bool = False
    error: Optional[str] = None
    storage: StorageInfo = field(default_factory=StorageInfo)
    ram: RAMInfo = field(default_factory=RAMInfo)
    overall_health: str = "Unknown"
    health_score: int = 0
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
#  ADB helpers
# ---------------------------------------------------------------------------

def _adb(cmd: str) -> str:
    """Run an ADB shell command and return stdout.

    Executes ``adb shell <cmd>`` with a 10-second timeout.  Returns the
    stripped stdout on success, or an empty string on any failure.
    """
    full_cmd = f"adb shell {cmd}"
    logger.debug("ADB >>> %s", full_cmd)
    try:
        proc = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        output = proc.stdout.strip()
        if proc.returncode != 0:
            logger.debug("ADB cmd failed (rc=%d): %s",
                         proc.returncode, proc.stderr.strip())
            return ""
        return output
    except FileNotFoundError:
        logger.error("adb binary not found on PATH")
        return ""
    except subprocess.TimeoutExpired:
        logger.warning("ADB command timed out: %s", full_cmd)
        return ""
    except Exception as exc:
        logger.error("ADB error: %s", exc)
        return ""


def _notify(callback: ProgressCallback, pct: float, msg: str) -> None:
    """Fire the progress callback if provided."""
    if callback is not None:
        try:
            callback(pct, msg)
        except Exception:
            logger.debug("Progress callback raised; ignoring", exc_info=True)


def _parse_int(value: str, default: int = 0) -> int:
    """Safely extract an integer from a raw string."""
    try:
        cleaned = re.sub(r"[^\d\-]", "", value.split("\n")[0].strip())
        return int(cleaned) if cleaned else default
    except (ValueError, IndexError):
        return default


def _parse_size_kb(value: str, default: int = 0) -> int:
    """Parse a kB value like '12345 kB' to an integer in kB."""
    m = re.search(r"(\d+)", value)
    return int(m.group(1)) if m else default


def _kb_to_human(kb: int) -> str:
    """Convert kilobytes to a human-readable string (MB or GB)."""
    if kb <= 0:
        return "0 KB"
    if kb < 1024:
        return f"{kb} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.1f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


# ---------------------------------------------------------------------------
#  Step 1 — ADB connection check
# ---------------------------------------------------------------------------

def _check_adb_connection(callback: ProgressCallback) -> Tuple[bool, str]:
    """Verify ADB connectivity.  Returns (connected, error_or_empty)."""
    _notify(callback, 0.0, "Checking ADB connection...")
    try:
        proc = subprocess.run(
            "adb devices",
            capture_output=True,
            text=True,
            timeout=10,
            shell=True,
        )
        output = proc.stdout.strip()
    except FileNotFoundError:
        return False, "adb binary not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "adb devices timed out"
    except Exception as exc:
        return False, f"adb error: {exc}"

    lines = [ln for ln in output.splitlines() if "\tdevice" in ln]
    if not lines:
        unauthorized = [ln for ln in output.splitlines() if "\tunauthorized" in ln]
        if unauthorized:
            return False, "Device connected but USB Debugging not authorized"
        return False, "No ADB device detected"

    serial = lines[0].split("\t")[0]
    logger.info("ADB device connected: %s", serial)
    _notify(callback, 3.0, f"ADB connected — serial {serial}")
    return True, ""


# ---------------------------------------------------------------------------
#  Step 2 — Storage type detection (UFS vs eMMC)
# ---------------------------------------------------------------------------

def _detect_storage_type(callback: ProgressCallback) -> Tuple[str, Dict[str, str]]:
    """Determine whether the device uses UFS or eMMC and gather raw info.

    Returns
    -------
    tuple[str, dict]
        ``("UFS" | "eMMC" | "Unknown", raw_properties_dict)``
    """
    _notify(callback, 5.0, "Detecting storage type (UFS vs eMMC)...")
    raw: Dict[str, str] = {}

    # ── Try UFS paths first ──
    ufs_model = _adb("cat /sys/class/block/sda/device/model")
    ufs_rev = _adb("cat /sys/class/block/sda/device/rev")
    ufs_vendor = _adb("cat /sys/class/block/sda/device/vendor")

    if ufs_model:
        raw["ufs_model"] = ufs_model
        raw["ufs_rev"] = ufs_rev
        raw["ufs_vendor"] = ufs_vendor

        # UFS HBA info
        hba_info = _adb("cat /sys/kernel/debug/ufshcd0/show_hba")
        if hba_info:
            raw["ufs_hba"] = hba_info

        # UFS health descriptors
        life_a = _adb("cat /sys/class/block/sda/device/life_time")
        if life_a:
            raw["ufs_life_time"] = life_a

        # Try individual health descriptor files
        for attr in ["life_time_a", "life_time_b", "life_time_est_a",
                     "life_time_est_b", "pre_eol_info"]:
            val = _adb(f"cat /sys/class/block/sda/device/{attr}")
            if val:
                raw[f"ufs_{attr}"] = val

        # Health descriptor directory
        health_dir = _adb("ls /sys/class/block/sda/device/health_descriptor/ 2>/dev/null")
        if health_dir:
            for fname in health_dir.splitlines():
                fname = fname.strip()
                if fname:
                    val = _adb(f"cat /sys/class/block/sda/device/health_descriptor/{fname}")
                    if val:
                        raw[f"ufs_health_{fname}"] = val

        # UFS string descriptors
        mfr_name = _adb(
            "cat /sys/bus/platform/drivers/ufshcd*/*/string_descriptors/manufacturer_name"
        )
        if mfr_name:
            raw["ufs_mfr_name"] = mfr_name

        product_name = _adb(
            "cat /sys/bus/platform/drivers/ufshcd*/*/string_descriptors/product_name"
        )
        if product_name:
            raw["ufs_product_name"] = product_name

        # UFS unique ID
        unique_id = _adb(
            "cat /sys/devices/platform/*/host*/scsi_host/host*/unique_id 2>/dev/null"
        )
        if unique_id:
            raw["ufs_unique_id"] = unique_id

        _notify(callback, 10.0, f"UFS storage detected — model: {ufs_model}")
        return "UFS", raw

    # ── Try eMMC paths ──
    emmc_name = _adb("cat /sys/class/block/mmcblk0/device/name")
    emmc_type = _adb("cat /sys/class/block/mmcblk0/device/type")
    emmc_cid = _adb("cat /sys/class/block/mmcblk0/device/cid")
    emmc_csd = _adb("cat /sys/class/block/mmcblk0/device/csd")
    emmc_fwrev = _adb("cat /sys/class/block/mmcblk0/device/fwrev")

    if emmc_name or emmc_cid:
        raw["emmc_name"] = emmc_name
        raw["emmc_type"] = emmc_type
        raw["emmc_cid"] = emmc_cid
        raw["emmc_csd"] = emmc_csd
        raw["emmc_fwrev"] = emmc_fwrev

        # eMMC health
        emmc_life = _adb("cat /sys/class/block/mmcblk0/device/life_time")
        if emmc_life:
            raw["emmc_life_time"] = emmc_life

        emmc_pre_eol = _adb("cat /sys/class/block/mmcblk0/device/pre_eol_info")
        if emmc_pre_eol:
            raw["emmc_pre_eol_info"] = emmc_pre_eol

        # eMMC extended CSD (some kernels expose this)
        emmc_ext_csd = _adb("cat /sys/class/block/mmcblk0/device/ext_csd 2>/dev/null")
        if emmc_ext_csd:
            raw["emmc_ext_csd"] = emmc_ext_csd[:500]

        _notify(callback, 10.0, f"eMMC storage detected — name: {emmc_name}")
        return "eMMC", raw

    _notify(callback, 10.0, "Storage type could not be determined")
    return "Unknown", raw


# ---------------------------------------------------------------------------
#  Step 3 — Parse storage details
# ---------------------------------------------------------------------------

def _identify_storage_ic(model: str, vendor: str) -> Optional[Dict[str, Any]]:
    """Match a storage model string against the IC database.

    Performs exact match first, then partial / substring matching.
    """
    model_clean = model.strip().upper()
    vendor_clean = vendor.strip().upper()

    # Exact match
    for part_number, info in STORAGE_IC_DATABASE.items():
        if part_number.upper() == model_clean:
            return info

    # Partial match on model
    for part_number, info in STORAGE_IC_DATABASE.items():
        pn_upper = part_number.upper()
        if pn_upper in model_clean or model_clean in pn_upper:
            return info

    # Match by vendor + type heuristics
    for part_number, info in STORAGE_IC_DATABASE.items():
        if info["manufacturer"].upper() in vendor_clean:
            return info

    return None


def _resolve_vendor(vendor_str: str) -> str:
    """Resolve a vendor string to a clean manufacturer name."""
    if not vendor_str:
        return "Unknown"
    lower = vendor_str.strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    for key, name in STORAGE_VENDOR_MAP.items():
        if key in lower:
            return name
    return vendor_str.strip()


def _parse_life_time_value(raw: str) -> str:
    """Interpret a UFS/eMMC life_time hex value into a human string."""
    raw = raw.strip()
    # May be in format "0x01 0x02" (two values) or just "0x01"
    parts = raw.split()
    descriptions = []
    for part in parts:
        part = part.strip().lower()
        if part in UFS_LIFE_TIME_MAP:
            descriptions.append(UFS_LIFE_TIME_MAP[part])
        elif part.isdigit():
            hex_val = f"0x{int(part):02X}"
            descriptions.append(UFS_LIFE_TIME_MAP.get(hex_val, f"Value {part}"))
        else:
            descriptions.append(f"Raw: {part}")
    return " | ".join(descriptions) if descriptions else raw


def _parse_pre_eol_value(raw: str) -> str:
    """Interpret a pre-EOL information byte."""
    raw = raw.strip().lower()
    if raw in PRE_EOL_MAP:
        return PRE_EOL_MAP[raw]
    # Try numeric
    try:
        val = int(raw, 0)
        hex_str = f"0x{val:02X}"
        return PRE_EOL_MAP.get(hex_str, f"Unknown ({raw})")
    except (ValueError, TypeError):
        return f"Raw: {raw}"


def _parse_storage_info(
    callback: ProgressCallback,
    storage_type: str,
    raw: Dict[str, str],
) -> StorageInfo:
    """Build a StorageInfo dataclass from raw sysfs data."""
    _notify(callback, 12.0, "Parsing storage controller information...")
    info = StorageInfo()
    info.storage_type = storage_type

    if storage_type == "UFS":
        info.model = raw.get("ufs_model", "").strip()
        info.firmware_version = raw.get("ufs_rev", "").strip()
        vendor_raw = raw.get("ufs_vendor", "")
        info.manufacturer = _resolve_vendor(vendor_raw)

        # Override manufacturer from string descriptor if available
        mfr_name = raw.get("ufs_mfr_name", "").strip()
        if mfr_name:
            info.manufacturer = mfr_name

        # Product name override
        product_name = raw.get("ufs_product_name", "").strip()
        if product_name:
            info.model = product_name

        # Life time
        life_time_raw = raw.get("ufs_life_time", "")
        if life_time_raw:
            parts = life_time_raw.strip().split()
            if len(parts) >= 2:
                info.life_time_a = _parse_life_time_value(parts[0])
                info.life_time_b = _parse_life_time_value(parts[1])
            elif len(parts) == 1:
                info.life_time_a = _parse_life_time_value(parts[0])

        # Individual life_time attrs override combined
        lt_a = raw.get("ufs_life_time_a", raw.get("ufs_life_time_est_a", ""))
        if lt_a:
            info.life_time_a = _parse_life_time_value(lt_a)
        lt_b = raw.get("ufs_life_time_b", raw.get("ufs_life_time_est_b", ""))
        if lt_b:
            info.life_time_b = _parse_life_time_value(lt_b)

        # Pre-EOL
        pre_eol = raw.get("ufs_pre_eol_info", "")
        if pre_eol:
            info.pre_eol_info = _parse_pre_eol_value(pre_eol)

        # Health from health_descriptor
        for key, val in raw.items():
            if key.startswith("ufs_health_"):
                attr_name = key.replace("ufs_health_", "")
                if "life_time_est_a" in attr_name and not info.life_time_a:
                    info.life_time_a = _parse_life_time_value(val)
                elif "life_time_est_b" in attr_name and not info.life_time_b:
                    info.life_time_b = _parse_life_time_value(val)
                elif "pre_eol" in attr_name and not info.pre_eol_info:
                    info.pre_eol_info = _parse_pre_eol_value(val)

        # UFS type detection from HBA or model string
        hba = raw.get("ufs_hba", "")
        if "HS-G5" in hba or "UFS4" in hba.upper() or "4.0" in info.model:
            info.storage_type = "UFS 4.0"
        elif "HS-G4" in hba or "UFS3" in hba.upper() or "3.1" in info.model:
            info.storage_type = "UFS 3.1"
        elif "HS-G3" in hba or "UFS2" in hba.upper() or "2.1" in info.model:
            info.storage_type = "UFS 2.1"
        else:
            info.storage_type = "UFS"

        # Detect read/write speed from HBA gear info
        if "HS-G5" in hba or info.storage_type == "UFS 4.0":
            info.read_speed = "~4200 MB/s (sequential)"
            info.write_speed = "~2800 MB/s (sequential)"
        elif "HS-G4" in hba or info.storage_type == "UFS 3.1":
            info.read_speed = "~2100 MB/s (sequential)"
            info.write_speed = "~1200 MB/s (sequential)"
        elif "HS-G3" in hba or info.storage_type == "UFS 2.1":
            info.read_speed = "~850 MB/s (sequential)"
            info.write_speed = "~250 MB/s (sequential)"

    elif storage_type == "eMMC":
        info.model = raw.get("emmc_name", "").strip()
        info.firmware_version = raw.get("emmc_fwrev", "").strip()
        emmc_type = raw.get("emmc_type", "").strip()

        # Decode CID for manufacturer
        cid = raw.get("emmc_cid", "").strip()
        if cid and len(cid) >= 4:
            mfr_code = cid[:2].upper()
            emmc_mfr_map = {
                "15": "Samsung",
                "45": "Western Digital (SanDisk)",
                "90": "SK Hynix",
                "13": "Micron",
                "FE": "Micron",
                "11": "Kioxia (Toshiba)",
                "70": "Kingston",
                "9B": "YMTC",
                "D6": "FORESEE",
            }
            info.manufacturer = emmc_mfr_map.get(mfr_code, f"MID 0x{mfr_code}")

        # eMMC subtype
        if "mmc" in emmc_type.lower() or emmc_type == "":
            info.storage_type = "eMMC 5.1"
        else:
            info.storage_type = f"eMMC ({emmc_type})"

        # eMMC life time
        emmc_life = raw.get("emmc_life_time", "")
        if emmc_life:
            parts = emmc_life.strip().split()
            if len(parts) >= 2:
                info.life_time_a = _parse_life_time_value(parts[0])
                info.life_time_b = _parse_life_time_value(parts[1])
            elif len(parts) == 1:
                info.life_time_a = _parse_life_time_value(parts[0])

        # Pre-EOL
        emmc_pre_eol = raw.get("emmc_pre_eol_info", "")
        if emmc_pre_eol:
            info.pre_eol_info = _parse_pre_eol_value(emmc_pre_eol)

        # eMMC speed
        info.read_speed = "~300 MB/s (sequential, HS400)"
        info.write_speed = "~90-170 MB/s (sequential)"

    # Match against IC database
    ic_match = _identify_storage_ic(info.model, info.manufacturer)
    if ic_match:
        info.common_failures = ic_match.get("common_failures", [])
        if not info.manufacturer or info.manufacturer == "Unknown":
            info.manufacturer = ic_match.get("manufacturer", info.manufacturer)
        if not info.storage_type or info.storage_type in ("UFS", "eMMC"):
            info.storage_type = ic_match.get("type", info.storage_type)
        info.total_capacity = ic_match.get("capacity", info.total_capacity)
        if ic_match.get("seq_read_mbps"):
            info.read_speed = f"~{ic_match['seq_read_mbps']} MB/s (sequential)"
        if ic_match.get("seq_write_mbps"):
            info.write_speed = f"~{ic_match['seq_write_mbps']} MB/s (sequential)"

    _notify(callback, 20.0,
            f"Storage IC: {info.manufacturer} {info.model} [{info.storage_type}]")
    return info


# ---------------------------------------------------------------------------
#  Step 4 — Disk usage and partitions
# ---------------------------------------------------------------------------

def _parse_disk_usage(callback: ProgressCallback, info: StorageInfo) -> StorageInfo:
    """Read disk usage (``df -h``) and partition table (``/proc/partitions``)."""
    _notify(callback, 22.0, "Reading disk usage (df -h)...")

    df_output = _adb("df -h")
    if df_output:
        # Parse df output for /data partition (main user storage)
        for line in df_output.splitlines():
            cols = line.split()
            if len(cols) >= 6:
                mount_point = cols[-1]
                if mount_point in ("/data", "/storage/emulated"):
                    info.total_capacity = info.total_capacity or cols[1]
                    info.used_space = cols[2]
                    info.free_space = cols[3]
                    # Parse usage percent
                    pct_str = cols[4].replace("%", "")
                    try:
                        info.usage_percent = float(pct_str)
                    except ValueError:
                        pass
                    break

        # If /data not found, try the largest partition
        if not info.used_space:
            largest_total = 0
            for line in df_output.splitlines():
                cols = line.split()
                if len(cols) >= 6 and cols[0].startswith("/"):
                    try:
                        total_str = cols[1].upper()
                        multiplier = 1
                        if total_str.endswith("G"):
                            multiplier = 1024 * 1024
                        elif total_str.endswith("M"):
                            multiplier = 1024
                        elif total_str.endswith("T"):
                            multiplier = 1024 * 1024 * 1024
                        num = float(re.sub(r"[^\d.]", "", total_str))
                        total_kb = int(num * multiplier)
                        if total_kb > largest_total:
                            largest_total = total_kb
                            info.total_capacity = info.total_capacity or cols[1]
                            info.used_space = cols[2]
                            info.free_space = cols[3]
                            pct_str = cols[4].replace("%", "")
                            try:
                                info.usage_percent = float(pct_str)
                            except ValueError:
                                pass
                    except (ValueError, IndexError):
                        continue

    # Parse /proc/partitions for partition list
    _notify(callback, 25.0, "Reading partition table...")
    partitions_raw = _adb("cat /proc/partitions")
    if partitions_raw:
        info.partitions = _parse_partition_table(partitions_raw)

    # Also try dumpsys diskstats for additional info
    diskstats = _adb("dumpsys diskstats")
    if diskstats:
        # Extract total/free from diskstats if df didn't give us good data
        for line in diskstats.splitlines():
            if "Data-Free" in line:
                m = re.search(r"(\d+)", line)
                if m and not info.free_space:
                    info.free_space = _kb_to_human(int(m.group(1)))
            elif "Data-Total" in line:
                m = re.search(r"(\d+)", line)
                if m and not info.total_capacity:
                    info.total_capacity = _kb_to_human(int(m.group(1)))

    _notify(callback, 30.0,
            f"Disk usage: {info.used_space} used / {info.free_space} free "
            f"({info.usage_percent}%)")
    return info


def _parse_partition_table(raw: str) -> List[Dict[str, str]]:
    """Parse ``/proc/partitions`` output into a list of partition dicts."""
    partitions: List[Dict[str, str]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("major"):
            continue
        parts = line.split()
        if len(parts) >= 4:
            size_kb = _parse_int(parts[2])
            partitions.append({
                "major": parts[0],
                "minor": parts[1],
                "blocks": parts[2],
                "name": parts[3],
                "size_human": _kb_to_human(size_kb),
            })
    return partitions


# ---------------------------------------------------------------------------
#  Step 5 — Storage health assessment
# ---------------------------------------------------------------------------

def _assess_storage_health(
    callback: ProgressCallback,
    info: StorageInfo,
) -> Tuple[str, int, List[str]]:
    """Compute storage health status, score, and warnings.

    Returns
    -------
    tuple[str, int, list[str]]
        ``(health_status, score_0_to_100, warning_list)``
    """
    _notify(callback, 32.0, "Assessing storage health...")
    score = 100
    warnings: List[str] = []

    # ── Pre-EOL assessment ──
    pre_eol_lower = info.pre_eol_info.lower()
    if "urgent" in pre_eol_lower or "replace" in pre_eol_lower:
        score -= 60
        warnings.append(
            f"CRITICAL: Pre-EOL status is URGENT — {info.pre_eol_info}. "
            "Storage IC should be replaced immediately."
        )
    elif "warning" in pre_eol_lower or "approaching" in pre_eol_lower:
        score -= 30
        warnings.append(
            f"WARNING: Pre-EOL status indicates approaching end-of-life — "
            f"{info.pre_eol_info}. Plan replacement."
        )

    # ── Life time A/B assessment ──
    for label, lt_str in [("A", info.life_time_a), ("B", info.life_time_b)]:
        lt_lower = lt_str.lower()
        if "end of life" in lt_lower or "exceeded" in lt_lower:
            score -= 40
            warnings.append(
                f"CRITICAL: Life Time Estimation {label} indicates device has "
                f"exceeded intended lifetime — {lt_str}"
            )
        elif "critical" in lt_lower or "90%" in lt_str:
            score -= 30
            warnings.append(
                f"CRITICAL: Life Time Estimation {label} is at 90-100% — {lt_str}"
            )
        elif "heavily worn" in lt_lower or "80%" in lt_str:
            score -= 20
            warnings.append(
                f"WARNING: Life Time Estimation {label} shows 70-80% wear — {lt_str}"
            )
        elif "worn" in lt_lower or "60%" in lt_str or "70%" in lt_str:
            score -= 10
            warnings.append(
                f"NOTICE: Life Time Estimation {label} shows moderate wear — {lt_str}"
            )

    # ── Disk usage assessment ──
    if info.usage_percent >= 95:
        score -= 15
        warnings.append(
            f"Storage is {info.usage_percent}% full — critically low free space. "
            "Device may become slow or unstable."
        )
    elif info.usage_percent >= 85:
        score -= 5
        warnings.append(
            f"Storage is {info.usage_percent}% full — low free space may impact "
            "performance and background operations."
        )

    # ── Known IC failures ──
    if info.common_failures:
        warnings.append(
            f"Known issues for this storage IC ({info.model}): "
            + "; ".join(info.common_failures[:2])
        )

    # Clamp score
    score = max(0, min(100, score))

    # Derive health status string
    if score >= 85:
        health = "Excellent"
    elif score >= 70:
        health = "Good"
    elif score >= 50:
        health = "Fair"
    elif score >= 30:
        health = "Poor"
    else:
        health = "Critical"

    info.health_status = health

    _notify(callback, 38.0,
            f"Storage health: {health} (score {score}/100), "
            f"{len(warnings)} warning(s)")
    return health, score, warnings


# ---------------------------------------------------------------------------
#  Step 6 — RAM detection and parsing
# ---------------------------------------------------------------------------

def _detect_ram_info(callback: ProgressCallback) -> RAMInfo:
    """Read RAM type, capacity, and manufacturer from the device."""
    _notify(callback, 40.0, "Reading RAM information...")
    ram = RAMInfo()

    # ── /proc/meminfo ──
    meminfo = _adb("cat /proc/meminfo")
    if meminfo:
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                total_kb = _parse_size_kb(line)
                ram.total_ram = _kb_to_human(total_kb)
            elif line.startswith("MemAvailable:"):
                avail_kb = _parse_size_kb(line)
                ram.available_ram = _kb_to_human(avail_kb)

    # ── RAM type detection from multiple sources ──

    # Method 1: getprop
    chipname = _adb("getprop ro.hardware.chipname")
    dram_info = _adb("getprop ro.boot.hardware.ddr")
    dram_type_prop = _adb("getprop ro.boot.ddr_type")
    dram_manufacturer = _adb("getprop ro.boot.ddr_manufacturer")
    dram_size = _adb("getprop ro.boot.ddr_size")

    if dram_info:
        ram.ram_type = _classify_ram_type(dram_info)
    elif dram_type_prop:
        ram.ram_type = _classify_ram_type(dram_type_prop)

    if dram_manufacturer:
        ram.manufacturer = dram_manufacturer.strip()

    # Method 2: Kernel DMI / device-tree info
    if not ram.ram_type:
        dram_type_dt = _adb("cat /proc/device-tree/memory/ddr_type 2>/dev/null")
        if dram_type_dt:
            ram.ram_type = _classify_ram_type(dram_type_dt)

    # Method 3: dumpsys meminfo for additional context
    dumpsys_mem = _adb("dumpsys meminfo")
    if dumpsys_mem:
        m = re.search(r"Total RAM:\s*([\d,]+)\s*kB", dumpsys_mem)
        if m and not ram.total_ram:
            total_kb = int(m.group(1).replace(",", ""))
            ram.total_ram = _kb_to_human(total_kb)

    # Method 4: /sys paths for DRAM frequency
    for freq_path in [
        "/sys/devices/platform/dmc/devfreq/devfreq*/cur_freq",
        "/sys/kernel/debug/clk/bimc_clk/clk_rate",
        "/sys/kernel/debug/clk/ddr_clk/clk_rate",
        "/sys/devices/system/cpu/bus_dcvs/DDR/cur_freq",
        "/sys/class/devfreq/*/cur_freq",
    ]:
        freq_raw = _adb(f"cat {freq_path} 2>/dev/null")
        if freq_raw:
            freq_val = _parse_int(freq_raw)
            if freq_val > 0:
                # Frequency may be in Hz or kHz
                if freq_val > 1000000:
                    freq_mhz = freq_val / 1000000
                elif freq_val > 1000:
                    freq_mhz = freq_val / 1000
                else:
                    freq_mhz = freq_val
                ram.frequency = f"{freq_mhz:.0f} MHz"

                # Infer RAM type from frequency if not yet known
                if not ram.ram_type:
                    ram.ram_type = _infer_ram_type_from_freq(freq_mhz)
                break

    # Method 5: Try to identify RAM IC from model string
    ic_match = _identify_ram_ic(ram.manufacturer, ram.ram_type, ram.total_ram)
    if ic_match:
        ram.model = ic_match.get("model", "")
        if not ram.manufacturer or ram.manufacturer == "Unknown":
            ram.manufacturer = ic_match.get("manufacturer", ram.manufacturer)
        if not ram.ram_type:
            ram.ram_type = ic_match.get("type", "")
        if not ram.frequency and ic_match.get("frequency_mhz"):
            ram.frequency = f"{ic_match['frequency_mhz']} MHz"
        if ic_match.get("channels"):
            ram.channels = f"{ic_match['channels']}ch"

    # Resolve manufacturer name
    if ram.manufacturer:
        ram.manufacturer = _resolve_ram_manufacturer(ram.manufacturer)

    # RAM status assessment
    if ram.total_ram and ram.available_ram:
        total_kb_val = _parse_size_kb(ram.total_ram.replace("GB", "000000 kB")
                                       .replace("MB", "000 kB"))
        avail_kb_val = _parse_size_kb(ram.available_ram.replace("GB", "000000 kB")
                                       .replace("MB", "000 kB"))
        if total_kb_val > 0 and avail_kb_val > 0:
            usage_pct = (1 - avail_kb_val / total_kb_val) * 100
            if usage_pct > 90:
                ram.status = "Critical — very low available RAM"
            elif usage_pct > 75:
                ram.status = "High usage"
            else:
                ram.status = "OK"
        else:
            ram.status = "OK" if ram.total_ram else "Unknown"
    else:
        ram.status = "OK" if ram.total_ram else "Unknown"

    _notify(callback, 55.0,
            f"RAM: {ram.total_ram} {ram.ram_type} ({ram.manufacturer}), "
            f"available {ram.available_ram}")
    return ram


def _classify_ram_type(raw: str) -> str:
    """Classify RAM type from a raw string."""
    lower = raw.strip().lower()
    if "lpddr5x" in lower:
        return "LPDDR5X"
    if "lpddr5" in lower:
        return "LPDDR5"
    if "lpddr4x" in lower:
        return "LPDDR4X"
    if "lpddr4" in lower:
        return "LPDDR4"
    if "lpddr3" in lower:
        return "LPDDR3"
    if "ddr5" in lower:
        return "LPDDR5"
    if "ddr4" in lower:
        return "LPDDR4X"
    # Numeric codes used by some bootloaders
    type_codes = {
        "7": "LPDDR4X",
        "8": "LPDDR5",
        "9": "LPDDR5X",
        "6": "LPDDR4",
        "5": "LPDDR3",
    }
    stripped = raw.strip()
    if stripped in type_codes:
        return type_codes[stripped]
    return raw.strip() if raw.strip() else ""


def _infer_ram_type_from_freq(freq_mhz: float) -> str:
    """Infer RAM type from operating frequency."""
    if freq_mhz >= 4000:
        return "LPDDR5X"
    if freq_mhz >= 2700:
        return "LPDDR5"
    if freq_mhz >= 1800:
        return "LPDDR4X"
    if freq_mhz >= 1500:
        return "LPDDR4"
    if freq_mhz >= 800:
        return "LPDDR3"
    return ""


def _identify_ram_ic(
    manufacturer: str,
    ram_type: str,
    total_ram: str,
) -> Optional[Dict[str, Any]]:
    """Attempt to match RAM IC from the database by manufacturer/type/capacity."""
    if not manufacturer and not ram_type:
        return None

    mfr_lower = (manufacturer or "").lower()
    type_lower = (ram_type or "").lower()
    ram_lower = (total_ram or "").lower()

    best_match: Optional[Dict[str, Any]] = None
    best_score = 0

    for part_number, info in RAM_IC_DATABASE.items():
        score = 0
        if info["manufacturer"].lower() in mfr_lower or mfr_lower in info["manufacturer"].lower():
            score += 3
        if info["type"].lower() == type_lower:
            score += 2
        # Match capacity
        cap_lower = info.get("capacity", "").lower()
        if cap_lower and cap_lower in ram_lower:
            score += 1

        if score > best_score:
            best_score = score
            best_match = {**info, "model": part_number}

    return best_match if best_score >= 2 else None


def _resolve_ram_manufacturer(raw: str) -> str:
    """Clean up RAM manufacturer string."""
    lower = raw.strip().lower()
    mfr_map = {
        "samsung": "Samsung",
        "sec": "Samsung",
        "hynix": "SK Hynix",
        "skhynix": "SK Hynix",
        "micron": "Micron",
        "elpida": "Micron (Elpida)",
        "nanya": "Nanya Technology",
        "winbond": "Winbond",
    }
    for key, name in mfr_map.items():
        if key in lower:
            return name
    return raw.strip() if raw.strip() else "Unknown"


# ---------------------------------------------------------------------------
#  Step 7 — Overall health and report generation
# ---------------------------------------------------------------------------

def _generate_overall_health(
    storage_health: str,
    storage_score: int,
    ram_info: RAMInfo,
    warnings: List[str],
) -> Tuple[str, int]:
    """Combine storage and RAM health into an overall verdict.

    Returns
    -------
    tuple[str, int]
        ``(overall_health_string, combined_score_0_to_100)``
    """
    # Storage is weighted 80%, RAM 20%
    ram_score = 100
    ram_status_lower = ram_info.status.lower()
    if "critical" in ram_status_lower:
        ram_score = 30
    elif "high" in ram_status_lower:
        ram_score = 60
    elif "unknown" in ram_status_lower:
        ram_score = 70

    combined_score = int(storage_score * 0.8 + ram_score * 0.2)
    combined_score = max(0, min(100, combined_score))

    if combined_score >= 85:
        overall = "Excellent"
    elif combined_score >= 70:
        overall = "Good"
    elif combined_score >= 50:
        overall = "Fair"
    elif combined_score >= 30:
        overall = "Poor"
    else:
        overall = "Critical"

    return overall, combined_score


def _generate_report(
    result: StorageTestResult,
) -> str:
    """Generate a human-readable multi-line report for the technician."""
    lines: List[str] = []
    s = result.storage
    r = result.ram

    lines.append(f"Storage & RAM Health: {result.overall_health} "
                 f"(Score {result.health_score}/100)")
    lines.append("")

    # ── Storage ──
    lines.append("== STORAGE ==")
    lines.append(f"  Type           : {s.storage_type}")
    lines.append(f"  Manufacturer   : {s.manufacturer}")
    lines.append(f"  Model          : {s.model}")
    lines.append(f"  Firmware       : {s.firmware_version}")
    lines.append(f"  Capacity       : {s.total_capacity}")
    lines.append(f"  Used / Free    : {s.used_space} / {s.free_space} "
                 f"({s.usage_percent}% used)")
    lines.append(f"  Read Speed     : {s.read_speed}")
    lines.append(f"  Write Speed    : {s.write_speed}")
    lines.append(f"  Health Status  : {s.health_status}")
    lines.append(f"  Life Time A    : {s.life_time_a}")
    lines.append(f"  Life Time B    : {s.life_time_b}")
    lines.append(f"  Pre-EOL Info   : {s.pre_eol_info}")
    lines.append("")

    if s.partitions:
        lines.append(f"  Partitions ({len(s.partitions)}):")
        for p in s.partitions[:15]:
            lines.append(f"    {p['name']:>20s}  {p['size_human']:>10s}")
        if len(s.partitions) > 15:
            lines.append(f"    ... and {len(s.partitions) - 15} more")
        lines.append("")

    # ── RAM ──
    lines.append("== RAM ==")
    lines.append(f"  Type           : {r.ram_type}")
    lines.append(f"  Manufacturer   : {r.manufacturer}")
    lines.append(f"  Model          : {r.model}")
    lines.append(f"  Total          : {r.total_ram}")
    lines.append(f"  Available      : {r.available_ram}")
    lines.append(f"  Frequency      : {r.frequency}")
    lines.append(f"  Channels       : {r.channels}")
    lines.append(f"  Status         : {r.status}")
    lines.append("")

    # ── Warnings ──
    if result.warnings:
        lines.append("== WARNINGS ==")
        for i, w in enumerate(result.warnings, 1):
            lines.append(f"  {i}. {w}")
    else:
        lines.append("No warnings.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_storage_status(
    callback: ProgressCallback = None,
) -> StorageTestResult:
    """Run the full storage and RAM diagnostic sequence.

    Parameters
    ----------
    callback : optional
        A callable ``(pct: float, msg: str) -> None`` invoked with progress
        updates.  *pct* ranges from 0 to 100.

    Returns
    -------
    StorageTestResult
        Populated result dataclass with storage info, RAM info, overall
        health verdict, score, and warnings.
    """
    result = StorageTestResult()
    logger.info("Starting storage & RAM diagnostic sequence")

    # ── Step 1: ADB connection ──
    connected, err = _check_adb_connection(callback)
    if not connected:
        result.connected = False
        result.error = err
        result.overall_health = f"UNABLE TO TEST — {err}"
        _notify(callback, 100.0, f"Test aborted: {err}")
        return result
    result.connected = True

    try:
        # ── Step 2: Storage type detection ──
        storage_type, raw_props = _detect_storage_type(callback)

        # ── Step 3: Parse storage details ──
        result.storage = _parse_storage_info(callback, storage_type, raw_props)

        # ── Step 4: Disk usage and partitions ──
        result.storage = _parse_disk_usage(callback, result.storage)

        # ── Step 5: Storage health assessment ──
        health_str, health_score, warnings = _assess_storage_health(
            callback, result.storage
        )

        # ── Step 6: RAM detection ──
        result.ram = _detect_ram_info(callback)

        # ── Step 7: Overall health ──
        _notify(callback, 60.0, "Computing overall health...")
        result.overall_health, result.health_score = _generate_overall_health(
            health_str, health_score, result.ram, warnings
        )
        result.warnings = warnings

        # Add RAM warnings if needed
        if "critical" in result.ram.status.lower():
            result.warnings.append(
                f"RAM usage is critically high — {result.ram.available_ram} available "
                f"of {result.ram.total_ram} total. Check for memory leaks or bloatware."
            )
        elif "high" in result.ram.status.lower():
            result.warnings.append(
                f"RAM usage is elevated — {result.ram.available_ram} available "
                f"of {result.ram.total_ram}. Consider closing background apps."
            )

        # Generate report
        _notify(callback, 70.0, "Generating report...")
        report = _generate_report(result)
        logger.info("Storage test report:\n%s", report)

    except Exception as exc:
        logger.exception("Storage & RAM diagnostic sequence failed")
        result.error = str(exc)
        result.overall_health = f"TEST ERROR — {exc}"

    _notify(callback, 100.0, "Storage & RAM diagnostic complete")
    logger.info("Storage & RAM diagnostic sequence finished — "
                "health=%s, score=%d", result.overall_health, result.health_score)
    return result


# ---------------------------------------------------------------------------
#  CLI convenience
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys
    from dataclasses import asdict

    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    def _cli_callback(pct: float, msg: str) -> None:
        print(f"  [{pct:5.1f}%] {msg}")

    print("=" * 70)
    print("  Storage & RAM Tester — Mooxy AI Fault Detector")
    print("=" * 70)
    print()

    test_result = detect_storage_status(callback=_cli_callback)

    print()
    print("-" * 70)
    print(_generate_report(test_result))
    print("-" * 70)

    if "--json" in sys.argv:
        print()
        print(json.dumps(asdict(test_result), indent=2, default=str))
