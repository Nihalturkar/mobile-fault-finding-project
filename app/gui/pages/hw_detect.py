import customtkinter as ctk
import threading
import json
from pathlib import Path


def _lookup_phone_db(brand="", chipset="", model="", codename_hint=""):
    """Match detected device against phone_database.json. Returns (model_name, device_dict) or None."""
    db_path = Path(__file__).parent.parent.parent / "config" / "phone_database.json"
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return None
    devices = db.get("devices", {})
    brand_lower = (brand or "").lower()
    chipset_upper = (chipset or "").upper()
    model_lower = (model or "").lower()
    codename_lower = (codename_hint or "").lower()

    best = None
    for brand_key, models in devices.items():
        for model_name, info in models.items():
            chip = (info.get("chipset", "") or "").upper()
            chip_name = (info.get("chipset_name", "") or "").upper()
            codename = (info.get("codename", "") or "").lower()
            mn_lower = model_name.lower()
            # Exact codename match (highest priority)
            if codename and codename_lower and codename == codename_lower:
                return model_name, info
            # Exact model match
            if model_lower and (model_lower in mn_lower or mn_lower in model_lower or (codename and codename in model_lower)):
                return model_name, info
            # Chipset + brand match
            if chipset_upper and (chipset_upper in chip or chipset_upper in chip_name):
                if brand_lower and brand_lower in brand_key:
                    if best is None:
                        best = (model_name, info)
                elif best is None:
                    best = (model_name, info)
    return best


def _format_phone_db_section(model_name, info):
    """Format phone_database entry as report lines."""
    lines = []
    lines.append("")
    lines.append("── Phone Database Info ──")
    lines.append(f"  Model: {model_name}")
    if info.get("chipset_name"):
        lines.append(f"  Chipset: {info['chipset_name']} ({info.get('chipset', '')})")
    if info.get("pmic"):
        lines.append(f"  PMIC: {info['pmic']}")
    if info.get("charging_ic"):
        lines.append(f"  Charging IC: {info['charging_ic']}")
    if info.get("wifi_bt"):
        lines.append(f"  WiFi/BT: {info['wifi_bt']}")
    if info.get("audio_codec"):
        lines.append(f"  Audio: {info['audio_codec']}")
    if info.get("nfc"):
        lines.append(f"  NFC: {info['nfc']}")
    if info.get("display"):
        lines.append(f"  Display: {info['display']}")
    if info.get("battery"):
        bat_line = f"  Battery: {info['battery']}"
        if info.get("charging_speed"):
            bat_line += f" | {info['charging_speed']}"
        lines.append(bat_line)
    if info.get("usb"):
        lines.append(f"  USB: {info['usb']}")
    if info.get("test_point"):
        lines.append(f"  Test Point: {info['test_point']}")
    if info.get("edl_mode"):
        lines.append(f"  EDL Mode: {info['edl_mode']}")
    if info.get("fastboot_key"):
        lines.append(f"  Fastboot: {info['fastboot_key']}")
    faults = info.get("common_faults", [])
    if faults:
        lines.append(f"  Known Issues: {', '.join(faults)}")
    return lines


