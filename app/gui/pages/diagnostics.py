import customtkinter as ctk
import random

# ---------------------------------------------------------------------------
# Symptom categories and their specific symptoms
# ---------------------------------------------------------------------------
SYMPTOM_CATEGORIES = {
    "Power Issues": [
        "Won't turn on", "Sudden shutdown", "Restart loop",
        "Battery drain", "Overheating",
    ],
    "Display Issues": [
        "Black screen", "Flickering", "Dead pixels",
        "Touch not responding", "Ghost touch", "Backlight issues",
    ],
    "Charging Issues": [
        "Not charging", "Slow charging", "Charges then stops",
        "Port loose", "Wireless charging not working",
    ],
    "Audio Issues": [
        "No sound", "Distorted sound", "Earpiece not working",
        "Microphone not working", "Speaker crackling",
    ],
    "Network Issues": [
        "No WiFi", "No Bluetooth", "No cellular",
        "Weak signal", "SIM not detected",
    ],
    "Software Issues": [
        "Boot loop", "Stuck on logo", "Factory reset needed",
        "Firmware corrupt",
    ],
}

# Maps symptoms to component types that are likely causes
_SYMPTOM_COMPONENT_MAP = {
    "Won't turn on":        ["PMIC", "Charge Controller", "Connector"],
    "Sudden shutdown":      ["PMIC", "Storage"],
    "Restart loop":         ["PMIC", "Storage"],
    "Battery drain":        ["PMIC", "Connectivity"],
    "Overheating":          ["PMIC", "Charge Controller"],
    "Black screen":         ["Connector", "PMIC"],
    "Flickering":           ["Connector"],
    "Dead pixels":          ["Connector"],
    "Touch not responding": ["Connector"],
    "Ghost touch":          ["Connector"],
    "Backlight issues":     ["Connector", "PMIC"],
    "Not charging":         ["Charge Controller", "Connector"],
    "Slow charging":        ["Charge Controller"],
    "Charges then stops":   ["Charge Controller", "PMIC"],
    "Port loose":           ["Connector", "Charge Controller"],
    "Wireless charging not working": ["Charge Controller", "PMIC"],
    "No sound":             ["Connector", "PMIC"],
    "Distorted sound":      ["Connector"],
    "Earpiece not working": ["Connector"],
    "Microphone not working": ["Connector"],
    "Speaker crackling":    ["Connector"],
    "No WiFi":              ["Connectivity"],
    "No Bluetooth":         ["Connectivity"],
    "No cellular":          ["Connectivity", "Connector"],
    "Weak signal":          ["Connectivity"],
    "SIM not detected":     ["Connector", "Connectivity"],
    "Boot loop":            ["Storage", "PMIC"],
    "Stuck on logo":        ["Storage", "PMIC"],
    "Factory reset needed": ["Storage"],
    "Firmware corrupt":     ["Storage"],
}

# Keyword matching from symptom text to procedure issue text
_SYMPTOM_PROCEDURE_KEYWORDS = {
    "Won't turn on":        ["no power", "dead", "won't turn"],
    "Sudden shutdown":      ["shutdown", "power", "dead"],
    "Restart loop":         ["restart", "boot loop", "reboot"],
    "Battery drain":        ["battery", "drain", "power"],
    "Overheating":          ["overheat", "hot", "thermal"],
    "Black screen":         ["display", "screen", "no display", "black"],
    "Flickering":           ["display", "flicker", "screen"],
    "Dead pixels":          ["display", "pixel", "screen"],
    "Touch not responding": ["touch", "display", "screen"],
    "Ghost touch":          ["touch", "ghost", "display"],
    "Backlight issues":     ["backlight", "display", "screen"],
    "Not charging":         ["charg", "not charging", "usb"],
    "Slow charging":        ["charg", "slow"],
    "Charges then stops":   ["charg", "stop"],
    "Port loose":           ["port", "usb", "connector", "charg"],
    "Wireless charging not working": ["wireless", "charg"],
    "No sound":             ["audio", "sound", "speaker"],
    "Distorted sound":      ["audio", "sound", "distort"],
    "Earpiece not working": ["earpiece", "audio", "sound"],
    "Microphone not working": ["mic", "audio"],
    "Speaker crackling":    ["speaker", "crackl", "audio"],
    "No WiFi":              ["wi-fi", "wifi", "wlan"],
    "No Bluetooth":         ["bluetooth", "bt"],
    "No cellular":          ["cellular", "network", "signal", "modem"],
    "Weak signal":          ["signal", "network", "weak"],
    "SIM not detected":     ["sim", "network"],
    "Boot loop":            ["boot", "loop", "restart"],
    "Stuck on logo":        ["boot", "logo", "stuck"],
    "Factory reset needed": ["factory", "reset", "software"],
    "Firmware corrupt":     ["firmware", "corrupt", "flash"],
}


