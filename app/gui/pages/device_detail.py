import customtkinter as ctk

def render_device_detail(app, device):
    """Render detailed device view with tabs"""
    colors = app.colors
    specs = device.get("specs", {})
    components = device.get("components", [])
    test_points = device.get("test_points", [])
    procedures = device.get("procedures", [])

    # Back button
    back_btn = ctk.CTkButton(
        app.content, text="← Back to Devices", width=150,
        fg_color="transparent", hover_color=colors["bg_light"],
        text_color=colors["text_dim"], font=("Segoe UI", 12),
        command=app.show_devices
    )
    back_btn.pack(anchor="w", padx=20, pady=(10, 5))

    # Device header card
    header_card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    header_card.pack(fill="x", padx=20, pady=10)

    header_inner = ctk.CTkFrame(header_card, fg_color="transparent")
    header_inner.pack(fill="x", padx=20, pady=20)

    # Brand + Model
    ctk.CTkLabel(header_inner, text=device.get("brand", ""), font=("Segoe UI", 14), text_color=colors["accent"]).pack(anchor="w")
    ctk.CTkLabel(header_inner, text=device.get("model", "Unknown"), font=("Segoe UI", 28, "bold"), text_color=colors["text"]).pack(anchor="w")
    ctk.CTkLabel(header_inner, text=f"Released: {device.get('release_date', 'N/A')}  •  ID: {device.get('id', 'N/A')}", font=("Segoe UI", 12), text_color=colors["text_dim"]).pack(anchor="w", pady=(5, 0))

    # Quick spec badges
    badges = ctk.CTkFrame(header_inner, fg_color="transparent")
    badges.pack(anchor="w", pady=(10, 0))

    badge_data = [
        (f"🔲 {specs.get('processor', 'N/A')}", colors["info"]),
        (f"💾 {specs.get('ram', 'N/A')}", colors["success"]),
    ]

    # Handle battery - could be dict or string
    battery = specs.get("battery", {})
    if isinstance(battery, dict):
        badge_data.append((f"🔋 {battery.get('capacity', 'N/A')}", colors["warning"]))
    else:
        badge_data.append((f"🔋 {battery}", colors["warning"]))

    display = specs.get("display", {})
    if isinstance(display, dict):
        badge_data.append((f"📺 {display.get('size', 'N/A')} {display.get('type', '')}", "#9b59b6"))
    else:
        badge_data.append((f"📺 {display}", "#9b59b6"))

    for text, color in badge_data:
        badge = ctk.CTkLabel(badges, text=f" {text} ", font=("Segoe UI", 11, "bold"), fg_color=color, corner_radius=6, text_color="#fff", height=28)
        badge.pack(side="left", padx=3)

    # TAB VIEW
    tabview = ctk.CTkTabview(app.content, fg_color=colors["bg_card"], segmented_button_fg_color=colors["bg_medium"], segmented_button_selected_color=colors["accent"], segmented_button_unselected_color=colors["bg_light"])
    tabview.pack(fill="both", expand=True, padx=20, pady=10)

    # --- SPECS TAB ---
    tab_specs = tabview.add("📋 Specifications")
    _render_specs_tab(tab_specs, specs, colors)

    # --- COMPONENTS TAB ---
    tab_comp = tabview.add(f"🔧 Components ({len(components)})")
    _render_components_tab(tab_comp, components, colors)

    # --- TEST POINTS TAB ---
    tab_tp = tabview.add(f"⚡ Test Points ({len(test_points)})")
    _render_test_points_tab(tab_tp, test_points, colors)

    # --- PROCEDURES TAB ---
    tab_proc = tabview.add(f"📋 Procedures ({len(procedures)})")
    _render_procedures_tab(tab_proc, procedures, colors)

    app.update_status(f"Device Detail • {device.get('brand', '')} {device.get('model', '')} • {len(components)} components • {len(procedures)} procedures")


def _render_specs_tab(parent, specs, colors):
    """Render specifications in a clean table format"""
    # Flatten specs into rows
    rows = []
    for key, value in specs.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                rows.append((f"{key.replace('_', ' ').title()} - {sub_key.replace('_', ' ').title()}", str(sub_value)))
        elif isinstance(value, list):
            rows.append((key.replace("_", " ").title(), ", ".join(str(v) for v in value)))
        else:
            rows.append((key.replace("_", " ").title(), str(value)))

    for i, (label, value) in enumerate(rows):
        row_color = colors["bg_light"] if i % 2 == 0 else colors["bg_card"]
        row = ctk.CTkFrame(parent, fg_color=row_color, height=40, corner_radius=0)
        row.pack(fill="x", padx=10, pady=1)
        row.pack_propagate(False)

        ctk.CTkLabel(row, text=label, font=("Segoe UI", 13, "bold"), text_color=colors["text_dim"], width=250, anchor="w").pack(side="left", padx=15, pady=5)
        ctk.CTkLabel(row, text=value, font=("Segoe UI", 13), text_color=colors["text"], anchor="w").pack(side="left", padx=10, pady=5)


