import customtkinter as ctk
import threading
import datetime as _dt

from app.hardware.frp_unlocker import (
    check_lock_status,
    remove_frp,
    remove_screen_lock,
    check_mi_account,
    check_knox_status,
)


def render_frp_unlock(app):
    """FRP / Unlock Features page — tabbed interface with live report output."""
    colors = app.colors

    # ── Page Title ──────────────────────────────────────────────
    ctk.CTkLabel(
        app.content, text="\U0001f513 FRP / Unlock Features",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Factory Reset Protection bypass, screen lock removal, Mi Account & Knox checks",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 10))

    # ── Warning Card ────────────────────────────────────────────
    warn_card = ctk.CTkFrame(app.content, fg_color="#3d2e00", corner_radius=10,
                              border_width=1, border_color="#fbbf24")
    warn_card.pack(fill="x", padx=20, pady=(0, 10))
    warn_inner = ctk.CTkFrame(warn_card, fg_color="transparent")
    warn_inner.pack(fill="x", padx=15, pady=10)
    ctk.CTkLabel(
        warn_inner, text="\u26a0\ufe0f  Authorized Technicians Only",
        font=("Segoe UI", 14, "bold"), text_color="#fbbf24",
    ).pack(anchor="w")
    ctk.CTkLabel(
        warn_inner,
        text="For authorized repair technicians only. Ensure device ownership is verified before proceeding.",
        font=("Segoe UI", 12), text_color="#ffcc66", wraplength=700,
    ).pack(anchor="w", pady=(3, 0))

    # ── Tab Buttons Row ─────────────────────────────────────────
    tab_bar = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=10)
    tab_bar.pack(fill="x", padx=20, pady=(0, 8))
    tab_inner = ctk.CTkFrame(tab_bar, fg_color="transparent")
    tab_inner.pack(fill="x", padx=10, pady=8)

    tab_names = ["Check Status", "Remove FRP", "Remove Lock", "Mi Account", "Knox Status"]
    tab_buttons = {}
    tab_frames = {}
    active_tab = {"name": "Check Status"}

    running = {"value": False}

    # ── Progress + Status ───────────────────────────────────────
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"],
                                   fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")

    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 5))

    # ── Status Badge ────────────────────────────────────────────
    badge_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"],
                                corner_radius=10, height=40)
    badge_frame.pack(fill="x", padx=20, pady=(0, 5))
    badge_frame.pack_propagate(False)
    status_badge = ctk.CTkLabel(badge_frame, text="  Ready — select a tab and run an operation",
                                 font=("Segoe UI", 13), text_color=colors["text_dim"])
    status_badge.pack(side="left", padx=15, pady=8)

    # ── Tab Content Container ───────────────────────────────────
    tab_container = ctk.CTkFrame(app.content, fg_color="transparent")
    tab_container.pack(fill="x", padx=20, pady=(0, 5))

    # ── Report Textbox ──────────────────────────────────────────
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"],
                                 font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=400, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 10))
    report_box.insert("1.0",
        "FRP / Unlock Features — Ready\n"
        "─────────────────────────────────────────────\n"
        "Select a tab above, then run the desired operation.\n"
        "Results will appear here with color-coded output.\n"
    )

    # ── Color Tags Setup ────────────────────────────────────────
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#34d399")
        tb.tag_configure("warning", foreground="#fbbf24")
        tb.tag_configure("fault", foreground="#ec4899")
        tb.tag_configure("info", foreground="#a855f7")
        tb.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#9a93b5")

    _setup_tags()

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["[xx]", "fault", "failed", "error", "no ",
                                  "tripped", "bound", "enabled: yes"]):
            return "fault"
        if any(k in t for k in ["warning", "caution", "methods tried",
                                  "reboot", "data wiped"]):
            return "warning"
        if any(k in t for k in ["[ok]", "success", "intact", "none",
                                  "disabled", "no lock", "clean", "passed",
                                  "unlocked", "not tripped"]):
            return "ok"
        if any(k in t for k in ["\u2550\u2550\u2550", "===", "\u2500\u2500\u2500",
                                  "---", "========", "REPORT", "RESULT", "STATUS"]):
            return "header"
        if any(k in t for k in ["checking", "reading", "scanning", "detecting",
                                  "method", "step"]):
            return "info"
        return None

    # ── Live Append Helpers ─────────────────────────────────────
    def _append_live(text):
        def _do():
            report_box.configure(state="normal")
            tag = _get_tag(text)
            if tag:
                start = report_box._textbox.index("end-1c")
                report_box.insert("end", text + "\n")
                end = report_box._textbox.index("end-1c")
                report_box._textbox.tag_add(tag, start, end)
            else:
                report_box.insert("end", text + "\n")
            report_box.see("end")
        app.content.after(0, _do)

    def _append_live_lines(lines):
        def _do():
            report_box.configure(state="normal")
            for line in lines:
                tag = _get_tag(line)
                if tag:
                    start = report_box._textbox.index("end-1c")
                    report_box.insert("end", line + "\n")
                    end = report_box._textbox.index("end-1c")
                    report_box._textbox.tag_add(tag, start, end)
                else:
                    report_box.insert("end", line + "\n")
            report_box.see("end")
        app.content.after(0, _do)

    def _clear_report():
        def _do():
            report_box.configure(state="normal")
            report_box.delete("1.0", "end")
        app.content.after(0, _do)

    def _set_progress(pct):
        app.content.after(0, lambda: progress.set(pct))

    def _set_msg(text, color=None):
        c = color or colors["text_dim"]
        app.content.after(0, lambda: msg_label.configure(text=text, text_color=c))

    def _set_badge(text, color=None):
        c = color or colors["text_dim"]
        app.content.after(0, lambda: status_badge.configure(text=text, text_color=c))

    # ── Copy / Save Buttons Row ─────────────────────────────────
    btn_row = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_row.pack(fill="x", padx=20, pady=(0, 10))

    def copy_report():
        try:
            text = report_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            _set_msg("Report copied to clipboard!", colors["success"])
        except Exception:
            pass

    def save_report():
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text", "*.txt")],
                initialfile="frp_unlock_report.txt",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                _set_msg(f"Saved to: {path}", colors["success"])
        except Exception:
            pass

    ctk.CTkButton(btn_row, text="Copy Report", width=120, height=38,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_row, text="Save Report", width=120, height=38,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # ══════════════════════════════════════════════════════════════
    # TAB CONTENT BUILDERS
    # ══════════════════════════════════════════════════════════════

    # ── Check Status Tab ────────────────────────────────────────
    def _build_check_status_tab(parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        info_label = ctk.CTkLabel(
            frame,
            text="Check the complete security and lock status of the connected device.\n"
                 "Detects FRP, screen lock, encryption, Google accounts, bootloader, and root status.",
            font=("Segoe UI", 12), text_color=colors["text_dim"], wraplength=700,
            justify="left",
        )
        info_label.pack(anchor="w", pady=(5, 10))

        def start_check():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            _set_progress(0)
            _set_badge("  Checking device status...", colors["info"])

            def run():
                header = [
                    "=" * 65,
                    "  FRP / UNLOCK — DEVICE STATUS CHECK",
                    "=" * 65,
                    f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "=" * 65,
                    "",
                ]
                _append_live_lines(header)

                def cb(pct, msg):
                    _set_progress(pct)
                    _set_msg(msg)
                    _append_live(f"  \U0001f50d {msg}")

                try:
                    result = check_lock_status(callback=cb)

                    _append_live("")
                    _append_live("=" * 65)
                    _append_live("  DEVICE SECURITY STATUS REPORT")
                    _append_live("=" * 65)

                    if not result.connected:
                        _append_live(f"  ERROR: {result.error or 'No device connected'}")
                        _set_badge("  No device connected", colors["warning"])
                    else:
                        lines = [
                            f"  Device:          {result.device_brand} {result.device_model}",
                            f"  Android:         {result.android_version}",
                            f"  ADB Mode:        {result.adb_mode}",
                            "",
                            "-" * 65,
                            "  SECURITY STATUS",
                            "-" * 65,
                            f"  FRP Enabled:     {'YES' if result.frp_enabled else 'No'}",
                            f"  Screen Lock:     {result.screen_lock_type}",
                            f"  Encryption:      {result.encryption_status}",
                            f"  Secure Startup:  {'Yes' if result.secure_startup else 'No'}",
                            "",
                            "-" * 65,
                            "  ACCOUNTS & ACCESS",
                            "-" * 65,
                            f"  Google Accounts: {len(result.google_accounts)}",
                        ]
                        for acct in result.google_accounts:
                            lines.append(f"    - {acct}")
                        lines.extend([
                            f"  Samsung Account: {'Yes' if result.samsung_account else 'No'}",
                            f"  Mi Account:      {'BOUND' if result.mi_account_bound else 'None'}",
                            f"  Knox Tripped:    {'YES' if result.knox_tripped else 'No'}",
                            "",
                            "-" * 65,
                            "  BOOTLOADER & ROOT",
                            "-" * 65,
                            f"  Bootloader:      {'UNLOCKED' if result.bootloader_unlocked else 'Locked'}",
                            f"  Root Access:     {'Yes' if result.root_access else 'No'}",
                        ])
                        _append_live_lines(lines)

                        # Set badge based on overall status
                        issues = []
                        if result.frp_enabled:
                            issues.append("FRP")
                        if result.screen_lock_type not in ("none", "swipe"):
                            issues.append(f"Lock({result.screen_lock_type})")
                        if result.mi_account_bound:
                            issues.append("Mi Account")
                        if result.knox_tripped:
                            issues.append("Knox")

                        if issues:
                            _set_badge(f"  Issues found: {', '.join(issues)}", colors["warning"])
                        else:
                            _set_badge("  Device is clean — no locks or FRP detected", colors["success"])

                except Exception as e:
                    _append_live(f"  Error: {str(e)}")
                    _set_badge(f"  Error: {str(e)}", colors["warning"])

                _append_live("")
                _append_live("=" * 65)
                _append_live("  Check complete")
                _append_live("=" * 65)
                _set_progress(1.0)
                _set_msg("Status check complete", colors["success"])
                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(
            frame, text="Start Check", width=220, height=44,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 15, "bold"), corner_radius=10,
            command=start_check,
        ).pack(anchor="w", pady=(5, 0))

        return frame

    # ── Remove FRP Tab ──────────────────────────────────────────
    def _build_remove_frp_tab(parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        warn_frp = ctk.CTkFrame(frame, fg_color="#3d1515", corner_radius=8,
                                 border_width=1, border_color="#ec4899")
        warn_frp.pack(fill="x", pady=(5, 10))
        ctk.CTkLabel(
            warn_frp,
            text="\u26a0\ufe0f  FRP removal will attempt 4 methods in sequence:\n"
                 "  1. Content provider delete (least invasive)\n"
                 "  2. Settings activity bypass\n"
                 "  3. Package manager disable\n"
                 "  4. Fastboot partition erase (most invasive, may require bootloader)",
            font=("Segoe UI", 12), text_color="#ff6b6b", wraplength=700,
            justify="left",
        ).pack(padx=12, pady=10)

        def start_frp_removal():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            _set_progress(0)
            _set_badge("  FRP removal in progress...", colors["warning"])

            def run():
                header = [
                    "=" * 65,
                    "  FRP / UNLOCK — FRP REMOVAL",
                    "=" * 65,
                    f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "=" * 65,
                    "",
                ]
                _append_live_lines(header)

                def cb(pct, msg):
                    _set_progress(pct)
                    _set_msg(msg)
                    _append_live(f"  \U0001f527 {msg}")

                try:
                    result = remove_frp(callback=cb)

                    _append_live("")
                    _append_live("=" * 65)
                    _append_live("  FRP REMOVAL RESULT")
                    _append_live("=" * 65)

                    result_lines = [
                        f"  Success:         {'YES' if result.success else 'NO'}",
                        f"  Method Used:     {result.method_used or 'none'}",
                        f"  Methods Tried:   {result.methods_tried}",
                        f"  Reboot Needed:   {'Yes' if result.reboot_required else 'No'}",
                    ]
                    if result.device_brand:
                        result_lines.insert(0, f"  Device Brand:    {result.device_brand}")
                    if result.error:
                        result_lines.append(f"  Error:           {result.error}")

                    _append_live_lines(result_lines)

                    _append_live("")
                    _append_live("-" * 65)
                    _append_live("  STEPS PERFORMED")
                    _append_live("-" * 65)
                    for i, step in enumerate(result.steps_performed, 1):
                        _append_live(f"    {i:3d}. {step}")

                    if result.success:
                        _set_badge("  FRP removal successful — reboot device", colors["success"])
                    else:
                        _set_badge("  FRP removal failed — see report", colors["warning"])

                except Exception as e:
                    _append_live(f"  Error: {str(e)}")
                    _set_badge(f"  Error: {str(e)}", colors["warning"])

                _append_live("")
                _append_live("=" * 65)
                _set_progress(1.0)
                _set_msg("FRP removal complete", colors["success"])
                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(
            frame, text="Start FRP Removal", width=240, height=44,
            fg_color="#ec4899", hover_color="#c0392b",
            font=("Segoe UI", 15, "bold"), corner_radius=10,
            command=start_frp_removal,
        ).pack(anchor="w", pady=(5, 0))

        return frame

    # ── Remove Lock Tab ─────────────────────────────────────────
    def _build_remove_lock_tab(parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        selector_row = ctk.CTkFrame(frame, fg_color="transparent")
        selector_row.pack(fill="x", pady=(5, 10))

        ctk.CTkLabel(
            selector_row, text="Lock Type:",
            font=("Segoe UI", 13, "bold"), text_color=colors["text"],
        ).pack(side="left", padx=(0, 10))

        lock_type_var = ctk.StringVar(value="Pattern")
        ctk.CTkOptionMenu(
            selector_row, values=["Pattern", "PIN", "Password"],
            variable=lock_type_var, width=160, height=38,
            fg_color=colors["bg_light"], button_color=colors["accent"],
            button_hover_color=colors["accent_hover"],
            font=("Segoe UI", 13),
        ).pack(side="left")

        ctk.CTkLabel(
            frame,
            text="Attempts 3 methods: locksettings clear (Android 8+), lock file deletion (root),\n"
                 "then fastboot factory reset (WARNING: erases all data).",
            font=("Segoe UI", 12), text_color=colors["text_dim"], wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        def start_lock_removal():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            _set_progress(0)
            lock_type = lock_type_var.get().lower()
            _set_badge(f"  Removing {lock_type} lock...", colors["warning"])

            def run():
                header = [
                    "=" * 65,
                    f"  FRP / UNLOCK — SCREEN LOCK REMOVAL ({lock_type.upper()})",
                    "=" * 65,
                    f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "=" * 65,
                    "",
                ]
                _append_live_lines(header)

                def cb(pct, msg):
                    _set_progress(pct)
                    _set_msg(msg)
                    _append_live(f"  \U0001f527 {msg}")

                try:
                    result = remove_screen_lock(lock_type=lock_type, callback=cb)

                    _append_live("")
                    _append_live("=" * 65)
                    _append_live("  SCREEN LOCK REMOVAL RESULT")
                    _append_live("=" * 65)

                    result_lines = [
                        f"  Success:         {'YES' if result.success else 'NO'}",
                        f"  Lock Removed:    {result.lock_type_removed}",
                        f"  Method Used:     {result.method_used or 'none'}",
                        f"  Reboot Needed:   {'Yes' if result.reboot_required else 'No'}",
                        f"  Data Wiped:      {'YES' if result.data_wiped else 'No'}",
                    ]
                    if result.error:
                        result_lines.append(f"  Error:           {result.error}")
                    _append_live_lines(result_lines)

                    _append_live("")
                    _append_live("-" * 65)
                    _append_live("  STEPS PERFORMED")
                    _append_live("-" * 65)
                    for i, step in enumerate(result.steps_performed, 1):
                        _append_live(f"    {i:3d}. {step}")

                    if result.success:
                        extra = " (DATA WIPED)" if result.data_wiped else ""
                        _set_badge(f"  Lock removed successfully{extra} — reboot device",
                                   colors["success"])
                    else:
                        _set_badge("  Lock removal failed — see report", colors["warning"])

                except Exception as e:
                    _append_live(f"  Error: {str(e)}")
                    _set_badge(f"  Error: {str(e)}", colors["warning"])

                _append_live("")
                _append_live("=" * 65)
                _set_progress(1.0)
                _set_msg("Screen lock removal complete", colors["success"])
                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(
            frame, text="Start Lock Removal", width=240, height=44,
            fg_color="#ec4899", hover_color="#c0392b",
            font=("Segoe UI", 15, "bold"), corner_radius=10,
            command=start_lock_removal,
        ).pack(anchor="w", pady=(5, 0))

        return frame

    # ── Mi Account Tab ──────────────────────────────────────────
    def _build_mi_account_tab(parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        ctk.CTkLabel(
            frame,
            text="Check Xiaomi Mi Account binding status. A bound Mi Account can trigger\n"
                 "a device lock similar to FRP. Works on Xiaomi, Redmi, and POCO devices.",
            font=("Segoe UI", 12), text_color=colors["text_dim"], wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(5, 10))

        def start_mi_check():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            _set_progress(0)
            _set_badge("  Checking Mi Account status...", colors["info"])

            def run():
                header = [
                    "=" * 65,
                    "  FRP / UNLOCK — MI ACCOUNT STATUS CHECK",
                    "=" * 65,
                    f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "=" * 65,
                    "",
                ]
                _append_live_lines(header)

                def cb(pct, msg):
                    _set_progress(pct)
                    _set_msg(msg)
                    _append_live(f"  \U0001f50d {msg}")

                try:
                    result = check_mi_account(callback=cb)

                    _append_live("")
                    _append_live("=" * 65)
                    _append_live("  MI ACCOUNT STATUS")
                    _append_live("=" * 65)

                    if not result.connected:
                        _append_live(f"  ERROR: {result.error or 'No device connected'}")
                        _set_badge("  No device connected", colors["warning"])
                    else:
                        result_lines = [
                            f"  Device:          {result.device_model}",
                            f"  MIUI Version:    {result.miui_version or 'unknown'}",
                            "",
                            "-" * 65,
                            "  MI ACCOUNT BINDING",
                            "-" * 65,
                            f"  Mi Account:      {'BOUND' if result.mi_account_bound else 'None'}",
                        ]
                        if result.mi_user_id:
                            result_lines.append(f"  Mi User ID:      {result.mi_user_id}")
                        if result.mi_email:
                            result_lines.append(f"  Mi Email:        {result.mi_email}")
                        result_lines.extend([
                            f"  MiCloud:         {'Active' if result.micloud_enabled else 'Inactive'}",
                            f"  Find Device:     {'Active' if result.find_device_active else 'Inactive'}",
                            "",
                            "-" * 65,
                            "  MI PACKAGES",
                            "-" * 65,
                            f"  Installed:       {len(result.mi_account_packages)}",
                        ])
                        for pkg in result.mi_account_packages:
                            result_lines.append(f"    - {pkg}")
                        _append_live_lines(result_lines)

                        if result.mi_account_bound:
                            _set_badge("  Mi Account is BOUND — device may be locked",
                                       colors["warning"])
                        else:
                            _set_badge("  Mi Account is not bound — device is clean",
                                       colors["success"])

                except Exception as e:
                    _append_live(f"  Error: {str(e)}")
                    _set_badge(f"  Error: {str(e)}", colors["warning"])

                _append_live("")
                _append_live("=" * 65)
                _set_progress(1.0)
                _set_msg("Mi Account check complete", colors["success"])
                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(
            frame, text="Check Mi Account", width=220, height=44,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 15, "bold"), corner_radius=10,
            command=start_mi_check,
        ).pack(anchor="w", pady=(5, 0))

        return frame

    # ── Knox Status Tab ─────────────────────────────────────────
    def _build_knox_status_tab(parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")

        ctk.CTkLabel(
            frame,
            text="Check Samsung Knox warranty and security status. A tripped Knox warranty bit\n"
                 "(0x1) indicates the device has been tampered with and is usually irreversible.",
            font=("Segoe UI", 12), text_color=colors["text_dim"], wraplength=700,
            justify="left",
        ).pack(anchor="w", pady=(5, 10))

        def start_knox_check():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            _set_progress(0)
            _set_badge("  Checking Knox status...", colors["info"])

            def run():
                header = [
                    "=" * 65,
                    "  FRP / UNLOCK — SAMSUNG KNOX STATUS CHECK",
                    "=" * 65,
                    f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "=" * 65,
                    "",
                ]
                _append_live_lines(header)

                def cb(pct, msg):
                    _set_progress(pct)
                    _set_msg(msg)
                    _append_live(f"  \U0001f50d {msg}")

                try:
                    result = check_knox_status(callback=cb)

                    _append_live("")
                    _append_live("=" * 65)
                    _append_live("  SAMSUNG KNOX STATUS")
                    _append_live("=" * 65)

                    if not result.connected:
                        _append_live(f"  ERROR: {result.error or 'No device connected'}")
                        _set_badge("  No device connected", colors["warning"])
                    else:
                        result_lines = [
                            f"  Device:          {result.device_model}",
                            f"  Firmware:        {result.firmware_version}",
                            "",
                            "-" * 65,
                            "  KNOX WARRANTY",
                            "-" * 65,
                            f"  Knox Tripped:    {'YES' if result.knox_tripped else 'No'}",
                            f"  Warranty Bit:    {result.warranty_bit}",
                            f"  Knox Version:    {result.knox_version or 'unknown'}",
                            "",
                            "-" * 65,
                            "  KNOX SERVICES",
                            "-" * 65,
                            f"  Knox Container:  {'Active' if result.knox_container_active else 'Inactive'}",
                            f"  Secure Folder:   {'Active' if result.secure_folder_active else 'Inactive'}",
                            "",
                            "-" * 65,
                            "  BOOTLOADER & SECURITY",
                            "-" * 65,
                            f"  Bootloader:      {'Locked' if result.bootloader_locked else 'UNLOCKED'}",
                            f"  dm-verity:       {'Enabled' if result.dm_verity_enabled else 'Disabled'}",
                            f"  OEM Unlock:      {'Enabled' if result.oem_unlock_enabled else 'Disabled'}",
                        ]
                        _append_live_lines(result_lines)

                        if result.knox_tripped:
                            _set_badge("  Knox warranty bit is TRIPPED (0x1) — irreversible",
                                       colors["warning"])
                        else:
                            _set_badge("  Knox warranty bit is intact (0x0) — device is clean",
                                       colors["success"])

                except Exception as e:
                    _append_live(f"  Error: {str(e)}")
                    _set_badge(f"  Error: {str(e)}", colors["warning"])

                _append_live("")
                _append_live("=" * 65)
                _set_progress(1.0)
                _set_msg("Knox status check complete", colors["success"])
                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(
            frame, text="Check Knox Status", width=220, height=44,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 15, "bold"), corner_radius=10,
            command=start_knox_check,
        ).pack(anchor="w", pady=(5, 0))

        return frame

    # ══════════════════════════════════════════════════════════════
    # BUILD ALL TABS & SWITCHING LOGIC
    # ══════════════════════════════════════════════════════════════

    builders = {
        "Check Status": _build_check_status_tab,
        "Remove FRP":   _build_remove_frp_tab,
        "Remove Lock":  _build_remove_lock_tab,
        "Mi Account":   _build_mi_account_tab,
        "Knox Status":  _build_knox_status_tab,
    }

    for name, builder in builders.items():
        f = builder(tab_container)
        tab_frames[name] = f

    def _switch_tab(name):
        active_tab["name"] = name
        # Hide all tab frames
        for tab_name, f in tab_frames.items():
            f.pack_forget()
        # Show selected tab frame
        tab_frames[name].pack(fill="x", pady=(5, 0))
        # Update button styles
        for btn_name, btn in tab_buttons.items():
            if btn_name == name:
                btn.configure(fg_color=colors["accent"],
                              text_color="#ffffff")
            else:
                btn.configure(fg_color=colors["bg_light"],
                              text_color=colors["text"])

    # Build tab buttons
    for tab_name in tab_names:
        btn = ctk.CTkButton(
            tab_inner, text=tab_name, width=130, height=36,
            fg_color=colors["bg_light"], hover_color=colors["accent_hover"],
            text_color=colors["text"], font=("Segoe UI", 13, "bold"),
            corner_radius=8,
            command=lambda n=tab_name: _switch_tab(n),
        )
        btn.pack(side="left", padx=3)
        tab_buttons[tab_name] = btn

    # Show default tab
    _switch_tab("Check Status")

    app.update_status("FRP / Unlock Features — Ready")