def _get_procedures(device):
    return device.get("procedures", device.get("repair_procedures", []))


def render_diagnostics(app):
    """Render the interactive diagnostic wizard."""
    colors = app.colors
    devices = app.devices

    # Page title
    ctk.CTkLabel(
        app.content, text="Diagnostics Wizard",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Step-by-step diagnostic tool to identify and resolve device issues",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 20))

    # Wizard container
    wizard = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    wizard.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # Step indicator bar
    step_bar = ctk.CTkFrame(wizard, fg_color=colors["bg_medium"], corner_radius=0, height=50)
    step_bar.pack(fill="x")
    step_bar.pack_propagate(False)

    step_labels = []
    step_names = ["1. Select Device", "2. Category", "3. Symptoms", "4. Results"]
    for i, name in enumerate(step_names):
        lbl = ctk.CTkLabel(
            step_bar, text=name, font=("Segoe UI", 13, "bold"),
            text_color=colors["text_dim"], width=180,
        )
        lbl.pack(side="left", padx=10, pady=10)
        step_labels.append(lbl)

    # Body frame where step content goes
    body = ctk.CTkFrame(wizard, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=20, pady=20)

    # Shared state
    state = {
        "current_step": 0,
        "device": None,
        "category": None,
        "symptoms": [],
    }

    def _highlight_step(idx):
        for i, lbl in enumerate(step_labels):
            if i < idx:
                lbl.configure(text_color=colors["success"])
            elif i == idx:
                lbl.configure(text_color=colors["accent"])
            else:
                lbl.configure(text_color=colors["text_dim"])

    def _clear_body():
        for w in body.winfo_children():
            w.destroy()

    # ---- STEP 1: Select device -----------------------------------------------
    def _step1():
        state["current_step"] = 0
        _highlight_step(0)
        _clear_body()

        ctk.CTkLabel(
            body, text="Step 1: Select the Device",
            font=("Segoe UI", 18, "bold"), text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 15))

        ctk.CTkLabel(
            body, text="Choose the device you want to diagnose:",
            font=("Segoe UI", 13), text_color=colors["text_dim"],
        ).pack(anchor="w", pady=(0, 10))

        device_names = [f"{d.get('brand', '')} {d.get('model', '')}" for d in devices]
        if not device_names:
            device_names = ["No devices loaded"]

        selected_var = ctk.StringVar(value=device_names[0] if device_names else "")

        menu = ctk.CTkOptionMenu(
            body, values=device_names, variable=selected_var,
            width=450, height=40, font=("Segoe UI", 13),
            fg_color=colors["bg_light"], button_color=colors["accent"],
            button_hover_color=colors["accent_hover"],
        )
        menu.pack(anchor="w", pady=(0, 20))

        def _next():
            name = selected_var.get()
            for d in devices:
                if f"{d.get('brand', '')} {d.get('model', '')}" == name:
                    state["device"] = d
                    break
            if state["device"]:
                _step2()

        ctk.CTkButton(
            body, text="Next  ->", width=140, height=40,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 14, "bold"), command=_next,
        ).pack(anchor="w")

    # ---- STEP 2: Select symptom category -------------------------------------
    def _step2():
        state["current_step"] = 1
        _highlight_step(1)
        _clear_body()

        device = state["device"]
        ctk.CTkLabel(
            body,
            text=f"Step 2: Select Symptom Category  ({device.get('brand', '')} {device.get('model', '')})",
            font=("Segoe UI", 18, "bold"), text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 15))

        ctk.CTkLabel(
            body, text="What type of issue is the device experiencing?",
            font=("Segoe UI", 13), text_color=colors["text_dim"],
        ).pack(anchor="w", pady=(0, 15))

        cat_icons = {
            "Power Issues": ("Power Issues", colors["accent"]),
            "Display Issues": ("Display Issues", colors["info"]),
            "Charging Issues": ("Charging Issues", colors["warning"]),
            "Audio Issues": ("Audio Issues", "#9b59b6"),
            "Network Issues": ("Network Issues", colors["success"]),
            "Software Issues": ("Software Issues", colors["text_dim"]),
        }

        grid = ctk.CTkFrame(body, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 20))

        row_frame = None
        for i, cat_name in enumerate(SYMPTOM_CATEGORIES):
            if i % 3 == 0:
                row_frame = ctk.CTkFrame(grid, fg_color="transparent")
                row_frame.pack(fill="x", pady=5)

            label, color = cat_icons.get(cat_name, (cat_name, colors["info"]))
            btn = ctk.CTkButton(
                row_frame, text=label, width=200, height=60,
                fg_color=colors["bg_light"], hover_color=color,
                text_color=colors["text"], font=("Segoe UI", 13, "bold"),
                corner_radius=10,
                command=lambda c=cat_name: _select_category(c),
            )
            btn.pack(side="left", padx=5)

        # Back button
        ctk.CTkButton(
            body, text="<-  Back", width=100, height=36,
            fg_color="transparent", hover_color=colors["bg_light"],
            text_color=colors["text_dim"], font=("Segoe UI", 12),
            command=_step1,
        ).pack(anchor="w", pady=(10, 0))

    def _select_category(category):
        state["category"] = category
        _step3()

    # ---- STEP 3: Select specific symptoms ------------------------------------
    def _step3():
        state["current_step"] = 2
        _highlight_step(2)
        _clear_body()

        category = state["category"]
        symptoms = SYMPTOM_CATEGORIES.get(category, [])

        ctk.CTkLabel(
            body, text=f"Step 3: Select Symptoms  -  {category}",
            font=("Segoe UI", 18, "bold"), text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(
            body, text="Check all symptoms that apply:",
            font=("Segoe UI", 13), text_color=colors["text_dim"],
        ).pack(anchor="w", pady=(0, 15))

        check_vars = {}
        for symptom in symptoms:
            var = ctk.BooleanVar(value=False)
            check_vars[symptom] = var
            cb = ctk.CTkCheckBox(
                body, text=symptom, variable=var,
                font=("Segoe UI", 14), text_color=colors["text"],
                fg_color=colors["accent"], hover_color=colors["accent_hover"],
                border_color=colors["border"], checkmark_color="#fff",
            )
            cb.pack(anchor="w", pady=4)

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(20, 0))

        ctk.CTkButton(
            btn_row, text="<-  Back", width=100, height=36,
            fg_color="transparent", hover_color=colors["bg_light"],
            text_color=colors["text_dim"], font=("Segoe UI", 12),
            command=_step2,
        ).pack(side="left", padx=(0, 10))

        def _run_diag():
            selected = [s for s, v in check_vars.items() if v.get()]
            if not selected:
                # Select all if none chosen
                selected = symptoms[:1]
            state["symptoms"] = selected
            _step4()

        ctk.CTkButton(
            btn_row, text="Run Diagnostics  ->", width=180, height=40,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 14, "bold"), command=_run_diag,
        ).pack(side="left")

    # ---- STEP 4: Show diagnostic results -------------------------------------
    def _step4():
        state["current_step"] = 3
        _highlight_step(3)
        _clear_body()

        device = state["device"]
        symptoms = state["symptoms"]
        components = device.get("components", [])
        procedures = _get_procedures(device)

        ctk.CTkLabel(
            body, text="Diagnostic Results",
            font=("Segoe UI", 18, "bold"), text_color=colors["text"],
        ).pack(anchor="w", pady=(0, 5))
        ctk.CTkLabel(
            body,
            text=f"Device: {device.get('brand', '')} {device.get('model', '')}  |  "
                 f"Symptoms: {', '.join(symptoms)}",
            font=("Segoe UI", 12), text_color=colors["text_dim"],
        ).pack(anchor="w", pady=(0, 15))

        # -- Likely causes ranked by confidence --------------------------------
        causes_frame = ctk.CTkFrame(body, fg_color=colors["bg_light"], corner_radius=10)
        causes_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            causes_frame, text="Likely Causes",
            font=("Segoe UI", 15, "bold"), text_color=colors["accent"],
        ).pack(anchor="w", padx=15, pady=(12, 8))

        causes = _analyze_causes(symptoms, components)
        if not causes:
            ctk.CTkLabel(
                causes_frame, text="No specific component causes identified for this device.",
                font=("Segoe UI", 12), text_color=colors["text_dim"],
            ).pack(padx=15, pady=(0, 12))
        else:
            for comp_name, confidence, comp_data in causes:
                row = ctk.CTkFrame(causes_frame, fg_color="transparent")
                row.pack(fill="x", padx=15, pady=3)

                # Severity color
                if confidence >= 80:
                    sev_color = "#ff4444"
                elif confidence >= 50:
                    sev_color = colors["warning"]
                else:
                    sev_color = colors["info"]

                sev_dot = ctk.CTkLabel(
                    row, text="", width=12, height=12, fg_color=sev_color,
                    corner_radius=6,
                )
                sev_dot.pack(side="left", padx=(0, 8))

                ctk.CTkLabel(
                    row, text=comp_name, font=("Segoe UI", 13, "bold"),
                    text_color=colors["text"], width=250, anchor="w",
                ).pack(side="left")

                bar = ctk.CTkProgressBar(
                    row, width=200, height=16,
                    progress_color=sev_color, fg_color=colors["bg_medium"],
                )
                bar.set(confidence / 100.0)
                bar.pack(side="left", padx=10)

                ctk.CTkLabel(
                    row, text=f"{confidence}%", font=("Segoe UI", 12, "bold"),
                    text_color=sev_color,
                ).pack(side="left")

                if comp_data.get("location"):
                    ctk.CTkLabel(
                        row, text=f"  ({comp_data.get('location', '')})",
                        font=("Segoe UI", 11), text_color=colors["text_dim"],
                    ).pack(side="left", padx=(5, 0))

            ctk.CTkFrame(causes_frame, fg_color="transparent", height=10).pack()

        # -- Recommended test points -------------------------------------------
        tp_frame = ctk.CTkFrame(body, fg_color=colors["bg_light"], corner_radius=10)
        tp_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            tp_frame, text="Recommended Test Points",
            font=("Segoe UI", 15, "bold"), text_color=colors["info"],
        ).pack(anchor="w", padx=15, pady=(12, 8))

        test_points = device.get("test_points", [])
        relevant_tps = _get_relevant_test_points(causes, test_points, components)
        if not relevant_tps:
            ctk.CTkLabel(
                tp_frame, text="No specific test points identified. Check all voltage rails.",
                font=("Segoe UI", 12), text_color=colors["text_dim"],
            ).pack(padx=15, pady=(0, 12))
        else:
            for tp in relevant_tps:
                tp_row = ctk.CTkFrame(tp_frame, fg_color="transparent")
                tp_row.pack(fill="x", padx=15, pady=2)
                ctk.CTkLabel(
                    tp_row, text=tp.get("name", ""),
                    font=("Segoe UI", 12, "bold"), text_color=colors["text"],
                ).pack(side="left")
                ctk.CTkLabel(
                    tp_row,
                    text=f"   Expected: {tp.get('voltage', '?')}V  |  {tp.get('description', '')}  |  {tp.get('location', '')}",
                    font=("Segoe UI", 11), text_color=colors["text_dim"],
                ).pack(side="left", padx=(5, 0))
            ctk.CTkFrame(tp_frame, fg_color="transparent", height=10).pack()

        # -- Suggested repair procedures ---------------------------------------
        proc_frame = ctk.CTkFrame(body, fg_color=colors["bg_light"], corner_radius=10)
        proc_frame.pack(fill="x", pady=(0, 15))

        ctk.CTkLabel(
            proc_frame, text="Suggested Repair Procedures",
            font=("Segoe UI", 15, "bold"), text_color=colors["success"],
        ).pack(anchor="w", padx=15, pady=(12, 8))

        matched_procs = _match_procedures(symptoms, procedures)
        if not matched_procs:
            ctk.CTkLabel(
                proc_frame,
                text="No specific procedures found for these symptoms. Refer to general repair guides.",
                font=("Segoe UI", 12), text_color=colors["text_dim"],
            ).pack(padx=15, pady=(0, 12))
        else:
            for proc in matched_procs:
                p_card = ctk.CTkFrame(proc_frame, fg_color=colors["bg_card"], corner_radius=8)
                p_card.pack(fill="x", padx=15, pady=5)

                p_header = ctk.CTkFrame(p_card, fg_color="transparent")
                p_header.pack(fill="x", padx=12, pady=(10, 5))

                ctk.CTkLabel(
                    p_header, text=proc.get("issue", ""),
                    font=("Segoe UI", 13, "bold"), text_color=colors["accent"],
                ).pack(side="left")

                difficulty = proc.get("difficulty", "Unknown")
                diff_colors = {
                    "easy": colors["success"], "intermediate": colors["warning"],
                    "advanced": colors["accent"], "expert": "#ff0000",
                }
                d_color = diff_colors.get(difficulty.lower(), colors["text_dim"])
                ctk.CTkLabel(
                    p_header, text=f"  Difficulty: {difficulty}",
                    font=("Segoe UI", 11, "bold"), text_color=d_color,
                ).pack(side="left")

                tools = proc.get("tools_required", [])
                if tools:
                    ctk.CTkLabel(
                        p_card, text=f"Tools: {', '.join(tools)}",
                        font=("Segoe UI", 11), text_color=colors["text_dim"],
                    ).pack(anchor="w", padx=12, pady=(0, 5))

                steps = proc.get("steps", [])
                for s in steps:
                    action = s.get("action", s) if isinstance(s, dict) else str(s)
                    step_num = s.get("step", "") if isinstance(s, dict) else ""
                    ctk.CTkLabel(
                        p_card,
                        text=f"  {step_num}. {action}" if step_num else f"  - {action}",
                        font=("Segoe UI", 11), text_color=colors["text"],
                        anchor="w", wraplength=700,
                    ).pack(anchor="w", padx=12, pady=1)

                ctk.CTkFrame(p_card, fg_color="transparent", height=8).pack()

            ctk.CTkFrame(proc_frame, fg_color="transparent", height=10).pack()

        # -- Buttons -----------------------------------------------------------
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(anchor="w", pady=(10, 0))

        ctk.CTkButton(
            btn_row, text="<-  Back to Symptoms", width=160, height=36,
            fg_color="transparent", hover_color=colors["bg_light"],
            text_color=colors["text_dim"], font=("Segoe UI", 12),
            command=_step3,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="View Device Details", width=160, height=40,
            fg_color=colors["info"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 13, "bold"),
            command=lambda: app.show_device_detail(device),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="New Diagnosis", width=140, height=40,
            fg_color=colors["accent"], hover_color=colors["accent_hover"],
            font=("Segoe UI", 13, "bold"), command=_step1,
        ).pack(side="left")

        app.update_status(
            f"Diagnostics complete - {len(causes)} likely causes, "
            f"{len(matched_procs)} suggested procedures"
        )

    # Start the wizard
    _step1()
    app.update_status("Diagnostics Wizard - Step 1: Select a device")


