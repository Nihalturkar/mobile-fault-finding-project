import customtkinter as ctk
import threading


def render_edl_detect(app):
    """Qualcomm EDL (9008) mode detection page."""
    colors = app.colors

    ctk.CTkLabel(app.content, text="⚡ Qualcomm EDL Mode Detection",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Deep hardware analysis via Qualcomm Emergency Download mode — like JB Tool / REWA Tool",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 20))

    # What EDL can detect
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="🔍 EDL Mode Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "✅ UFS/eMMC — Manufacturer, capacity, health, boot LUN",
        "✅ DDR — Manufacturer (Samsung/Hynix/Micron), type (LPDDR5), size, training status",
        "✅ PMIC — Version, bus status, power on reason",
        "✅ PS_HOLD — Power status, fault codes",
        "✅ CDT — Configuration Data Table status",
        "✅ Secure Boot — Authentication status",
        "✅ Battery — Charging controller, voltage",
        "✅ Chipset ID — MSM ID, OEM ID, PK Hash",
        "✅ Partitions — Full partition table",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # How to enter EDL
    edl_instr = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    edl_instr.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(edl_instr, text="📋 How to Enter EDL Mode (Port 9008)",
                 font=("Segoe UI", 16, "bold"), text_color=colors["warning"]).pack(anchor="w", padx=20, pady=(15, 8))

    methods = [
        "Method 1: Short EDL test point on motherboard + connect USB to PC",
        "Method 2: adb reboot edl (if phone is ON with USB debugging)",
        "Method 3: Hold Volume Up + Down + connect USB (some phones)",
        "Method 4: Using UART: send special command to enter EDL",
        "",
        "Device Manager should show: 'Qualcomm HS-USB QDLoader 9008'",
        "Install Qualcomm USB drivers if device not recognized",
    ]
    for m in methods:
        ctk.CTkLabel(edl_instr, text=f"  {m}" if m else "", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(edl_instr, fg_color="transparent", height=12).pack()

    # Status
    status_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    status_card.pack(fill="x", padx=20, pady=(0, 15))
    s_header = ctk.CTkFrame(status_card, fg_color="transparent")
    s_header.pack(fill="x", padx=20, pady=(15, 5))
    ctk.CTkLabel(s_header, text="Detection Status", font=("Segoe UI", 16, "bold"),
                 text_color=colors["text"]).pack(side="left")
    status_label = ctk.CTkLabel(s_header, text="  ⏸ Waiting",
                                 font=("Segoe UI", 13, "bold"), text_color=colors["text_dim"])
    status_label.pack(side="left", padx=(10, 0))

    progress = ctk.CTkProgressBar(status_card, width=600, height=18,
                                   progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(5, 3), anchor="w")
    msg_label = ctk.CTkLabel(status_card, text="",
                              font=("Segoe UI", 13), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 15))

    # Results
    results_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    results_card.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(results_card, text="⚡ EDL Results", font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    result_fields = [
        ("edl_status", "🔌 EDL Connection"),
        ("usb_product", "🔗 USB Product String"),
        ("serial", "🔢 Chip Serial"),
        ("sahara_mode", "📡 Sahara Protocol"),
        ("cmd_mode", "🛠 Sahara Command Mode"),
        ("msm_id", "🔲 Chipset (MSM ID)"),
        ("oem", "🏷 OEM / Model ID"),
        ("pk_hash", "🔑 OEM PK Hash"),
        ("storage_type", "💿 Storage Type"),
        ("storage_mfg", "🏭 Storage Manufacturer"),
        ("storage_cap", "📊 Storage Capacity"),
        ("storage_health", "❤️ Storage Health (EOL)"),
        ("partitions", "📑 Partitions (GPT)"),
        ("secure_boot", "🔒 Secure Boot"),
    ]

    field_labels = {}
    for key, name in result_fields:
        row = ctk.CTkFrame(results_card, fg_color=colors["bg_light"], corner_radius=4, height=35)
        row.pack(fill="x", padx=15, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=180, anchor="w").pack(side="left", padx=10)
        val = ctk.CTkLabel(row, text="—", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=10)
        dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 12),
                            text_color=colors["text_dim"], width=25)
        dot.pack(side="right", padx=10)
        field_labels[key] = (val, dot)
    ctk.CTkFrame(results_card, fg_color="transparent", height=10).pack()

    # Log
    log_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    log_card.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(log_card, text="📜 EDL Detection Log", font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))
    log_text = ctk.CTkTextbox(log_card, height=200, fg_color=colors["bg_dark"],
                               text_color=colors["success"], font=("Consolas", 10),
                               border_color=colors["border"], border_width=1)
    log_text.pack(fill="x", padx=15, pady=(0, 15))

    running = {"value": False}
    loader = {"path": None}

    def pick_loader():
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select Firehose programmer",
            filetypes=[("Firehose programmer", "*.elf *.mbn *.bin"), ("All files", "*.*")])
        if path:
            loader["path"] = path
            loader_label.configure(text=path.split("/")[-1], text_color=colors["success"])

    def start_detection():
        if running["value"]:
            return
        running["value"] = True
        status_label.configure(text="  🔄 Scanning...", text_color=colors["info"])
        progress.set(0)
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        log_text.configure(state="disabled")

        def run():
            try:
                from app.hardware.edl_detector import detect_via_edl

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                result = detect_via_edl(callback=cb, loader_path=loader["path"])

                for line in result.log:
                    app.content.after(0, lambda l=line: _add_log(l))

                # Update fields
                def set_field(key, value, ok=True):
                    if key in field_labels:
                        v, d = field_labels[key]
                        app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
                        app.content.after(0, lambda: d.configure(
                            text_color=colors["success"] if ok else colors["warning"]))

                set_field("edl_status", f"Connected ({result.port})" if result.connected else "Not found",
                          result.connected)
                if result.usb_product:
                    set_field("usb_product", result.usb_product)
                if result.serial_number:
                    set_field("serial", result.serial_number)
                if result.sahara_version:
                    set_field("sahara_mode", f"v{result.sahara_version}, {result.sahara_mode}, "
                              f"pkt {result.sahara_max_packet_size}")
                if result.connected:
                    set_field("cmd_mode", "Supported" if result.command_mode_supported
                              else "Not supported by PBL — Firehose programmer needed",
                              result.command_mode_supported)
                if result.msm_id:
                    set_field("msm_id", f"{result.msm_id} {result.chipset_name}".strip())
                if result.oem_id or result.model_id:
                    set_field("oem", f"{result.oem_name or result.oem_id} / {result.model_id}")
                if result.pk_hash:
                    set_field("pk_hash", result.pk_hash[:32] + "…")
                if result.storage_type:
                    set_field("storage_type", result.storage_type)
                if result.storage_manufacturer:
                    set_field("storage_mfg", result.storage_manufacturer)
                if result.storage_capacity_human:
                    set_field("storage_cap", result.storage_capacity_human)
                if result.storage_health_eol:
                    set_field("storage_health", result.storage_health_eol,
                              result.storage_health_eol.strip() in ("", "0", "0x00", "1", "0x01"))
                if result.partitions:
                    set_field("partitions", f"{len(result.partitions)} found")
                if result.msm_id:
                    set_field("secure_boot", "Enabled" if result.secure_boot_enabled else "Disabled")

                app.content.after(0, lambda: progress.set(1.0))

                if result.connected:
                    app.content.after(0, lambda: status_label.configure(
                        text="  ✅ EDL Connected", text_color=colors["success"]))
                else:
                    app.content.after(0, lambda: status_label.configure(
                        text="  ❌ Not Found", text_color=colors["accent"]))
                    if result.errors:
                        app.content.after(0, lambda: msg_label.configure(
                            text=result.errors[0][:100], text_color=colors["accent"]))

                running["value"] = False

            except Exception as e:
                app.content.after(0, lambda: status_label.configure(
                    text="  ❌ Error", text_color=colors["accent"]))
                app.content.after(0, lambda: _add_log(f"Error: {str(e)}"))
                running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    def _add_log(text):
        log_text.configure(state="normal")
        log_text.insert("end", text + "\n")
        log_text.see("end")
        log_text.configure(state="disabled")

    loader_row = ctk.CTkFrame(app.content, fg_color="transparent")
    loader_row.pack(pady=(10, 0))
    ctk.CTkButton(loader_row, text="📂 Firehose programmer (.elf/.mbn)", width=260, height=36,
                  fg_color=colors["bg_light"], command=pick_loader).pack(side="left", padx=5)
    loader_label = ctk.CTkLabel(loader_row, text="none — PBL-level info only",
                                font=("Consolas", 11), text_color=colors["text_dim"])
    loader_label.pack(side="left", padx=5)

    ctk.CTkButton(app.content, text="⚡ Start EDL Detection", width=300, height=50,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 16, "bold"), corner_radius=10,
                  command=start_detection).pack(padx=20, pady=(0, 10))

    ctk.CTkLabel(app.content, text="Tip: Install edl.py for full data extraction: pip install edl",
                 font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(padx=20, pady=(0, 20))

    app.update_status("EDL Detection — Enter EDL mode (9008) and press Start")
