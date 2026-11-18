import customtkinter as ctk
import threading


def render_storage_test(app):
    """Storage & RAM Testing page — UFS/eMMC health, RAM type detection, SMART data, capacity analysis.
    Shows detections LIVE as they happen — real-time append with color-coded output."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="💾 Storage & RAM Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="UFS/eMMC storage health, RAM type detection, SMART data, capacity analysis",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card: What storage & RAM testing detects ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="🔍 Storage & RAM Testing Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ Storage Type — UFS 3.1/4.0 or eMMC 5.1 identification",
        "✅ Storage Health — Life time estimation, Pre-EOL info, wear analysis",
        "✅ Storage Info — Manufacturer, model, firmware, capacity, usage",
        "✅ RAM Type — LPDDR4X/LPDDR5/LPDDR5X detection",
        "✅ RAM Info — Total/available memory, manufacturer, frequency",
        "✅ Partitions — Disk usage per partition",
        "✅ IC Database — Samsung, SK Hynix, Micron, Kioxia flash ICs",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Overall Storage Health Badge ──
    badge_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=55)
    badge_frame.pack(fill="x", padx=20, pady=(0, 10))
    badge_frame.pack_propagate(False)
    badge_inner = ctk.CTkFrame(badge_frame, fg_color="transparent")
    badge_inner.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(badge_inner, text="Overall Storage Health:",
                 font=("Segoe UI", 14, "bold"), text_color=colors["text"]).pack(side="left")
    health_badge = ctk.CTkLabel(badge_inner, text="  ⏸ Not Tested",
                                 font=("Segoe UI", 14, "bold"), text_color=colors["text_dim"])
    health_badge.pack(side="left", padx=(10, 0))

    # ── Progress bar + message ──
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 10))

    # ── Buttons row ──
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    # ── Result cards container ──
    cards_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    cards_frame.pack(fill="x", padx=20, pady=(0, 10))

    # Two-column layout for result cards
    cards_left = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_left.pack(side="left", fill="both", expand=True, padx=(0, 5))
    cards_right = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_right.pack(side="left", fill="both", expand=True, padx=(5, 0))

    # ── Storage Info card (LEFT) ──
    stor_info_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    stor_info_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(stor_info_card, text="💾 Storage Info",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    stor_info_fields = [
        ("stor_type", "Storage Type"),
        ("stor_manufacturer", "Manufacturer"),
        ("stor_model", "Model"),
        ("stor_firmware", "Firmware"),
        ("stor_capacity", "Total Capacity"),
        ("stor_used", "Used Space"),
        ("stor_free", "Free Space"),
        ("stor_usage_pct", "Usage %"),
    ]
    stor_info_labels = {}
    for key, name in stor_info_fields:
        row = ctk.CTkFrame(stor_info_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=130, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        stor_info_labels[key] = (val, dot)
    ctk.CTkFrame(stor_info_card, fg_color="transparent", height=8).pack()

    # ── Storage Health card (LEFT) ──
    stor_health_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    stor_health_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(stor_health_card, text="🏥 Storage Health",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    stor_health_fields = [
        ("stor_life_a", "Life Time Est. A"),
        ("stor_life_b", "Life Time Est. B"),
        ("stor_pre_eol", "Pre-EOL Info"),
        ("stor_health_status", "Health Status"),
    ]
    stor_health_labels = {}
    for key, name in stor_health_fields:
        row = ctk.CTkFrame(stor_health_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        stor_health_labels[key] = (val, dot)
    ctk.CTkFrame(stor_health_card, fg_color="transparent", height=8).pack()

    # ── RAM Info card (RIGHT) ──
    ram_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    ram_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(ram_card, text="🧠 RAM Info",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    ram_fields = [
        ("ram_type", "RAM Type"),
        ("ram_total", "Total RAM"),
        ("ram_available", "Available"),
        ("ram_manufacturer", "Manufacturer"),
        ("ram_frequency", "Frequency"),
        ("ram_status", "Status"),
    ]
    ram_labels = {}
    for key, name in ram_fields:
        row = ctk.CTkFrame(ram_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=130, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        ram_labels[key] = (val, dot)
    ctk.CTkFrame(ram_card, fg_color="transparent", height=8).pack()

    # ── Partition Usage card (RIGHT) — textbox showing partition list ──
    part_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    part_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(part_card, text="📊 Partition Usage",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    part_textbox = ctk.CTkTextbox(part_card, fg_color=colors["bg_light"],
                                   text_color=colors["text"], font=("Consolas", 10),
                                   height=160, wrap="none", border_width=0)
    part_textbox.pack(fill="x", padx=12, pady=(0, 5))
    part_textbox.insert("1.0", "  No partition data yet — run detection first.")
    part_textbox.configure(state="disabled")
    ctk.CTkFrame(part_card, fg_color="transparent", height=8).pack()

    # ── Color tags setup ──
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#34d399")
        tb.tag_configure("warning", foreground="#fbbf24")
        tb.tag_configure("fault", foreground="#ec4899")
        tb.tag_configure("info", foreground="#a855f7")
        tb.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#9a93b5")

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "🔴", "critical", "danger", "❌", "[xx]", "fail", "bad", "exceeded"]):
            return "fault"
        if any(k in t for k in ["warning", "🟡", "⚠️", "[!!]", "degraded", "worn", "urgent"]):
            return "warning"
        if any(k in t for k in ["✅", "[ok]", "ok", "pass", "working", "healthy", "good", "normal"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "========", "STORAGE", "REPORT", "PHASE"]):
            return "header"
        if any(k in t for k in ["🔍", "scanning", "detecting", "reading", "checking", "querying"]):
            return "info"
        return None

    # ── Live append helpers ──
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

    # ── Field update helper ──
    def _set_field(labels_dict, key, value, ok=True):
        """Update a result field value and status dot."""
        if key in labels_dict:
            v, d = labels_dict[key]
            app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
            color = colors["success"] if ok else colors["warning"]
            app.content.after(0, lambda: d.configure(text_color=color))

    # ── Storage health evaluation helpers ──
    def _life_time_to_pct(val):
        """Convert UFS/eMMC life_time_estimation hex string to usage percentage.
        0x01=0-10%, 0x02=10-20%, ..., 0x0A=90-100%, 0x0B=exceeded."""
        try:
            s = str(val).strip().lower()
            if s.startswith("0x"):
                n = int(s, 16)
            else:
                n = int(s)
            if n == 0:
                return 0, "Unused"
            if 1 <= n <= 10:
                pct = n * 10
                return pct, f"{(n-1)*10}-{pct}% used"
            if n == 11:
                return 110, "Exceeded lifespan"
            return n, f"Unknown (0x{n:02X})"
        except (ValueError, TypeError):
            return -1, str(val)

    def _is_life_ok(val):
        """Return True if life_time value indicates healthy storage (<=70% used)."""
        pct, _ = _life_time_to_pct(val)
        return 0 <= pct <= 70

    def _pre_eol_str(val):
        """Convert pre_eol_info value to human-readable string."""
        try:
            s = str(val).strip().lower()
            if s.startswith("0x"):
                n = int(s, 16)
            else:
                n = int(s)
            if n == 0x01:
                return "Normal", True
            if n == 0x02:
                return "Warning (80% lifetime used)", False
            if n == 0x03:
                return "Urgent (90%+ lifetime used)", False
            return f"Unknown (0x{n:02X})", False
        except (ValueError, TypeError):
            s = str(val).strip().upper()
            if s in ("NORMAL", "OK", "GOOD"):
                return s, True
            if s in ("WARNING", "URGENT", "CRITICAL"):
                return s, False
            return str(val), True

    def _is_usage_ok(pct):
        """Return True if disk usage percentage is below 90%."""
        try:
            p = float(str(pct).replace("%", "").strip())
            return p < 90.0
        except (ValueError, TypeError):
            return True

    # ── Start detection ──
    def start_detection():
        if running["value"]:
            return
        running["value"] = True

        # Reset UI
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        progress.set(0)
        health_badge.configure(text="  🔄 Testing...", text_color=colors["info"])
        msg_label.configure(text="Initializing storage & RAM detection...", text_color=colors["text_dim"])

        # Reset all field labels
        for labels_dict in [stor_info_labels, stor_health_labels, ram_labels]:
            for key, (v, d) in labels_dict.items():
                v.configure(text="—", text_color=colors["text_dim"])
                d.configure(text_color=colors["text_dim"])

        # Reset partition textbox
        part_textbox.configure(state="normal")
        part_textbox.delete("1.0", "end")
        part_textbox.insert("1.0", "  Scanning partitions...")
        part_textbox.configure(state="disabled")

        full_report = {"lines": []}

        def _track(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_lines(lines):
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            import datetime as _dt

            # ── Report Header ──
            header = [
                "=" * 70,
                "  MOOXY AI FAULT DETECTOR — STORAGE & RAM TEST REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70,
                "",
            ]
            _track_lines(header)

            result = None
            try:
                from app.hardware.storage_tester import detect_storage_status

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct / 100.0 if pct > 1 else pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                _track("🔍 Scanning storage & RAM subsystem...")
                _track("")

                result = detect_storage_status(callback=cb)

                # ═══ PHASE 1: STORAGE DETECTION ═══
                _track("")
                _track("═══ PHASE 1: STORAGE DETECTION ═══")
                _track("")

                stor = getattr(result, "storage", None) or {}
                if isinstance(stor, dict) and stor:
                    s_type = stor.get("storage_type", "Unknown")
                    s_mfg = stor.get("manufacturer", "Unknown")
                    s_model = stor.get("model", "Unknown")
                    s_fw = stor.get("firmware_version", "Unknown")
                    s_cap = stor.get("total_capacity", "Unknown")
                    s_used = stor.get("used_space", "Unknown")
                    s_free = stor.get("free_space", "Unknown")
                    s_pct = stor.get("usage_percent", "Unknown")

                    _track(f"  Storage Type:     {s_type}")
                    _track(f"  Manufacturer:     {s_mfg}")
                    _track(f"  Model:            {s_model}")
                    _track(f"  Firmware:         {s_fw}")
                    _track(f"  Total Capacity:   {s_cap}")
                    _track(f"  Used Space:       {s_used}")
                    _track(f"  Free Space:       {s_free}")
                    _track(f"  Usage:            {s_pct}")

                    is_ufs = "ufs" in str(s_type).lower()
                    type_icon = "✅" if is_ufs else "✅"
                    _track(f"  {type_icon} Detected: {s_type}")

                    _set_field(stor_info_labels, "stor_type", s_type)
                    _set_field(stor_info_labels, "stor_manufacturer", s_mfg)
                    _set_field(stor_info_labels, "stor_model", s_model)
                    _set_field(stor_info_labels, "stor_firmware", s_fw)
                    _set_field(stor_info_labels, "stor_capacity", s_cap)
                    _set_field(stor_info_labels, "stor_used", s_used)
                    _set_field(stor_info_labels, "stor_free", s_free)
                    _set_field(stor_info_labels, "stor_usage_pct", s_pct,
                               ok=_is_usage_ok(s_pct))
                else:
                    _track("  ⚠️ Storage info not available")

                app.content.after(0, lambda: progress.set(0.25))

                # ═══ PHASE 2: STORAGE HEALTH ═══
                _track("")
                _track("═══ PHASE 2: STORAGE HEALTH ═══")
                _track("")

                if isinstance(stor, dict) and stor:
                    life_a = stor.get("life_time_a", "Unknown")
                    life_b = stor.get("life_time_b", "Unknown")
                    pre_eol = stor.get("pre_eol_info", "Unknown")
                    h_status = stor.get("health_status", "Unknown")

                    pct_a, desc_a = _life_time_to_pct(life_a)
                    pct_b, desc_b = _life_time_to_pct(life_b)
                    eol_str, eol_ok = _pre_eol_str(pre_eol)

                    _track(f"  Life Time Est. A: {life_a} ({desc_a})")
                    _track(f"  Life Time Est. B: {life_b} ({desc_b})")
                    _track(f"  Pre-EOL Info:     {pre_eol} ({eol_str})")
                    _track(f"  Health Status:    {h_status}")

                    # Evaluate overall storage health
                    a_ok = _is_life_ok(life_a)
                    b_ok = _is_life_ok(life_b)

                    if a_ok and b_ok and eol_ok:
                        _track("")
                        _track("  ✅ Storage health is GOOD")
                    elif not eol_ok or pct_a >= 110 or pct_b >= 110:
                        _track("")
                        _track("  🔴 Storage health is CRITICAL — replacement recommended")
                    else:
                        _track("")
                        _track("  🟡 Storage health is DEGRADED — monitor closely")

                    _set_field(stor_health_labels, "stor_life_a", f"{life_a} ({desc_a})",
                               ok=a_ok)
                    _set_field(stor_health_labels, "stor_life_b", f"{life_b} ({desc_b})",
                               ok=b_ok)
                    _set_field(stor_health_labels, "stor_pre_eol", f"{pre_eol} ({eol_str})",
                               ok=eol_ok)

                    status_ok = str(h_status).lower() in ("good", "healthy", "ok", "normal")
                    _set_field(stor_health_labels, "stor_health_status", h_status,
                               ok=status_ok)
                else:
                    _track("  ⚠️ Storage health data not available")

                app.content.after(0, lambda: progress.set(0.50))

                # ═══ PHASE 3: RAM DETECTION ═══
                _track("")
                _track("═══ PHASE 3: RAM DETECTION ═══")
                _track("")

                ram = getattr(result, "ram", None) or {}
                if isinstance(ram, dict) and ram:
                    r_type = ram.get("ram_type", "Unknown")
                    r_total = ram.get("total_ram", "Unknown")
                    r_avail = ram.get("available_ram", "Unknown")
                    r_mfg = ram.get("manufacturer", "Unknown")
                    r_freq = ram.get("frequency", "Unknown")
                    r_status = ram.get("status", "Unknown")

                    _track(f"  RAM Type:       {r_type}")
                    _track(f"  Total RAM:      {r_total}")
                    _track(f"  Available:      {r_avail}")
                    _track(f"  Manufacturer:   {r_mfg}")
                    _track(f"  Frequency:      {r_freq}")
                    _track(f"  Status:         {r_status}")

                    is_lpddr5 = "lpddr5" in str(r_type).lower()
                    if is_lpddr5:
                        _track(f"  ✅ High-speed RAM detected: {r_type}")
                    else:
                        _track(f"  ✅ RAM detected: {r_type}")

                    ram_status_ok = str(r_status).lower() in ("ok", "good", "normal", "healthy", "working")
                    _set_field(ram_labels, "ram_type", r_type)
                    _set_field(ram_labels, "ram_total", r_total)
                    _set_field(ram_labels, "ram_available", r_avail)
                    _set_field(ram_labels, "ram_manufacturer", r_mfg)
                    _set_field(ram_labels, "ram_frequency", r_freq)
                    _set_field(ram_labels, "ram_status", r_status, ok=ram_status_ok)
                else:
                    _track("  ⚠️ RAM info not available")

                app.content.after(0, lambda: progress.set(0.75))

                # ═══ PHASE 4: PARTITION USAGE ═══
                _track("")
                _track("═══ PHASE 4: PARTITION USAGE ═══")
                _track("")

                partitions = []
                if isinstance(stor, dict):
                    partitions = stor.get("partitions", []) or []

                if partitions and isinstance(partitions, list):
                    _track(f"  {'Mount':<20} {'Size':<10} {'Used':<10} {'Avail':<10} {'Use%':<8}")
                    _track(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")

                    part_lines = []
                    part_lines.append(f"  {'Mount':<20} {'Size':<10} {'Used':<10} {'Avail':<10} {'Use%':<8}")
                    part_lines.append(f"  {'─'*20} {'─'*10} {'─'*10} {'─'*10} {'─'*8}")

                    for p in partitions:
                        if isinstance(p, dict):
                            mp = p.get("mount_point", "?")
                            sz = p.get("size", "?")
                            us = p.get("used", "?")
                            av = p.get("available", "?")
                            up = p.get("use_percent", "?")
                            line = f"  {str(mp):<20} {str(sz):<10} {str(us):<10} {str(av):<10} {str(up):<8}"
                            _track(line)
                            part_lines.append(line)

                    _track(f"  Total partitions: {len(partitions)}")

                    # Update partition textbox
                    def _update_part():
                        part_textbox.configure(state="normal")
                        part_textbox.delete("1.0", "end")
                        part_textbox.insert("1.0", "\n".join(part_lines))
                        part_textbox.configure(state="disabled")
                    app.content.after(0, _update_part)
                else:
                    _track("  ⚠️ No partition data available")
                    def _update_part_empty():
                        part_textbox.configure(state="normal")
                        part_textbox.delete("1.0", "end")
                        part_textbox.insert("1.0", "  No partition data available.")
                        part_textbox.configure(state="disabled")
                    app.content.after(0, _update_part_empty)

                app.content.after(0, lambda: progress.set(0.90))

                # ═══ OVERALL VERDICT ═══
                _track("")
                _track("═══ OVERALL STORAGE & RAM VERDICT ═══")
                _track("")

                overall = getattr(result, "overall_health", None) or "Unknown"
                score = getattr(result, "health_score", 0)
                overall_str = str(overall).upper()

                _track(f"  Health Score: {score}/100")

                warnings = getattr(result, "warnings", []) or []
                if warnings:
                    _track("")
                    _track("  ⚠️ Warnings:")
                    for w in warnings:
                        _track(f"    • {w}")

                if overall_str in ("GOOD", "HEALTHY", "OK", "NORMAL"):
                    _track("")
                    _track(f"  ✅ OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  ✅ {overall_str} ({score}/100)", text_color=colors["success"]))
                elif overall_str in ("DEGRADED", "FAIR", "WORN"):
                    _track("")
                    _track(f"  🟡 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  🟡 {overall_str} ({score}/100)", text_color=colors["warning"]))
                elif overall_str in ("POOR", "BAD", "CRITICAL", "REPLACE"):
                    _track("")
                    _track(f"  🔴 OVERALL: {overall_str} — Storage replacement needed")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  🔴 {overall_str} ({score}/100)", text_color=colors["accent"]))
                else:
                    _track(f"  ⚠️ OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  ⚠️ {overall_str}", text_color=colors["text_dim"]))

            except ImportError:
                _track("  ❌ Storage tester module not found")
                _track("  Install: app/hardware/storage_tester.py required")
                app.content.after(0, lambda: health_badge.configure(
                    text="  ❌ Module Error", text_color=colors["accent"]))
            except Exception as e:
                _track(f"  ❌ Storage detection error: {str(e)}")
                app.content.after(0, lambda: health_badge.configure(
                    text="  ❌ Error", text_color=colors["accent"]))

            # ── Footer ──
            _track("")
            _track("=" * 70)
            _track("  Report generated by Mooxy AI Fault Detector v1.0")
            _track("=" * 70)

            report_text = "\n".join(full_report["lines"])

            # Final UI updates
            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Storage & RAM test complete — full report above", text_color=colors["success"]))

            # Auto-save to file
            try:
                from app.gui.history_manager import get_unique_log_path
                log_path = get_unique_log_path("storage_report")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
            except Exception:
                log_path = None

            # Save to history
            try:
                from app.gui.history_manager import add_detection

                device_name = "Storage & RAM Test"
                summary_text = "Storage & RAM diagnostics completed"
                faults_count = 0
                faults_summary = ""

                if result:
                    overall_h = str(getattr(result, "overall_health", "Unknown"))
                    stor_d = getattr(result, "storage", {}) or {}
                    ram_d = getattr(result, "ram", {}) or {}
                    if isinstance(stor_d, dict):
                        s_type_v = stor_d.get("storage_type", "?")
                        s_cap_v = stor_d.get("total_capacity", "?")
                    else:
                        s_type_v = "?"
                        s_cap_v = "?"
                    if isinstance(ram_d, dict):
                        r_type_v = ram_d.get("ram_type", "?")
                        r_total_v = ram_d.get("total_ram", "?")
                    else:
                        r_type_v = "?"
                        r_total_v = "?"

                    device_name = f"Storage ({s_type_v} / {r_type_v})"
                    summary_text = (
                        f"Health: {overall_h} | "
                        f"Storage: {s_type_v} {s_cap_v} | "
                        f"RAM: {r_type_v} {r_total_v}"
                    )

                    warn_list = getattr(result, "warnings", []) or []
                    if overall_h.upper() in ("POOR", "BAD", "CRITICAL", "REPLACE"):
                        faults_count = 1
                        faults_summary = "Storage replacement recommended"
                    elif warn_list:
                        faults_count = len(warn_list)
                        faults_summary = "; ".join(warn_list[:3])

                add_detection(
                    detection_type="STORAGE",
                    device_name=device_name,
                    summary=summary_text,
                    faults_count=faults_count,
                    faults_summary=faults_summary,
                    report_file=str(log_path) if log_path else "",
                    extra={
                        "overall_health": str(getattr(result, "overall_health", "Unknown")) if result else "Unknown",
                        "health_score": getattr(result, "health_score", 0) if result else 0,
                    }
                )
            except Exception as e:
                print(f"[Storage Test] History save error: {e}")

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    # ── Copy / Save buttons ──
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
                                                 initialfile="storage_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="💾 Start Storage Detection", width=300, height=46,
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

    # ── Report textbox ──
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=500, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0",
                      "Press 'Start Storage Detection' to begin.\n\n"
                      "Requirements:\n"
                      "• Device connected via USB with ADB enabled\n"
                      "• OR device in EDL/UART mode for raw storage data\n\n"
                      "Tests performed:\n"
                      "  1. Storage type detection (UFS 3.1/4.0 or eMMC 5.1)\n"
                      "  2. Storage health (life time estimation, Pre-EOL, wear)\n"
                      "  3. Storage info (manufacturer, model, firmware, capacity)\n"
                      "  4. RAM detection (LPDDR4X/LPDDR5/LPDDR5X, frequency)\n"
                      "  5. Partition usage analysis (per-partition disk usage)\n"
                      "  6. IC database matching (Samsung, SK Hynix, Micron, Kioxia)\n")
    _setup_tags()

    app.update_status("Storage & RAM Test — Connect device and press Start")
