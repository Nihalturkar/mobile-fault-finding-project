"""
Detection History Page — shows all past UART / ADB / EDL detections
with clickable entries, report viewer, and clear history.
"""

import customtkinter as ctk
import os


def render_history(app):
    """Render the detection history page."""
    colors = app.colors

    from app.gui.history_manager import get_history, clear_history, delete_detection

    # ── Page Header ──
    ctk.CTkLabel(
        app.content, text="Detection History",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="View all past hardware and ADB detections with saved reports",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Top action bar ──
    action_bar = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    action_bar.pack(fill="x", padx=20, pady=(0, 10))
    action_inner = ctk.CTkFrame(action_bar, fg_color="transparent")
    action_inner.pack(fill="x", padx=15, pady=10)

    # Filter by type
    ctk.CTkLabel(
        action_inner, text="Filter:", font=("Segoe UI", 13, "bold"),
        text_color=colors["text"],
    ).pack(side="left", padx=(0, 8))

    current_filter = {"value": "All"}
    filter_buttons = {}
    filter_names = ["All", "Fault", "ADB", "EDL"]
    filter_colors_map = {
        "All": colors["info"],
        "Fault": colors["accent"],
        "ADB": colors["info"],
        "EDL": colors["warning"],
    }

    def _apply_filter(ftype):
        current_filter["value"] = ftype
        for fname, btn in filter_buttons.items():
            if fname == ftype:
                btn.configure(fg_color=filter_colors_map[fname], text_color="#fff")
            else:
                btn.configure(fg_color=colors["bg_light"], text_color=colors["text_dim"])
        _render_list()

    for fname in filter_names:
        btn = ctk.CTkButton(
            action_inner, text=fname, width=80, height=34,
            fg_color=colors["bg_light"] if fname != "All" else filter_colors_map["All"],
            text_color=colors["text_dim"] if fname != "All" else "#fff",
            hover_color=filter_colors_map[fname],
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=lambda f=fname: _apply_filter(f),
        )
        btn.pack(side="left", padx=3)
        filter_buttons[fname] = btn

    count_label = ctk.CTkLabel(
        action_inner, text="", font=("Segoe UI", 12),
        text_color=colors["text_dim"],
    )
    count_label.pack(side="left", padx=(15, 0))

    # Clear History button
    def _confirm_clear():
        """Clear all detection history after confirmation."""
        clear_history()
        _render_list()
        app.update_status("Detection history cleared")

    ctk.CTkButton(
        action_inner, text="Clear History", width=130, height=34,
        fg_color="#cc0000", hover_color="#ff3333",
        text_color="#fff", font=("Segoe UI", 12, "bold"),
        corner_radius=8, command=_confirm_clear,
    ).pack(side="right")

    # ── Report viewer (hidden by default) ──
    viewer_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    viewer_visible = {"value": False}

    viewer_title = ctk.CTkLabel(
        viewer_frame, text="Report Viewer",
        font=("Segoe UI", 16, "bold"), text_color=colors["accent"],
    )
    viewer_title.pack(anchor="w", padx=20, pady=(15, 5))

    viewer_text = ctk.CTkTextbox(
        viewer_frame, font=("Consolas", 11), fg_color=colors["bg_dark"],
        text_color=colors["success"], height=300,
        border_color=colors["border"], border_width=1, wrap="none",
    )
    viewer_text.pack(fill="both", expand=True, padx=20, pady=(0, 10))

    viewer_btn_row = ctk.CTkFrame(viewer_frame, fg_color="transparent")
    viewer_btn_row.pack(fill="x", padx=20, pady=(0, 15))

    def _close_viewer():
        viewer_frame.pack_forget()
        viewer_visible["value"] = False

    def _copy_viewer():
        try:
            text = viewer_text.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
        except Exception:
            pass

    ctk.CTkButton(
        viewer_btn_row, text="Copy Report", width=120, height=32,
        fg_color=colors["info"], hover_color=colors["accent"],
        text_color="#fff", font=("Segoe UI", 12), corner_radius=6,
        command=_copy_viewer,
    ).pack(side="left", padx=(0, 10))

    ctk.CTkButton(
        viewer_btn_row, text="Close Viewer", width=120, height=32,
        fg_color=colors["bg_light"], hover_color=colors["accent"],
        text_color=colors["text_dim"], font=("Segoe UI", 12), corner_radius=6,
        command=_close_viewer,
    ).pack(side="left")

    # ── Detection list area ──
    list_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # ── Helpers ──

    def _view_report(report_path, device_name=""):
        """Load a report file into the inline viewer."""
        viewer_title.configure(text=f"Report: {device_name}" if device_name else "Report Viewer")
        viewer_text.configure(state="normal")
        viewer_text.delete("1.0", "end")

        if not report_path or not os.path.exists(report_path):
            viewer_text.insert("1.0", f"Report file not found:\n{report_path}")
        else:
            try:
                with open(report_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                viewer_text.insert("1.0", content)
            except Exception as e:
                viewer_text.insert("1.0", f"Error reading report:\n{e}")

        if not viewer_visible["value"]:
            viewer_frame.pack(fill="both", padx=20, pady=(0, 10), before=list_frame)
            viewer_visible["value"] = True

    def _open_report_external(report_path):
        """Open report file in the system default application."""
        if not report_path:
            return
        try:
            os.startfile(report_path)
        except Exception:
            pass

    def _render_list():
        """Render the detection entries list."""
        for w in list_frame.winfo_children():
            w.destroy()

        history = get_history()

        # Apply filter
        filt = current_filter["value"]
        if filt != "All":
            history = [d for d in history if d.get("type", "") == filt]

        count_label.configure(text=f"  {len(history)} records")

        if not history:
            empty_frame = ctk.CTkFrame(list_frame, fg_color=colors["bg_card"], corner_radius=12)
            empty_frame.pack(fill="x", pady=20)
            msg = "No detection records yet.\nRun a UART or ADB scan to see results here."
            if filt != "All":
                msg = f"No '{filt}' detection records found."
            ctk.CTkLabel(
                empty_frame, text=msg,
                font=("Segoe UI", 14), text_color=colors["text_dim"],
            ).pack(pady=40)
            return

        for entry in history:
            _render_detection_entry(list_frame, entry)

        app.update_status(f"Detection History — {len(history)} records")

    def _render_detection_entry(parent, entry):
        """Render a single detection history card."""
        det_type = entry.get("type", "?")
        type_colors_map = {
            "UART": colors["accent"],
            "ADB": colors["info"],
            "EDL": colors["warning"],
            "JTAG": "#fbbf24",
            "Manual": colors["success"],
        }
        type_color = type_colors_map.get(det_type, colors["info"])

        card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10)
        card.pack(fill="x", pady=4)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=15, pady=12)

        # Left column: device info
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="y")

        # Top row: type badge + device name
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

        # Date
        date_str = entry.get("date", "")
        if date_str:
            ctk.CTkLabel(
                left, text=f"Date: {date_str}",
                font=("Segoe UI", 11), text_color=colors["text_dim"],
            ).pack(anchor="w", pady=(4, 0))

        # Summary
        summary = entry.get("summary", "")
        if summary:
            ctk.CTkLabel(
                left, text=summary,
                font=("Segoe UI", 12), text_color=colors["text_dim"],
                anchor="w", wraplength=500,
            ).pack(anchor="w", pady=(2, 0))

        # Faults info
        faults_count = entry.get("faults_count", 0)
        faults_summary = entry.get("faults_summary", "")
        if faults_count > 0:
            fault_text = f"{faults_count} fault(s) detected"
            if faults_summary:
                fault_text += f": {faults_summary[:80]}"
            ctk.CTkLabel(
                left, text=fault_text,
                font=("Segoe UI", 11, "bold"), text_color=colors["accent"],
                anchor="w", wraplength=500,
            ).pack(anchor="w", pady=(2, 0))
        else:
            ctk.CTkLabel(
                left, text="No faults detected",
                font=("Segoe UI", 11), text_color=colors["success"],
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        # Report file path
        report_file = entry.get("report_file", "")
        if report_file:
            ctk.CTkLabel(
                left, text=f"Report: {report_file}",
                font=("Segoe UI", 10), text_color=colors["text_dim"],
                anchor="w", wraplength=500,
            ).pack(anchor="w", pady=(2, 0))

        # Right column: action buttons
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right")

        # View report inline
        if report_file:
            device_name = entry.get("device_name", "")

            ctk.CTkButton(
                right, text="View Report", width=120, height=30,
                fg_color=colors["info"], hover_color=colors["accent"],
                text_color="#fff", font=("Segoe UI", 11, "bold"),
                corner_radius=6,
                command=lambda p=report_file, d=device_name: _view_report(p, d),
            ).pack(pady=(0, 5))

            ctk.CTkButton(
                right, text="Open Report", width=120, height=30,
                fg_color=colors["success"], hover_color=colors["accent"],
                text_color="#fff", font=("Segoe UI", 11),
                corner_radius=6,
                command=lambda p=report_file: _open_report_external(p),
            ).pack(pady=(0, 5))

        # Delete button
        det_id = entry.get("id")

        def _delete(did=det_id):
            delete_detection(did)
            if viewer_visible["value"]:
                _close_viewer()
            _render_list()

        ctk.CTkButton(
            right, text="Delete", width=120, height=30,
            fg_color="#cc0000", hover_color="#ff3333",
            text_color="#fff", font=("Segoe UI", 11),
            corner_radius=6, command=_delete,
        ).pack()

        # Make the card clickable to view report
        if report_file:
            def _on_card_click(event, p=report_file, d=entry.get("device_name", "")):
                _view_report(p, d)

            card.bind("<Button-1>", _on_card_click)
            inner.bind("<Button-1>", _on_card_click)
            left.bind("<Button-1>", _on_card_click)

    # ── Initial render ──
    _render_list()
    app.update_status("Detection History — Browse past detections")
