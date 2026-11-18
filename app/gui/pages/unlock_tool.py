"""
Unlock Tool — one consolidated, ownership-gated screen-lock + FRP page.

Replaces the old separate "Auto Unlock" and "FRP / Lock Unlock" pages.
It drives the real backends (app.hardware.frp_unlocker) and is honest about
what each method does:

    • Screen lock (PIN/pattern):  lock-file delete keeps data on OLD / rooted
      phones; on modern encrypted phones only a factory reset removes it (data
      is wiped) — the UI says which one will happen.
    • FRP (Google account after reset):  bypass so the GENUINE owner can set the
      phone up again.

Ownership gate:  no unlock button works until the technician records the owner
and confirms the device is the customer's own. Every unlock is logged to
config/unlock_log.json. This is the legitimate repair-shop workflow — the tool
is for phones the customer owns, not for defeating theft protection.
"""

import json
import threading
import time
import datetime as _dt
from pathlib import Path

import customtkinter as ctk

_LOG_FILE = Path(__file__).resolve().parent.parent.parent.parent / "config" / "unlock_log.json"

PROOF_OPTIONS = [
    "Purchase bill / invoice",
    "Owner ID + matching box/IMEI",
    "Customer written statement",
    "Shop job-sheet (known customer)",
]


# ── ownership log ────────────────────────────────────────────────────────────

