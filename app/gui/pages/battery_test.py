import customtkinter as ctk
import threading
from pathlib import Path
from app.gui.ui_utils import (
    get_line_tag, setup_report_tags, append_live, append_live_lines,
    safe_after, copy_report_to_clipboard, save_report_to_file,
)


def render_battery_test(app):
    """Advanced Battery Testing page — thermistor, charging IC, fast charge, health analysis.
    Shows detections LIVE as they happen — real-time append with color-coded output."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="🔋 Advanced Battery Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Deep battery diagnostics — thermistor, charging IC, fast charge protocols, health analysis",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card: What battery testing detects ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="🔍 Battery Testing Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ Thermistor — Presence, resistance, temperature reading, NTC/PTC type",
        "✅ Battery ID — Manufacturer, chemistry, design capacity, cycle count",
        "✅ Charging IC — Controller chip, input/charge voltage & current, status",
        "✅ Fast Charge — Supported protocols (QC/PD/VOOC/AFC), max wattage, adapter type",
        "✅ Health Analysis — Capacity fade, internal resistance, wear level, estimated life",
        "✅ Voltage & Current — Real-time battery voltage, charge/discharge current",
        "✅ Temperature — Battery temp, thermistor validation, thermal safety",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Overall Battery Health Badge ──
    badge_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=55)
    badge_frame.pack(fill="x", padx=20, pady=(0, 10))
    badge_frame.pack_propagate(False)
    badge_inner = ctk.CTkFrame(badge_frame, fg_color="transparent")
    badge_inner.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(badge_inner, text="Overall Battery Health:",
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

    # ── Battery Info card ──
    batt_info_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    batt_info_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(batt_info_card, text="🔋 Battery Info",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    batt_info_fields = [
        ("batt_manufacturer", "Manufacturer"),
        ("batt_chemistry", "Chemistry"),
        ("batt_capacity", "Design Capacity"),
        ("batt_voltage", "Voltage"),
        ("batt_current", "Current"),
        ("batt_temp", "Temperature"),
        ("batt_cycle_count", "Cycle Count"),
        ("batt_health_pct", "Health %"),
    ]
    batt_info_labels = {}
    for key, name in batt_info_fields:
        row = ctk.CTkFrame(batt_info_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        batt_info_labels[key] = (val, dot)
    ctk.CTkFrame(batt_info_card, fg_color="transparent", height=8).pack()

    # ── Thermistor card ──
    therm_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    therm_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(therm_card, text="🌡️ Thermistor",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    therm_fields = [
        ("therm_present", "Presence"),
        ("therm_resistance", "Resistance"),
        ("therm_temperature", "Temperature"),
        ("therm_type", "Type (NTC/PTC)"),
    ]
    therm_labels = {}
    for key, name in therm_fields:
        row = ctk.CTkFrame(therm_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        therm_labels[key] = (val, dot)
    ctk.CTkFrame(therm_card, fg_color="transparent", height=8).pack()

    # ── Battery Health Detail card ──
    health_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    health_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(health_card, text="📊 Battery Health Detail",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    health_fields = [
        ("health_capacity_fade", "Capacity Fade"),
        ("health_internal_resistance", "Internal Resistance"),
        ("health_wear_level", "Wear Level"),
        ("health_estimated_life", "Estimated Life"),
    ]
    health_labels = {}
    for key, name in health_fields:
        row = ctk.CTkFrame(health_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        health_labels[key] = (val, dot)
    ctk.CTkFrame(health_card, fg_color="transparent", height=8).pack()

    # ── Charging IC card ──
    charge_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    charge_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(charge_card, text="⚡ Charging IC",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    charge_fields = [
        ("charge_ic_name", "IC Name"),
        ("charge_ic_mfg", "Manufacturer"),
        ("charge_input_voltage", "Input Voltage"),
        ("charge_input_current", "Input Current"),
        ("charge_voltage", "Charge Voltage"),
        ("charge_current", "Charge Current"),
        ("charge_status", "Status"),
    ]
    charge_labels = {}
    for key, name in charge_fields:
        row = ctk.CTkFrame(charge_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        charge_labels[key] = (val, dot)
    ctk.CTkFrame(charge_card, fg_color="transparent", height=8).pack()

    # ── Fast Charge card ──
    fast_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    fast_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(fast_card, text="🚀 Fast Charge",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    fast_fields = [
        ("fast_protocols", "Protocols Supported"),
        ("fast_active", "Active Protocol"),
        ("fast_max_wattage", "Max Wattage"),
        ("fast_adapter_type", "Adapter Type"),
    ]
    fast_labels = {}
    for key, name in fast_fields:
        row = ctk.CTkFrame(fast_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
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
        fast_labels[key] = (val, dot)
    ctk.CTkFrame(fast_card, fg_color="transparent", height=8).pack()

    # ── Live append helpers (using shared utilities) ──
    def _append_live(text):
        append_live(app, report_box, text)

    def _append_live_lines(lines):
        append_live_lines(app, report_box, lines)

    def _append_section_header(title):
        """Append a visible section header."""
        _append_live("")
        _append_live(f"{'=' * 60}")
        _append_live(f"  {title}")
        _append_live(f"{'=' * 60}")
        _append_live("")

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
        msg_label.configure(text="Initializing battery detection...", text_color=colors["text_dim"])

        # Reset all field labels
        for labels_dict in [batt_info_labels, therm_labels, charge_labels, fast_labels, health_labels]:
            for key, (v, d) in labels_dict.items():
                v.configure(text="—", text_color=colors["text_dim"])
                d.configure(text_color=colors["text_dim"])

        full_report = {"lines": []}

        def _track_and_append(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_and_append_lines(lines):
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            import datetime as _dt

            # ── Report Header ──
            header = [
                "=" * 70,
                "  MOOXY AI FAULT DETECTOR — ADVANCED BATTERY TEST REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70,
                "",
            ]
            _track_and_append_lines(header)

            result = None
            try:
                from app.hardware.battery_tester import detect_battery_status

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                _track_and_append("🔍 Scanning battery subsystem...")
                _track_and_append("")

                result = detect_battery_status(callback=cb)

                # ═══ PHASE 1: BATTERY INFO ═══
                _track_and_append("")
                _track_and_append("═══ PHASE 1: BATTERY INFORMATION ═══")
                _track_and_append("")

                batt = getattr(result, "battery_info", None) or {}
                if isinstance(batt, dict) and batt:
                    mfg = batt.get("manufacturer", "Unknown")
                    chem = batt.get("chemistry", "Unknown")
                    cap = batt.get("design_capacity", "Unknown")
                    volt = batt.get("voltage", "Unknown")
                    curr = batt.get("current", "Unknown")
                    temp = batt.get("temperature", "Unknown")
                    cycles = batt.get("cycle_count", "Unknown")
                    health_pct = batt.get("health_percent", "Unknown")

                    _track_and_append(f"  Manufacturer:    {mfg}")
                    _track_and_append(f"  Chemistry:       {chem}")
                    _track_and_append(f"  Design Capacity: {cap}")
                    _track_and_append(f"  Voltage:         {volt}")
                    _track_and_append(f"  Current:         {curr}")
                    _track_and_append(f"  Temperature:     {temp}")
                    _track_and_append(f"  Cycle Count:     {cycles}")
                    _track_and_append(f"  Health:          {health_pct}")

                    _set_field(batt_info_labels, "batt_manufacturer", mfg)
                    _set_field(batt_info_labels, "batt_chemistry", chem)
                    _set_field(batt_info_labels, "batt_capacity", cap)
                    _set_field(batt_info_labels, "batt_voltage", volt)
                    _set_field(batt_info_labels, "batt_current", curr)
                    _set_field(batt_info_labels, "batt_temp", temp)
                    _set_field(batt_info_labels, "batt_cycle_count", cycles,
                               ok=_is_cycle_ok(cycles))
                    _set_field(batt_info_labels, "batt_health_pct", health_pct,
                               ok=_is_health_ok(health_pct))
                else:
                    _track_and_append("  ⚠️ Battery info not available")

                app.content.after(0, lambda: progress.set(0.25))

                # ═══ PHASE 2: THERMISTOR ═══
                _track_and_append("")
                _track_and_append("═══ PHASE 2: THERMISTOR DETECTION ═══")
                _track_and_append("")

                therm = getattr(result, "thermistor", None) or {}
                if isinstance(therm, dict) and therm:
                    present = therm.get("present", "Unknown")
                    resistance = therm.get("resistance", "Unknown")
                    therm_temp = therm.get("temperature", "Unknown")
                    therm_type = therm.get("type", "Unknown")

                    present_str = str(present)
                    is_present = present_str.lower() in ("true", "yes", "detected", "1")

                    if is_present:
                        _track_and_append(f"  ✅ Thermistor Detected")
                    else:
                        _track_and_append(f"  ❌ Thermistor NOT Detected — possible open/missing")
                    _track_and_append(f"  Resistance:   {resistance}")
                    _track_and_append(f"  Temperature:  {therm_temp}")
                    _track_and_append(f"  Type:         {therm_type}")

                    _set_field(therm_labels, "therm_present", "Detected" if is_present else "NOT Detected",
                               ok=is_present)
                    _set_field(therm_labels, "therm_resistance", resistance)
                    _set_field(therm_labels, "therm_temperature", therm_temp)
                    _set_field(therm_labels, "therm_type", therm_type)
                else:
                    _track_and_append("  ⚠️ Thermistor data not available")

                app.content.after(0, lambda: progress.set(0.45))

                # ═══ PHASE 3: CHARGING IC ═══
                _track_and_append("")
                _track_and_append("═══ PHASE 3: CHARGING IC DETECTION ═══")
                _track_and_append("")

                charge = getattr(result, "charging_ic", None) or {}
                if isinstance(charge, dict) and charge:
                    ic_name = charge.get("ic_name", "Unknown")
                    ic_mfg = charge.get("manufacturer", "Unknown")
                    in_volt = charge.get("input_voltage", "Unknown")
                    in_curr = charge.get("input_current", "Unknown")
                    ch_volt = charge.get("charge_voltage", "Unknown")
                    ch_curr = charge.get("charge_current", "Unknown")
                    ch_status = charge.get("status", "Unknown")

                    _track_and_append(f"  IC Name:        {ic_name}")
                    _track_and_append(f"  Manufacturer:   {ic_mfg}")
                    _track_and_append(f"  Input Voltage:  {in_volt}")
                    _track_and_append(f"  Input Current:  {in_curr}")
                    _track_and_append(f"  Charge Voltage: {ch_volt}")
                    _track_and_append(f"  Charge Current: {ch_curr}")

                    status_ok = ch_status.lower() in ("charging", "full", "ok", "normal", "not charging")
                    icon = "✅" if status_ok else "⚠️"
                    _track_and_append(f"  {icon} Status: {ch_status}")

                    _set_field(charge_labels, "charge_ic_name", ic_name)
                    _set_field(charge_labels, "charge_ic_mfg", ic_mfg)
                    _set_field(charge_labels, "charge_input_voltage", in_volt)
                    _set_field(charge_labels, "charge_input_current", in_curr)
                    _set_field(charge_labels, "charge_voltage", ch_volt)
                    _set_field(charge_labels, "charge_current", ch_curr)
                    _set_field(charge_labels, "charge_status", ch_status, ok=status_ok)
                else:
                    _track_and_append("  ⚠️ Charging IC data not available")

                app.content.after(0, lambda: progress.set(0.65))

                # ═══ PHASE 4: FAST CHARGE ═══
                _track_and_append("")
                _track_and_append("═══ PHASE 4: FAST CHARGE PROTOCOLS ═══")
                _track_and_append("")

                fast = getattr(result, "fast_charge", None) or {}
                if isinstance(fast, dict) and fast:
                    protocols = fast.get("protocols_supported", "None")
                    active = fast.get("active_protocol", "None")
                    max_w = fast.get("max_wattage", "Unknown")
                    adapter = fast.get("adapter_type", "Unknown")

                    if isinstance(protocols, list):
                        protocols_str = ", ".join(protocols) if protocols else "None"
                    else:
                        protocols_str = str(protocols)

                    _track_and_append(f"  Protocols:      {protocols_str}")
                    _track_and_append(f"  Active:         {active}")
                    _track_and_append(f"  Max Wattage:    {max_w}")
                    _track_and_append(f"  Adapter Type:   {adapter}")

                    has_fast = protocols_str.lower() != "none" and protocols_str.strip() != ""
                    if has_fast:
                        _track_and_append(f"  ✅ Fast charging supported")
                    else:
                        _track_and_append(f"  ⚠️ No fast charge protocols detected")

                    _set_field(fast_labels, "fast_protocols", protocols_str, ok=has_fast)
                    _set_field(fast_labels, "fast_active", active,
                               ok=str(active).lower() not in ("none", "unknown", ""))
                    _set_field(fast_labels, "fast_max_wattage", max_w)
                    _set_field(fast_labels, "fast_adapter_type", adapter)
                else:
                    _track_and_append("  ⚠️ Fast charge data not available")

                app.content.after(0, lambda: progress.set(0.80))

                # ═══ PHASE 5: HEALTH ANALYSIS ═══
                _track_and_append("")
                _track_and_append("═══ PHASE 5: BATTERY HEALTH ANALYSIS ═══")
                _track_and_append("")

                health = getattr(result, "health_detail", None) or {}
                if isinstance(health, dict) and health:
                    cap_fade = health.get("capacity_fade", "Unknown")
                    int_res = health.get("internal_resistance", "Unknown")
                    wear = health.get("wear_level", "Unknown")
                    est_life = health.get("estimated_life", "Unknown")

                    _track_and_append(f"  Capacity Fade:       {cap_fade}")
                    _track_and_append(f"  Internal Resistance: {int_res}")
                    _track_and_append(f"  Wear Level:          {wear}")
                    _track_and_append(f"  Estimated Life:      {est_life}")

                    _set_field(health_labels, "health_capacity_fade", cap_fade,
                               ok=_is_fade_ok(cap_fade))
                    _set_field(health_labels, "health_internal_resistance", int_res)
                    _set_field(health_labels, "health_wear_level", wear,
                               ok=_is_wear_ok(wear))
                    _set_field(health_labels, "health_estimated_life", est_life)

                    # Determine overall health verdict
                    wear_ok = _is_wear_ok(wear)
                    fade_ok = _is_fade_ok(cap_fade)
                    if wear_ok and fade_ok:
                        _track_and_append("")
                        _track_and_append("  ✅ Battery health is GOOD")
                    elif not wear_ok and not fade_ok:
                        _track_and_append("")
                        _track_and_append("  🔴 Battery health is POOR — replacement recommended")
                    else:
                        _track_and_append("")
                        _track_and_append("  🟡 Battery health is DEGRADED — monitor closely")
                else:
                    _track_and_append("  ⚠️ Health detail data not available")

                app.content.after(0, lambda: progress.set(0.95))

                # ═══ OVERALL VERDICT ═══
                _track_and_append("")
                _track_and_append("═══ OVERALL BATTERY VERDICT ═══")
                _track_and_append("")

                overall = getattr(result, "overall_health", None) or "Unknown"
                overall_str = str(overall).upper()

                if overall_str in ("GOOD", "HEALTHY", "OK", "NORMAL"):
                    _track_and_append(f"  ✅ OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  ✅ {overall_str}", text_color=colors["success"]))
                elif overall_str in ("DEGRADED", "FAIR", "WORN"):
                    _track_and_append(f"  🟡 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  🟡 {overall_str}", text_color=colors["warning"]))
                elif overall_str in ("POOR", "BAD", "CRITICAL", "REPLACE"):
                    _track_and_append(f"  🔴 OVERALL: {overall_str} — Battery replacement needed")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  🔴 {overall_str}", text_color=colors["accent"]))
                else:
                    _track_and_append(f"  ⚠️ OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  ⚠️ {overall_str}", text_color=colors["text_dim"]))

            except ImportError:
                _track_and_append("  ❌ Battery tester module not found")
                _track_and_append("  Install: app/hardware/battery_tester.py required")
                app.content.after(0, lambda: health_badge.configure(
                    text="  ❌ Module Error", text_color=colors["accent"]))
            except Exception as e:
                _track_and_append(f"  ❌ Battery detection error: {str(e)}")
                app.content.after(0, lambda: health_badge.configure(
                    text="  ❌ Error", text_color=colors["accent"]))

            # ── Footer ──
            _track_and_append("")
            _track_and_append("=" * 70)
            _track_and_append("  Report generated by Mooxy AI Fault Detector v1.0")
            _track_and_append("=" * 70)

            report_text = "\n".join(full_report["lines"])

            # Final UI updates
            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Battery test complete — full report above", text_color=colors["success"]))

            # Auto-save to file
            from app.gui.history_manager import get_unique_log_path
            log_path = get_unique_log_path("battery_report")
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
            except Exception:
                pass

            # Save to history
            try:
                from app.gui.history_manager import add_detection

                device_name = "Battery Test"
                summary_text = "Battery diagnostics completed"
                faults_count = 0
                faults_summary = ""

                if result:
                    overall_h = str(getattr(result, "overall_health", "Unknown"))
                    batt_i = getattr(result, "battery_info", {}) or {}
                    if isinstance(batt_i, dict):
                        device_name = f"Battery ({batt_i.get('manufacturer', 'Unknown')})"
                        summary_text = (
                            f"Health: {overall_h} | "
                            f"Capacity: {batt_i.get('design_capacity', '?')} | "
                            f"Cycles: {batt_i.get('cycle_count', '?')}"
                        )
                    if overall_h.upper() in ("POOR", "BAD", "CRITICAL", "REPLACE"):
                        faults_count = 1
                        faults_summary = "Battery replacement recommended"

                add_detection(
                    detection_type="BATTERY",
                    device_name=device_name,
                    summary=summary_text,
                    faults_count=faults_count,
                    faults_summary=faults_summary,
                    report_file=str(log_path),
                    extra={
                        "overall_health": str(getattr(result, "overall_health", "Unknown")) if result else "Unknown",
                    }
                )
            except Exception as e:
                print(f"[Battery Test] History save error: {e}")

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    # ── Helper functions for health evaluation ──
    def _is_cycle_ok(cycles):
        try:
            c = int(str(cycles).replace(",", "").strip())
            return c < 500
        except (ValueError, TypeError):
            return True

    def _is_health_ok(health):
        try:
            h = float(str(health).replace("%", "").strip())
            return h >= 80
        except (ValueError, TypeError):
            return True

    def _is_fade_ok(fade):
        try:
            f = float(str(fade).replace("%", "").strip())
            return f < 20
        except (ValueError, TypeError):
            return True

    def _is_wear_ok(wear):
        try:
            w_str = str(wear).lower().strip()
            if w_str in ("low", "minimal", "none", "good"):
                return True
            if w_str in ("high", "severe", "critical", "bad"):
                return False
            w = float(w_str.replace("%", ""))
            return w < 50
        except (ValueError, TypeError):
            return True

    # ── Copy / Save buttons ──
    def copy_report():
        copy_report_to_clipboard(app, report_box, status_label=msg_label, colors=colors)

    def save_report():
        save_report_to_file(app, report_box, default_prefix="battery_report",
                            status_label=msg_label, colors=colors)

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="🔋 Start Battery Detection", width=300, height=46,
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
                      "Press 'Start Battery Detection' to begin.\n\n"
                      "Requirements:\n"
                      "• Device connected via USB with ADB enabled\n"
                      "• OR device in EDL/UART mode for raw battery data\n\n"
                      "Tests performed:\n"
                      "  1. Battery info (manufacturer, capacity, voltage)\n"
                      "  2. Thermistor check (NTC/PTC presence & reading)\n"
                      "  3. Charging IC detection (controller chip status)\n"
                      "  4. Fast charge protocol scan (QC/PD/VOOC/AFC)\n"
                      "  5. Health analysis (fade, resistance, wear, life)\n")
    setup_report_tags(report_box)

    app.update_status("Battery Test — Connect device and press Start")
