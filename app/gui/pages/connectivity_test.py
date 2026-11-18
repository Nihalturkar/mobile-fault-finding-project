import customtkinter as ctk
import threading


def render_connectivity_test(app):
    """Connectivity Testing page — WiFi, Bluetooth, GPS, NFC, Cellular signal diagnostics.
    Shows detections LIVE as they happen — real-time append with color-coded output."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="📶 Connectivity Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="WiFi, Bluetooth, GPS, NFC, Cellular signal diagnostics",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card: What connectivity testing detects ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="🔍 Connectivity Testing Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ WiFi — Chipset ID, signal strength (RSSI), link speed, standard (WiFi 5/6/7)",
        "✅ Bluetooth — Controller IC, version, paired devices, status",
        "✅ GPS — Providers, satellite count, fix accuracy, GNSS support",
        "✅ NFC — Controller IC, firmware version, read/write capability",
        "✅ Cellular — Signal (RSRP/RSRQ/SINR), network type, band, operator",
        "✅ IC Database — Qualcomm WCN, Broadcom BCM, NXP PN, MediaTek MT",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Overall Connectivity Health Badge ──
    badge_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=55)
    badge_frame.pack(fill="x", padx=20, pady=(0, 10))
    badge_frame.pack_propagate(False)
    badge_inner = ctk.CTkFrame(badge_frame, fg_color="transparent")
    badge_inner.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(badge_inner, text="Overall Connectivity Health:",
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

    # ── WiFi card ──
    wifi_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    wifi_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(wifi_card, text="📶 WiFi",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    wifi_fields = [
        ("wifi_enabled", "Enabled"),
        ("wifi_connected", "Connected"),
        ("wifi_ssid", "SSID"),
        ("wifi_signal", "Signal (RSSI)"),
        ("wifi_speed", "Link Speed"),
        ("wifi_standard", "WiFi Standard"),
        ("wifi_chipset", "Chipset"),
        ("wifi_mac", "MAC Address"),
        ("wifi_status", "Status"),
    ]
    wifi_labels = {}
    for key, name in wifi_fields:
        row = ctk.CTkFrame(wifi_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        wifi_labels[key] = (val, dot)
    ctk.CTkFrame(wifi_card, fg_color="transparent", height=8).pack()

    # ── Bluetooth card ──
    bt_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    bt_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(bt_card, text="🔵 Bluetooth",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    bt_fields = [
        ("bt_enabled", "Enabled"),
        ("bt_address", "Address"),
        ("bt_chipset", "Chipset"),
        ("bt_version", "BT Version"),
        ("bt_paired", "Paired Devices"),
        ("bt_status", "Status"),
    ]
    bt_labels = {}
    for key, name in bt_fields:
        row = ctk.CTkFrame(bt_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        bt_labels[key] = (val, dot)
    ctk.CTkFrame(bt_card, fg_color="transparent", height=8).pack()

    # ── NFC card ──
    nfc_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    nfc_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(nfc_card, text="📱 NFC",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    nfc_fields = [
        ("nfc_present", "Present"),
        ("nfc_enabled", "Enabled"),
        ("nfc_controller", "Controller"),
        ("nfc_firmware", "Firmware"),
        ("nfc_status", "Status"),
    ]
    nfc_labels = {}
    for key, name in nfc_fields:
        row = ctk.CTkFrame(nfc_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        nfc_labels[key] = (val, dot)
    ctk.CTkFrame(nfc_card, fg_color="transparent", height=8).pack()

    # ── GPS card ──
    gps_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    gps_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(gps_card, text="🛰️ GPS / GNSS",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    gps_fields = [
        ("gps_enabled", "Enabled"),
        ("gps_providers", "Providers"),
        ("gps_satellites", "Satellites"),
        ("gps_accuracy", "Fix Accuracy"),
        ("gps_glonass", "GLONASS"),
        ("gps_galileo", "Galileo"),
        ("gps_beidou", "BeiDou"),
        ("gps_status", "Status"),
    ]
    gps_labels = {}
    for key, name in gps_fields:
        row = ctk.CTkFrame(gps_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        gps_labels[key] = (val, dot)
    ctk.CTkFrame(gps_card, fg_color="transparent", height=8).pack()

    # ── Cellular card ──
    cell_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    cell_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(cell_card, text="📡 Cellular",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    cell_fields = [
        ("cell_signal", "Signal Strength"),
        ("cell_quality", "Signal Quality"),
        ("cell_type", "Network Type"),
        ("cell_rsrp", "RSRP"),
        ("cell_rsrq", "RSRQ"),
        ("cell_sinr", "SINR"),
        ("cell_band", "Band"),
        ("cell_operator", "Operator"),
        ("cell_status", "Status"),
    ]
    cell_labels = {}
    for key, name in cell_fields:
        row = ctk.CTkFrame(cell_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        cell_labels[key] = (val, dot)
    ctk.CTkFrame(cell_card, fg_color="transparent", height=8).pack()

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
        if any(k in t for k in ["fault", "🔴", "critical", "danger", "❌", "[xx]", "fail", "not found", "missing", "disabled"]):
            return "fault"
        if any(k in t for k in ["warning", "🟡", "⚠️", "[!!]", "degraded", "weak", "poor"]):
            return "warning"
        if any(k in t for k in ["✅", "[ok]", "ok", "pass", "working", "detected", "active", "connected", "enabled"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "========", "CONNECTIVITY", "REPORT", "PHASE"]):
            return "header"
        if any(k in t for k in ["🔍", "scanning", "detecting", "reading", "checking", "probing"]):
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
        msg_label.configure(text="Initializing connectivity detection...", text_color=colors["text_dim"])

        # Reset all field labels
        for labels_dict in [wifi_labels, bt_labels, nfc_labels, gps_labels, cell_labels]:
            for key, (v, d) in labels_dict.items():
                v.configure(text="—", text_color=colors["text_dim"])
                d.configure(text_color=colors["text_dim"])

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
                "  MOOXY AI FAULT DETECTOR — CONNECTIVITY TEST REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70,
                "",
            ]
            _track_lines(header)

            result = None
            try:
                from app.hardware.connectivity_tester import detect_connectivity_status

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct / 100.0 if pct > 1 else pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                _track("🔍 Scanning connectivity subsystems...")
                _track("")

                result = detect_connectivity_status(callback=cb)

                # ═══ PHASE 1: WiFi ═══
                _track("")
                _track("═══ PHASE 1: WiFi ═══")
                _track("")

                wifi = getattr(result, "wifi", None)
                if wifi:
                    w_enabled = getattr(wifi, "enabled", None)
                    w_connected = getattr(wifi, "connected", None)
                    w_ssid = getattr(wifi, "ssid", None)
                    w_bssid = getattr(wifi, "bssid", None)
                    w_mac = getattr(wifi, "mac_address", None)
                    w_ip = getattr(wifi, "ip_address", None)
                    w_signal = getattr(wifi, "signal_strength", None)
                    w_speed = getattr(wifi, "link_speed", None)
                    w_freq = getattr(wifi, "frequency", None)
                    w_standard = getattr(wifi, "wifi_standard", None)
                    w_chipset = getattr(wifi, "chipset", None)
                    w_status = getattr(wifi, "status", "Unknown")

                    enabled_str = str(w_enabled) if w_enabled is not None else "Unknown"
                    connected_str = str(w_connected) if w_connected is not None else "Unknown"
                    is_enabled = str(w_enabled).lower() in ("true", "yes", "1", "enabled")
                    is_connected = str(w_connected).lower() in ("true", "yes", "1", "connected")

                    if is_enabled:
                        _track(f"  ✅ WiFi Enabled")
                    else:
                        _track(f"  ❌ WiFi Disabled")
                    if is_connected:
                        _track(f"  ✅ Connected to: {w_ssid or 'Unknown'}")
                    else:
                        _track(f"  ⚠️ Not connected to any network")

                    _track(f"  BSSID:        {w_bssid or 'N/A'}")
                    _track(f"  MAC Address:  {w_mac or 'N/A'}")
                    _track(f"  IP Address:   {w_ip or 'N/A'}")
                    _track(f"  Signal:       {w_signal or 'N/A'}")
                    _track(f"  Link Speed:   {w_speed or 'N/A'}")
                    _track(f"  Frequency:    {w_freq or 'N/A'}")
                    _track(f"  WiFi Standard:{w_standard or 'N/A'}")
                    _track(f"  Chipset:      {w_chipset or 'N/A'}")
                    _track(f"  Status:       {w_status}")

                    _set_field(wifi_labels, "wifi_enabled", enabled_str, ok=is_enabled)
                    _set_field(wifi_labels, "wifi_connected", connected_str, ok=is_connected)
                    _set_field(wifi_labels, "wifi_ssid", w_ssid or "N/A", ok=is_connected)
                    _set_field(wifi_labels, "wifi_signal", w_signal or "N/A",
                               ok=_is_signal_ok(w_signal))
                    _set_field(wifi_labels, "wifi_speed", w_speed or "N/A")
                    _set_field(wifi_labels, "wifi_standard", w_standard or "N/A")
                    _set_field(wifi_labels, "wifi_chipset", w_chipset or "N/A")
                    _set_field(wifi_labels, "wifi_mac", w_mac or "N/A")
                    _set_field(wifi_labels, "wifi_status", w_status,
                               ok=str(w_status).lower() in ("ok", "active", "working", "connected"))
                else:
                    _track("  ❌ WiFi data NOT FOUND")
                    _set_field(wifi_labels, "wifi_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.20))

                # ═══ PHASE 2: Bluetooth ═══
                _track("")
                _track("═══ PHASE 2: BLUETOOTH ═══")
                _track("")

                bt = getattr(result, "bluetooth", None)
                if bt:
                    b_enabled = getattr(bt, "enabled", None)
                    b_address = getattr(bt, "address", None)
                    b_chipset = getattr(bt, "chipset", None)
                    b_version = getattr(bt, "bt_version", None)
                    b_paired = getattr(bt, "paired_devices", None)
                    b_status = getattr(bt, "status", "Unknown")

                    is_bt_enabled = str(b_enabled).lower() in ("true", "yes", "1", "enabled")

                    if is_bt_enabled:
                        _track(f"  ✅ Bluetooth Enabled")
                    else:
                        _track(f"  ❌ Bluetooth Disabled")

                    _track(f"  Address:      {b_address or 'N/A'}")
                    _track(f"  Chipset:      {b_chipset or 'N/A'}")
                    _track(f"  BT Version:   {b_version or 'N/A'}")

                    if isinstance(b_paired, list):
                        paired_str = f"{len(b_paired)} device(s)"
                        _track(f"  Paired:       {paired_str}")
                        for dev in b_paired[:5]:
                            _track(f"    • {dev}")
                    else:
                        paired_str = str(b_paired) if b_paired is not None else "N/A"
                        _track(f"  Paired:       {paired_str}")

                    _track(f"  Status:       {b_status}")

                    _set_field(bt_labels, "bt_enabled", str(b_enabled) if b_enabled is not None else "Unknown",
                               ok=is_bt_enabled)
                    _set_field(bt_labels, "bt_address", b_address or "N/A")
                    _set_field(bt_labels, "bt_chipset", b_chipset or "N/A")
                    _set_field(bt_labels, "bt_version", b_version or "N/A")
                    _set_field(bt_labels, "bt_paired", paired_str)
                    _set_field(bt_labels, "bt_status", b_status,
                               ok=str(b_status).lower() in ("ok", "active", "working", "enabled"))
                else:
                    _track("  ❌ Bluetooth data NOT FOUND")
                    _set_field(bt_labels, "bt_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.40))

                # ═══ PHASE 3: GPS / GNSS ═══
                _track("")
                _track("═══ PHASE 3: GPS / GNSS ═══")
                _track("")

                gps = getattr(result, "gps", None)
                if gps:
                    g_enabled = getattr(gps, "enabled", None)
                    g_providers = getattr(gps, "providers", None)
                    g_sat_visible = getattr(gps, "satellites_visible", None)
                    g_sat_used = getattr(gps, "satellites_used", None)
                    g_accuracy = getattr(gps, "fix_accuracy", None)
                    g_glonass = getattr(gps, "supports_glonass", None)
                    g_galileo = getattr(gps, "supports_galileo", None)
                    g_beidou = getattr(gps, "supports_beidou", None)
                    g_status = getattr(gps, "status", "Unknown")

                    is_gps_enabled = str(g_enabled).lower() in ("true", "yes", "1", "enabled")

                    if is_gps_enabled:
                        _track(f"  ✅ GPS Enabled")
                    else:
                        _track(f"  ❌ GPS Disabled")

                    if isinstance(g_providers, list):
                        providers_str = ", ".join(g_providers) if g_providers else "None"
                    else:
                        providers_str = str(g_providers) if g_providers is not None else "N/A"

                    _track(f"  Providers:    {providers_str}")

                    sat_str = "N/A"
                    if g_sat_visible is not None and g_sat_used is not None:
                        sat_str = f"{g_sat_used} used / {g_sat_visible} visible"
                    elif g_sat_visible is not None:
                        sat_str = f"{g_sat_visible} visible"

                    _track(f"  Satellites:   {sat_str}")
                    _track(f"  Fix Accuracy: {g_accuracy or 'N/A'}")

                    glonass_str = _bool_support_str(g_glonass)
                    galileo_str = _bool_support_str(g_galileo)
                    beidou_str = _bool_support_str(g_beidou)

                    _track(f"  GLONASS:      {glonass_str}")
                    _track(f"  Galileo:      {galileo_str}")
                    _track(f"  BeiDou:       {beidou_str}")
                    _track(f"  Status:       {g_status}")

                    _set_field(gps_labels, "gps_enabled", str(g_enabled) if g_enabled is not None else "Unknown",
                               ok=is_gps_enabled)
                    _set_field(gps_labels, "gps_providers", providers_str)
                    _set_field(gps_labels, "gps_satellites", sat_str)
                    _set_field(gps_labels, "gps_accuracy", g_accuracy or "N/A")
                    _set_field(gps_labels, "gps_glonass", glonass_str,
                               ok=str(g_glonass).lower() in ("true", "yes", "1", "supported"))
                    _set_field(gps_labels, "gps_galileo", galileo_str,
                               ok=str(g_galileo).lower() in ("true", "yes", "1", "supported"))
                    _set_field(gps_labels, "gps_beidou", beidou_str,
                               ok=str(g_beidou).lower() in ("true", "yes", "1", "supported"))
                    _set_field(gps_labels, "gps_status", g_status,
                               ok=str(g_status).lower() in ("ok", "active", "working", "enabled"))
                else:
                    _track("  ❌ GPS data NOT FOUND")
                    _set_field(gps_labels, "gps_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.60))

                # ═══ PHASE 4: NFC ═══
                _track("")
                _track("═══ PHASE 4: NFC ═══")
                _track("")

                nfc = getattr(result, "nfc", None)
                if nfc:
                    n_present = getattr(nfc, "present", None)
                    n_enabled = getattr(nfc, "enabled", None)
                    n_controller = getattr(nfc, "controller", None)
                    n_mfg = getattr(nfc, "controller_manufacturer", None)
                    n_firmware = getattr(nfc, "firmware_version", None)
                    n_status = getattr(nfc, "status", "Unknown")

                    is_nfc_present = str(n_present).lower() in ("true", "yes", "1", "present")
                    is_nfc_enabled = str(n_enabled).lower() in ("true", "yes", "1", "enabled")

                    if is_nfc_present:
                        _track(f"  ✅ NFC Hardware Present")
                    else:
                        _track(f"  ❌ NFC Hardware NOT Present")

                    if is_nfc_enabled:
                        _track(f"  ✅ NFC Enabled")
                    else:
                        _track(f"  ⚠️ NFC Disabled")

                    controller_str = n_controller or "N/A"
                    if n_mfg:
                        controller_str = f"{n_mfg} {n_controller}" if n_controller else n_mfg

                    _track(f"  Controller:   {controller_str}")
                    _track(f"  Firmware:     {n_firmware or 'N/A'}")
                    _track(f"  Status:       {n_status}")

                    _set_field(nfc_labels, "nfc_present", "Yes" if is_nfc_present else "No",
                               ok=is_nfc_present)
                    _set_field(nfc_labels, "nfc_enabled", "Yes" if is_nfc_enabled else "No",
                               ok=is_nfc_enabled)
                    _set_field(nfc_labels, "nfc_controller", controller_str)
                    _set_field(nfc_labels, "nfc_firmware", n_firmware or "N/A")
                    _set_field(nfc_labels, "nfc_status", n_status,
                               ok=str(n_status).lower() in ("ok", "active", "working", "enabled"))
                else:
                    _track("  ⚠️ NFC not found (some devices lack NFC hardware)")
                    _set_field(nfc_labels, "nfc_present", "No", ok=False)
                    _set_field(nfc_labels, "nfc_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.78))

                # ═══ PHASE 5: Cellular ═══
                _track("")
                _track("═══ PHASE 5: CELLULAR SIGNAL ═══")
                _track("")

                cell = getattr(result, "cellular", None)
                if cell:
                    c_signal = getattr(cell, "signal_strength_dbm", None)
                    c_quality = getattr(cell, "signal_quality", None)
                    c_type = getattr(cell, "network_type", None)
                    c_rsrp = getattr(cell, "rsrp", None)
                    c_rsrq = getattr(cell, "rsrq", None)
                    c_sinr = getattr(cell, "sinr", None)
                    c_band = getattr(cell, "band", None)
                    c_operator = getattr(cell, "operator", None)
                    c_status = getattr(cell, "status", "Unknown")

                    _track(f"  Signal:       {c_signal or 'N/A'} dBm")
                    _track(f"  Quality:      {c_quality or 'N/A'}")
                    _track(f"  Network Type: {c_type or 'N/A'}")
                    _track(f"  RSRP:         {c_rsrp or 'N/A'}")
                    _track(f"  RSRQ:         {c_rsrq or 'N/A'}")
                    _track(f"  SINR:         {c_sinr or 'N/A'}")
                    _track(f"  Band:         {c_band or 'N/A'}")
                    _track(f"  Operator:     {c_operator or 'N/A'}")

                    signal_ok = _is_cellular_signal_ok(c_signal)
                    status_ok = str(c_status).lower() in ("ok", "active", "working", "connected", "registered")
                    icon = "✅" if status_ok else "⚠️"
                    _track(f"  {icon} Status: {c_status}")

                    _set_field(cell_labels, "cell_signal", f"{c_signal} dBm" if c_signal is not None else "N/A",
                               ok=signal_ok)
                    _set_field(cell_labels, "cell_quality", c_quality or "N/A",
                               ok=str(c_quality).lower() not in ("poor", "bad", "none", "no signal"))
                    _set_field(cell_labels, "cell_type", c_type or "N/A")
                    _set_field(cell_labels, "cell_rsrp", str(c_rsrp) if c_rsrp is not None else "N/A")
                    _set_field(cell_labels, "cell_rsrq", str(c_rsrq) if c_rsrq is not None else "N/A")
                    _set_field(cell_labels, "cell_sinr", str(c_sinr) if c_sinr is not None else "N/A")
                    _set_field(cell_labels, "cell_band", str(c_band) if c_band is not None else "N/A")
                    _set_field(cell_labels, "cell_operator", c_operator or "N/A")
                    _set_field(cell_labels, "cell_status", c_status, ok=status_ok)
                else:
                    _track("  ❌ Cellular data NOT FOUND")
                    _set_field(cell_labels, "cell_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.92))

                # ═══ CONNECTIVITY HEALTH SUMMARY ═══
                _track("")
                _track("═══ CONNECTIVITY HEALTH SUMMARY ═══")
                _track("")

                overall = getattr(result, "overall_health", "Unknown")
                score = getattr(result, "health_score", 0)

                _track(f"  Health Score:  {score}/100")
                _track(f"  Overall:       {overall}")

                warnings = getattr(result, "warnings", [])
                if warnings:
                    _track("")
                    _track("  ⚠️ Warnings:")
                    for w in warnings:
                        _track(f"    • {w}")

                overall_str = str(overall).upper()
                if overall_str in ("GOOD", "HEALTHY", "OK"):
                    _track("")
                    _track(f"  ✅ OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  ✅ {overall_str} ({score}/100)", text_color=colors["success"]))
                elif overall_str in ("DEGRADED", "FAIR", "PARTIAL"):
                    _track("")
                    _track(f"  🟡 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  🟡 {overall_str} ({score}/100)", text_color=colors["warning"]))
                elif overall_str in ("POOR", "BAD", "CRITICAL"):
                    _track("")
                    _track(f"  🔴 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  🔴 {overall_str} ({score}/100)", text_color=colors["accent"]))
                else:
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  ⚠️ {overall_str}", text_color=colors["text_dim"]))

            except ImportError:
                _track("  ❌ Connectivity tester module not found")
                _track("  Install: app/hardware/connectivity_tester.py required")
                app.content.after(0, lambda: health_badge.configure(
                    text="  ❌ Module Error", text_color=colors["accent"]))
            except Exception as e:
                _track(f"  ❌ Connectivity detection error: {str(e)}")
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
                text="Connectivity test complete — full report above", text_color=colors["success"]))

            # Auto-save to file
            try:
                from app.gui.history_manager import get_unique_log_path
                log_path = get_unique_log_path("connectivity_report")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
            except Exception:
                log_path = None

            # Save to history
            try:
                from app.gui.history_manager import add_detection

                device_name = "Connectivity Test"
                summary_text = "Connectivity diagnostics completed"
                faults_count = 0
                faults_summary = ""

                if result:
                    overall_h = str(getattr(result, "overall_health", "Unknown"))
                    h_score = getattr(result, "health_score", 0)
                    warn_list = getattr(result, "warnings", [])
                    summary_text = (
                        f"Health: {overall_h} ({h_score}/100) | "
                        f"Warnings: {len(warn_list)}"
                    )
                    faults_count = len(warn_list)
                    faults_summary = "; ".join(warn_list[:3])

                add_detection(
                    detection_type="CONNECTIVITY",
                    device_name=device_name,
                    summary=summary_text,
                    faults_count=faults_count,
                    faults_summary=faults_summary,
                    report_file=str(log_path) if log_path else "",
                    extra={
                        "health_score": getattr(result, "health_score", 0),
                        "overall_health": str(getattr(result, "overall_health", "Unknown")),
                    } if result else {}
                )
            except Exception as e:
                print(f"[Connectivity Test] History save error: {e}")

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    # ── Helper functions for signal evaluation ──
    def _is_signal_ok(signal):
        """Check if WiFi signal strength is acceptable."""
        try:
            s = int(str(signal).replace("dBm", "").replace(" ", "").strip())
            return s >= -70  # Above -70 dBm is good
        except (ValueError, TypeError):
            return True

    def _is_cellular_signal_ok(signal):
        """Check if cellular signal strength is acceptable."""
        try:
            s = int(str(signal).replace("dBm", "").replace(" ", "").strip())
            return s >= -100  # Above -100 dBm is acceptable for LTE
        except (ValueError, TypeError):
            return True

    def _bool_support_str(value):
        """Convert a boolean-like value to Supported/Not Supported string."""
        if value is None:
            return "N/A"
        v = str(value).lower()
        if v in ("true", "yes", "1", "supported"):
            return "Supported"
        if v in ("false", "no", "0", "not supported"):
            return "Not Supported"
        return str(value)

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
                                                 initialfile="connectivity_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="📶 Start Connectivity Detection", width=300, height=46,
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
                      "Press 'Start Connectivity Detection' to begin.\n\n"
                      "Requirements:\n"
                      "• Device connected via USB with ADB enabled\n\n"
                      "Tests performed:\n"
                      "  1. WiFi — chipset, signal, link speed, standard\n"
                      "  2. Bluetooth — controller IC, version, paired devices\n"
                      "  3. GPS/GNSS — providers, satellites, accuracy, constellations\n"
                      "  4. NFC — controller, firmware, read/write capability\n"
                      "  5. Cellular — RSRP/RSRQ/SINR, network type, band, operator\n"
                      "  6. IC identification (Qualcomm WCN, Broadcom BCM, NXP PN, MediaTek MT)\n")
    _setup_tags()

    app.update_status("Connectivity Test — Connect device and press Start")