def _append_log(record: dict) -> None:
    try:
        data = []
        if _LOG_FILE.exists():
            data = json.loads(_LOG_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        data.append(record)
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LOG_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[Unlock] could not write log: {e}")


# ── page ─────────────────────────────────────────────────────────────────────

def render_unlock_tool(app):
    colors = app.colors
    app.set_active_nav(6)

    state = {"busy": False, "status": None, "owner_ok": False}

    scroll = app.content
    for w in scroll.winfo_children():
        w.destroy()

    # ── header ──
    head = ctk.CTkFrame(scroll, fg_color="transparent")
    head.pack(fill="x", padx=20, pady=(16, 4))
    ctk.CTkLabel(head, text="🔓 Unlock Tool", font=("Segoe UI", 26, "bold"),
                 text_color=colors["text"]).pack(anchor="w")
    ctk.CTkLabel(head, text="Screen lock (PIN/pattern) + FRP removal — genuine, customer-owned devices only",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w")

    # ── honesty banner ──
    note = ctk.CTkFrame(scroll, fg_color=colors["bg_card"], corner_radius=10,
                        border_width=1, border_color=colors["warning"])
    note.pack(fill="x", padx=20, pady=(10, 6))
    ctk.CTkLabel(note, text="ⓘ  Modern phones (Android 6+) ka lock bina data wipe kiye software se nahi tootta "
                            "— ye hardware encryption hai. Yahan jo hota hai:",
                 font=("Segoe UI", 12, "bold"), text_color=colors["warning"],
                 justify="left", wraplength=1100).pack(anchor="w", padx=14, pady=(10, 2))
    for line in ("• Purana / rooted phone  →  lock-file delete (DATA BACHTA HAI)",
                 "• Modern encrypted phone  →  sirf factory reset se lock hatega (DATA UDD JAATA HAI)",
                 "• FRP bypass  →  reset ke baad Google account lock, taaki genuine owner phone dobara setup kar sake"):
        ctk.CTkLabel(note, text=line, font=("Segoe UI", 12), text_color=colors["text"],
                     justify="left").pack(anchor="w", padx=22, pady=1)
    ctk.CTkLabel(note, text="", height=4, fg_color="transparent").pack()

    # ── STEP 1: ownership gate ──
    gate = ctk.CTkFrame(scroll, fg_color=colors["bg_medium"], corner_radius=12,
                        border_width=2, border_color=colors["accent"])
    gate.pack(fill="x", padx=20, pady=(8, 6))
    ctk.CTkLabel(gate, text="STEP 1 — Ownership (zaroori)", font=("Segoe UI", 14, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=16, pady=(12, 2))
    ctk.CTkLabel(gate, text="Unlock sirf genuine, customer ke apne phone pe. Niche bharo, tabhi buttons on honge.",
                 font=("Segoe UI", 12), text_color=colors["text_dim"]).pack(anchor="w", padx=16)

    form = ctk.CTkFrame(gate, fg_color="transparent")
    form.pack(fill="x", padx=16, pady=(8, 4))
    form.grid_columnconfigure(1, weight=1)
    form.grid_columnconfigure(3, weight=1)

    ctk.CTkLabel(form, text="Owner name", font=("Segoe UI", 12),
                 text_color=colors["text"]).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=5)
    owner_entry = ctk.CTkEntry(form, placeholder_text="Customer ka naam", height=34,
                               fg_color=colors["bg_light"], border_color=colors["border"])
    owner_entry.grid(row=0, column=1, sticky="ew", pady=5)

    ctk.CTkLabel(form, text="Proof", font=("Segoe UI", 12),
                 text_color=colors["text"]).grid(row=0, column=2, sticky="w", padx=(16, 8), pady=5)
    proof_var = ctk.StringVar(value=PROOF_OPTIONS[0])
    ctk.CTkOptionMenu(form, values=PROOF_OPTIONS, variable=proof_var, height=34,
                      fg_color=colors["bg_light"], button_color=colors["border"]).grid(
        row=0, column=3, sticky="ew", pady=5)

    ctk.CTkLabel(form, text="Phone / IMEI", font=("Segoe UI", 12),
                 text_color=colors["text"]).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=5)
    imei_entry = ctk.CTkEntry(form, placeholder_text="IMEI ya phone number (optional)", height=34,
                              fg_color=colors["bg_light"], border_color=colors["border"])
    imei_entry.grid(row=1, column=1, sticky="ew", pady=5)

    confirm_var = ctk.BooleanVar(value=False)

    def on_gate_change(*_):
        ok = bool(owner_entry.get().strip()) and confirm_var.get()
        state["owner_ok"] = ok
        refresh_actions()

    confirm_chk = ctk.CTkCheckBox(
        gate, variable=confirm_var, onvalue=True, offvalue=False, command=on_gate_change,
        text="Main confirm karta hoon: ye phone customer ka apna hai, aur unlock ki permission hai.",
        font=("Segoe UI", 12, "bold"), text_color=colors["text"],
        fg_color=colors["success"], hover_color=colors["success"])
    confirm_chk.pack(anchor="w", padx=16, pady=(4, 12))
    owner_entry.bind("<KeyRelease>", on_gate_change)

    # ── STEP 2: device scan ──
    scan_card = ctk.CTkFrame(scroll, fg_color=colors["bg_medium"], corner_radius=12)
    scan_card.pack(fill="x", padx=20, pady=6)
    srow = ctk.CTkFrame(scan_card, fg_color="transparent")
    srow.pack(fill="x", padx=16, pady=12)
    ctk.CTkLabel(srow, text="STEP 2 — Device scan", font=("Segoe UI", 14, "bold"),
                 text_color=colors["info"]).pack(side="left")
    scan_btn = ctk.CTkButton(srow, text="🔍 Scan connected device", height=36, width=210,
                             font=("Segoe UI", 13, "bold"), fg_color=colors["info"],
                             hover_color="#c084fc", command=lambda: do_scan())
    scan_btn.pack(side="right")

    # status grid
    grid = ctk.CTkFrame(scan_card, fg_color="transparent")
    grid.pack(fill="x", padx=16, pady=(0, 8))
    for i in range(4):
        grid.grid_columnconfigure(i, weight=1, uniform="s")
    status_cells = {}
    cell_defs = [("brand", "Brand / Model"), ("android", "Android"), ("mode", "Mode"),
                 ("lock", "Screen lock"), ("frp", "FRP"), ("encryption", "Encryption"),
                 ("account", "Google / Mi"), ("knox", "Knox / Root")]
    for n, (key, label) in enumerate(cell_defs):
        cell = ctk.CTkFrame(grid, fg_color=colors["bg_dark"], corner_radius=8,
                            border_width=1, border_color=colors["border"])
        cell.grid(row=n // 4, column=n % 4, padx=4, pady=4, sticky="ew")
        ctk.CTkLabel(cell, text=label, font=("Segoe UI", 10), text_color=colors["text_dim"]).pack(
            anchor="w", padx=10, pady=(6, 0))
        val = ctk.CTkLabel(cell, text="—", font=("Segoe UI", 13, "bold"), text_color=colors["text"])
        val.pack(anchor="w", padx=10, pady=(0, 6))
        status_cells[key] = val

    assess = ctk.CTkLabel(scan_card, text="Pehle device scan karo — phir tool batayega kya possible hai.",
                          font=("Segoe UI", 12, "bold"), text_color=colors["text_dim"],
                          justify="left", wraplength=1100)
    assess.pack(anchor="w", padx=16, pady=(0, 12))

    # ── STEP 3: actions ──
    act_card = ctk.CTkFrame(scroll, fg_color=colors["bg_medium"], corner_radius=12)
    act_card.pack(fill="x", padx=20, pady=6)
    ctk.CTkLabel(act_card, text="STEP 3 — Unlock action", font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=16, pady=(12, 2))
    act_row = ctk.CTkFrame(act_card, fg_color="transparent")
    act_row.pack(fill="x", padx=16, pady=(4, 12))

    lock_btn = ctk.CTkButton(act_row, text="🔓 Remove Screen Lock\n(PIN / pattern)", height=56, width=230,
                             font=("Segoe UI", 13, "bold"), fg_color=colors["bg_light"],
                             hover_color=colors["border"], state="disabled",
                             command=lambda: confirm_and_run("screen"))
    lock_btn.pack(side="left", padx=(0, 10))
    frp_btn = ctk.CTkButton(act_row, text="🌐 Remove FRP\n(Google account lock)", height=56, width=230,
                            font=("Segoe UI", 13, "bold"), fg_color=colors["bg_light"],
                            hover_color=colors["border"], state="disabled",
                            command=lambda: confirm_and_run("frp"))
    frp_btn.pack(side="left", padx=(0, 10))
    reboot_btn = ctk.CTkButton(act_row, text="🔄 Reboot phone", height=56, width=150,
                               font=("Segoe UI", 13), fg_color=colors["bg_light"],
                               hover_color=colors["border"], state="disabled",
                               command=lambda: confirm_and_run("reboot"))
    reboot_btn.pack(side="left")

    gate_hint = ctk.CTkLabel(act_card, text="⤷  STEP 1 (ownership) bharo, tabhi ye buttons on honge.",
                             font=("Segoe UI", 11), text_color=colors["warning"])
    gate_hint.pack(anchor="w", padx=16, pady=(0, 12))

    # ── live log ──
    log_card = ctk.CTkFrame(scroll, fg_color=colors["bg_medium"], corner_radius=12)
    log_card.pack(fill="both", expand=True, padx=20, pady=(6, 16))
    lrow = ctk.CTkFrame(log_card, fg_color="transparent")
    lrow.pack(fill="x", padx=16, pady=(12, 2))
    ctk.CTkLabel(lrow, text="📟 Live log", font=("Segoe UI", 13, "bold"),
                 text_color=colors["text"]).pack(side="left")
    prog = ctk.CTkProgressBar(lrow, height=10, progress_color=colors["info"], fg_color=colors["bg_light"])
    prog.set(0)
    prog.pack(side="right", fill="x", expand=True, padx=(16, 0))
    logbox = ctk.CTkTextbox(log_card, height=200, font=("Consolas", 12), fg_color=colors["bg_dark"],
                            text_color=colors["text"], wrap="word")
    logbox.pack(fill="both", expand=True, padx=16, pady=(6, 14))
    tb = logbox._textbox
    for tag, col in (("ok", "#34d399"), ("warn", "#fbbf24"), ("err", "#ec4899"), ("info", "#a855f7")):
        tb.tag_configure(tag, foreground=col)
    logbox.configure(state="disabled")

    # ── helpers ──
    def alive():
        try:
            return log_card.winfo_exists()
        except Exception:
            return False

    def log(msg, tag=None):
        if not alive():
            return
        logbox.configure(state="normal")
        start = tb.index("end-1c")
        logbox.insert("end", msg + "\n")
        if tag:
            tb.tag_add(tag, start, tb.index("end-1c"))
        logbox.see("end")
        logbox.configure(state="disabled")

    def set_progress(pct, msg):
        if alive():
            prog.set(max(0.0, min(1.0, float(pct))))
            if msg:
                log(f"  {msg}", "info")

    def refresh_actions():
        if state["busy"]:
            return
        on = state["owner_ok"]
        st = state["status"]
        gate_hint.configure(
            text="✓ Ownership record ho gaya — ab unlock kar sakte ho." if on else
                 "⤷  STEP 1 (ownership) bharo, tabhi ye buttons on honge.",
            text_color=colors["success"] if on else colors["warning"])
        # buttons need ownership AND a successful scan showing a connected device
        ready = on and st is not None and getattr(st, "connected", False)
        for b, col in ((lock_btn, colors["accent"]), (frp_btn, colors["warning"]), (reboot_btn, colors["bg_light"])):
            b.configure(state="normal" if (ready or (b is reboot_btn and on)) else "disabled")
        lock_btn.configure(fg_color=colors["accent"] if ready else colors["bg_light"])
        frp_btn.configure(fg_color=colors["warning"] if ready else colors["bg_light"],
                          text_color="#1a1a1a" if ready else colors["text"])

    def set_busy(b):
        state["busy"] = b
        for w in (scan_btn, lock_btn, frp_btn, reboot_btn):
            w.configure(state="disabled" if b else "normal")
        if not b:
            refresh_actions()

    # ── device scan ──
    def do_scan():
        if state["busy"]:
            return
        set_busy(True)
        prog.set(0)
        log("", None)
        log("🔍 Device scan shuru…", "info")
        from app.hardware.frp_unlocker import check_lock_status

        def ui(fn, *a):
            try:
                app.after(0, lambda: fn(*a))
            except Exception:
                pass

        def work():
            try:
                res = check_lock_status(callback=lambda p, m: ui(set_progress, p, m))
            except Exception as e:
                ui(log, f"✗ Scan failed: {e}", "err")
                ui(set_busy, False)
                return
            ui(apply_scan, res)

        threading.Thread(target=work, daemon=True).start()

    def apply_scan(res):
        state["status"] = res
        if not res.connected:
            log("✗ Koi device nahi mila (ADB/fastboot). USB debugging ya download mode check karo.", "err")
            for v in status_cells.values():
                v.configure(text="—")
            assess.configure(text="Device connect nahi hua. Phone ko ADB (USB debugging) ya fastboot/download mode me lao.",
                             text_color=colors["accent"])
            set_busy(False)
            return
        c = colors
        status_cells["brand"].configure(text=f"{res.device_brand or '?'} {res.device_model or ''}".strip())
        status_cells["android"].configure(text=res.android_version or "?")
        status_cells["mode"].configure(text=res.adb_mode or "?")
        lock = res.screen_lock_type or "none"
        status_cells["lock"].configure(text=lock, text_color=c["warning"] if lock not in ("none", "unknown") else c["success"])
        status_cells["frp"].configure(text="ON" if res.frp_enabled else "off",
                                      text_color=c["warning"] if res.frp_enabled else c["success"])
        status_cells["encryption"].configure(text=res.encryption_status or "?")
        acct = []
        if res.google_accounts:
            acct.append(f"{len(res.google_accounts)} Google")
        if res.mi_account_bound:
            acct.append("Mi")
        status_cells["account"].configure(text=", ".join(acct) if acct else "none",
                                         text_color=c["warning"] if acct else c["success"])
        knox = []
        if res.knox_tripped:
            knox.append("Knox tripped")
        if res.root_access:
            knox.append("root")
        status_cells["knox"].configure(text=", ".join(knox) if knox else "clean")
        log(f"✓ {res.device_brand} {res.device_model} • Android {res.android_version} • mode {res.adb_mode}", "ok")

        # honest assessment
        enc = (res.encryption_status or "").lower()
        rooted = res.root_access
        modern = ("encrypt" in enc) and not rooted
        msgs = []
        if lock in ("none", "unknown"):
            msgs.append("Screen lock set nahi dikh raha.")
        elif rooted or (res.android_version and _ver_lt(res.android_version, 6)):
            msgs.append("✓ Screen lock lock-file delete se hatega — DATA BACHEGA (purana/rooted phone).")
        else:
            msgs.append("⚠ Ye encrypted phone hai — screen lock sirf FACTORY RESET se hatega, DATA UDD JAAYEGA.")
        if res.frp_enabled or res.google_accounts:
            msgs.append("FRP bypass available — reset ke baad genuine owner phone setup kar sake.")
        if res.knox_tripped:
            msgs.append("Samsung Knox tripped — kuch methods limited ho sakte hain.")
        assess.configure(text="  ".join(msgs),
                         text_color=c["warning"] if modern and lock not in ("none", "unknown") else c["text"])
        set_busy(False)

    # ── confirm + run unlock ──
    def confirm_and_run(kind):
        if state["busy"] or not state["owner_ok"]:
            return
        st = state["status"]
        wipes = False
        if kind == "screen":
            rooted = st and st.root_access
            old = st and st.android_version and _ver_lt(st.android_version, 6)
            wipes = not (rooted or old)
            title = "Remove Screen Lock"
            body = ("Ye phone encrypted hai — lock hataane ke liye FACTORY RESET hoga.\nSAARA DATA DELETE HO JAAYEGA."
                    if wipes else "Lock-file delete hoga. Data bachne ka chance hai, par guarantee nahi.")
        elif kind == "frp":
            title = "Remove FRP"
            body = "FRP partition / account lock hataane ki koshish. Kuch methods me reset ho sakta hai (data jaa sakta hai)."
        else:
            title = "Reboot phone"
            body = "Phone normal mode me reboot hoga."

        _confirm_dialog(app, colors, title, body, wipes,
                        on_yes=lambda: _start_unlock(kind))

    def _start_unlock(kind):
        set_busy(True)
        prog.set(0)
        log("", None)
        record = {
            "time": _dt.datetime.now().isoformat(timespec="seconds"),
            "owner": owner_entry.get().strip(),
            "proof": proof_var.get(),
            "phone_imei": imei_entry.get().strip(),
            "action": kind,
            "device": f"{getattr(state['status'],'device_brand','')} {getattr(state['status'],'device_model','')}".strip(),
        }
        _append_log(record)
        log(f"📝 Ownership record saved: {record['owner']} • {record['proof']}", "ok")
        log(f"▶ {kind.upper()} shuru…", "info")

        from app.hardware import frp_unlocker as F

        def ui(fn, *a):
            try:
                app.after(0, lambda: fn(*a))
            except Exception:
                pass

        def work():
            try:
                if kind == "screen":
                    res = F.remove_screen_lock(callback=lambda p, m: ui(set_progress, p, m))
                    ok, txt = res.success, F.format_screen_lock_result_text(res)
                    if getattr(res, "data_wiped", False):
                        ui(log, "⚠ Device data wiped (factory reset).", "warn")
                elif kind == "frp":
                    res = F.remove_frp(callback=lambda p, m: ui(set_progress, p, m))
                    ok, txt = res.success, F.format_frp_result_text(res)
                else:
                    ok = F.reboot_device("normal")
                    txt = "Reboot command sent." if ok else "Reboot failed."
            except Exception as e:
                ui(log, f"✗ Error: {e}", "err")
                ui(set_busy, False)
                return
            ui(finish_unlock, ok, txt, kind)

        threading.Thread(target=work, daemon=True).start()

    def finish_unlock(ok, txt, kind):
        for line in (txt or "").splitlines():
            t = "ok" if ok else "err"
            if any(k in line.lower() for k in ("warn", "wipe", "data")):
                t = "warn"
            log(line, t)
        log(("✓ " + kind.upper() + " done.") if ok else ("✗ " + kind.upper() + " could not complete."),
            "ok" if ok else "err")
        if ok:
            app.update_status(f"Unlock ({kind}) complete • logged")
        set_busy(False)

    refresh_actions()
    log("Ready. STEP 1 bharo, phir device scan karo.", "info")


def _ver_lt(version_str, major):
    try:
        return int(str(version_str).split(".")[0]) < major
    except Exception:
        return False


def _confirm_dialog(app, colors, title, body, danger, on_yes):
    win = ctk.CTkToplevel(app)
    win.title(title)
    win.geometry("460x240")
    win.transient(app)
    win.grab_set()
    win.configure(fg_color=colors["bg_medium"])
    ctk.CTkLabel(win, text=("⚠ " if danger else "") + title, font=("Segoe UI", 17, "bold"),
                 text_color=colors["accent"] if danger else colors["text"]).pack(anchor="w", padx=20, pady=(18, 6))
    ctk.CTkLabel(win, text=body, font=("Segoe UI", 13), text_color=colors["text"],
                 justify="left", wraplength=420).pack(anchor="w", padx=20)
    if danger:
        ctk.CTkLabel(win, text="Customer ko confirm kar lo — data wapas nahi aayega.",
                     font=("Segoe UI", 12, "bold"), text_color=colors["warning"]).pack(anchor="w", padx=20, pady=(8, 0))
    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack(side="bottom", fill="x", padx=20, pady=16)

    def yes():
        win.destroy()
        on_yes()

    ctk.CTkButton(btns, text="Cancel", width=120, height=38, fg_color=colors["bg_light"],
                  hover_color=colors["border"], command=win.destroy).pack(side="right", padx=(8, 0))
    ctk.CTkButton(btns, text="Haan, proceed", width=150, height=38,
                  fg_color=colors["accent"] if danger else colors["success"],
                  hover_color=colors["accent_hover"] if danger else "#6ee7b7",
                  command=yes).pack(side="right")
