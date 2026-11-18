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
        tb.tag_configure("ok", foreground="#34d399")       # Green
        tb.tag_configure("warning", foreground="#fbbf24")   # Orange
        tb.tag_configure("fault", foreground="#ec4899")     # Red
        tb.tag_configure("info", foreground="#a855f7")      # Blue
        tb.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#9a93b5")       # Grey

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
            # Report logic lives in app/hardware/scan_runners.py (shared with Jack).
            from app.hardware.scan_runners import run_adb_scan

            def _progress(pct, msg):
                app.content.after(0, lambda: progress.set(pct))
                if msg:
                    app.content.after(0, lambda: msg_label.configure(text=msg))

            try:
                res = run_adb_scan(emit=_track_and_append, progress=_progress)
                last_scan["result"] = res.get("result")
                if res.get("error"):
                    app.content.after(0, lambda: summary_label.configure(
                        text=res.get("summary_text", ""), text_color=colors["accent"]))
                else:
                    app.content.after(0, lambda: msg_label.configure(
                        text=res.get("saved_msg") or "Detection complete — full report above",
                        text_color=colors["success"]))
                    app.content.after(0, lambda: summary_label.configure(
                        text=res.get("summary_text", ""), text_color=colors["success"]))
                try:                            # Section 7 — proactive summary
                    if not res.get("error") and getattr(app, "proactive", None):
                        app.proactive.on_scan_done("ADB Detect", res.get("device_name", ""),
                                                   int(res.get("faults_count", 0) or 0))
                except Exception:
                    pass
            finally:
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