def render_hw_detect(app):
    """Hardware detection page — UART + EDL + JTAG, full report in copyable textbox.
    Shows detections LIVE as they happen — real-time append."""
    colors = app.colors

    ctk.CTkLabel(app.content, text="🔌 Hardware Detection (AI Engine)",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content, text="Boot phone during detection — captures hardware data automatically",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 10))

    # Settings row
    settings = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=10)
    settings.pack(fill="x", padx=20, pady=(0, 10))
    s_inner = ctk.CTkFrame(settings, fg_color="transparent")
    s_inner.pack(fill="x", padx=15, pady=10)

    ctk.CTkLabel(s_inner, text="COM:", font=("Segoe UI", 13, "bold"),
                 text_color=colors["text"]).pack(side="left")
    port_var = ctk.StringVar(value="COM12")
    ctk.CTkEntry(s_inner, textvariable=port_var, width=80, height=36,
                 fg_color=colors["bg_light"], border_color=colors["border"],
                 font=("Segoe UI", 13)).pack(side="left", padx=(5, 15))

    ctk.CTkLabel(s_inner, text="Baud:", font=("Segoe UI", 13, "bold"),
                 text_color=colors["text"]).pack(side="left")
    baud_var = ctk.StringVar(value="921600")
    ctk.CTkOptionMenu(s_inner, values=["115200", "921600"], variable=baud_var,
                       width=100, height=36, fg_color=colors["bg_light"],
                       button_color=colors["accent"]).pack(side="left", padx=(5, 15))

    ctk.CTkLabel(s_inner, text="Listen:", font=("Segoe UI", 13, "bold"),
                 text_color=colors["text"]).pack(side="left")
    dur_var = ctk.StringVar(value="90")
    ctk.CTkOptionMenu(s_inner, values=["45", "60", "90", "120", "180", "240"], variable=dur_var,
                       width=70, height=36, fg_color=colors["bg_light"],
                       button_color=colors["accent"]).pack(side="left", padx=(5, 5))
    ctk.CTkLabel(s_inner, text="sec", font=("Segoe UI", 12),
                 text_color=colors["text_dim"]).pack(side="left")

    # Summary bar
    summary_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=10, height=45)
    summary_frame.pack(fill="x", padx=20, pady=(0, 5))
    summary_frame.pack_propagate(False)
    summary_label = ctk.CTkLabel(summary_frame, text="Press Start, then boot the phone within listening time",
                                  font=("Segoe UI", 13), text_color=colors["text_dim"])
    summary_label.pack(side="left", padx=15, pady=8)

    # Progress
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 5))

    # Buttons
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    def _safe_after(fn):
        """Schedule fn on the main thread only if widgets still exist."""
        def _wrapped():
            try:
                fn()
            except Exception:
                pass
        try:
            if app.content.winfo_exists():
                app.content.after(0, _wrapped)
        except Exception:
            pass

    # ── Color tags setup ──
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#34d399")
        tb.tag_configure("warning", foreground="#fbbf24")
        tb.tag_configure("fault", foreground="#ec4899")
        tb.tag_configure("info", foreground="#a855f7")
        tb.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "🔴", "critical", "danger", "❌", "[xx]"]):
            return "fault"
        if any(k in t for k in ["warning", "🟡", "⚠️", "[!!]"]):
            return "warning"
        if any(k in t for k in ["✅", "[ok]", "ok", "pass", "working", "healthy", "clean boot"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "========", "PHASE", "REPORT"]):
            return "header"
        if any(k in t for k in ["🔍", "listening", "boot the phone"]):
            return "info"
        return None

    # ── Live append helper ──────────────────────────────────────
    def _append_live(text):
        """Append text to report box in real-time with color."""
        def _do():
            try:
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
            except Exception:
                pass
        _safe_after(_do)

    def _append_live_lines(lines):
        """Append multiple lines at once with colors."""
        def _do():
            try:
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
            except Exception:
                pass
        _safe_after(_do)

    def _append_section_header(title):
        """Append a visible section header."""
        _append_live("")
        _append_live(f"{'═' * 60}")
        _append_live(f"  {title}")
        _append_live(f"{'═' * 60}")
        _append_live("")

    # Holds the most recent scan so "Explain with AI" can reuse it instead of
    # asking the tech to boot the phone a second time.
    last_scan = {"report": None, "parsed": None}

    def start_detection():
        if running["value"]:
            return
        running["value"] = True

        # Enable stop button in sidebar
        import threading as _threading
        stop_event = _threading.Event()
        running["stop_event"] = stop_event
        try:
            app.enable_stop_button(stop_event)
        except Exception:
            pass

        report_box.configure(state="normal")
        report_box.delete("1.0", "end")

        summary_label.configure(text="🔴 LISTENING — BOOT THE PHONE NOW!", text_color=colors["accent"])
        progress.set(0)

        port = port_var.get().strip()
        baud = int(baud_var.get().strip())
        duration = int(dur_var.get().strip())

        # Store full report for saving
        full_report = {"lines": []}
        last_scan["report"] = full_report

        def _track_and_append(text):
            """Append to screen AND track for final save."""
            full_report["lines"].append(text)
            _append_live(text)

        def _track_and_append_lines(lines):
            """Append multiple lines to screen AND track."""
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            # Report logic lives in app/hardware/scan_runners.py (shared with Jack).
            from app.hardware.scan_runners import run_uart_scan

            def _progress(pct, msg):
                _safe_after(lambda: progress.set(pct))
                if msg:
                    _safe_after(lambda: msg_label.configure(text=msg))

            try:
                res = run_uart_scan(port, baud, duration, emit=_track_and_append,
                                    progress=_progress, stop_event=stop_event)
                last_scan["parsed"] = res.get("parsed")
                if res.get("stopped"):
                    _safe_after(lambda: msg_label.configure(
                        text="Scan stopped", text_color=colors["warning"]))
                else:
                    _safe_after(lambda: msg_label.configure(
                        text="Detection complete — full report above", text_color=colors["success"]))
                    ok = res.get("summary_ok")
                    _safe_after(lambda: summary_label.configure(
                        text=res.get("summary_text", ""),
                        text_color=colors["success"] if ok else colors["warning"]))
                    try:                        # Section 7 — proactive summary
                        if getattr(app, "proactive", None):
                            app.proactive.on_scan_done("HW Detect", res.get("device_name", ""),
                                                       int(res.get("faults_count", 0) or 0))
                    except Exception:
                        pass
            except Exception as e:
                _track_and_append(f"  ❌ Detection Error: {str(e)}")
            finally:
                running["value"] = False
                try:
                    app.disable_stop_button()
                except Exception:
                    pass

        threading.Thread(target=run, daemon=True).start()

    def explain_with_ai():
        """Send the parsed scan to the AI backends for a written diagnosis.

        Only runs on demand, so a normal scan never costs an API call. Sends
        the facts the parser already extracted rather than the raw capture —
        cheaper, and the model reasons over clean data instead of 37 KB of
        boot chatter.
        """
        parsed = last_scan.get("parsed")
        if not parsed:
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
                for key, label in (
                    ("chipset", "Chipset"), ("db_match", "SoC"),
                    ("platform", "Platform"), ("battery_vbat", "VBAT"),
                    ("battery_vbat_per_cycle", "VBAT per boot cycle"),
                    ("battery_vi_samples", "Battery V/I samples"),
                    ("qcom_battery_id", "Battery ID"),
                    ("boot_cycle_count", "Boot cycles in capture"),
                    ("boot_reason", "Boot reason"),
                    ("boot_reason_detail", "Power-off reason"),
                    ("qcom_last_stage", "Last boot stage reached"),
                    ("ram", "RAM"), ("storage_type", "Storage"),
                ):
                    val = parsed.get(key)
                    if val:
                        facts.append(f"{label}: {val}")

                for f in parsed.get("faults_detected", []):
                    if f.get("confidence", 0) >= 50:
                        facts.append(
                            f"Rule matched [{f.get('confidence')}%]: "
                            f"{f.get('name')} — {f.get('value', '')}")

                context = "\n".join(facts)
                log = parsed.get("readable_lines", "") or parsed.get("raw_text", "")

                result = FallbackAnalyzer().analyze(
                    log_text=log[:15000], mode="boot", detected_context=context)

                lines = ["", "=" * 55, "  🧠 AI DIAGNOSIS", "=" * 55, ""]
                if result.success and result.parsed:
                    p = result.parsed
                    for k in ("summary", "diagnosis", "root_cause", "conclusion"):
                        if p.get(k):
                            lines += [f"  {p[k]}", ""]
                    for step in (p.get("repair_steps") or p.get("next_steps") or []):
                        lines.append(f"  • {step}")
                    if not any(l.strip() for l in lines[5:]):
                        lines.append("  " + (result.raw_response or "")[:2000])
                elif result.success:
                    lines.append("  " + (result.raw_response or "")[:2000])
                else:
                    lines.append(f"  ⚠️ {result.error or 'AI analysis unavailable.'}")
                    lines.append("  Set a Groq API key, or run Ollama locally,")
                    lines.append("  in the AI Log Analysis page.")
                lines.append("")

                _safe_after(lambda: _append_live_lines(lines))
                if last_scan.get("report"):
                    last_scan["report"]["lines"].extend(lines)
                _safe_after(lambda: msg_label.configure(
                    text="🧠 AI diagnosis added to report.",
                    text_color=colors["success"]))
            except Exception as e:
                # Bind the message now: `e` is cleared when the except block
                # ends, before the scheduled lambda runs on the main thread.
                err = str(e)
                _safe_after(lambda: msg_label.configure(
                    text=f"⚠️ AI error: {err}", text_color=colors["warning"]))

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
                                                 initialfile="hw_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    ctk.CTkButton(btn_frame, text="🔌 Start Detection — Boot Phone!", width=300, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_detection).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="🧠 Explain with AI", width=170, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=explain_with_ai).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="📋 Copy", width=100, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="💾 Save", width=100, height=46,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # Report textbox
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=600, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0", "Press 'Start Detection' then boot the phone.\n\nSetup:\n• TX → Phone RX\n• RX → Phone TX\n• GND → Phone GND\n\nPhone boot karo jab 'BOOT NOW' dikhe.\n")
    _setup_tags()

    app.update_status("HW Detection — Press Start, then boot the phone")
