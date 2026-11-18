"""
UART Boot Log Analyzer — LUOWEI LW-FAT style motherboard fault detection.

Captures UART serial port logs from phone motherboards and analyzes them
for hardware faults. Two modes:
  1. Live Capture  — connect to UART port, capture boot logs in real-time
  2. Import & Analyze — load a .txt/.log file and analyze it offline

Detects faults in: PMIC, CPU, Storage, Display, Modem, WiFi, Audio, and more.
Pattern-matches 80+ known error signatures against boot log output.
"""

import customtkinter as ctk
import threading
import datetime as _dt
from pathlib import Path


def render_uart_analysis(app):
    """UART Boot Log Analyzer page — LUOWEI-style motherboard fault detection
    via UART serial boot logs with AI-powered diagnostics."""
    colors = app.colors

    # ── Title ──────────────────────────────────────────────────────────────
    ctk.CTkLabel(
        app.content, text="🔌 Boot Log Fault Analyzer",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Motherboard fault detection via serial boot logs — AI-powered diagnostics",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card: What UART analysis detects ──────────────────────────────
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(
        info, text="🔍 Boot Log Fault Analysis Can Detect:",
        font=("Segoe UI", 16, "bold"), text_color=colors["info"],
    ).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ Live Capture — Real-time serial port log capture (TX/GND connection)",
        "✅ Boot Log Analysis — Pattern matching against 80+ known error signatures",
        "✅ Fault Detection — PMIC, CPU, Storage, Display, Modem, WiFi, Audio faults",
        "✅ Repair Suggestions — Component-level repair recommendations",
        "✅ Boot Stage Tracking — SBL → XBL → ABL → Kernel → Android boot progress",
        "✅ Severity Classification — Critical, High, Medium, Low fault ranking",
    ]
    for item in detect_items:
        ctk.CTkLabel(
            info, text=f"  {item}", font=("Segoe UI", 12),
            text_color=colors["text_dim"],
        ).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Connection Panel ───────────────────────────────────────────────────
    conn_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    conn_card.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(
        conn_card, text="🔌 Serial Connection",
        font=("Segoe UI", 16, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", padx=20, pady=(15, 10))

    conn_inner = ctk.CTkFrame(conn_card, fg_color="transparent")
    conn_inner.pack(fill="x", padx=20, pady=(0, 15))

    # Port selection
    ctk.CTkLabel(
        conn_inner, text="Port:", font=("Segoe UI", 12, "bold"),
        text_color=colors["text"],
    ).pack(side="left")

    port_combo = ctk.CTkComboBox(
        conn_inner, values=["No ports found"], width=220, height=36,
        fg_color=colors["bg_light"], border_color=colors["border"],
        button_color=colors["accent"], dropdown_fg_color=colors["bg_card"],
        dropdown_hover_color=colors["bg_light"],
        text_color=colors["text"], font=("Consolas", 11),
    )
    port_combo.pack(side="left", padx=(8, 5))
    port_combo.set("No ports found")

    def refresh_ports():
        """Scan system for available serial/COM ports."""
        try:
            # Check if widgets still exist before updating
            if not app.content.winfo_exists():
                return
            import serial.tools.list_ports
            ports = [f"{p.device} - {p.description}" for p in serial.tools.list_ports.comports()]
            port_combo.configure(values=ports if ports else ["No ports found"])
            if ports:
                port_combo.set(ports[0])
                conn_status_label.configure(
                    text=f"Found {len(ports)} port(s)", text_color=colors["success"],
                )
            else:
                port_combo.set("No ports found")
                conn_status_label.configure(
                    text="No serial ports detected", text_color=colors["warning"],
                )
        except ImportError:
            try:
                port_combo.configure(values=["pyserial not installed"])
                port_combo.set("pyserial not installed")
                conn_status_label.configure(
                    text="Install pyserial: pip install pyserial", text_color=colors["accent"],
                )
            except Exception:
                pass
        except Exception:
            pass

    ctk.CTkButton(
        conn_inner, text="🔄 Refresh", width=90, height=36,
        fg_color=colors["bg_light"], hover_color=colors["border"],
        text_color=colors["text_dim"], font=("Segoe UI", 11),
        command=refresh_ports,
    ).pack(side="left", padx=(0, 15))

    # Baud rate
    ctk.CTkLabel(
        conn_inner, text="Baud:", font=("Segoe UI", 12, "bold"),
        text_color=colors["text"],
    ).pack(side="left")

    baud_values = ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
    baud_combo = ctk.CTkComboBox(
        conn_inner, values=baud_values, width=120, height=36,
        fg_color=colors["bg_light"], border_color=colors["border"],
        button_color=colors["accent"], dropdown_fg_color=colors["bg_card"],
        dropdown_hover_color=colors["bg_light"],
        text_color=colors["text"], font=("Consolas", 11),
    )
    baud_combo.pack(side="left", padx=(8, 15))
    baud_combo.set("115200")

    # Connect / Disconnect button
    uart_state = {
        "connected": False,
        "uart": None,
        "capturing": False,
        "captured_lines": [],
        "capture_start": None,
    }

    connect_btn = ctk.CTkButton(
        conn_inner, text="Connect", width=120, height=36,
        fg_color=colors["success"], hover_color="#27ae60",
        font=("Segoe UI", 12, "bold"),
    )
    connect_btn.pack(side="left", padx=(0, 15))

    # Connection status label
    conn_status_label = ctk.CTkLabel(
        conn_inner, text="Disconnected",
        font=("Segoe UI", 12), text_color=colors["text_dim"],
    )
    conn_status_label.pack(side="left", padx=(0, 10))

    # Status dot
    conn_dot = ctk.CTkLabel(
        conn_inner, text="●", font=("Segoe UI", 14),
        text_color=colors["accent"],
    )
    conn_dot.pack(side="left")

    def _get_selected_port():
        """Extract COM port name from combo selection (e.g. 'COM3 - USB Serial' -> 'COM3')."""
        val = port_combo.get()
        if not val or val in ("No ports found", "pyserial not installed"):
            return None
        return val.split(" - ")[0].strip()

    def connect_uart():
        """Connect or disconnect the UART serial port."""
        if uart_state["connected"]:
            # Disconnect
            try:
                if uart_state["uart"]:
                    uart_state["uart"].disconnect()
            except Exception:
                pass
            uart_state["connected"] = False
            uart_state["uart"] = None
            connect_btn.configure(text="Connect", fg_color=colors["success"])
            conn_status_label.configure(text="Disconnected", text_color=colors["text_dim"])
            conn_dot.configure(text_color=colors["accent"])
            msg_label.configure(text="Disconnected", text_color=colors["text_dim"])
            return

        # Connect
        port = _get_selected_port()
        if not port:
            conn_status_label.configure(
                text="Select a valid port first", text_color=colors["accent"],
            )
            return

        baud = int(baud_combo.get())

        try:
            from app.hardware.uart_analyzer import UARTConnection
            uart = UARTConnection(port=port, baud_rate=baud)
            uart.connect()
            uart_state["connected"] = True
            uart_state["uart"] = uart
            connect_btn.configure(text="Disconnect", fg_color=colors["accent"])
            conn_status_label.configure(
                text=f"Connected to {port} @ {baud}", text_color=colors["success"],
            )
            conn_dot.configure(text_color=colors["success"])
            msg_label.configure(
                text=f"Connected: {port} at {baud} baud", text_color=colors["success"],
            )
        except ImportError:
            conn_status_label.configure(
                text="uart_analyzer module not found", text_color=colors["accent"],
            )
            msg_label.configure(
                text="Missing: app/hardware/uart_analyzer.py", text_color=colors["accent"],
            )
        except Exception as e:
            conn_status_label.configure(
                text=f"Connection failed: {str(e)[:50]}", text_color=colors["accent"],
            )
            msg_label.configure(
                text=f"Connection error: {str(e)[:80]}", text_color=colors["accent"],
            )

    connect_btn.configure(command=connect_uart)

    # Initial port scan
    app.content.after(500, refresh_ports)

    # ── Progress bar + message ─────────────────────────────────────────────
    progress = ctk.CTkProgressBar(
        app.content, width=600, height=16,
        progress_color=colors["accent"], fg_color=colors["bg_light"],
    )
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(
        app.content, text="",
        font=("Segoe UI", 12), text_color=colors["text_dim"],
    )
    msg_label.pack(anchor="w", padx=20, pady=(0, 10))

    # ── Action Buttons Row ─────────────────────────────────────────────────
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    # ── Result cards container (two-column) ────────────────────────────────
    cards_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    cards_frame.pack(fill="x", padx=20, pady=(0, 10))

    cards_left = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_left.pack(side="left", fill="both", expand=True, padx=(0, 5))
    cards_right = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_right.pack(side="left", fill="both", expand=True, padx=(5, 0))

    # ── Analysis Summary card (LEFT) ───────────────────────────────────────
    summary_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    summary_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(
        summary_card, text="📊 Analysis Summary",
        font=("Segoe UI", 14, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", padx=15, pady=(12, 5))

    summary_fields = [
        ("total_lines", "Total Lines"),
        ("capture_duration", "Capture Duration"),
        ("boot_stage", "Last Boot Stage"),
        ("overall_status", "Overall Status"),
    ]
    summary_labels = {}
    for key, name in summary_fields:
        row = ctk.CTkFrame(summary_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(
            row, text=name, font=("Segoe UI", 11, "bold"),
            text_color=colors["text"], width=130, anchor="w",
        ).pack(side="left", padx=8)
        val = ctk.CTkLabel(
            row, text="—", font=("Consolas", 11),
            text_color=colors["text_dim"], anchor="w",
        )
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(
            row, text="●", font=("Segoe UI", 10),
            text_color=colors["text_dim"], width=20,
        )
        dot.pack(side="right", padx=8)
        summary_labels[key] = (val, dot)
    ctk.CTkFrame(summary_card, fg_color="transparent", height=8).pack()

    # ── Fault Summary card (LEFT) ──────────────────────────────────────────
    fault_summary_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    fault_summary_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(
        fault_summary_card, text="🔴 Fault Summary",
        font=("Segoe UI", 14, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", padx=15, pady=(12, 5))

    fault_sum_fields = [
        ("critical_count", "Critical"),
        ("high_count", "High"),
        ("medium_count", "Medium"),
        ("low_count", "Low"),
        ("primary_fault", "Primary Fault"),
    ]
    fault_sum_labels = {}
    for key, name in fault_sum_fields:
        row = ctk.CTkFrame(fault_summary_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(
            row, text=name, font=("Segoe UI", 11, "bold"),
            text_color=colors["text"], width=130, anchor="w",
        ).pack(side="left", padx=8)
        val = ctk.CTkLabel(
            row, text="—", font=("Consolas", 11),
            text_color=colors["text_dim"], anchor="w",
        )
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(
            row, text="●", font=("Segoe UI", 10),
            text_color=colors["text_dim"], width=20,
        )
        dot.pack(side="right", padx=8)
        fault_sum_labels[key] = (val, dot)
    ctk.CTkFrame(fault_summary_card, fg_color="transparent", height=8).pack()

    # ── Primary Fault card (RIGHT) ─────────────────────────────────────────
    primary_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    primary_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(
        primary_card, text="⚠️ Primary Fault Detail",
        font=("Segoe UI", 14, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", padx=15, pady=(12, 5))

    primary_fields = [
        ("fault_component", "Component"),
        ("fault_severity", "Severity"),
        ("fault_description", "Description"),
        ("fault_repair", "Repair Action"),
    ]
    primary_labels = {}
    for key, name in primary_fields:
        row = ctk.CTkFrame(primary_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(
            row, text=name, font=("Segoe UI", 11, "bold"),
            text_color=colors["text"], width=130, anchor="w",
        ).pack(side="left", padx=8)
        val = ctk.CTkLabel(
            row, text="—", font=("Consolas", 11),
            text_color=colors["text_dim"], anchor="w",
        )
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(
            row, text="●", font=("Segoe UI", 10),
            text_color=colors["text_dim"], width=20,
        )
        dot.pack(side="right", padx=8)
        primary_labels[key] = (val, dot)
    ctk.CTkFrame(primary_card, fg_color="transparent", height=8).pack()

    # ── Boot Stage Tracker card (RIGHT) ────────────────────────────────────
    boot_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    boot_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(
        boot_card, text="🚀 Boot Stage Progress",
        font=("Segoe UI", 14, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", padx=15, pady=(12, 5))

    boot_stages = ["PBL", "SBL", "XBL", "ABL", "Kernel", "Android"]
    boot_stage_labels = {}
    for stage in boot_stages:
        row = ctk.CTkFrame(boot_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(
            row, text=stage, font=("Segoe UI", 11, "bold"),
            text_color=colors["text"], width=100, anchor="w",
        ).pack(side="left", padx=8)
        status_lbl = ctk.CTkLabel(
            row, text="Waiting", font=("Consolas", 11),
            text_color=colors["text_dim"], anchor="w",
        )
        status_lbl.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(
            row, text="●", font=("Segoe UI", 10),
            text_color=colors["text_dim"], width=20,
        )
        dot.pack(side="right", padx=8)
        boot_stage_labels[stage] = (status_lbl, dot)
    ctk.CTkFrame(boot_card, fg_color="transparent", height=8).pack()

    # ── Color tags setup ───────────────────────────────────────────────────
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#34d399")
        tb.tag_configure("warning", foreground="#fbbf24")
        tb.tag_configure("fault", foreground="#ec4899")
        tb.tag_configure("info", foreground="#a855f7")
        tb.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))
        tb.tag_configure("dim", foreground="#9a93b5")
        tb.tag_configure("critical", foreground="#f43f5e", font=("Consolas", 11, "bold"))
        tb.tag_configure("high_sev", foreground="#fbbf24", font=("Consolas", 11, "bold"))
        tb.tag_configure("medium_sev", foreground="#eccc68")
        tb.tag_configure("low_sev", foreground="#9a93b5")
        tb.tag_configure("stage", foreground="#7bed9f", font=("Consolas", 11, "bold"))
        tb.tag_configure("component", foreground="#70a1ff", font=("Consolas", 11, "bold"))
        tb.tag_configure("repair", foreground="#5352ed", font=("Consolas", 11))

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["critical", "🔴", "fatal", "panic", "fail", "dead", "[xx]", "❌"]):
            return "fault"
        if any(k in t for k in ["warning", "🟡", "⚠️", "[!!]", "degraded", "high"]):
            return "warning"
        if any(k in t for k in ["✅", "[ok]", "ok", "pass", "success", "healthy", "good", "normal"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "========", "REPORT", "PHASE", "BOOT", "MOOXY"]):
            return "header"
        if any(k in t for k in ["🔍", "scanning", "detecting", "reading", "checking", "capturing", "analyzing"]):
            return "info"
        if any(k in t for k in ["repair", "reball", "replace", "reflow", "solder"]):
            return "repair"
        return None

    # ── Live append helpers ────────────────────────────────────────────────
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

    def _append_tagged(text, tag):
        """Append text with a specific tag."""
        def _do():
            report_box.configure(state="normal")
            start = report_box._textbox.index("end-1c")
            report_box.insert("end", text + "\n")
            end = report_box._textbox.index("end-1c")
            report_box._textbox.tag_add(tag, start, end)
            report_box.see("end")
        app.content.after(0, _do)

    # ── Field update helper ────────────────────────────────────────────────
    def _set_field(labels_dict, key, value, ok=True):
        """Update a result field value and status dot."""
        if key in labels_dict:
            v, d = labels_dict[key]
            app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
            color = colors["success"] if ok else colors["accent"]
            app.content.after(0, lambda: d.configure(text_color=color))

    def _set_field_color(labels_dict, key, value, dot_color):
        """Update a result field with explicit dot color."""
        if key in labels_dict:
            v, d = labels_dict[key]
            app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
            app.content.after(0, lambda: d.configure(text_color=dot_color))

    # ── Reset all result cards ─────────────────────────────────────────────
    def _reset_cards():
        for labels_dict in [summary_labels, fault_sum_labels, primary_labels]:
            for key, (v, d) in labels_dict.items():
                v.configure(text="—", text_color=colors["text_dim"])
                d.configure(text_color=colors["text_dim"])
        for stage, (status_lbl, dot) in boot_stage_labels.items():
            status_lbl.configure(text="Waiting", text_color=colors["text_dim"])
            dot.configure(text_color=colors["text_dim"])

    # ── Severity helpers ───────────────────────────────────────────────────
    def _severity_icon(severity):
        s = str(severity).lower()
        if s == "critical":
            return "🔴"
        elif s == "high":
            return "🟠"
        elif s == "medium":
            return "🟡"
        else:
            return "⚪"

    def _severity_tag(severity):
        s = str(severity).lower()
        if s == "critical":
            return "critical"
        elif s == "high":
            return "high_sev"
        elif s == "medium":
            return "medium_sev"
        else:
            return "low_sev"

    def _severity_color(severity):
        s = str(severity).lower()
        if s == "critical":
            return "#f43f5e"
        elif s == "high":
            return "#fbbf24"
        elif s == "medium":
            return "#eccc68"
        else:
            return colors["text_dim"]

    # ── Display analysis results ───────────────────────────────────────────
    def _display_analysis(analysis, lines, capture_duration=None, full_report=None):
        """Render analysis results into report box and result cards."""
        if full_report is None:
            full_report = {"lines": []}

        def _track(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_lines(lines_list):
            full_report["lines"].extend(lines_list)
            _append_live_lines(lines_list)

        def _track_tagged(text, tag):
            full_report["lines"].append(text)
            _append_tagged(text, tag)

        # ── Report Header ──
        header = [
            "=" * 72,
            "  MOOXY AI FAULT DETECTOR — BOOT LOG FAULT ANALYSIS REPORT",
            "=" * 72,
            f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  Lines Analyzed: {len(lines)}",
        ]
        if capture_duration:
            header.append(f"  Capture Duration: {capture_duration}")
        header.extend(["=" * 72, ""])
        _track_lines(header)

        # ── Populate Analysis Summary card ──
        total_lines = len(lines)
        _set_field(summary_labels, "total_lines", f"{total_lines:,}")

        if capture_duration:
            _set_field(summary_labels, "capture_duration", str(capture_duration))
        else:
            _set_field(summary_labels, "capture_duration", "N/A (file import)")

        # Extract analysis attributes safely
        faults = []
        boot_stage_reached = "Unknown"
        overall_status = "Unknown"

        if hasattr(analysis, "faults"):
            faults = analysis.faults or []
        elif isinstance(analysis, dict):
            faults = analysis.get("faults", [])

        if hasattr(analysis, "boot_stage"):
            boot_stage_reached = analysis.boot_stage or "Unknown"
        elif isinstance(analysis, dict):
            boot_stage_reached = analysis.get("boot_stage", "Unknown")

        if hasattr(analysis, "overall_status"):
            overall_status = analysis.overall_status or "Unknown"
        elif isinstance(analysis, dict):
            overall_status = analysis.get("overall_status", "Unknown")

        _set_field(summary_labels, "boot_stage", boot_stage_reached)

        status_upper = str(overall_status).upper()
        if status_upper in ("OK", "GOOD", "NORMAL", "PASS"):
            _set_field_color(summary_labels, "overall_status", overall_status, colors["success"])
        elif status_upper in ("WARNING", "DEGRADED"):
            _set_field_color(summary_labels, "overall_status", overall_status, colors["warning"])
        else:
            _set_field_color(summary_labels, "overall_status", overall_status, colors["accent"])

        # ── Boot Stage Tracking ──
        _track("")
        _track("═══ BOOT STAGE PROGRESS ═══")
        _track("")

        boot_stages_detected = {}
        if hasattr(analysis, "boot_stages"):
            boot_stages_detected = analysis.boot_stages or {}
        elif isinstance(analysis, dict):
            boot_stages_detected = analysis.get("boot_stages", {})

        for stage in boot_stages:
            stage_info = boot_stages_detected.get(stage, boot_stages_detected.get(stage.lower(), None))
            if stage_info:
                if isinstance(stage_info, dict):
                    st = stage_info.get("status", "Detected")
                    is_ok = st.lower() in ("ok", "pass", "done", "detected", "complete")
                else:
                    st = str(stage_info)
                    is_ok = st.lower() in ("ok", "pass", "done", "detected", "complete")
                icon = "✅" if is_ok else "❌"
                _track(f"  {icon} {stage}: {st}")
                boot_stage_labels[stage][0].configure(text=st, text_color=colors["text"])
                boot_stage_labels[stage][1].configure(
                    text_color=colors["success"] if is_ok else colors["accent"])
            else:
                _track(f"  ⏸ {stage}: Not reached")
                boot_stage_labels[stage][0].configure(text="Not reached", text_color=colors["text_dim"])
                boot_stage_labels[stage][1].configure(text_color=colors["text_dim"])

        # ── Fault Classification ──
        critical_faults = [f for f in faults if _get_fault_severity(f).lower() == "critical"]
        high_faults = [f for f in faults if _get_fault_severity(f).lower() == "high"]
        medium_faults = [f for f in faults if _get_fault_severity(f).lower() == "medium"]
        low_faults = [f for f in faults if _get_fault_severity(f).lower() == "low"]

        _track("")
        _track("═══ FAULT CLASSIFICATION ═══")
        _track("")
        _track(f"  🔴 Critical: {len(critical_faults)}")
        _track(f"  🟠 High:     {len(high_faults)}")
        _track(f"  🟡 Medium:   {len(medium_faults)}")
        _track(f"  ⚪ Low:      {len(low_faults)}")
        _track(f"  ── Total:    {len(faults)} fault(s) detected")

        # Update Fault Summary card
        _set_field_color(fault_sum_labels, "critical_count",
                         str(len(critical_faults)),
                         colors["accent"] if critical_faults else colors["success"])
        _set_field_color(fault_sum_labels, "high_count",
                         str(len(high_faults)),
                         colors["warning"] if high_faults else colors["success"])
        _set_field_color(fault_sum_labels, "medium_count",
                         str(len(medium_faults)),
                         "#eccc68" if medium_faults else colors["success"])
        _set_field_color(fault_sum_labels, "low_count",
                         str(len(low_faults)),
                         colors["text_dim"] if low_faults else colors["success"])

        if faults:
            primary = faults[0]
            primary_name = _get_fault_attr(primary, "component", "Unknown")
            _set_field(fault_sum_labels, "primary_fault", primary_name, ok=False)
        else:
            _set_field(fault_sum_labels, "primary_fault", "None — all clear", ok=True)

        # ── Primary Fault Detail card ──
        if faults:
            pf = faults[0]
            pf_component = _get_fault_attr(pf, "component", "Unknown")
            pf_severity = _get_fault_attr(pf, "severity", "Unknown")
            pf_description = _get_fault_attr(pf, "description", "No description")
            pf_repair = _get_fault_attr(pf, "repair", "No repair info")

            _set_field(primary_labels, "fault_component", pf_component, ok=False)
            _set_field_color(primary_labels, "fault_severity", pf_severity,
                             _severity_color(pf_severity))
            _set_field(primary_labels, "fault_description", pf_description, ok=False)
            _set_field(primary_labels, "fault_repair", pf_repair, ok=False)
        else:
            _set_field(primary_labels, "fault_component", "None", ok=True)
            _set_field(primary_labels, "fault_severity", "None", ok=True)
            _set_field(primary_labels, "fault_description", "No faults detected", ok=True)
            _set_field(primary_labels, "fault_repair", "N/A", ok=True)

        # ── Detailed Fault List ──
        if faults:
            _track("")
            _track("═══ DETAILED FAULT REPORT ═══")
            _track("")

            for i, fault in enumerate(faults, 1):
                severity = _get_fault_severity(fault)
                component = _get_fault_attr(fault, "component", "Unknown")
                description = _get_fault_attr(fault, "description", "No description")
                line_num = _get_fault_attr(fault, "line_number", "")
                line_text = _get_fault_attr(fault, "line_text", "")
                repair = _get_fault_attr(fault, "repair", "")
                related_ics = _get_fault_attr(fault, "related_ics", "")

                icon = _severity_icon(severity)
                tag = _severity_tag(severity)

                _track(f"  {'─' * 60}")
                _track_tagged(
                    f"  {icon} {severity.upper()}: {description}",
                    tag
                )
                _track_tagged(
                    f"     Component: {component}",
                    "component"
                )

                if line_num:
                    line_display = f"     Line {line_num}"
                    if line_text:
                        line_display += f': "{line_text}"'
                    _track(line_display)

                if repair:
                    _track_tagged(f"     Repair: {repair}", "repair")

                if related_ics:
                    if isinstance(related_ics, list):
                        ics_str = ", ".join(related_ics)
                    else:
                        ics_str = str(related_ics)
                    _track(f"     Related ICs: {ics_str}")

                _track("")

        else:
            _track("")
            _track("═══ NO FAULTS DETECTED ═══")
            _track("")
            _track("  ✅ Boot log analysis complete — no known fault patterns found.")
            _track("  ✅ All boot stages appear normal.")
            _track("")

        # ── Additional analysis info ──
        error_lines = []
        if hasattr(analysis, "error_lines"):
            error_lines = analysis.error_lines or []
        elif isinstance(analysis, dict):
            error_lines = analysis.get("error_lines", [])

        if error_lines:
            _track("═══ RAW ERROR LINES FROM LOG ═══")
            _track("")
            for eline in error_lines[:50]:
                if isinstance(eline, dict):
                    lno = eline.get("line_number", "?")
                    ltxt = eline.get("text", "")
                    _track(f"  [{lno}] {ltxt}")
                else:
                    _track(f"  {eline}")
            if len(error_lines) > 50:
                _track(f"  ... and {len(error_lines) - 50} more error lines")
            _track("")

        # ── Footer ──
        _track("=" * 72)
        _track("  Report generated by Mooxy AI Fault Detector — Boot Log Fault Analyzer")
        _track(f"  {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        _track("=" * 72)

        return full_report

    # ── Fault attribute extraction helpers ─────────────────────────────────
    def _get_fault_severity(fault):
        if hasattr(fault, "severity"):
            return str(fault.severity)
        elif isinstance(fault, dict):
            return str(fault.get("severity", "unknown"))
        return "unknown"

    def _get_fault_attr(fault, attr, default=""):
        if hasattr(fault, attr):
            val = getattr(fault, attr, default)
            return val if val is not None else default
        elif isinstance(fault, dict):
            val = fault.get(attr, default)
            return val if val is not None else default
        return default

    # ══════════════════════════════════════════════════════════════════════
    #  MODE 1: LIVE UART CAPTURE
    # ══════════════════════════════════════════════════════════════════════

    def start_capture():
        """Start capturing UART serial output in real-time."""
        if running["value"]:
            return
        if not uart_state["connected"] or not uart_state["uart"]:
            msg_label.configure(
                text="Connect to UART port first!", text_color=colors["accent"],
            )
            return

        running["value"] = True
        uart_state["capturing"] = True
        uart_state["captured_lines"] = []
        uart_state["capture_start"] = _dt.datetime.now()

        # Reset UI
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        _reset_cards()
        progress.set(0)
        msg_label.configure(text="Capturing boot log...", text_color=colors["info"])
        capture_btn.configure(state="disabled")
        stop_btn.configure(state="normal")

        # Header
        header_lines = [
            "=" * 72,
            f"  LIVE UART CAPTURE — {_get_selected_port()} @ {baud_combo.get()} baud",
            f"  Started: {uart_state['capture_start'].strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 72,
            "",
            "Waiting for boot log output...",
            "",
        ]
        _append_live_lines(header_lines)

        line_counter = {"count": 0}

        def on_line_received(line):
            """Callback for each line received from UART."""
            uart_state["captured_lines"].append(line)
            line_counter["count"] += 1

            # Show live output
            def _show():
                report_box.configure(state="normal")
                prefix = f"[{line_counter['count']:>5d}] "
                tag = _get_tag(line)
                if tag:
                    start = report_box._textbox.index("end-1c")
                    report_box.insert("end", prefix + line + "\n")
                    end = report_box._textbox.index("end-1c")
                    report_box._textbox.tag_add(tag, start, end)
                else:
                    report_box.insert("end", prefix + line + "\n")
                report_box.see("end")

                # Update line counter in summary card
                summary_labels["total_lines"][0].configure(
                    text=str(line_counter["count"]),
                    text_color=colors["text"],
                )

                # Update capture duration
                if uart_state["capture_start"]:
                    elapsed = _dt.datetime.now() - uart_state["capture_start"]
                    elapsed_str = str(elapsed).split(".")[0]
                    summary_labels["capture_duration"][0].configure(
                        text=elapsed_str, text_color=colors["text"],
                    )

                # Update progress message
                msg_label.configure(
                    text=f"Capturing... {line_counter['count']} lines received",
                    text_color=colors["info"],
                )

            app.content.after(0, _show)

        # Start capture in background
        def run_capture():
            try:
                uart = uart_state["uart"]
                uart.start_capture(callback=on_line_received)
            except Exception as e:
                app.content.after(0, lambda: msg_label.configure(
                    text=f"Capture error: {str(e)[:80]}", text_color=colors["accent"],
                ))
                running["value"] = False
                uart_state["capturing"] = False
                app.content.after(0, lambda: capture_btn.configure(state="normal"))
                app.content.after(0, lambda: stop_btn.configure(state="disabled"))

        threading.Thread(target=run_capture, daemon=True).start()

    def stop_and_analyze():
        """Stop UART capture and analyze the captured boot log."""
        if not uart_state["capturing"]:
            msg_label.configure(
                text="No active capture to stop", text_color=colors["warning"],
            )
            return

        uart_state["capturing"] = False
        msg_label.configure(text="Stopping capture and analyzing...", text_color=colors["info"])
        progress.set(0.1)

        # Stop capture
        captured_lines = []
        try:
            uart = uart_state["uart"]
            captured_lines = uart.stop_capture()
            if not captured_lines:
                captured_lines = list(uart_state["captured_lines"])
        except Exception:
            captured_lines = list(uart_state["captured_lines"])

        # Calculate duration
        capture_duration = None
        if uart_state["capture_start"]:
            elapsed = _dt.datetime.now() - uart_state["capture_start"]
            capture_duration = str(elapsed).split(".")[0]

        stop_btn.configure(state="disabled")
        capture_btn.configure(state="normal")

        # Clear report box for analysis output
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")

        # Run analysis in background
        def run_analysis():
            full_report = {"lines": []}
            try:
                from app.hardware.uart_analyzer import analyze_boot_log

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                analysis = analyze_boot_log(captured_lines, callback=cb)
                _display_analysis(analysis, captured_lines, capture_duration, full_report)

            except ImportError:
                full_report["lines"].append("Module not found — running basic pattern analysis")
                _append_live("⚠️ uart_analyzer module not found — running built-in pattern match")
                _append_live("")
                analysis = _builtin_pattern_analysis(captured_lines)
                _display_analysis(analysis, captured_lines, capture_duration, full_report)

            except Exception as e:
                _append_live(f"❌ Analysis error: {str(e)}")
                full_report["lines"].append(f"Error: {str(e)}")

            # Save report
            _save_report_and_history(full_report, captured_lines, capture_duration, "live_capture")

            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text=f"Analysis complete — {len(captured_lines)} lines analyzed",
                text_color=colors["success"],
            ))
            running["value"] = False

        threading.Thread(target=run_analysis, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    #  MODE 2: IMPORT LOG FILE & ANALYZE
    # ══════════════════════════════════════════════════════════════════════

    def import_log():
        """Open file dialog to import a UART/boot log file and analyze it."""
        if running["value"]:
            return

        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Import UART / Boot Log File",
            filetypes=[
                ("Log files", "*.txt *.log *.ips *.panic *.crash"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        running["value"] = True

        # Reset UI
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        _reset_cards()
        progress.set(0)
        msg_label.configure(text=f"Loading {Path(path).name}...", text_color=colors["info"])

        # Read file
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw_lines = f.readlines()
        except Exception as e:
            msg_label.configure(
                text=f"Failed to read file: {str(e)[:80]}", text_color=colors["accent"],
            )
            running["value"] = False
            return

        lines = [line.rstrip("\n\r") for line in raw_lines]
        msg_label.configure(
            text=f"Loaded {len(lines):,} lines from {Path(path).name} — analyzing...",
            text_color=colors["info"],
        )
        progress.set(0.1)

        # Show file preview
        preview_lines = [
            "=" * 72,
            f"  IMPORTED LOG: {Path(path).name}",
            f"  Lines: {len(lines):,}",
            f"  Size: {Path(path).stat().st_size:,} bytes",
            "=" * 72,
            "",
            "  First 20 lines of log:",
            "  " + "─" * 40,
        ]
        for i, line in enumerate(lines[:20], 1):
            preview_lines.append(f"  [{i:>5d}] {line[:120]}")
        if len(lines) > 20:
            preview_lines.append(f"  ... ({len(lines) - 20} more lines)")
        preview_lines.extend(["", "  Analyzing...", ""])
        _append_live_lines(preview_lines)

        def run_analysis():
            full_report = {"lines": list(preview_lines)}
            try:
                from app.hardware.uart_analyzer import analyze_boot_log

                def cb(pct, msg):
                    # Scale from 0.1 to 0.95
                    actual_pct = 0.1 + (pct * 0.85)
                    app.content.after(0, lambda: progress.set(actual_pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                analysis = analyze_boot_log(lines, callback=cb)
                _display_analysis(analysis, lines, None, full_report)

            except ImportError:
                _append_live("⚠️ uart_analyzer module not found — running built-in pattern match")
                _append_live("")
                full_report["lines"].append("Using built-in pattern analysis")
                analysis = _builtin_pattern_analysis(lines)
                _display_analysis(analysis, lines, None, full_report)

            except Exception as e:
                _append_live(f"❌ Analysis error: {str(e)}")
                full_report["lines"].append(f"Error: {str(e)}")

            # Save report
            _save_report_and_history(full_report, lines, None, "file_import")

            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text=f"Analysis complete — {len(lines):,} lines from {Path(path).name}",
                text_color=colors["success"],
            ))
            running["value"] = False

        threading.Thread(target=run_analysis, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    #  BUILT-IN PATTERN ANALYSIS (fallback when uart_analyzer not installed)
    # ══════════════════════════════════════════════════════════════════════

    def _builtin_pattern_analysis(lines):
        """
        Basic built-in boot log fault detection using regex pattern matching.
        Used as a fallback when app.hardware.uart_analyzer is not available.
        Returns a dict matching the expected analysis result format.
        """
        import re

        # Known fault patterns: (regex, severity, component, description, repair, related_ics)
        fault_patterns = [
            # PMIC faults
            (r"pmic.*init.*fail|pmic.*error|SPMI.*bus.*error|pm\d{4}.*fail",
             "critical", "PMIC (Power Management IC)",
             "PMIC initialization failure detected",
             "Check PMIC solder joints. Reball or replace PMIC IC. Verify VDD supply lines.",
             ["PM8150", "PM8350", "PMK8350", "PMR735A"]),
            (r"pmic.*over.?current|pmic.*short|pmic.*uvlo",
             "critical", "PMIC (Power Management IC)",
             "PMIC overcurrent / short circuit / UVLO detected",
             "Check for shorts around PMIC. Inspect capacitors on power rails. Replace PMIC if dead short.",
             ["PM8150", "PM8350"]),

            # CPU / SoC faults
            (r"cpu.*hang|cpu.*stuck|watchdog.*reset|wdt.*bark|wdt.*bite",
             "critical", "CPU / SoC",
             "CPU hang or watchdog reset detected",
             "Check CPU solder joints. Reball SoC if necessary. Verify clock crystal.",
             ["Snapdragon SoC", "CPU BGA"]),
            (r"thermal.*shutdown|tsens.*critical|cpu.*thermal.*trip",
             "high", "CPU / Thermal",
             "CPU thermal shutdown or overheating detected",
             "Check thermal paste. Inspect heat sink/shield. May indicate shorted CPU rail.",
             ["SoC", "Thermal Sensor"]),

            # Storage (UFS/eMMC) faults
            (r"ufs.*error|ufs.*fail|ufs.*timeout|sdhci.*error|emmc.*fail|storage.*init.*fail",
             "critical", "Storage (UFS/eMMC)",
             "Storage controller initialization failure",
             "Check UFS/eMMC IC solder joints. Reball storage chip. Verify VCCQ/VCC rails.",
             ["UFS IC", "eMMC", "Storage Controller"]),
            (r"ufs.*link.*down|ufs.*hibern.*fail|ufs.*gear.*change.*fail",
             "high", "Storage (UFS)",
             "UFS link or hibernate failure",
             "Reball UFS IC. Check data lines. May need new UFS chip.",
             ["UFS IC"]),

            # DDR / Memory faults
            (r"ddr.*fail|ddr.*training.*fail|memory.*error|dram.*init.*fail|lpddr.*error",
             "critical", "DDR / Memory",
             "DDR memory initialization or training failure",
             "Reball or replace RAM IC. Check VDD2/VDDQ power supply to DDR.",
             ["LPDDR4X", "LPDDR5", "RAM IC"]),

            # Display / DSI faults
            (r"dsi.*error|dsi.*timeout|mdss.*fail|display.*init.*fail|panel.*detect.*fail",
             "high", "Display (DSI/MDSS)",
             "Display DSI interface or panel initialization failure",
             "Check display connector. Inspect DSI data lines. Replace display flex cable.",
             ["Display IC", "DSI PHY"]),
            (r"backlight.*fail|wled.*error|lcd.*no.*signal",
             "medium", "Display (Backlight)",
             "Backlight or WLED driver failure",
             "Check backlight driver IC and FPC connector. Verify WLED boost circuit.",
             ["Backlight IC", "WLED Driver"]),

            # Modem / Baseband faults
            (r"modem.*crash|modem.*assert|baseband.*fail|mdm.*error|rild.*error",
             "high", "Modem / Baseband",
             "Modem or baseband processor crash",
             "Check modem RF IC. Inspect PA (Power Amplifier) and antenna switch. May need baseband reball.",
             ["Modem IC", "RF Transceiver", "PA"]),
            (r"no.*sim|sim.*detect.*fail|sim.*card.*error|uicc.*error",
             "medium", "SIM Interface",
             "SIM card detection failure",
             "Check SIM card tray and connector. Inspect SIM IC and ESD protection.",
             ["SIM IC", "ESD IC"]),

            # WiFi / Bluetooth faults
            (r"wifi.*fail|wlan.*error|wcn.*error|wcn.*crash|wifi.*fw.*crash",
             "high", "WiFi / WLAN",
             "WiFi chip initialization failure or firmware crash",
             "Reball WiFi IC. Check antenna connection and RF filter.",
             ["WCN3990", "WCN6855", "WiFi IC"]),
            (r"bt.*error|bluetooth.*fail|bt.*fw.*fail",
             "medium", "Bluetooth",
             "Bluetooth initialization failure",
             "Check BT antenna. WiFi/BT combo IC may need reball.",
             ["WiFi/BT Combo IC"]),

            # Audio faults
            (r"codec.*error|audio.*fail|wcd.*error|wsa.*error|speaker.*amp.*fail",
             "medium", "Audio Codec",
             "Audio codec or amplifier failure",
             "Check audio codec IC solder joints. Verify speaker amplifier. Inspect audio flex.",
             ["WCD9380", "WSA8815", "Audio Codec IC"]),

            # Camera faults
            (r"camera.*fail|cci.*error|sensor.*probe.*fail|cam.*power.*fail",
             "medium", "Camera",
             "Camera sensor probe or power failure",
             "Check camera connector FPC. Verify camera PMIC rails (VANA, VDIG, VIO).",
             ["Camera Sensor", "Camera PMIC"]),

            # Charging faults
            (r"charger.*error|smb.*fail|chg.*fail|battery.*missing|fg.*error",
             "high", "Charging / Battery",
             "Charging IC or fuel gauge error",
             "Check charging IC. Inspect battery connector. Verify USB-C CC lines.",
             ["SMB1390", "SMB1396", "Fuel Gauge IC"]),

            # USB faults
            (r"usb.*fail|usb.*error|dwc3.*error|usb.*phy.*fail|type.?c.*error",
             "medium", "USB / Type-C",
             "USB controller or PHY failure",
             "Check USB Type-C port and CC chips. Inspect USB PHY on SoC.",
             ["USB PHY", "Type-C Controller"]),

            # Secure boot / authentication
            (r"auth.*fail|secure.*boot.*fail|signature.*verif.*fail|anti.?rollback",
             "high", "Secure Boot",
             "Secure boot authentication failure",
             "May indicate tampered firmware or wrong firmware version. Reflash correct firmware.",
             []),

            # Clock / PLL faults
            (r"pll.*lock.*fail|clock.*error|xo.*fail|19\.2.*mhz.*fail",
             "high", "Clock / PLL",
             "PLL lock or crystal oscillator failure",
             "Check 19.2 MHz crystal oscillator. Inspect PLL circuits on SoC.",
             ["XO Crystal", "PLL"]),

            # I2C / SPI bus errors
            (r"i2c.*error|i2c.*timeout|spi.*error|spi.*timeout",
             "medium", "Bus (I2C/SPI)",
             "I2C or SPI bus communication error",
             "Check bus pull-up resistors. Inspect connected IC solder joints.",
             []),

            # NFC faults
            (r"nfc.*error|nfc.*fail|nfc.*fw.*fail|ese.*error",
             "low", "NFC",
             "NFC controller initialization failure",
             "Check NFC antenna connection. May need NFC IC reball.",
             ["NFC Controller IC"]),

            # GPS faults
            (r"gps.*fail|gnss.*error|location.*hw.*fail",
             "low", "GPS / GNSS",
             "GPS/GNSS hardware failure",
             "Check GPS antenna. Inspect RF path and LNA.",
             ["GPS LNA", "GNSS IC"]),

            # Fingerprint sensor
            (r"fingerprint.*error|fps.*fail|fpc.*error|goodix.*fail",
             "low", "Fingerprint Sensor",
             "Fingerprint sensor initialization failure",
             "Check fingerprint sensor FPC connector. Replace sensor module if damaged.",
             ["FPC1028", "Goodix Sensor"]),

            # General boot failures
            (r"kernel.*panic|unable.*to.*mount.*root|init.*fail|ramdisk.*fail",
             "critical", "Kernel / Boot",
             "Kernel panic or boot init failure",
             "May indicate corrupt firmware or storage issue. Try reflashing full firmware.",
             []),
            (r"subsys.*crash|ssr|subsystem.*restart",
             "high", "Subsystem",
             "Subsystem crash / restart detected",
             "Identify which subsystem crashed (modem/adsp/cdsp). Check related IC.",
             []),
        ]

        faults = []
        error_lines = []
        boot_stages_found = {}

        # Boot stage detection patterns
        stage_patterns = {
            "PBL": r"PBL|primary.*boot|pbl_.*start",
            "SBL": r"SBL\d|sbl.*start|secondary.*boot",
            "XBL": r"XBL|xbl.*start|extensible.*boot",
            "ABL": r"ABL|abl.*start|android.*boot.*loader|fastboot",
            "Kernel": r"Linux.*version|Booting.*Linux|starting.*kernel",
            "Android": r"init.*first.*stage|zygote|SystemServer|android.*boot.*complete",
        }

        last_stage = "Unknown"

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            # Check boot stages
            for stage, pattern in stage_patterns.items():
                if re.search(pattern, line_stripped, re.IGNORECASE):
                    boot_stages_found[stage] = {"status": "Detected"}
                    last_stage = stage

            # Check fault patterns
            for pattern, severity, component, description, repair, related in fault_patterns:
                if re.search(pattern, line_stripped, re.IGNORECASE):
                    # Avoid duplicate faults for same component+severity
                    already = any(
                        _get_fault_attr(f, "component") == component and
                        _get_fault_attr(f, "severity") == severity
                        for f in faults
                    )
                    if not already:
                        faults.append({
                            "severity": severity,
                            "component": component,
                            "description": description,
                            "line_number": i + 1,
                            "line_text": line_stripped[:120],
                            "repair": repair,
                            "related_ics": related,
                        })
                    # Track as error line regardless
                    error_lines.append({
                        "line_number": i + 1,
                        "text": line_stripped[:150],
                    })
                    break  # one match per line is enough

            # Also catch generic error/fail lines
            if re.search(r"\berror\b|\bfail\b|\bpanic\b|\bfatal\b|\bassert\b|\bcrash\b",
                         line_stripped, re.IGNORECASE):
                if not any(el.get("line_number") == i + 1 for el in error_lines):
                    error_lines.append({
                        "line_number": i + 1,
                        "text": line_stripped[:150],
                    })

        # Sort faults by severity (critical first)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        faults.sort(key=lambda f: severity_order.get(f.get("severity", "low"), 3))

        # Determine overall status
        if any(f["severity"] == "critical" for f in faults):
            overall = "CRITICAL — Hardware fault detected"
        elif any(f["severity"] == "high" for f in faults):
            overall = "WARNING — Potential hardware issue"
        elif faults:
            overall = "MINOR ISSUES — Check details"
        else:
            overall = "OK — No faults detected"

        return {
            "faults": faults,
            "error_lines": error_lines,
            "boot_stage": last_stage,
            "boot_stages": boot_stages_found,
            "overall_status": overall,
        }

    # ══════════════════════════════════════════════════════════════════════
    #  SAVE REPORT & HISTORY
    # ══════════════════════════════════════════════════════════════════════

    def _save_report_and_history(full_report, lines, capture_duration, source_type):
        """Save analysis report to file and add to detection history."""
        report_text = "\n".join(full_report.get("lines", []))

        # Save to log file
        try:
            from app.gui.history_manager import get_unique_log_path
            log_path = get_unique_log_path("uart_analysis")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            saved_name = log_path.name
            app.content.after(0, lambda: msg_label.configure(
                text=f"Saved: {saved_name} in config/logs/", text_color=colors["success"],
            ))
        except Exception as e:
            log_path = None
            print(f"[UART Analysis] Log save error: {e}")

        # Save raw captured lines (for AI analysis)
        raw_log_path = None
        if lines:
            try:
                from app.gui.history_manager import get_unique_log_path
                raw_log_path = get_unique_log_path("raw_uart")
                with open(raw_log_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
            except Exception:
                raw_log_path = None

        # Save to detection history
        try:
            from app.gui.history_manager import add_detection

            # Extract summary info
            total_faults = 0
            faults_text = ""
            primary_fault_name = "None"
            overall_health = "Unknown"

            if full_report.get("lines"):
                for line in full_report["lines"]:
                    if "Total:" in line and "fault" in line:
                        try:
                            total_faults = int(line.split("Total:")[1].strip().split()[0])
                        except (ValueError, IndexError):
                            pass
                    if "CRITICAL:" in line and primary_fault_name == "None":
                        primary_fault_name = line.split("CRITICAL:")[-1].strip()[:80]
                    elif "HIGH:" in line and primary_fault_name == "None":
                        primary_fault_name = line.split("HIGH:")[-1].strip()[:80]

            for key, (v, _) in summary_labels.items():
                if key == "overall_status":
                    overall_health = v.cget("text")

            summary_text = (
                f"Lines: {len(lines):,} | "
                f"Source: {source_type} | "
                f"Faults: {total_faults} | "
                f"Status: {overall_health}"
            )
            if capture_duration:
                summary_text = f"Duration: {capture_duration} | " + summary_text

            add_detection(
                detection_type="FAULT_LOG",
                device_name=f"Boot Log Fault Analysis ({source_type})",
                summary=summary_text,
                faults_count=total_faults,
                faults_summary=primary_fault_name,
                report_file=str(log_path) if log_path else "",
                extra={
                    "overall_health": overall_health,
                    "source": source_type,
                    "total_lines": len(lines),
                    "capture_duration": str(capture_duration) if capture_duration else None,
                    "raw_log_file": str(raw_log_path) if raw_log_path else "",
                },
            )
        except Exception as e:
            print(f"[UART Analysis] History save error: {e}")

    # ══════════════════════════════════════════════════════════════════════
    #  COPY / SAVE BUTTONS
    # ══════════════════════════════════════════════════════════════════════

    def copy_report():
        try:
            text = report_box.get("1.0", "end").strip()
            if text:
                app.clipboard_clear()
                app.clipboard_append(text)
                msg_label.configure(text="📋 Report copied to clipboard!", text_color=colors["success"])
        except Exception:
            pass

    def save_report():
        try:
            from tkinter import filedialog
            text = report_box.get("1.0", "end").strip()
            if not text:
                return
            path = filedialog.asksaveasfilename(
                title="Save UART Analysis Report",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                initialfile=f"uart_analysis_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                msg_label.configure(text=f"💾 Saved to: {path}", text_color=colors["success"])
        except Exception:
            pass

    # ── Place action buttons ───────────────────────────────────────────────
    capture_btn = ctk.CTkButton(
        btn_frame, text="▶ Start Capture", width=170, height=46,
        fg_color=colors["accent"], hover_color=colors["accent_hover"],
        font=("Segoe UI", 14, "bold"), corner_radius=10,
        command=start_capture,
    )
    capture_btn.pack(side="left", padx=(0, 8))

    stop_btn = ctk.CTkButton(
        btn_frame, text="⏹ Stop & Analyze", width=170, height=46,
        fg_color=colors["warning"], hover_color="#e67e22",
        font=("Segoe UI", 14, "bold"), corner_radius=10,
        command=stop_and_analyze,
    )
    stop_btn.pack(side="left", padx=(0, 8))
    stop_btn.configure(state="disabled")

    ctk.CTkButton(
        btn_frame, text="📂 Import Log File", width=170, height=46,
        fg_color=colors["info"], hover_color="#1565c0",
        font=("Segoe UI", 14, "bold"), corner_radius=10,
        command=import_log,
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(
        btn_frame, text="📋 Copy", width=90, height=46,
        fg_color=colors["bg_light"], hover_color=colors["border"],
        text_color=colors["text_dim"],
        font=("Segoe UI", 13, "bold"), corner_radius=10,
        command=copy_report,
    ).pack(side="left", padx=(0, 8))

    ctk.CTkButton(
        btn_frame, text="💾 Save", width=90, height=46,
        fg_color=colors["bg_light"], hover_color=colors["border"],
        text_color=colors["text_dim"],
        font=("Segoe UI", 13, "bold"), corner_radius=10,
        command=save_report,
    ).pack(side="left")

    # ── Main report textbox (live log display + analysis output) ──────────
    report_box = ctk.CTkTextbox(
        app.content, fg_color=colors["bg_dark"],
        text_color=colors["success"], font=("Consolas", 11),
        border_color=colors["border"], border_width=1,
        height=500, wrap="none",
    )
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0",
        "Boot Log Fault Analyzer — Mooxy AI Fault Detector\n"
        "=" * 65 + "\n\n"
        "Two modes available:\n\n"
        "  1. LIVE CAPTURE:\n"
        "     - Select COM port and baud rate above\n"
        "     - Click 'Connect' to establish serial connection\n"
        "     - Click 'Start Capture' to begin logging\n"
        "     - Power on the phone motherboard (connect battery + trigger boot)\n"
        "     - Boot log output appears here in real-time\n"
        "     - Click 'Stop & Analyze' when boot completes or stalls\n\n"
        "  2. IMPORT & ANALYZE:\n"
        "     - Click 'Import Log File' to load a saved boot log\n"
        "     - Supports .txt, .log, .ips, .panic, .crash files\n"
        "     - Analysis runs automatically after import\n\n"
        "Wiring:\n"
        "  Phone Motherboard          USB-TTL Adapter\n"
        "  ─────────────────          ──────────────\n"
        "  TX (Test Point) ────────── RX\n"
        "  GND ──────────────── ───── GND\n"
        "  (Do NOT connect VCC unless required)\n\n"
        "  Typical baud: 115200 (Qualcomm) or 921600 (MediaTek)\n\n"
        "Fault Detection Covers:\n"
        "  PMIC, CPU/SoC, Storage (UFS/eMMC), DDR/RAM, Display,\n"
        "  Modem/Baseband, WiFi, Audio, Camera, Charging, USB,\n"
        "  Clock/PLL, NFC, GPS, Fingerprint, Secure Boot\n\n"
        "  80+ known error patterns with component-level repair guidance.\n"
    )
    _setup_tags()

    # ── Status bar ─────────────────────────────────────────────────────────
    app.update_status("Boot Log Fault Analyzer — Connect device or import log file to begin")
