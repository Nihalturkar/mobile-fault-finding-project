import customtkinter as ctk
import json
from collections import Counter
from pathlib import Path


def render_dashboard(app):
    """Render the main dashboard page with REAL data from detection history."""
    colors = app.colors
    devices = app.devices

    # Load detection history for real stats
    history_path = Path(__file__).parent.parent.parent.parent / "config" / "detection_history.json"
    detections = []
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            detections = data.get("detections", [])
    except Exception:
        pass

    # Load repair history
    repair_path = Path(__file__).parent.parent.parent.parent / "config" / "repair_history.json"
    repairs = []
    try:
        with open(repair_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            repairs = data.get("repairs", [])
    except Exception:
        pass

    # Page title
    ctk.CTkLabel(app.content, text="📊 Dashboard",
                 font=("Segoe UI", 24, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Live overview — detection history, device stats, and quick actions",
                 font=("Segoe UI", 13),
                 text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 20))

    # ── Live Connection Status ──
    conn_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    conn_frame.pack(fill="x", padx=20, pady=(0, 10))

    conn_inner = ctk.CTkFrame(conn_frame, fg_color="transparent")
    conn_inner.pack(fill="x", padx=20, pady=12)

    ctk.CTkLabel(conn_inner, text="🔌 Connection Status",
                 font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(side="left", padx=(0, 20))

    ftdi_dot = ctk.CTkLabel(conn_inner, text="● Device: Checking...",
                             font=("Segoe UI", 12), text_color=colors["text_dim"])
    ftdi_dot.pack(side="left", padx=(0, 20))

    adb_dot = ctk.CTkLabel(conn_inner, text="● ADB: Checking...",
                             font=("Segoe UI", 12), text_color=colors["text_dim"])
    adb_dot.pack(side="left", padx=(0, 20))

    edl_dot = ctk.CTkLabel(conn_inner, text="● EDL 9008: Checking...",
                             font=("Segoe UI", 12), text_color=colors["text_dim"])
    edl_dot.pack(side="left")

    def _check_live():
        import threading

        def check():
            ftdi_ok = False
            ftdi_port = ""
            adb_ok = False
            adb_device = ""
            edl_ok = False

            try:
                import serial.tools.list_ports
                for port in serial.tools.list_ports.comports():
                    if "FTDI" in port.description or "0403:6001" in port.hwid.upper():
                        ftdi_ok = True
                        ftdi_port = port.device
                        break
            except Exception:
                pass

            try:
                import subprocess
                result = subprocess.run("adb devices", capture_output=True, text=True,
                                       timeout=3, shell=True)
                lines = result.stdout.strip().split("\n")
                for line in lines[1:]:
                    parts = line.strip().split("\t")
                    if len(parts) >= 2 and parts[1] == "device":
                        adb_ok = True
                        adb_device = parts[0]
                        break
            except Exception:
                pass

            try:
                import serial.tools.list_ports
                for port in serial.tools.list_ports.comports():
                    if "9008" in port.description.lower() or "05C6:9008" in port.hwid.upper():
                        edl_ok = True
                        break
            except Exception:
                pass
            if not edl_ok:  # WinUSB-bound 9008 has no COM port
                try:
                    from app.hardware.edl_detector import find_edl_usb
                    edl_ok = find_edl_usb() is not None
                except Exception:
                    pass

            def update():
                try:
                    ftdi_dot.configure(
                        text=f"● Device: Connected ({ftdi_port})" if ftdi_ok else "● Device: Not Connected",
                        text_color=colors["success"] if ftdi_ok else colors["accent"])
                    adb_dot.configure(
                        text=f"● ADB: Connected ({adb_device[:15]})" if adb_ok else "● ADB: Not Connected",
                        text_color=colors["success"] if adb_ok else colors["accent"])
                    edl_dot.configure(
                        text="● EDL 9008: Device Found!" if edl_ok else "● EDL 9008: No Device",
                        text_color=colors["success"] if edl_ok else colors["text_dim"])
                except Exception:
                    return

            try:
                app.after(0, update)
            except Exception:
                return

        threading.Thread(target=check, daemon=True).start()

        def _schedule_next():
            try:
                conn_frame.winfo_id()
                app.after(5000, _check_live)
            except Exception:
                pass

        _schedule_next()

    _check_live()

    # ── Stats Cards — from REAL detection history ──
    stats_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    stats_frame.pack(fill="x", padx=20, pady=10)

    # Calculate REAL stats from detection history
    total_scans = len(detections)
    adb_scans = sum(1 for d in detections if d.get("type") == "ADB")
    uart_scans = sum(1 for d in detections if d.get("type") == "UART")
    power_scans = sum(1 for d in detections if d.get("type") == "Power Test")
    battery_scans = sum(1 for d in detections if d.get("type") == "BATTERY")
    other_scans = total_scans - adb_scans - uart_scans - power_scans - battery_scans

    # Unique devices detected
    device_names = set()
    for d in detections:
        name = d.get("device_name", "")
        if name and name not in ("Unknown Device", "Unknown (Unknown)", "unknown", "Battery Test"):
            device_names.add(name)

    # Total faults found
    total_faults = sum(d.get("faults_count", 0) for d in detections)
    total_warnings = sum(d.get("warnings_count", 0) for d in detections)

    stats = [
        ("🔍", "Total Scans", str(total_scans), colors["accent"]),
        ("📱", "Devices Found", str(len(device_names)), colors["info"]),
        ("🔴", "Faults Found", str(total_faults), "#e74c3c"),
        ("🟡", "Warnings", str(total_warnings), colors["warning"]),
        ("🔧", "Repairs Done", str(len(repairs)), colors["success"]),
    ]

    for icon, label, value, color in stats:
        card = ctk.CTkFrame(stats_frame, fg_color=colors["bg_card"],
                            corner_radius=12, height=120)
        card.pack(side="left", fill="both", expand=True, padx=5)
        card.pack_propagate(False)

        ctk.CTkLabel(card, text=icon, font=("Segoe UI Emoji", 28)).pack(pady=(15, 5))
        ctk.CTkLabel(card, text=value, font=("Segoe UI", 28, "bold"),
                     text_color=color).pack()
        ctk.CTkLabel(card, text=label, font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack()

    # ── Scan Type Breakdown ──
    scan_section = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    scan_section.pack(fill="x", padx=20, pady=10)

    ctk.CTkLabel(scan_section, text="📊 Scans by Type",
                 font=("Segoe UI", 16, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

    scan_types = [
        ("ADB Detection", adb_scans, colors["success"]),
        ("Fault Detection", uart_scans, colors["warning"]),
        ("Power Test", power_scans, "#9b59b6"),
        ("Battery Test", battery_scans, colors["info"]),
        ("Other", other_scans, colors["text_dim"]),
    ]

    scan_grid = ctk.CTkFrame(scan_section, fg_color="transparent")
    scan_grid.pack(fill="x", padx=20, pady=(0, 15))

    max_scan = max((adb_scans, uart_scans, power_scans, battery_scans, other_scans, 1))

    for name, count, color in scan_types:
        if count == 0:
            continue
        row = ctk.CTkFrame(scan_grid, fg_color="transparent")
        row.pack(fill="x", pady=3)

        ctk.CTkLabel(row, text=name, font=("Segoe UI", 12, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left")

        bar = ctk.CTkProgressBar(row, width=300, height=22,
                                  progress_color=color, fg_color=colors["bg_light"])
        bar.set(count / max_scan)
        bar.pack(side="left", padx=10)

        ctk.CTkLabel(row, text=str(count), font=("Segoe UI", 13, "bold"),
                     text_color=color).pack(side="left", padx=5)

    # ── Recent Detections (last 6) ──
    recent_section = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    recent_section.pack(fill="x", padx=20, pady=10)

    ctk.CTkLabel(recent_section, text="🕐 Recent Detections",
                 font=("Segoe UI", 16, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

    recent_grid = ctk.CTkFrame(recent_section, fg_color="transparent")
    recent_grid.pack(fill="x", padx=20, pady=(0, 15))

    if detections:
        # Header row
        header = ctk.CTkFrame(recent_grid, fg_color=colors["bg_light"], corner_radius=6)
        header.pack(fill="x", pady=(0, 5))
        for col_text, col_w in [("Type", 100), ("Device", 200), ("Date", 150),
                                 ("Status", 80), ("Health/Summary", 250)]:
            ctk.CTkLabel(header, text=col_text, font=("Segoe UI", 11, "bold"),
                         text_color=colors["text_dim"], width=col_w,
                         anchor="w").pack(side="left", padx=8, pady=6)

        # Last 6 detections (newest first)
        for det in reversed(detections[-6:]):
            det_type = det.get("type", "?")
            det_name = det.get("device_name", "Unknown")
            det_date = det.get("date", "?")
            det_faults = det.get("faults_count", 0)
            det_health = det.get("overall_health", det.get("summary", ""))

            # Truncate long strings
            if len(det_name) > 28:
                det_name = det_name[:26] + ".."
            if len(det_health) > 35:
                det_health = det_health[:33] + ".."

            # Type icon
            type_icons = {
                "ADB": "📱", "UART": "🔌", "Power Test": "⚡",
                "BATTERY": "🔋", "EDL": "💿", "DISPLAY": "🖥️",
                "CLOCK": "🕐",
            }
            type_icon = type_icons.get(det_type, "🔍")

            # Status color
            if det_faults > 0:
                status_text = f"🔴 {det_faults} fault"
                status_color = "#e74c3c"
            elif det.get("warnings_count", 0) > 0:
                status_text = "🟡 Warning"
                status_color = colors["warning"]
            else:
                status_text = "🟢 OK"
                status_color = colors["success"]

            row = ctk.CTkFrame(recent_grid, fg_color="transparent")
            row.pack(fill="x", pady=1)

            ctk.CTkLabel(row, text=f"{type_icon} {det_type}",
                         font=("Segoe UI", 11), text_color=colors["info"],
                         width=100, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=det_name,
                         font=("Segoe UI", 11), text_color=colors["text"],
                         width=200, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=det_date,
                         font=("Segoe UI", 10), text_color=colors["text_dim"],
                         width=150, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=status_text,
                         font=("Segoe UI", 11, "bold"), text_color=status_color,
                         width=80, anchor="w").pack(side="left", padx=8)
            ctk.CTkLabel(row, text=det_health,
                         font=("Segoe UI", 10), text_color=colors["text_dim"],
                         width=250, anchor="w").pack(side="left", padx=8)
    else:
        ctk.CTkLabel(recent_grid,
                     text="No detections yet — connect a phone and run ADB Detect!",
                     font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(pady=20)

    # ── Device History Summary ──
    if device_names:
        device_section = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
        device_section.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(device_section, text="📱 Detected Devices",
                     font=("Segoe UI", 16, "bold"),
                     text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

        dev_grid = ctk.CTkFrame(device_section, fg_color="transparent")
        dev_grid.pack(fill="x", padx=20, pady=(0, 15))

        # Count scans per device
        device_scan_counts = Counter()
        device_last_date = {}
        device_last_battery = {}
        for d in detections:
            name = d.get("device_name", "")
            if name and name not in ("Unknown Device", "Unknown (Unknown)", "unknown", "Battery Test"):
                device_scan_counts[name] += 1
                device_last_date[name] = d.get("date", "")
                if d.get("battery_level"):
                    device_last_battery[name] = d.get("battery_level")

        for name, count in device_scan_counts.most_common(10):
            row = ctk.CTkFrame(dev_grid, fg_color="transparent")
            row.pack(fill="x", pady=3)

            ctk.CTkLabel(row, text=f"📱 {name}",
                         font=("Segoe UI", 12, "bold"),
                         text_color=colors["text"], anchor="w").pack(side="left", padx=(0, 15))
            ctk.CTkLabel(row, text=f"{count} scans",
                         font=("Segoe UI", 11),
                         text_color=colors["info"]).pack(side="left", padx=(0, 15))

            last_date = device_last_date.get(name, "")
            if last_date:
                ctk.CTkLabel(row, text=f"Last: {last_date}",
                             font=("Segoe UI", 10),
                             text_color=colors["text_dim"]).pack(side="left", padx=(0, 15))

            batt = device_last_battery.get(name)
            if batt is not None:
                batt_color = colors["success"] if batt > 50 else (colors["warning"] if batt > 20 else "#e74c3c")
                ctk.CTkLabel(row, text=f"🔋 {batt}%",
                             font=("Segoe UI", 11, "bold"),
                             text_color=batt_color).pack(side="left")

    # ── Quick Actions (updated with new features) ──
    actions_section = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    actions_section.pack(fill="x", padx=20, pady=10)

    ctk.CTkLabel(actions_section, text="⚡ Quick Actions",
                 font=("Segoe UI", 16, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

    # Row 1: Detection tools
    actions_row1 = ctk.CTkFrame(actions_section, fg_color="transparent")
    actions_row1.pack(fill="x", padx=20, pady=(0, 5))

    row1_actions = [
        ("📱 ADB Detect", app.show_adb_detect, colors["success"]),
        ("🔌 HW Detect", app.show_hw_detect, colors["warning"]),
        ("⚡ Power Test", app.show_power_test, "#9b59b6"),
        ("🔋 Battery Test", app.show_battery_test, colors["info"]),
    ]

    for text, cmd, color in row1_actions:
        ctk.CTkButton(
            actions_row1, text=text, command=cmd,
            font=("Segoe UI", 13, "bold"), height=45,
            fg_color=color, hover_color=colors["accent_hover"],
            corner_radius=10
        ).pack(side="left", fill="x", expand=True, padx=3)

    # Row 2: Repair tools
    actions_row2 = ctk.CTkFrame(actions_section, fg_color="transparent")
    actions_row2.pack(fill="x", padx=20, pady=(0, 15))

    row2_actions = [
        ("🔓 FRP/Unlock", app.show_frp_unlock, "#e74c3c"),
        ("📡 IMEI Repair", app.show_imei_repair, "#e67e22"),
        ("💾 Firmware Flash", app.show_firmware_flash, "#2c3e50"),
        ("📤 Export PDF", app.show_export, colors["accent"]),
    ]

    for text, cmd, color in row2_actions:
        ctk.CTkButton(
            actions_row2, text=text, command=cmd,
            font=("Segoe UI", 13, "bold"), height=45,
            fg_color=color, hover_color=colors["accent_hover"],
            corner_radius=10
        ).pack(side="left", fill="x", expand=True, padx=3)

    # Status bar update
    app.update_status(
        f"Dashboard • {total_scans} scans • {len(device_names)} devices detected • "
        f"{total_faults} faults found • {len(repairs)} repairs"
    )
