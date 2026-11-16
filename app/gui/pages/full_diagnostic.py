import customtkinter as ctk
import threading
import time


def render_full_diagnostic(app):
    """Full Device Diagnostic — runs ALL hardware tests sequentially in one page.
    Battery → Power → Display → Clock → Sensor → Audio → Connectivity → Storage → Thermal.
    Each section appears live as its test completes."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="🩺 Full Device Diagnostic",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="One-click complete hardware scan — all tests run automatically, results shown in real-time",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Test modules to run in order ──
    TEST_MODULES = [
        {
            "id": "battery",
            "name": "Battery & Charging",
            "icon": "🔋",
            "module": "app.hardware.battery_tester",
            "func": "detect_battery_status",
            "fields": [
                ("Manufacturer", lambda r: _deep(r, "battery_info", "manufacturer")),
                ("Chemistry", lambda r: _deep(r, "battery_info", "chemistry")),
                ("Design Capacity", lambda r: _deep(r, "battery_info", "design_capacity")),
                ("Voltage", lambda r: _deep(r, "battery_info", "voltage")),
                ("Current", lambda r: _deep(r, "battery_info", "current")),
                ("Temperature", lambda r: _deep(r, "battery_info", "temperature")),
                ("Cycle Count", lambda r: _deep(r, "battery_info", "cycle_count")),
                ("Health %", lambda r: _deep(r, "battery_info", "health_percent")),
                ("Charging IC", lambda r: _deep(r, "charging_ic", "ic_name")),
                ("Charge Status", lambda r: _deep(r, "charging_ic", "status")),
                ("Fast Charge", lambda r: _list_or_deep(r, "fast_charge", "protocols_supported")),
                ("Max Wattage", lambda r: _deep(r, "fast_charge", "max_wattage")),
                ("Wear Level", lambda r: _deep(r, "health_detail", "wear_level")),
                ("Estimated Life", lambda r: _deep(r, "health_detail", "estimated_life")),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "power",
            "name": "Power & Voltage Rails",
            "icon": "⚡",
            "module": "app.hardware.power_tester",
            "func": "detect_power_status",
            "fields": [
                ("PMIC IC", lambda r: _attr(r, "pmic_name")),
                ("PMIC Manufacturer", lambda r: _attr(r, "pmic_manufacturer")),
                ("Input Voltage", lambda r: _attr(r, "input_voltage")),
                ("VDD_CX", lambda r: _rail(r, "VDD_CX")),
                ("VDD_MX", lambda r: _rail(r, "VDD_MX")),
                ("VDD_GFX", lambda r: _rail(r, "VDD_GFX")),
                ("VDD_EBI", lambda r: _rail(r, "VDD_EBI")),
                ("Short Circuit", lambda r: _attr(r, "short_circuit_detected")),
                ("Overcurrent", lambda r: _attr(r, "overcurrent_detected")),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "display",
            "name": "Display & Touch",
            "icon": "🖥️",
            "module": "app.hardware.display_tester",
            "func": "detect_display_status",
            "fields": [
                ("Panel Type", lambda r: _attr(r, "panel_type")),
                ("Panel Manufacturer", lambda r: _attr(r, "panel_manufacturer")),
                ("Resolution", lambda r: _attr(r, "resolution")),
                ("Refresh Rate", lambda r: _attr(r, "refresh_rate")),
                ("HDR Support", lambda r: _attr(r, "hdr_support")),
                ("Brightness", lambda r: _attr(r, "brightness_level")),
                ("Touch IC", lambda r: _attr(r, "touch_ic")),
                ("Touch Protocol", lambda r: _attr(r, "touch_protocol")),
                ("Multitouch Points", lambda r: _attr(r, "multitouch_points")),
                ("Dead Pixels", lambda r: _attr(r, "dead_pixel_count")),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "clock",
            "name": "Clock & Oscillators",
            "icon": "🕐",
            "module": "app.hardware.clock_tester",
            "func": "detect_clock_status",
            "fields": [
                ("Primary XO", lambda r: _attr(r, "primary_xo")),
                ("XO Frequency", lambda r: _attr(r, "xo_frequency")),
                ("RTC Source", lambda r: _attr(r, "rtc_source")),
                ("RTC Drift", lambda r: _attr(r, "rtc_drift")),
                ("PLL Count", lambda r: _attr(r, "pll_count")),
                ("PLL Status", lambda r: _attr(r, "pll_status")),
                ("XO Calibration", lambda r: _attr(r, "xo_calibration")),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "sensor",
            "name": "Sensors",
            "icon": "📡",
            "module": "app.hardware.sensor_tester",
            "func": "detect_sensor_status",
            "fields": [
                ("Sensors Found", lambda r: _attr(r, "sensors_found")),
                ("Accelerometer", lambda r: _sensor_line(r, "accelerometer")),
                ("Gyroscope", lambda r: _sensor_line(r, "gyroscope")),
                ("Magnetometer", lambda r: _sensor_line(r, "magnetometer")),
                ("Proximity", lambda r: _sensor_line(r, "proximity")),
                ("Light Sensor", lambda r: _sensor_line(r, "light_sensor")),
                ("Barometer", lambda r: _sensor_line(r, "barometer")),
                ("Health Score", lambda r: f"{_attr(r, 'health_score')}/100"),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "audio",
            "name": "Audio Subsystem",
            "icon": "🔊",
            "module": "app.hardware.audio_tester",
            "func": "detect_audio_status",
            "fields": [
                ("Audio Codec", lambda r: _sub_attr(r, "codec_info", "name")),
                ("Codec Manufacturer", lambda r: _sub_attr(r, "codec_info", "manufacturer")),
                ("Sample Rate", lambda r: _sub_attr(r, "codec_info", "sample_rate")),
                ("Speaker Count", lambda r: _sub_attr(r, "speaker_info", "count")),
                ("Speaker Amp IC", lambda r: _sub_attr(r, "speaker_info", "amplifier_ic")),
                ("Mic Count", lambda r: _sub_attr(r, "microphone_info", "count")),
                ("Headphone Jack", lambda r: _sub_attr(r, "headphone_info", "jack_present")),
                ("DAC IC", lambda r: _sub_attr(r, "headphone_info", "dac_ic")),
                ("Health Score", lambda r: f"{_attr(r, 'health_score')}/100"),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "connectivity",
            "name": "WiFi / BT / GPS / NFC",
            "icon": "📶",
            "module": "app.hardware.connectivity_tester",
            "func": "detect_connectivity_status",
            "fields": [
                ("WiFi Enabled", lambda r: _sub_attr(r, "wifi", "enabled")),
                ("WiFi Chipset", lambda r: _sub_attr(r, "wifi", "chipset")),
                ("WiFi Standard", lambda r: _sub_attr(r, "wifi", "wifi_standard")),
                ("WiFi Signal", lambda r: _fmt_dbm(r, "wifi", "signal_strength")),
                ("BT Enabled", lambda r: _sub_attr(r, "bluetooth", "enabled")),
                ("BT Version", lambda r: _sub_attr(r, "bluetooth", "bt_version")),
                ("GPS Enabled", lambda r: _sub_attr(r, "gps", "enabled")),
                ("GPS Satellites", lambda r: _sub_attr(r, "gps", "satellites_visible")),
                ("NFC Present", lambda r: _sub_attr(r, "nfc", "present")),
                ("NFC Controller", lambda r: _sub_attr(r, "nfc", "controller")),
                ("Cell Signal", lambda r: _fmt_dbm(r, "cellular", "signal_strength_dbm")),
                ("Network Type", lambda r: _sub_attr(r, "cellular", "network_type")),
                ("Health Score", lambda r: f"{_attr(r, 'health_score')}/100"),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "storage",
            "name": "Storage & RAM",
            "icon": "💾",
            "module": "app.hardware.storage_tester",
            "func": "detect_storage_status",
            "fields": [
                ("Storage Type", lambda r: _sub_attr(r, "storage", "storage_type")),
                ("Storage Manufacturer", lambda r: _sub_attr(r, "storage", "manufacturer")),
                ("Storage Model", lambda r: _sub_attr(r, "storage", "model")),
                ("Total Capacity", lambda r: _sub_attr(r, "storage", "total_capacity")),
                ("Used / Free", lambda r: _storage_usage(r)),
                ("Storage Health", lambda r: _sub_attr(r, "storage", "health_status")),
                ("Pre-EOL Info", lambda r: _sub_attr(r, "storage", "pre_eol_info")),
                ("RAM Type", lambda r: _sub_attr(r, "ram", "ram_type")),
                ("Total RAM", lambda r: _sub_attr(r, "ram", "total_ram")),
                ("Available RAM", lambda r: _sub_attr(r, "ram", "available_ram")),
                ("Health Score", lambda r: f"{_attr(r, 'health_score')}/100"),
            ],
            "health_key": "overall_health",
        },
        {
            "id": "thermal",
            "name": "Thermal Management",
            "icon": "🌡️",
            "module": "app.hardware.thermal_tester",
            "func": "detect_thermal_status",
            "fields": [
                ("CPU Temp", lambda r: _fmt_temp(r, "cpu_temp")),
                ("GPU Temp", lambda r: _fmt_temp(r, "gpu_temp")),
                ("Battery Temp", lambda r: _fmt_temp(r, "battery_temp")),
                ("Skin Temp", lambda r: _fmt_temp(r, "skin_temp")),
                ("Max Temp", lambda r: _fmt_temp(r, "max_temperature")),
                ("Hottest Zone", lambda r: _attr(r, "hottest_zone")),
                ("Throttling", lambda r: _attr(r, "is_any_throttling")),
                ("Throttle Severity", lambda r: _attr(r, "throttle_severity")),
                ("Thermal Zones", lambda r: str(len(getattr(r, "thermal_zones", [])))),
                ("Health Score", lambda r: f"{_attr(r, 'health_score')}/100"),
            ],
            "health_key": "overall_health",
        },
    ]

    # ── Helper functions for extracting values ──
    def _attr(obj, key):
        """Get attribute or dict key from result."""
        if obj is None:
            return "—"
        val = getattr(obj, key, None)
        if val is None and isinstance(obj, dict):
            val = obj.get(key)
        if val is None:
            return "—"
        return str(val)

    def _deep(obj, sub_key, field_key):
        """Get nested value: result.sub_key.field_key or result.sub_key[field_key]."""
        if obj is None:
            return "—"
        sub = getattr(obj, sub_key, None)
        if sub is None:
            return "—"
        if isinstance(sub, dict):
            val = sub.get(field_key, "—")
        else:
            val = getattr(sub, field_key, "—")
        return str(val) if val is not None else "—"

    def _sub_attr(obj, sub_key, field_key):
        """Same as _deep but for connectivity/audio style nested dataclasses."""
        return _deep(obj, sub_key, field_key)

    def _list_or_deep(obj, sub_key, field_key):
        """Handle list fields like protocols_supported."""
        if obj is None:
            return "—"
        sub = getattr(obj, sub_key, None)
        if sub is None:
            return "—"
        val = sub.get(field_key) if isinstance(sub, dict) else getattr(sub, field_key, None)
        if isinstance(val, list):
            return ", ".join(str(v) for v in val) if val else "None"
        return str(val) if val is not None else "—"

    def _sensor_line(obj, sensor_key):
        """Format sensor info into a compact line."""
        if obj is None:
            return "—"
        sensor = getattr(obj, sensor_key, None)
        if sensor is None or not getattr(sensor, "name", ""):
            return "Not Found"
        name = getattr(sensor, "name", "")
        ic = getattr(sensor, "ic_name", "")
        status = getattr(sensor, "status", "")
        parts = [name]
        if ic:
            parts.append(f"[{ic}]")
        if status:
            parts.append(f"({status})")
        return " ".join(parts)

    def _rail(obj, rail_name):
        """Extract a power rail voltage."""
        if obj is None:
            return "—"
        rails = getattr(obj, "power_rails", None) or getattr(obj, "rails", None)
        if isinstance(rails, dict):
            r = rails.get(rail_name, {})
            if isinstance(r, dict):
                return r.get("voltage", "—")
            return str(r) if r else "—"
        if isinstance(rails, list):
            for r in rails:
                if isinstance(r, dict) and r.get("name", "") == rail_name:
                    return r.get("voltage", "—")
        return "—"

    def _fmt_temp(obj, key):
        """Format temperature value."""
        if obj is None:
            return "—"
        val = getattr(obj, key, None)
        if val is None or val == 0:
            return "—"
        return f"{val:.1f}°C" if isinstance(val, float) else f"{val}°C"

    def _fmt_dbm(obj, sub_key, field_key):
        """Format signal strength in dBm."""
        val = _deep(obj, sub_key, field_key)
        if val == "—" or val == "0":
            return "—"
        return f"{val} dBm" if "dBm" not in val else val

    def _storage_usage(obj):
        """Format storage used/free."""
        if obj is None:
            return "—"
        storage = getattr(obj, "storage", None)
        if storage is None:
            return "—"
        used = getattr(storage, "used_space", None) if not isinstance(storage, dict) else storage.get("used_space")
        free = getattr(storage, "free_space", None) if not isinstance(storage, dict) else storage.get("free_space")
        if used and free:
            return f"{used} used / {free} free"
        return "—"

    # ── Overall summary bar ──
    summary_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=60)
    summary_frame.pack(fill="x", padx=20, pady=(0, 10))
    summary_frame.pack_propagate(False)
    summary_inner = ctk.CTkFrame(summary_frame, fg_color="transparent")
    summary_inner.pack(fill="x", padx=20, pady=12)

    ctk.CTkLabel(summary_inner, text="Device Health:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["text"]).pack(side="left")
    overall_badge = ctk.CTkLabel(summary_inner, text="  ⏸ Not Tested",
                                  font=("Segoe UI", 16, "bold"), text_color=colors["text_dim"])
    overall_badge.pack(side="left", padx=(10, 0))

    tests_passed_label = ctk.CTkLabel(summary_inner, text="",
                                       font=("Segoe UI", 13), text_color=colors["text_dim"])
    tests_passed_label.pack(side="right")

    # ── Master progress bar ──
    master_progress = ctk.CTkProgressBar(app.content, width=600, height=18,
                                          progress_color=colors["accent"], fg_color=colors["bg_light"])
    master_progress.set(0)
    master_progress.pack(padx=20, pady=(0, 3), anchor="w")
    master_msg = ctk.CTkLabel(app.content, text="Press Start to begin full device diagnostic",
                               font=("Segoe UI", 12), text_color=colors["text_dim"])
    master_msg.pack(anchor="w", padx=20, pady=(0, 10))

    # ── Buttons row ──
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    # ── Section containers — will be populated dynamically ──
    sections_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    sections_frame.pack(fill="x", padx=20, pady=(0, 10))

    # Pre-create section cards for each test (collapsed initially)
    section_widgets = {}
    for test in TEST_MODULES:
        tid = test["id"]

        # Section card
        card = ctk.CTkFrame(sections_frame, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x", pady=(0, 8))

        # Header row with icon, name, status
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 5))

        icon_label = ctk.CTkLabel(header, text=f"{test['icon']} {test['name']}",
                                   font=("Segoe UI", 15, "bold"), text_color=colors["text"])
        icon_label.pack(side="left")

        status_label = ctk.CTkLabel(header, text="⏸ Pending",
                                     font=("Segoe UI", 12), text_color=colors["text_dim"])
        status_label.pack(side="right")

        # Progress bar for this section
        sec_progress = ctk.CTkProgressBar(card, height=8,
                                           progress_color=colors["info"], fg_color=colors["bg_light"])
        sec_progress.set(0)
        sec_progress.pack(fill="x", padx=15, pady=(0, 5))

        # Results frame (hidden initially, populated after test completes)
        results_frame = ctk.CTkFrame(card, fg_color="transparent")
        # Not packed yet — will pack after test runs

        section_widgets[tid] = {
            "card": card,
            "header": icon_label,
            "status": status_label,
            "progress": sec_progress,
            "results_frame": results_frame,
            "result_labels": {},
        }

    # ── Report textbox ──
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=400, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0",
                      "Press 'Start Full Diagnostic' to begin.\n\n"
                      "This will run ALL hardware tests sequentially:\n\n"
                      "  1. 🔋 Battery & Charging — capacity, IC, fast charge, health\n"
                      "  2. ⚡ Power & Voltage — PMIC, rails, short circuit detection\n"
                      "  3. 🖥️ Display & Touch — panel, backlight, touch IC, dead pixels\n"
                      "  4. 🕐 Clock & Oscillators — XO, PLL, RTC drift\n"
                      "  5. 📡 Sensors — accel, gyro, proximity, light, magnetometer\n"
                      "  6. 🔊 Audio — codec, speaker, mic, headphone, amp IC\n"
                      "  7. 📶 Connectivity — WiFi, BT, GPS, NFC, cellular\n"
                      "  8. 💾 Storage & RAM — UFS/eMMC health, LPDDR type, SMART\n"
                      "  9. 🌡️ Thermal — temps, throttling, cooling devices\n\n"
                      "Requirements:\n"
                      "  • Device connected via USB with ADB debugging enabled\n")

    # Color tags
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#2ed573")
        tb.tag_configure("warning", foreground="#ffa502")
        tb.tag_configure("fault", foreground="#e94560")
        tb.tag_configure("info", foreground="#1e90ff")
        tb.tag_configure("header", foreground="#e94560", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#8892b0")
        tb.tag_configure("section", foreground="#1e90ff", font=("Consolas", 13, "bold"))

    _setup_tags()

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "🔴", "critical", "❌", "fail", "bad", "poor", "not found"]):
            return "fault"
        if any(k in t for k in ["warning", "🟡", "⚠️", "degraded", "worn"]):
            return "warning"
        if any(k in t for k in ["✅", "ok", "pass", "working", "good", "healthy", "detected", "active", "normal"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "▶▶▶"]):
            return "header"
        if any(k in t for k in ["🔍", "scanning", "testing", "checking"]):
            return "info"
        return None

    def _append(text):
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

    def _append_section(text):
        def _do():
            report_box.configure(state="normal")
            start = report_box._textbox.index("end-1c")
            report_box.insert("end", text + "\n")
            end = report_box._textbox.index("end-1c")
            report_box._textbox.tag_add("section", start, end)
            report_box.see("end")
        app.content.after(0, _do)

    # ── Run all tests ──
    def start_full_diagnostic():
        if running["value"]:
            return
        running["value"] = True

        # Reset UI
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        master_progress.set(0)
        overall_badge.configure(text="  🔄 Running...", text_color=colors["info"])
        master_msg.configure(text="Starting full device diagnostic...", text_color=colors["text_dim"])
        tests_passed_label.configure(text="")

        # Reset all section statuses
        for tid, sw in section_widgets.items():
            sw["status"].configure(text="⏸ Pending", text_color=colors["text_dim"])
            sw["progress"].set(0)
            sw["progress"].configure(progress_color=colors["info"])
            # Hide previous results
            sw["results_frame"].pack_forget()
            for child in sw["results_frame"].winfo_children():
                child.destroy()
            sw["result_labels"] = {}

        full_report = {"lines": []}

        def _track(text):
            full_report["lines"].append(text)
            _append(text)

        def run():
            import datetime as _dt
            import importlib

            _track("=" * 70)
            _track("  MOOXY AI FAULT DETECTOR — FULL DEVICE DIAGNOSTIC REPORT")
            _track("=" * 70)
            _track(f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            _track("=" * 70)
            _track("")

            total_tests = len(TEST_MODULES)
            passed = 0
            failed = 0
            warnings_count = 0
            all_results = {}

            for idx, test in enumerate(TEST_MODULES):
                tid = test["id"]
                sw = section_widgets[tid]
                test_num = idx + 1
                base_pct = idx / total_tests
                next_pct = (idx + 1) / total_tests

                # Update section status to "Running"
                app.content.after(0, lambda s=sw: s["status"].configure(
                    text="🔄 Running...", text_color=colors["info"]))
                app.content.after(0, lambda: master_msg.configure(
                    text=f"[{test_num}/{total_tests}] Testing {test['name']}..."))

                _track("")
                _append_section(f"▶▶▶ [{test_num}/{total_tests}] {test['icon']} {test['name']}")
                _track("─" * 50)

                result = None
                error_msg = None

                try:
                    mod = importlib.import_module(test["module"])
                    detect_fn = getattr(mod, test["func"])

                    def make_cb(s=sw, bp=base_pct, np=next_pct):
                        def cb(pct, msg):
                            # pct from module is 0-100, normalize to section
                            frac = pct / 100.0 if pct > 1 else pct
                            app.content.after(0, lambda: s["progress"].set(frac))
                            overall_pct = bp + frac * (np - bp)
                            app.content.after(0, lambda: master_progress.set(overall_pct))
                        return cb

                    result = detect_fn(callback=make_cb())
                    all_results[tid] = result

                except ImportError as e:
                    error_msg = f"Module not available: {e}"
                except Exception as e:
                    error_msg = f"Error: {e}"

                # Process result
                if error_msg:
                    _track(f"  ❌ {error_msg}")
                    app.content.after(0, lambda s=sw: s["status"].configure(
                        text="❌ Error", text_color=colors["accent"]))
                    app.content.after(0, lambda s=sw: s["progress"].configure(
                        progress_color=colors["accent"]))
                    app.content.after(0, lambda s=sw: s["progress"].set(1.0))
                    failed += 1
                elif result is not None:
                    # Extract health
                    health = str(getattr(result, test.get("health_key", "overall_health"), "Unknown"))
                    health_upper = health.upper()

                    # Show fields in report
                    for field_name, extractor in test["fields"]:
                        try:
                            val = extractor(result)
                        except Exception:
                            val = "—"
                        _track(f"  {field_name:.<28s} {val}")

                    # Populate result rows inside the section card
                    def _populate_results(s=sw, t=test, r=result):
                        s["results_frame"].pack(fill="x", padx=15, pady=(0, 8))
                        for field_name, extractor in t["fields"]:
                            try:
                                val = str(extractor(r))
                            except Exception:
                                val = "—"

                            row = ctk.CTkFrame(s["results_frame"],
                                               fg_color=colors["bg_light"], corner_radius=4, height=26)
                            row.pack(fill="x", pady=1)
                            row.pack_propagate(False)
                            ctk.CTkLabel(row, text=field_name, font=("Segoe UI", 10, "bold"),
                                         text_color=colors["text"], width=160, anchor="w").pack(side="left", padx=6)
                            # Color the value based on content
                            val_color = colors["text"]
                            val_lower = val.lower()
                            if any(k in val_lower for k in ["not found", "fail", "bad", "poor", "false", "error", "critical"]):
                                val_color = colors["accent"]
                            elif any(k in val_lower for k in ["warning", "degraded", "worn"]):
                                val_color = colors["warning"]
                            elif any(k in val_lower for k in ["ok", "good", "healthy", "true", "active", "normal", "detected"]):
                                val_color = colors["success"]
                            ctk.CTkLabel(row, text=val, font=("Consolas", 10),
                                         text_color=val_color, anchor="w").pack(side="left", fill="x", expand=True, padx=6)

                    app.content.after(0, _populate_results)

                    # Determine status
                    if health_upper in ("GOOD", "HEALTHY", "OK", "NORMAL"):
                        _track(f"  ✅ Status: {health}")
                        app.content.after(0, lambda s=sw, h=health: s["status"].configure(
                            text=f"✅ {h}", text_color=colors["success"]))
                        app.content.after(0, lambda s=sw: s["progress"].configure(
                            progress_color=colors["success"]))
                        passed += 1
                    elif health_upper in ("DEGRADED", "FAIR", "WORN", "PARTIAL"):
                        _track(f"  🟡 Status: {health}")
                        app.content.after(0, lambda s=sw, h=health: s["status"].configure(
                            text=f"🟡 {h}", text_color=colors["warning"]))
                        app.content.after(0, lambda s=sw: s["progress"].configure(
                            progress_color=colors["warning"]))
                        warnings_count += 1
                    elif health_upper in ("POOR", "BAD", "CRITICAL", "REPLACE"):
                        _track(f"  🔴 Status: {health}")
                        app.content.after(0, lambda s=sw, h=health: s["status"].configure(
                            text=f"🔴 {h}", text_color=colors["accent"]))
                        app.content.after(0, lambda s=sw: s["progress"].configure(
                            progress_color=colors["accent"]))
                        failed += 1
                    else:
                        _track(f"  ⚠️ Status: {health}")
                        app.content.after(0, lambda s=sw, h=health: s["status"].configure(
                            text=f"⚠️ {h}", text_color=colors["text_dim"]))
                        passed += 1

                    app.content.after(0, lambda s=sw: s["progress"].set(1.0))

                    # Show warnings from this module
                    mod_warnings = getattr(result, "warnings", [])
                    if mod_warnings:
                        for w in mod_warnings[:3]:
                            _track(f"  ⚠️ {w}")
                else:
                    _track("  ⚠️ No result returned")
                    app.content.after(0, lambda s=sw: s["status"].configure(
                        text="⚠️ No Data", text_color=colors["text_dim"]))
                    app.content.after(0, lambda s=sw: s["progress"].set(1.0))

                # Update master progress
                app.content.after(0, lambda p=next_pct: master_progress.set(p))

            # ═══ FINAL SUMMARY ═══
            _track("")
            _track("=" * 70)
            _track("  FULL DIAGNOSTIC SUMMARY")
            _track("=" * 70)
            _track(f"  Tests Run:     {total_tests}")
            _track(f"  Passed:        {passed}")
            _track(f"  Warnings:      {warnings_count}")
            _track(f"  Failed/Issues: {failed}")
            _track("")

            if failed == 0 and warnings_count == 0:
                verdict = "EXCELLENT"
                _track("  ✅ VERDICT: EXCELLENT — All systems healthy")
                app.content.after(0, lambda: overall_badge.configure(
                    text=f"  ✅ EXCELLENT ({passed}/{total_tests} passed)",
                    text_color=colors["success"]))
            elif failed == 0:
                verdict = "GOOD"
                _track(f"  🟡 VERDICT: GOOD — {warnings_count} warning(s) found")
                app.content.after(0, lambda: overall_badge.configure(
                    text=f"  🟡 GOOD ({warnings_count} warnings)",
                    text_color=colors["warning"]))
            elif failed <= 2:
                verdict = "NEEDS ATTENTION"
                _track(f"  🟡 VERDICT: NEEDS ATTENTION — {failed} issue(s) detected")
                app.content.after(0, lambda: overall_badge.configure(
                    text=f"  🟡 NEEDS ATTENTION ({failed} issues)",
                    text_color=colors["warning"]))
            else:
                verdict = "CRITICAL"
                _track(f"  🔴 VERDICT: CRITICAL — {failed} failures detected")
                app.content.after(0, lambda: overall_badge.configure(
                    text=f"  🔴 CRITICAL ({failed} failures)",
                    text_color=colors["accent"]))

            _track("")
            _track("=" * 70)
            _track("  Report generated by Mooxy AI Fault Detector v1.0")
            _track("=" * 70)

            app.content.after(0, lambda: master_progress.set(1.0))
            app.content.after(0, lambda: master_msg.configure(
                text=f"Full diagnostic complete — {passed} passed, {warnings_count} warnings, {failed} issues",
                text_color=colors["success"]))
            app.content.after(0, lambda: tests_passed_label.configure(
                text=f"{passed}✅  {warnings_count}🟡  {failed}🔴"))

            # Save report
            report_text = "\n".join(full_report["lines"])
            try:
                from app.gui.history_manager import get_unique_log_path, add_detection
                log_path = get_unique_log_path("full_diagnostic")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
                add_detection(
                    detection_type="FULL_DIAGNOSTIC",
                    device_name="Full Device Scan",
                    summary=f"Verdict: {verdict} | Passed: {passed} | Warnings: {warnings_count} | Failed: {failed}",
                    faults_count=failed,
                    faults_summary=f"{failed} test(s) with issues",
                    report_file=str(log_path),
                    extra={"verdict": verdict, "passed": passed, "warnings": warnings_count, "failed": failed}
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
            master_msg.configure(text="📋 Report copied to clipboard!", text_color=colors["success"])
        except Exception:
            pass

    def save_report():
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(defaultextension=".txt",
                                                 filetypes=[("Text", "*.txt")],
                                                 initialfile="full_diagnostic_report.txt")
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                master_msg.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="🩺 Start Full Diagnostic", width=320, height=50,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 16, "bold"), corner_radius=10,
                  command=start_full_diagnostic).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="📋 Copy Report", width=130, height=50,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="💾 Save Report", width=130, height=50,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    app.update_status("Full Diagnostic — Connect device via ADB and press Start")
