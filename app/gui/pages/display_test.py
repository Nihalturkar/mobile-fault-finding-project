import customtkinter as ctk
import threading
from pathlib import Path
from app.gui.ui_utils import (
    get_line_tag, setup_report_tags, append_live, append_live_lines,
    safe_after, copy_report_to_clipboard, save_report_to_file,
)


def render_display_test(app):
    """Display Testing page — panel info, backlight, touch IC, dead pixels.
    Shows detections LIVE as they happen — real-time append with color tags."""
    colors = app.colors

    ctk.CTkLabel(app.content, text="\U0001f5a5\ufe0f Display Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content, text="Full display diagnosis — panel info, backlight health, touch IC, dead pixel analysis",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card: what display testing detects ──
    info_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info_card.pack(fill="x", padx=20, pady=(0, 10))
    info_inner = ctk.CTkFrame(info_card, fg_color="transparent")
    info_inner.pack(fill="x", padx=15, pady=12)

    ctk.CTkLabel(info_inner, text="What this test detects:",
                 font=("Segoe UI", 14, "bold"), text_color=colors["text"]).pack(anchor="w")
    detect_items = [
        "Panel Info — type, resolution, density, refresh rate, HDR support, manufacturer",
        "Backlight — current/max brightness, adaptive mode, LED driver status",
        "Touch IC — controller device, protocol, multitouch points, pressure sensitivity",
        "Dead Pixels — full pixel scan, suspect count, affected locations on panel",
    ]
    for item in detect_items:
        ctk.CTkLabel(info_inner, text=f"  \u2022 {item}",
                     font=("Segoe UI", 12), text_color=colors["text_dim"]).pack(anchor="w", pady=1)

    # ── Summary bar ──
    summary_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=50)
    summary_frame.pack(fill="x", padx=20, pady=(0, 10))
    summary_frame.pack_propagate(False)
    summary_label = ctk.CTkLabel(summary_frame, text="Press Start to begin display testing...",
                                  font=("Segoe UI", 14), text_color=colors["text_dim"])
    summary_label.pack(side="left", padx=20, pady=10)

    # ── Health badge (hidden until detection done) ──
    health_badge = ctk.CTkLabel(summary_frame, text="",
                                 font=("Segoe UI", 14, "bold"), text_color=colors["success"])
    health_badge.pack(side="right", padx=20, pady=10)

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

    # ── Result cards container (populated after detection) ──
    cards_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    cards_frame.pack(fill="x", padx=20, pady=(0, 10))

    # ── Live append helpers (using shared utilities) ──
    def _append_live(text):
        append_live(app, report_box, text)

    def _append_live_lines(lines):
        append_live_lines(app, report_box, lines)

    def _make_result_card(parent, title, rows):
        """Create a result card with key-value rows inside the cards_frame."""
        def _do():
            card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10)
            card.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=5)
            ctk.CTkLabel(card, text=title, font=("Segoe UI", 14, "bold"),
                         text_color=colors["text"]).pack(anchor="w", padx=12, pady=(10, 5))
            for key, value, status in rows:
                row_frame = ctk.CTkFrame(card, fg_color="transparent")
                row_frame.pack(fill="x", padx=12, pady=1)
                ctk.CTkLabel(row_frame, text=f"{key}:", font=("Segoe UI", 12),
                             text_color=colors["text_dim"]).pack(side="left")
                val_color = colors["success"] if status == "ok" else colors["accent"] if status == "fault" else colors.get("warning", colors["text"]) if status == "warning" else colors["text"]
                ctk.CTkLabel(row_frame, text=f" {value}", font=("Segoe UI", 12, "bold"),
                             text_color=val_color).pack(side="left")
            # Bottom padding
            ctk.CTkFrame(card, fg_color="transparent", height=8).pack()
        app.content.after(0, _do)

    def start_detection():
        if running["value"]:
            return
        running["value"] = True

        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        summary_label.configure(text="Detecting display...", text_color=colors["info"])
        health_badge.configure(text="")
        progress.set(0)

        # Clear previous result cards
        for widget in cards_frame.winfo_children():
            widget.destroy()

        full_report = {"lines": []}

        def _track_and_append(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_and_append_lines(lines):
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            import datetime as _dt

            # ── Header ──
            header = [
                "=" * 72,
                "  MOOXY AI FAULT DETECTOR - DISPLAY TESTING REPORT",
                "=" * 72,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 72,
                "",
            ]
            _track_and_append_lines(header)

            app.content.after(0, lambda: msg_label.configure(text="Connecting to device..."))
            app.content.after(0, lambda: progress.set(0.05))

            result = None
            try:
                from app.hardware.display_tester import detect_display_status

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))
                    _track_and_append(f"  {msg}")

                result = detect_display_status(callback=cb)

            except ImportError as e:
                _track_and_append(f"  Import error: {e}")
                app.content.after(0, lambda: summary_label.configure(
                    text=f"Display tester module not found", text_color=colors["accent"]))
                app.content.after(0, lambda: progress.set(1.0))
                running["value"] = False
                return
            except Exception as e:
                _track_and_append(f"  Error: {str(e)}")
                app.content.after(0, lambda: summary_label.configure(
                    text=f"Error: {str(e)[:80]}", text_color=colors["accent"]))
                app.content.after(0, lambda: progress.set(1.0))
                running["value"] = False
                return

            if not result:
                _track_and_append("  No display data returned")
                app.content.after(0, lambda: summary_label.configure(
                    text="No display data — check device connection", text_color=colors["accent"]))
                app.content.after(0, lambda: progress.set(1.0))
                running["value"] = False
                return

            app.content.after(0, lambda: progress.set(0.40))

            # result is a DisplayTestResult dataclass — access via attributes
            di = result.display_info
            bl = result.backlight_info
            ti = result.touch_info
            dp = result.dead_pixel_result

            # ═══ DISPLAY INFO ═══
            _track_and_append("")
            _track_and_append("=" * 60)
            _track_and_append("  PANEL INFORMATION")
            _track_and_append("=" * 60)
            _track_and_append("")

            panel_type = di.panel_type
            resolution = f"{di.resolution_w}x{di.resolution_h}" if di.resolution_w > 0 else "Unknown"
            density = di.density if di.density > 0 else "Unknown"
            refresh_rate = di.refresh_rate if di.refresh_rate > 0 else "Unknown"
            hdr_support = "Yes" if di.hdr_support else "No"
            manufacturer = di.manufacturer

            _track_and_append(f"  Panel Type:     {panel_type}")
            _track_and_append(f"  Resolution:     {resolution}")
            _track_and_append(f"  Density:        {density} dpi")
            _track_and_append(f"  Refresh Rate:   {refresh_rate} Hz")
            _track_and_append(f"  HDR Support:    {hdr_support}")
            _track_and_append(f"  Wide Color:     {'Yes' if di.wide_color_gamut else 'No'}")
            _track_and_append(f"  Manufacturer:   {manufacturer}")
            _track_and_append(f"  Driver:         {di.driver}")

            panel_rows = [
                ("Panel Type", str(panel_type), "ok"),
                ("Resolution", str(resolution), "ok"),
                ("Density", f"{density} dpi", "ok"),
                ("Refresh Rate", f"{refresh_rate} Hz", "ok"),
                ("HDR", hdr_support, "ok" if di.hdr_support else "info"),
                ("Manufacturer", str(manufacturer), "ok"),
            ]

            top_row = ctk.CTkFrame(cards_frame, fg_color="transparent")
            app.content.after(0, lambda: top_row.pack(fill="x", pady=(0, 5)))

            _make_result_card(top_row, "Display Info", panel_rows)

            app.content.after(0, lambda: progress.set(0.55))

            # ═══ BACKLIGHT ═══
            _track_and_append("")
            _track_and_append("=" * 60)
            _track_and_append("  BACKLIGHT ANALYSIS")
            _track_and_append("=" * 60)
            _track_and_append("")

            current_brightness = bl.current_brightness if bl.current_brightness >= 0 else "Unknown"
            max_brightness = bl.max_brightness
            adaptive_mode = "ON" if bl.adaptive_enabled else "OFF"
            bl_status = bl.status

            _track_and_append(f"  Current Brightness:  {current_brightness}")
            _track_and_append(f"  Max Brightness:      {max_brightness}")
            _track_and_append(f"  Adaptive Mode:       {adaptive_mode}")
            _track_and_append(f"  Status:              {bl_status}")

            bl_stat = "ok" if bl_status == "OK" else "fault" if bl_status == "FAULT" else "warning"
            backlight_rows = [
                ("Current", str(current_brightness), "ok"),
                ("Max", str(max_brightness), "ok"),
                ("Adaptive", adaptive_mode, "ok"),
                ("Status", bl_status, bl_stat),
            ]

            _make_result_card(top_row, "Backlight", backlight_rows)

            app.content.after(0, lambda: progress.set(0.70))

            # ═══ TOUCH IC ═══
            _track_and_append("")
            _track_and_append("=" * 60)
            _track_and_append("  TOUCH IC ANALYSIS")
            _track_and_append("=" * 60)
            _track_and_append("")

            touch_device = ti.device_name
            touch_protocol = ti.protocol
            multitouch = ti.multitouch_slots
            pressure_support = "Yes" if ti.pressure_support else "No"
            response_time = f"{ti.response_time_ms:.1f} ms" if ti.response_time_ms >= 0 else "N/A"
            touch_status = ti.status

            _track_and_append(f"  Device:              {touch_device}")
            _track_and_append(f"  Protocol:            {touch_protocol}")
            _track_and_append(f"  Multitouch Slots:    {multitouch}")
            _track_and_append(f"  Pressure Support:    {pressure_support}")
            _track_and_append(f"  Touch Range:         {ti.max_x}x{ti.max_y}")
            _track_and_append(f"  Response Time:       {response_time}")
            _track_and_append(f"  Status:              {touch_status}")

            t_stat = "ok" if touch_status == "OK" else "fault" if touch_status == "FAULT" else "warning"
            touch_rows = [
                ("Device", str(touch_device), "ok"),
                ("Protocol", str(touch_protocol), "ok"),
                ("MT Slots", str(multitouch), "ok" if multitouch >= 2 else "warning"),
                ("Pressure", pressure_support, "ok"),
                ("Range", f"{ti.max_x}x{ti.max_y}", "ok"),
                ("Status", touch_status, t_stat),
            ]

            bottom_row = ctk.CTkFrame(cards_frame, fg_color="transparent")
            app.content.after(0, lambda: bottom_row.pack(fill="x", pady=(0, 5)))

            _make_result_card(bottom_row, "Touch IC", touch_rows)

            app.content.after(0, lambda: progress.set(0.85))

            # ═══ DEAD PIXEL ANALYSIS ═══
            _track_and_append("")
            _track_and_append("=" * 60)
            _track_and_append("  DEAD PIXEL ANALYSIS")
            _track_and_append("=" * 60)
            _track_and_append("")

            total_pixels = dp.total_pixels
            suspect_count = dp.suspect_pixels
            locations = dp.suspect_locations
            dp_status = dp.status

            _track_and_append(f"  Total Pixels:        {total_pixels:,}")
            _track_and_append(f"  Suspect Count:       {suspect_count}")
            _track_and_append(f"  Analyzed:            {'Yes' if dp.screenshot_analyzed else 'No'}")
            _track_and_append(f"  Status:              {dp_status}")

            if locations:
                _track_and_append(f"  Suspect Locations (sample):")
                for x, y in locations[:10]:
                    _track_and_append(f"    Pixel at ({x}, {y})")
            else:
                _track_and_append(f"  No dead pixels detected — panel is clean")

            dp_stat = "ok" if dp_status == "OK" else "fault" if dp_status == "FAULT" else "warning"
            dp_rows = [
                ("Total Pixels", f"{total_pixels:,}" if total_pixels > 0 else "N/A", "ok"),
                ("Suspect Count", str(suspect_count), dp_stat),
                ("Analyzed", "Yes" if dp.screenshot_analyzed else "No", "ok" if dp.screenshot_analyzed else "warning"),
                ("Status", dp_status, dp_stat),
            ]

            _make_result_card(bottom_row, "Dead Pixel Analysis", dp_rows)

            app.content.after(0, lambda: progress.set(0.95))

            # ═══ OVERALL HEALTH ═══
            overall_health = result.display_health
            health_score = None

            _track_and_append("")
            _track_and_append("=" * 60)
            _track_and_append("  OVERALL DISPLAY HEALTH")
            _track_and_append("=" * 60)
            _track_and_append("")

            if health_score is not None:
                _track_and_append(f"  Health Score:  {health_score}%")
            _track_and_append(f"  Verdict:       {overall_health}")

            # Determine health color
            health_lower = str(overall_health).lower()
            if any(k in health_lower for k in ["good", "healthy", "pass", "ok", "excellent"]):
                h_color = colors["success"]
                h_icon = "[OK]"
            elif any(k in health_lower for k in ["warning", "degraded", "fair"]):
                h_color = colors.get("warning", "#ffa502")
                h_icon = "[!!]"
            else:
                h_color = colors["accent"]
                h_icon = "[XX]"

            health_text = f"{h_icon} {overall_health}"
            if health_score is not None:
                health_text += f" ({health_score}%)"

            # Footer
            _track_and_append("")
            _track_and_append("=" * 72)
            _track_and_append("  Report generated by Mooxy AI Fault Detector v1.0")
            _track_and_append("=" * 72)

            report_text = "\n".join(full_report["lines"])

            # ── Final UI updates ──
            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Display testing complete - full report above", text_color=colors["success"]))

            summary_txt = f"{panel_type} | {resolution} @ {refresh_rate}Hz | Touch: {touch_status} | Pixels: {suspect_count} suspect"
            def _update_summary():
                summary_label.configure(text=summary_txt, text_color=colors["success"])
                health_badge.configure(text=health_text, text_color=h_color)
            app.content.after(0, _update_summary)

            # ── Auto-save to file ──
            from app.gui.history_manager import get_unique_log_path
            log_path = get_unique_log_path("display_test_log")
            try:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
            except Exception:
                pass

            # ── Save to history ──
            try:
                from app.gui.history_manager import add_detection

                faults_count = 0
                faults_summary = ""
                fault_items = []

                if str(bl_status).lower() not in ("ok", "normal", "healthy", "working"):
                    faults_count += 1
                    fault_items.append(f"Backlight: {bl_status}")
                if str(touch_status).lower() not in ("ok", "normal", "healthy", "working"):
                    faults_count += 1
                    fault_items.append(f"Touch IC: {touch_status}")
                if suspect_count and int(suspect_count) > 0:
                    faults_count += 1
                    fault_items.append(f"Dead Pixels: {suspect_count} suspect")
                faults_summary = "; ".join(fault_items)

                add_detection(
                    detection_type="DISPLAY",
                    device_name=f"{manufacturer} {panel_type}",
                    summary=f"{resolution} @ {refresh_rate}Hz | Backlight: {bl_status} | Touch: {touch_status} | Dead Pixels: {suspect_count}",
                    faults_count=faults_count,
                    faults_summary=faults_summary,
                    report_file=str(log_path),
                    extra={
                        "panel_type": str(panel_type),
                        "resolution": str(resolution),
                        "refresh_rate": str(refresh_rate),
                        "touch_device": str(touch_device),
                        "dead_pixel_count": suspect_count,
                        "overall_health": str(overall_health),
                        "health_score": health_score,
                    }
                )
            except Exception as e:
                print(f"[Display Test] History save error: {e}")

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    def copy_report():
        copy_report_to_clipboard(app, report_box, status_label=msg_label, colors=colors)

    def save_report():
        save_report_to_file(app, report_box, default_prefix="display_test_report",
                            status_label=msg_label, colors=colors)

    ctk.CTkButton(btn_frame, text="Start Display Detection", width=280, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_detection).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="Copy Report", width=140, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="Save Report", width=140, height=46,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # ── Main report textbox (scrollable, selectable, copyable) ──
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=600, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0", "Press 'Start Display Detection' to begin.\n\nThis test will check:\n  - Panel type, resolution, density, refresh rate\n  - Backlight driver and brightness levels\n  - Touch IC controller, multitouch, pressure sensitivity\n  - Dead pixel scan across entire panel\n\nRequirements:\n  - Phone connected via USB\n  - USB Debugging enabled\n  - ADB installed and in PATH\n")
    report_box.configure(state="normal")
    setup_report_tags(report_box)

    app.update_status("Display Testing - Press Start to begin diagnosis")
