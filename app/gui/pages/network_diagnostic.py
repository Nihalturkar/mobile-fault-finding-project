import customtkinter as ctk
import threading


def render_network_diagnostic(app):
    """Network Diagnostic page — Deep cellular/network fault analysis.
    Shows SIM status, signal, registration, IMEI, baseband, diagnosis & repair steps."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="📡 Network Diagnostic",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Deep cellular/network fault analysis — SIM, Signal, Registration, Modem, Diagnosis & Repair",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="🔍 Network Diagnostic Checks:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ SIM State — Detection per slot, ABSENT/LOADED/READY status",
        "✅ Signal Strength — GSM/WCDMA/LTE/NR signal, RSRP/RSRQ/SINR",
        "✅ Registration — Voice/Data state, searching/denied/registered",
        "✅ IMEI & Baseband — Modem health, IMEI presence, firmware version",
        "✅ Radio Power — Modem ON/OFF, airplane mode detection",
        "✅ Root Cause Analysis — Auto-diagnose NO SERVICE problems",
        "✅ Repair Steps — Software fixes first, then hardware if needed",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Overall Status Badge ──
    badge_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=55)
    badge_frame.pack(fill="x", padx=20, pady=(0, 10))
    badge_frame.pack_propagate(False)
    badge_inner = ctk.CTkFrame(badge_frame, fg_color="transparent")
    badge_inner.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(badge_inner, text="Network Status:",
                 font=("Segoe UI", 14, "bold"), text_color=colors["text"]).pack(side="left")
    status_badge = ctk.CTkLabel(badge_inner, text="  ⏸ Not Tested",
                                 font=("Segoe UI", 14, "bold"), text_color=colors["text_dim"])
    status_badge.pack(side="left", padx=(10, 0))

    # ── Progress bar ──
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 10))

    # ── Buttons ──
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    # ── Result cards — two columns ──
    cards_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    cards_frame.pack(fill="x", padx=20, pady=(0, 10))
    cards_left = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_left.pack(side="left", fill="both", expand=True, padx=(0, 5))
    cards_right = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_right.pack(side="left", fill="both", expand=True, padx=(5, 0))

    # ── Helper to create a result card ──
    def _make_card(parent, title, fields):
        card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card, text=title,
                     font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))
        labels = {}
        for key, name in fields:
            row = ctk.CTkFrame(card, fg_color=colors["bg_light"], corner_radius=4, height=30)
            row.pack(fill="x", padx=12, pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                         text_color=colors["text"], width=140, anchor="w").pack(side="left", padx=8)
            val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                                text_color=colors["text_dim"], anchor="w")
            val.pack(side="left", fill="x", expand=True, padx=8)
            dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                                text_color=colors["text_dim"], width=20)
            dot.pack(side="right", padx=8)
            labels[key] = (val, dot)
        ctk.CTkFrame(card, fg_color="transparent", height=8).pack()
        return labels

    # ── SIM Status Card ──
    sim_labels = _make_card(cards_left, "📱 SIM Status", [
        ("sim1_state", "SIM 1 State"),
        ("sim1_operator", "SIM 1 Operator"),
        ("sim2_state", "SIM 2 State"),
        ("sim2_operator", "SIM 2 Operator"),
    ])

    # ── Modem / IMEI Card ──
    modem_labels = _make_card(cards_left, "🔧 Modem / IMEI", [
        ("imei", "IMEI"),
        ("imei2", "IMEI 2"),
        ("baseband", "Baseband"),
        ("radio_power", "Radio Power"),
        ("modem_status", "Modem Status"),
    ])

    # ── Signal Strength Card ──
    signal_labels = _make_card(cards_right, "📶 Signal Strength", [
        ("gsm_signal", "GSM Signal"),
        ("wcdma_signal", "WCDMA Signal"),
        ("lte_signal", "LTE Signal"),
        ("nr_signal", "5G NR Signal"),
        ("rsrp", "RSRP"),
        ("rsrq", "RSRQ"),
        ("sinr", "SINR"),
        ("signal_status", "Signal Status"),
    ])

    # ── Registration Card ──
    reg_labels = _make_card(cards_right, "🌐 Registration", [
        ("voice_state", "Voice State"),
        ("data_state", "Data State"),
        ("searching", "Searching"),
        ("reject_cause", "Reject Cause"),
        ("registered_net", "Network Tech"),
    ])

    # ── Color tags for report box ──
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#34d399")
        tb.tag_configure("warning", foreground="#fbbf24")
        tb.tag_configure("fault", foreground="#ec4899")
        tb.tag_configure("info", foreground="#a855f7")
        tb.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#9a93b5")
        tb.tag_configure("step_sw", foreground="#34d399")
        tb.tag_configure("step_hw", foreground="#fbbf24")
        tb.tag_configure("step_check", foreground="#a855f7")

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "critical", "❌", "fail", "not working", "absent", "dead", "off", "no signal", "out_of_service"]):
            return "fault"
        if any(k in t for k in ["warning", "⚠️", "degraded", "weak", "poor", "searching"]):
            return "warning"
        if any(k in t for k in ["✅", "ok", "pass", "working", "detected", "active", "in_service", "present", "loaded", "ready"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "========", "DIAGNOSIS", "REPORT", "PHASE", "REPAIR", "SOFTWARE", "HARDWARE"]):
            return "header"
        if any(k in t for k in ["🔍", "scanning", "detecting", "checking", "probing", "step"]):
            return "info"
        if "🔧 sw" in t.lower() or "software" in t.lower():
            return "step_sw"
        if "🔩 hw" in t.lower() or "hardware" in t.lower():
            return "step_hw"
        return None

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

    def _append_lines(lines):
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

    def _set_field(labels_dict, key, value, ok=True):
        if key in labels_dict:
            v, d = labels_dict[key]
            app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
            color = colors["success"] if ok else colors["accent"]
            app.content.after(0, lambda: d.configure(text_color=color))

    # ── Start Diagnostic ──
    def start_diagnostic():
        if running["value"]:
            return
        running["value"] = True

        # Reset UI
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        progress.set(0)
        status_badge.configure(text="  🔄 Diagnosing...", text_color=colors["info"])
        msg_label.configure(text="Starting network diagnostic...", text_color=colors["text_dim"])

        for labels_dict in [sim_labels, modem_labels, signal_labels, reg_labels]:
            for key, (v, d) in labels_dict.items():
                v.configure(text="—", text_color=colors["text_dim"])
                d.configure(text_color=colors["text_dim"])

        full_report = {"lines": []}

        def _track(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_lines(lines):
            full_report["lines"].extend(lines)
            _append_lines(lines)

        def run():
            import datetime as _dt

            header = [
                "=" * 70,
                "  MOOXY AI — NETWORK DIAGNOSTIC REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70,
                "",
            ]
            _track_lines(header)

            try:
                from app.hardware.network_diagnostics import run_network_diagnostic

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct / 100.0 if pct > 1 else pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                _track("🔍 Starting deep network diagnostic...")
                _track("")

                result = run_network_diagnostic(callback=cb)

                if result.error and not result.connected:
                    _track(f"  ❌ {result.error}")
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  ❌ {result.error}", text_color=colors["accent"]))
                    running["value"] = False
                    return

                # ═══ Device Info ═══
                _track(f"  Device: {result.device_model} ({result.device_serial})")
                _track("")

                # ═══ PHASE 1: SIM STATUS ═══
                _track("═══ PHASE 1: SIM STATUS ═══")
                _track("")

                for slot in result.sim_slots:
                    icon = "✅" if slot.is_detected else "❌"
                    _track(f"  {icon} SIM {slot.slot}: {slot.state}")
                    if slot.operator:
                        _track(f"     Operator: {slot.operator}")
                    if slot.network_type and slot.network_type != "Unknown":
                        _track(f"     Network:  {slot.network_type}")

                    if slot.slot == 1:
                        _set_field(sim_labels, "sim1_state", slot.state, ok=slot.is_detected)
                        _set_field(sim_labels, "sim1_operator", slot.operator or "N/A", ok=bool(slot.operator))
                    elif slot.slot == 2:
                        _set_field(sim_labels, "sim2_state", slot.state, ok=slot.is_detected)
                        _set_field(sim_labels, "sim2_operator", slot.operator or "N/A", ok=bool(slot.operator))

                _track("")
                app.content.after(0, lambda: progress.set(0.25))

                # ═══ PHASE 2: MODEM / IMEI ═══
                _track("═══ PHASE 2: MODEM / IMEI ═══")
                _track("")

                modem = result.modem
                imei_ok = bool(modem.imei and len(modem.imei) >= 14)
                _track(f"  {'✅' if imei_ok else '⚠️'} IMEI:     {modem.imei or 'Not readable'}")
                if modem.imei2:
                    _track(f"  {'✅' if len(modem.imei2) >= 14 else '⚠️'} IMEI 2:   {modem.imei2}")
                _track(f"  {'✅' if modem.modem_active else '❌'} Baseband: {modem.baseband_version or 'EMPTY'}")
                _track(f"  {'✅' if modem.radio_power == 'ON' else '❌'} Radio:    {modem.radio_power or 'Unknown'}")

                _set_field(modem_labels, "imei", modem.imei or "Not readable", ok=imei_ok)
                _set_field(modem_labels, "imei2", modem.imei2 or "N/A", ok=bool(modem.imei2))
                _set_field(modem_labels, "baseband", modem.baseband_version or "EMPTY", ok=modem.modem_active)
                _set_field(modem_labels, "radio_power", modem.radio_power or "Unknown", ok=modem.radio_power == "ON")
                _set_field(modem_labels, "modem_status", "Active" if modem.modem_active else "NOT ACTIVE", ok=modem.modem_active)

                _track("")
                app.content.after(0, lambda: progress.set(0.45))

                # ═══ PHASE 3: SIGNAL STRENGTH ═══
                _track("═══ PHASE 3: SIGNAL STRENGTH ═══")
                _track("")

                sig = result.signal
                if sig.all_invalid:
                    _track("  ❌ ALL SIGNALS INVALID — No cellular signal on any band")
                    _set_field(signal_labels, "signal_status", "ALL INVALID", ok=False)
                else:
                    _track("  Signal levels detected:")

                _track(f"     GSM:   {sig.gsm_signal or 'Invalid'}")
                _track(f"     WCDMA: {sig.wcdma_signal or 'Invalid'}")
                _track(f"     LTE:   {sig.lte_signal or 'Invalid'}")
                _track(f"     5G NR: {sig.nr_signal or 'Invalid'}")
                if sig.rsrp:
                    _track(f"     RSRP:  {sig.rsrp}")
                if sig.rsrq:
                    _track(f"     RSRQ:  {sig.rsrq}")
                if sig.sinr:
                    _track(f"     SINR:  {sig.sinr}")

                _set_field(signal_labels, "gsm_signal", sig.gsm_signal or "Invalid", ok=bool(sig.gsm_signal))
                _set_field(signal_labels, "wcdma_signal", sig.wcdma_signal or "Invalid", ok=bool(sig.wcdma_signal))
                _set_field(signal_labels, "lte_signal", sig.lte_signal or "Invalid", ok=bool(sig.lte_signal))
                _set_field(signal_labels, "nr_signal", sig.nr_signal or "Invalid", ok=bool(sig.nr_signal))
                _set_field(signal_labels, "rsrp", sig.rsrp or "N/A", ok=bool(sig.rsrp))
                _set_field(signal_labels, "rsrq", sig.rsrq or "N/A", ok=bool(sig.rsrq))
                _set_field(signal_labels, "sinr", sig.sinr or "N/A", ok=bool(sig.sinr))
                if not sig.all_invalid:
                    _set_field(signal_labels, "signal_status", "Signal Found", ok=True)

                _track("")
                app.content.after(0, lambda: progress.set(0.60))

                # ═══ PHASE 4: REGISTRATION ═══
                _track("═══ PHASE 4: REGISTRATION STATE ═══")
                _track("")

                reg = result.registration
                voice_ok = reg.voice_state == "IN_SERVICE"
                data_ok = reg.data_state == "IN_SERVICE"

                _track(f"  {'✅' if voice_ok else '❌'} Voice: {reg.voice_state or 'Unknown'}")
                _track(f"  {'✅' if data_ok else '❌'} Data:  {reg.data_state or 'Unknown'}")
                if reg.voice_searching:
                    _track(f"  ⚠️ Phone is SEARCHING for network...")
                if reg.reject_cause > 0:
                    _track(f"  ❌ Network Reject Cause: #{reg.reject_cause}")
                if reg.registered_network:
                    _track(f"  Network Tech: {reg.registered_network}")

                _set_field(reg_labels, "voice_state", reg.voice_state or "Unknown", ok=voice_ok)
                _set_field(reg_labels, "data_state", reg.data_state or "Unknown", ok=data_ok)
                _set_field(reg_labels, "searching", "Yes (searching...)" if reg.voice_searching else "No", ok=not reg.voice_searching)
                _set_field(reg_labels, "reject_cause", f"#{reg.reject_cause}" if reg.reject_cause > 0 else "None", ok=reg.reject_cause == 0)
                _set_field(reg_labels, "registered_net", reg.registered_network or "None", ok=bool(reg.registered_network))

                _track("")
                app.content.after(0, lambda: progress.set(0.75))

                # ═══ PHASE 5: WHAT'S WORKING / NOT WORKING ═══
                _track("═══ PHASE 5: STATUS SUMMARY ═══")
                _track("")

                if result.working:
                    _track("  ✅ WORKING:")
                    for w in result.working:
                        _track(f"     ✅ {w}")
                _track("")

                if result.not_working:
                    _track("  ❌ NOT WORKING:")
                    for nw in result.not_working:
                        _track(f"     ❌ {nw}")
                _track("")

                app.content.after(0, lambda: progress.set(0.82))

                # ═══ PHASE 6: DIAGNOSIS ═══
                if result.diagnoses:
                    _track("═══ PHASE 6: DIAGNOSIS (Root Cause Analysis) ═══")
                    _track("")
                    for i, diag in enumerate(result.diagnoses, 1):
                        sev_icon = "🔴" if diag.severity == "critical" else "🟡"
                        _track(f"  {sev_icon} Diagnosis #{i}: {diag.problem}")
                        _track(f"     Root Cause:  {diag.root_cause}")
                        _track(f"     Confidence:  {diag.confidence}%")
                        if diag.evidence:
                            _track(f"     Evidence:")
                            for ev in diag.evidence:
                                _track(f"       • {ev}")
                        _track("")

                app.content.after(0, lambda: progress.set(0.88))

                # ═══ PHASE 7: REPAIR STEPS ═══
                _track("═══ PHASE 7: REPAIR STEPS ═══")
                _track("")

                if result.check_steps:
                    _track("  🔍 CHECKS (Do These First):")
                    for step in sorted(result.check_steps, key=lambda s: s.priority):
                        _track(f"     {step.priority}. {step.title}")
                        _track(f"        {step.description}")
                    _track("")

                if result.software_steps:
                    _track("  🔧 SOFTWARE FIXES (Try These):")
                    for step in sorted(result.software_steps, key=lambda s: s.priority):
                        _track(f"     {step.priority}. {step.title}")
                        _track(f"        {step.description}")
                        if step.command:
                            _track(f"        Command: {step.command}")
                    _track("")

                if result.hardware_steps:
                    _track("  🔩 HARDWARE FIXES (If Software Fails):")
                    for step in sorted(result.hardware_steps, key=lambda s: s.priority):
                        _track(f"     {step.priority}. {step.title}")
                        _track(f"        {step.description}")
                    _track("")

                if not result.check_steps and not result.software_steps and not result.hardware_steps:
                    _track("  ✅ No repair needed — network is working normally!")
                    _track("")

                app.content.after(0, lambda: progress.set(0.95))

                # ═══ OVERALL STATUS ═══
                _track("═══ OVERALL STATUS ═══")
                _track("")
                _track(f"  Health Score: {result.health_score}/100")
                _track(f"  Status:       {result.overall_status}")
                _track("")

                # Update badge
                score = result.health_score
                overall = result.overall_status
                if score >= 80:
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  ✅ {overall} ({score}/100)", text_color=colors["success"]))
                elif score >= 40:
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  🟡 {overall} ({score}/100)", text_color=colors["warning"]))
                else:
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  🔴 {overall} ({score}/100)", text_color=colors["accent"]))

            except ImportError:
                _track("  ❌ Network diagnostics module not found")
                app.content.after(0, lambda: status_badge.configure(
                    text="  ❌ Module Error", text_color=colors["accent"]))
            except Exception as e:
                _track(f"  ❌ Error: {str(e)}")
                app.content.after(0, lambda: status_badge.configure(
                    text="  ❌ Error", text_color=colors["accent"]))

            # Footer
            _track("=" * 70)
            _track("  Report generated by Mooxy AI Fault Detector v1.0")
            _track("=" * 70)

            report_text = "\n".join(full_report["lines"])

            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Network diagnostic complete — full report above", text_color=colors["success"]))

            # Auto-save
            try:
                from app.gui.history_manager import get_unique_log_path
                log_path = get_unique_log_path("network_diagnostic_report")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
            except Exception:
                log_path = None

            # Save to history
            try:
                from app.gui.history_manager import add_detection
                add_detection(
                    detection_type="NETWORK_DIAGNOSTIC",
                    device_name=f"{result.device_model}" if result else "Unknown",
                    summary=result.overall_status if result else "Error",
                    faults_count=len(result.not_working) if result else 0,
                    faults_summary="; ".join(result.not_working[:3]) if result else "",
                    report_file=str(log_path) if log_path else "",
                    extra={
                        "health_score": result.health_score,
                        "overall_status": result.overall_status,
                    } if result else {},
                )
            except Exception:
                pass

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    # ── Copy / Save ──
    def copy_report():
        try:
            text = report_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            msg_label.configure(text="📋 Report copied to clipboard!", text_color=colors["success"])
        except Exception:
            pass

    def save_report():
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                 filetypes=[("Text", "*.txt")],
                                                 initialfile="network_diagnostic_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="📡 Start Network Diagnostic", width=300, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_diagnostic).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="📋 Copy", width=100, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="💾 Save", width=100, height=46,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # ── Report Textbox ──
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=500, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0",
                      "Press 'Start Network Diagnostic' to begin.\n\n"
                      "Requirements:\n"
                      "• Device connected via USB/WiFi with ADB enabled\n\n"
                      "This tool diagnoses:\n"
                      "  1. SIM card detection per slot\n"
                      "  2. Signal strength on all bands (GSM/WCDMA/LTE/5G)\n"
                      "  3. Network registration state (voice + data)\n"
                      "  4. IMEI & baseband modem health\n"
                      "  5. Radio power state\n"
                      "  6. Root cause analysis for 'No Service' problems\n"
                      "  7. Software fix steps (ADB commands)\n"
                      "  8. Hardware fix steps (if software fails)\n")
    _setup_tags()

    app.update_status("Network Diagnostic — Connect device and press Start")
