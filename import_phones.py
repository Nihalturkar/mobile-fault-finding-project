#!/usr/bin/env python3
"""
Safe bulk phone importer for config/phone_database.json.

The existing DB had many phones with a WRONG placeholder chipset code (e.g.
MT6877 for every Dimensity). This importer fixes that class of error for good:
whenever the chipset NAME is known, it writes the CORRECT MediaTek/Unisoc code
automatically, and warns on anything it can't verify.

Usage:
    # add from a CSV (columns: brand,model,chipset_name,battery,common_faults[;...],pmic,charging_ic,display)
    python import_phones.py phones.csv

    # or import the add_phone() function from your own script
    from import_phones import add_phone, load_db, save_db, soc_code_for

CSV example row:
    realme,Realme C51,Unisoc T612,5000mAh,"charging port;display flicker",SC2730,,IPS 6.74"
"""
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

DB = Path(__file__).resolve().parent / "config" / "phone_database.json"

# marketing name (lowercase substring, longest-match wins) -> correct SoC code
SOC_CODE = {
    # MediaTek Dimensity
    "dimensity 9300": "MT6989", "dimensity 9200+": "MT6985", "dimensity 9200": "MT6985",
    "dimensity 9000": "MT6983", "dimensity 8300": "MT6897", "dimensity 8200": "MT6896",
    "dimensity 8100": "MT6895", "dimensity 7350": "MT6878", "dimensity 7300": "MT6878",
    "dimensity 7200": "MT6886", "dimensity 7050": "MT6877", "dimensity 7025": "MT6855",
    "dimensity 7020": "MT6855", "dimensity 930": "MT6855", "dimensity 1300": "MT6893",
    "dimensity 1200": "MT6893", "dimensity 1080": "MT6877", "dimensity 920": "MT6877",
    "dimensity 900": "MT6877", "dimensity 810": "MT6833", "dimensity 800u": "MT6853",
    "dimensity 720": "MT6853", "dimensity 700": "MT6833", "dimensity 6300": "MT6835",
    "dimensity 6100+": "MT6835", "dimensity 6080": "MT6833", "dimensity 6020": "MT6833",
    # MediaTek Helio
    "helio g99": "MT6789", "helio g96": "MT6781", "helio g95": "MT6785", "helio g91": "MT6769",
    "helio g90": "MT6785", "helio g88": "MT6769", "helio g85": "MT6769", "helio g81": "MT6769",
    "helio g80": "MT6769", "helio g70": "MT6769", "helio g37": "MT6765", "helio g36": "MT6765",
    "helio g35": "MT6765", "helio p35": "MT6765", "helio p65": "MT6768", "helio p22": "MT6762",
    "helio a22": "MT6761", "helio a25": "MT6762",
    # Unisoc
    "unisoc t612": "T612", "unisoc t606": "T606", "unisoc t616": "T616", "unisoc t618": "T618",
    "unisoc t620": "T620", "unisoc t760": "T760", "unisoc t820": "T820", "unisoc sc9863": "SC9863A",
    # Qualcomm (name -> code)
    "snapdragon 680": "SM6225", "snapdragon 685": "SM6225", "snapdragon 695": "SM6375",
    "snapdragon 4 gen 2": "SM4450", "snapdragon 6 gen 1": "SM6450", "snapdragon 7 gen 1": "SM7435",
    "snapdragon 8 gen 2": "SM8550", "snapdragon 8 gen 3": "SM8650",
}
_KEYS = sorted(SOC_CODE, key=len, reverse=True)


def soc_code_for(chipset_name: str) -> str:
    """Return the correct SoC code for a marketing name, or '' if unknown."""
    n = (chipset_name or "").lower()
    for k in _KEYS:
        if k in n:
            return SOC_CODE[k]
    return ""


def load_db() -> dict:
    return json.loads(DB.read_text(encoding="utf-8"))


def save_db(d: dict) -> str:
    bak = str(DB) + ".bak_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(DB, bak)
    DB.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    return bak


def add_phone(d: dict, brand: str, model: str, chipset_name: str = "", code: str = "",
              battery: str = "", faults=None, pmic: str = "", charging_ic: str = "",
              display: str = "", overwrite: bool = False):
    """Add/merge one phone into db dict `d`. Returns (status, message)."""
    brand = brand.strip().lower().replace(" ", "_")
    dev = d.setdefault("devices", {}).setdefault(brand, {})
    if model in dev and not overwrite:
        return "skip", f"{model}: already exists"
    final_code = code.strip() or soc_code_for(chipset_name)
    warn = ""
    if chipset_name and not final_code:
        warn = " ⚠ code auto-detect nahi hua — manually bharo"
    elif code and chipset_name:
        auto = soc_code_for(chipset_name)
        if auto and auto.upper() != code.strip().upper():
            final_code = auto
            warn = f" ⚠ given code {code} != {auto} (name se) — {auto} use kiya"
    entry = {"chipset": final_code, "chipset_name": chipset_name,
             "battery": battery, "common_faults": faults or []}
    for k, v in (("pmic", pmic), ("charging_ic", charging_ic), ("display", display)):
        if v:
            entry[k] = v
    dev[model] = {k: v for k, v in entry.items() if v or k == "common_faults"}
    return "ok", f"{model}: added as {final_code or '?'}{warn}"


def main(csv_path: str):
    d = load_db()
    rows = 0
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            faults = [x.strip() for x in (r.get("common_faults") or "").split(";") if x.strip()]
            status, msg = add_phone(d, r.get("brand", ""), r.get("model", ""),
                                    r.get("chipset_name", ""), r.get("chipset", ""),
                                    r.get("battery", ""), faults, r.get("pmic", ""),
                                    r.get("charging_ic", ""), r.get("display", ""))
            print(f"  [{status}] {msg}")
            rows += 1
    bak = save_db(d)
    total = sum(len(v) for v in d["devices"].values())
    print(f"\nProcessed {rows} rows. DB now {total} phones. Backup: {bak}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    main(sys.argv[1])
