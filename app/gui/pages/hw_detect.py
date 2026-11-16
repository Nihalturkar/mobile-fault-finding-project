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
    ctk.CTkOptionMenu(s_inner, values=["45", "60", "90", "120"], variable=dur_var,
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
        tb.tag_configure("ok", foreground="#2ed573")
        tb.tag_configure("warning", foreground="#ffa502")
        tb.tag_configure("fault", foreground="#e94560")
        tb.tag_configure("info", foreground="#1e90ff")
        tb.tag_configure("header", foreground="#e94560", font=("Consolas", 12, "bold"))

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
            import datetime as _dt

            # ── Header ──
            header = [
                "=" * 70,
                "  MOOXY AI FAULT DETECTOR — HARDWARE DETECTION REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"  Port: {port} @ {baud} baud | Listen: {duration} sec",
                "=" * 70,
                "",
            ]
            _track_and_append_lines(header)

            # ═══ PHASE 1: DETECTION ═══
            _track_and_append("")
            _track_and_append("═══ PHASE 1: DETECTION ═══")
            _track_and_append("")
            _track_and_append("🔴 BOOT THE PHONE NOW! Listening...")
            _track_and_append("")

            uart_result = None
            try:
                from app.hardware.device_detector import DeviceAutoDetector

                def uart_cb(elapsed, total_bytes):
                    # Check if user pressed Stop
                    stop_ev = running.get("stop_event")
                    if stop_ev and stop_ev.is_set():
                        raise InterruptedError("Scan stopped by user")
                    pct = elapsed / duration * 0.7
                    remaining = int(duration - elapsed)
                    _safe_after(lambda: progress.set(min(pct, 0.7)))
                    _safe_after(lambda: msg_label.configure(
                        text=f"Scanning: {remaining}s left | {total_bytes} bytes | BOOT PHONE NOW!"))

                detector = DeviceAutoDetector(port=port, baud=baud)
                try:
                    uart_result = detector.detect(listen_duration=duration, callback=uart_cb)
                except InterruptedError:
                    _track_and_append("")
                    _track_and_append("⏹ Scan stopped by user")
                    _safe_after(lambda: msg_label.configure(
                        text="Scan stopped", text_color=colors["warning"]))
                    running["value"] = False
                    try:
                        app.disable_stop_button()
                    except Exception:
                        pass
                    return

                if not uart_result.detected:
                    err_msg = uart_result.error or "No data received — check TX/GND connections"
                    _track_and_append(f"  ⚠️ {err_msg}")
                else:
                    r = uart_result.raw_responses

                    # ══════════════════════════════════════════════
                    #  SMART REPORT — sirf useful info dikhao
                    #  Confirmed fault → PROBLEM DETECTED
                    #  Possible fault → "Check kijiye"
                    #  No evidence → mat dikhao
                    # ══════════════════════════════════════════════

                    # 1. DEVICE INFO (one line)
                    chip_name = r.get("chipset_marketing_name", "")
                    db_match = r.get("chipset_db_match", "")
                    pmic = r.get("pmic_model", "")
                    product_name = r.get("qcom_product_name", "")
                    brand_display = uart_result.brand or "Unknown"
                    if product_name:
                        brand_display += f" ({product_name})"
                    device_line = f"  {brand_display}"
                    if db_match:
                        device_line += f" | {db_match} ({chip_name})"
                    else:
                        device_line += f" | {uart_result.chipset}"
                    if pmic:
                        device_line += f" | PMIC: {pmic}"
                    bat = r.get("battery_vbat", "")
                    if bat:
                        device_line += f" | Battery: {bat}"
                    _track_and_append(device_line)

                    # 2. Collect all faults by confidence level
                    confirmed_faults = []   # confidence >= 75% — show as PROBLEM
                    possible_faults = []    # confidence 50-74% — show as "check kijiye"
                    # Skip below 50% — insufficient evidence

                    # From uart_log, extract structured fault data
                    # Parse the raw_responses for structured data instead of log text
                    import json as _json

                    # Get parsed data from device_detector
                    try:
                        from app.hardware.device_detector import DeviceAutoDetector
                        _det = DeviceAutoDetector(port=port, baud=baud)
                        # raw_data is a hex string — convert back to bytes for parsing
                        _raw_bytes = bytes.fromhex(uart_result.raw_data) if isinstance(uart_result.raw_data, str) else uart_result.raw_data
                        _parsed = _det._parse_boot_data(_raw_bytes)
                    except Exception as _parse_err:
                        print(f"[HW Detect] Re-parse error: {_parse_err}")
                        _parsed = {}
                    last_scan["parsed"] = _parsed

                    # Categorize faults
                    for fault in _parsed.get("faults_detected", []):
                        conf = fault.get("confidence", 50)
                        if conf >= 75:
                            confirmed_faults.append(fault)
                        elif conf >= 50:
                            possible_faults.append(fault)

                    # Known fault from database (highest priority)
                    known_fault = _parsed.get("known_fault_info")
                    correlated = _parsed.get("correlated_faults", [])
                    boot_stuck = _parsed.get("boot_stuck", False)
                    matched_patterns = _parsed.get("matched_fault_patterns", [])

                    # ── CONFIRMED PROBLEMS (>= 75% confidence)
                    has_problem = bool(known_fault or correlated or confirmed_faults or boot_stuck)

                    if has_problem:
                        _track_and_append("")
                        _track_and_append("=" * 55)
                        _track_and_append("  🔴 PROBLEM DETECTED")
                        _track_and_append("=" * 55)

                        # Known fault from database — most specific
                        if known_fault:
                            _track_and_append("")
                            _track_and_append(f"  Problem: {known_fault.get('symptom', '')}")
                            _track_and_append(f"  Cause:   {known_fault.get('root_cause', '')}")
                            _track_and_append(f"  Confidence: {known_fault.get('confidence', 0)}%")
                            _track_and_append("")
                            _track_and_append("  How to Fix:")
                            for i, step in enumerate(known_fault.get("repair_steps", []), 1):
                                _track_and_append(f"    {i}. {step}")
                            _track_and_append(f"  Difficulty: {known_fault.get('difficulty', '?')}")

                        # Correlated diagnosis
                        elif correlated:
                            for cf in correlated:
                                _track_and_append("")
                                _track_and_append(f"  Problem: {cf.get('title', '')}")
                                _track_and_append(f"  Cause:   {cf.get('root_cause', '')}")
                                _track_and_append(f"  Confidence: {cf.get('confidence', 0)}%")
                                _track_and_append("")
                                _track_and_append("  How to Fix:")
                                for i, step in enumerate(cf.get("repair_steps", []), 1):
                                    _track_and_append(f"    {i}. {step}")

                        # Individual confirmed faults
                        if confirmed_faults:
                            seen_names = set()
                            for fault in confirmed_faults:
                                name = fault.get("name", "")
                                if name in seen_names:
                                    continue
                                seen_names.add(name)
                                count = fault.get("repeat_count", 1)
                                count_str = f" (x{count})" if count > 1 else ""
                                _track_and_append(f"  ⚠️ {name}{count_str}: {fault.get('message', '')[:100]}")

                        # DDR voltage rails — show when DDR fault is detected
                        ddr_rails = _parsed.get("ddr_voltage_rails", {})
                        if ddr_rails:
                            ddr_type = _parsed.get("ddr_type_detected", "DDR")
                            abort_reason = _parsed.get("ddr_abort_reason", "")
                            _track_and_append("")
                            _track_and_append(f"  ── {ddr_type} Voltage Rails (measure with multimeter) ──")
                            if abort_reason:
                                _track_and_append(f"  Abort Reason: {abort_reason}")
                            _track_and_append("")
                            for rail_name, rail_info in ddr_rails.items():
                                expected = rail_info.get("expected", "?")
                                status = rail_info.get("status", "check")
                                if status == "ok":
                                    _track_and_append(f"    {rail_name}: {expected} ✅ OK")
                                elif status == "missing":
                                    _track_and_append(f"    {rail_name}: {expected} ❌ MISSING")
                                elif status == "low":
                                    _track_and_append(f"    {rail_name}: {expected} ⚠️ LOW")
                                else:
                                    _track_and_append(f"    {rail_name}: {expected} — measure this")
                            _track_and_append("")
                            _track_and_append("  Repair: Check each rail with multimeter on PMIC output.")
                            _track_and_append("  Missing voltage = trace back to PMIC regulator / inductor / capacitor.")

                        _track_and_append("")
                        _track_and_append("=" * 55)

                    else:
                        _track_and_append("")
                        _track_and_append("  ✅ No confirmed faults detected")

                    # ── POSSIBLE ISSUES (50-74% confidence) — "check kijiye"
                    if possible_faults:
                        seen_names = set()
                        has_possible_header = False
                        for fault in possible_faults:
                            name = fault.get("name", "")
                            if name in seen_names:
                                continue
                            seen_names.add(name)
                            if not has_possible_header:
                                _track_and_append("")
                                _track_and_append("  ── Isse bhi check kijiye ──")
                                has_possible_header = True
                            count = fault.get("repeat_count", 1)
                            count_str = f" (x{count})" if count > 1 else ""
                            _track_and_append(f"  ℹ️ {name}{count_str} — {fault.get('message', '')[:80]}")

                    # ── MATCHED FAULT PATTERNS from database (suggestions)
                    if matched_patterns and not known_fault:
                        _track_and_append("")
                        _track_and_append("  ── Database se match ──")
                        for mp in matched_patterns[:2]:
                            info = mp["info"]
                            _track_and_append(f"  ℹ️ {info['symptom'][:70]}")
                            top_cause = info.get("possible_causes", [{}])[0]
                            if top_cause:
                                _track_and_append(f"     Check: {top_cause.get('ic', '?')} — {top_cause.get('check', '')[:70]}")

                    # ── FULL DEVICE DATA ──
                    _track_and_append("")
                    _track_and_append("=" * 55)
                    _track_and_append("  FULL DEVICE DATA")
                    _track_and_append("=" * 55)

                    # ── Chipset & SoC ──
                    _track_and_append("")
                    _track_and_append("── Chipset / SoC ──")
                    _track_and_append(f"  Chipset: {uart_result.chipset or 'Unknown'}")
                    if r.get("chipset_db_match"):
                        _track_and_append(f"  DB Match: {r['chipset_db_match']}")
                    if r.get("chipset_marketing_name"):
                        _track_and_append(f"  Marketing Name: {r['chipset_marketing_name']}")
                    for k in ("qcom_chip_name", "qcom_chip_ver", "qcom_codename", "qcom_jtag_id",
                              "qcom_oem_id", "qcom_serial", "qcom_device_code",
                              "qcom_secure_boot", "qcom_vb_state",
                              "mtk_chip_code", "mtk_chip_name"):
                        if r.get(k):
                            label = k.replace("qcom_", "QC ").replace("mtk_", "MTK ").replace("_", " ").title()
                            _track_and_append(f"  {label}: {r[k]}")

                    # ── CPU ──
                    _track_and_append("")
                    _track_and_append("── CPU ──")
                    cpu_cores = _parsed.get("cpu_cores", "")
                    if cpu_cores:
                        _track_and_append(f"  Cores: {cpu_cores}")
                    if r.get("qcom_core_freq"):
                        _track_and_append(f"  Frequency: {r['qcom_core_freq']}")

                    # ── RAM / DDR ──
                    _track_and_append("")
                    _track_and_append("── RAM / DDR ──")
                    ram = _parsed.get("ram", "")
                    if ram:
                        _track_and_append(f"  Size: {ram}")
                    if _parsed.get("ram_type"):
                        _track_and_append(f"  Type: {_parsed['ram_type']}")
                    if _parsed.get("ram_freq"):
                        _track_and_append(f"  Frequency: {_parsed['ram_freq']}")
                    if _parsed.get("ram_manufacturer"):
                        _track_and_append(f"  Manufacturer: {_parsed['ram_manufacturer']}")
                    for k in ("qcom_ddr_ranks", "ddr_type_detected", "ddr_dsf_version",
                              "ddr_abort_reason", "ddr_abort_freq", "ddr_abort_channel"):
                        if r.get(k):
                            label = k.replace("qcom_", "").replace("ddr_", "DDR ").replace("_", " ").title()
                            _track_and_append(f"  {label}: {r[k]}")

                    # ── Storage ──
                    _track_and_append("")
                    _track_and_append("── Storage ──")
                    storage = _parsed.get("storage", "")
                    if storage:
                        _track_and_append(f"  Type: {storage}")
                    if _parsed.get("storage_type"):
                        _track_and_append(f"  Interface: {_parsed['storage_type']}")
                    if _parsed.get("storage_max_speed"):
                        _track_and_append(f"  Max Speed: {_parsed['storage_max_speed']}")
                    if r.get("qcom_ufs_id"):
                        _track_and_append(f"  UFS ID: {r['qcom_ufs_id']}")
                    if r.get("qcom_ufs_spec"):
                        _track_and_append(f"  UFS Spec: {r['qcom_ufs_spec']}")

                    # ── Battery & Power ──
                    _track_and_append("")
                    _track_and_append("── Battery & Power ──")
                    vbat = _parsed.get("battery_vbat", "")
                    if vbat:
                        _track_and_append(f"  VBAT: {vbat}")
                    if _parsed.get("battery_vchr"):
                        _track_and_append(f"  Charger Voltage: {_parsed['battery_vchr']}")
                    if r.get("qcom_ibat"):
                        _track_and_append(f"  Battery Current: {r['qcom_ibat']}")
                    if r.get("qcom_battery_id"):
                        _track_and_append(f"  Battery ID: {r['qcom_battery_id']}")

                    # ── PMIC ──
                    _track_and_append("")
                    _track_and_append("── PMIC ──")
                    pmic = _parsed.get("pmic_model", "")
                    if pmic:
                        _track_and_append(f"  Model: {pmic}")
                    rst = _parsed.get("pmic_reset_cause", "")
                    if rst:
                        _track_and_append(f"  Last Reset: {rst}")
                    pmic_regs = _parsed.get("pmic_registers", {})
                    if pmic_regs:
                        for reg_name, reg_val in pmic_regs.items():
                            _track_and_append(f"  {reg_name}: {reg_val}")

                    # ── Voltage Rails ──
                    voltages = _parsed.get("voltage_rails", {})
                    if voltages:
                        _track_and_append("")
                        _track_and_append("── Voltage Rails ──")
                        for rail, uv in voltages.items():
                            _track_and_append(f"  {rail}: {uv/1000:.1f}mV ({uv}uV)")

                    # ── Display ──
                    display = _parsed.get("qcom_display", "")
                    if display:
                        _track_and_append("")
                        _track_and_append("── Display ──")
                        _track_and_append(f"  Panel: {display}")
                        if _parsed.get("qcom_display_res"):
                            _track_and_append(f"  Resolution: {_parsed['qcom_display_res']}")

                    # ── Connectivity ──
                    has_conn = r.get("qcom_wifi") or r.get("qcom_bluetooth")
                    if has_conn:
                        _track_and_append("")
                        _track_and_append("── Connectivity ──")
                        if r.get("qcom_wifi"):
                            _track_and_append(f"  WiFi: {r['qcom_wifi']}")
                        if r.get("qcom_bluetooth"):
                            _track_and_append(f"  Bluetooth: {r['qcom_bluetooth']}")

                    # ── Boot Information ──
                    _track_and_append("")
                    _track_and_append("── Boot Information ──")
                    boot_reason = _parsed.get("boot_reason", "")
                    if boot_reason:
                        _track_and_append(f"  Boot Reason: {boot_reason}")
                    if _parsed.get("boot_reason_detail"):
                        _track_and_append(f"  Boot Detail: {_parsed['boot_reason_detail']}")
                    if _parsed.get("boot_mode"):
                        _track_and_append(f"  Boot Mode: {_parsed['boot_mode']}")
                    if _parsed.get("abnormal_boot"):
                        _track_and_append(f"  Abnormal Boot: {_parsed['abnormal_boot']}")
                    boot_stage = _parsed.get("boot_stage", "")
                    if boot_stage:
                        _track_and_append(f"  Boot Stage: {boot_stage}")
                    if _parsed.get("boot_stuck_stage"):
                        _track_and_append(f"  Boot Stuck At: {_parsed['boot_stuck_stage']}")
                    if _parsed.get("boot_stuck_reason"):
                        _track_and_append(f"  Stuck Cause: {_parsed['boot_stuck_reason']}")
                    if r.get("qcom_boot_time_ms"):
                        _track_and_append(f"  SBL Boot Time: {r['qcom_boot_time_ms']}")
                    if r.get("qcom_uefi_total"):
                        _track_and_append(f"  UEFI Boot Time: {r['qcom_uefi_total']}")

                    # ── Firmware Versions ──
                    has_fw = r.get("firmware_version") or _parsed.get("atf_version") or _parsed.get("trustzone_version")
                    if has_fw:
                        _track_and_append("")
                        _track_and_append("── Firmware ──")
                        if r.get("firmware_version"):
                            _track_and_append(f"  Version: {r['firmware_version']}")
                        if _parsed.get("atf_version"):
                            _track_and_append(f"  ATF/BL31: {_parsed['atf_version']}")
                        if _parsed.get("trustzone_version"):
                            _track_and_append(f"  TrustZone: {_parsed['trustzone_version']}")
                        if _parsed.get("spm_firmware"):
                            _track_and_append(f"  SPM: {_parsed['spm_firmware']}")
                        if _parsed.get("kernel_entry"):
                            _track_and_append(f"  Kernel Entry: {_parsed['kernel_entry']}")
                        if r.get("qcom_mbm_version"):
                            _track_and_append(f"  MBM Version: {r['qcom_mbm_version']}")

                    # ── I2C Bus Errors ──
                    i2c_keys = sorted(k for k in _parsed if k.startswith("i2c_error"))
                    if i2c_keys:
                        _track_and_append("")
                        _track_and_append("── I2C Bus Errors ──")
                        for key in i2c_keys:
                            _track_and_append(f"  {_parsed[key]}")

                    # ── IC Probes ──
                    ic_probes = _parsed.get("ic_probes_failed", [])
                    if ic_probes:
                        _track_and_append("")
                        _track_and_append("── IC Probes Failed ──")
                        for probe in ic_probes:
                            _track_and_append(f"  ⚪ {probe}")

                    # ── Companion ICs from Database ──
                    companion = _parsed.get("companion_ics", {})
                    if companion:
                        _track_and_append("")
                        _track_and_append("── Board ICs (from DB) ──")
                        for ic_name, ic_info in companion.items():
                            if isinstance(ic_info, dict):
                                addr = ic_info.get("i2c_address", "")
                                func = ic_info.get("function", "")
                                _track_and_append(f"  {ic_name}: {func} (I2C: {addr})" if addr else f"  {ic_name}: {func}")
                            else:
                                _track_and_append(f"  {ic_name}")

                    # ── Live Dmesg Data ──
                    dmesg = _parsed.get("dmesg_data", {})
                    if dmesg:
                        _track_and_append("")
                        _track_and_append("── Live Dmesg Data ──")
                        for dk, dv in dmesg.items():
                            label = dk.replace("_", " ").title()
                            _track_and_append(f"  {label}: {dv}")

                    # ── All Other Parsed Fields ──
                    shown_keys = {
                        "chipset", "chipset_detail", "brand", "boot_registers", "boot_stage",
                        "version", "ram", "storage", "board_name", "ram_type", "ram_freq",
                        "ram_manufacturer", "cpu_cores", "atf_version", "trustzone_version",
                        "spm_firmware", "boot_mode", "abnormal_boot", "boot_reason",
                        "kernel_entry", "mtk_chip_code", "mtk_chip_name", "pmic_model",
                        "pmic_reset_cause", "boot_reason_detail", "storage_type",
                        "storage_max_speed", "battery_vbat", "battery_vchr",
                        "boot_stuck_stage", "boot_stuck_reason", "boot_stuck",
                        "qcom_chip_name", "qcom_chip_ver", "qcom_codename", "qcom_jtag_id",
                        "qcom_core_freq", "qcom_ufs_id", "qcom_ufs_spec", "qcom_ddr_ranks",
                        "qcom_ibat", "qcom_battery_id", "qcom_display", "qcom_display_res",
                        "qcom_wifi", "qcom_bluetooth", "qcom_vb_state", "qcom_secure_boot",
                        "qcom_serial", "qcom_device_code", "qcom_uefi_total",
                        "qcom_boot_time_ms", "qcom_mbm_version", "qcom_oem_id", "qcom_product_name",
                        "ddr_type_detected", "ddr_dsf_version",
                        "ddr_abort_reason", "ddr_abort_freq", "ddr_abort_channel",
                        "voltage_rails", "pmic_registers", "ic_probes_failed",
                        "companion_ics", "dmesg_data", "faults_detected",
                        "known_fault_info", "correlated_faults", "matched_fault_patterns",
                        "chipset_db_match", "chipset_marketing_name", "data_received",
                    }
                    extra = {k: v for k, v in _parsed.items()
                             if k not in shown_keys and not k.startswith("i2c_error") and v}
                    if extra:
                        _track_and_append("")
                        _track_and_append("── Additional Data ──")
                        for ek, ev in extra.items():
                            label = ek.replace("_", " ").title()
                            if isinstance(ev, (list, dict)):
                                _track_and_append(f"  {label}: {json.dumps(ev, default=str)}")
                            else:
                                _track_and_append(f"  {label}: {ev}")

                    # ── Phone Database Lookup ──
                    _brand = uart_result.brand or ""
                    _chip = db_match or uart_result.chipset or ""
                    _codename = r.get("qcom_product_name", "") or _parsed.get("qcom_product_name", "")
                    _db_hit = _lookup_phone_db(brand=_brand, chipset=_chip, codename_hint=_codename)
                    if _db_hit:
                        for line in _format_phone_db_section(*_db_hit):
                            _track_and_append(line)

            except Exception as e:
                _track_and_append(f"  ❌ Detection Error: {str(e)}")

            _safe_after(lambda: progress.set(0.75))

            _safe_after(lambda: progress.set(0.90))

            # ═══ ADDITIONAL FAULT ANALYSIS ═══
            faults_count = 0
            faults_summary_text = ""
            healthy_list = []

            if uart_result and uart_result.detected:
                try:
                    from app.hardware.fault_analyzer import analyze_uart_result
                    report = analyze_uart_result(uart_result)

                    faults_count = len(report.faults)
                    if report.faults:
                        fault_names = [f"{f.component}: {f.problem}" for f in report.faults]
                        faults_summary_text = "; ".join(fault_names[:5])

                    if report.healthy_components:
                        healthy_list = report.healthy_components

                except Exception:
                    pass

            # Footer
            _track_and_append("")
            _track_and_append("=" * 70)
            _track_and_append("  Report generated by Mooxy AI Fault Detector v1.0")
            _track_and_append("=" * 70)

            report_text = "\n".join(full_report["lines"])

            # ── Final UI updates ──
            _safe_after(lambda: progress.set(1.0))
            _safe_after(lambda: msg_label.configure(
                text="Detection complete — full report above", text_color=colors["success"]))

            if uart_result and uart_result.detected:
                r = uart_result.raw_responses
                def _update_summary():
                    summary_label.configure(
                        text=f"✅ {uart_result.chipset} | CPU: {r.get('cpu_cores', '?')} cores | RAM: {r.get('ram_type', '?')} {r.get('ram_freq', '')} | {r.get('data_received', '')}",
                        text_color=colors["success"])
                _safe_after(_update_summary)
            else:
                _safe_after(lambda: summary_label.configure(
                    text="⚠️ Limited data — check report", text_color=colors["warning"]))

            # ── Auto-save to file ──
            from app.gui.history_manager import get_unique_log_path
            log_path = get_unique_log_path("boot_log")
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
            except Exception:
                pass

            # ── Save raw boot log (for AI analysis) ──
            # raw_data is now a hex string — save as binary for proper analysis
            raw_log_path = None
            if uart_result and uart_result.raw_data:
                raw_log_path = get_unique_log_path("raw_boot")
                try:
                    with open(raw_log_path, "wb") as f:
                        f.write(bytes.fromhex(uart_result.raw_data))
                except Exception:
                    raw_log_path = None

            # ── Save to history ──
            try:
                from app.gui.history_manager import add_detection

                device_name = "Unknown Device"
                summary_text = "Scan completed"
                if uart_result and uart_result.detected:
                    device_name = f"{uart_result.brand} ({uart_result.chipset})"
                    summary_text = f"Chipset: {uart_result.chipset} | Brand: {uart_result.brand} | Confidence: {uart_result.confidence:.0%}"

                add_detection(
                    detection_type="UART",
                    device_name=device_name,
                    summary=summary_text,
                    faults_count=faults_count,
                    faults_summary=faults_summary_text,
                    report_file=str(log_path),
                    extra={
                        "port": port,
                        "baud": baud,
                        "duration": duration,
                        "healthy_components": healthy_list,
                        "raw_log_file": str(raw_log_path) if raw_log_path else "",
                    }
                )
            except Exception as e:
                print(f"[HW Detect] History save error: {e}")

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

                _safe_after(lambda: _append_live_lines(lines))()
                if last_scan.get("report"):
                    last_scan["report"]["lines"].extend(lines)
                _safe_after(lambda: msg_label.configure(
                    text="🧠 AI diagnosis added to report.",
                    text_color=colors["success"]))()
            except Exception as e:
                _safe_after(lambda: msg_label.configure(
                    text=f"⚠️ AI error: {e}", text_color=colors["warning"]))()

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