def _render_components_tab(parent, components, colors):
    """Render components list"""
    if not components:
        ctk.CTkLabel(parent, text="No component data available", font=("Segoe UI", 14), text_color=colors["text_dim"]).pack(pady=30)
        return

    for i, comp in enumerate(components):
        card = ctk.CTkFrame(parent, fg_color=colors["bg_light"], corner_radius=8)
        card.pack(fill="x", padx=10, pady=4)

        # Component header
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(header, text=comp.get("name", "Unknown"), font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(side="left")

        comp_type = comp.get("type", "")
        if comp_type:
            ctk.CTkLabel(header, text=f" [{comp_type}]", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")

        # Details
        details = ctk.CTkFrame(card, fg_color="transparent")
        details.pack(fill="x", padx=15, pady=(0, 10))

        info_items = []
        if comp.get("part_number"):
            info_items.append(f"Part#: {comp['part_number']}")
        if comp.get("location"):
            info_items.append(f"📍 {comp['location']}")
        if comp.get("voltage"):
            info_items.append(f"⚡ {comp['voltage']}")
        if comp.get("test_point"):
            info_items.append(f"🔍 TP: {comp['test_point']}")

        if info_items:
            ctk.CTkLabel(details, text="  •  ".join(info_items), font=("Segoe UI", 11), text_color=colors["text_dim"], wraplength=800, anchor="w").pack(anchor="w")

        # Failure symptoms
        symptoms = comp.get("failure_symptoms", [])
        if symptoms:
            ctk.CTkLabel(details, text=f"⚠️ Failure signs: {', '.join(symptoms)}", font=("Segoe UI", 11), text_color=colors["warning"], wraplength=800, anchor="w").pack(anchor="w", pady=(3, 0))


def _render_test_points_tab(parent, test_points, colors):
    """Render test points table"""
    if not test_points:
        ctk.CTkLabel(parent, text="No test point data available", font=("Segoe UI", 14), text_color=colors["text_dim"]).pack(pady=30)
        return

    # Table header
    header = ctk.CTkFrame(parent, fg_color=colors["accent"], corner_radius=0, height=40)
    header.pack(fill="x", padx=10, pady=(10, 0))
    header.pack_propagate(False)

    cols = [("Name", 150), ("Voltage", 100), ("Description", 300), ("Location", 250)]
    for text, width in cols:
        ctk.CTkLabel(header, text=text, font=("Segoe UI", 12, "bold"), text_color="#fff", width=width, anchor="w").pack(side="left", padx=10)

    # Rows
    for i, tp in enumerate(test_points):
        row_color = colors["bg_light"] if i % 2 == 0 else colors["bg_card"]
        row = ctk.CTkFrame(parent, fg_color=row_color, corner_radius=0, height=38)
        row.pack(fill="x", padx=10)
        row.pack_propagate(False)

        values = [
            (tp.get("name", ""), 150),
            (tp.get("voltage", ""), 100),
            (tp.get("description", ""), 300),
            (tp.get("location", ""), 250),
        ]
        for text, width in values:
            ctk.CTkLabel(row, text=text, font=("Segoe UI", 12), text_color=colors["text"], width=width, anchor="w").pack(side="left", padx=10)


def _render_procedures_tab(parent, procedures, colors):
    """Render repair procedures"""
    if not procedures:
        ctk.CTkLabel(parent, text="No repair procedures available", font=("Segoe UI", 14), text_color=colors["text_dim"]).pack(pady=30)
        return

    for proc in procedures:
        card = ctk.CTkFrame(parent, fg_color=colors["bg_light"], corner_radius=10)
        card.pack(fill="x", padx=10, pady=5)

        # Issue header
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(12, 5))

        ctk.CTkLabel(header, text=f"🔧 {proc.get('issue', 'Unknown Issue')}", font=("Segoe UI", 15, "bold"), text_color=colors["accent"]).pack(side="left")

        difficulty = proc.get("difficulty", "unknown")
        diff_colors = {"easy": colors["success"], "intermediate": colors["warning"], "advanced": colors["accent"], "expert": "#ff0000"}
        diff_color = diff_colors.get(difficulty, colors["text_dim"])
        ctk.CTkLabel(header, text=f"  [{difficulty.upper()}]", font=("Segoe UI", 11, "bold"), text_color=diff_color).pack(side="left")

        # Tools required
        tools = proc.get("tools_required", [])
        if tools:
            ctk.CTkLabel(card, text=f"🛠️ Tools: {', '.join(tools)}", font=("Segoe UI", 11), text_color=colors["text_dim"], anchor="w").pack(anchor="w", padx=15, pady=(0, 5))

        # Steps
        steps = proc.get("steps", [])
        for j, step in enumerate(steps, 1):
            step_frame = ctk.CTkFrame(card, fg_color="transparent")
            step_frame.pack(fill="x", padx=15, pady=2)

            ctk.CTkLabel(step_frame, text=f"  {j}.", font=("Segoe UI", 12, "bold"), text_color=colors["info"], width=30).pack(side="left")
            ctk.CTkLabel(step_frame, text=step, font=("Segoe UI", 12), text_color=colors["text"], anchor="w", wraplength=700).pack(side="left", padx=5)

        # Bottom padding
        ctk.CTkFrame(card, fg_color="transparent", height=10).pack()
