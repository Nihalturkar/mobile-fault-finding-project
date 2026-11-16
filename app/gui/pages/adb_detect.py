import customtkinter as ctk
import threading
from pathlib import Path


def render_adb_detect(app):
    """ADB detection page — shows detections LIVE as they happen, real-time append."""
    colors = app.colors

    ctk.CTkLabel(app.content, text="📱 ADB Detection",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content, text="Full device diagnosis via USB — connects, scans everything, shows detailed report",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # Summary bar (hidden until detection done)
    summary_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=50)
    summary_frame.pack(fill="x", padx=20, pady=(0, 10))
    summary_frame.pack_propagate(False)
    summary_label = ctk.CTkLabel(summary_frame, text="Press Start to begin detection...",
                                  font=("Segoe UI", 14), text_color=colors["text_dim"])
    summary_label.pack(side="left", padx=20, pady=10)

    # Progress
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 10))

    # Buttons row
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    # ── Color tags setup ──
    def _setup_tags():
        """Setup color tags for the textbox."""
        tb = report_box._textbox  # Access internal tkinter Text widget
        tb.tag_configure("ok", foreground="#2ed573")       # Green
        tb.tag_configure("warning", foreground="#ffa502")   # Orange
        tb.tag_configure("fault", foreground="#e94560")     # Red
        tb.tag_configure("info", foreground="#1e90ff")      # Blue
        tb.tag_configure("header", foreground="#e94560", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#8892b0")       # Grey

    def _get_tag(text):
        """Determine color tag based on line content."""
        t = text.lower()
        if any(k in t for k in ["[xx]", "[!!]", "fault", "🔴", "critical", "danger", "overheating"]):
            return "fault"
        if any(k in t for k in ["[!!]", "warning", "🟡", "warm", "slightly warm"]):
            return "warning"
        if any(k in t for k in ["[ok]", "✅", "ok", "working", "normal", "healthy", "no fault", "no issue", "clean"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "---", "========", "DIAGNOSIS", "SUMMARY", "REPORT"]):
            return "header"
        if any(k in t for k in ["🔍", "checking", "reading", "scanning"]):
            return "info"
        return None

    # ── Live append helpers ─────────────────────────────────────
    def _append_live(text):
        """Append text to report box in real-time with color (thread-safe)."""
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
        """Append multiple lines at once with colors."""
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

    # Holds the most recent scan so "Explain with AI" can reuse it instead of
    # making the tech re-run detection on the device.
    last_scan = {"report": None, "result": None}

    def start_detection():
        if running["value"]:
            return
        running["value"] = True
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        summary_label.configure(text="🔄 Detecting...", text_color=colors["info"])
        progress.set(0)

        # Track all lines for final save
        full_report = {"lines": []}
        last_scan["report"] = full_report

        def _track_and_append(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_and_append_lines(lines):
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            try:
                from app.hardware.adb_detector import detect_via_adb, generate_full_report

                # Track what's been detected for live display
                last_phase = {"msg": ""}

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                    # Show each scan phase live as it happens
                    if msg != last_phase["msg"]:
                        last_phase["msg"] = msg
                        icon = "🔍"
                        msg_lower = msg.lower()
                        if "ok" in msg_lower or "found" in msg_lower or "done" in msg_lower:
                            icon = "✅"
                        elif "error" in msg_lower or "fail" in msg_lower or "not found" in msg_lower:
                            icon = "❌"
                        elif "reading" in msg_lower or "scanning" in msg_lower or "checking" in msg_lower:
                            icon = "🔍"
                        elif "sampling" in msg_lower:
                            icon = "📊"
                        elif "running" in msg_lower or "ai" in msg_lower:
                            icon = "🧠"
                        _track_and_append(f"  {icon} {msg}")

                # Show header
                import datetime as _dt
                header = [
                    "=" * 72,
                    "  MOOXY AI FAULT DETECTOR — ADB DETECTION",
                    "=" * 72,
                    f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "=" * 72,
                    "",
                    "═══ SCANNING DEVICE ═══",
                    "",
                ]
                _track_and_append_lines(header)

                result = detect_via_adb(callback=cb)
                last_scan["result"] = result

                if result.error:
                    _track_and_append(f"")
                    _track_and_append(f"  ❌ ERROR: {result.error}")
                    _track_and_append(f"")
                    app.content.after(0, lambda: summary_label.configure(
                        text=f"❌ {result.error[:80]}", text_color=colors["accent"]))
                    app.content.after(0, lambda: progress.set(1.0))
                    running["value"] = False
                    return

                # ══════════════════════════════════════════════
                #  SMART REPORT — same format as UART
                #  Confirmed fault → PROBLEM DETECTED
                #  Possible → "Check kijiye"
                #  No evidence → don't show
                # ══════════════════════════════════════════════

                # 1. DEVICE INFO (compact)
                _track_and_append("")
                device_line = f"  {result.brand} {result.model} | Android {result.android_version}"
                if result.chipset:
                    device_line += f" | {result.chipset}"
                _track_and_append(device_line)

                info_parts = []
                if result.ram_total_kb:
                    info_parts.append(f"RAM: {result.ram_total_kb // 1024}MB")
                if result.storage_total_kb:
                    info_parts.append(f"Storage: {result.storage_total_kb // (1024*1024)}GB free {result.storage_free_kb // (1024*1024)}GB")
                if result.battery_level:
                    info_parts.append(f"Battery: {result.battery_level}% ({result.battery_health})")
                if info_parts:
                    _track_and_append(f"  {' | '.join(info_parts)}")

                # 2. CATEGORIZE DIAGNOSES
                faults = [d for d in result.diagnoses if d.status == "FAULT"]
                warnings = [d for d in result.diagnoses if d.status == "WARNING"]

                # Also run fault analyzer for confidence scores
                from app.hardware.fault_analyzer import analyze_adb_result
                fault_report = analyze_adb_result(result)
                confirmed = [f for f in fault_report.faults if f.confidence >= 75]
                possible = [f for f in fault_report.faults if 50 <= f.confidence < 75]

                # 3. CONFIRMED PROBLEMS
                has_problems = bool(faults or confirmed)

                if has_problems:
                    _track_and_append("")
                    _track_and_append("=" * 55)
                    _track_and_append("  🔴 PROBLEM DETECTED")
                    _track_and_append("=" * 55)

                    # Show confirmed faults with repair steps
                    shown = set()
                    for f in confirmed:
                        key = f.component + f.problem
                        if key in shown:
                            continue
                        shown.add(key)
                        _track_and_append("")
                        _track_and_append(f"  Problem: {f.problem}")
                        _track_and_append(f"  Component: {f.component} ({f.confidence}%)")
                        if f.repair_steps:
                            _track_and_append("  How to Fix:")
                            for i, step in enumerate(f.repair_steps, 1):
                                _track_and_append(f"    {i}. {step}")
                        if f.parts_needed:
                            _track_and_append(f"  Parts: {', '.join(f.parts_needed)}")

                    # Show diagnosis faults that weren't in fault_report
                    for d in faults:
                        if d.component not in shown:
                            _track_and_append(f"  🔴 {d.component}: {d.summary}")
                            for fix in d.fixes[:2]:
                                _track_and_append(f"     Fix: {fix}")

                    _track_and_append("")
                    _track_and_append("=" * 55)
                else:
                    _track_and_append("")
                    _track_and_append("  ✅ No confirmed faults detected")

                # 4. POSSIBLE ISSUES — "check kijiye"
                if possible or warnings:
                    _track_and_append("")
                    _track_and_append("  ── Isse bhi check kijiye ──")
                    shown_possible = set()
                    for f in possible:
                        key = f.component
                        if key in shown_possible:
                            continue
                        shown_possible.add(key)
                        _track_and_append(f"  ℹ️ {f.component}: {f.problem} ({f.confidence}%)")
                    for d in warnings:
                        if d.component not in shown_possible:
                            _track_and_append(f"  ℹ️ {d.component}: {d.summary}")

                # 5. DEVICE DATA (compact)
                _track_and_append("")
                _track_and_append("── Device Data ──")

                # Battery
                bat_parts = [f"Level:{result.battery_level}%", f"Health:{result.battery_health}", f"Temp:{result.battery_temp_c}C"]
                if result.battery_wear_pct >= 0:
                    bat_parts.append(f"Wear:{result.battery_wear_pct}%")
                _track_and_append(f"  Battery: {' | '.join(bat_parts)}")

                # Connectivity (compact)
                conn_parts = []
                if result.wifi_state:
                    conn_parts.append(f"WiFi:{result.wifi_state}")
                if result.sim_state:
                    conn_parts.append(f"SIM:{result.sim_state}")
                if result.bt_mac:
                    conn_parts.append(f"BT:Connected")
                if conn_parts:
                    _track_and_append(f"  Connectivity: {' | '.join(conn_parts)}")

                # Healthy components (one line)
                oks = [d for d in result.diagnoses if d.status == "OK"]
                if oks:
                    ok_names = [d.component for d in oks]
                    _track_and_append(f"  OK: {', '.join(ok_names)}")

                # ── Phone Database Lookup ──
                from app.gui.pages.hw_detect import _lookup_phone_db, _format_phone_db_section
                _db_hit = _lookup_phone_db(
                    brand=result.brand or "",
                    chipset=result.chipset or "",
                    model=f"{result.brand} {result.model}" if result.model else "",
                )
                if _db_hit:
                    for line in _format_phone_db_section(*_db_hit):
                        _track_and_append(line)

                # Store full detailed report for file saving
                ai_report = ""
                full_detailed_report = generate_full_report(result)

                # ── Final UI ──
                app.content.after(0, lambda: progress.set(1.0))
                app.content.after(0, lambda: msg_label.configure(
                    text="Detection complete — full report above", text_color=colors["success"]))
                app.content.after(0, lambda: summary_label.configure(
                    text=f"✅ {result.brand} {result.model} | Android {result.android_version} | Battery: {result.battery_level}% {result.battery_health} | Faults: {len([d for d in result.diagnoses if d.status == 'FAULT'])}",
                    text_color=colors["success"]))

                # ── Save raw files ──
                from app.gui.history_manager import get_unique_log_path
                report_text = "\n".join(full_report["lines"])
                adb_log_path = get_unique_log_path("adb_log")

                try:
                    with open(adb_log_path, "w", encoding="utf-8") as f:
                        f.write(report_text)

                    logcat_all = "\n".join(
                        result.logcat_battery_events + result.logcat_display_events +
                        result.logcat_touch_events + result.logcat_audio_events +
                        result.logcat_camera_events + result.logcat_fingerprint_events +
                        result.logcat_wifi_events + result.logcat_bluetooth_events +
                        result.logcat_modem_events + result.logcat_sensors_events +
                        result.logcat_crash_events + result.logcat_errors +
                        result.logcat_hw_driver_lines
                    )
                    if logcat_all:
                        logcat_path = get_unique_log_path("raw_logcat")
                        with open(logcat_path, "w", encoding="utf-8") as f:
                            f.write(f"=== Raw Logcat — {result.logcat_raw_lines} lines ===\n")
                            f.write(f"=== Date: {__import__('datetime').datetime.now()} ===\n\n")
                            f.write(logcat_all)

                    if result.thermal_service_raw:
                        thermal_path = get_unique_log_path("raw_thermalservice")
                        with open(thermal_path, "w", encoding="utf-8") as f:
                            f.write(f"=== Raw Thermalservice Dump ===\n")
                            f.write(f"=== Date: {__import__('datetime').datetime.now()} ===\n\n")
                            f.write(result.thermal_service_raw)

                    if result.battery_sysfs or result.charger_sysfs:
                        batt_path = get_unique_log_path("raw_battery")
                        with open(batt_path, "w", encoding="utf-8") as f:
                            f.write(f"=== Raw Battery/Charging Data ===\n")
                            f.write(f"=== Date: {__import__('datetime').datetime.now()} ===\n\n")
                            f.write("--- Battery sysfs ---\n")
                            for k, v in result.battery_sysfs.items():
                                f.write(f"{k}: {v}\n")
                            f.write("\n--- Charger sysfs ---\n")
                            for k, v in result.charger_sysfs.items():
                                f.write(f"{k}: {v}\n")
                            f.write(f"\n--- dumpsys battery ---\n")
                            f.write(result.battery_dumpsys_raw)

                    saved_name = adb_log_path.name
                    app.content.after(0, lambda: msg_label.configure(
                        text=f"📁 Saved: {saved_name} + raw logs → config/logs/",
                        text_color=colors["success"]))
                except Exception:
                    pass

                # ── Save to history ──
                try:
                    from app.gui.history_manager import add_detection

                    faults = [d for d in result.diagnoses if d.status == "FAULT"]
                    warnings = [d for d in result.diagnoses if d.status == "WARNING"]
                    fault_names = [f"{d.component}: {d.summary}" for d in faults + warnings]

                    add_detection(
                        detection_type="ADB",
                        device_name=f"{result.brand} {result.model}",
                        summary=f"Android {result.android_version} | Chipset: {result.chipset} | Battery: {result.battery_level}% {result.battery_health}",
                        faults_count=len(faults),
                        faults_summary="; ".join(fault_names[:5]),
                        report_file=str(adb_log_path),
                        extra={
                            "android_version": result.android_version,
                            "battery_level": result.battery_level,
                            "battery_health": result.battery_health,
                            "warnings_count": len(warnings),
                            "ok_count": len([d for d in result.diagnoses if d.status == "OK"]),
                        }
                    )
                except Exception as e:
                    print(f"[ADB Detect] History save error: {e}")

                running["value"] = False

            except Exception as e:
                _track_and_append(f"")
                _track_and_append(f"  ❌ ERROR: {str(e)}")
                app.content.after(0, lambda: summary_label.configure(
                    text=f"❌ {str(e)[:80]}", text_color=colors["accent"]))
                app.content.after(0, lambda: progress.set(1.0))
                running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    def explain_with_ai():
        """Send the completed ADB scan to the AI backends for a written diagnosis.

        On demand only, so a normal scan never costs an API call. Sends the
        measurements the detector already collected plus the rule verdicts,
        rather than raw logcat — cheaper, and the model reasons over numbers
        instead of thousands of chatter lines.
        """
        result = last_scan.get("result")
        if not result:
            msg_label.configure(text="⚠️ Run a detection first.",
                                text_color=colors["warning"])
            return
        if running["value"]:
            msg_label.configure(text="⚠️ Detection still running.",
                                text_color=colors["warning"])
            return

        msg_label.configure(text="🧠 Asking AI…", text_color=colors["info"])

        def run_ai():
            try:
                from app.hardware.fallback_analyzer import FallbackAnalyzer

                facts = []
                for attr, label in (
                    ("brand", "Brand"), ("model", "Model"),
                    ("android_version", "Android"), ("chipset", "Chipset"),
                    ("battery_level", "Battery level %"),
                    ("battery_health", "Battery health"),
                    ("battery_voltage", "Battery voltage"),
                    ("battery_temp_c", "Battery temp C"),
                    ("battery_wear_pct", "Battery wear %"),
                    ("battery_cycle_count", "Charge cycles"),
                    ("storage_health_pct", "Storage health %"),
                    ("storage_pre_eol", "Storage pre-EOL"),
                    ("storage_life_time_a", "UFS life time A"),
                    ("storage_life_time_b", "UFS life time B"),
                ):
                    val = getattr(result, attr, None)
                    if val not in (None, "", -1, 0):
                        facts.append(f"{label}: {val}")

                hot = [f"{z.name} {z.temp_c}C" for z in getattr(result, "thermal_zones", [])
                       if getattr(z, "temp_c", 0) and z.temp_c >= 45]
                if hot:
                    facts.append("Hot thermal zones: " + ", ".join(hot[:6]))

                for d in getattr(result, "diagnoses", []):
                    if d.status in ("FAULT", "WARNING"):
                        facts.append(f"Rule [{d.status}] {d.component}: {d.summary}")

                for name, count in (
                    ("crash events", len(getattr(result, "logcat_crash_events", []))),
                    ("error lines", len(getattr(result, "logcat_errors", []))),
                ):
                    if count:
                        facts.append(f"logcat {name}: {count}")

                context = "\n".join(facts)
                # A sample of real crash lines helps far more than the counts.
                sample = "\n".join(
                    (getattr(result, "logcat_crash_events", [])[:20]
                     + getattr(result, "logcat_errors", [])[:30]))

                ai = FallbackAnalyzer().analyze(
                    log_text=(sample or context)[:15000], mode="android",
                    detected_context=context)

                lines = ["", "=" * 55, "  🧠 AI DIAGNOSIS", "=" * 55, ""]
                if ai.success and ai.parsed:
                    p = ai.parsed
                    for k in ("summary", "diagnosis", "root_cause", "conclusion"):
                        if p.get(k):
                            lines += [f"  {p[k]}", ""]
                    for step in (p.get("repair_steps") or p.get("next_steps") or []):
                        lines.append(f"  • {step}")
                    if not any(l.strip() for l in lines[5:]):
                        lines.append("  " + (ai.raw_response or "")[:2000])
                elif ai.success:
                    lines.append("  " + (ai.raw_response or "")[:2000])
                else:
                    lines.append(f"  ⚠️ {ai.error or 'AI analysis unavailable.'}")
                    lines.append("  Set a Groq API key, or run Ollama locally,")
                    lines.append("  in the AI Log Analysis page.")
                lines.append("")

                app.content.after(0, lambda: _append_live_lines(lines))
                if last_scan.get("report"):
                    last_scan["report"]["lines"].extend(lines)
                app.content.after(0, lambda: msg_label.configure(
                    text="🧠 AI diagnosis added to report.",
                    text_color=colors["success"]))
            except Exception as e:
                app.content.after(0, lambda: msg_label.configure(
                    text=f"⚠️ AI error: {e}", text_color=colors["warning"]))

        threading.Thread(target=run_ai, daemon=True).start()

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
                                                 initialfile="adb_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    ctk.CTkButton(btn_frame, text="🔍 Start ADB Detection", width=250, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_detection).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="🧠 Explain with AI", width=170, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=explain_with_ai).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="📋 Copy Report", width=140, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="💾 Save Report", width=140, height=46,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # Main report textbox (scrollable, selectable, copyable)
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=600, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0", "Press 'Start ADB Detection' to begin.\n\nRequirements:\n• Phone connected via USB\n• USB Debugging enabled\n• ADB installed and in PATH\n• PC authorized on phone\n")
    report_box.configure(state="normal")
    _setup_tags()

    app.update_status("ADB Detection — Connect phone via USB and press Start")
