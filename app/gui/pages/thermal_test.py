import customtkinter as ctk
import threading


def render_thermal_test(app):
    """Thermal Management Testing page — temperature monitoring, throttling detection,
    thermal zones, cooling device analysis. Shows detections LIVE with color-coded output."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="\U0001f321\ufe0f Thermal Management Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Temperature monitoring, throttling detection, thermal zones, cooling device analysis",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="\U0001f50d Thermal Testing Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "\u2705 CPU Temperature \u2014 Per-core temperature readings, throttle detection",
        "\u2705 GPU Temperature \u2014 Graphics processor thermal state",
        "\u2705 Battery Temperature \u2014 Battery thermal safety check",
        "\u2705 Skin Temperature \u2014 External device temperature",
        "\u2705 Thermal Zones \u2014 All thermal zone enumeration with trip points",
        "\u2705 Throttling \u2014 CPU frequency throttle %, cooling device state",
        "\u2705 Sensor ICs \u2014 TI TMP, STMicro STTS, Maxim, NXP thermal sensors",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Overall Health Badge ──
    badge_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=55)
    badge_frame.pack(fill="x", padx=20, pady=(0, 10))
    badge_frame.pack_propagate(False)
    badge_inner = ctk.CTkFrame(badge_frame, fg_color="transparent")
    badge_inner.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(badge_inner, text="Overall Thermal Health:",
                 font=("Segoe UI", 14, "bold"), text_color=colors["text"]).pack(side="left")
    health_badge = ctk.CTkLabel(badge_inner, text="  \u23f8 Not Tested",
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

    # ── Result cards container (2 columns) ──
    cards_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    cards_frame.pack(fill="x", padx=20, pady=(0, 10))

    cards_left = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_left.pack(side="left", fill="both", expand=True, padx=(0, 5))
    cards_right = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_right.pack(side="left", fill="both", expand=True, padx=(5, 0))

    # ── LEFT COLUMN ──

    # ── Temperature Overview card ──
    temp_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    temp_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(temp_card, text="\U0001f321\ufe0f Temperature Overview",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    temp_fields = [
        ("temp_cpu", "CPU Temp"),
        ("temp_gpu", "GPU Temp"),
        ("temp_battery", "Battery Temp"),
        ("temp_skin", "Skin Temp"),
        ("temp_max", "Max Temp"),
        ("temp_hottest_zone", "Hottest Zone"),
    ]
    temp_labels = {}
    for key, name in temp_fields:
        row = ctk.CTkFrame(temp_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        temp_labels[key] = (val, dot)
    ctk.CTkFrame(temp_card, fg_color="transparent", height=8).pack()

    # ── CPU Throttling card ──
    throttle_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    throttle_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(throttle_card, text="\u26a1 CPU Throttling",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    throttle_fields = [
        ("throttle_active", "Throttling Active"),
        ("throttle_severity", "Severity"),
        ("cpu_max_freq", "Max Frequency"),
        ("cpu_cur_freq", "Current Frequency"),
        ("throttle_pct", "Throttle %"),
    ]
    throttle_labels = {}
    for key, name in throttle_fields:
        row = ctk.CTkFrame(throttle_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=140, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        throttle_labels[key] = (val, dot)
    ctk.CTkFrame(throttle_card, fg_color="transparent", height=8).pack()

    # ── RIGHT COLUMN ──

    # ── Thermal Zones card (textbox) ──
    zones_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    zones_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(zones_card, text="\U0001f5fa\ufe0f Thermal Zones",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    zones_textbox = ctk.CTkTextbox(zones_card, fg_color=colors["bg_light"],
                                    text_color=colors["text"], font=("Consolas", 10),
                                    height=160, wrap="none", border_width=0)
    zones_textbox.pack(fill="x", padx=12, pady=(0, 4))
    zones_textbox.insert("1.0", "  No thermal zones detected yet.\n  Run detection to enumerate zones.")
    zones_textbox.configure(state="disabled")

    def _setup_zones_tags():
        tb = zones_textbox._textbox
        tb.tag_configure("temp_ok", foreground="#2ed573")
        tb.tag_configure("temp_warm", foreground="#ffa502")
        tb.tag_configure("temp_hot", foreground="#ff6348")
        tb.tag_configure("temp_critical", foreground="#e94560")
        tb.tag_configure("zone_header", foreground="#1e90ff", font=("Consolas", 10, "bold"))

    _setup_zones_tags()
    ctk.CTkFrame(zones_card, fg_color="transparent", height=8).pack()

    # ── Cooling Devices card ──
    cool_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    cool_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(cool_card, text="\u2744\ufe0f Cooling Devices",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    cool_fields = [
        ("cool_device_count", "Total Devices"),
        ("cool_active_count", "Active Devices"),
        ("cool_max_state", "Max Cool State"),
    ]
    cool_labels = {}
    for key, name in cool_fields:
        row = ctk.CTkFrame(cool_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        cool_labels[key] = (val, dot)
    ctk.CTkFrame(cool_card, fg_color="transparent", height=8).pack()

    # ── Color tags for report textbox ──
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#2ed573")
        tb.tag_configure("warning", foreground="#ffa502")
        tb.tag_configure("fault", foreground="#e94560")
        tb.tag_configure("info", foreground="#1e90ff")
        tb.tag_configure("header", foreground="#e94560", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#8892b0")

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "\U0001f534", "critical", "danger", "\u274c", "[xx]", "fail", "overheat", "> 60"]):
            return "fault"
        if any(k in t for k in ["warning", "\U0001f7e1", "\u26a0\ufe0f", "[!!]", "throttl", "hot", "warm"]):
            return "warning"
        if any(k in t for k in ["\u2705", "[ok]", "ok", "pass", "normal", "cool", "safe"]):
            return "ok"
        if any(k in t for k in ["\u2550\u2550\u2550", "===", "\u2500\u2500\u2500", "========", "THERMAL", "REPORT", "PHASE"]):
            return "header"
        if any(k in t for k in ["\U0001f50d", "scanning", "detecting", "reading", "checking", "enumerating", "monitoring"]):
            return "info"
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

    def _set_field(labels_dict, key, value, ok=True):
        if key in labels_dict:
            v, d = labels_dict[key]
            app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
            color = colors["success"] if ok else colors["warning"]
            app.content.after(0, lambda: d.configure(text_color=color))

    def _temp_color(temp_c):
        """Return a color string based on temperature thresholds."""
        try:
            t = float(temp_c)
        except (ValueError, TypeError):
            return colors["text_dim"]
        if t < 40.0:
            return "#2ed573"   # green  — ok
        elif t < 50.0:
            return "#ffa502"   # yellow — warm
        elif t < 60.0:
            return "#ff6348"   # orange — hot
        else:
            return "#e94560"   # red    — critical

    def _temp_ok(temp_c):
        """Return True if temperature is within safe range (< 50 C)."""
        try:
            return float(temp_c) < 50.0
        except (ValueError, TypeError):
            return True

    def _temp_tag(temp_c):
        """Return zones_textbox tag name for a temperature value."""
        try:
            t = float(temp_c)
        except (ValueError, TypeError):
            return None
        if t < 40.0:
            return "temp_ok"
        elif t < 50.0:
            return "temp_warm"
        elif t < 60.0:
            return "temp_hot"
        else:
            return "temp_critical"

    def _temp_status_label(temp_c):
        """Return a human-readable status for a temperature."""
        try:
            t = float(temp_c)
        except (ValueError, TypeError):
            return "Unknown"
        if t < 40.0:
            return "OK"
        elif t < 50.0:
            return "Warm"
        elif t < 60.0:
            return "Hot"
        else:
            return "CRITICAL"

    def _set_temp_field(labels_dict, key, value_str, temp_c):
        """Set a field with temperature-aware color on the dot indicator."""
        if key in labels_dict:
            v, d = labels_dict[key]
            color = _temp_color(temp_c)
            app.content.after(0, lambda: v.configure(text=str(value_str), text_color=colors["text"]))
            app.content.after(0, lambda: d.configure(text_color=color))

    def _populate_zones_textbox(thermal_zones):
        """Fill the thermal zones textbox with zone data and color coding."""
        def _do():
            zones_textbox.configure(state="normal")
            zones_textbox.delete("1.0", "end")
            tb = zones_textbox._textbox

            if not thermal_zones:
                zones_textbox.insert("end", "  No thermal zones found on this device.\n")
                zones_textbox.configure(state="disabled")
                return

            # Header line
            hdr = f"  {'Zone Name':<30s} {'Temp':>7s}  {'Status':<12s} {'Policy':<10s}"
            start_idx = tb.index("end-1c")
            zones_textbox.insert("end", hdr + "\n")
            end_idx = tb.index("end-1c")
            tb.tag_add("zone_header", start_idx, end_idx)

            zones_textbox.insert("end", "  " + "-" * 65 + "\n")

            for zone in thermal_zones:
                z_name = getattr(zone, "name", "unknown")
                z_temp = getattr(zone, "temperature", 0.0)
                z_status = getattr(zone, "status", "unknown")
                z_policy = getattr(zone, "policy", "N/A")
                is_throttling = getattr(zone, "is_throttling", False)

                status_icon = "\U0001f534" if is_throttling else ("\U0001f7e1" if z_temp >= 50 else "\U0001f7e2")
                status_text = f"{status_icon} {z_status}"

                line = f"  {z_name:<30s} {z_temp:>6.1f}\u00b0C  {status_text:<12s} {z_policy:<10s}"
                tag = _temp_tag(z_temp)

                start_idx = tb.index("end-1c")
                zones_textbox.insert("end", line + "\n")
                end_idx = tb.index("end-1c")
                if tag:
                    tb.tag_add(tag, start_idx, end_idx)

                # Show trip points if available
                trip_points = getattr(zone, "trip_points", [])
                if trip_points:
                    for tp in trip_points[:3]:  # limit to first 3 trip points
                        tp_str = f"    \u2514\u2500 trip: {tp}"
                        zones_textbox.insert("end", tp_str + "\n")

            zones_textbox.see("1.0")
            zones_textbox.configure(state="disabled")
        app.content.after(0, _do)

    # ── Start detection ──
    def start_detection():
        if running["value"]:
            return
        running["value"] = True

        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        progress.set(0)
        health_badge.configure(text="  \U0001f504 Testing...", text_color=colors["info"])
        msg_label.configure(text="Initializing thermal detection...", text_color=colors["text_dim"])

        # Reset all field cards
        for labels_dict in [temp_labels, throttle_labels, cool_labels]:
            for key, (v, d) in labels_dict.items():
                v.configure(text="\u2014", text_color=colors["text_dim"])
                d.configure(text_color=colors["text_dim"])

        # Reset zones textbox
        def _reset_zones():
            zones_textbox.configure(state="normal")
            zones_textbox.delete("1.0", "end")
            zones_textbox.insert("1.0", "  Waiting for thermal zone scan...")
            zones_textbox.configure(state="disabled")
        app.content.after(0, _reset_zones)

        full_report = {"lines": []}

        def _track(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_lines(lines):
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            import datetime as _dt

            header = [
                "=" * 70,
                "  MOOXY AI FAULT DETECTOR \u2014 THERMAL TEST REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70, "",
            ]
            _track_lines(header)

            result = None
            try:
                from app.hardware.thermal_tester import detect_thermal_status

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct / 100.0 if pct > 1 else pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                _track("\U0001f50d Scanning device thermal sensors...")
                _track("")

                result = detect_thermal_status(callback=cb)

                # ═══ PHASE 1: TEMPERATURE READINGS ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 1: TEMPERATURE READINGS \u2550\u2550\u2550")
                _track("")

                cpu_temp = getattr(result, "cpu_temp", None)
                gpu_temp = getattr(result, "gpu_temp", None)
                battery_temp = getattr(result, "battery_temp", None)
                skin_temp = getattr(result, "skin_temp", None)
                max_temp = getattr(result, "max_temperature", None)
                hottest_zone = getattr(result, "hottest_zone", None)

                if cpu_temp is not None:
                    status = _temp_status_label(cpu_temp)
                    _track(f"  CPU Temperature:     {cpu_temp:.1f}\u00b0C  [{status}]")
                    _set_temp_field(temp_labels, "temp_cpu", f"{cpu_temp:.1f}\u00b0C", cpu_temp)
                else:
                    _track("  CPU Temperature:     \u274c Not Available")
                    _set_field(temp_labels, "temp_cpu", "N/A", ok=False)

                if gpu_temp is not None:
                    status = _temp_status_label(gpu_temp)
                    _track(f"  GPU Temperature:     {gpu_temp:.1f}\u00b0C  [{status}]")
                    _set_temp_field(temp_labels, "temp_gpu", f"{gpu_temp:.1f}\u00b0C", gpu_temp)
                else:
                    _track("  GPU Temperature:     \u274c Not Available")
                    _set_field(temp_labels, "temp_gpu", "N/A", ok=False)

                if battery_temp is not None:
                    status = _temp_status_label(battery_temp)
                    _track(f"  Battery Temperature: {battery_temp:.1f}\u00b0C  [{status}]")
                    _set_temp_field(temp_labels, "temp_battery", f"{battery_temp:.1f}\u00b0C", battery_temp)
                else:
                    _track("  Battery Temperature: \u274c Not Available")
                    _set_field(temp_labels, "temp_battery", "N/A", ok=False)

                if skin_temp is not None:
                    status = _temp_status_label(skin_temp)
                    _track(f"  Skin Temperature:    {skin_temp:.1f}\u00b0C  [{status}]")
                    _set_temp_field(temp_labels, "temp_skin", f"{skin_temp:.1f}\u00b0C", skin_temp)
                else:
                    _track("  Skin Temperature:    \u274c Not Available")
                    _set_field(temp_labels, "temp_skin", "N/A", ok=False)

                if max_temp is not None:
                    status = _temp_status_label(max_temp)
                    _track(f"  Max Temperature:     {max_temp:.1f}\u00b0C  [{status}]")
                    _set_temp_field(temp_labels, "temp_max", f"{max_temp:.1f}\u00b0C", max_temp)
                else:
                    _track("  Max Temperature:     N/A")
                    _set_field(temp_labels, "temp_max", "N/A", ok=False)

                if hottest_zone:
                    _track(f"  Hottest Zone:        {hottest_zone}")
                    _set_field(temp_labels, "temp_hottest_zone", str(hottest_zone),
                               ok=_temp_ok(max_temp) if max_temp is not None else True)
                else:
                    _track("  Hottest Zone:        N/A")
                    _set_field(temp_labels, "temp_hottest_zone", "N/A", ok=True)

                app.content.after(0, lambda: progress.set(0.25))

                # ═══ PHASE 2: THROTTLING ANALYSIS ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 2: THROTTLING ANALYSIS \u2550\u2550\u2550")
                _track("")

                is_throttling = getattr(result, "is_any_throttling", False)
                throttle_severity = getattr(result, "throttle_severity", "None")
                cpu_throttle_list = getattr(result, "cpu_throttle", [])

                if is_throttling:
                    _track(f"  \u26a0\ufe0f Throttling ACTIVE \u2014 Severity: {throttle_severity}")
                    _set_field(throttle_labels, "throttle_active", "YES \u2014 Active", ok=False)
                    _set_field(throttle_labels, "throttle_severity", str(throttle_severity), ok=False)
                else:
                    _track(f"  \u2705 No throttling detected")
                    _set_field(throttle_labels, "throttle_active", "No", ok=True)
                    _set_field(throttle_labels, "throttle_severity", "None", ok=True)

                if cpu_throttle_list:
                    _track("")
                    _track("  Per-Core Throttle Status:")

                    total_max = 0
                    total_cur = 0
                    worst_pct = 0.0

                    for core in cpu_throttle_list:
                        core_id = getattr(core, "core_id", "?")
                        cur_freq = getattr(core, "current_freq_mhz", 0)
                        max_freq = getattr(core, "max_freq_mhz", 0)
                        throttle_pct = getattr(core, "throttle_percent", 0.0)
                        is_core_throttled = getattr(core, "is_throttled", False)

                        total_max += max_freq
                        total_cur += cur_freq
                        if throttle_pct > worst_pct:
                            worst_pct = throttle_pct

                        icon = "\U0001f534" if is_core_throttled else "\U0001f7e2"
                        _track(f"    {icon} Core {core_id}: {cur_freq} MHz / {max_freq} MHz "
                               f"(throttle: {throttle_pct:.1f}%)")

                    # Set aggregate throttle card fields
                    if cpu_throttle_list:
                        avg_max = total_max / len(cpu_throttle_list)
                        avg_cur = total_cur / len(cpu_throttle_list)
                        _set_field(throttle_labels, "cpu_max_freq",
                                   f"{avg_max:.0f} MHz (avg)", ok=True)
                        _set_field(throttle_labels, "cpu_cur_freq",
                                   f"{avg_cur:.0f} MHz (avg)", ok=avg_cur >= avg_max * 0.7)
                        _set_field(throttle_labels, "throttle_pct",
                                   f"{worst_pct:.1f}% (worst core)", ok=worst_pct < 20.0)
                else:
                    _track("  No per-core throttle data available.")
                    _set_field(throttle_labels, "cpu_max_freq", "N/A", ok=True)
                    _set_field(throttle_labels, "cpu_cur_freq", "N/A", ok=True)
                    _set_field(throttle_labels, "throttle_pct", "N/A", ok=True)

                app.content.after(0, lambda: progress.set(0.50))

                # ═══ PHASE 3: THERMAL ZONES ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 3: THERMAL ZONES \u2550\u2550\u2550")
                _track("")

                thermal_zones = getattr(result, "thermal_zones", [])

                if thermal_zones:
                    _track(f"  Found {len(thermal_zones)} thermal zone(s):")
                    _track("")

                    for zone in thermal_zones:
                        z_name = getattr(zone, "name", "unknown")
                        z_type = getattr(zone, "zone_type", "N/A")
                        z_temp = getattr(zone, "temperature", 0.0)
                        z_trip = getattr(zone, "trip_points", [])
                        z_policy = getattr(zone, "policy", "N/A")
                        z_throttling = getattr(zone, "is_throttling", False)
                        z_status = getattr(zone, "status", "unknown")

                        status_lbl = _temp_status_label(z_temp)
                        icon = "\U0001f534" if z_throttling else (
                            "\U0001f7e1" if z_temp >= 50 else "\U0001f7e2")

                        _track(f"  {icon} {z_name} ({z_type})")
                        _track(f"      Temp: {z_temp:.1f}\u00b0C  [{status_lbl}]  Policy: {z_policy}  Status: {z_status}")
                        if z_trip:
                            trip_str = ", ".join(str(tp) for tp in z_trip[:5])
                            _track(f"      Trip points: {trip_str}")

                    # Populate the zones textbox card
                    _populate_zones_textbox(thermal_zones)
                else:
                    _track("  \u274c No thermal zones found on this device.")
                    _populate_zones_textbox([])

                app.content.after(0, lambda: progress.set(0.75))

                # ═══ PHASE 4: COOLING DEVICES ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 4: COOLING DEVICES \u2550\u2550\u2550")
                _track("")

                cooling_devices = getattr(result, "cooling_devices", [])

                if cooling_devices:
                    active_count = sum(1 for cd in cooling_devices if getattr(cd, "is_active", False))
                    max_state_val = max((getattr(cd, "max_state", 0) for cd in cooling_devices), default=0)

                    _track(f"  Found {len(cooling_devices)} cooling device(s), {active_count} active:")
                    _track("")

                    _set_field(cool_labels, "cool_device_count", str(len(cooling_devices)), ok=True)
                    _set_field(cool_labels, "cool_active_count", str(active_count),
                               ok=active_count <= len(cooling_devices) // 2 + 1)
                    _set_field(cool_labels, "cool_max_state", str(max_state_val), ok=True)

                    for cd in cooling_devices:
                        cd_name = getattr(cd, "name", "unknown")
                        cd_type = getattr(cd, "device_type", "N/A")
                        cd_cur = getattr(cd, "current_state", 0)
                        cd_max = getattr(cd, "max_state", 0)
                        cd_active = getattr(cd, "is_active", False)

                        icon = "\u2744\ufe0f" if cd_active else "\u23f8"
                        active_str = "ACTIVE" if cd_active else "idle"
                        _track(f"    {icon} {cd_name} ({cd_type})")
                        _track(f"        State: {cd_cur}/{cd_max}  [{active_str}]")
                else:
                    _track("  \u274c No cooling devices found.")
                    _set_field(cool_labels, "cool_device_count", "0", ok=False)
                    _set_field(cool_labels, "cool_active_count", "0", ok=True)
                    _set_field(cool_labels, "cool_max_state", "N/A", ok=True)

                app.content.after(0, lambda: progress.set(0.92))

                # ═══ THERMAL HEALTH SUMMARY ═══
                _track("")
                _track("\u2550\u2550\u2550 THERMAL HEALTH SUMMARY \u2550\u2550\u2550")
                _track("")

                overall = getattr(result, "overall_health", "Unknown")
                score = getattr(result, "health_score", 0)
                warnings = getattr(result, "warnings", [])

                _track(f"  Health Score:  {score}/100")
                _track(f"  Overall:       {overall}")

                if warnings:
                    _track("")
                    _track("  \u26a0\ufe0f Warnings:")
                    for w in warnings:
                        _track(f"    \u2022 {w}")

                overall_str = str(overall).upper()
                if overall_str in ("GOOD", "HEALTHY", "OK", "COOL", "NORMAL"):
                    _track("")
                    _track(f"  \u2705 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \u2705 {overall_str} ({score}/100)", text_color=colors["success"]))
                elif overall_str in ("DEGRADED", "FAIR", "WARM", "PARTIAL"):
                    _track("")
                    _track(f"  \U0001f7e1 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \U0001f7e1 {overall_str} ({score}/100)", text_color=colors["warning"]))
                elif overall_str in ("POOR", "BAD", "CRITICAL", "HOT", "OVERHEAT"):
                    _track("")
                    _track(f"  \U0001f534 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \U0001f534 {overall_str} ({score}/100)", text_color=colors["accent"]))
                else:
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \u26a0\ufe0f {overall_str}", text_color=colors["text_dim"]))

            except ImportError:
                _track("  \u274c Thermal tester module not found")
                _track("  Install: app/hardware/thermal_tester.py required")
                app.content.after(0, lambda: health_badge.configure(
                    text="  \u274c Module Error", text_color=colors["accent"]))
            except Exception as e:
                _track(f"  \u274c Thermal detection error: {str(e)}")
                app.content.after(0, lambda: health_badge.configure(
                    text="  \u274c Error", text_color=colors["accent"]))

            _track("")
            _track("=" * 70)
            _track("  Report generated by Mooxy AI Fault Detector v1.0")
            _track("=" * 70)

            report_text = "\n".join(full_report["lines"])

            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Thermal test complete \u2014 full report above", text_color=colors["success"]))

            # ── Save to history ──
            try:
                from app.gui.history_manager import get_unique_log_path, add_detection
                log_path = get_unique_log_path("thermal_report")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)

                zone_count = len(getattr(result, "thermal_zones", [])) if result else 0
                cool_count = len(getattr(result, "cooling_devices", [])) if result else 0
                add_detection(
                    detection_type="THERMAL",
                    device_name="Thermal Test",
                    summary=(
                        f"Max: {getattr(result, 'max_temperature', 'N/A')}\u00b0C | "
                        f"Zones: {zone_count} | "
                        f"Cooling: {cool_count} | "
                        f"Health: {getattr(result, 'overall_health', 'Unknown')}"
                    ) if result else "Thermal test failed",
                    faults_count=len(getattr(result, "warnings", [])) if result else 0,
                    faults_summary="; ".join(getattr(result, "warnings", [])[:3]) if result else "",
                    report_file=str(log_path),
                    extra={
                        "health_score": getattr(result, "health_score", 0),
                        "max_temp": getattr(result, "max_temperature", None),
                        "is_throttling": getattr(result, "is_any_throttling", False),
                        "zone_count": zone_count,
                        "cooling_count": cool_count,
                    } if result else {}
                )
            except Exception:
                pass

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    def copy_report():
        try:
            text = report_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            msg_label.configure(text="\U0001f4cb Report copied to clipboard!", text_color=colors["success"])
        except Exception:
            pass

    def save_report():
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                 filetypes=[("Text", "*.txt")],
                                                 initialfile="thermal_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"\U0001f4be Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="\U0001f321\ufe0f Start Thermal Detection", width=300, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_detection).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="\U0001f4cb Copy", width=100, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="\U0001f4be Save", width=100, height=46,
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
                      "Press 'Start Thermal Detection' to begin.\n\n"
                      "Requirements:\n"
                      "\u2022 Device connected via USB with ADB enabled\n"
                      "\u2022 Root access recommended for full thermal zone visibility\n\n"
                      "Tests performed:\n"
                      "  1. CPU temperature \u2014 per-core readings & throttle detection\n"
                      "  2. GPU temperature \u2014 graphics processor thermal state\n"
                      "  3. Battery temperature \u2014 thermal safety check\n"
                      "  4. Skin temperature \u2014 external device temperature\n"
                      "  5. Thermal zone enumeration with trip points\n"
                      "  6. CPU frequency throttle analysis\n"
                      "  7. Cooling device state & capacity\n"
                      "  8. Sensor IC identification (TI TMP, STMicro, Maxim, NXP)\n")
    _setup_tags()

    app.update_status("Thermal Test \u2014 Connect device and press Start")
