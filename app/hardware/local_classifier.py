"""
Local Fault Classifier — Offline AI analysis using the 200+ rule engine patterns.

No internet required. No LLM required. Uses the existing rule_engine.py patterns
plus heuristic scoring to produce structured analysis results in the SAME JSON
format as the Groq/Ollama analyzers. This means the GUI can render results
identically regardless of which backend produced them.

This is the last fallback in the chain:
  Groq (cloud) → Ollama (local LLM) → LocalClassifier (pure rules)
"""

import re
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

from app.hardware.rule_engine import RuleEngine, MatchedFault, FAULT_RULES
from app.hardware.ai_analyzer import (
    AIAnalysisResult, detect_log_type, _smart_extract,
    DMESG_LOG_PATTERN,
)


# ── Boot log pattern database (supplements rule_engine for UART logs) ──────

BOOT_PATTERNS = {
    # Chipset identification
    "chipset": [
        (r"MT\d{4}[A-Z]?", "MediaTek"),
        (r"SDM\d{3}", "Qualcomm"),
        (r"SM\d{4}", "Qualcomm"),
        (r"MSM\d{4}", "Qualcomm"),
        (r"Exynos\s*\d{4}", "Samsung"),
        (r"A\d{2}\s*Bionic|Apple\s*[A-Z]\d+", "Apple"),
        (r"sc\d{4}", "Unisoc"),
    ],
    # PMIC identification
    "pmic": [
        (r"MT\d{4}[A-Z]?\s*PMIC|pmic.*MT\d{4}", "MediaTek PMIC"),
        (r"PM\d{4}", "Qualcomm PMIC"),
        (r"S2MP[A-Z]\d+", "Samsung PMIC"),
    ],
    # Critical errors
    "critical_errors": [
        (r"DRAM.*fail|dram_init.*error|EMI.*fail", "RAM/DRAM initialization failure"),
        (r"eMMC.*error|UFS.*fail|storage.*fail|mmc.*error", "Storage failure"),
        (r"PMIC.*fault|PMIC.*OC|overcurrent|OC.*shutdown", "PMIC fault/overcurrent"),
        (r"panic|kernel.*panic|oops", "Kernel panic"),
        (r"watchdog.*reset|wdt.*bite|WDT.*timeout", "Watchdog reset"),
        (r"PL\s*fatal|preloader.*fatal", "Preloader fatal error"),
        (r"CPU.*dead|cpu.*not respond|SoC.*fail", "CPU/SoC failure"),
    ],
    # Warning patterns
    "warnings": [
        (r"I2C.*error|i2c.*fail|transfer\s+error", "I2C bus error"),
        (r"cert.*verify.*fail|cert.*chain.*fail", "Certificate verification failure"),
        (r"abnormal.*boot|crash.*detect", "Abnormal boot detected"),
        (r"thermal.*shutdown|thermal.*warning|over.*temp", "Thermal warning"),
        (r"voltage.*low|under.*voltage|brown.*out", "Voltage anomaly"),
        (r"ATF.*WARNING|ATF.*unknown", "ATF/TrustZone warning"),
        (r"recalibration|impedance.*mismatch", "Memory recalibration needed"),
    ],
    # Boot stages
    "boot_stages": [
        (r"preloader|PL\s+Start|PL_BOOT_MODE", "Preloader"),
        (r"LK\s+START|little\s*kernel|Jump to BL", "LK/Bootloader"),
        (r"ABL|XBL|sbl1|UEFI", "XBL/ABL Bootloader"),
        (r"Linux version|Booting Linux|kernel_init", "Linux Kernel"),
        (r"init:|zygote|SystemServer|Android.*boot", "Android Init"),
    ],
    # Hardware probes
    "hw_probes": [
        (r"(fan53526|rt5738|hl7593|mt6691).*probe", "Voltage regulator probe"),
        (r"(mt6631|wcn\d+|bcm\d+).*probe", "WiFi/BT combo IC probe"),
        (r"(bq\d+|mt6370|sm5714).*probe", "Charging IC probe"),
    ],
}

