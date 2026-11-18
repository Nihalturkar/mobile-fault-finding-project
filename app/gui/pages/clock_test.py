import customtkinter as ctk
import threading
import datetime as _dt


def render_clock_test(app):
    """Oscillator / Clock Testing page — XTAL, DCXO/TCXO, RTC, PLL analysis."""
    colors = app.colors

    ctk.CTkLabel(app.content, text="🕐 Oscillator / Clock Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Analyze crystal oscillators, RTC, PLLs, and clock calibration status",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 20))

    # ── Info card: what clock testing detects ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="🔍 Clock Testing Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ XTAL — Main crystal oscillator frequency, stability, drift",
        "✅ DCXO/TCXO — Digitally/Temperature compensated oscillator status",
        "✅ RTC — Real-time clock accuracy, alarm registers, backup battery",
        "✅ PLLs — Phase-locked loop lock status, frequency synthesis",
        "✅ Clock Tree — Distribution network, dividers, mux selection",
        "✅ Calibration — Trim values, temperature compensation curves",
        "✅ Sleep Clocks — 32.768 kHz accuracy, power-down retention",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Progress bar + message ──
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 5))

    # ── Buttons ──
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    # ── Clock Sources card ──
    clk_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    clk_card.pack(fill="x", padx=20, pady=(0, 10))
    ctk.CTkLabel(clk_card, text="📡 Clock Sources",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    clock_fields = [
        ("clk_xtal", "🔷 Main XTAL"),
        ("clk_dcxo", "🔶 DCXO/TCXO"),
        ("clk_sleep", "🌙 Sleep Clock (32.768 kHz)"),
        ("clk_rf", "📶 RF Reference Clock"),
        ("clk_audio", "🔊 Audio Clock"),
        ("clk_usb", "🔌 USB Clock"),
    ]
    clk_labels = {}
    for key, name in clock_fields:
        row = ctk.CTkFrame(clk_card, fg_color=colors["bg_light"], corner_radius=4, height=35)
        row.pack(fill="x", padx=15, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=200, anchor="w").pack(side="left", padx=10)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=10)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 12),
                            text_color=colors["text_dim"], width=25)
        dot.pack(side="right", padx=10)
        clk_labels[key] = (val, dot)
    ctk.CTkFrame(clk_card, fg_color="transparent", height=10).pack()

    # ── RTC Info card ──
    rtc_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    rtc_card.pack(fill="x", padx=20, pady=(0, 10))
    ctk.CTkLabel(rtc_card, text="⏰ RTC Information",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    rtc_fields = [
        ("rtc_time", "🕐 Current RTC Time"),
        ("rtc_alarm", "⏰ Alarm Register"),
        ("rtc_drift", "📉 Drift (sec/day)"),
        ("rtc_accuracy", "🎯 Accuracy (PPM)"),
        ("rtc_battery", "🔋 Backup Battery"),
        ("rtc_status", "📋 RTC Status"),
    ]
    rtc_labels = {}
    for key, name in rtc_fields:
        row = ctk.CTkFrame(rtc_card, fg_color=colors["bg_light"], corner_radius=4, height=35)
        row.pack(fill="x", padx=15, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=200, anchor="w").pack(side="left", padx=10)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=10)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 12),
                            text_color=colors["text_dim"], width=25)
        dot.pack(side="right", padx=10)
        rtc_labels[key] = (val, dot)
    ctk.CTkFrame(rtc_card, fg_color="transparent", height=10).pack()

    # ── PLL Status card ──
    pll_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    pll_card.pack(fill="x", padx=20, pady=(0, 10))
    ctk.CTkLabel(pll_card, text="🔄 PLL Status",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    pll_fields = [
        ("pll_cpu", "⚙️ CPU PLL"),
        ("pll_gpu", "🎮 GPU PLL"),
        ("pll_ddr", "💾 DDR PLL"),
        ("pll_disp", "🖥️ Display PLL"),
        ("pll_cam", "📷 Camera PLL"),
        ("pll_npu", "🧠 NPU PLL"),
    ]
    pll_labels = {}
    for key, name in pll_fields:
        row = ctk.CTkFrame(pll_card, fg_color=colors["bg_light"], corner_radius=4, height=35)
        row.pack(fill="x", padx=15, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=200, anchor="w").pack(side="left", padx=10)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=10)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 12),
                            text_color=colors["text_dim"], width=25)
        dot.pack(side="right", padx=10)
        pll_labels[key] = (val, dot)
    ctk.CTkFrame(pll_card, fg_color="transparent", height=10).pack()

    # ── XO Calibration card ──
    xo_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    xo_card.pack(fill="x", padx=20, pady=(0, 10))
    ctk.CTkLabel(xo_card, text="🔧 XO Calibration",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    xo_fields = [
        ("xo_type", "📋 Oscillator Type"),
        ("xo_freq", "📡 Nominal Frequency"),
        ("xo_trim", "🎛️ Trim Value"),
        ("xo_temp_comp", "🌡️ Temperature Compensation"),
        ("xo_aging", "📉 Aging Offset"),
        ("xo_status", "📋 Calibration Status"),
    ]
    xo_labels = {}
    for key, name in xo_fields:
        row = ctk.CTkFrame(xo_card, fg_color=colors["bg_light"], corner_radius=4, height=35)
        row.pack(fill="x", padx=15, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=200, anchor="w").pack(side="left", padx=10)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=10)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 12),
                            text_color=colors["text_dim"], width=25)
        dot.pack(side="right", padx=10)
        xo_labels[key] = (val, dot)
    ctk.CTkFrame(xo_card, fg_color="transparent", height=10).pack()

    # ── Overall Health Badge ──
    health_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=55)
    health_frame.pack(fill="x", padx=20, pady=(0, 10))
    health_frame.pack_propagate(False)
    health_label = ctk.CTkLabel(health_frame, text="⏳ Clock Health: Waiting for detection...",
                                 font=("Segoe UI", 15, "bold"), text_color=colors["text_dim"])
    health_label.pack(side="left", padx=20, pady=12)

    # ── Report textbox ──
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=350, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0", "Press 'Start Detection' to analyze oscillator and clock subsystems.\n\n"
                      "This test checks:\n"
                      "  - Crystal oscillator (XTAL) frequency and stability\n"
                      "  - DCXO/TCXO compensation status\n"
                      "  - RTC accuracy, drift, and backup battery\n"
                      "  - PLL lock status for all clock domains\n"
                      "  - XO calibration trim and temperature compensation\n")

    # ── Color tags setup ──
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#34d399")
        tb.tag_configure("warning", foreground="#fbbf24")
        tb.tag_configure("fault", foreground="#ec4899")
        tb.tag_configure("info", foreground="#a855f7")
        tb.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))

    _setup_tags()

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "critical", "danger", "fail", "error", "unlocked", "[xx]"]):
            return "fault"
        if any(k in t for k in ["warning", "degraded", "drift", "marginal", "[!!]"]):
            return "warning"
        if any(k in t for k in ["ok", "pass", "locked", "healthy", "stable", "good", "[ok]"]):
            return "ok"
        if any(k in t for k in ["===", "───", "═══", "REPORT", "PHASE"]):
            return "header"
        if any(k in t for k in ["detecting", "scanning", "analyzing"]):
            return "info"
        return None

    def _append_line(text):
        """Append a single line with color tagging."""
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
        """Append multiple lines at once with color tagging."""
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
        """Update a field row value and status dot."""
        if key in labels_dict:
            v, d = labels_dict[key]
            app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
            color = colors["success"] if ok else colors["warning"]
            app.content.after(0, lambda: d.configure(text_color=color))

    def start_detection():
        if running["value"]:
            return
        running["value"] = True

        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        progress.set(0)
        msg_label.configure(text="Initializing clock detection...", text_color=colors["text_dim"])
        health_label.configure(text="⏳ Clock Health: Detecting...", text_color=colors["info"])

        def run():
            header = [
                "=" * 70,
                "  MOOXY AI FAULT DETECTOR — OSCILLATOR / CLOCK TEST REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70,
                "",
            ]
            _append_lines(header)

            try:
                from app.hardware.clock_tester import detect_clock_status

                def cb(pct, message):
                    app.content.after(0, lambda: progress.set(pct))
                    app.content.after(0, lambda: msg_label.configure(text=message))

                result = detect_clock_status(callback=cb)

                # ═══ Clock Sources ═══
                _append_line("")
                _append_line("═══ CLOCK SOURCES ═══")
                _append_line("")

                if hasattr(result, "clocks") and result.clocks:
                    for clk in result.clocks:
                        name = clk.get("name", "Unknown")
                        freq = clk.get("frequency", "N/A")
                        ctype = clk.get("type", "N/A")
                        status = clk.get("status", "unknown")
                        ok = status.lower() in ("ok", "stable", "running", "locked", "active")
                        icon = "[OK]" if ok else "[!!]" if status.lower() in ("degraded", "marginal", "warning") else "[XX]"
                        _append_line(f"  {icon} {name}: {freq} | Type: {ctype} | Status: {status}")

                    # Update card fields from clock list
                    clk_map = {
                        "xtal": "clk_xtal", "dcxo": "clk_dcxo", "tcxo": "clk_dcxo",
                        "sleep": "clk_sleep", "rf": "clk_rf", "audio": "clk_audio",
                        "usb": "clk_usb",
                    }
                    for clk in result.clocks:
                        cname = clk.get("name", "").lower()
                        for pattern, field_key in clk_map.items():
                            if pattern in cname:
                                status = clk.get("status", "unknown")
                                freq = clk.get("frequency", "N/A")
                                ok = status.lower() in ("ok", "stable", "running", "locked", "active")
                                _set_field(clk_labels, field_key, f"{freq} | {status}", ok)
                                break
                else:
                    _append_line("  No clock source data available")

                app.content.after(0, lambda: progress.set(0.35))

                # ═══ RTC Information ═══
                _append_line("")
                _append_line("═══ RTC INFORMATION ═══")
                _append_line("")

                if hasattr(result, "rtc") and result.rtc:
                    rtc = result.rtc
                    rtc_time = rtc.get("time", "N/A")
                    rtc_alarm = rtc.get("alarm", "Not set")
                    rtc_drift_val = rtc.get("drift", "N/A")
                    rtc_ppm = rtc.get("accuracy_ppm", "N/A")
                    rtc_batt = rtc.get("battery", "N/A")
                    rtc_stat = rtc.get("status", "unknown")

                    _append_line(f"  Current Time:    {rtc_time}")
                    _append_line(f"  Alarm Register:  {rtc_alarm}")
                    _append_line(f"  Drift:           {rtc_drift_val} sec/day")
                    _append_line(f"  Accuracy:        {rtc_ppm} PPM")
                    _append_line(f"  Backup Battery:  {rtc_batt}")
                    _append_line(f"  Status:          {rtc_stat}")

                    rtc_ok = rtc_stat.lower() in ("ok", "running", "healthy", "good", "stable")
                    _set_field(rtc_labels, "rtc_time", rtc_time, rtc_ok)
                    _set_field(rtc_labels, "rtc_alarm", rtc_alarm, True)
                    drift_ok = True
                    try:
                        drift_ok = abs(float(str(rtc_drift_val).replace(" ", ""))) < 2.0
                    except (ValueError, TypeError):
                        pass
                    _set_field(rtc_labels, "rtc_drift", f"{rtc_drift_val} sec/day", drift_ok)
                    ppm_ok = True
                    try:
                        ppm_ok = abs(float(str(rtc_ppm).replace(" ", ""))) < 20.0
                    except (ValueError, TypeError):
                        pass
                    _set_field(rtc_labels, "rtc_accuracy", f"{rtc_ppm} PPM", ppm_ok)
                    batt_ok = str(rtc_batt).lower() not in ("low", "dead", "missing", "n/a")
                    _set_field(rtc_labels, "rtc_battery", rtc_batt, batt_ok)
                    _set_field(rtc_labels, "rtc_status", rtc_stat, rtc_ok)
                else:
                    _append_line("  No RTC data available")

                app.content.after(0, lambda: progress.set(0.55))

                # ═══ PLL Status ═══
                _append_line("")
                _append_line("═══ PLL STATUS ═══")
                _append_line("")

                if hasattr(result, "plls") and result.plls:
                    for pll in result.plls:
                        name = pll.get("name", "Unknown")
                        freq = pll.get("frequency", "N/A")
                        locked = pll.get("locked", False)
                        status_txt = "LOCKED" if locked else "UNLOCKED"
                        icon = "[OK]" if locked else "[XX]"
                        _append_line(f"  {icon} {name}: {freq} | {status_txt}")

                    # Update PLL card fields
                    pll_map = {
                        "cpu": "pll_cpu", "gpu": "pll_gpu", "ddr": "pll_ddr",
                        "disp": "pll_disp", "display": "pll_disp",
                        "cam": "pll_cam", "camera": "pll_cam",
                        "npu": "pll_npu",
                    }
                    for pll in result.plls:
                        pname = pll.get("name", "").lower()
                        for pattern, field_key in pll_map.items():
                            if pattern in pname:
                                freq = pll.get("frequency", "N/A")
                                locked = pll.get("locked", False)
                                status_txt = "LOCKED" if locked else "UNLOCKED"
                                _set_field(pll_labels, field_key, f"{freq} | {status_txt}", locked)
                                break
                else:
                    _append_line("  No PLL data available")

                app.content.after(0, lambda: progress.set(0.75))

                # ═══ XO Calibration ═══
                _append_line("")
                _append_line("═══ XO CALIBRATION ═══")
                _append_line("")

                if hasattr(result, "xo_cal") and result.xo_cal:
                    xo = result.xo_cal
                    xo_type_val = xo.get("type", "N/A")
                    xo_freq_val = xo.get("frequency", "N/A")
                    xo_trim_val = xo.get("trim", "N/A")
                    xo_tc = xo.get("temp_compensation", "N/A")
                    xo_aging_val = xo.get("aging", "N/A")
                    xo_stat = xo.get("status", "unknown")

                    _append_line(f"  Oscillator Type:        {xo_type_val}")
                    _append_line(f"  Nominal Frequency:      {xo_freq_val}")
                    _append_line(f"  Trim Value:             {xo_trim_val}")
                    _append_line(f"  Temp Compensation:      {xo_tc}")
                    _append_line(f"  Aging Offset:           {xo_aging_val}")
                    _append_line(f"  Calibration Status:     {xo_stat}")

                    cal_ok = xo_stat.lower() in ("ok", "calibrated", "good", "stable", "valid")
                    _set_field(xo_labels, "xo_type", xo_type_val, True)
                    _set_field(xo_labels, "xo_freq", xo_freq_val, True)
                    _set_field(xo_labels, "xo_trim", xo_trim_val, cal_ok)
                    _set_field(xo_labels, "xo_temp_comp", xo_tc, cal_ok)
                    _set_field(xo_labels, "xo_aging", xo_aging_val, cal_ok)
                    _set_field(xo_labels, "xo_status", xo_stat, cal_ok)
                else:
                    _append_line("  No XO calibration data available")

                app.content.after(0, lambda: progress.set(0.90))

                # ═══ Overall Health ═══
                _append_line("")
                _append_line("═══ OVERALL CLOCK HEALTH ═══")
                _append_line("")

                overall = getattr(result, "overall_health", "unknown")
                faults_list = getattr(result, "faults", [])
                warnings_list = getattr(result, "warnings", [])

                if faults_list:
                    _append_line(f"  Faults ({len(faults_list)}):")
                    for f in faults_list:
                        _append_line(f"    [XX] {f}")

                if warnings_list:
                    _append_line(f"  Warnings ({len(warnings_list)}):")
                    for w in warnings_list:
                        _append_line(f"    [!!] {w}")

                if not faults_list and not warnings_list:
                    if overall.lower() == "unknown":
                        _append_line("  [??] No clock data collected — connect device and retry")
                    else:
                        _append_line("  [OK] All clock subsystems healthy — no faults detected")

                # Update health badge
                if overall.lower() in ("healthy", "good", "ok", "pass"):
                    badge_text = "✅ Clock Health: HEALTHY — All oscillators and PLLs nominal"
                    badge_color = colors["success"]
                elif overall.lower() in ("degraded", "warning", "marginal"):
                    badge_text = f"⚠️ Clock Health: DEGRADED — {len(warnings_list)} warning(s)"
                    badge_color = colors["warning"]
                elif overall.lower() in ("critical", "fault", "fail", "error"):
                    badge_text = f"❌ Clock Health: CRITICAL — {len(faults_list)} fault(s) detected"
                    badge_color = colors["accent"]
                else:
                    badge_text = f"📋 Clock Health: {overall.upper()}"
                    badge_color = colors["text_dim"]

                app.content.after(0, lambda: health_label.configure(
                    text=badge_text, text_color=badge_color))

            except ImportError:
                _append_line("  ❌ Clock tester module not available")
                _append_line("     Ensure app.hardware.clock_tester is installed")
                app.content.after(0, lambda: health_label.configure(
                    text="❌ Clock Health: Module not found", text_color=colors["accent"]))
            except Exception as e:
                _append_line(f"  ❌ Clock detection error: {str(e)}")
                app.content.after(0, lambda: health_label.configure(
                    text=f"❌ Clock Health: Error — {str(e)[:60]}", text_color=colors["accent"]))

            # Footer
            _append_line("")
            _append_line("=" * 70)
            _append_line(f"  Report generated: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            _append_line("  Mooxy AI Fault Detector — Oscillator / Clock Test Module")
            _append_line("=" * 70)

            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Clock detection complete — see report above", text_color=colors["success"]))
            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

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
                                                 initialfile="clock_test_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    ctk.CTkButton(btn_frame, text="🕐 Start Detection", width=300, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_detection).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="📋 Copy", width=100, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="💾 Save", width=100, height=46,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    app.update_status("Clock Testing — Press Start to analyze oscillators and PLLs")