# ---------------------------------------------------------------------------
# Diagnostic analysis helpers
# ---------------------------------------------------------------------------

def _analyze_causes(symptoms, components):
    """
    Match selected symptoms against device components and return a list of
    (component_name, confidence_pct, component_data) sorted by confidence.
    """
    comp_scores = {}  # comp name -> (total_score, comp_data)

    for symptom in symptoms:
        target_types = _SYMPTOM_COMPONENT_MAP.get(symptom, [])
        for comp in components:
            ctype = comp.get("type", "")
            cname = comp.get("name", "Unknown")
            failure_symptoms = [s.lower() for s in comp.get("failure_symptoms", [])]
            symptom_lower = symptom.lower()

            score = 0
            # Direct match against component failure_symptoms
            for fs in failure_symptoms:
                if symptom_lower in fs or fs in symptom_lower:
                    score += 40
                    break
                # Partial keyword match
                for word in symptom_lower.split():
                    if len(word) > 3 and word in fs:
                        score += 20
                        break

            # Type-based match
            if ctype in target_types:
                score += 30

            if score > 0:
                prev_score, _ = comp_scores.get(cname, (0, comp))
                comp_scores[cname] = (prev_score + score, comp)

    if not comp_scores:
        return []

    # Normalize to max 95
    max_raw = max(s for s, _ in comp_scores.values())
    results = []
    for cname, (raw, comp_data) in comp_scores.items():
        pct = min(int((raw / max_raw) * 95), 95)
        # Add small random jitter so scores aren't all identical
        pct = max(15, min(95, pct + random.randint(-3, 3)))
        results.append((cname, pct, comp_data))

    results.sort(key=lambda x: -x[1])
    return results