# I2C address → IC mapping (common MediaTek)
I2C_IC_MAP = {
    "0x60": ("MT6691ZXP / fan53526", "DRAM VDDQ voltage regulator (0.6V)"),
    "0x6b": ("RT5738", "DRAM VDD2 core voltage regulator (1.125V)"),
    "0x50": ("EEPROM / MT6691ZXP alt", "EEPROM or voltage regulator alternate addr"),
    "0x48": ("Temperature sensor", "Board temperature sensor"),
    "0x34": ("PMIC slave", "PMIC secondary I2C interface"),
    "0x36": ("Fuel gauge", "Battery fuel gauge IC"),
}


class LocalClassifier:
    """Offline fault classifier using rule-based pattern matching.

    Produces output in the same JSON format as AILogAnalyzer so the GUI
    can render results identically.
    """

    def __init__(self):
        self.rule_engine = RuleEngine()

    @staticmethod
    def is_available() -> bool:
        """Always available — no external dependencies."""
        return True

    def analyze(self, log_text: str, mode: str = "boot",
                callback=None, detected_context: str = "") -> AIAnalysisResult:
        """Analyze a log using local rule engine + pattern matching.

        Returns an AIAnalysisResult with parsed JSON in the same format
        as the cloud/Ollama analyzers.
        """
        result = AIAnalysisResult(mode=mode)

        if not log_text or not log_text.strip():
            result.error = "No log content to analyze."
            return result

        if callback:
            callback("Running local fault classifier (offline mode)...")

        text = log_text.strip()

        # Auto-detect mode if needed
        if mode == "auto":
            mode = detect_log_type(text)

        # Run rule engine on applicable data
        if callback:
            callback("Matching against 200+ fault patterns...")

        matched_faults = self._run_rule_engine(text, mode)

        # Run boot log pattern analysis
        if callback:
            callback("Analyzing boot patterns and hardware probes...")

        boot_analysis = self._analyze_boot_patterns(text)

        # Build structured result
        if callback:
            callback("Building diagnostic report...")

        parsed = self._build_result_json(
            text, mode, matched_faults, boot_analysis, detected_context
        )

        result.parsed = parsed
        result.success = True
        result.tokens_used = 0  # No tokens — it's local

        return result

    def _run_rule_engine(self, text: str, mode: str) -> List[MatchedFault]:
        """Run the 200+ rule engine against the text."""
        if mode in ("boot", "dmesg"):
            return self.rule_engine.analyze(dmesg_text=text)
        elif mode == "android":
            return self.rule_engine.analyze(logcat_text=text)
        else:
            # Try all sources
            return self.rule_engine.analyze(
                logcat_text=text, dmesg_text=text,
            )

    def _analyze_boot_patterns(self, text: str) -> Dict:
        """Extract structured info from boot log patterns."""
        analysis = {
            "chipset": "",
            "chipset_vendor": "",
            "pmic": "",
            "critical_errors": [],
            "warnings": [],
            "boot_stages_reached": [],
            "hw_probes": [],
            "i2c_errors": [],
            "health_items": [],
        }

        text_lower = text.lower()

        # Chipset detection
        for pattern, vendor in BOOT_PATTERNS["chipset"]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                analysis["chipset"] = m.group(0)
                analysis["chipset_vendor"] = vendor
                break

        # PMIC detection
        for pattern, name in BOOT_PATTERNS["pmic"]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                analysis["pmic"] = m.group(0)
                break

        # Critical errors
        for pattern, name in BOOT_PATTERNS["critical_errors"]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                # Get the full line for evidence
                start = text.rfind("\n", 0, m.start())
                end = text.find("\n", m.end())
                start = 0 if start == -1 else start + 1
                end = len(text) if end == -1 else end
                line = text[start:end].strip()
                analysis["critical_errors"].append({
                    "name": name,
                    "evidence": line[:200],
                    "match": m.group(0),
                })

        # Warnings
        for pattern, name in BOOT_PATTERNS["warnings"]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                start = text.rfind("\n", 0, m.start())
                end = text.find("\n", m.end())
                start = 0 if start == -1 else start + 1
                end = len(text) if end == -1 else end
                line = text[start:end].strip()
                analysis["warnings"].append({
                    "name": name,
                    "evidence": line[:200],
                    "match": m.group(0),
                })

        # Boot stages reached
        for pattern, name in BOOT_PATTERNS["boot_stages"]:
            if re.search(pattern, text, re.IGNORECASE):
                analysis["boot_stages_reached"].append(name)

        # HW probes
        for pattern, name in BOOT_PATTERNS["hw_probes"]:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                analysis["hw_probes"].append({
                    "name": name,
                    "ic": m.group(1) if m.lastindex else m.group(0),
                    "status": "found",
                })

        # I2C errors with IC identification
        i2c_pattern = re.compile(
            r"i2c.*(?:error|fail)|transfer\s+error.*(?:bus|addr|0x[0-9a-f]+)",
            re.IGNORECASE
        )
        for m in i2c_pattern.finditer(text):
            start = text.rfind("\n", 0, m.start())
            end = text.find("\n", m.end())
            start = 0 if start == -1 else start + 1
            end = len(text) if end == -1 else end
            line = text[start:end].strip()

            # Try to extract I2C address
            addr_match = re.search(r"0x([0-9a-fA-F]{2})", line)
            ic_name = "Unknown IC"
            ic_function = ""
            if addr_match:
                addr = f"0x{addr_match.group(1).lower()}"
                if addr in I2C_IC_MAP:
                    ic_name, ic_function = I2C_IC_MAP[addr]

            analysis["i2c_errors"].append({
                "evidence": line[:200],
                "ic_name": ic_name,
                "ic_function": ic_function,
                "address": addr_match.group(0) if addr_match else "unknown",
            })

        # Build health items based on what was found
        # CPU
        if analysis["boot_stages_reached"]:
            last_stage = analysis["boot_stages_reached"][-1]
            if last_stage in ("Linux Kernel", "Android Init"):
                analysis["health_items"].append(("CPU / SoC", f"Boot reached {last_stage}", "ok"))
            else:
                analysis["health_items"].append(("CPU / SoC", f"Boot stopped at {last_stage}", "minor_issue"))
        else:
            has_cpu_error = any(e["name"] == "CPU/SoC failure" for e in analysis["critical_errors"])
            if has_cpu_error:
                analysis["health_items"].append(("CPU / SoC", "Not responding", "fail"))

        # RAM
        has_ram_error = any(e["name"] == "RAM/DRAM initialization failure" for e in analysis["critical_errors"])
        kernel_reached = "Linux Kernel" in analysis["boot_stages_reached"]
        if has_ram_error:
            analysis["health_items"].append(("RAM / DRAM", "Initialization failure detected", "fail"))
        elif kernel_reached:
            analysis["health_items"].append(("RAM / DRAM", "Working (kernel booted)", "ok"))

        # Storage
        has_storage_error = any(e["name"] == "Storage failure" for e in analysis["critical_errors"])
        if has_storage_error:
            analysis["health_items"].append(("Storage (eMMC/UFS)", "Error detected", "fail"))
        elif kernel_reached or "LK/Bootloader" in analysis["boot_stages_reached"]:
            analysis["health_items"].append(("Storage (eMMC/UFS)", "Accessible (bootloader loaded)", "ok"))

        # PMIC
        has_pmic_error = any(e["name"] == "PMIC fault/overcurrent" for e in analysis["critical_errors"])
        if has_pmic_error:
            analysis["health_items"].append(("PMIC", "Fault/overcurrent detected", "fail"))
        elif analysis["pmic"]:
            analysis["health_items"].append(("PMIC", f"{analysis['pmic']} — responding", "ok"))

        # WiFi/BT/Camera/etc — not testable via UART
        for item in ["WiFi / Bluetooth", "Camera", "Audio", "Display", "Sensors", "GPS / NFC"]:
            analysis["health_items"].append((item, "Not testable via UART (needs ADB)", "not_testable_via_uart"))

        return analysis

    def _build_result_json(self, text: str, mode: str,
                           matched_faults: List[MatchedFault],
                           boot_analysis: Dict,
                           detected_context: str) -> Dict:
        """Build the same JSON structure as Groq/Ollama analyzers."""

        # Determine overall status
        critical_count = sum(1 for mf in matched_faults if mf.rule.severity == "critical")
        warning_count = sum(1 for mf in matched_faults if mf.rule.severity == "warning")
        critical_boot = len(boot_analysis.get("critical_errors", []))
        warning_boot = len(boot_analysis.get("warnings", []))

        total_critical = critical_count + critical_boot
        total_warning = warning_count + warning_boot

        if total_critical > 0:
            status = "needs_repair"
            health = max(10, 50 - total_critical * 15 - total_warning * 5)
        elif total_warning > 0:
            status = "minor_issues"
            health = max(40, 80 - total_warning * 10)
        else:
            status = "healthy"
            health = 95

        chipset = boot_analysis.get("chipset", "Unknown")
        vendor = boot_analysis.get("chipset_vendor", "")

        # Build verdict
        if total_critical > 0:
            first_critical = (boot_analysis["critical_errors"][0]["name"]
                            if boot_analysis["critical_errors"]
                            else matched_faults[0].rule.fault_name if matched_faults else "Unknown fault")
            verdict = f"{vendor} {chipset} — {first_critical}"
        elif total_warning > 0:
            verdict = f"{vendor} {chipset} — {total_warning} warning(s) detected"
        else:
            verdict = f"{vendor} {chipset} — No critical faults detected"

        # Reasoning
        stages = boot_analysis.get("boot_stages_reached", [])
        reasoning_parts = []
        if stages:
            reasoning_parts.append(f"Boot reached: {' → '.join(stages)}")
        if total_critical:
            reasoning_parts.append(f"{total_critical} critical error(s) found")
        if total_warning:
            reasoning_parts.append(f"{total_warning} warning(s) found")
        if boot_analysis.get("i2c_errors"):
            reasoning_parts.append(f"{len(boot_analysis['i2c_errors'])} I2C error(s)")
        if not total_critical and not total_warning:
            reasoning_parts.append("No known fault patterns matched. Device appears healthy from log data.")

        reasoning = ". ".join(reasoning_parts)

        # Build issue cards
        issue_cards = []

        # From boot analysis critical errors
        for err in boot_analysis.get("critical_errors", []):
            issue_cards.append({
                "title": err["name"],
                "symptom": f"Detected in boot log: {err['match']}",
                "evidence": err["evidence"],
                "status": "confirmed",
                "severity": "critical",
                "impact": "Device may not boot or function properly",
                "repair_action": self._get_repair_action(err["name"]),
            })

        # From boot analysis warnings
        for warn in boot_analysis.get("warnings", []):
            issue_cards.append({
                "title": warn["name"],
                "symptom": f"Warning pattern: {warn['match']}",
                "evidence": warn["evidence"],
                "status": "likely",
                "severity": "warning",
                "impact": "May cause intermittent issues",
                "repair_action": self._get_repair_action(warn["name"]),
            })

        # From I2C errors (with IC identification)
        for i2c in boot_analysis.get("i2c_errors", []):
            issue_cards.append({
                "title": f"I2C Error — {i2c['ic_name']}",
                "symptom": f"I2C communication failure at address {i2c['address']}",
                "evidence": i2c["evidence"],
                "status": "confirmed",
                "severity": "critical",
                "impact": f"{i2c['ic_function']}" if i2c['ic_function'] else "IC not responding on I2C bus",
                "repair_action": f"Check {i2c['ic_name']} solder joints and power supply. Reball or replace if needed.",
            })

        # From rule engine matched faults (avoid duplicates)
        seen_titles = {ic["title"] for ic in issue_cards}
        for mf in matched_faults[:15]:  # Limit to top 15
            title = mf.rule.fault_name
            if title in seen_titles:
                continue
            seen_titles.add(title)
            issue_cards.append({
                "title": title,
                "symptom": mf.rule.description,
                "evidence": mf.matched_text[:200],
                "status": "confirmed" if mf.confidence >= 0.7 else "likely" if mf.confidence >= 0.4 else "possible",
                "severity": mf.rule.severity,
                "impact": mf.rule.description,
                "repair_action": "; ".join(mf.rule.repair_steps[:2]) if mf.rule.repair_steps else "Investigate component",
            })

        # Hardware health
        hardware_health = []
        for item, result_text, hw_status in boot_analysis.get("health_items", []):
            hardware_health.append({
                "item": item,
                "result": result_text,
                "status": hw_status,
            })

        # Recommendations
        recommendations = []
        if total_critical > 0:
            recommendations.append({
                "title": "Address critical faults immediately",
                "priority": "high",
                "steps": [
                    f"Found {total_critical} critical fault(s) — device needs hardware repair",
                    "Check voltage rails with multimeter",
                    "Inspect for physical damage or corrosion",
                    "See issue cards above for specific repair steps",
                ],
            })
        if boot_analysis.get("i2c_errors"):
            recommendations.append({
                "title": "Investigate I2C communication failures",
                "priority": "high",
                "steps": [
                    "I2C errors indicate IC communication failure",
                    "Check solder joints of identified ICs under microscope",
                    "Verify power supply to affected ICs",
                    "Reball or replace faulty ICs",
                ],
            })
        if total_warning > 0 and total_critical == 0:
            recommendations.append({
                "title": "Monitor warning conditions",
                "priority": "medium",
                "steps": [
                    f"{total_warning} warning(s) detected — may indicate developing issues",
                    "Run full diagnostic via ADB for detailed component status",
                    "Compare against baseline for this device model",
                ],
            })
        if not recommendations:
            recommendations.append({
                "title": "Device appears healthy",
                "priority": "low",
                "steps": [
                    "No critical faults detected in boot log",
                    "Run ADB detection for full component check",
                    "Store as baseline if this is a known-good device",
                ],
            })

        # Warnings/caveats
        warnings = [
            "Analysis performed by local rule engine (offline mode) — 200+ patterns checked",
            "UART boot log only shows early boot hardware. WiFi, Camera, Sensors etc. need ADB scan.",
        ]
        if not boot_analysis.get("chipset"):
            warnings.append("Could not identify chipset from log — results may be less specific")

        return {
            "analysis_mode": mode,
            "conclusion": {
                "verdict": verdict,
                "status": status,
                "health_percent": health,
                "reasoning": reasoning,
            },
            "device_info": {
                "chip": f"{vendor} {chipset}" if vendor else chipset,
                "brand": vendor,
                "memory": "",
                "storage": "",
                "battery": "",
            },
            "issue_cards": issue_cards,
            "hardware_health": hardware_health,
            "recommendations": recommendations,
            "warnings": warnings,
        }

    @staticmethod
    def _get_repair_action(error_name: str) -> str:
        """Get repair action for a known error pattern."""
        actions = {
            "RAM/DRAM initialization failure": "Check DRAM voltage rails (VDD2 ~1.1V, VDDQ ~0.6V). Reball RAM if voltages OK.",
            "Storage failure": "Try flashing firmware via BROM/EDL mode. If fails, check eMMC/UFS power and reball/replace.",
            "PMIC fault/overcurrent": "Check for short circuits on all PMIC output rails. Replace PMIC if shorted.",
            "Kernel panic": "Could be software (flash firmware) or hardware (check RAM, storage). Start with firmware flash.",
            "Watchdog reset": "Check what caused the hang — often storage I/O failure or RAM instability.",
            "Preloader fatal error": "Flash preloader via SP Flash Tool. If fails, check storage IC.",
            "CPU/SoC failure": "Check PMIC output voltages (VDD_CORE, VDD_IO). If no power, replace PMIC. If power OK but no response, CPU may need reballing.",
            "I2C bus error": "Identify the IC from the I2C address. Check its power supply and solder joints.",
            "Certificate verification failure": "Reflash firmware with correct signed images. Not usually a hardware issue.",
            "Abnormal boot detected": "Previous boot crashed. Check crash log. If repeated, investigate hardware (RAM, storage).",
            "Thermal warning": "Check for short circuits causing excessive current. Use thermal camera to find hot spot.",
            "Voltage anomaly": "Measure affected voltage rail. Check regulator IC and surrounding components.",
            "ATF/TrustZone warning": "Usually firmware version mismatch. Reflash with matching ATF version.",
            "Memory recalibration needed": "DRAM impedance mismatch. May indicate degrading RAM solder joints.",
        }
        return actions.get(error_name, "Investigate the reported component. Check power supply and solder joints.")
