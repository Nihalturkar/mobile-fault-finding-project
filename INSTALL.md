# Schematic Diagnosis Integration — Install Guide (Hinglish + English)

## Kya ye hai? / What is this?

Ye integration aapke **Mooxy AI Fault Detector** me board flat-dump (schematic)
diagnosis add karta hai. Ab aap:

1. `config/boardviews/` me apna board flat-dump JSON daalo (REFOX ya skilbypm format)
2. Fault pattern chuno (jaise `camera_not_working`)
3. Tool automatically us fault ke **test points** (AVDD, DVDD, MCLK, I2C nets...)
   real board par dhoondh kar **board image par highlight** karega
4. Multimeter se reading lo, tool me type karo → **OK / ZERO / LOW / HIGH** verdict
5. Report + highlighted image export karo

This adds schematic-driven hardware diagnosis: fault pattern → real test points on
your board → multimeter reading → verdict → report with highlighted board image.

---

## Nayi files / New files (copy as-is)

| File | Kya karta hai |
|---|---|
| `app/hardware/boardview_loader.py` | Board flat-dump loader — **REFOX** (`netName` + `diode` on pins) aur **skilbypm v1.0** (`netTable`/`netIndex`) dono formats. Net index, test-point ranking (testPads pehle), PIL highlight renderer. |
| `app/hardware/schematic_diagnosis.py` | Fault pattern → test plan → measurement compare (OK/ZERO/LOW/HIGH) → text report + highlighted PNG. Expected voltages `config/chipset_ic_database.json` ke `test_points` se aate hain. |
| `app/hardware/camera_tester.py` | ADB se camera evidence (dumpsys media.camera, logcat, /dev/video, HAL props) — **read-only**, `shell=True` nahi use karta. |
| `app/gui/pages/schematic_diagnostics.py` | GUI page — board select, fault pattern select, "Run camera evidence" button, measurement entries, live report. |
| `config/boardviews/index.json` | Boardviews folder ka documentation index (auto-detection `*.json` glob se hoti hai). |

## Patch ki hui files / Patched files (replace kar do)

| File | Kya change hua |
|---|---|
| `app/gui/main_window.py` | Sidebar nav me `🔬 Schematic Diagnosis` item + `show_schematic_diagnostics()` method add hua; `show_export()` ka nav index 11 → 12. |
| `config/chipset_ic_database.json` | Sab 12 fault patterns me `test_points` array add hua (`{"ic", "nets": [keywords], "volts"}`). Yahi se expected rail voltages aate hain — yahin edit karoge to naye boards ke liye tunable. |
| `MooxyAI.spec` | hiddenimports me 4 naye modules. (Pura `config` folder pehle se bundled hai, isliye `config/boardviews` automatically EXE me chala jayega.) |
| `MobileRepairToolPro.spec` | Same 4 hiddenimports. |

---

## Install steps

1. **Backup** apna current project folder.
2. Upar wali files apne project me copy/replace karo (paths same rakho).
3. `config/boardviews/` folder me apna flat-dump JSON daalo:
   - skilbypm: e.g. `POCO M2_flat.json` (Mooxy Bitmap Editor ka export)
   - REFOX: e.g. `sdffgdgh_flat_dump.json` (iPhone 12 flat dump)
4. `pip install pillow` (agar nahi hai) — highlight render ke liye.
5. App chalao: `python run_gui.py` → sidebar me **🔬 Schematic Diagnosis**.

### Optional: sample board test

Apne Mooxy editor folder se `POCO M2_flat.json` copy karke
`config/boardviews/` me daal do. Page load hote hi dikh jayega:
`1093 comps · 4278 pins · 503 nets · image ✓`.

---

## Use flow (GUI)

1. Board dropdown se board select karo (auto-load hota hai pehla board).
2. **Fault pattern** chuno — ya **⚡ Run Camera Evidence** dabao (device ADB
   se connected ho to live camera HAL evidence milta hai).
3. **Generate Test Plan** → har net ke best probe points dikhenge
   (testPads > FPAD > sabse bada pad priority ke saath).
4. Board image par markers aayenge — multimeter probe wahin rakho.
5. Reading type karo → status icon: ✓ OK, ✗ ZERO (rail dead), ↘ LOW, ↗ HIGH.
6. **Apply & Report** → full report + highlighted PNG export.

## Use flow (headless / CLI)

```bash
# board summary + nets + highlight
python app/hardware/boardview_loader.py "config/boardviews/POCO M2_flat.json" CAM out.png

# camera diagnosis (ADB evidence + test plan + report)
python -c "from app.hardware.camera_tester import diagnose_camera; \
import json; print(json.dumps(diagnose_camera('', 'config/boardviews/POCO M2_flat.json'), indent=2, ensure_ascii=False)[:3000])"
```

---

## Naya fault pattern / expected voltage kaise add karein

`config/chipset_ic_database.json` → `fault_patterns.<pattern>.test_points`:

```json
"test_points": [
  {"ic": "Camera PMIC", "nets": ["AVDD", "DVDD", "DOVDD"], "volts": 2.8},
  {"ic": "Camera connector", "nets": ["CAM_CLK", "MCLK", "SCL", "SDA"], "volts": null}
]
```

- `nets` = **substring keywords** — board ke real net names par match hote hain
  (`AVDD` → `AVDD_EN`, `FM_AVDD28`, ...).
- `volts` = expected rail voltage (`null` = signal/clock line, sirf diode-mode
  comparison karo). Matching bhi built-in rail hints se hoti hai (VBAT≈3.8, VSYS≈4.2...).

## PyInstaller build note

`config/boardviews/` pura `config` folder ke saath EXE me bundle hota hai.
Production build se pehle bade sample flat-dumps (8MB+) hata do — sirf
`index.json` rakho, warna EXE size badh jayega. Users apne boards
`config/boardviews/` me drop karte hain.

## Testing status (sandbox me verified)

- POCO M2 skilbypm load: 1093 comps / 4278 pins / 503 named nets ✓
- camera_not_working plan: 90 real test points matched on board ✓
- REFOX-style fixture (netName+diode+testPads): load, plan, render ✓
- Highlight render (embedded 4200×1440 board image + markers) ✓
- camera_tester without adb: graceful empty evidence, no crash ✓
- Full suite: **15/15 passed** (`test_results.txt`)
