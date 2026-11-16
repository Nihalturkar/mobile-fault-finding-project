import customtkinter as ctk

def render_device_list(app):
    """Render the device browser page with grid of device cards"""
    colors = app.colors
    devices = app.filtered_devices

    # Page header
    header = ctk.CTkFrame(app.content, fg_color="transparent")
    header.pack(fill="x", padx=20, pady=(20, 10))

    ctk.CTkLabel(header, text="📱 All Devices", font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(side="left")
    ctk.CTkLabel(header, text=f"  ({len(devices)} devices)", font=("Segoe UI", 14), text_color=colors["text_dim"]).pack(side="left", pady=(8, 0))

    # Sort options
    sort_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    sort_frame.pack(fill="x", padx=20, pady=(0, 10))

    ctk.CTkLabel(sort_frame, text="Sort by:", font=("Segoe UI", 12), text_color=colors["text_dim"]).pack(side="left")

    sort_var = ctk.StringVar(value="Brand")

    def sort_devices(choice):
        if choice == "Brand":
            app.filtered_devices.sort(key=lambda d: (d.get("brand", ""), d.get("model", "")))
        elif choice == "Model":
            app.filtered_devices.sort(key=lambda d: d.get("model", ""))
        elif choice == "Release Date":
            app.filtered_devices.sort(key=lambda d: d.get("release_date", ""), reverse=True)
        render_device_list(app)  # Re-render

    sort_menu = ctk.CTkOptionMenu(sort_frame, values=["Brand", "Model", "Release Date"], variable=sort_var, command=sort_devices, width=150, fg_color=colors["bg_light"], button_color=colors["accent"])
    sort_menu.pack(side="left", padx=10)

    # Device grid
    current_brand = None
    for i, device in enumerate(devices):
        brand = device.get("brand", "Unknown")

        # Brand section header
        if brand != current_brand:
            current_brand = brand
            brand_header = ctk.CTkFrame(app.content, fg_color="transparent")
            brand_header.pack(fill="x", padx=20, pady=(15, 5))
            ctk.CTkLabel(brand_header, text=f"━━━ {brand} ━━━", font=("Segoe UI", 16, "bold"), text_color=colors["accent"]).pack(anchor="w")

        # Device card
        specs = device.get("specs", {})

        card = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=10, height=90)
        card.pack(fill="x", padx=20, pady=3)
        card.pack_propagate(False)

        # Left side - brand & model
        left = ctk.CTkFrame(card, fg_color="transparent", width=300)
        left.pack(side="left", fill="y", padx=15, pady=10)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text=device.get("model", "Unknown"), font=("Segoe UI", 15, "bold"), text_color=colors["text"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(left, text=f"{brand} • {device.get('release_date', 'N/A')}", font=("Segoe UI", 11), text_color=colors["text_dim"], anchor="w").pack(anchor="w")

        # Middle - key specs
        mid = ctk.CTkFrame(card, fg_color="transparent")
        mid.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        spec_items = [
            f"🔲 {specs.get('processor', 'N/A')}",
            f"💾 {specs.get('ram', 'N/A')}",
            f"🔋 {specs.get('battery', {}).get('capacity', 'N/A') if isinstance(specs.get('battery'), dict) else specs.get('battery', 'N/A')}",
            f"📺 {specs.get('display', {}).get('size', 'N/A') if isinstance(specs.get('display'), dict) else specs.get('display', 'N/A')}"
        ]

        spec_text = "  •  ".join(spec_items)
        ctk.CTkLabel(mid, text=spec_text, font=("Segoe UI", 11), text_color=colors["text_dim"], anchor="w", wraplength=500).pack(anchor="w", pady=(10, 0))

        # Components/procedures count
        comp_count = len(device.get("components", []))
        proc_count = len(device.get("procedures", []))
        ctk.CTkLabel(mid, text=f"🔧 {comp_count} components  •  📋 {proc_count} procedures", font=("Segoe UI", 10), text_color=colors["text_dim"], anchor="w").pack(anchor="w")

        # Right side - action button
        view_btn = ctk.CTkButton(
            card, text="View Details →", width=130, height=36,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=lambda d=device: app.show_device_detail(d)
        )
        view_btn.pack(side="right", padx=15)

    if not devices:
        ctk.CTkLabel(app.content, text="No devices found.", font=("Segoe UI", 16), text_color=colors["text_dim"]).pack(pady=50)

    app.update_status(f"Devices • Showing {len(devices)} of {len(app.devices)} devices")
