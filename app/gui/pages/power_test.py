import customtkinter as ctk
import threading
import datetime as _dt
from pathlib import Path
from app.gui.ui_utils import (
    get_line_tag, setup_report_tags, append_live, append_live_lines,
    safe_after, copy_report_to_clipboard, save_report_to_file,
)


def render_power_test(app):
    """Power / Voltage Testing page — reads PMIC, regulators, power rails, short-circuit analysis."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="⚡ Power / Voltage Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content, text="PMIC registers, regulator voltages, power rails, and short-circuit detection via ADB",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card: what power testing can detect ──
    info_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info_card.pack(fill="x", padx=20, pady=(0, 10))
    ctk.CTkLabel(info_card, text="🔎 What Power Testing Can Detect",
                 font=("Segoe UI", 14, "bold"), text_color=colors["text"]).pack(anchor="w", padx=15, pady=(12, 5))
    capabilities = [
        "• PMIC register reading — identify PMIC model, revision, SPMI bus status",
        "• Buck/LDO voltage measurement — read all regulator outputs in real-time",
        "• Power rail monitoring — compare actual vs expected voltages per chipset",
        "• Short circuit detection — voltage drop analysis, overcurrent, low-resistance faults",
    ]
    for cap in capabilities:
        ctk.CTkLabel(info_card, text=cap, font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    # bottom padding
    ctk.CTkFrame(info_card, height=8, fg_color="transparent").pack()

    # ── Summary bar ──
    summary_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=50)
    summary_frame.pack(fill="x", padx=20, pady=(0, 10))
    summary_frame.pack_propagate(False)
    summary_label = ctk.CTkLabel(summary_frame, text="Press Start to begin power testing...",
                                  font=("Segoe UI", 14), text_color=colors["text_dim"])
    summary_label.pack(side="left", padx=20, pady=10)

    # ── Progress ──
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

    # ── Result card frames (hidden until detection completes) ──
    results_container = ctk.CTkFrame(app.content, fg_color="transparent")
    results_container.pack(fill="x", padx=20, pady=(0, 10))

    # PMIC Information card
    pmic_card = ctk.CTkFrame(results_container, fg_color=colors["bg_card"], corner_radius=12)
    pmic_card_label = ctk.CTkLabel(pmic_card, text="", font=("Consolas", 11),
                                    text_color=colors["text"], justify="left", anchor="w")
    pmic_card_label.pack(padx=15, pady=10, anchor="w")

    # Regulators table card
    reg_card = ctk.CTkFrame(results_container, fg_color=colors["bg_card"], corner_radius=12)
    reg_card_label = ctk.CTkLabel(reg_card, text="", font=("Consolas", 10),
                                   text_color=colors["text"], justify="left", anchor="w")
    reg_card_label.pack(padx=15, pady=10, anchor="w")

    # Power Rails card
    rails_card = ctk.CTkFrame(results_container, fg_color=colors["bg_card"], corner_radius=12)
    rails_card_label = ctk.CTkLabel(rails_card, text="", font=("Consolas", 10),
                                     text_color=colors["text"], justify="left", anchor="w")
    rails_card_label.pack(padx=15, pady=10, anchor="w")

    # Short Circuit Results card
    sc_card = ctk.CTkFrame(results_container, fg_color=colors["bg_card"], corner_radius=12)
    sc_card_label = ctk.CTkLabel(sc_card, text="", font=("Consolas", 11),
                                  text_color=colors["text"], justify="left", anchor="w")
    sc_card_label.pack(padx=15, pady=10, anchor="w")

    # Thermal Power card
    thermal_card = ctk.CTkFrame(results_container, fg_color=colors["bg_card"], corner_radius=12)
    thermal_card_label = ctk.CTkLabel(thermal_card, text="", font=("Consolas", 11),
                                       text_color=colors["text"], justify="left", anchor="w")
    thermal_card_label.pack(padx=15, pady=10, anchor="w")

    # Overall health badge
    health_frame = ctk.CTkFrame(results_container, fg_color="transparent")
    health_label = ctk.CTkLabel(health_frame, text="", font=("Segoe UI", 16, "bold"),
                                 text_color=colors["text"])
    health_label.pack(pady=5)

    # ── Live append helpers (using shared utilities) ──
    def _append_live(text):
        append_live(app, report_box, text)

    def _append_live_lines(lines):
        append_live_lines(app, report_box, lines)

    # ── Populate result cards ──
    def _populate_results(result):
        """Fill in all result cards from PowerTestResult data. Runs on main thread."""

        # --- PMIC Information ---
        pmic = result.pmic_info
        pmic_lines = ["⚙ PMIC Information"]
        pmic_lines.append(f"  Version      : {pmic.get('version', 'unknown')}")
        pmic_lines.append(f"  Manufacturer : {pmic.get('manufacturer', 'unknown')}")
        pmic_lines.append(f"  Bus Status   : {pmic.get('bus_status', 'unknown')}")
        pmic_lines.append(f"  Platform     : {pmic.get('platform', 'N/A')}")
        pmic_lines.append(f"  Hardware     : {pmic.get('hardware', 'N/A')}")
        detected = pmic.get("detected_pmics", [])
        if detected:
            pmic_lines.append(f"  Detected PMICs ({len(detected)}):")
            for p in detected:
                name = p.get("name", p.get("bus_id", "?"))
                desc = p.get("description", "")
                pmic_lines.append(f"    {name}: {desc}")
        ps = pmic.get("power_supplies", {})
        if ps:
            pmic_lines.append(f"  Power Supplies ({len(ps)}):")
            for ps_name, ps_info in ps.items():
                v = ps_info.get("voltage_mv", 0)
                c = ps_info.get("current_ma", 0)
                pmic_lines.append(f"    {ps_name}: {v:.0f} mV, {c:.1f} mA ({ps_info.get('type', '')})")
        pmic_card_label.configure(text="\n".join(pmic_lines))
        pmic_card.pack(fill="x", pady=(0, 8))

        # --- Regulators table ---
        regs = result.regulators
        if regs:
            enabled = [r for r in regs if r.status == "enabled"]
            disabled = [r for r in regs if r.status == "disabled"]
            bucks = sum(1 for r in regs if "Buck" in r.regulator_type)
            ldos = sum(1 for r in regs if "LDO" in r.regulator_type)
            reg_lines = [f"📊 Regulators ({len(regs)} total | Enabled: {len(enabled)} | Disabled: {len(disabled)} | Bucks: {bucks} | LDOs: {ldos})"]
            reg_lines.append("")
            reg_lines.append(f"  {'Name':<28s} {'Type':<16s} {'Voltage (mV)':>13s}  {'Status':<10s}")
            reg_lines.append("  " + "-" * 72)
            shown = sorted(enabled, key=lambda x: x.name)[:40]  # limit display
            for r in shown:
                v_str = f"{r.voltage_mv:.1f}" if r.voltage_mv > 0 else "N/A"
                reg_lines.append(f"  {r.name:<28s} {r.regulator_type:<16s} {v_str:>13s}  {r.status:<10s}")
            if len(enabled) > 40:
                reg_lines.append(f"  ... and {len(enabled) - 40} more enabled regulators")
            reg_card_label.configure(text="\n".join(reg_lines))
            reg_card.pack(fill="x", pady=(0, 8))

        # --- Power Rails ---
        rails = result.power_rails
        if rails:
            rails_lines = [f"🔌 Power Rails ({len(rails)} monitored)"]
            rails_lines.append("")
            rails_lines.append(f"  {'Rail':<20s} {'Actual (mV)':>12s} {'Expected (mV)':>14s} {'Status':<8s} {'Current (mA)':>13s}")
            rails_lines.append("  " + "-" * 72)
            for rail in rails:
                v_str = f"{rail.voltage_mv:.1f}" if rail.voltage_mv > 0 else "OFF"
                e_str = f"{rail.expected_voltage_mv:.0f}" if rail.expected_voltage_mv > 0 else "N/A"
                c_str = f"{rail.current_ma:.1f}" if rail.current_ma > 0 else "-"
                status_icon = {"OK": "✅", "LOW": "⬇️", "HIGH": "⬆️", "OFF": "⛔"}.get(rail.status, "❓")
                rails_lines.append(
                    f"  {rail.name:<20s} {v_str:>12s} {e_str:>14s} {status_icon} {rail.status:<5s} {c_str:>13s}"
                )
            rails_card_label.configure(text="\n".join(rails_lines))
            rails_card.pack(fill="x", pady=(0, 8))

        # --- Short Circuit Results ---
        sc_results = result.short_circuit_results
        if sc_results:
            faults = [sc for sc in sc_results if sc.status not in ("OK", "UNKNOWN")]
            ok_count = sum(1 for sc in sc_results if sc.status == "OK")
            unknown_count = sum(1 for sc in sc_results if sc.status == "UNKNOWN")
            sc_lines = [f"🔍 Short Circuit Analysis ({len(sc_results)} rails checked)"]
            sc_lines.append("")
            if faults:
                sc_lines.append(f"  🔴 FAULTS DETECTED: {len(faults)}  |  ✅ OK: {ok_count}  |  ❓ Unknown: {unknown_count}")
                sc_lines.append("")
                for sc in faults:
                    icon = {"SHORT": "🔴", "LEAKY": "🟠", "OPEN": "🟡"}.get(sc.status, "❓")
                    sc_lines.append(f"  {icon} [{sc.status}] {sc.rail_name}")
                    sc_lines.append(f"      {sc.verdict}")
                    if sc.resistance_ohm > 0:
                        sc_lines.append(f"      Resistance: {sc.resistance_ohm:.3f} ohm")
                    if sc.voltage_drop_mv != 0:
                        sc_lines.append(f"      Voltage drop: {sc.voltage_drop_mv:.1f} mV")
            else:
                sc_lines.append(f"  ✅ All {ok_count} checked rails within tolerance. No faults detected.")
            sc_card_label.configure(text="\n".join(sc_lines))
            sc_card.pack(fill="x", pady=(0, 8))

        # --- Thermal Power ---
        tp = result.thermal_power
        if tp:
            tp_lines = ["🌡 Thermal / Power Consumption"]
            tp_lines.append("")
            if tp.get("battery_power_mw"):
                tp_lines.append(f"  Battery power  : {tp['battery_power_mw']:.1f} mW")
            if tp.get("usb_power_mw"):
                tp_lines.append(f"  USB power      : {tp['usb_power_mw']:.1f} mW")
            if tp.get("estimated_total_mw"):
                tp_lines.append(f"  Est. total     : {tp['estimated_total_mw']:.1f} mW")
            zones = tp.get("zones", {})
            if zones:
                hot = {k: v for k, v in zones.items() if v > 45.0}
                if hot:
                    tp_lines.append(f"  Hot zones (> 45 C):")
                    for zn, zt in sorted(hot.items(), key=lambda x: -x[1]):
                        marker = "🔴" if zt > 65 else "🟡" if zt > 55 else "🟢"
                        tp_lines.append(f"    {marker} {zn}: {zt:.1f} C")
                else:
                    tp_lines.append(f"  All {len(zones)} thermal zones within normal range.")
            thermal_card_label.configure(text="\n".join(tp_lines))
            thermal_card.pack(fill="x", pady=(0, 8))

        # --- Overall health badge ---
        health = result.overall_health
        health_colors = {
            "GOOD": colors["success"],
            "WARNING": "#ffa502",
            "CRITICAL": colors["accent"],
            "INCOMPLETE": colors["info"],
            "NO CONNECTION": colors["accent"],
            "UNKNOWN": colors["text_dim"],
        }
        badge_color = health_colors.get(health, colors["text_dim"])
        health_label.configure(
            text=f"Overall Health: {health}",
            text_color=badge_color,
        )
        health_frame.pack(fill="x", pady=(5, 5))

    # ── Start detection ──
    def start_detection():
        if running["value"]:
            return
        running["value"] = True
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        summary_label.configure(text="🔄 Running power test...", text_color=colors["info"])
        progress.set(0)

        # Hide previous result cards
        for card in (pmic_card, reg_card, rails_card, sc_card, thermal_card, health_frame):
            card.pack_forget()

        full_report = {"lines": []}

        def _track_and_append(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_and_append_lines(lines):
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            try:
                from app.hardware.power_tester import detect_power_status, generate_power_report

                last_phase = {"msg": ""}

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                    if msg != last_phase["msg"]:
                        last_phase["msg"] = msg
                        icon = "🔍"
                        msg_lower = msg.lower()
                        if "complete" in msg_lower or "done" in msg_lower:
                            icon = "✅"
                        elif "error" in msg_lower or "fail" in msg_lower or "abort" in msg_lower:
                            icon = "❌"
                        elif "reading" in msg_lower or "scanning" in msg_lower or "checking" in msg_lower:
                            icon = "🔍"
                        elif "monitoring" in msg_lower:
                            icon = "📊"
                        elif "analy" in msg_lower:
                            icon = "🧠"
                        _track_and_append(f"  {icon} {msg}")

                # Show header
                header = [
                    "=" * 72,
                    "  MOOXY AI FAULT DETECTOR — POWER / VOLTAGE TESTING",
                    "=" * 72,
                    f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    "=" * 72,
                    "",
                    "═══ STARTING POWER TEST ═══",
                    "",
                ]
                _track_and_append_lines(header)

                result = detect_power_status(callback=cb)

                if result.error:
                    _track_and_append("")
                    _track_and_append(f"  ❌ ERROR: {result.error}")
                    _track_and_append("")
                    app.content.after(0, lambda: summary_label.configure(
                        text=f"❌ {result.error[:80]}", text_color=colors["accent"]))
                    app.content.after(0, lambda: progress.set(1.0))
                    running["value"] = False
                    return

                # ── Show live detection summary ──
                _track_and_append("")
                _track_and_append("═══ PMIC IDENTIFIED ═══")
                _track_and_append("")
                pmic = result.pmic_info
                _track_and_append(f"  ✅ PMIC Version: {pmic.get('version', 'unknown')}")
                _track_and_append(f"  ✅ Manufacturer: {pmic.get('manufacturer', 'unknown')}")
                _track_and_append(f"  ✅ Platform: {pmic.get('platform', 'N/A')}")
                _track_and_append(f"  ✅ Hardware: {pmic.get('hardware', 'N/A')}")
                _track_and_append(f"  ✅ Bus Status: {pmic.get('bus_status', 'unknown')}")

                detected = pmic.get("detected_pmics", [])
                if detected:
                    _track_and_append(f"  ✅ Detected PMICs: {len(detected)}")
                    for p in detected:
                        name = p.get("name", p.get("bus_id", "?"))
                        desc = p.get("description", "")
                        _track_and_append(f"     {name}: {desc}")

                # Regulators summary
                _track_and_append("")
                _track_and_append("  ── Regulator Summary ──")
                enabled = sum(1 for r in result.regulators if r.status == "enabled")
                disabled = sum(1 for r in result.regulators if r.status == "disabled")
                bucks = sum(1 for r in result.regulators if "Buck" in r.regulator_type)
                ldos = sum(1 for r in result.regulators if "LDO" in r.regulator_type)
                _track_and_append(f"  📊 Total: {len(result.regulators)} | Enabled: {enabled} | Disabled: {disabled}")
                _track_and_append(f"  📊 Bucks/SMPS: {bucks} | LDOs: {ldos}")

                # Power rails summary
                if result.power_rails:
                    _track_and_append("")
                    _track_and_append("  ── Power Rail Status ──")
                    ok_rails = sum(1 for r in result.power_rails if r.status == "OK")
                    off_rails = sum(1 for r in result.power_rails if r.status == "OFF")
                    problem_rails = sum(1 for r in result.power_rails if r.status in ("LOW", "HIGH"))
                    _track_and_append(f"  🔌 Total: {len(result.power_rails)} | OK: {ok_rails} | OFF: {off_rails} | Issues: {problem_rails}")
                    for rail in result.power_rails:
                        if rail.expected_voltage_mv > 0:
                            icon = {"OK": "✅", "LOW": "🔴", "HIGH": "🟡", "OFF": "⛔"}.get(rail.status, "❓")
                            _track_and_append(
                                f"  {icon} {rail.name}: {rail.voltage_mv:.1f} mV "
                                f"(expected {rail.expected_voltage_mv:.0f} mV) [{rail.status}]"
                            )

                # Short circuit results
                if result.short_circuit_results:
                    faults_sc = [sc for sc in result.short_circuit_results if sc.status not in ("OK", "UNKNOWN")]
                    ok_sc = sum(1 for sc in result.short_circuit_results if sc.status == "OK")
                    _track_and_append("")
                    _track_and_append("═══ SHORT CIRCUIT ANALYSIS ═══")
                    _track_and_append("")
                    _track_and_append(f"  🔴 FAULTS: {len(faults_sc)}  |  ✅ OK: {ok_sc}")
                    _track_and_append("")
                    if faults_sc:
                        for sc in faults_sc:
                            icon = {"SHORT": "🔴", "LEAKY": "🟠", "OPEN": "🟡"}.get(sc.status, "❓")
                            _track_and_append(f"  {icon} [{sc.status}] {sc.rail_name}")
                            _track_and_append(f"     {sc.verdict}")
                    else:
                        _track_and_append("  ✅ No short circuits or faults detected")

                # Thermal
                tp = result.thermal_power
                if tp:
                    _track_and_append("")
                    _track_and_append("  ── Thermal / Power ──")
                    if tp.get("battery_power_mw"):
                        _track_and_append(f"  🔋 Battery power: {tp['battery_power_mw']:.1f} mW")
                    if tp.get("usb_power_mw"):
                        _track_and_append(f"  🔌 USB power: {tp['usb_power_mw']:.1f} mW")
                    if tp.get("estimated_total_mw"):
                        _track_and_append(f"  ⚡ Estimated total: {tp['estimated_total_mw']:.1f} mW")
                    zones = tp.get("zones", {})
                    hot = {k: v for k, v in zones.items() if v > 50.0}
                    if hot:
                        for zn, zt in sorted(hot.items(), key=lambda x: -x[1]):
                            _track_and_append(f"  🌡 HOT: {zn} = {zt:.1f} C")

                # Overall health
                _track_and_append("")
                _track_and_append("═══ OVERALL HEALTH ═══")
                _track_and_append("")
                health = result.overall_health
                health_icon = {
                    "GOOD": "✅", "WARNING": "🟡", "CRITICAL": "🔴",
                    "INCOMPLETE": "❓", "NO CONNECTION": "❌",
                }.get(health, "❓")
                _track_and_append(f"  {health_icon} Overall Health: {health}")
                _track_and_append(f"  ⏱ Detection time: {result.detection_duration_s:.1f}s")

                # ── Full detailed report ──
                _track_and_append("")
                _track_and_append("═" * 72)
                _track_and_append("  FULL DETAILED REPORT")
                _track_and_append("═" * 72)

                full_detailed_report = generate_power_report(result)
                for line in full_detailed_report.splitlines():
                    full_report["lines"].append(line)

                def _append_full():
                    report_box.configure(state="normal")
                    report_box.insert("end", "\n" + full_detailed_report)
                    report_box.see("1.0")
                app.content.after(0, _append_full)

                # ── Populate result cards on main thread ──
                app.content.after(0, lambda: _populate_results(result))

                # ── Final UI updates ──
                faults_count = sum(
                    1 for sc in result.short_circuit_results if sc.status in ("SHORT", "LEAKY")
                )
                app.content.after(0, lambda: progress.set(1.0))
                app.content.after(0, lambda: msg_label.configure(
                    text="Power test complete — full report above", text_color=colors["success"]))
                app.content.after(0, lambda: summary_label.configure(
                    text=f"{health_icon} {pmic.get('version', 'unknown')} | "
                         f"Regulators: {len(result.regulators)} | "
                         f"Rails: {len(result.power_rails)} | "
                         f"Faults: {faults_count} | "
                         f"Health: {health}",
                    text_color=colors["success"] if health == "GOOD" else colors["accent"]))

                # ── Save report file ──
                from app.gui.history_manager import get_unique_log_path
                report_text = "\n".join(full_report["lines"])
                power_log_path = get_unique_log_path("power_test_log")
                try:
                    with open(power_log_path, "w", encoding="utf-8") as f:
                        f.write(report_text)
                    saved_name = power_log_path.name
                    app.content.after(0, lambda: msg_label.configure(
                        text=f"📁 Saved: {saved_name} → config/logs/", text_color=colors["success"]))
                except Exception:
                    pass

                # ── Save to history ──
                try:
                    from app.gui.history_manager import add_detection
                    fault_names = [
                        f"{sc.rail_name}: {sc.status} - {sc.verdict[:60]}"
                        for sc in result.short_circuit_results
                        if sc.status not in ("OK", "UNKNOWN")
                    ]
                    add_detection(
                        detection_type="Power Test",
                        device_name=pmic.get("version", "Unknown PMIC"),
                        summary=f"Platform: {pmic.get('platform', 'N/A')} | "
                                f"Regulators: {len(result.regulators)} | "
                                f"Rails: {len(result.power_rails)} | "
                                f"Health: {health}",
                        faults_count=faults_count,
                        faults_summary="; ".join(fault_names[:5]),
                        report_file=str(power_log_path),
                        extra={
                            "pmic_version": pmic.get("version", "unknown"),
                            "regulators_count": len(result.regulators),
                            "rails_count": len(result.power_rails),
                            "overall_health": health,
                            "detection_time_s": result.detection_duration_s,
                        }
                    )
                except Exception as e:
                    print(f"[Power Test] History save error: {e}")

                running["value"] = False

            except Exception as e:
                _track_and_append("")
                _track_and_append(f"  ❌ ERROR: {str(e)}")
                app.content.after(0, lambda: summary_label.configure(
                    text=f"❌ {str(e)[:80]}", text_color=colors["accent"]))
                app.content.after(0, lambda: progress.set(1.0))
                running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    def copy_report():
        copy_report_to_clipboard(app, report_box, status_label=msg_label, colors=colors)

    def save_report():
        save_report_to_file(app, report_box, default_prefix="power_test_report",
                            status_label=msg_label, colors=colors)

    ctk.CTkButton(btn_frame, text="⚡ Start Power Test", width=250, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_detection).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="📋 Copy Report", width=140, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="💾 Save Report", width=140, height=46,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # ── Main report textbox ──
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=600, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0",
        "Press 'Start Power Test' to begin.\n\n"
        "Requirements:\n"
        "• Phone connected via USB\n"
        "• USB Debugging enabled\n"
        "• ADB installed and in PATH\n"
        "• Root access recommended for full SPMI register visibility\n\n"
        "What this test does:\n"
        "  1. Checks ADB connection\n"
        "  2. Reads PMIC registers via SPMI debug bus\n"
        "  3. Enumerates all Buck/LDO/Boost regulators\n"
        "  4. Monitors power rail voltages vs chipset baselines\n"
        "  5. Analyses for short circuits and overcurrent\n"
        "  6. Gathers thermal data and power consumption\n"
    )
    report_box.configure(state="normal")
    setup_report_tags(report_box)

    app.update_status("Power / Voltage Testing — Connect phone via USB and press Start")
