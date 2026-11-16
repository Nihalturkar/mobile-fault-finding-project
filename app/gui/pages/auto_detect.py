import customtkinter as ctk
import threading


def render_auto_detect(app):
    """Render the auto-detect page - FTDI 232 UART boot listener."""
    colors = app.colors
    devices = app.devices

    ctk.CTkLabel(
        app.content, text="🔌 Auto-Detect Device (FTDI 232)",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Phone UART → FTDI 232 → USB → PC — Boot phone during detection to capture data",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 20))

    # ── Instructions ──
    instructions = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    instructions.pack(fill="x", padx=20, pady=(0, 15))

    ctk.CTkLabel(instructions, text="📋 How To Detect",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    steps = [
        "1. FTDI TX → Phone UART RX  |  FTDI RX → Phone UART TX  |  GND → GND",
        "2. Click 'Start Detection' button",
        "3. IMMEDIATELY boot the phone (connect battery / press power button)",
        "4. Wait 15 seconds — tool will capture all boot data from UART",
        "5. Tool will analyze boot log and identify chipset, brand, board info",
    ]
    for line in steps:
        ctk.CTkLabel(instructions, text=line, font=("Segoe UI", 12),
                     text_color=colors["text_dim"], anchor="w").pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(instructions, fg_color="transparent", height=12).pack()

    # ── Port Settings ──
    control_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    control_frame.pack(fill="x", padx=20, pady=(0, 15))

    ctrl_inner = ctk.CTkFrame(control_frame, fg_color="transparent")
    ctrl_inner.pack(fill="x", padx=20, pady=15)

    ctk.CTkLabel(ctrl_inner, text="COM Port:", font=("Segoe UI", 13, "bold"),
                 text_color=colors["text"]).pack(side="left")
    port_var = ctk.StringVar(value="COM12")
    ctk.CTkEntry(ctrl_inner, textvariable=port_var, width=100, height=38,
                 fg_color=colors["bg_light"], border_color=colors["border"],
                 font=("Segoe UI", 13)).pack(side="left", padx=(10, 20))

    ctk.CTkLabel(ctrl_inner, text="Baud:", font=("Segoe UI", 13, "bold"),
                 text_color=colors["text"]).pack(side="left")
    baud_var = ctk.StringVar(value="115200")
    ctk.CTkOptionMenu(ctrl_inner, values=["9600", "57600", "115200", "921600"],
                       variable=baud_var, width=120, height=38,
                       fg_color=colors["bg_light"], button_color=colors["accent"]).pack(side="left", padx=(10, 20))

    ctk.CTkLabel(ctrl_inner, text="Listen:", font=("Segoe UI", 13, "bold"),
                 text_color=colors["text"]).pack(side="left")
    duration_var = ctk.StringVar(value="45")
    ctk.CTkOptionMenu(ctrl_inner, values=["30", "45", "60", "90"],
                       variable=duration_var, width=80, height=38,
                       fg_color=colors["bg_light"], button_color=colors["accent"]).pack(side="left", padx=(10, 0))
    ctk.CTkLabel(ctrl_inner, text="sec", font=("Segoe UI", 12),
                 text_color=colors["text_dim"]).pack(side="left", padx=(5, 0))

    # ── Status ──
    status_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    status_card.pack(fill="x", padx=20, pady=(0, 15))

    status_header = ctk.CTkFrame(status_card, fg_color="transparent")
    status_header.pack(fill="x", padx=20, pady=(15, 5))

    ctk.CTkLabel(status_header, text="Detection Status",
                 font=("Segoe UI", 16, "bold"), text_color=colors["text"]).pack(side="left")

    hw_status_label = ctk.CTkLabel(status_header, text="  ⏸ Waiting",
                                    font=("Segoe UI", 13, "bold"), text_color=colors["text_dim"])
    hw_status_label.pack(side="left", padx=(10, 0))

    progress_bar = ctk.CTkProgressBar(status_card, width=600, height=20,
                                       progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress_bar.set(0)
    progress_bar.pack(padx=20, pady=(5, 3), anchor="w")

    progress_label = ctk.CTkLabel(status_card, text="",
                                   font=("Segoe UI", 12), text_color=colors["text_dim"])
    progress_label.pack(anchor="w", padx=20)

    detection_msg = ctk.CTkLabel(status_card, text="Press 'Start Detection' then boot the phone",
                                  font=("Segoe UI", 14, "bold"), text_color=colors["text_dim"])
    detection_msg.pack(anchor="w", padx=20, pady=(5, 15))

    # ── Results ──
    results_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    results_card.pack(fill="x", padx=20, pady=(0, 15))

    ctk.CTkLabel(results_card, text="⚡ Detected Information",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    result_fields = [
        ("ftdi", "📟 FTDI Connection", "Serial adapter status"),
        ("data_size", "📊 Data Received", "Boot data captured"),
        ("chipset", "🔲 Chipset / SoC", "Processor family"),
        ("chipset_detail", "🔲 Exact Chip", "e.g. MT6877 Dimensity 900"),
        ("mtk_chip_code", "🔢 Chip Code", "Hardware ID from F0 register"),
        ("brand", "🏢 Brand", "Manufacturer"),
        ("cpu_cores", "💻 CPU Cores", "Number of processor cores"),
        ("ram_type", "💾 RAM Type", "LPDDR4X / LPDDR5 etc."),
        ("ram_freq", "💾 RAM Speed", "Maximum frequency"),
        ("boot_registers", "📋 Boot Registers", "BROM register dump"),
        ("boot_stage", "🚀 Boot Stage", "Boot progress"),
        ("boot_mode", "🔄 Boot Mode", "Normal / Recovery / Factory"),
        ("boot_reason", "⚡ Boot Reason", "Power key / USB / Watchdog"),
        ("abnormal_boot", "⚠️ Crash Check", "Was last boot abnormal?"),
        ("kernel_entry", "🖥️ Kernel", "Kernel boot status"),
        ("atf_version", "🔒 ATF/BL31", "ARM Trusted Firmware version"),
        ("trustzone_version", "🛡️ TrustZone", "MTEE/GZ version"),
        ("spm_firmware", "💤 SPM", "Suspend power management"),
        ("firmware_version", "💿 Firmware", "Version string"),
        ("protocol", "📡 Protocol", "Detection method"),
        ("confidence", "🎯 Confidence", "Detection score"),
    ]

    field_labels = {}

    for key, name, desc in result_fields:
        row = ctk.CTkFrame(results_card, fg_color=colors["bg_light"], corner_radius=6, height=45)
        row.pack(fill="x", padx=15, pady=2)
        row.pack_propagate(False)

        name_frame = ctk.CTkFrame(row, fg_color="transparent", width=200)
        name_frame.pack(side="left", padx=(10, 10))
        name_frame.pack_propagate(False)

        ctk.CTkLabel(name_frame, text=name, font=("Segoe UI", 12, "bold"),
                     text_color=colors["text"], anchor="w").pack(anchor="w", pady=(5, 0))
        ctk.CTkLabel(name_frame, text=desc, font=("Segoe UI", 9),
                     text_color=colors["text_dim"], anchor="w").pack(anchor="w")

        val_label = ctk.CTkLabel(row, text="—", font=("Consolas", 12),
                                  text_color=colors["text_dim"], anchor="w")
        val_label.pack(side="left", fill="x", expand=True, padx=10)

        status_dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 14),
                                   text_color=colors["text_dim"], width=30)
        status_dot.pack(side="right", padx=10)

        field_labels[key] = (val_label, status_dot)

    ctk.CTkFrame(results_card, fg_color="transparent", height=10).pack()

    # ── Hardware Health Status ──
    hw_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    hw_card.pack(fill="x", padx=20, pady=(0, 15))

    ctk.CTkLabel(hw_card, text="🩺 Hardware Health Diagnosis",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))
    ctk.CTkLabel(hw_card, text="Based on boot log analysis — checks which subsystems initialized or failed",
                 font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 10))

    hw_items = [
        ("ram", "💾 RAM / Memory"),
        ("storage", "💿 Storage (eMMC/UFS)"),
        ("display", "📺 Display / LCD"),
        ("touchscreen", "👆 Touchscreen"),
        ("charging", "🔋 Charging / PMIC"),
        ("camera", "📷 Camera"),
        ("wifi", "📶 WiFi"),
        ("bluetooth", "🔵 Bluetooth"),
        ("audio", "🔊 Audio"),
        ("network", "📡 Network / Modem"),
        ("gps", "📍 GPS"),
        ("fingerprint", "👆 Fingerprint"),
        ("usb", "🔌 USB"),
        ("nfc", "💳 NFC"),
        ("sensors", "🧭 Sensors (Accel/Gyro)"),
    ]

    hw_labels = {}

    # Grid layout - 3 columns
    hw_grid = ctk.CTkFrame(hw_card, fg_color="transparent")
    hw_grid.pack(fill="x", padx=15, pady=(0, 15))

    for i, (key, name) in enumerate(hw_items):
        col = i % 3
        if col == 0:
            row_frame = ctk.CTkFrame(hw_grid, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)

        item = ctk.CTkFrame(row_frame, fg_color=colors["bg_light"], corner_radius=8, height=40)
        item.pack(side="left", fill="x", expand=True, padx=3)
        item.pack_propagate(False)

        status_label = ctk.CTkLabel(item, text="⚪", font=("Segoe UI", 14), width=25)
        status_label.pack(side="left", padx=(8, 3))

        name_label = ctk.CTkLabel(item, text=name, font=("Segoe UI", 11, "bold"),
                                   text_color=colors["text_dim"], anchor="w")
        name_label.pack(side="left", padx=(0, 5))

        val_label = ctk.CTkLabel(item, text="—", font=("Segoe UI", 10),
                                  text_color=colors["text_dim"], anchor="e")
        val_label.pack(side="right", padx=8)

        hw_labels[key] = (status_label, name_label, val_label)

    def update_hw_status(hw_status_dict):
        """Update hardware health display from detection result."""
        for key, (dot, name_lbl, val_lbl) in hw_labels.items():
            if key in hw_status_dict:
                status = hw_status_dict[key]["status"]
                if status == "ok":
                    dot.configure(text="✅")
                    val_lbl.configure(text="Working", text_color=colors["success"])
                    name_lbl.configure(text_color=colors["text"])
                elif status == "fail":
                    dot.configure(text="❌")
                    val_lbl.configure(text="FAULT", text_color=colors["accent"])
                    name_lbl.configure(text_color=colors["accent"])
                else:
                    dot.configure(text="⚪")
                    val_lbl.configure(text="Not in log", text_color=colors["text_dim"])
                    name_lbl.configure(text_color=colors["text_dim"])

    # ── Register Analysis Section ──
    reg_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    reg_card.pack(fill="x", padx=20, pady=(0, 15))

    ctk.CTkLabel(reg_card, text="📋 Register Analysis & Fault Detection",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))
    ctk.CTkLabel(reg_card, text="Compares boot register values against known good values to find hardware faults",
                 font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 10))

    # Register table header
    reg_header = ctk.CTkFrame(reg_card, fg_color=colors["accent"], corner_radius=0, height=35)
    reg_header.pack(fill="x", padx=15)
    reg_header.pack_propagate(False)

    for text_h, width_h in [("Status", 60), ("Register", 80), ("Name", 160), ("Value", 150), ("Description", 250)]:
        ctk.CTkLabel(reg_header, text=text_h, font=("Segoe UI", 11, "bold"),
                     text_color="#fff", width=width_h, anchor="w").pack(side="left", padx=5)

    reg_rows_frame = ctk.CTkFrame(reg_card, fg_color="transparent")
    reg_rows_frame.pack(fill="x", padx=15, pady=(0, 10))

    # Fault alert frame
    fault_frame = ctk.CTkFrame(reg_card, fg_color="transparent")
    fault_frame.pack(fill="x", padx=15, pady=(0, 15))

    def update_registers(result):
        """Update register table and fault alerts from detection result."""
        # Clear old rows
        for w in reg_rows_frame.winfo_children():
            w.destroy()
        for w in fault_frame.winfo_children():
            w.destroy()

        # Parse register analysis from uart_log
        reg_lines = [l for l in result.uart_log if l.strip().startswith(("✅", "❌")) and "(" in l and ":" in l]

        if not reg_lines:
            ctk.CTkLabel(reg_rows_frame, text="No register data — boot phone and detect first",
                         font=("Segoe UI", 12), text_color=colors["text_dim"]).pack(pady=10)
            return

        for i, line in enumerate(reg_lines):
            is_ok = line.strip().startswith("✅")
            row_bg = colors["bg_light"] if i % 2 == 0 else "transparent"

            if not is_ok:
                row_bg = "#3d1111"  # Red tint for faults

            row = ctk.CTkFrame(reg_rows_frame, fg_color=row_bg, corner_radius=0, height=32)
            row.pack(fill="x")
            row.pack_propagate(False)

            # Parse: ✅ F0 (Chip ID): 102B 0000 — SoC hardware identification code
            status_icon = "✅" if is_ok else "❌"
            # Extract parts
            parts = line.strip()[2:].strip()  # Remove icon
            reg_name = parts.split("(")[0].strip() if "(" in parts else parts.split(":")[0].strip()
            friendly_name = parts.split("(")[1].split(")")[0] if "(" in parts and ")" in parts else ""
            value_part = parts.split("): ")[1].split(" — ")[0] if "): " in parts else ""
            desc_part = parts.split(" — ")[1] if " — " in parts else ""

            ctk.CTkLabel(row, text=status_icon, font=("Segoe UI", 14), width=60).pack(side="left", padx=5)
            ctk.CTkLabel(row, text=reg_name, font=("Consolas", 12, "bold"),
                         text_color=colors["accent"] if not is_ok else colors["info"],
                         width=80, anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(row, text=friendly_name, font=("Segoe UI", 11),
                         text_color=colors["text"], width=160, anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(row, text=value_part, font=("Consolas", 11, "bold"),
                         text_color=colors["accent"] if not is_ok else colors["success"],
                         width=150, anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(row, text=desc_part, font=("Segoe UI", 10),
                         text_color=colors["text_dim"], width=250, anchor="w").pack(side="left", padx=5)

        # Show faults
        fault_lines = [l for l in result.uart_log if "CRITICAL" in l or "WARNING" in l]
        fault_detail = [l for l in result.uart_log if l.strip().startswith("→")]

        if fault_lines:
            alert = ctk.CTkFrame(fault_frame, fg_color="#4a1010", corner_radius=10)
            alert.pack(fill="x", pady=5)

            ctk.CTkLabel(alert, text="🚨 FAULTS DETECTED",
                         font=("Segoe UI", 16, "bold"), text_color="#ff4444").pack(anchor="w", padx=15, pady=(10, 5))

            for fl in fault_lines:
                ctk.CTkLabel(alert, text=fl.strip(), font=("Consolas", 12),
                             text_color="#ff6666", anchor="w").pack(anchor="w", padx=15, pady=1)

            for fd in fault_detail:
                ctk.CTkLabel(alert, text=fd.strip(), font=("Segoe UI", 11),
                             text_color="#ffaaaa", anchor="w", wraplength=700).pack(anchor="w", padx=15, pady=1)

            ctk.CTkFrame(alert, fg_color="transparent", height=10).pack()
        else:
            no_fault = [l for l in result.uart_log if "No register faults" in l]
            if no_fault:
                ok_frame = ctk.CTkFrame(fault_frame, fg_color="#0a3d0a", corner_radius=10)
                ok_frame.pack(fill="x", pady=5)
                ctk.CTkLabel(ok_frame, text="✅ All registers normal — no hardware faults detected",
                             font=("Segoe UI", 14, "bold"), text_color=colors["success"]).pack(padx=15, pady=12)

    # ── Raw UART Log ──
    log_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    log_card.pack(fill="x", padx=20, pady=(0, 15))

    ctk.CTkLabel(log_card, text="📜 UART Boot Log (Raw Data)",
                 font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    log_text = ctk.CTkTextbox(log_card, height=200, fg_color=colors["bg_dark"],
                               text_color=colors["success"], font=("Consolas", 10),
                               border_color=colors["border"], border_width=1)
    log_text.pack(fill="x", padx=15, pady=(0, 15))
    log_text.insert("1.0", "Waiting...\n")
    log_text.configure(state="disabled")

    # ── Action buttons area ──
    action_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    action_frame.pack(fill="x", padx=20, pady=(0, 15))

    # ── Helpers ──
    def update_field(key, value, status="success"):
        if key in field_labels:
            val_label, dot = field_labels[key]
            val_label.configure(text=str(value), text_color=colors["text"])
            color_map = {"success": colors["success"], "warning": colors["warning"],
                         "error": colors["accent"], "info": colors["info"]}
            dot.configure(text_color=color_map.get(status, colors["text_dim"]))

    def reset_fields():
        for key in field_labels:
            val_label, dot = field_labels[key]
            val_label.configure(text="—", text_color=colors["text_dim"])
            dot.configure(text_color=colors["text_dim"])

    def add_log(text):
        log_text.configure(state="normal")
        log_text.insert("end", text + "\n")
        log_text.see("end")
        log_text.configure(state="disabled")

    def clear_log():
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")

    detect_running = {"value": False}

    def _start_detection():
        if detect_running["value"]:
            return
        detect_running["value"] = True

        reset_fields()
        clear_log()

        for w in action_frame.winfo_children():
            w.destroy()

        port = port_var.get().strip()
        baud = int(baud_var.get().strip())
        duration = int(duration_var.get().strip())

        hw_status_label.configure(text="  🔴 LISTENING — BOOT PHONE NOW!", text_color=colors["accent"])
        detection_msg.configure(
            text=f"⚡ BOOT THE PHONE NOW! Listening for {duration} seconds...",
            text_color=colors["accent"])
        progress_bar.set(0)

        def run():
            try:
                from app.hardware.device_detector import DeviceAutoDetector

                app.content.after(0, lambda: add_log(f"[*] Opening FTDI on {port} @ {baud}..."))

                def progress_callback(elapsed, bytes_received):
                    pct = elapsed / duration
                    app.content.after(0, lambda p=pct: progress_bar.set(min(p, 1.0)))
                    remaining = int(duration - elapsed)
                    app.content.after(0, lambda r=remaining, b=bytes_received:
                        progress_label.configure(text=f"{r}s remaining  |  {b} bytes received"))

                    if bytes_received > 0 and elapsed < 3:
                        app.content.after(0, lambda: hw_status_label.configure(
                            text="  🟢 DATA COMING IN!", text_color=colors["success"]))
                        app.content.after(0, lambda: detection_msg.configure(
                            text="Receiving boot data from phone...", text_color=colors["success"]))

                detector = DeviceAutoDetector(port=port, baud=baud)
                result = detector.detect(listen_duration=duration, callback=progress_callback)

                # Update log
                for line in result.uart_log:
                    app.content.after(0, lambda l=line: add_log(l))

                # Show raw boot data in log
                if result.raw_data:
                    app.content.after(0, lambda: add_log("\n--- RAW BOOT DATA ---"))
                    # Show readable parts
                    readable = result.raw_responses.get("readable_boot_log", "")
                    if readable:
                        for line in readable.split("\n")[:30]:
                            app.content.after(0, lambda l=line: add_log(l))

                app.content.after(0, lambda: progress_bar.set(1.0))
                app.content.after(0, lambda: progress_label.configure(text="Detection complete"))

                # Update result fields
                app.content.after(0, lambda: update_field("ftdi",
                    result.raw_responses.get("ftdi_connection", "Failed"),
                    "success" if "Connected" in result.raw_responses.get("ftdi_connection", "") else "error"))

                app.content.after(0, lambda: update_field("data_size",
                    result.raw_responses.get("data_received", "0 bytes"),
                    "success" if result.detected else "error"))

                if result.detected:
                    # Chipset
                    app.content.after(0, lambda: update_field("chipset", result.chipset,
                        "success" if result.chipset != "Unknown" else "warning"))
                    app.content.after(0, lambda: update_field("chipset_detail",
                        result.raw_responses.get("chipset_detail", "—"),
                        "success" if "chipset_detail" in result.raw_responses else "warning"))

                    # Auto-fill all result fields from raw_responses
                    auto_fields = [
                        "mtk_chip_code", "cpu_cores", "ram_type", "ram_freq",
                        "boot_registers", "boot_stage", "boot_mode", "boot_reason",
                        "abnormal_boot", "kernel_entry", "atf_version",
                        "trustzone_version", "spm_firmware", "firmware_version",
                    ]
                    for fkey in auto_fields:
                        val = result.raw_responses.get(fkey, "")
                        if val:
                            app.content.after(0, lambda k=fkey, v=val: update_field(k, v, "success"))
                        else:
                            app.content.after(0, lambda k=fkey: update_field(k, "Not in log", "warning"))

                    # Brand
                    app.content.after(0, lambda: update_field("brand", result.brand,
                        "success" if result.brand != "Unknown" else "warning"))

                    # Protocol
                    app.content.after(0, lambda: update_field("protocol", result.protocol, "success"))

                    # Confidence
                    conf_status = "success" if result.confidence >= 50 else "warning"
                    app.content.after(0, lambda: update_field("confidence",
                        f"{result.confidence}%", conf_status))

                    # Hardware health status
                    if result.hw_status:
                        app.content.after(0, lambda: update_hw_status(result.hw_status))

                    # Register analysis & fault detection
                    app.content.after(0, lambda: update_registers(result))

                    # Final status
                    app.content.after(0, lambda: hw_status_label.configure(
                        text=f"  ✅ {result.chipset} detected ({result.confidence}%)",
                        text_color=colors["success"]))
                    app.content.after(0, lambda: detection_msg.configure(
                        text=f"Detected: {result.brand} / {result.chipset} / {result.device_name}",
                        text_color=colors["success"]))

                    # Fault Analysis
                    app.content.after(0, lambda: _show_fault_report(result))

                    # Action buttons
                    app.content.after(0, lambda: _show_actions(result))

                elif result.error:
                    app.content.after(0, lambda: hw_status_label.configure(
                        text="  ❌ No Data", text_color=colors["accent"]))
                    app.content.after(0, lambda: detection_msg.configure(
                        text=result.error, text_color=colors["accent"]))

                detect_running["value"] = False

            except Exception as e:
                app.content.after(0, lambda: hw_status_label.configure(
                    text="  ❌ Error", text_color=colors["accent"]))
                app.content.after(0, lambda: detection_msg.configure(
                    text=str(e), text_color=colors["accent"]))
                detect_running["value"] = False

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def _show_fault_report(result):
        """Show fault analysis with problems, causes, and repair steps."""
        from app.hardware.fault_analyzer import analyze_uart_result

        report = analyze_uart_result(result)

        # Create fault report card
        fault_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
        fault_card.pack(fill="x", padx=20, pady=(0, 15))

        # Summary header
        if report.total_faults == 0:
            ctk.CTkLabel(fault_card, text="✅ FAULT ANALYSIS — No Problems Found",
                         font=("Segoe UI", 18, "bold"), text_color=colors["success"]).pack(anchor="w", padx=20, pady=(15, 5))
            ctk.CTkLabel(fault_card, text=report.summary,
                         font=("Segoe UI", 13), text_color=colors["success"]).pack(anchor="w", padx=20, pady=(0, 10))
        else:
            ctk.CTkLabel(fault_card, text=f"🚨 FAULT ANALYSIS — {report.total_faults} Problem(s) Found",
                         font=("Segoe UI", 18, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))
            ctk.CTkLabel(fault_card, text=report.summary,
                         font=("Segoe UI", 13), text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(0, 10))

        # Each fault as expandable card
        for i, fault in enumerate(report.faults):
            sev_color = colors["accent"] if fault.severity == "critical" else colors["warning"]
            sev_icon = "🔴" if fault.severity == "critical" else "🟡"

            f_card = ctk.CTkFrame(fault_card, fg_color="#2a1020" if fault.severity == "critical" else "#2a2010", corner_radius=10)
            f_card.pack(fill="x", padx=15, pady=5)

            # Fault header
            ctk.CTkLabel(f_card, text=f"{sev_icon} [{fault.component}] {fault.problem}",
                         font=("Segoe UI", 14, "bold"), text_color=sev_color,
                         wraplength=700, anchor="w").pack(anchor="w", padx=15, pady=(10, 3))

            ctk.CTkLabel(f_card, text=f"Evidence: {fault.evidence}",
                         font=("Segoe UI", 11), text_color=colors["text_dim"],
                         wraplength=700, anchor="w").pack(anchor="w", padx=15, pady=(0, 5))

            # Possible causes
            if fault.possible_causes:
                ctk.CTkLabel(f_card, text="🔍 Possible Causes:",
                             font=("Segoe UI", 12, "bold"), text_color=colors["info"]).pack(anchor="w", padx=15, pady=(5, 2))
                for cause in fault.possible_causes:
                    ctk.CTkLabel(f_card, text=f"  • {cause}",
                                 font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(anchor="w", padx=15)

            # What to check
            if fault.what_to_check:
                ctk.CTkLabel(f_card, text="🔧 What to Check:",
                             font=("Segoe UI", 12, "bold"), text_color=colors["warning"]).pack(anchor="w", padx=15, pady=(8, 2))
                for check in fault.what_to_check:
                    ctk.CTkLabel(f_card, text=f"  • {check}",
                                 font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(anchor="w", padx=15)

            # Repair steps
            if fault.repair_steps:
                ctk.CTkLabel(f_card, text="🛠️ Repair Steps:",
                             font=("Segoe UI", 12, "bold"), text_color=colors["success"]).pack(anchor="w", padx=15, pady=(8, 2))
                for j, step in enumerate(fault.repair_steps, 1):
                    ctk.CTkLabel(f_card, text=f"  {j}. {step}",
                                 font=("Segoe UI", 11), text_color=colors["text"]).pack(anchor="w", padx=15)

            # Parts needed
            if fault.parts_needed:
                ctk.CTkLabel(f_card, text=f"📦 Parts: {', '.join(fault.parts_needed)}",
                             font=("Segoe UI", 11, "bold"), text_color=colors["info"]).pack(anchor="w", padx=15, pady=(5, 2))

            ctk.CTkLabel(f_card, text=f"Difficulty: {fault.estimated_difficulty.upper()}",
                         font=("Segoe UI", 10, "bold"), text_color=sev_color).pack(anchor="w", padx=15, pady=(3, 10))

        # Healthy components
        if report.healthy_components:
            ctk.CTkLabel(fault_card, text="✅ Working Components:",
                         font=("Segoe UI", 13, "bold"), text_color=colors["success"]).pack(anchor="w", padx=20, pady=(10, 5))
            for comp in report.healthy_components:
                ctk.CTkLabel(fault_card, text=f"  ✓ {comp}",
                             font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(anchor="w", padx=20)

        ctk.CTkFrame(fault_card, fg_color="transparent", height=15).pack()

    def _show_actions(result):
        for w in action_frame.winfo_children():
            w.destroy()

        card = ctk.CTkFrame(action_frame, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x", pady=5)

        ctk.CTkLabel(card, text=f"✅ {result.brand} — {result.chipset}",
                     font=("Segoe UI", 18, "bold"), text_color=colors["success"]).pack(anchor="w", padx=20, pady=(15, 5))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(btn_row, text="➕ Save as New Device", width=200, height=42,
                      fg_color=colors["accent"], hover_color=colors["accent_hover"],
                      font=("Segoe UI", 14, "bold"), corner_radius=10,
                      command=app.show_add_device).pack(side="left", padx=(0, 10))

        ctk.CTkButton(btn_row, text="🔄 Detect Again", width=150, height=42,
                      fg_color=colors["bg_light"], hover_color=colors["accent"],
                      font=("Segoe UI", 13), corner_radius=10,
                      command=_start_detection).pack(side="left")

    # ── Buttons ──
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    ctk.CTkButton(btn_frame, text="🔌 Start Detection — Then Boot Phone!", width=350, height=50,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 16, "bold"), corner_radius=10,
                  command=_start_detection).pack(side="left", padx=(0, 15))

    # ── Manual Selection ──
    ctk.CTkFrame(app.content, height=2, fg_color=colors["border"]).pack(fill="x", padx=20, pady=15)

    manual = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    manual.pack(fill="x", padx=20, pady=(0, 20))

    ctk.CTkLabel(manual, text="📱 Manual Selection",
                 font=("Segoe UI", 16, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

    manual_inner = ctk.CTkFrame(manual, fg_color="transparent")
    manual_inner.pack(fill="x", padx=20, pady=(0, 15))

    device_names = sorted([f"{d.get('brand', '')} {d.get('model', '')}" for d in devices])
    if not device_names:
        device_names = ["No devices — Add Device first"]

    manual_var = ctk.StringVar(value=device_names[0])
    ctk.CTkOptionMenu(manual_inner, values=device_names, variable=manual_var,
                       width=400, height=38, fg_color=colors["bg_light"],
                       button_color=colors["accent"]).pack(side="left", padx=(0, 10))

    def _manual():
        name = manual_var.get()
        for d in devices:
            if f"{d.get('brand', '')} {d.get('model', '')}" == name:
                app.show_device_detail(d)
                return

    ctk.CTkButton(manual_inner, text="Select →", width=100, height=38,
                  fg_color=colors["success"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 13, "bold"), command=_manual).pack(side="left")

    app.update_status("Auto-Detect — Click Start, then boot the phone within 15 seconds")
