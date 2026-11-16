"""
Auto Unlock GUI Page — One-Click FRP & Lock Screen Bypass.

Features:
    - USB device auto-monitoring with live status
    - One-click auto unlock (detect mode → run bypass → done)
    - Real-time colored log output
    - Device info card with live detection
    - Progress bar with step tracking
    - Individual mode buttons (ADB / Fastboot / EDL)
"""

import customtkinter as ctk
import threading
import datetime as _dt

from app.hardware.auto_unlocker import (
    AutoUnlocker,
    DeviceMode,
    DeviceInfo,
    UnlockResult,
    detect_usb_devices,
)


def render_auto_unlock(app):
    """Render the Auto Unlock page."""
    colors = app.colors

    # State
    state = {
        "running": False,
        "monitoring": False,
        "monitor_stop": None,
        "unlocker": None,
        "device_info": None,
    }

    # ── Page Title ──────────────────────────────────────────────
    title_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    title_frame.pack(fill="x", padx=20, pady=(20, 5))

    ctk.CTkLabel(
        title_frame, text="\U0001f513 Auto Unlock Tool",
        font=("Segoe UI", 26, "bold"), text_color=colors["accent"],
    ).pack(side="left")

    # Monitor toggle button
    monitor_btn = ctk.CTkButton(
        title_frame, text="\u25cf Start USB Monitor", width=180, height=36,
        fg_color="#1e90ff", hover_color="#3742fa",
        font=("Segoe UI", 13, "bold"), corner_radius=8,
    )
    monitor_btn.pack(side="right", padx=(10, 0))

    ctk.CTkLabel(
        app.content,
        text="One-click FRP bypass & lock screen removal. Connect device via USB — tool auto-detects mode and unlocks.",
        font=("Segoe UI", 13), text_color=colors["text_dim"], wraplength=800,
    ).pack(anchor="w", padx=20, pady=(0, 10))

    # ── Device Info Card ────────────────────────────────────────
    info_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"],
                              corner_radius=12, border_width=1,
                              border_color=colors["border"])
    info_card.pack(fill="x", padx=20, pady=(0, 10))

    info_inner = ctk.CTkFrame(info_card, fg_color="transparent")
    info_inner.pack(fill="x", padx=20, pady=15)

    # Row 1: Connection status
    row1 = ctk.CTkFrame(info_inner, fg_color="transparent")
    row1.pack(fill="x", pady=(0, 8))

    conn_indicator = ctk.CTkLabel(
        row1, text="\u25cf", font=("Segoe UI", 20),
        text_color="#e94560",  # red = disconnected
    )
    conn_indicator.pack(side="left", padx=(0, 8))

    conn_label = ctk.CTkLabel(
        row1, text="No Device Connected",
        font=("Segoe UI", 16, "bold"), text_color=colors["text"],
    )
    conn_label.pack(side="left")

    mode_badge = ctk.CTkLabel(
        row1, text="",
        font=("Segoe UI", 12, "bold"), text_color="#ffffff",
        fg_color=colors["bg_light"], corner_radius=6,
    )
    mode_badge.pack(side="right")

    # Row 2: Device details
    row2 = ctk.CTkFrame(info_inner, fg_color="transparent")
    row2.pack(fill="x")

    detail_labels = {}
    details = [
        ("Brand", "—"), ("Model", "—"), ("Android", "—"),
        ("Root", "—"), ("FRP", "—"), ("Lock", "—"),
    ]
    for name, val in details:
        f = ctk.CTkFrame(row2, fg_color="transparent")
        f.pack(side="left", padx=(0, 25))
        ctk.CTkLabel(f, text=name, font=("Segoe UI", 11),
                     text_color=colors["text_dim"]).pack()
        lbl = ctk.CTkLabel(f, text=val, font=("Segoe UI", 13, "bold"),
                           text_color=colors["text"])
        lbl.pack()
        detail_labels[name] = lbl

    def _update_device_card(info: DeviceInfo):
        """Update the device info card."""
        def _do():
            try:
                if info.mode == DeviceMode.NONE:
                    conn_indicator.configure(text_color="#e94560")
                    conn_label.configure(text="No Device Connected")
                    mode_badge.configure(text="", fg_color=colors["bg_light"])
                    for key in detail_labels:
                        detail_labels[key].configure(text="—")
                    return

                conn_indicator.configure(text_color="#2ed573")
                conn_label.configure(text="Device Connected")

                mode_colors = {
                    DeviceMode.ADB_NORMAL: ("#2ed573", "ADB Normal"),
                    DeviceMode.ADB_RECOVERY: ("#ffa502", "Recovery"),
                    DeviceMode.ADB_SIDELOAD: ("#ffa502", "Sideload"),
                    DeviceMode.ADB_UNAUTHORIZED: ("#e94560", "Unauthorized"),
                    DeviceMode.FASTBOOT: ("#1e90ff", "Fastboot"),
                    DeviceMode.EDL_9008: ("#9b59b6", "EDL 9008"),
                }
                mc, mt = mode_colors.get(info.mode, ("#888", "Unknown"))
                mode_badge.configure(text=f"  {mt}  ", fg_color=mc)

                detail_labels["Brand"].configure(text=info.brand.title() or "—")
                detail_labels["Model"].configure(text=info.model or "—")
                detail_labels["Android"].configure(text=info.android_version or "—")
                detail_labels["Root"].configure(
                    text="Yes" if info.has_root else "No",
                    text_color="#2ed573" if info.has_root else colors["text"],
                )
                detail_labels["FRP"].configure(
                    text="Enabled" if info.frp_enabled else "Clean",
                    text_color="#e94560" if info.frp_enabled else "#2ed573",
                )
                detail_labels["Lock"].configure(
                    text=info.lock_type.title() if info.screen_locked else "None",
                    text_color="#e94560" if info.screen_locked else "#2ed573",
                )
            except Exception:
                pass

        app.content.after(0, _do)

    # ── Action Buttons ──────────────────────────────────────────
    action_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"],
                                 corner_radius=12)
    action_frame.pack(fill="x", padx=20, pady=(0, 10))

    action_inner = ctk.CTkFrame(action_frame, fg_color="transparent")
    action_inner.pack(fill="x", padx=15, pady=15)

    # Main one-click button
    main_btn = ctk.CTkButton(
        action_inner, text="\u26a1 ONE-CLICK AUTO UNLOCK",
        width=320, height=55,
        fg_color="#e94560", hover_color="#c0392b",
        font=("Segoe UI", 18, "bold"), corner_radius=12,
    )
    main_btn.pack(pady=(0, 12))

    # Secondary buttons row
    sec_row = ctk.CTkFrame(action_inner, fg_color="transparent")
    sec_row.pack(fill="x")

    btn_configs = [
        ("\U0001f4f1 ADB Unlock", "#2ed573", "#27ae60"),
        ("\u26a1 Fastboot Unlock", "#1e90ff", "#2980b9"),
        ("\U0001f534 EDL Flash", "#9b59b6", "#8e44ad"),
        ("\U0001f504 Detect Device", "#ffa502", "#e67e22"),
        ("\u23f9 Stop", "#666", "#555"),
    ]

    sec_buttons = {}
    for text, fg, hover in btn_configs:
        btn = ctk.CTkButton(
            sec_row, text=text, width=150, height=40,
            fg_color=fg, hover_color=hover,
            font=("Segoe UI", 12, "bold"), corner_radius=8,
        )
        btn.pack(side="left", padx=4, expand=True)
        sec_buttons[text] = btn

    # ── Progress Bar ────────────────────────────────────────────
    progress_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    progress_frame.pack(fill="x", padx=20, pady=(0, 3))

    progress_bar = ctk.CTkProgressBar(
        progress_frame, width=600, height=18,
        progress_color=colors["accent"],
        fg_color=colors["bg_light"],
    )
    progress_bar.set(0)
    progress_bar.pack(fill="x")

    status_label = ctk.CTkLabel(
        app.content, text="Ready — connect a device via USB to begin",
        font=("Segoe UI", 12), text_color=colors["text_dim"],
    )
    status_label.pack(anchor="w", padx=20, pady=(2, 5))

    # ── Log Output ──────────────────────────────────────────────
    log_box = ctk.CTkTextbox(
        app.content, fg_color=colors["bg_dark"],
        text_color="#2ed573", font=("Consolas", 11),
        border_color=colors["border"], border_width=1,
        height=350, wrap="none",
    )
    log_box.pack(fill="both", expand=True, padx=20, pady=(0, 10))

    # Color tags
    tb = log_box._textbox
    tb.tag_configure("info", foreground="#1e90ff")
    tb.tag_configure("success", foreground="#2ed573")
    tb.tag_configure("warning", foreground="#ffa502")
    tb.tag_configure("error", foreground="#e94560")
    tb.tag_configure("step", foreground="#9b59b6")
    tb.tag_configure("header", foreground="#e94560", font=("Consolas", 12, "bold"))
    tb.tag_configure("dim", foreground="#8892b0")

    def _write_initial():
        log_box.insert("1.0",
            "=" * 70 + "\n"
            "  MOOXY AI — AUTO UNLOCK ENGINE\n"
            "=" * 70 + "\n"
            f"  {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "=" * 70 + "\n\n"
            "  Connect a device via USB. The tool supports:\n"
            "    \u2022 ADB mode — FRP bypass + lock removal (non-destructive first)\n"
            "    \u2022 Fastboot — bootloader unlock + partition erase\n"
            "    \u2022 EDL 9008 — firehose-based FRP wipe (test point required)\n"
            "    \u2022 Recovery — factory reset + lock file deletion\n\n"
            "  Click 'ONE-CLICK AUTO UNLOCK' or enable USB Monitor for auto-detect.\n"
            "\n" + "=" * 70 + "\n"
        )
    _write_initial()

    # ── Log Helpers ─────────────────────────────────────────────
    def _log(text: str, level: str = "info"):
        def _do():
            try:
                log_box.configure(state="normal")
                ts = _dt.datetime.now().strftime("%H:%M:%S")
                prefix = {
                    "info": "\u2139\ufe0f ",
                    "success": "\u2705 ",
                    "warning": "\u26a0\ufe0f ",
                    "error": "\u274c ",
                    "step": "\u25b6 ",
                }.get(level, "  ")

                line = f"  [{ts}] {prefix}{text}\n"
                start = tb.index("end-1c")
                log_box.insert("end", line)
                end = tb.index("end-1c")

                tag = level if level in ("info", "success", "warning", "error", "step") else None
                if tag:
                    tb.tag_add(tag, start, end)
                log_box.see("end")
            except Exception:
                pass
        app.content.after(0, _do)

    def _clear_log():
        def _do():
            try:
                log_box.configure(state="normal")
                log_box.delete("1.0", "end")
                _write_initial()
            except Exception:
                pass
        app.content.after(0, _do)

    def _set_progress(pct: float):
        app.content.after(0, lambda: progress_bar.set(min(1.0, max(0.0, pct))))

    def _set_status(text: str, color=None):
        c = color or colors["text_dim"]
        app.content.after(0, lambda: status_label.configure(text=text, text_color=c))

    def _set_buttons_enabled(enabled: bool):
        st = "normal" if enabled else "disabled"
        def _do():
            try:
                main_btn.configure(state=st)
                for btn in sec_buttons.values():
                    if "\u23f9" not in btn.cget("text"):  # keep Stop enabled
                        btn.configure(state=st)
            except Exception:
                pass
        app.content.after(0, _do)

    # ── Callback for AutoUnlocker ───────────────────────────────
    def _unlock_callback(pct: float, msg: str, level: str):
        _set_progress(pct)
        _set_status(msg, {
            "success": colors["success"],
            "error": colors["accent"],
            "warning": colors["warning"],
        }.get(level, colors["text_dim"]))
        _log(msg, level)

    # ── Show Result ─────────────────────────────────────────────
    def _show_result(result: UnlockResult):
        _log("", "info")
        _log("=" * 60, "info")
        _log("  AUTO UNLOCK RESULT", "info")
        _log("=" * 60, "info")
        _log(f"  Success:           {'YES' if result.success else 'NO'}",
             "success" if result.success else "error")
        _log(f"  FRP Removed:       {'Yes' if result.frp_removed else 'No'}",
             "success" if result.frp_removed else "warning")
        _log(f"  Lock Removed:      {'Yes' if result.lock_removed else 'No'}",
             "success" if result.lock_removed else "warning")
        _log(f"  Data Wiped:        {'Yes' if result.data_wiped else 'No'}",
             "warning" if result.data_wiped else "info")
        _log(f"  Reboot Required:   {'Yes' if result.reboot_required else 'No'}", "info")
        _log(f"  Duration:          {result.duration_seconds:.1f}s", "info")
        _log(f"  Methods Tried:     {len(result.methods_tried)}", "info")
        _log(f"  Methods Succeeded: {len(result.methods_succeeded)}", "info")

        if result.methods_succeeded:
            _log("", "info")
            _log("  Successful Methods:", "success")
            for m in result.methods_succeeded:
                _log(f"    \u2713 {m}", "success")

        if result.error:
            _log("", "error")
            _log(f"  Error: {result.error}", "error")

        _log("", "info")
        _log("  Detailed Steps:", "info")
        for i, step in enumerate(result.steps, 1):
            _log(f"    {i:3d}. {step}", "dim" if step.startswith("  ") else "step")

        _log("", "info")
        _log("=" * 60, "info")

    # ── Button Actions ──────────────────────────────────────────

    def _do_auto_unlock():
        """One-click auto unlock."""
        if state["running"]:
            return
        state["running"] = True
        _set_buttons_enabled(False)
        _clear_log()
        _set_progress(0)
        _set_status("Auto unlock starting...", colors["warning"])
        _log("ONE-CLICK AUTO UNLOCK STARTED", "step")

        def run():
            unlocker = AutoUnlocker(callback=_unlock_callback, auto_reboot=True)
            state["unlocker"] = unlocker

            result = unlocker.detect_and_unlock()
            _show_result(result)

            if result.device_info:
                _update_device_card(result.device_info)

            state["running"] = False
            state["unlocker"] = None
            _set_buttons_enabled(True)

            if result.success:
                _set_status("UNLOCK SUCCESSFUL! Device should reboot clean.", colors["success"])
            else:
                _set_status(f"Unlock failed: {result.error or 'see log'}", colors["accent"])

        threading.Thread(target=run, daemon=True).start()

    def _do_detect():
        """Just detect device, don't unlock."""
        if state["running"]:
            return
        state["running"] = True
        _set_buttons_enabled(False)
        _set_progress(0)
        _set_status("Detecting device...", colors["info"])
        _log("Device detection started...", "info")

        def run():
            unlocker = AutoUnlocker(callback=_unlock_callback)
            info = unlocker.detect_device()
            _update_device_card(info)
            state["device_info"] = info

            if info.mode != DeviceMode.NONE:
                _log(f"Device found: {info.brand} {info.model} in {info.mode.value} mode", "success")
                _set_status(f"Device: {info.brand} {info.model} ({info.mode.value})", colors["success"])
            else:
                _log("No device detected", "warning")
                _set_status("No device detected — check USB connection", colors["warning"])

            _set_progress(1.0)
            state["running"] = False
            _set_buttons_enabled(True)

        threading.Thread(target=run, daemon=True).start()

    def _do_adb_unlock():
        """ADB-specific unlock."""
        if state["running"]:
            return
        state["running"] = True
        _set_buttons_enabled(False)
        _clear_log()
        _set_progress(0)
        _log("ADB UNLOCK MODE STARTED", "step")

        def run():
            unlocker = AutoUnlocker(callback=_unlock_callback)
            info = unlocker.detect_device()
            _update_device_card(info)

            if info.mode not in (DeviceMode.ADB_NORMAL, DeviceMode.ADB_RECOVERY):
                _log("Device not in ADB mode — cannot proceed", "error")
                _set_status("Device not in ADB mode", colors["accent"])
                state["running"] = False
                _set_buttons_enabled(True)
                return

            result = UnlockResult()
            result.device_info = info

            if info.mode == DeviceMode.ADB_NORMAL:
                unlocker._unlock_via_adb(result)
            else:
                unlocker._unlock_via_recovery(result)

            result.success = result.frp_removed or result.lock_removed
            _show_result(result)

            state["running"] = False
            _set_buttons_enabled(True)

        threading.Thread(target=run, daemon=True).start()

    def _do_fastboot_unlock():
        """Fastboot-specific unlock."""
        if state["running"]:
            return
        state["running"] = True
        _set_buttons_enabled(False)
        _clear_log()
        _set_progress(0)
        _log("FASTBOOT UNLOCK MODE STARTED", "step")

        def run():
            unlocker = AutoUnlocker(callback=_unlock_callback)
            info = unlocker.detect_device()
            _update_device_card(info)

            if info.mode != DeviceMode.FASTBOOT:
                _log("Device not in Fastboot mode — cannot proceed", "error")
                _set_status("Device not in Fastboot mode", colors["accent"])
                state["running"] = False
                _set_buttons_enabled(True)
                return

            result = UnlockResult()
            result.device_info = info
            unlocker._unlock_via_fastboot(result)
            result.success = result.frp_removed or result.lock_removed
            _show_result(result)

            state["running"] = False
            _set_buttons_enabled(True)

        threading.Thread(target=run, daemon=True).start()

    def _do_edl_unlock():
        """EDL-specific unlock."""
        if state["running"]:
            return
        state["running"] = True
        _set_buttons_enabled(False)
        _clear_log()
        _set_progress(0)
        _log("EDL 9008 UNLOCK MODE STARTED", "step")

        def run():
            unlocker = AutoUnlocker(callback=_unlock_callback)
            info = unlocker.detect_device()
            _update_device_card(info)

            if info.mode != DeviceMode.EDL_9008:
                _log("Device not in EDL 9008 mode — cannot proceed", "error")
                _log("EDL mode requires test point short on motherboard + USB", "warning")
                _set_status("Device not in EDL mode", colors["accent"])
                state["running"] = False
                _set_buttons_enabled(True)
                return

            result = UnlockResult()
            result.device_info = info
            unlocker._unlock_via_edl(result)
            result.success = result.frp_removed or result.lock_removed
            _show_result(result)

            state["running"] = False
            _set_buttons_enabled(True)

        threading.Thread(target=run, daemon=True).start()

    def _do_stop():
        """Stop running operation."""
        if state["unlocker"]:
            state["unlocker"].stop()
            _log("Stop signal sent — operation will halt at next checkpoint", "warning")
            _set_status("Stopping...", colors["warning"])

    # ── USB Monitor ─────────────────────────────────────────────
    def _toggle_monitor():
        if state["monitoring"]:
            # Stop monitoring
            if state["monitor_stop"]:
                state["monitor_stop"].set()
            state["monitoring"] = False
            monitor_btn.configure(text="\u25cf Start USB Monitor", fg_color="#1e90ff")
            _log("USB Monitor stopped", "info")
            _set_status("USB Monitor stopped", colors["text_dim"])
        else:
            # Start monitoring
            state["monitoring"] = True
            monitor_btn.configure(text="\u25a0 Stop USB Monitor", fg_color="#e94560")
            _log("USB Monitor started — waiting for device...", "info")
            _set_status("USB Monitor active — connect a device", colors["info"])

            unlocker = AutoUnlocker(callback=_unlock_callback)

            def on_found(info: DeviceInfo):
                _update_device_card(info)
                _log(f"Device detected: {info.brand} {info.model} ({info.mode.value})", "success")
                _set_status(f"Device found: {info.mode.value} — click Auto Unlock to proceed",
                           colors["success"])

            def on_lost():
                _update_device_card(DeviceInfo())
                _log("Device disconnected", "warning")
                _set_status("Device disconnected — waiting...", colors["warning"])

            stop_event = unlocker.start_monitoring(
                on_device_found=on_found,
                on_device_lost=on_lost,
            )
            state["monitor_stop"] = stop_event

    # ── Wire up buttons ────────────────────────────────────────
    main_btn.configure(command=_do_auto_unlock)
    monitor_btn.configure(command=_toggle_monitor)
    sec_buttons["\U0001f4f1 ADB Unlock"].configure(command=_do_adb_unlock)
    sec_buttons["\u26a1 Fastboot Unlock"].configure(command=_do_fastboot_unlock)
    sec_buttons["\U0001f534 EDL Flash"].configure(command=_do_edl_unlock)
    sec_buttons["\U0001f504 Detect Device"].configure(command=_do_detect)
    sec_buttons["\u23f9 Stop"].configure(command=_do_stop)

    # ── Bottom buttons (Copy/Save) ──────────────────────────────
    bottom_row = ctk.CTkFrame(app.content, fg_color="transparent")
    bottom_row.pack(fill="x", padx=20, pady=(0, 10))

    def _copy_log():
        try:
            text = log_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            _set_status("Log copied to clipboard!", colors["success"])
        except Exception:
            pass

    def _save_log():
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("All", "*.*")],
                initialfile=f"auto_unlock_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(log_box.get("1.0", "end"))
                _set_status(f"Log saved to: {path}", colors["success"])
        except Exception:
            pass

    ctk.CTkButton(bottom_row, text="Copy Log", width=120, height=36,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=_copy_log).pack(side="left", padx=(0, 10))

    ctk.CTkButton(bottom_row, text="Save Log", width=120, height=36,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=_save_log).pack(side="left")

    # ── Cleanup on page change ──────────────────────────────────
    def _on_destroy(event):
        if state["monitor_stop"]:
            state["monitor_stop"].set()
        if state["unlocker"]:
            state["unlocker"].stop()

    app.content.bind("<Destroy>", _on_destroy, add="+")

    app.update_status("Auto Unlock Tool — Ready")
