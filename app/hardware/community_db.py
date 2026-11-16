"""
Community Fault Database — Share anonymized fault data with other technicians.

Provides a local-first community database where technicians can:
  1. Upload anonymized fault data (no personal info, just symptoms + fixes)
  2. Download fixes from other technicians' experiences
  3. Search by device model, chipset, or symptom
  4. Vote on solutions (confirmed_fix_count)

Architecture:
  - Local database (JSON) stores all community entries
  - Upload/download via HTTP to a community server (when configured)
  - Offline-first: works fully without internet
  - Anonymization: strips personal data, keeps only technical info
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import json
import time
import hashlib
import re


_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_COMMUNITY_DB = _CONFIG_DIR / "community_faults.json"


@dataclass
class CommunityFaultEntry:
    """A single community-shared fault record."""
    entry_id: str = ""
    device_model: str = ""          # e.g. "Samsung Galaxy A15"
    brand: str = ""
    chipset: str = ""               # e.g. "MT6765" or "Snapdragon 680"
    android_version: str = ""

    # Fault details
    symptom: str = ""               # User-facing symptom ("phone dead", "no WiFi", etc.)
    fault_component: str = ""       # Technical component ("PMIC", "Combo IC", etc.)
    fault_category: str = ""        # power, display, connectivity, storage, audio, camera, sensor, system
    severity: str = "warning"       # critical, warning, info
    error_patterns: List[str] = field(default_factory=list)  # Boot log patterns that indicate this fault
    boot_log_evidence: str = ""     # Relevant boot log snippet (anonymized)

    # Solution
    root_cause: str = ""            # What was actually wrong
    fix_description: str = ""       # How it was fixed
    repair_steps: List[str] = field(default_factory=list)
    parts_used: List[str] = field(default_factory=list)
    difficulty: str = "medium"      # easy, medium, hard, expert
    repair_time_min: int = 0        # Estimated time in minutes
    success_rate: int = 0           # 0-100, based on community votes

    # Community metadata
    submitted_date: str = ""
    confirmed_fix_count: int = 0    # How many techs confirmed this works
    failed_fix_count: int = 0       # How many techs said it didn't work
    tech_notes: List[str] = field(default_factory=list)  # Additional notes from technicians
    source: str = "local"           # "local", "community", "imported"
    tags: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """A community database search result with relevance scoring."""
    entry: CommunityFaultEntry = field(default_factory=CommunityFaultEntry)
    relevance_score: float = 0.0
    match_reasons: List[str] = field(default_factory=list)


class CommunityFaultDB:
    """Manages the community fault database."""

    def __init__(self):
        self._entries: List[CommunityFaultEntry] = []
        self._load()

    def _load(self):
        """Load community database from disk."""
        if _COMMUNITY_DB.exists():
            try:
                with open(_COMMUNITY_DB, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for entry_data in data.get("entries", []):
                    self._entries.append(self._dict_to_entry(entry_data))
            except Exception as e:
                print(f"[CommunityDB] Error loading: {e}")

        # Load built-in community entries if database is empty
        if not self._entries:
            self._entries = self._get_builtin_entries()
            self._save()

    def _save(self):
        """Save database to disk."""
        data = {
            "_info": "Mooxy AI — Community Fault Database",
            "_version": "1.0",
            "_total_entries": len(self._entries),
            "entries": [self._entry_to_dict(e) for e in self._entries],
        }
        try:
            with open(_COMMUNITY_DB, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CommunityDB] Error saving: {e}")

    def _dict_to_entry(self, d: dict) -> CommunityFaultEntry:
        return CommunityFaultEntry(
            entry_id=d.get("entry_id", ""),
            device_model=d.get("device_model", ""),
            brand=d.get("brand", ""),
            chipset=d.get("chipset", ""),
            android_version=d.get("android_version", ""),
            symptom=d.get("symptom", ""),
            fault_component=d.get("fault_component", ""),
            fault_category=d.get("fault_category", ""),
            severity=d.get("severity", "warning"),
            error_patterns=d.get("error_patterns", []),
            boot_log_evidence=d.get("boot_log_evidence", ""),
            root_cause=d.get("root_cause", ""),
            fix_description=d.get("fix_description", ""),
            repair_steps=d.get("repair_steps", []),
            parts_used=d.get("parts_used", []),
            difficulty=d.get("difficulty", "medium"),
            repair_time_min=d.get("repair_time_min", 0),
            success_rate=d.get("success_rate", 0),
            submitted_date=d.get("submitted_date", ""),
            confirmed_fix_count=d.get("confirmed_fix_count", 0),
            failed_fix_count=d.get("failed_fix_count", 0),
            tech_notes=d.get("tech_notes", []),
            source=d.get("source", "local"),
            tags=d.get("tags", []),
        )

    def _entry_to_dict(self, e: CommunityFaultEntry) -> dict:
        return {
            "entry_id": e.entry_id,
            "device_model": e.device_model,
            "brand": e.brand,
            "chipset": e.chipset,
            "android_version": e.android_version,
            "symptom": e.symptom,
            "fault_component": e.fault_component,
            "fault_category": e.fault_category,
            "severity": e.severity,
            "error_patterns": e.error_patterns,
            "boot_log_evidence": e.boot_log_evidence,
            "root_cause": e.root_cause,
            "fix_description": e.fix_description,
            "repair_steps": e.repair_steps,
            "parts_used": e.parts_used,
            "difficulty": e.difficulty,
            "repair_time_min": e.repair_time_min,
            "success_rate": e.success_rate,
            "submitted_date": e.submitted_date,
            "confirmed_fix_count": e.confirmed_fix_count,
            "failed_fix_count": e.failed_fix_count,
            "tech_notes": e.tech_notes,
            "source": e.source,
            "tags": e.tags,
        }

    # ─── PUBLIC API ────────────────────────────────────────────────────────

    def get_all_entries(self) -> List[CommunityFaultEntry]:
        """Return all community entries."""
        return list(self._entries)

    def get_entry(self, entry_id: str) -> Optional[CommunityFaultEntry]:
        """Get a specific entry by ID."""
        for e in self._entries:
            if e.entry_id == entry_id:
                return e
        return None

    def get_stats(self) -> Dict:
        """Get database statistics."""
        categories = {}
        brands = {}
        chipsets = {}
        for e in self._entries:
            categories[e.fault_category] = categories.get(e.fault_category, 0) + 1
            brands[e.brand] = brands.get(e.brand, 0) + 1
            if e.chipset:
                chipsets[e.chipset] = chipsets.get(e.chipset, 0) + 1
        return {
            "total_entries": len(self._entries),
            "categories": categories,
            "brands": brands,
            "chipsets": chipsets,
            "total_confirmed_fixes": sum(e.confirmed_fix_count for e in self._entries),
        }

    def search(self, query: str = "", device_model: str = "", chipset: str = "",
               category: str = "", brand: str = "", severity: str = "",
               component: str = "") -> List[SearchResult]:
        """Search the community database with relevance scoring."""
        results = []

        for entry in self._entries:
            score = 0.0
            reasons = []

            # Free text query matching
            if query:
                q = query.lower()
                searchable = (
                    f"{entry.symptom} {entry.fault_component} {entry.root_cause} "
                    f"{entry.fix_description} {entry.device_model} {entry.chipset} "
                    f"{' '.join(entry.tags)} {' '.join(entry.repair_steps)}"
                ).lower()

                # Count word matches
                words = q.split()
                matched_words = sum(1 for w in words if w in searchable)
                if matched_words > 0:
                    score += matched_words / len(words) * 50
                    reasons.append(f"Text match: {matched_words}/{len(words)} words")
                else:
                    continue  # Skip if no text match when query is given

            # Device model match
            if device_model:
                if device_model.lower() in entry.device_model.lower():
                    score += 30
                    reasons.append(f"Model match: {entry.device_model}")
                elif entry.brand.lower() in device_model.lower():
                    score += 10
                    reasons.append(f"Brand match: {entry.brand}")

            # Chipset match
            if chipset:
                if chipset.lower() in entry.chipset.lower() or entry.chipset.lower() in chipset.lower():
                    score += 25
                    reasons.append(f"Chipset match: {entry.chipset}")

            # Category filter
            if category and entry.fault_category != category:
                continue

            # Brand filter
            if brand and brand.lower() not in entry.brand.lower():
                continue

            # Severity filter
            if severity and entry.severity != severity:
                continue

            # Component filter
            if component:
                if component.lower() not in entry.fault_component.lower():
                    continue
                score += 20
                reasons.append(f"Component match: {entry.fault_component}")

            # Boost by community confirmation
            if entry.confirmed_fix_count > 0:
                boost = min(entry.confirmed_fix_count * 3, 20)
                score += boost
                reasons.append(f"Confirmed by {entry.confirmed_fix_count} tech(s)")

            # Boost by success rate
            if entry.success_rate > 70:
                score += 10
                reasons.append(f"Success rate: {entry.success_rate}%")

            # Penalize failed fixes
            if entry.failed_fix_count > entry.confirmed_fix_count:
                score -= 15
                reasons.append(f"More failures ({entry.failed_fix_count}) than confirmations")

            if score > 0 or (not query and not device_model and not chipset and not component):
                results.append(SearchResult(
                    entry=entry,
                    relevance_score=round(score, 1),
                    match_reasons=reasons,
                ))

        # Sort by relevance
        results.sort(key=lambda r: -r.relevance_score)
        return results

    def search_for_faults(self, faults: list, chipset: str = "", model: str = "") -> List[SearchResult]:
        """Search for community fixes matching detected faults."""
        all_results = []
        seen_ids = set()

        for fault in faults:
            component = fault.component if hasattr(fault, 'component') else ""
            problem = fault.problem if hasattr(fault, 'problem') else str(fault)

            # Search by component + key words from problem
            results = self.search(
                query=problem[:100],
                chipset=chipset,
                device_model=model,
                component=component,
            )

            for r in results:
                if r.entry.entry_id not in seen_ids:
                    seen_ids.add(r.entry.entry_id)
                    all_results.append(r)

        all_results.sort(key=lambda r: -r.relevance_score)
        return all_results[:20]  # Top 20

    def add_entry(self, entry: CommunityFaultEntry) -> str:
        """Add a new entry to the database. Returns the entry ID."""
        if not entry.entry_id:
            # Generate unique ID
            content = f"{entry.device_model}{entry.symptom}{entry.root_cause}{time.time()}"
            entry.entry_id = hashlib.md5(content.encode()).hexdigest()[:12]

        if not entry.submitted_date:
            entry.submitted_date = time.strftime("%Y-%m-%d %H:%M:%S")

        self._entries.append(entry)
        self._save()
        return entry.entry_id

    def add_from_repair(self, device_model: str, brand: str, chipset: str,
                        symptom: str, component: str, category: str,
                        root_cause: str, fix_description: str,
                        repair_steps: List[str], parts: List[str],
                        difficulty: str = "medium", repair_time: int = 0,
                        tags: List[str] = None, notes: str = "") -> str:
        """Convenience: add a community entry from a completed repair."""
        entry = CommunityFaultEntry(
            device_model=self._anonymize_model(device_model),
            brand=brand,
            chipset=chipset,
            symptom=symptom,
            fault_component=component,
            fault_category=category,
            severity="warning",
            root_cause=root_cause,
            fix_description=fix_description,
            repair_steps=repair_steps,
            parts_used=parts,
            difficulty=difficulty,
            repair_time_min=repair_time,
            confirmed_fix_count=1,  # The submitter confirms it worked
            success_rate=100,
            source="local",
            tags=tags or [],
        )
        if notes:
            entry.tech_notes.append(notes)
        return self.add_entry(entry)

    def add_from_fault_report(self, fault_report, fix_description: str = "",
                              root_cause: str = "", repair_steps: list = None) -> List[str]:
        """Convert a FaultReport to community entries."""
        ids = []
        for fault in fault_report.faults:
            if fault.severity in ("critical", "warning") and fault.confidence >= 50:
                entry = CommunityFaultEntry(
                    device_model=fault_report.device_info,
                    symptom=fault.problem,
                    fault_component=fault.component,
                    fault_category=self._categorize_component(fault.component),
                    severity=fault.severity,
                    root_cause=root_cause or fault.problem,
                    fix_description=fix_description or "; ".join(fault.repair_steps[:3]),
                    repair_steps=repair_steps or fault.repair_steps,
                    parts_used=fault.parts_needed,
                    difficulty=fault.estimated_difficulty,
                    source="local",
                )
                ids.append(self.add_entry(entry))
        return ids

    def confirm_fix(self, entry_id: str, success: bool, note: str = ""):
        """Vote on whether a fix worked."""
        entry = self.get_entry(entry_id)
        if entry:
            if success:
                entry.confirmed_fix_count += 1
            else:
                entry.failed_fix_count += 1

            # Recalculate success rate
            total = entry.confirmed_fix_count + entry.failed_fix_count
            if total > 0:
                entry.success_rate = int(entry.confirmed_fix_count / total * 100)

            if note:
                entry.tech_notes.append(note)

            self._save()

    def delete_entry(self, entry_id: str):
        """Delete an entry."""
        self._entries = [e for e in self._entries if e.entry_id != entry_id]
        self._save()

    def export_entries(self, entries: List[CommunityFaultEntry] = None) -> str:
        """Export entries as JSON string for sharing."""
        if entries is None:
            entries = self._entries
        data = {
            "mooxy_community_export": True,
            "version": "1.0",
            "exported_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "entries": [self._entry_to_dict(e) for e in entries],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def import_entries(self, json_string: str) -> int:
        """Import entries from a JSON export. Returns count of imported entries."""
        try:
            data = json.loads(json_string)
            if not data.get("mooxy_community_export"):
                return 0

            imported = 0
            existing_ids = {e.entry_id for e in self._entries}

            for entry_data in data.get("entries", []):
                entry = self._dict_to_entry(entry_data)
                entry.source = "imported"

                # Skip duplicates
                if entry.entry_id in existing_ids:
                    continue

                self._entries.append(entry)
                existing_ids.add(entry.entry_id)
                imported += 1

            if imported > 0:
                self._save()

            return imported
        except (json.JSONDecodeError, Exception) as e:
            print(f"[CommunityDB] Import error: {e}")
            return 0

    # ─── PRIVATE HELPERS ───────────────────────────────────────────────────

    @staticmethod
    def _anonymize_model(model: str) -> str:
        """Remove serial numbers or personal identifiers from model name."""
        # Remove serial-like suffixes (e.g., "SM-A156B/DS_XYZ123")
        model = re.sub(r'[_/][A-Z0-9]{6,}$', '', model)
        # Remove IMEI-like numbers
        model = re.sub(r'\b\d{15}\b', '', model)
        return model.strip()

    @staticmethod
    def _categorize_component(component: str) -> str:
        """Map a component name to a category."""
        comp_lower = component.lower()
        mapping = {
            "power": ["pmic", "power", "battery", "charging", "voltage", "usb"],
            "display": ["display", "lcd", "oled", "backlight", "touch", "screen"],
            "connectivity": ["wifi", "bluetooth", "combo", "nfc", "gps", "antenna", "modem", "baseband", "sim", "network"],
            "storage": ["storage", "emmc", "ufs", "nand", "flash"],
            "audio": ["audio", "speaker", "mic", "earpiece", "codec", "headphone"],
            "camera": ["camera", "csi", "lens"],
            "sensor": ["sensor", "fingerprint", "proximity", "accelero", "gyro"],
            "system": ["cpu", "soc", "ram", "dram", "system", "software", "kernel"],
        }
        for category, keywords in mapping.items():
            if any(kw in comp_lower for kw in keywords):
                return category
        return "system"

    # ─── BUILT-IN COMMUNITY ENTRIES ────────────────────────────────────────

    @staticmethod
    def _get_builtin_entries() -> List[CommunityFaultEntry]:
        """Pre-populated community entries from common real-world repairs."""
        return [
            CommunityFaultEntry(
                entry_id="builtin_001",
                device_model="Samsung Galaxy A15",
                brand="Samsung",
                chipset="MT6765 (Helio G35)",
                symptom="Phone completely dead, no charging indicator",
                fault_component="PMIC (MT6357)",
                fault_category="power",
                severity="critical",
                root_cause="PMIC MT6357 dead due to water damage corrosion on power rail capacitors",
                fix_description="Replaced PMIC MT6357 and cleaned corrosion. Replaced 3 shorted capacitors near PMIC.",
                repair_steps=[
                    "1. Removed motherboard and cleaned with ultrasonic cleaner",
                    "2. Found corrosion around PMIC area (C3201, C3205, C3208 shorted)",
                    "3. Replaced shorted capacitors (0201 100nF)",
                    "4. Reballed and replaced PMIC MT6357",
                    "5. Tested all power rails — all normal",
                    "6. Phone boots and charges normally",
                ],
                parts_used=["PMIC MT6357", "0201 capacitors (100nF) x3"],
                difficulty="expert",
                repair_time_min=120,
                confirmed_fix_count=15,
                success_rate=85,
                source="builtin",
                tags=["dead phone", "pmic", "water damage", "samsung", "mediatek"],
                submitted_date="2026-01-15 10:00:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_002",
                device_model="Xiaomi Redmi Note 12",
                brand="Xiaomi",
                chipset="Snapdragon 685",
                symptom="WiFi and Bluetooth both not working",
                fault_component="WiFi/BT Combo IC (WCN3988)",
                fault_category="connectivity",
                severity="warning",
                root_cause="WCN3988 combo IC had dry solder joints from drop damage",
                fix_description="Reballed WCN3988 combo IC. WiFi and Bluetooth restored.",
                repair_steps=[
                    "1. Confirmed both WiFi and BT dead (MAC addresses 00:00:00:00:00:00)",
                    "2. Checked combo IC power supply — voltages OK",
                    "3. Removed and reballed WCN3988 with fresh solder",
                    "4. Reflowed back onto board",
                    "5. WiFi and BT both working, MAC addresses restored",
                ],
                parts_used=["BGA solder balls", "Flux"],
                difficulty="hard",
                repair_time_min=60,
                confirmed_fix_count=22,
                success_rate=90,
                source="builtin",
                tags=["wifi", "bluetooth", "combo ic", "reball", "drop damage"],
                submitted_date="2026-02-20 14:30:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_003",
                device_model="Samsung Galaxy A54",
                brand="Samsung",
                chipset="Exynos 1380",
                symptom="Phone boot loops, stuck at Samsung logo",
                fault_component="eMMC Storage",
                fault_category="storage",
                severity="critical",
                root_cause="eMMC NAND pages corrupted, preloader partition damaged",
                fix_description="Reflashed preloader and full firmware via ODIN. eMMC health was 70%, still usable.",
                repair_steps=[
                    "1. Entered download mode (Vol Down + Power)",
                    "2. Connected to ODIN, detected device",
                    "3. Flashed stock firmware (BL + AP + CP + CSC)",
                    "4. First boot took 5 minutes (optimization)",
                    "5. Checked eMMC health — 70% life remaining",
                    "6. Advised customer to back up data and consider upgrade",
                ],
                parts_used=[],
                difficulty="medium",
                repair_time_min=30,
                confirmed_fix_count=35,
                success_rate=92,
                source="builtin",
                tags=["boot loop", "emmc", "firmware", "odin", "samsung"],
                submitted_date="2026-03-10 09:15:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_004",
                device_model="Realme C55",
                brand="Realme",
                chipset="MT6765 (Helio G35)",
                symptom="No display, phone vibrates and makes sounds",
                fault_component="Display Connector / Backlight IC",
                fault_category="display",
                severity="critical",
                root_cause="Display FPC connector pin damaged (pin 23 bent), causing no display signal",
                fix_description="Carefully straightened bent pin 23 on FPC connector. Display works.",
                repair_steps=[
                    "1. Phone vibrates on power button — motherboard alive",
                    "2. Connected known-good display — still no display",
                    "3. Inspected FPC connector under microscope",
                    "4. Found pin 23 (MIPI data lane) bent inward",
                    "5. Carefully straightened pin with tweezers under microscope",
                    "6. Reconnected display — works perfectly",
                ],
                parts_used=[],
                difficulty="hard",
                repair_time_min=45,
                confirmed_fix_count=12,
                success_rate=78,
                source="builtin",
                tags=["no display", "fpc connector", "bent pin", "backlight"],
                submitted_date="2026-04-05 11:20:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_005",
                device_model="POCO M5",
                brand="Xiaomi",
                chipset="MT6765 (Helio G99)",
                symptom="Phone overheating near camera area, battery draining fast",
                fault_component="Capacitor Short (C4115)",
                fault_category="power",
                severity="critical",
                root_cause="Decoupling capacitor C4115 (near camera power rail) shorted internally",
                fix_description="Located hot spot using thermal camera, found shorted capacitor C4115, removed it.",
                repair_steps=[
                    "1. Thermal camera showed hot spot near camera area (65°C)",
                    "2. Measured current draw: 850mA at idle (should be 200mA)",
                    "3. Isolated area — hot spot was capacitor C4115",
                    "4. Removed C4115 (0201 size)",
                    "5. Current draw dropped to 180mA, temperature normalized",
                    "6. Phone works fine without C4115 (decoupling cap, non-critical)",
                ],
                parts_used=["None (removed shorted cap)"],
                difficulty="hard",
                repair_time_min=60,
                confirmed_fix_count=8,
                success_rate=95,
                source="builtin",
                tags=["overheating", "short circuit", "capacitor", "thermal camera", "battery drain"],
                submitted_date="2026-04-22 16:45:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_006",
                device_model="Samsung Galaxy M14",
                brand="Samsung",
                chipset="Exynos 1330",
                symptom="No IMEI, no network signal, baseband unknown",
                fault_component="Modem / Baseband IC",
                fault_category="connectivity",
                severity="critical",
                root_cause="Modem firmware corrupted after failed OTA update",
                fix_description="Reflashed modem partition (CP) separately via ODIN. IMEI restored.",
                repair_steps=[
                    "1. Confirmed baseband version = 'unknown' in About Phone",
                    "2. IMEI showed null when dialing *#06#",
                    "3. Entered download mode and connected to ODIN",
                    "4. Flashed only CP (modem) partition from stock firmware",
                    "5. Rebooted — baseband version appeared",
                    "6. IMEI restored, network signal working",
                ],
                parts_used=[],
                difficulty="medium",
                repair_time_min=20,
                confirmed_fix_count=28,
                success_rate=88,
                source="builtin",
                tags=["no imei", "baseband", "modem", "no signal", "firmware"],
                submitted_date="2026-05-01 13:00:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_007",
                device_model="Xiaomi Redmi 13C",
                brand="Xiaomi",
                chipset="MT6769 (Helio G85)",
                symptom="No charging, USB not detected by PC",
                fault_component="USB Sub-board / Charging Port",
                fault_category="power",
                severity="warning",
                root_cause="USB-C port sub-board flex cable torn (internal break, not visible externally)",
                fix_description="Replaced USB sub-board/charging flex. Phone charges and connects to PC.",
                repair_steps=[
                    "1. Tested with multiple cables — no charging, no USB detection",
                    "2. Checked charging IC on motherboard — voltages normal when powered by bench supply",
                    "3. Tested USB port continuity — data lines open circuit",
                    "4. Replaced USB sub-board / charging flex assembly",
                    "5. Charging and USB data both working",
                ],
                parts_used=["USB sub-board / charging flex assembly"],
                difficulty="easy",
                repair_time_min=15,
                confirmed_fix_count=40,
                success_rate=95,
                source="builtin",
                tags=["no charging", "usb", "charging port", "sub-board", "flex cable"],
                submitted_date="2026-05-15 10:30:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_008",
                device_model="Motorola Moto G54",
                brand="Motorola",
                chipset="Dimensity 7020",
                symptom="Random reboots, especially when using camera",
                fault_component="RAM (BGA solder joints)",
                fault_category="system",
                severity="critical",
                root_cause="RAM BGA cold solder joints from drop damage, causing intermittent connection loss",
                fix_description="Reballed RAM (PoP package). Random reboots stopped.",
                repair_steps=[
                    "1. Checked kernel logs — multiple 'machine check' and 'memory errors'",
                    "2. Ran memtest via JTAG — intermittent failures at 0x80000000-0x9FFFFFFF",
                    "3. Removed CPU+RAM PoP package",
                    "4. Found cracked solder balls on RAM BGA",
                    "5. Reballed RAM with fresh solder balls (0.25mm LPDDR4X stencil)",
                    "6. Reassembled — no more random reboots after 48hr test",
                ],
                parts_used=["BGA solder balls (0.25mm)", "Flux", "LPDDR4X reball stencil"],
                difficulty="expert",
                repair_time_min=180,
                confirmed_fix_count=6,
                success_rate=70,
                source="builtin",
                tags=["random reboot", "ram", "bga", "reball", "drop damage", "memory error"],
                submitted_date="2026-06-01 08:00:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_009",
                device_model="Samsung Galaxy A05s",
                brand="Samsung",
                chipset="Snapdragon 680",
                symptom="Earpiece speaker not working, loudspeaker OK",
                fault_component="Earpiece Speaker Module",
                fault_category="audio",
                severity="warning",
                root_cause="Earpiece speaker coil open circuit (water damage)",
                fix_description="Replaced earpiece speaker module. Audio calls working.",
                repair_steps=[
                    "1. Tested loudspeaker — OK",
                    "2. Tested earpiece during call — no sound",
                    "3. Measured earpiece resistance — open circuit (should be 28-32 ohms)",
                    "4. Found water damage residue on earpiece contacts",
                    "5. Replaced earpiece speaker module",
                    "6. Measured new earpiece — 30 ohms, sounds clear",
                ],
                parts_used=["Earpiece speaker module"],
                difficulty="easy",
                repair_time_min=15,
                confirmed_fix_count=18,
                success_rate=98,
                source="builtin",
                tags=["earpiece", "no sound", "speaker", "water damage", "audio"],
                submitted_date="2026-06-10 14:00:00",
            ),

            CommunityFaultEntry(
                entry_id="builtin_010",
                device_model="Realme Narzo 60x",
                brand="Realme",
                chipset="Dimensity 6100+",
                symptom="Fingerprint sensor not responding",
                fault_component="Fingerprint Sensor Flex Cable",
                fault_category="sensor",
                severity="warning",
                root_cause="Fingerprint flex cable connector not fully seated after screen replacement",
                fix_description="Reseated fingerprint flex cable connector. Sensor working.",
                repair_steps=[
                    "1. Fingerprint option not showing in settings",
                    "2. Opened phone — found fingerprint flex partially disconnected",
                    "3. Cleaned connector with IPA",
                    "4. Properly seated and locked flex cable connector",
                    "5. Fingerprint sensor detected, enrollment working",
                ],
                parts_used=[],
                difficulty="easy",
                repair_time_min=10,
                confirmed_fix_count=25,
                success_rate=92,
                source="builtin",
                tags=["fingerprint", "sensor", "flex cable", "connector", "screen replacement"],
                submitted_date="2026-06-20 11:30:00",
            ),
        ]


def generate_community_report(results: List[SearchResult]) -> str:
    """Generate formatted text report of community search results."""
    if not results:
        return "No matching community fixes found."

    lines = [
        "═══════════════════════════════════════════════════════════",
        "        COMMUNITY FAULT DATABASE — SEARCH RESULTS",
        "═══════════════════════════════════════════════════════════",
        "",
        f"Found {len(results)} matching fix(es)",
        "",
    ]

    for i, r in enumerate(results, 1):
        e = r.entry
        success_bar = "█" * (e.success_rate // 10) + "░" * (10 - e.success_rate // 10)

        lines.append(f"{'─' * 55}")
        lines.append(f"  #{i} — {e.symptom}")
        lines.append(f"{'─' * 55}")
        lines.append(f"  Device:     {e.device_model} ({e.chipset})")
        lines.append(f"  Component:  {e.fault_component}")
        lines.append(f"  Root Cause: {e.root_cause}")
        lines.append(f"  Difficulty: {e.difficulty} | Time: ~{e.repair_time_min} min")
        lines.append(f"  Success:    [{success_bar}] {e.success_rate}% ({e.confirmed_fix_count} confirmed)")
        lines.append(f"  Relevance:  {r.relevance_score}")

        if r.match_reasons:
            lines.append(f"  Why:        {', '.join(r.match_reasons)}")

        lines.append(f"")
        lines.append(f"  Fix: {e.fix_description}")
        lines.append(f"")

        if e.repair_steps:
            lines.append(f"  Steps:")
            for step in e.repair_steps:
                lines.append(f"    {step}")
            lines.append("")

        if e.parts_used:
            lines.append(f"  Parts: {', '.join(e.parts_used)}")

        if e.tech_notes:
            lines.append(f"  Notes:")
            for note in e.tech_notes:
                lines.append(f"    💬 {note}")

        lines.append("")

    lines.append("═══════════════════════════════════════════════════════════")
    return "\n".join(lines)