def _get_relevant_test_points(causes, test_points, components):
    """Return test points related to the likely-cause components."""
    # Gather test point names referenced by flagged components
    relevant_tp_names = set()
    for _, _, comp_data in causes:
        tp_ref = comp_data.get("test_point", "")
        if tp_ref:
            relevant_tp_names.add(tp_ref.lower())

    if not relevant_tp_names:
        return test_points[:3]  # fallback: return first few

    matched = []
    for tp in test_points:
        tp_name = tp.get("name", "").lower()
        for ref in relevant_tp_names:
            if ref in tp_name:
                matched.append(tp)
                break

    return matched if matched else test_points[:3]


def _match_procedures(symptoms, procedures):
    """Match selected symptoms to relevant repair procedures."""
    proc_scores = {}
    for symptom in symptoms:
        keywords = _SYMPTOM_PROCEDURE_KEYWORDS.get(symptom, [symptom.lower()])
        for proc in procedures:
            issue = proc.get("issue", "").lower()
            pid = id(proc)
            score = proc_scores.get(pid, (0, proc))[0]
            for kw in keywords:
                if kw in issue:
                    score += 10
                    break
            proc_scores[pid] = (score, proc)

    matched = [(s, p) for s, p in proc_scores.values() if s > 0]
    matched.sort(key=lambda x: -x[0])
    return [p for _, p in matched]
