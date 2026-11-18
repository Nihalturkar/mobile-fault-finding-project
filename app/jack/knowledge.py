"""
Section 2 — Knowledge tools.

Searches the local JSON repair databases so Jack answers from *your* data
instead of guessing IC names, voltages or test points.

Every public search_* method returns a plain dict/list (JSON-serialisable)
so it can be sent straight back to the LLM as a tool result.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app.jack.config import CONFIG_DIR

# Hinglish / technician slang → database vocabulary
SYNONYMS = {
    "dead": ["dead", "no power", "power", "off"],
    "band": ["dead", "power", "off"],
    "on": ["power", "boot"],
    "charging": ["charging", "charge", "charger", "usb", "vbus"],
    "charge": ["charging", "charger", "usb"],
    "network": ["network", "signal", "baseband", "modem", "sim", "imei"],
    "signal": ["network", "signal", "baseband"],
    "sim": ["sim", "network", "baseband"],
    "display": ["display", "screen", "lcd", "backlight", "oled"],
    "screen": ["display", "screen", "lcd"],
    "light": ["backlight", "display"],
    "restart": ["restart", "reboot", "bootloop", "boot", "logo"],
    "reboot": ["restart", "reboot", "bootloop", "boot"],
    "logo": ["logo", "boot", "bootloop", "stuck"],
    "hang": ["hang", "freeze", "stuck", "logo"],
    "garam": ["overheating", "heat", "hot", "thermal"],
    "heat": ["overheating", "heat", "hot", "thermal"],
    "hot": ["overheating", "heat", "thermal"],
    "wifi": ["wifi", "wlan", "bluetooth"],
    "bluetooth": ["bluetooth", "wifi", "bt"],
    "awaz": ["audio", "speaker", "sound", "mic"],
    "awaaz": ["audio", "speaker", "sound", "mic"],
    "sound": ["audio", "speaker", "sound"],
    "speaker": ["audio", "speaker", "amplifier"],
    "mic": ["mic", "microphone", "audio"],
    "drain": ["drain", "battery", "leakage"],
    "battery": ["battery", "vbat", "drain"],
    "short": ["short", "leakage", "shorted"],
    "pani": ["water", "liquid", "corrosion"],
    "water": ["water", "liquid", "corrosion"],
    "touch": ["touch", "digitizer"],
    "camera": ["camera"],
    "fingerprint": ["fingerprint", "fp"],
}

STOPWORDS = {
    "the", "a", "an", "is", "are", "and", "or", "of", "to", "in", "on", "for",
    "hai", "he", "h", "nahi", "nhi", "ho", "raha", "rha", "rahi", "kya", "ka",
    "ki", "ke", "ko", "me", "mein", "se", "phone", "mobile", "mera", "mere",
    "not", "no", "working", "kaam", "kar", "kr", "problem", "issue",
}


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOPWORDS]


def _expand(tokens: List[str]) -> List[str]:
    out = []
    for t in tokens:
        out.append(t)
        out.extend(SYNONYMS.get(t, []))
    return list(dict.fromkeys(out))  # dedupe, keep order


def _score(query_terms: List[str], text: str, boost_text: str = "") -> float:
    """Count query terms that appear in text; terms in boost_text count double."""
    hay = text.lower()
    boost = boost_text.lower()
    score = 0.0
    for term in query_terms:
        if term in boost:
            score += 2
        elif term in hay:
            score += 1
    return score


def _norm_chip(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _load(name: str) -> Dict[str, Any]:
    path = CONFIG_DIR / name
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"[Jack] Could not load {name}: {e}")
        return {}


class KnowledgeBase:
    """Loads all repair databases once and answers search queries."""

    CHIP_FAMILIES = ("mediatek", "qualcomm", "samsung_exynos", "unisoc")

    def __init__(self):
        self.reload()

    def reload(self) -> None:
        self.phones = _load("phone_database.json")
        self.chipsets = _load("chipset_ic_database.json")
        self.community = _load("community_faults.json")
        self.history = _load("repair_history.json")

    # ── Phones ──────────────────────────────────────────────────────────
    def search_phone(self, model: str, limit: int = 3) -> Dict[str, Any]:
        """Find phone models by name / codename / chipset."""
        terms = _tokens(model)
        if not terms:
            return {"found": False, "message": "Model name required"}
        # Tokens with digits ("y20", "10", "a15") identify the model — they must match exactly,
        # otherwise "Vivo Y20" would wrongly return "Vivo Y200".
        key_terms = [t for t in terms if any(ch.isdigit() for ch in t)]
        exact, close = [], []
        for brand, models in self.phones.get("devices", {}).items():
            if not isinstance(models, dict):
                continue
            for name, info in models.items():
                name_toks = set(_tokens(name) + _tokens(brand.replace("_", " ")))
                s = sum(3 for t in terms if t in name_toks)
                s += sum(1 for t in terms if t not in name_toks and t in json.dumps(info).lower())
                if set(_tokens(name)) == set(terms) or set(_tokens(name)) == set(terms) - set(_tokens(brand)):
                    s += 10  # whole name matches
                if s <= 0:
                    continue
                entry = (s, len(name), brand, name, info)
                if all(t in name_toks for t in key_terms):
                    exact.append(entry)
                elif any(t in name_toks for t in terms):
                    close.append(entry)
        # best score first; shorter name wins ties ("Redmi Note 10" before "Redmi Note 10 Pro")
        for lst in (exact, close):
            lst.sort(key=lambda x: (-x[0], x[1]))
        if exact:
            return {"found": True, "exact": True,
                    "results": [{"brand": b, "model": n, **i} for _, _, b, n, i in exact[:limit]]}
        if close:
            return {"found": False, "exact": False,
                    "message": f"'{model}' exact database mein nahi hai. Milte-julte models:",
                    "similar_models": [n for _, _, _, n, _ in close[:limit]]}
        return {"found": False, "message": f"'{model}' phone database mein nahi mila"}

    def get_edl_test_point(self, model: str) -> Dict[str, Any]:
        terms = _tokens(model)
        best = None
        for brand, points in self.phones.get("edl_test_points", {}).items():
            if not isinstance(points, dict):
                continue
            for name, desc in points.items():
                s = _score(terms, name + " " + brand, boost_text=name)
                if best is None or s > best[0]:
                    best = (s, brand, name, desc, points.get("general"))
        if not best or best[0] < 2:
            return {"found": False, "message": f"'{model}' ka EDL test point database mein nahi hai",
                    "how_to": self.phones.get("edl_test_points", {}).get("_description", "")}
        _, brand, name, desc, general = best
        return {"found": True, "brand": brand, "model": name, "test_point": desc,
                "brand_general_note": general}

    def get_brand_tools(self, brand: str) -> Dict[str, Any]:
        tools = self.phones.get("brand_specific_tools", {})
        b = _norm_chip(brand)
        for key, info in tools.items():
            if b and (b in _norm_chip(key) or _norm_chip(key) in b):
                return {"found": True, "brand": key, **info}
        return {"found": False, "available_brands": list(tools.keys())}

    # ── Chipsets / ICs ─────────────────────────────────────────────────
    def get_chipset_info(self, chip: str) -> Dict[str, Any]:
        """Look up a SoC (MT6765, SM6225, Helio G35, Snapdragon 680) or any IC (MT6357, BQ25601)."""
        q = _norm_chip(chip)
        if not q:
            return {"found": False, "message": "Chipset/IC name required"}
        q_toks = set(_tokens(chip))

        # 1. SoC by code or marketing name ("Helio P35 / G35" must match "Helio G35" and "G35")
        for family in self.CHIP_FAMILIES:
            for code, info in self.chipsets.get(family, {}).items():
                if not isinstance(info, dict):
                    continue
                mname = str(info.get("marketing_name", ""))
                names = [_norm_chip(code)] + [_norm_chip(n) for n in mname.split("/")]
                m_toks = set(_tokens(mname))
                token_hit = (q_toks <= m_toks and any(any(c.isdigit() for c in t) for t in q_toks))
                if token_hit or q in names or any(n and len(q) >= 5 and q in n for n in names):
                    return {"found": True, "type": "soc", "family": family, "code": code, **info}

        # 2. Companion / common IC
        hits = []
        for category, ics in self.chipsets.get("common_ics", {}).items():
            if isinstance(ics, dict):
                for name, info in ics.items():
                    if q in _norm_chip(name):
                        hits.append({"category": category, "ic": name, **(info if isinstance(info, dict) else {"info": info})})
        for family in self.CHIP_FAMILIES:
            for code, info in self.chipsets.get(family, {}).items():
                comp = info.get("companion_ics", {}) if isinstance(info, dict) else {}
                for name, cinfo in comp.items():
                    if q in _norm_chip(name):
                        hits.append({"ic": name, "used_with_soc": code, **(cinfo if isinstance(cinfo, dict) else {})})
        for addr, desc in self.chipsets.get("i2c_address_map", {}).items():
            if q in _norm_chip(desc):
                hits.append({"i2c_address": addr, "ic": desc})
        if hits:
            return {"found": True, "type": "ic", "matches": hits[:6]}
        return {"found": False, "message": f"'{chip}' chipset/IC database mein nahi mila"}

    # ── Symptoms → fault patterns ──────────────────────────────────────
    def search_fault_patterns(self, symptom: str, limit: int = 2) -> Dict[str, Any]:
        terms = _expand(_tokens(symptom))
        scored = []
        for key, pattern in self.chipsets.get("fault_patterns", {}).items():
            boost = key.replace("_", " ") + " " + str(pattern.get("symptom", ""))
            s = _score(terms, json.dumps(pattern, ensure_ascii=False), boost_text=boost)
            if s > 0:
                scored.append((s, key, pattern))
        scored.sort(key=lambda x: -x[0])
        if not scored:
            return {"found": False, "message": "Is symptom ka fault pattern nahi mila",
                    "known_patterns": list(self.chipsets.get("fault_patterns", {}).keys())}
        top = scored[0][0]
        scored = [x for x in scored if x[0] >= top * 0.6]   # drop weak secondary matches
        # Log-evidence regex lists are for log analysis, not symptom diagnosis — skip them to save tokens.
        skip = ("boot_log_evidence", "dmesg_evidence")
        return {"found": True, "results": [{"pattern_id": k, **{f: v for f, v in p.items() if f not in skip}}
                                           for _, k, p in scored[:limit]]}

    # ── Community fixes ────────────────────────────────────────────────
    def search_community_fixes(self, query: str, brand: str = "", chipset: str = "",
                               limit: int = 3, min_score: float = 1) -> Dict[str, Any]:
        terms = _expand(_tokens(query))
        brand_n, chip_n = _norm_chip(brand), _norm_chip(chipset)
        keep = ("device_model", "brand", "chipset", "symptom", "fault_component", "root_cause",
                "fix_description", "repair_steps", "parts_used", "difficulty", "success_rate",
                "confirmed_fix_count", "tech_notes")
        scored = []
        for e in self.community.get("entries", []):
            boost = f"{e.get('symptom', '')} {e.get('device_model', '')} {e.get('fault_component', '')}"
            s = _score(terms, json.dumps(e, ensure_ascii=False), boost_text=boost)
            if brand_n and brand_n in _norm_chip(e.get("brand", "") + e.get("device_model", "")):
                s += 3
            if chip_n and chip_n in _norm_chip(e.get("chipset", "")):
                s += 3
            if s >= min_score:
                scored.append((s, e))
        scored.sort(key=lambda x: (-x[0], -(x[1].get("confirmed_fix_count") or 0)))
        if not scored:
            return {"found": False, "message": "Community database mein matching fix nahi mila"}
        return {"found": True, "results": [{k: e.get(k) for k in keep if e.get(k)} for _, e in scored[:limit]]}

    # ── Shop's own repair / detection history ──────────────────────────
    def search_repair_history(self, query: str, limit: int = 5) -> Dict[str, Any]:
        terms = _expand(_tokens(query))
        keep = ("type", "device_name", "summary", "faults_summary", "date", "status",
                "healthy_components", "fault", "fix", "notes")
        records = [("repair", r) for r in self.history.get("repairs", [])] + \
                  [("detection", r) for r in self.history.get("detections", [])]
        scored = []
        for kind, r in records:
            s = _score(terms, json.dumps(r, ensure_ascii=False),
                       boost_text=str(r.get("device_name", "")) + " " + str(r.get("faults_summary", "")))
            if s > 0 or not terms:
                scored.append((s, r.get("date", ""), kind, r))
        scored.sort(key=lambda x: x[1], reverse=True)   # newest first...
        scored.sort(key=lambda x: -x[0])                # ...then best match (stable sort)
        if not scored:
            return {"found": False, "message": "History mein matching record nahi mila",
                    "total_records": len(records)}
        out = []
        for _, _, kind, r in scored[:limit]:
            item = {"record_type": kind, **{k: r.get(k) for k in keep if r.get(k)}}
            out.append(item)
        return {"found": True, "total_records": len(records), "results": out}

    def stats(self) -> Dict[str, int]:
        return {
            "phones": sum(len(v) for v in self.phones.get("devices", {}).values() if isinstance(v, dict)),
            "fault_patterns": len(self.chipsets.get("fault_patterns", {})),
            "community_fixes": len(self.community.get("entries", [])),
            "history_records": len(self.history.get("repairs", [])) + len(self.history.get("detections", [])),
        }
