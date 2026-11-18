import customtkinter as ctk
from datetime import datetime


def render_repair_history(app):
    """Render the repair history tracking page with persistent storage.
    Shows both manual repair records AND auto-saved detection records."""
    colors = app.colors

    # ── Load from persistent storage ──
    from app.gui.history_manager import (
        load_repairs, save_repairs, load_detections, delete_detection
    )

    # Load persistent data
    if not hasattr(app, "repair_history"):
        app.repair_history = load_repairs()
    else:
        # Sync: if app has in-memory records, merge with file
        file_repairs = load_repairs()
        if app.repair_history and not file_repairs:
            save_repairs(app.repair_history)
        elif file_repairs:
            app.repair_history = file_repairs

    history = app.repair_history
    detections = load_detections()

    # Page title
    ctk.CTkLabel(
        app.content, text="Repair History",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Track repairs and view all past detections (UART / ADB / Manual)",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Tab selector: Repairs vs Detections ──
    tab_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    tab_frame.pack(fill="x", padx=20, pady=(0, 10))
    tab_inner = ctk.CTkFrame(tab_frame, fg_color="transparent")
    tab_inner.pack(fill="x", padx=15, pady=10)

    current_tab = {"value": "detections"}
    tab_buttons = {}

    def _switch_tab(tab_name):
        current_tab["value"] = tab_name
        for name, btn in tab_buttons.items():
            if name == tab_name:
                btn.configure(fg_color=colors["accent"], text_color="#fff")
            else:
                btn.configure(fg_color=colors["bg_light"], text_color=colors["text_dim"])
        _render_content()

    det_count = len(detections)
    rep_count = len(history)

    tab_buttons["detections"] = ctk.CTkButton(
        tab_inner, text=f"🔍 Detections ({det_count})", width=180, height=38,
        fg_color=colors["accent"], text_color="#fff",
        hover_color=colors["accent_hover"], font=("Segoe UI", 13, "bold"),
        corner_radius=8, command=lambda: _switch_tab("detections"),
    )
    tab_buttons["detections"].pack(side="left", padx=(0, 8))

    tab_buttons["repairs"] = ctk.CTkButton(
        tab_inner, text=f"🛠️ Repairs ({rep_count})", width=180, height=38,
        fg_color=colors["bg_light"], text_color=colors["text_dim"],
        hover_color=colors["accent_hover"], font=("Segoe UI", 13, "bold"),
        corner_radius=8, command=lambda: _switch_tab("repairs"),
    )
    tab_buttons["repairs"].pack(side="left", padx=(0, 8))

    # ── Top bar: New Repair + Filters ──
    top_bar = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    top_bar.pack(fill="x", padx=20, pady=(0, 15))

    top_inner = ctk.CTkFrame(top_bar, fg_color="transparent")
    top_inner.pack(fill="x", padx=20, pady=15)

    new_btn = ctk.CTkButton(
        top_inner, text="+ New Repair", width=150, height=40,
        fg_color=colors["accent"], hover_color=colors["accent_hover"],
        font=("Segoe UI", 14, "bold"), corner_radius=10,
        command=lambda: _show_new_repair_form(),
    )
    new_btn.pack(side="left", padx=(0, 20))

    # Status filter buttons
    ctk.CTkLabel(
        top_inner, text="Filter:", font=("Segoe UI", 12),
        text_color=colors["text_dim"],
    ).pack(side="left", padx=(0, 8))

    current_filter = {"value": "All"}
    filter_buttons = {}

    filter_names = ["All", "Pending", "In Progress", "Completed"]
    filter_colors = {
        "All": colors["info"],
        "Pending": colors["warning"],
        "In Progress": colors["accent"],
        "Completed": colors["success"],
    }

    for fname in filter_names:
        def _make_filter(f=fname):
            return lambda: _apply_filter(f)

        btn = ctk.CTkButton(
            top_inner, text=fname, width=100, height=34,
            fg_color=colors["bg_light"], hover_color=filter_colors[fname],
            text_color=colors["text_dim"], font=("Segoe UI", 12),
            corner_radius=8, command=_make_filter(fname),
        )
        btn.pack(side="left", padx=3)
        filter_buttons[fname] = btn

    filter_buttons["All"].configure(fg_color=filter_colors["All"], text_color="#fff")

    count_label = ctk.CTkLabel(
        top_inner, text="",
        font=("Segoe UI", 12), text_color=colors["text_dim"],
    )
    count_label.pack(side="right")

    # ── Form frame (hidden until New Repair) ──
    form_frame = ctk.CTkFrame(app.content, fg_color="transparent")

    # ── Content list area ──
    list_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # ────── Helpers ──────

    def _apply_filter(status):
        current_filter["value"] = status
        for fname, btn in filter_buttons.items():
            if fname == status:
                btn.configure(fg_color=filter_colors[fname], text_color="#fff")
            else:
                btn.configure(fg_color=colors["bg_light"], text_color=colors["text_dim"])
        _render_content()

    def _render_content():
        """Render based on current tab."""
        for w in list_frame.winfo_children():
            w.destroy()

        if current_tab["value"] == "detections":
            _render_detections_list()
        else:
            _render_repairs_list()

    # ════════════════════════════════════════════════════════════
    #  DETECTIONS TAB
    # ════════════════════════════════════════════════════════════

    def _render_detections_list():
        det_list = load_detections()

        filt = current_filter["value"]
        if filt != "All":
            det_list = [d for d in det_list if d.get("status") == filt]

        count_label.configure(text=f"  {len(det_list)} detection records")

        if not det_list:
            msg = "No detection records yet. Run a UART or ADB scan to see results here."
            if filt != "All":
                msg = f"No '{filt}' detections found."
            ctk.CTkLabel(
                list_frame, text=msg,
                font=("Segoe UI", 14), text_color=colors["text_dim"],
            ).pack(pady=40)
            return

        for entry in reversed(det_list):
            _render_detection_card(list_frame, entry)

        app.update_status(f"Detection History — {len(det_list)} records")

    def _render_detection_card(parent, entry):
        det_type = entry.get("type", "?")
        type_colors = {
            "UART": "#ec4899",
            "ADB": "#a855f7",
            "EDL": "#c084fc",
            "JTAG": "#fbbf24",
            "Manual": "#34d399",
        }
        type_color = type_colors.get(det_type, colors["info"])

        card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10)
        card.pack(fill="x", pady=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        # Left: device info
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="y")

        # Type badge + device name on same line
        top_row = ctk.CTkFrame(left, fg_color="transparent")
        top_row.pack(anchor="w")

        ctk.CTkLabel(
            top_row, text=f"  {det_type}  ", font=("Segoe UI", 11, "bold"),
            fg_color=type_color, corner_radius=6, text_color="#fff", height=24,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            top_row, text=entry.get("device_name", "Unknown Device"),
            font=("Segoe UI", 14, "bold"), text_color=colors["text"],
        ).pack(side="left")

        # Summary
        summary = entry.get("summary", "")
        if summary:
            ctk.CTkLabel(
                left, text=summary,
                font=("Segoe UI", 12), text_color=colors["text_dim"],
                anchor="w", wraplength=500,
            ).pack(anchor="w", pady=(4, 0))

        # Faults info
        faults_count = entry.get("faults_count", 0)
        faults_summary = entry.get("faults_summary", "")
        if faults_count > 0:
            fault_text = f"🔴 {faults_count} fault(s)"
            if faults_summary:
                fault_text += f": {faults_summary[:80]}"
            ctk.CTkLabel(
                left, text=fault_text,
                font=("Segoe UI", 11), text_color=colors["accent"],
                anchor="w", wraplength=500,
            ).pack(anchor="w", pady=(2, 0))
        else:
            ctk.CTkLabel(
                left, text="✅ No faults detected",
                font=("Segoe UI", 11), text_color=colors["success"],
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        # Date
        date_str = entry.get("date", "")
        if date_str:
            ctk.CTkLabel(
                left, text=f"📅 {date_str}",
                font=("Segoe UI", 11), text_color=colors["text_dim"],
            ).pack(anchor="w", pady=(2, 0))

        # Right: actions
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right")

        # Open report file button
        report_file = entry.get("report_file", "")
        if report_file:
            def _open_report(path=report_file):
                try:
                    import os
                    os.startfile(path)
                except Exception:
                    pass

            ctk.CTkButton(
                right, text="📄 Open Report", width=120, height=30,
                fg_color=colors["info"], hover_color=colors["accent"],
                text_color="#fff", font=("Segoe UI", 11),
                corner_radius=6, command=_open_report,
            ).pack(pady=(0, 5))

        # Delete button
        def _delete_det(det_id=entry.get("id")):
            delete_detection(det_id)
            _render_content()

        ctk.CTkButton(
            right, text="🗑️ Delete", width=120, height=30,
            fg_color="#cc0000", hover_color="#ff3333",
            text_color="#fff", font=("Segoe UI", 11),
            corner_radius=6, command=_delete_det,
        ).pack()

    # ════════════════════════════════════════════════════════════
    #  REPAIRS TAB
    # ════════════════════════════════════════════════════════════

    def _render_repairs_list():
        filt = current_filter["value"]
        if filt == "All":
            visible = list(history)
        else:
            visible = [r for r in history if r.get("status") == filt]

        count_label.configure(text=f"  {len(visible)} repair records")

        if not visible:
            msg = "No repair records yet. Click '+ New Repair' to add one."
            if filt != "All":
                msg = f"No '{filt}' repairs found."
            ctk.CTkLabel(
                list_frame, text=msg,
                font=("Segoe UI", 14), text_color=colors["text_dim"],
            ).pack(pady=40)
            app.update_status(f"Repair History — {len(history)} total records")
            return

        for entry in reversed(visible):
            _render_entry_card(list_frame, entry)

        app.update_status(
            f"Repair History — Showing {len(visible)} of {len(history)} records"
        )

    def _render_entry_card(parent, entry):
        status = entry.get("status", "Pending")
        status_colors = {
            "Pending": colors["warning"],
            "In Progress": colors["accent"],
            "Completed": colors["success"],
        }
        s_color = status_colors.get(status, colors["text_dim"])

        card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10)
        card.pack(fill="x", pady=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        # Left: device + issue
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="y")

        ctk.CTkLabel(
            left, text=entry.get("device_name", "Unknown Device"),
            font=("Segoe UI", 14, "bold"), text_color=colors["text"], anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            left, text=entry.get("issue", "No issue described"),
            font=("Segoe UI", 12), text_color=colors["text_dim"],
            anchor="w", wraplength=400,
        ).pack(anchor="w", pady=(2, 0))

        date_str = entry.get("date", "")
        if date_str:
            ctk.CTkLabel(
                left, text=f"Date: {date_str}",
                font=("Segoe UI", 11), text_color=colors["text_dim"], anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        notes = entry.get("notes", "")
        if notes:
            ctk.CTkLabel(
                left, text=f"Notes: {notes}",
                font=("Segoe UI", 11), text_color=colors["text_dim"],
                anchor="w", wraplength=400,
            ).pack(anchor="w", pady=(2, 0))

        # Right: status badge + toggle buttons
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right")

        badge = ctk.CTkLabel(
            right, text=f"  {status}  ", font=("Segoe UI", 12, "bold"),
            fg_color=s_color, corner_radius=6, text_color="#fff", height=28,
        )
        badge.pack(pady=(0, 8))

        toggle_frame = ctk.CTkFrame(right, fg_color="transparent")
        toggle_frame.pack()

        for s_name in ["Pending", "In Progress", "Completed"]:
            if s_name == status:
                continue

            def _make_toggle(e=entry, s=s_name):
                return lambda: _change_status(e, s)

            ctk.CTkButton(
                toggle_frame, text=s_name, width=90, height=26,
                fg_color=status_colors.get(s_name, colors["bg_light"]),
                hover_color=colors["accent_hover"],
                text_color="#fff", font=("Segoe UI", 10),
                corner_radius=6, command=_make_toggle(),
            ).pack(side="left", padx=2, pady=2)

        ctk.CTkButton(
            toggle_frame, text="Edit", width=50, height=26,
            fg_color=colors["bg_light"], hover_color=colors["info"],
            text_color=colors["text_dim"], font=("Segoe UI", 10),
            corner_radius=6,
            command=lambda e=entry: _show_edit_form(e),
        ).pack(side="left", padx=2, pady=2)

    def _change_status(entry, new_status):
        entry["status"] = new_status
        save_repairs(history)
        _render_content()

    # ── New repair form ──
    def _show_new_repair_form():
        _switch_tab("repairs")
        form_frame.pack(fill="x", padx=20, pady=(0, 15), before=list_frame)
        for w in form_frame.winfo_children():
            w.destroy()

        card = ctk.CTkFrame(form_frame, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x")

        ctk.CTkLabel(
            card, text="New Repair Entry",
            font=("Segoe UI", 16, "bold"), text_color=colors["accent"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        form_inner = ctk.CTkFrame(card, fg_color="transparent")
        form_inner.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            form_inner, text="Device:", font=("Segoe UI", 13),
            text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 3))

        devices = app.devices
        device_names = [f"{d.get('brand', '')} {d.get('model', '')}" for d in devices]
        if not device_names:
            device_names = ["No devices loaded"]
        device_var = ctk.StringVar(value=device_names[0])
        ctk.CTkOptionMenu(
            form_inner, values=device_names, variable=device_var,
            width=400, height=36, font=("Segoe UI", 12),
            fg_color=colors["bg_light"], button_color=colors["accent"],
        ).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            form_inner, text="Issue Description:", font=("Segoe UI", 13),
            text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 3))

        issue_entry = ctk.CTkEntry(
            form_inner, width=500, height=36,
            placeholder_text="Describe the issue...",
            font=("Segoe UI", 12),
            fg_color=colors["bg_light"], border_color=colors["border"],
        )
        issue_entry.pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            form_inner, text="Notes (optional):", font=("Segoe UI", 13),
            text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 3))

        notes_entry = ctk.CTkTextbox(
            form_inner, width=500, height=80, font=("Segoe UI", 12),
            fg_color=colors["bg_light"], border_color=colors["border"],
        )
        notes_entry.pack(anchor="w", pady=(0, 10))

        btn_row = ctk.CTkFrame(form_inner, fg_color="transparent")
        btn_row.pack(anchor="w")

        def _save():
            issue = issue_entry.get().strip()
            if not issue:
                issue = "No issue described"
            notes_text = notes_entry.get("1.0", "end").strip()

            entry = {
                "device_name": device_var.get(),
                "issue": issue,
                "notes": notes_text,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "status": "Pending",
            }
            history.append(entry)
            save_repairs(history)
            form_frame.pack_forget()
            _render_content()

        ctk.CTkButton(
            btn_row, text="Save", width=100, height=36,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 13, "bold"), command=_save,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="Cancel", width=100, height=36,
            fg_color=colors["bg_light"], hover_color=colors["accent"],
            text_color=colors["text_dim"], font=("Segoe UI", 13),
            command=lambda: form_frame.pack_forget(),
        ).pack(side="left")

    # ── Edit repair form ──
    def _show_edit_form(entry):
        form_frame.pack(fill="x", padx=20, pady=(0, 15), before=list_frame)
        for w in form_frame.winfo_children():
            w.destroy()

        card = ctk.CTkFrame(form_frame, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x")

        ctk.CTkLabel(
            card, text="Edit Repair Entry",
            font=("Segoe UI", 16, "bold"), text_color=colors["info"],
        ).pack(anchor="w", padx=20, pady=(15, 10))

        form_inner = ctk.CTkFrame(card, fg_color="transparent")
        form_inner.pack(fill="x", padx=20, pady=(0, 15))

        ctk.CTkLabel(
            form_inner, text=f"Device: {entry.get('device_name', '')}",
            font=("Segoe UI", 13, "bold"), text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            form_inner, text="Issue Description:", font=("Segoe UI", 13),
            text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 3))

        issue_entry = ctk.CTkEntry(
            form_inner, width=500, height=36, font=("Segoe UI", 12),
            fg_color=colors["bg_light"], border_color=colors["border"],
        )
        issue_entry.insert(0, entry.get("issue", ""))
        issue_entry.pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            form_inner, text="Notes:", font=("Segoe UI", 13),
            text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 3))

        notes_box = ctk.CTkTextbox(
            form_inner, width=500, height=80, font=("Segoe UI", 12),
            fg_color=colors["bg_light"], border_color=colors["border"],
        )
        notes_box.insert("1.0", entry.get("notes", ""))
        notes_box.pack(anchor="w", pady=(0, 10))

        ctk.CTkLabel(
            form_inner, text="Status:", font=("Segoe UI", 13),
            text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 3))

        status_var = ctk.StringVar(value=entry.get("status", "Pending"))
        ctk.CTkOptionMenu(
            form_inner, values=["Pending", "In Progress", "Completed"],
            variable=status_var, width=200, height=36,
            fg_color=colors["bg_light"], button_color=colors["accent"],
        ).pack(anchor="w", pady=(0, 10))

        btn_row = ctk.CTkFrame(form_inner, fg_color="transparent")
        btn_row.pack(anchor="w")

        def _save_edit():
            entry["issue"] = issue_entry.get().strip() or entry.get("issue", "")
            entry["notes"] = notes_box.get("1.0", "end").strip()
            entry["status"] = status_var.get()
            save_repairs(history)
            form_frame.pack_forget()
            _render_content()

        ctk.CTkButton(
            btn_row, text="Save Changes", width=130, height=36,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 13, "bold"), command=_save_edit,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="Cancel", width=100, height=36,
            fg_color=colors["bg_light"], hover_color=colors["accent"],
            text_color=colors["text_dim"], font=("Segoe UI", 13),
            command=lambda: form_frame.pack_forget(),
        ).pack(side="left")

        def _delete():
            if entry in history:
                history.remove(entry)
            save_repairs(history)
            form_frame.pack_forget()
            _render_content()

        ctk.CTkButton(
            btn_row, text="Delete", width=80, height=36,
            fg_color="#cc0000", hover_color="#ff3333",
            text_color="#fff", font=("Segoe UI", 13),
            command=_delete,
        ).pack(side="left", padx=(10, 0))

    # ── Initial render — show detections tab by default ──
    _render_content()
