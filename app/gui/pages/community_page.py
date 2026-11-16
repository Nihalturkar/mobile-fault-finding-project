"""
Community Fault Database Page — Search, browse, and contribute repair fixes.

Features:
  - Search community fixes by device, chipset, symptom, or component
  - Browse all entries with filtering
  - Add new fixes from completed repairs
  - Vote on fixes (confirm / mark as failed)
  - Import/export community data for sharing
"""

import customtkinter as ctk
import threading
import json
from tkinter import filedialog


def render_community_page(app):
    """Render the Community Fault Database page."""
    colors = app.colors
    content = app.content

    # Title
    ctk.CTkLabel(content, text="🌍 Community Fault Database",
                 font=("Segoe UI", 24, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(content, text="Learn from other technicians' repairs • Search fixes • Share your knowledge",
                 font=("Segoe UI", 13),
                 text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # Stats card
    from app.hardware.community_db import CommunityFaultDB
    db = CommunityFaultDB()
    stats = db.get_stats()

    stats_card = ctk.CTkFrame(content, fg_color=colors["bg_card"], corner_radius=12)
    stats_card.pack(fill="x", padx=20, pady=(0, 10))

    stats_row = ctk.CTkFrame(stats_card, fg_color="transparent")
    stats_row.pack(fill="x", padx=20, pady=15)

    stat_items = [
        (f"{stats['total_entries']}", "Total Fixes", colors["accent"]),
        (f"{stats['total_confirmed_fixes']}", "Confirmed", colors["success"]),
        (f"{len(stats.get('brands', {}))}", "Brands", colors["info"]),
        (f"{len(stats.get('chipsets', {}))}", "Chipsets", colors["warning"]),
        (f"{len(stats.get('categories', {}))}", "Categories", "#b794f6"),
    ]

    for val, label, color in stat_items:
        sf = ctk.CTkFrame(stats_row, fg_color="transparent")
        sf.pack(side="left", expand=True, fill="x")
        ctk.CTkLabel(sf, text=val, font=("Segoe UI", 24, "bold"),
                     text_color=color).pack()
        ctk.CTkLabel(sf, text=label, font=("Segoe UI", 11),
                     text_color=colors["text_dim"]).pack()

    # Search section
    search_card = ctk.CTkFrame(content, fg_color=colors["bg_card"], corner_radius=12)
    search_card.pack(fill="x", padx=20, pady=5)

    ctk.CTkLabel(search_card, text="🔍 Search Community Fixes",
                 font=("Segoe UI", 15, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(15, 10))

    # Search inputs row
    search_row = ctk.CTkFrame(search_card, fg_color="transparent")
    search_row.pack(fill="x", padx=20, pady=(0, 5))

    search_entry = ctk.CTkEntry(search_row, placeholder_text="Search symptoms, components, fixes...",
                                fg_color=colors["bg_light"], font=("Segoe UI", 13),
                                width=350, height=38)
    search_entry.pack(side="left", padx=(0, 10))

    model_entry = ctk.CTkEntry(search_row, placeholder_text="Device model",
                               fg_color=colors["bg_light"], font=("Segoe UI", 13),
                               width=200, height=38)
    model_entry.pack(side="left", padx=(0, 10))

    chipset_entry = ctk.CTkEntry(search_row, placeholder_text="Chipset",
                                 fg_color=colors["bg_light"], font=("Segoe UI", 13),
                                 width=150, height=38)
    chipset_entry.pack(side="left", padx=(0, 10))

    # Filter row
    filter_row = ctk.CTkFrame(search_card, fg_color="transparent")
    filter_row.pack(fill="x", padx=20, pady=(5, 15))

    category_var = ctk.StringVar(value="All Categories")
    categories = ["All Categories", "power", "display", "connectivity", "storage",
                  "audio", "camera", "sensor", "system"]
    ctk.CTkOptionMenu(filter_row, values=categories, variable=category_var,
                      fg_color=colors["bg_light"],
                      button_color=colors["accent"],
                      font=("Segoe UI", 12), width=160).pack(side="left", padx=(0, 10))

    severity_var = ctk.StringVar(value="All Severities")
    ctk.CTkOptionMenu(filter_row, values=["All Severities", "critical", "warning", "info"],
                      variable=severity_var,
                      fg_color=colors["bg_light"],
                      button_color=colors["accent"],
                      font=("Segoe UI", 12), width=160).pack(side="left", padx=(0, 10))

    # Results area
    results_container = ctk.CTkFrame(content, fg_color="transparent")
    results_container.pack(fill="both", expand=True, padx=0, pady=0)

    results_scroll = ctk.CTkScrollableFrame(results_container, fg_color="transparent",
                                            scrollbar_button_color=colors["bg_light"],
                                            height=500)

    status_label = ctk.CTkLabel(content, text="",
                                font=("Segoe UI", 12),
                                text_color=colors["text_dim"])
    status_label.pack(anchor="w", padx=20, pady=5)

    def do_search():
        """Execute search and display results."""
        # Clear previous results
        for w in results_scroll.winfo_children():
            w.destroy()

        results_scroll.pack(fill="both", expand=True, padx=20, pady=10)

        query = search_entry.get().strip()
        model = model_entry.get().strip()
        chipset = chipset_entry.get().strip()
        cat = category_var.get()
        sev = severity_var.get()

        results = db.search(
            query=query,
            device_model=model,
            chipset=chipset,
            category="" if cat == "All Categories" else cat,
            severity="" if sev == "All Severities" else sev,
        )

        if not results:
            ctk.CTkLabel(results_scroll, text="No matching fixes found. Try broader search terms.",
                         font=("Segoe UI", 14),
                         text_color=colors["text_dim"]).pack(pady=20)
            status_label.configure(text="0 results found", text_color=colors["text_dim"])
            return

        status_label.configure(text=f"Found {len(results)} fix(es)",
                               text_color=colors["success"])

        for i, r in enumerate(results[:25]):  # Show top 25
            _build_result_card(results_scroll, r, i + 1, db, colors, status_label)

    def browse_all():
        """Show all community entries."""
        search_entry.delete(0, "end")
        model_entry.delete(0, "end")
        chipset_entry.delete(0, "end")
        category_var.set("All Categories")
        severity_var.set("All Severities")
        do_search()

    # Search buttons
    btn_row = ctk.CTkFrame(search_card, fg_color="transparent")
    btn_row.pack(fill="x", padx=20, pady=(0, 15))

    ctk.CTkButton(btn_row, text="🔍 Search",
                  font=("Segoe UI", 13, "bold"), height=38,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  command=do_search).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_row, text="📋 Browse All",
                  font=("Segoe UI", 13), height=38,
                  fg_color=colors["bg_light"], hover_color=colors["bg_card"],
                  text_color=colors["text"],
                  command=browse_all).pack(side="left", padx=(0, 10))

    search_entry.bind("<Return>", lambda e: do_search())

    # Bottom action bar
    action_bar = ctk.CTkFrame(content, fg_color=colors["bg_card"], corner_radius=12)
    action_bar.pack(fill="x", padx=20, pady=10)

    ab_row = ctk.CTkFrame(action_bar, fg_color="transparent")
    ab_row.pack(fill="x", padx=20, pady=15)

    def add_fix_dialog():
        """Open dialog to add a new community fix."""
        _show_add_fix_window(app, db, colors, status_label)

    def import_fixes():
        """Import community data from JSON file."""
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            title="Import Community Fixes",
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = f.read()
                count = db.import_entries(data)
                status_label.configure(text=f"✅ Imported {count} new fix(es)!",
                                       text_color=colors["success"])
            except Exception as e:
                status_label.configure(text=f"❌ Import failed: {e}",
                                       text_color=colors["accent"])

    def export_fixes():
        """Export community data to JSON file."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="mooxy_community_fixes.json",
            title="Export Community Fixes",
        )
        if path:
            try:
                data = db.export_entries()
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(data)
                status_label.configure(text=f"✅ Exported to: {path}",
                                       text_color=colors["success"])
            except Exception as e:
                status_label.configure(text=f"❌ Export failed: {e}",
                                       text_color=colors["accent"])

    ctk.CTkButton(ab_row, text="➕ Add New Fix",
                  font=("Segoe UI", 13, "bold"), height=38,
                  fg_color=colors["success"], hover_color="#3ce882",
                  text_color="#000000",
                  command=add_fix_dialog).pack(side="left", padx=(0, 10))

    ctk.CTkButton(ab_row, text="📥 Import Fixes",
                  font=("Segoe UI", 13), height=38,
                  fg_color=colors["bg_light"], hover_color=colors["bg_card"],
                  text_color=colors["text"],
                  command=import_fixes).pack(side="left", padx=(0, 10))

    ctk.CTkButton(ab_row, text="📤 Export Fixes",
                  font=("Segoe UI", 13), height=38,
                  fg_color=colors["bg_light"], hover_color=colors["bg_card"],
                  text_color=colors["text"],
                  command=export_fixes).pack(side="left")

    # Auto-show all entries on load
    browse_all()


def _build_result_card(parent, result, index, db, colors, status_label):
    """Build a single result card for a community fix."""
    e = result.entry

    card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10)
    card.pack(fill="x", pady=5)

    # Header row
    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill="x", padx=15, pady=(12, 5))

    severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(e.severity, "⚪")
    ctk.CTkLabel(header, text=f"{severity_icon} #{index}",
                 font=("Segoe UI", 12, "bold"),
                 text_color=colors["text_dim"]).pack(side="left", padx=(0, 8))

    ctk.CTkLabel(header, text=e.symptom,
                 font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(side="left", fill="x", expand=True, anchor="w")

    # Success badge
    if e.success_rate >= 80:
        badge_color = colors["success"]
    elif e.success_rate >= 50:
        badge_color = colors["warning"]
    else:
        badge_color = colors["accent"]

    ctk.CTkLabel(header, text=f"{e.success_rate}% success",
                 font=("Segoe UI", 11, "bold"),
                 text_color=badge_color).pack(side="right", padx=5)

    ctk.CTkLabel(header, text=f"✅ {e.confirmed_fix_count}",
                 font=("Segoe UI", 11),
                 text_color=colors["success"]).pack(side="right", padx=5)

    # Info row
    info_row = ctk.CTkFrame(card, fg_color="transparent")
    info_row.pack(fill="x", padx=15, pady=(0, 5))

    info_items = [
        f"📱 {e.device_model}",
        f"🔧 {e.fault_component}",
        f"⏱ ~{e.repair_time_min}min" if e.repair_time_min else "",
        f"🎯 {e.difficulty}",
    ]
    info_text = "  •  ".join([i for i in info_items if i])
    ctk.CTkLabel(info_row, text=info_text,
                 font=("Segoe UI", 11),
                 text_color=colors["text_dim"]).pack(anchor="w")

    if e.chipset:
        ctk.CTkLabel(info_row, text=f"Chipset: {e.chipset}",
                     font=("Segoe UI", 11),
                     text_color=colors["info"]).pack(anchor="w")

    # Root cause + fix
    ctk.CTkLabel(card, text=f"Root Cause: {e.root_cause}",
                 font=("Segoe UI", 12),
                 text_color=colors["warning"],
                 wraplength=800, justify="left").pack(anchor="w", padx=15, pady=(5, 2))

    ctk.CTkLabel(card, text=f"Fix: {e.fix_description}",
                 font=("Segoe UI", 12),
                 text_color=colors["success"],
                 wraplength=800, justify="left").pack(anchor="w", padx=15, pady=(0, 5))

    # Expandable details
    details_var = ctk.BooleanVar(value=False)
    details_frame = ctk.CTkFrame(card, fg_color=colors["bg_light"], corner_radius=8)

    def toggle_details():
        if details_var.get():
            details_frame.pack(fill="x", padx=15, pady=(0, 10))
        else:
            details_frame.pack_forget()

    # Bottom button row
    btn_row = ctk.CTkFrame(card, fg_color="transparent")
    btn_row.pack(fill="x", padx=15, pady=(0, 10))

    ctk.CTkButton(btn_row, text="📖 Details",
                  font=("Segoe UI", 11), height=30, width=90,
                  fg_color=colors["bg_light"], hover_color=colors["bg_medium"],
                  text_color=colors["text"],
                  command=lambda: (details_var.set(not details_var.get()), toggle_details())).pack(side="left", padx=(0, 5))

    def _confirm():
        db.confirm_fix(e.entry_id, success=True)
        status_label.configure(text=f"✅ Confirmed fix for: {e.symptom}", text_color=colors["success"])

    def _fail():
        db.confirm_fix(e.entry_id, success=False)
        status_label.configure(text=f"❌ Marked as failed: {e.symptom}", text_color=colors["accent"])

    ctk.CTkButton(btn_row, text="✅ Worked",
                  font=("Segoe UI", 11), height=30, width=80,
                  fg_color=colors["success"], hover_color="#3ce882",
                  text_color="#000000",
                  command=_confirm).pack(side="left", padx=(0, 5))

    ctk.CTkButton(btn_row, text="❌ Failed",
                  font=("Segoe UI", 11), height=30, width=80,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  command=_fail).pack(side="left", padx=(0, 5))

    # Relevance score
    if result.relevance_score > 0:
        ctk.CTkLabel(btn_row, text=f"Relevance: {result.relevance_score}",
                     font=("Segoe UI", 10),
                     text_color=colors["text_dim"]).pack(side="right")

    # Build details content (hidden initially)
    if e.repair_steps:
        ctk.CTkLabel(details_frame, text="Repair Steps:",
                     font=("Segoe UI", 12, "bold"),
                     text_color=colors["text"]).pack(anchor="w", padx=15, pady=(10, 5))
        for step in e.repair_steps:
            ctk.CTkLabel(details_frame, text=step,
                         font=("Segoe UI", 11),
                         text_color=colors["text_dim"],
                         wraplength=750, justify="left").pack(anchor="w", padx=25, pady=1)

    if e.parts_used:
        ctk.CTkLabel(details_frame, text=f"Parts: {', '.join(e.parts_used)}",
                     font=("Segoe UI", 11),
                     text_color=colors["info"]).pack(anchor="w", padx=15, pady=(10, 5))

    if e.tags:
        ctk.CTkLabel(details_frame, text=f"Tags: {', '.join(e.tags)}",
                     font=("Segoe UI", 10),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=15, pady=(5, 10))

    if e.tech_notes:
        ctk.CTkLabel(details_frame, text="Technician Notes:",
                     font=("Segoe UI", 12, "bold"),
                     text_color=colors["text"]).pack(anchor="w", padx=15, pady=(10, 5))
        for note in e.tech_notes:
            ctk.CTkLabel(details_frame, text=f"💬 {note}",
                         font=("Segoe UI", 11),
                         text_color=colors["text_dim"],
                         wraplength=750, justify="left").pack(anchor="w", padx=25, pady=1)

    # Pad bottom of details
    ctk.CTkFrame(details_frame, fg_color="transparent", height=10).pack()


def _show_add_fix_window(app, db, colors, status_label):
    """Show a dialog to add a new community fix."""
    dialog = ctk.CTkToplevel(app)
    dialog.title("Add New Community Fix")
    dialog.geometry("700x750")
    dialog.configure(fg_color=colors["bg_dark"])
    dialog.transient(app)
    dialog.grab_set()

    scroll = ctk.CTkScrollableFrame(dialog, fg_color=colors["bg_dark"],
                                    scrollbar_button_color=colors["bg_light"])
    scroll.pack(fill="both", expand=True, padx=10, pady=10)

    ctk.CTkLabel(scroll, text="➕ Add New Community Fix",
                 font=("Segoe UI", 20, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=10, pady=(10, 15))

    fields = {}

    def add_field(label, placeholder="", height=35, multiline=False):
        ctk.CTkLabel(scroll, text=label, font=("Segoe UI", 12, "bold"),
                     text_color=colors["text"]).pack(anchor="w", padx=10, pady=(10, 3))
        if multiline:
            widget = ctk.CTkTextbox(scroll, height=height, fg_color=colors["bg_light"],
                                    font=("Segoe UI", 12), text_color=colors["text"])
        else:
            widget = ctk.CTkEntry(scroll, placeholder_text=placeholder,
                                  fg_color=colors["bg_light"], font=("Segoe UI", 12),
                                  height=height)
        widget.pack(fill="x", padx=10, pady=(0, 5))
        fields[label] = widget
        return widget

    add_field("Device Model *", "e.g. Samsung Galaxy A15")
    add_field("Brand *", "e.g. Samsung")
    add_field("Chipset", "e.g. MT6765 / Snapdragon 680")
    add_field("Symptom *", "e.g. Phone dead, no charging indicator")
    add_field("Fault Component *", "e.g. PMIC MT6357")

    ctk.CTkLabel(scroll, text="Category:", font=("Segoe UI", 12, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=10, pady=(10, 3))
    cat_var = ctk.StringVar(value="power")
    ctk.CTkOptionMenu(scroll, values=["power", "display", "connectivity", "storage",
                                       "audio", "camera", "sensor", "system"],
                      variable=cat_var,
                      fg_color=colors["bg_light"],
                      button_color=colors["accent"],
                      font=("Segoe UI", 12)).pack(anchor="w", padx=10, pady=(0, 5))

    add_field("Root Cause *", "What was actually wrong")
    add_field("Fix Description *", "How was it fixed (one line)")
    add_field("Repair Steps (one per line)", height=100, multiline=True)
    add_field("Parts Used (comma separated)", "e.g. PMIC MT6357, 0201 capacitors x3")

    ctk.CTkLabel(scroll, text="Difficulty:", font=("Segoe UI", 12, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=10, pady=(10, 3))
    diff_var = ctk.StringVar(value="medium")
    ctk.CTkOptionMenu(scroll, values=["easy", "medium", "hard", "expert"],
                      variable=diff_var,
                      fg_color=colors["bg_light"],
                      button_color=colors["accent"],
                      font=("Segoe UI", 12)).pack(anchor="w", padx=10, pady=(0, 5))

    add_field("Repair Time (minutes)", "e.g. 60")
    add_field("Tags (comma separated)", "e.g. dead phone, pmic, water damage")

    def save_entry():
        try:
            model = fields["Device Model *"].get().strip()
            brand = fields["Brand *"].get().strip()
            symptom = fields["Symptom *"].get().strip()
            component = fields["Fault Component *"].get().strip()
            root_cause = fields["Root Cause *"].get().strip()
            fix_desc = fields["Fix Description *"].get().strip()

            if not all([model, brand, symptom, component, root_cause, fix_desc]):
                status_label.configure(text="❌ Fill all required fields (*)",
                                       text_color=colors["accent"])
                return

            steps_text = fields["Repair Steps (one per line)"].get("1.0", "end").strip()
            steps = [s.strip() for s in steps_text.split("\n") if s.strip()]

            parts_text = fields["Parts Used (comma separated)"].get().strip()
            parts = [p.strip() for p in parts_text.split(",") if p.strip()]

            tags_text = fields["Tags (comma separated)"].get().strip()
            tags = [t.strip() for t in tags_text.split(",") if t.strip()]

            time_str = fields["Repair Time (minutes)"].get().strip()
            try:
                repair_time = int(time_str)
            except ValueError:
                repair_time = 0

            entry_id = db.add_from_repair(
                device_model=model,
                brand=brand,
                chipset=fields["Chipset"].get().strip(),
                symptom=symptom,
                component=component,
                category=cat_var.get(),
                root_cause=root_cause,
                fix_description=fix_desc,
                repair_steps=steps,
                parts=parts,
                difficulty=diff_var.get(),
                repair_time=repair_time,
                tags=tags,
            )

            status_label.configure(text=f"✅ Fix added to community database! ID: {entry_id}",
                                   text_color=colors["success"])
            dialog.destroy()

        except Exception as e:
            status_label.configure(text=f"❌ Error: {e}", text_color=colors["accent"])

    # Save button
    ctk.CTkButton(scroll, text="💾 Save to Community Database",
                  font=("Segoe UI", 14, "bold"), height=42,
                  fg_color=colors["success"], hover_color="#3ce882",
                  text_color="#000000",
                  command=save_entry).pack(fill="x", padx=10, pady=(15, 10))

    ctk.CTkButton(scroll, text="Cancel",
                  font=("Segoe UI", 13), height=38,
                  fg_color=colors["bg_light"], hover_color=colors["bg_card"],
                  text_color=colors["text"],
                  command=dialog.destroy).pack(fill="x", padx=10, pady=(0, 10))
