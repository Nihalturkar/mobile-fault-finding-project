import customtkinter as ctk
import threading
from app.gui.ui_utils import (
    get_line_tag, setup_report_tags, append_live, append_live_lines,
    safe_after, copy_report_to_clipboard, save_report_to_file,
)


def render_sensor_test(app):
    """Sensor Testing page — accelerometer, gyroscope, proximity, light, magnetometer, barometer.
    Shows detections LIVE as they happen — real-time append with color-coded output."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="📡 Sensor Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Full sensor diagnosis — accelerometer, gyroscope, proximity, light, magnetometer, barometer",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="🔍 Sensor Testing Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ Accelerometer — IC identification, vendor, resolution, max range, status",
        "✅ Gyroscope — Rotation sensor IC, calibration, drift detection",
        "✅ Magnetometer — Compass IC, magnetic field strength, calibration",
        "✅ Proximity — Near/far sensor IC, threshold, response status",
        "✅ Ambient Light — Lux sensor IC, current reading, sensitivity",
        "✅ Barometer — Pressure sensor presence, altitude estimation",
        "✅ Gravity & Step Counter — Virtual/hardware sensor status",
        "✅ Sensor IC Identification — Bosch, STMicro, InvenSense, AKM, Kionix, Vishay",
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
    ctk.CTkLabel(badge_inner, text="Overall Sensor Health:",
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

    cards_left = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_left.pack(side="left", fill="both", expand=True, padx=(0, 5))
    cards_right = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_right.pack(side="left", fill="both", expand=True, padx=(5, 0))

    # ── Accelerometer card ──
    accel_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    accel_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(accel_card, text="📐 Accelerometer",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    accel_fields = [
        ("accel_name", "Sensor Name"),
        ("accel_vendor", "Vendor/IC"),
        ("accel_resolution", "Resolution"),
        ("accel_range", "Max Range"),
        ("accel_power", "Power"),
        ("accel_status", "Status"),
    ]
    accel_labels = {}
    for key, name in accel_fields:
        row = ctk.CTkFrame(accel_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        accel_labels[key] = (val, dot)
    ctk.CTkFrame(accel_card, fg_color="transparent", height=8).pack()

    # ── Gyroscope card ──
    gyro_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    gyro_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(gyro_card, text="🔄 Gyroscope",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    gyro_fields = [
        ("gyro_name", "Sensor Name"),
        ("gyro_vendor", "Vendor/IC"),
        ("gyro_resolution", "Resolution"),
        ("gyro_range", "Max Range"),
        ("gyro_status", "Status"),
    ]
    gyro_labels = {}
    for key, name in gyro_fields:
        row = ctk.CTkFrame(gyro_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        gyro_labels[key] = (val, dot)
    ctk.CTkFrame(gyro_card, fg_color="transparent", height=8).pack()

    # ── Magnetometer card ──
    mag_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    mag_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(mag_card, text="🧭 Magnetometer",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    mag_fields = [
        ("mag_name", "Sensor Name"),
        ("mag_vendor", "Vendor/IC"),
        ("mag_resolution", "Resolution"),
        ("mag_status", "Status"),
    ]
    mag_labels = {}
    for key, name in mag_fields:
        row = ctk.CTkFrame(mag_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        mag_labels[key] = (val, dot)
    ctk.CTkFrame(mag_card, fg_color="transparent", height=8).pack()

    # ── Proximity card ──
    prox_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    prox_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(prox_card, text="👋 Proximity Sensor",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    prox_fields = [
        ("prox_name", "Sensor Name"),
        ("prox_vendor", "Vendor/IC"),
        ("prox_range", "Max Range"),
        ("prox_status", "Status"),
    ]
    prox_labels = {}
    for key, name in prox_fields:
        row = ctk.CTkFrame(prox_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        prox_labels[key] = (val, dot)
    ctk.CTkFrame(prox_card, fg_color="transparent", height=8).pack()

    # ── Light Sensor card ──
    light_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    light_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(light_card, text="💡 Ambient Light Sensor",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    light_fields = [
        ("light_name", "Sensor Name"),
        ("light_vendor", "Vendor/IC"),
        ("light_range", "Max Range"),
        ("light_power", "Power"),
        ("light_status", "Status"),
    ]
    light_labels = {}
    for key, name in light_fields:
        row = ctk.CTkFrame(light_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        light_labels[key] = (val, dot)
    ctk.CTkFrame(light_card, fg_color="transparent", height=8).pack()

    # ── Barometer card ──
    baro_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    baro_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(baro_card, text="🌡️ Barometer / Other",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    baro_fields = [
        ("baro_name", "Barometer"),
        ("baro_vendor", "Vendor/IC"),
        ("gravity_status", "Gravity Sensor"),
        ("step_status", "Step Counter"),
    ]
    baro_labels = {}
    for key, name in baro_fields:
        row = ctk.CTkFrame(baro_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        baro_labels[key] = (val, dot)
    ctk.CTkFrame(baro_card, fg_color="transparent", height=8).pack()

    # ── Live append helpers (using shared utilities) ──
    def _append_live(text):
        append_live(app, report_box, text)

    def _append_live_lines(lines):
        append_live_lines(app, report_box, lines)

    def _set_field(labels_dict, key, value, ok=True):
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

        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        progress.set(0)
        health_badge.configure(text="  🔄 Testing...", text_color=colors["info"])
        msg_label.configure(text="Initializing sensor detection...", text_color=colors["text_dim"])

        for labels_dict in [accel_labels, gyro_labels, mag_labels, prox_labels, light_labels, baro_labels]:
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

            header = [
                "=" * 70,
                "  MOOXY AI FAULT DETECTOR — SENSOR TEST REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70, "",
            ]
            _track_lines(header)

            result = None
            try:
                from app.hardware.sensor_tester import detect_sensor_status

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct / 100.0 if pct > 1 else pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                _track("🔍 Scanning device sensors...")
                _track("")

                result = detect_sensor_status(callback=cb)

                # ═══ ACCELEROMETER ═══
                _track("")
                _track("═══ PHASE 1: ACCELEROMETER ═══")
                _track("")

                accel = getattr(result, "accelerometer", None)
                if accel and accel.name:
                    _track(f"  ✅ Accelerometer Detected")
                    _track(f"  Name:       {accel.name}")
                    _track(f"  Vendor/IC:  {accel.vendor} / {accel.ic_name}")
                    _track(f"  Resolution: {accel.resolution}")
                    _track(f"  Max Range:  {accel.max_range}")
                    _track(f"  Power:      {accel.power_consumption}")
                    _track(f"  Status:     {accel.status}")
                    _set_field(accel_labels, "accel_name", accel.name)
                    _set_field(accel_labels, "accel_vendor", f"{accel.vendor} / {accel.ic_name}" if accel.ic_name else accel.vendor)
                    _set_field(accel_labels, "accel_resolution", accel.resolution)
                    _set_field(accel_labels, "accel_range", accel.max_range)
                    _set_field(accel_labels, "accel_power", accel.power_consumption)
                    _set_field(accel_labels, "accel_status", accel.status, ok=accel.status.lower() in ("ok", "active", "working"))
                    if accel.common_failures:
                        _track("  ⚠️ Known issues for this IC:")
                        for f in accel.common_failures:
                            _track(f"    • {f}")
                else:
                    _track("  ❌ Accelerometer NOT FOUND")
                    _set_field(accel_labels, "accel_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.25))

                # ═══ GYROSCOPE ═══
                _track("")
                _track("═══ PHASE 2: GYROSCOPE ═══")
                _track("")

                gyro = getattr(result, "gyroscope", None)
                if gyro and gyro.name:
                    _track(f"  ✅ Gyroscope Detected")
                    _track(f"  Name:       {gyro.name}")
                    _track(f"  Vendor/IC:  {gyro.vendor} / {gyro.ic_name}")
                    _track(f"  Resolution: {gyro.resolution}")
                    _track(f"  Max Range:  {gyro.max_range}")
                    _track(f"  Status:     {gyro.status}")
                    _set_field(gyro_labels, "gyro_name", gyro.name)
                    _set_field(gyro_labels, "gyro_vendor", f"{gyro.vendor} / {gyro.ic_name}" if gyro.ic_name else gyro.vendor)
                    _set_field(gyro_labels, "gyro_resolution", gyro.resolution)
                    _set_field(gyro_labels, "gyro_range", gyro.max_range)
                    _set_field(gyro_labels, "gyro_status", gyro.status, ok=gyro.status.lower() in ("ok", "active", "working"))
                else:
                    _track("  ❌ Gyroscope NOT FOUND")
                    _set_field(gyro_labels, "gyro_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.40))

                # ═══ MAGNETOMETER ═══
                _track("")
                _track("═══ PHASE 3: MAGNETOMETER ═══")
                _track("")

                mag = getattr(result, "magnetometer", None)
                if mag and mag.name:
                    _track(f"  ✅ Magnetometer Detected")
                    _track(f"  Name:       {mag.name}")
                    _track(f"  Vendor/IC:  {mag.vendor} / {mag.ic_name}")
                    _track(f"  Resolution: {mag.resolution}")
                    _track(f"  Status:     {mag.status}")
                    _set_field(mag_labels, "mag_name", mag.name)
                    _set_field(mag_labels, "mag_vendor", f"{mag.vendor} / {mag.ic_name}" if mag.ic_name else mag.vendor)
                    _set_field(mag_labels, "mag_resolution", mag.resolution)
                    _set_field(mag_labels, "mag_status", mag.status, ok=mag.status.lower() in ("ok", "active", "working"))
                else:
                    _track("  ⚠️ Magnetometer not found (some devices lack this sensor)")
                    _set_field(mag_labels, "mag_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.55))

                # ═══ PROXIMITY ═══
                _track("")
                _track("═══ PHASE 4: PROXIMITY SENSOR ═══")
                _track("")

                prox = getattr(result, "proximity", None)
                if prox and prox.name:
                    _track(f"  ✅ Proximity Sensor Detected")
                    _track(f"  Name:       {prox.name}")
                    _track(f"  Vendor/IC:  {prox.vendor} / {prox.ic_name}")
                    _track(f"  Max Range:  {prox.max_range}")
                    _track(f"  Status:     {prox.status}")
                    _set_field(prox_labels, "prox_name", prox.name)
                    _set_field(prox_labels, "prox_vendor", f"{prox.vendor} / {prox.ic_name}" if prox.ic_name else prox.vendor)
                    _set_field(prox_labels, "prox_range", prox.max_range)
                    _set_field(prox_labels, "prox_status", prox.status, ok=prox.status.lower() in ("ok", "active", "working"))
                else:
                    _track("  ❌ Proximity Sensor NOT FOUND")
                    _set_field(prox_labels, "prox_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.70))

                # ═══ LIGHT SENSOR ═══
                _track("")
                _track("═══ PHASE 5: AMBIENT LIGHT SENSOR ═══")
                _track("")

                light = getattr(result, "light_sensor", None)
                if light and light.name:
                    _track(f"  ✅ Light Sensor Detected")
                    _track(f"  Name:       {light.name}")
                    _track(f"  Vendor/IC:  {light.vendor} / {light.ic_name}")
                    _track(f"  Max Range:  {light.max_range}")
                    _track(f"  Power:      {light.power_consumption}")
                    _track(f"  Status:     {light.status}")
                    _set_field(light_labels, "light_name", light.name)
                    _set_field(light_labels, "light_vendor", f"{light.vendor} / {light.ic_name}" if light.ic_name else light.vendor)
                    _set_field(light_labels, "light_range", light.max_range)
                    _set_field(light_labels, "light_power", light.power_consumption)
                    _set_field(light_labels, "light_status", light.status, ok=light.status.lower() in ("ok", "active", "working"))
                else:
                    _track("  ❌ Light Sensor NOT FOUND")
                    _set_field(light_labels, "light_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.82))

                # ═══ BAROMETER & OTHER ═══
                _track("")
                _track("═══ PHASE 6: BAROMETER & OTHER SENSORS ═══")
                _track("")

                baro = getattr(result, "barometer", None)
                if baro and baro.name:
                    _track(f"  ✅ Barometer Detected: {baro.name}")
                    _set_field(baro_labels, "baro_name", baro.name)
                    _set_field(baro_labels, "baro_vendor", baro.vendor)
                else:
                    _track("  ⚠️ Barometer not found (optional sensor)")
                    _set_field(baro_labels, "baro_name", "Not Present", ok=False)

                gravity = getattr(result, "gravity", None)
                if gravity and gravity.name:
                    _track(f"  ✅ Gravity Sensor: {gravity.status}")
                    _set_field(baro_labels, "gravity_status", gravity.status, ok=True)
                else:
                    _set_field(baro_labels, "gravity_status", "Not Found", ok=False)

                step = getattr(result, "step_counter", None)
                if step and step.name:
                    _track(f"  ✅ Step Counter: {step.status}")
                    _set_field(baro_labels, "step_status", step.status, ok=True)
                else:
                    _set_field(baro_labels, "step_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.92))

                # ═══ SUMMARY ═══
                _track("")
                _track("═══ SENSOR HEALTH SUMMARY ═══")
                _track("")

                found = getattr(result, "sensors_found", 0)
                score = getattr(result, "health_score", 0)
                overall = getattr(result, "overall_health", "Unknown")
                _track(f"  Sensors Found: {found}")
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
                _track("  ❌ Sensor tester module not found")
                _track("  Install: app/hardware/sensor_tester.py required")
                app.content.after(0, lambda: health_badge.configure(
                    text="  ❌ Module Error", text_color=colors["accent"]))
            except Exception as e:
                _track(f"  ❌ Sensor detection error: {str(e)}")
                app.content.after(0, lambda: health_badge.configure(
                    text="  ❌ Error", text_color=colors["accent"]))

            _track("")
            _track("=" * 70)
            _track("  Report generated by Mooxy AI Fault Detector v1.0")
            _track("=" * 70)

            report_text = "\n".join(full_report["lines"])

            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Sensor test complete — full report above", text_color=colors["success"]))

            try:
                from app.gui.history_manager import get_unique_log_path, add_detection
                log_path = get_unique_log_path("sensor_report")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
                add_detection(
                    detection_type="SENSOR",
                    device_name="Sensor Test",
                    summary=f"Found {getattr(result, 'sensors_found', 0)} sensors | Health: {getattr(result, 'overall_health', 'Unknown')}",
                    faults_count=len(getattr(result, 'warnings', [])),
                    faults_summary="; ".join(getattr(result, 'warnings', [])[:3]),
                    report_file=str(log_path),
                    extra={"health_score": getattr(result, 'health_score', 0)} if result else {}
                )
            except Exception:
                pass

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    def copy_report():
        copy_report_to_clipboard(app, report_box, status_label=msg_label, colors=colors)

    def save_report():
        save_report_to_file(app, report_box, default_prefix="sensor_report",
                            status_label=msg_label, colors=colors)

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="📡 Start Sensor Detection", width=300, height=46,
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
                      "Press 'Start Sensor Detection' to begin.\n\n"
                      "Requirements:\n"
                      "• Device connected via USB with ADB enabled\n\n"
                      "Tests performed:\n"
                      "  1. Accelerometer detection & IC identification\n"
                      "  2. Gyroscope testing & calibration check\n"
                      "  3. Magnetometer (compass) status\n"
                      "  4. Proximity sensor verification\n"
                      "  5. Ambient light sensor check\n"
                      "  6. Barometer, gravity, step counter\n"
                      "  7. Sensor IC matching (Bosch, STMicro, InvenSense, AKM)\n")
    setup_report_tags(report_box)

    app.update_status("Sensor Test — Connect device and press Start")
