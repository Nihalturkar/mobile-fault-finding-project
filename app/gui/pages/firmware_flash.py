import customtkinter as ctk
import threading
from tkinter import filedialog

from app.hardware.firmware_flasher import (
    detect_flash_mode,
    flash_qualcomm_edl,
    flash_mediatek,
    flash_samsung,
    flash_fastboot,
    read_partition_table,
)


def render_firmware_flash(app):
    """Firmware flashing page — multi-protocol flash with live progress and report."""
    colors = app.colors

    # ── Page title ──
    ctk.CTkLabel(
        app.content, text="Firmware Flashing",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Flash firmware via Qualcomm EDL, MediaTek BROM, Samsung Odin, or Fastboot",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Warning card ──
    warn_card = ctk.CTkFrame(app.content, fg_color="#3a1010", corner_radius=12,
                              border_color="#e94560", border_width=2)
    warn_card.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(
        warn_card,
        text="WARNING: Incorrect flashing can brick the device. "
             "Ensure correct firmware files are selected.",
        font=("Segoe UI", 13, "bold"), text_color="#ff4444",
        wraplength=700, anchor="w",
    ).pack(padx=15, pady=12, anchor="w")

    # ── Flash Mode Detection card ──
    detect_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    detect_card.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(
        detect_card, text="Flash Mode Detection",
        font=("Segoe UI", 16, "bold"), text_color=colors["info"],
    ).pack(anchor="w", padx=20, pady=(15, 8))

    detect_inner = ctk.CTkFrame(detect_card, fg_color="transparent")
    detect_inner.pack(fill="x", padx=20, pady=(0, 5))

    detect_fields = {}
    for key, label in [("mode", "Mode"), ("device_info", "Device Info"),
                       ("chipset", "Chipset"), ("serial", "Serial")]:
        row = ctk.CTkFrame(detect_inner, fg_color=colors["bg_light"],
                           corner_radius=4, height=32)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=10)
        val = ctk.CTkLabel(row, text="--", font=("Consolas", 11),
                           text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=10)
        detect_fields[key] = val

    detect_status = ctk.CTkLabel(detect_card, text="",
                                  font=("Segoe UI", 12), text_color=colors["text_dim"])
    detect_status.pack(anchor="w", padx=20, pady=(2, 5))

    running = {"value": False}

    def _do_detect_mode():
        if running["value"]:
            return
        running["value"] = True
        detect_status.configure(text="Scanning...", text_color=colors["info"])
        _append_report("[INFO] Detecting flash mode...")

        def _run():
            try:
                def cb(pct, msg):
                    app.content.after(0, lambda: detect_status.configure(text=msg))

                result = detect_flash_mode(callback=cb)

                def _update():
                    if result.connected:
                        detect_fields["mode"].configure(
                            text=result.mode.upper(), text_color=colors["success"])
                        info_str = ", ".join(f"{k}: {v}" for k, v in result.device_info.items())
                        detect_fields["device_info"].configure(
                            text=info_str or "--", text_color=colors["text"])
                        detect_fields["chipset"].configure(
                            text=result.chipset or "--", text_color=colors["text"])
                        detect_fields["serial"].configure(
                            text=result.serial or "--", text_color=colors["text"])
                        detect_status.configure(
                            text=f"Device detected in {result.mode.upper()} mode",
                            text_color=colors["success"])
                        _append_report(f"[OK] Device detected: {result.mode.upper()} | "
                                       f"Chipset: {result.chipset} | Serial: {result.serial}")
                    else:
                        for v in detect_fields.values():
                            v.configure(text="--", text_color=colors["text_dim"])
                        detect_status.configure(
                            text=result.error or "No device found",
                            text_color=colors["accent"])
                        _append_report(f"[!!] {result.error or 'No device found'}")
                    running["value"] = False

                app.content.after(0, _update)
            except Exception as e:
                app.content.after(0, lambda: detect_status.configure(
                    text=f"Error: {e}", text_color=colors["accent"]))
                app.content.after(0, lambda: _append_report(f"[xx] Detection error: {e}"))
                running["value"] = False

        threading.Thread(target=_run, daemon=True).start()

    ctk.CTkButton(
        detect_card, text="Detect Flash Mode", width=200, height=38,
        fg_color=colors["accent"], hover_color=colors["accent_hover"],
        font=("Segoe UI", 13, "bold"), corner_radius=8,
        command=_do_detect_mode,
    ).pack(padx=20, pady=(5, 15))

    # ── Tab-like buttons ──
    tab_bar = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    tab_bar.pack(fill="x", padx=20, pady=(0, 0))
    tab_btn_row = ctk.CTkFrame(tab_bar, fg_color="transparent")
    tab_btn_row.pack(fill="x", padx=15, pady=10)

    tab_frames = {}
    active_tab = {"name": None}
    tab_buttons = {}

    tab_names = ["Qualcomm EDL", "MediaTek", "Samsung", "Fastboot"]

    # Container for tab content
    tab_container = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    tab_container.pack(fill="x", padx=20, pady=(0, 15))

    def _switch_tab(name):
        for tname, tf in tab_frames.items():
            tf.pack_forget()
        if name in tab_frames:
            tab_frames[name].pack(fill="x", padx=15, pady=10)
        for tname, btn in tab_buttons.items():
            if tname == name:
                btn.configure(fg_color=colors["accent"], text_color="#ffffff")
            else:
                btn.configure(fg_color=colors["bg_light"], text_color=colors["text"])
        active_tab["name"] = name

    for tname in tab_names:
        btn = ctk.CTkButton(
            tab_btn_row, text=tname, width=140, height=36,
            fg_color=colors["bg_light"], hover_color=colors["accent_hover"],
            text_color=colors["text"], font=("Segoe UI", 12, "bold"),
            corner_radius=8, command=lambda n=tname: _switch_tab(n),
        )
        btn.pack(side="left", padx=3)
        tab_buttons[tname] = btn

    # ======================================================================
    # Qualcomm EDL tab
    # ======================================================================
    edl_frame = ctk.CTkFrame(tab_container, fg_color="transparent")
    tab_frames["Qualcomm EDL"] = edl_frame

    ctk.CTkLabel(
        edl_frame, text="Qualcomm EDL Firehose Flash",
        font=("Segoe UI", 15, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", pady=(5, 10))

    # Firehose programmer selector
    fh_row = ctk.CTkFrame(edl_frame, fg_color="transparent")
    fh_row.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(fh_row, text="Firehose Programmer:",
                 font=("Segoe UI", 12, "bold"), text_color=colors["text"],
                 width=160, anchor="w").pack(side="left")
    fh_path_var = ctk.StringVar(value="")
    fh_entry = ctk.CTkEntry(fh_row, textvariable=fh_path_var, width=350, height=32,
                             fg_color=colors["bg_light"], border_color=colors["border"],
                             font=("Consolas", 11))
    fh_entry.pack(side="left", padx=(5, 5))

    def _browse_firehose():
        path = filedialog.askopenfilename(
            title="Select Firehose Programmer",
            filetypes=[("Firehose MBN/ELF", "*.mbn *.elf"), ("All Files", "*.*")])
        if path:
            fh_path_var.set(path)

    ctk.CTkButton(fh_row, text="Browse", width=80, height=32,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 11), command=_browse_firehose).pack(side="left")

    # Partition list
    ctk.CTkLabel(edl_frame, text="Partitions to Flash:",
                 font=("Segoe UI", 12, "bold"), text_color=colors["text"],
                 ).pack(anchor="w", pady=(5, 3))

    edl_parts_frame = ctk.CTkScrollableFrame(edl_frame, fg_color=colors["bg_light"],
                                              corner_radius=8, height=140)
    edl_parts_frame.pack(fill="x", pady=(0, 5))

    edl_partition_rows = []

    def _add_edl_partition(part_name="", file_path=""):
        row_frame = ctk.CTkFrame(edl_parts_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)

        name_var = ctk.StringVar(value=part_name)
        ctk.CTkEntry(row_frame, textvariable=name_var, width=120, height=30,
                     placeholder_text="partition",
                     fg_color=colors["bg_card"], border_color=colors["border"],
                     font=("Consolas", 11)).pack(side="left", padx=(0, 5))

        path_var = ctk.StringVar(value=file_path)
        ctk.CTkEntry(row_frame, textvariable=path_var, width=320, height=30,
                     placeholder_text="image file path",
                     fg_color=colors["bg_card"], border_color=colors["border"],
                     font=("Consolas", 11)).pack(side="left", padx=(0, 5))

        def _browse_part():
            p = filedialog.askopenfilename(
                title=f"Select Image for {name_var.get() or 'partition'}",
                filetypes=[("Image Files", "*.img *.bin *.mbn"), ("All Files", "*.*")])
            if p:
                path_var.set(p)

        ctk.CTkButton(row_frame, text="Browse", width=65, height=30,
                      fg_color=colors["info"], hover_color=colors["accent"],
                      font=("Segoe UI", 10), command=_browse_part).pack(side="left", padx=(0, 3))

        def _remove_row():
            row_frame.destroy()
            edl_partition_rows[:] = [r for r in edl_partition_rows if r["frame"].winfo_exists()]

        ctk.CTkButton(row_frame, text="X", width=30, height=30,
                      fg_color="#e94560", hover_color="#ff4444",
                      font=("Segoe UI", 10, "bold"), command=_remove_row).pack(side="left")

        edl_partition_rows.append({"frame": row_frame, "name": name_var, "path": path_var})

    # Add default partitions
    for pname in ["boot", "system"]:
        _add_edl_partition(part_name=pname)

    edl_btn_row = ctk.CTkFrame(edl_frame, fg_color="transparent")
    edl_btn_row.pack(fill="x", pady=(5, 5))

    ctk.CTkButton(edl_btn_row, text="+ Add Partition", width=130, height=32,
                  fg_color=colors["bg_medium"], hover_color=colors["bg_light"],
                  text_color=colors["text"], font=("Segoe UI", 11),
                  command=lambda: _add_edl_partition()).pack(side="left", padx=(0, 10))

    def _flash_edl():
        if running["value"]:
            return
        firehose = fh_path_var.get().strip()
        if not firehose:
            _append_report("[!!] No firehose programmer selected")
            return
        parts = {}
        for r in edl_partition_rows:
            if not r["frame"].winfo_exists():
                continue
            n = r["name"].get().strip()
            p = r["path"].get().strip()
            if n and p:
                parts[n] = p
        if not parts:
            _append_report("[!!] No partitions configured for flashing")
            return
        _run_flash_operation("Qualcomm EDL", lambda cb: flash_qualcomm_edl(firehose, parts, callback=cb))

    ctk.CTkButton(edl_btn_row, text="Flash via EDL", width=160, height=38,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 13, "bold"), corner_radius=8,
                  command=_flash_edl).pack(side="left")

    # ======================================================================
    # MediaTek tab
    # ======================================================================
    mtk_frame = ctk.CTkFrame(tab_container, fg_color="transparent")
    tab_frames["MediaTek"] = mtk_frame

    ctk.CTkLabel(
        mtk_frame, text="MediaTek SP Flash (BROM/Preloader)",
        font=("Segoe UI", 15, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", pady=(5, 10))

    scatter_row = ctk.CTkFrame(mtk_frame, fg_color="transparent")
    scatter_row.pack(fill="x", pady=(0, 8))
    ctk.CTkLabel(scatter_row, text="Scatter File:",
                 font=("Segoe UI", 12, "bold"), text_color=colors["text"],
                 width=120, anchor="w").pack(side="left")

    scatter_var = ctk.StringVar(value="")
    ctk.CTkEntry(scatter_row, textvariable=scatter_var, width=380, height=32,
                 fg_color=colors["bg_light"], border_color=colors["border"],
                 font=("Consolas", 11)).pack(side="left", padx=(5, 5))

    def _browse_scatter():
        path = filedialog.askopenfilename(
            title="Select MediaTek Scatter File",
            filetypes=[("Scatter TXT", "*.txt"), ("All Files", "*.*")])
        if path:
            scatter_var.set(path)

    ctk.CTkButton(scatter_row, text="Browse", width=80, height=32,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 11), command=_browse_scatter).pack(side="left")

    ctk.CTkLabel(
        mtk_frame,
        text="Place firmware images in the same directory as the scatter file.",
        font=("Segoe UI", 11), text_color=colors["text_dim"],
    ).pack(anchor="w", pady=(0, 5))

    def _flash_mtk():
        if running["value"]:
            return
        scatter = scatter_var.get().strip()
        if not scatter:
            _append_report("[!!] No scatter file selected")
            return
        _run_flash_operation("MediaTek", lambda cb: flash_mediatek(scatter, callback=cb))

    ctk.CTkButton(mtk_frame, text="Flash via BROM", width=160, height=38,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 13, "bold"), corner_radius=8,
                  command=_flash_mtk).pack(anchor="w", pady=(5, 5))

    # ======================================================================
    # Samsung tab
    # ======================================================================
    sam_frame = ctk.CTkFrame(tab_container, fg_color="transparent")
    tab_frames["Samsung"] = sam_frame

    ctk.CTkLabel(
        sam_frame, text="Samsung Odin / Heimdall Flash",
        font=("Segoe UI", 15, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", pady=(5, 10))

    samsung_slots = {"BL": "Bootloader", "AP": "Android/System", "CP": "Modem/Baseband", "CSC": "CSC Region"}
    samsung_vars = {}

    for slot_key, slot_label in samsung_slots.items():
        s_row = ctk.CTkFrame(sam_frame, fg_color="transparent")
        s_row.pack(fill="x", pady=2)
        ctk.CTkLabel(s_row, text=f"{slot_key} ({slot_label}):",
                     font=("Segoe UI", 12, "bold"), text_color=colors["text"],
                     width=200, anchor="w").pack(side="left")

        s_var = ctk.StringVar(value="")
        ctk.CTkEntry(s_row, textvariable=s_var, width=320, height=30,
                     fg_color=colors["bg_light"], border_color=colors["border"],
                     font=("Consolas", 11)).pack(side="left", padx=(5, 5))

        def _browse_samsung(sv=s_var, sk=slot_key):
            path = filedialog.askopenfilename(
                title=f"Select {sk} File",
                filetypes=[("Samsung Firmware", "*.tar.md5 *.img *.bin"), ("All Files", "*.*")])
            if path:
                sv.set(path)

        ctk.CTkButton(s_row, text="Browse", width=80, height=30,
                      fg_color=colors["info"], hover_color=colors["accent"],
                      font=("Segoe UI", 10), command=_browse_samsung).pack(side="left")
        samsung_vars[slot_key] = s_var

    def _flash_samsung():
        if running["value"]:
            return
        files = {}
        for sk, sv in samsung_vars.items():
            p = sv.get().strip()
            if p:
                files[sk] = p
        if not files:
            _append_report("[!!] No Samsung firmware files selected")
            return
        _run_flash_operation("Samsung", lambda cb: flash_samsung(files, callback=cb))

    ctk.CTkButton(sam_frame, text="Flash via Heimdall", width=180, height=38,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 13, "bold"), corner_radius=8,
                  command=_flash_samsung).pack(anchor="w", pady=(10, 5))

    # ======================================================================
    # Fastboot tab
    # ======================================================================
    fb_frame = ctk.CTkFrame(tab_container, fg_color="transparent")
    tab_frames["Fastboot"] = fb_frame

    ctk.CTkLabel(
        fb_frame, text="Fastboot Flash",
        font=("Segoe UI", 15, "bold"), text_color=colors["accent"],
    ).pack(anchor="w", pady=(5, 10))

    fb_parts_frame = ctk.CTkScrollableFrame(fb_frame, fg_color=colors["bg_light"],
                                             corner_radius=8, height=140)
    fb_parts_frame.pack(fill="x", pady=(0, 5))

    fb_partition_rows = []

    def _add_fb_partition(part_name="", file_path=""):
        row_frame = ctk.CTkFrame(fb_parts_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)

        name_var = ctk.StringVar(value=part_name)
        ctk.CTkEntry(row_frame, textvariable=name_var, width=120, height=30,
                     placeholder_text="partition",
                     fg_color=colors["bg_card"], border_color=colors["border"],
                     font=("Consolas", 11)).pack(side="left", padx=(0, 5))

        path_var = ctk.StringVar(value=file_path)
        ctk.CTkEntry(row_frame, textvariable=path_var, width=320, height=30,
                     placeholder_text="image file path",
                     fg_color=colors["bg_card"], border_color=colors["border"],
                     font=("Consolas", 11)).pack(side="left", padx=(0, 5))

        def _browse_fb():
            p = filedialog.askopenfilename(
                title=f"Select Image for {name_var.get() or 'partition'}",
                filetypes=[("Image Files", "*.img *.bin"), ("All Files", "*.*")])
            if p:
                path_var.set(p)

        ctk.CTkButton(row_frame, text="Browse", width=65, height=30,
                      fg_color=colors["info"], hover_color=colors["accent"],
                      font=("Segoe UI", 10), command=_browse_fb).pack(side="left", padx=(0, 3))

        def _remove_fb_row():
            row_frame.destroy()
            fb_partition_rows[:] = [r for r in fb_partition_rows if r["frame"].winfo_exists()]

        ctk.CTkButton(row_frame, text="X", width=30, height=30,
                      fg_color="#e94560", hover_color="#ff4444",
                      font=("Segoe UI", 10, "bold"), command=_remove_fb_row).pack(side="left")

        fb_partition_rows.append({"frame": row_frame, "name": name_var, "path": path_var})

    for pname in ["boot", "system", "vendor"]:
        _add_fb_partition(part_name=pname)

    fb_btn_row = ctk.CTkFrame(fb_frame, fg_color="transparent")
    fb_btn_row.pack(fill="x", pady=(5, 5))

    ctk.CTkButton(fb_btn_row, text="+ Add Partition", width=130, height=32,
                  fg_color=colors["bg_medium"], hover_color=colors["bg_light"],
                  text_color=colors["text"], font=("Segoe UI", 11),
                  command=lambda: _add_fb_partition()).pack(side="left", padx=(0, 10))

    def _flash_fb():
        if running["value"]:
            return
        parts = {}
        for r in fb_partition_rows:
            if not r["frame"].winfo_exists():
                continue
            n = r["name"].get().strip()
            p = r["path"].get().strip()
            if n and p:
                parts[n] = p
        if not parts:
            _append_report("[!!] No partitions configured for flashing")
            return
        _run_flash_operation("Fastboot", lambda cb: flash_fastboot(parts, callback=cb))

    ctk.CTkButton(fb_btn_row, text="Flash via Fastboot", width=180, height=38,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 13, "bold"), corner_radius=8,
                  command=_flash_fb).pack(side="left")

    # ======================================================================
    # Partition Table card
    # ======================================================================
    pt_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    pt_card.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(
        pt_card, text="Partition Table",
        font=("Segoe UI", 16, "bold"), text_color=colors["info"],
    ).pack(anchor="w", padx=20, pady=(15, 8))

    pt_table_frame = ctk.CTkScrollableFrame(pt_card, fg_color=colors["bg_light"],
                                             corner_radius=8, height=160)
    pt_table_frame.pack(fill="x", padx=15, pady=(0, 5))

    # Table header
    pt_header = ctk.CTkFrame(pt_table_frame, fg_color=colors["bg_medium"], corner_radius=4, height=30)
    pt_header.pack(fill="x", pady=(0, 2))
    pt_header.pack_propagate(False)
    ctk.CTkLabel(pt_header, text="Name", font=("Segoe UI", 11, "bold"),
                 text_color=colors["text"], width=180, anchor="w").pack(side="left", padx=10)
    ctk.CTkLabel(pt_header, text="Size", font=("Segoe UI", 11, "bold"),
                 text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=5)
    ctk.CTkLabel(pt_header, text="Type / Info", font=("Segoe UI", 11, "bold"),
                 text_color=colors["text"], width=250, anchor="w").pack(side="left", padx=5)

    pt_status_label = ctk.CTkLabel(pt_card, text="",
                                    font=("Segoe UI", 12), text_color=colors["text_dim"])
    pt_status_label.pack(anchor="w", padx=20, pady=(2, 5))

    pt_row_widgets = []

    def _do_read_partitions():
        if running["value"]:
            return
        running["value"] = True
        pt_status_label.configure(text="Reading partitions...", text_color=colors["info"])
        _append_report("[INFO] Reading partition table from device...")

        # Clear old rows
        for w in pt_row_widgets:
            w.destroy()
        pt_row_widgets.clear()

        def _run():
            try:
                def cb(pct, msg):
                    app.content.after(0, lambda: pt_status_label.configure(text=msg))
                    app.content.after(0, lambda: progress_bar.set(pct / 100.0))

                result = read_partition_table(callback=cb)

                def _update():
                    if result.partitions:
                        for part in result.partitions:
                            row = ctk.CTkFrame(pt_table_frame, fg_color="transparent",
                                               height=26)
                            row.pack(fill="x", pady=1)
                            row.pack_propagate(False)
                            ctk.CTkLabel(
                                row, text=part.name, font=("Consolas", 10),
                                text_color=colors["text"], width=180, anchor="w",
                            ).pack(side="left", padx=10)
                            ctk.CTkLabel(
                                row, text=part.size_readable, font=("Consolas", 10),
                                text_color=colors["success"], width=120, anchor="w",
                            ).pack(side="left", padx=5)
                            info_text = part.type_guid or part.attributes or ""
                            ctk.CTkLabel(
                                row, text=info_text, font=("Consolas", 10),
                                text_color=colors["text_dim"], width=250, anchor="w",
                            ).pack(side="left", padx=5)
                            pt_row_widgets.append(row)

                        storage_info = (
                            f"Storage: {result.storage_type} | "
                            f"Total: {result.total_size_gb} GB | "
                            f"Partitions: {len(result.partitions)}"
                        )
                        pt_status_label.configure(text=storage_info, text_color=colors["success"])
                        _append_report(f"[OK] {storage_info}")
                    elif result.error:
                        pt_status_label.configure(text=result.error, text_color=colors["accent"])
                        _append_report(f"[!!] {result.error}")
                    else:
                        pt_status_label.configure(text="No partitions found", text_color=colors["warning"])
                        _append_report("[!!] No partitions found")

                    progress_bar.set(0)
                    running["value"] = False

                app.content.after(0, _update)
            except Exception as e:
                app.content.after(0, lambda: pt_status_label.configure(
                    text=f"Error: {e}", text_color=colors["accent"]))
                app.content.after(0, lambda: _append_report(f"[xx] Partition read error: {e}"))
                running["value"] = False

        threading.Thread(target=_run, daemon=True).start()

    ctk.CTkButton(
        pt_card, text="Read Partitions", width=160, height=36,
        fg_color=colors["info"], hover_color=colors["accent"],
        font=("Segoe UI", 12, "bold"), corner_radius=8,
        command=_do_read_partitions,
    ).pack(padx=20, pady=(0, 15))

    # ======================================================================
    # Progress bar + status badge
    # ======================================================================
    progress_bar = ctk.CTkProgressBar(app.content, width=600, height=18,
                                       progress_color=colors["accent"],
                                       fg_color=colors["bg_light"])
    progress_bar.set(0)
    progress_bar.pack(padx=20, pady=(0, 3), anchor="w")

    flash_status = ctk.CTkLabel(app.content, text="",
                                 font=("Segoe UI", 13, "bold"), text_color=colors["text_dim"])
    flash_status.pack(anchor="w", padx=20, pady=(0, 5))

    # ======================================================================
    # Report textbox with color-coded output
    # ======================================================================
    report_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    report_card.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    report_header_row = ctk.CTkFrame(report_card, fg_color="transparent")
    report_header_row.pack(fill="x", padx=15, pady=(10, 5))
    ctk.CTkLabel(
        report_header_row, text="Flash Log",
        font=("Segoe UI", 15, "bold"), text_color=colors["accent"],
    ).pack(side="left")

    def _copy_report():
        try:
            text = report_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            flash_status.configure(text="Report copied to clipboard", text_color=colors["success"])
        except Exception:
            pass

    def _clear_report():
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")

    ctk.CTkButton(report_header_row, text="Copy", width=70, height=28,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 10), command=_copy_report).pack(side="right", padx=(5, 0))
    ctk.CTkButton(report_header_row, text="Clear", width=70, height=28,
                  fg_color=colors["bg_medium"], hover_color=colors["bg_light"],
                  text_color=colors["text"], font=("Segoe UI", 10),
                  command=_clear_report).pack(side="right")

    report_box = ctk.CTkTextbox(report_card, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=250, wrap="none")
    report_box.pack(fill="both", expand=True, padx=15, pady=(0, 15))
    report_box.insert("1.0", "Firmware Flash Log\n" + "=" * 50 + "\n\n"
                      "Select flash mode and configure files above, then press Flash.\n"
                      "Detect the device flash mode first for best results.\n")

    # Color tags setup
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok", foreground="#2ed573")
        tb.tag_configure("warning", foreground="#ffa502")
        tb.tag_configure("fault", foreground="#e94560")
        tb.tag_configure("info", foreground="#1e90ff")
        tb.tag_configure("header", foreground="#e94560", font=("Consolas", 12, "bold"))

    _setup_tags()

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "critical", "danger", "[xx]", "error", "failed", "brick"]):
            return "fault"
        if any(k in t for k in ["warning", "[!!]", "missing", "not found", "skipping"]):
            return "warning"
        if any(k in t for k in ["[ok]", "success", "pass", "complete", "verified", "flashed"]):
            return "ok"
        if any(k in t for k in ["===", "---", "flash complete", "REPORT"]):
            return "header"
        if any(k in t for k in ["[info]", "detecting", "scanning", "reading", "checking"]):
            return "info"
        return None

    def _append_report(text):
        """Append a line to the report textbox with color tagging."""
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

    # ======================================================================
    # Shared flash operation runner
    # ======================================================================
    def _run_flash_operation(mode_name, flash_fn):
        """Run a flash operation in a background thread with progress updates."""
        if running["value"]:
            return
        running["value"] = True
        flash_status.configure(text=f"Flashing via {mode_name}...", text_color=colors["info"])
        progress_bar.set(0)

        _append_report("")
        _append_report(f"{'=' * 50}")
        _append_report(f"  FLASH OPERATION: {mode_name}")
        _append_report(f"{'=' * 50}")

        def _run():
            try:
                def cb(pct, msg):
                    app.content.after(0, lambda: progress_bar.set(pct / 100.0))
                    app.content.after(0, lambda: flash_status.configure(text=msg))
                    _append_report(f"  [{pct:5.1f}%] {msg}")

                result = flash_fn(cb)

                def _update():
                    if result.success:
                        flash_status.configure(
                            text=f"{mode_name} flash complete! "
                                 f"{len(result.partitions_flashed)} partition(s) in {result.duration_seconds}s",
                            text_color=colors["success"])
                        _append_report(f"[OK] Flash complete: {', '.join(result.partitions_flashed)}")
                        _append_report(f"[OK] Duration: {result.duration_seconds}s | Verified: {result.verified}")
                        if result.steps_performed:
                            _append_report("")
                            _append_report("  Steps performed:")
                            for step in result.steps_performed:
                                _append_report(f"    - {step}")
                    else:
                        flash_status.configure(
                            text=f"{mode_name} flash failed: {result.error}",
                            text_color=colors["accent"])
                        _append_report(f"[xx] Flash failed: {result.error}")
                        if result.steps_performed:
                            _append_report("  Steps completed before failure:")
                            for step in result.steps_performed:
                                _append_report(f"    - {step}")

                    progress_bar.set(0)
                    running["value"] = False

                app.content.after(0, _update)

            except Exception as e:
                def _err():
                    flash_status.configure(
                        text=f"Error: {e}", text_color=colors["accent"])
                    _append_report(f"[xx] Exception: {e}")
                    progress_bar.set(0)
                    running["value"] = False
                app.content.after(0, _err)

        threading.Thread(target=_run, daemon=True).start()

    # ── Show first tab ──
    _switch_tab("Qualcomm EDL")

    app.update_status("Firmware Flashing -- Select mode and configure files")
