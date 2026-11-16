import customtkinter as ctk
from datetime import date


def render_add_device(app):
    """Render the Add Device page - manually add a new device to the database"""
    colors = app.colors

    # Page title
    ctk.CTkLabel(app.content, text="➕ Add New Device", font=("Segoe UI", 24, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content, text="Manually add a device or use Auto-Detect to fill details automatically",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 20))

    # ── BASIC INFO SECTION ──
    section1 = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    section1.pack(fill="x", padx=20, pady=8)

    ctk.CTkLabel(section1, text="📱 Basic Information", font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    fields_frame1 = ctk.CTkFrame(section1, fg_color="transparent")
    fields_frame1.pack(fill="x", padx=20, pady=(0, 15))

    # Row 1: Brand, Model
    row1 = ctk.CTkFrame(fields_frame1, fg_color="transparent")
    row1.pack(fill="x", pady=5)

    ctk.CTkLabel(row1, text="Brand:", font=("Segoe UI", 13), text_color=colors["text"], width=100, anchor="w").pack(side="left")
    brand_var = ctk.StringVar()
    brand_entry = ctk.CTkComboBox(row1, values=["Apple", "Samsung", "Xiaomi", "OnePlus", "Google", "Oppo", "Vivo",
                                                  "Realme", "Motorola", "Nothing", "Asus", "Sony", "Honor",
                                                  "Huawei", "Tecno", "Infinix", "Other"],
                                   variable=brand_var, width=250, fg_color=colors["bg_light"],
                                   border_color=colors["border"])
    brand_entry.pack(side="left", padx=(0, 20))

    ctk.CTkLabel(row1, text="Model:", font=("Segoe UI", 13), text_color=colors["text"], width=100, anchor="w").pack(side="left")
    model_var = ctk.StringVar()
    model_entry = ctk.CTkEntry(row1, textvariable=model_var, width=300, fg_color=colors["bg_light"],
                                border_color=colors["border"], placeholder_text="e.g. Galaxy S24 Ultra")
    model_entry.pack(side="left")

    # Row 2: Release Date
    row2 = ctk.CTkFrame(fields_frame1, fg_color="transparent")
    row2.pack(fill="x", pady=5)

    ctk.CTkLabel(row2, text="Release Date:", font=("Segoe UI", 13), text_color=colors["text"], width=100, anchor="w").pack(side="left")
    release_var = ctk.StringVar(value=str(date.today()))
    ctk.CTkEntry(row2, textvariable=release_var, width=250, fg_color=colors["bg_light"],
                 border_color=colors["border"], placeholder_text="YYYY-MM-DD").pack(side="left")

    # ── SPECS SECTION ──
    section2 = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    section2.pack(fill="x", padx=20, pady=8)

    ctk.CTkLabel(section2, text="⚙️ Specifications", font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 10))

    fields_frame2 = ctk.CTkFrame(section2, fg_color="transparent")
    fields_frame2.pack(fill="x", padx=20, pady=(0, 15))

    spec_vars = {}
    spec_fields = [
        ("Processor", "e.g. Snapdragon 8 Gen 3"),
        ("RAM", "e.g. 8GB"),
        ("Storage", "e.g. 128GB, 256GB, 512GB"),
        ("Display", "e.g. 6.7 inch AMOLED, 2400x1080, 120Hz"),
        ("Battery", "e.g. 5000 mAh Li-Po"),
        ("Charging", "e.g. USB-C, 67W fast, 15W wireless"),
        ("Cameras", "e.g. 50MP + 12MP + 8MP rear, 32MP front"),
        ("Security", "e.g. Fingerprint (under display), Face Unlock"),
        ("Connectivity", "e.g. 5G, WiFi 6, Bluetooth 5.3, NFC"),
        ("OS", "e.g. Android 14, One UI 6.1"),
    ]

    for label, placeholder in spec_fields:
        row = ctk.CTkFrame(fields_frame2, fg_color="transparent")
        row.pack(fill="x", pady=3)

        ctk.CTkLabel(row, text=f"{label}:", font=("Segoe UI", 12), text_color=colors["text"],
                     width=110, anchor="w").pack(side="left")
        var = ctk.StringVar()
        ctk.CTkEntry(row, textvariable=var, width=600, fg_color=colors["bg_light"],
                     border_color=colors["border"], placeholder_text=placeholder).pack(side="left")
        spec_vars[label.lower()] = var

    # ── COMPONENTS SECTION ──
    section3 = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    section3.pack(fill="x", padx=20, pady=8)

    ctk.CTkLabel(section3, text="🔧 Components (Optional - add later)", font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))
    ctk.CTkLabel(section3, text="You can add components after creating the device, or they'll be detected automatically via hardware board.",
                 font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 5))

    components_list = []

    comp_container = ctk.CTkFrame(section3, fg_color="transparent")
    comp_container.pack(fill="x", padx=20, pady=5)

    def add_component_row():
        """Add a new component input row"""
        comp_frame = ctk.CTkFrame(comp_container, fg_color=colors["bg_light"], corner_radius=8)
        comp_frame.pack(fill="x", pady=3)

        comp_data = {}

        r1 = ctk.CTkFrame(comp_frame, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=(8, 3))

        ctk.CTkLabel(r1, text="Name:", width=80, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        comp_data["name"] = ctk.StringVar()
        ctk.CTkEntry(r1, textvariable=comp_data["name"], width=200, fg_color=colors["bg_dark"],
                     placeholder_text="e.g. U1 - Power IC").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(r1, text="Type:", width=50, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        comp_data["type"] = ctk.StringVar()
        ctk.CTkComboBox(r1, values=["PMIC", "SoC", "RAM", "Storage", "Charging IC", "Display IC",
                                     "Audio IC", "WiFi/BT", "Modem", "Connector", "Capacitor",
                                     "Resistor", "Other"],
                        variable=comp_data["type"], width=150, fg_color=colors["bg_dark"]).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(r1, text="Part#:", width=50, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        comp_data["part_number"] = ctk.StringVar()
        ctk.CTkEntry(r1, textvariable=comp_data["part_number"], width=150, fg_color=colors["bg_dark"],
                     placeholder_text="Part number").pack(side="left")

        r2 = ctk.CTkFrame(comp_frame, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=(3, 8))

        ctk.CTkLabel(r2, text="Location:", width=80, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        comp_data["location"] = ctk.StringVar()
        ctk.CTkEntry(r2, textvariable=comp_data["location"], width=200, fg_color=colors["bg_dark"],
                     placeholder_text="e.g. Top-left near battery").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(r2, text="Voltage:", width=60, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        comp_data["voltage"] = ctk.StringVar()
        ctk.CTkEntry(r2, textvariable=comp_data["voltage"], width=100, fg_color=colors["bg_dark"],
                     placeholder_text="e.g. 3.7V").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(r2, text="Test Point:", width=80, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        comp_data["test_point"] = ctk.StringVar()
        ctk.CTkEntry(r2, textvariable=comp_data["test_point"], width=100, fg_color=colors["bg_dark"],
                     placeholder_text="e.g. TP101").pack(side="left")

        def remove_comp():
            comp_frame.destroy()
            components_list.remove(comp_data)

        ctk.CTkButton(r2, text="✕", width=30, height=28, fg_color=colors["accent"],
                      hover_color="#ff0000", command=remove_comp).pack(side="right", padx=5)

        components_list.append(comp_data)

    add_comp_btn = ctk.CTkButton(section3, text="+ Add Component", width=180, height=35,
                                  fg_color=colors["info"], hover_color=colors["accent"],
                                  font=("Segoe UI", 12, "bold"), command=add_component_row)
    add_comp_btn.pack(anchor="w", padx=20, pady=(5, 15))

    # ── TEST POINTS SECTION ──
    section4 = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    section4.pack(fill="x", padx=20, pady=8)

    ctk.CTkLabel(section4, text="⚡ Test Points (Optional)", font=("Segoe UI", 16, "bold"),
                 text_color=colors["accent"]).pack(anchor="w", padx=20, pady=(15, 5))

    tp_list = []
    tp_container = ctk.CTkFrame(section4, fg_color="transparent")
    tp_container.pack(fill="x", padx=20, pady=5)

    def add_test_point_row():
        tp_frame = ctk.CTkFrame(tp_container, fg_color=colors["bg_light"], corner_radius=8)
        tp_frame.pack(fill="x", pady=3)

        tp_data = {}
        row = ctk.CTkFrame(tp_frame, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(row, text="Name:", width=50, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        tp_data["name"] = ctk.StringVar()
        ctk.CTkEntry(row, textvariable=tp_data["name"], width=120, fg_color=colors["bg_dark"],
                     placeholder_text="TP_VBAT").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row, text="Voltage:", width=60, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        tp_data["voltage"] = ctk.StringVar()
        ctk.CTkEntry(row, textvariable=tp_data["voltage"], width=100, fg_color=colors["bg_dark"],
                     placeholder_text="3.7-4.2V").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row, text="Description:", width=80, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        tp_data["description"] = ctk.StringVar()
        ctk.CTkEntry(row, textvariable=tp_data["description"], width=200, fg_color=colors["bg_dark"],
                     placeholder_text="Battery voltage").pack(side="left", padx=(0, 10))

        ctk.CTkLabel(row, text="Location:", width=60, anchor="w", font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left")
        tp_data["location"] = ctk.StringVar()
        ctk.CTkEntry(row, textvariable=tp_data["location"], width=150, fg_color=colors["bg_dark"],
                     placeholder_text="Near battery").pack(side="left")

        def remove_tp():
            tp_frame.destroy()
            tp_list.remove(tp_data)

        ctk.CTkButton(row, text="✕", width=30, height=28, fg_color=colors["accent"],
                      hover_color="#ff0000", command=remove_tp).pack(side="right", padx=5)

        tp_list.append(tp_data)

    ctk.CTkButton(section4, text="+ Add Test Point", width=180, height=35,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 12, "bold"), command=add_test_point_row).pack(anchor="w", padx=20, pady=(5, 15))

    # ── SAVE BUTTON ──
    def save_device():
        brand = brand_var.get().strip()
        model = model_var.get().strip()

        if not brand or not model:
            # Show error
            error_label.configure(text="Brand and Model are required!", text_color=colors["accent"])
            return

        # Generate ID
        device_id = f"{brand.lower()}_{model.lower().replace(' ', '_').replace('(', '').replace(')', '')}"

        # Check duplicate
        for d in app.devices:
            if d.get("id") == device_id:
                error_label.configure(text=f"Device '{brand} {model}' already exists!", text_color=colors["accent"])
                return

        # Build specs dict
        specs = {}
        for key, var in spec_vars.items():
            val = var.get().strip()
            if val:
                specs[key] = val

        # Build components list
        comps = []
        for comp_data in components_list:
            comp = {}
            for key, var in comp_data.items():
                val = var.get().strip()
                if val:
                    comp[key] = val
            if comp.get("name"):
                comps.append(comp)

        # Build test points list
        tps = []
        for tp_data in tp_list:
            tp = {}
            for key, var in tp_data.items():
                val = var.get().strip()
                if val:
                    tp[key] = val
            if tp.get("name"):
                tps.append(tp)

        # Create device object
        device = {
            "id": device_id,
            "brand": brand,
            "model": model,
            "release_date": release_var.get().strip(),
            "specs": specs,
            "components": comps,
            "test_points": tps,
            "procedures": []
        }

        # Save to database
        app.add_device_to_db(device)

        # Show success and navigate to device detail
        app.show_device_detail(device)

    # Error/success label
    error_label = ctk.CTkLabel(app.content, text="", font=("Segoe UI", 13, "bold"))
    error_label.pack(pady=(10, 0))

    # Buttons row
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=15)

    ctk.CTkButton(btn_frame, text="💾 Save Device", width=200, height=50,
                  fg_color=colors["success"], hover_color="#27ae60",
                  font=("Segoe UI", 16, "bold"), command=save_device).pack(side="left", padx=5)

    ctk.CTkButton(btn_frame, text="🔌 Auto-Detect Instead", width=200, height=50,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 14), command=app.show_hw_detect).pack(side="left", padx=5)

    ctk.CTkButton(btn_frame, text="Cancel", width=120, height=50,
                  fg_color=colors["bg_light"], hover_color=colors["accent"],
                  font=("Segoe UI", 14), text_color=colors["text_dim"],
                  command=app.show_dashboard).pack(side="left", padx=5)

    app.update_status("Add Device • Fill in device details or use Auto-Detect")
