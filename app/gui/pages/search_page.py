import customtkinter as ctk
import time


def render_search(app, initial_query=None):
    """Render the search page with real-time filtering and grouped results."""
    colors = app.colors
    devices = app.devices

    # Page title
    ctk.CTkLabel(
        app.content, text="Search", font=("Segoe UI", 24, "bold"),
        text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Search across devices, components, test points, and repair procedures",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 15))

    # --- search bar -----------------------------------------------------------
    search_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    search_frame.pack(fill="x", padx=20, pady=(0, 10))

    inner = ctk.CTkFrame(search_frame, fg_color="transparent")
    inner.pack(fill="x", padx=20, pady=15)

    search_var = ctk.StringVar(value=initial_query or "")
    search_entry = ctk.CTkEntry(
        inner, textvariable=search_var, width=600, height=44,
        placeholder_text="Type to search devices, components, procedures...",
        font=("Segoe UI", 14),
        fg_color=colors["bg_light"], border_color=colors["border"],
    )
    search_entry.pack(side="left", padx=(0, 10))
    search_entry.focus_set()

    clear_btn = ctk.CTkButton(
        inner, text="Clear", width=80, height=44,
        fg_color=colors["bg_light"], hover_color=colors["accent"],
        text_color=colors["text_dim"], font=("Segoe UI", 13),
        command=lambda: (search_var.set(""), _do_search()),
    )
    clear_btn.pack(side="left")

    # Stats label
    stats_label = ctk.CTkLabel(
        app.content, text="", font=("Segoe UI", 12), text_color=colors["text_dim"],
    )
    stats_label.pack(anchor="w", padx=20, pady=(0, 5))

    # Results container
    results_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    results_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

    # ---- helpers -------------------------------------------------------------

    def _get_procedures(device):
        """Return procedures list handling both key names."""
        return device.get("procedures", device.get("repair_procedures", []))

    def _match(text, query_lower):
        return query_lower in str(text).lower()

    def _search(query):
        """Return grouped results: devices, components, procedures."""
        q = query.lower().strip()
        if not q:
            return [], [], []

        device_results = []
        component_results = []
        procedure_results = []

        for device in devices:
            model = device.get("model", "")
            brand = device.get("brand", "")
            specs = device.get("specs", {})
            components = device.get("components", [])
            procedures = _get_procedures(device)
            device_label = f"{brand} {model}"

            # Device-level match
            device_matched = False
            if _match(model, q) or _match(brand, q):
                device_matched = True
            # Specs match
            for val in specs.values():
                if _match(val, q):
                    device_matched = True
                    break
            if device_matched:
                device_results.append(device)

            # Component match
            for comp in components:
                fields = [
                    comp.get("name", ""),
                    comp.get("type", ""),
                    comp.get("part_number", ""),
                    comp.get("location", ""),
                ]
                symptoms = comp.get("failure_symptoms", [])
                all_text = " ".join(fields) + " " + " ".join(symptoms)
                if _match(all_text, q):
                    component_results.append({
                        "device": device,
                        "device_label": device_label,
                        "component": comp,
                    })

            # Procedure match
            for proc in procedures:
                issue = proc.get("issue", "")
                steps = proc.get("steps", [])
                step_text = " ".join(
                    s.get("action", s) if isinstance(s, dict) else str(s)
                    for s in steps
                )
                tools = " ".join(proc.get("tools_required", []))
                all_text = f"{issue} {step_text} {tools}"
                if _match(all_text, q):
                    procedure_results.append({
                        "device": device,
                        "device_label": device_label,
                        "procedure": proc,
                    })

        return device_results, component_results, procedure_results

    def _clear_results():
        for w in results_frame.winfo_children():
            w.destroy()

    def _do_search(*_args):
        query = search_var.get().strip()
        _clear_results()

        if not query:
            stats_label.configure(text="")
            ctk.CTkLabel(
                results_frame,
                text="Start typing to search across all device data.",
                font=("Segoe UI", 14), text_color=colors["text_dim"],
            ).pack(pady=40)
            app.update_status("Search")
            return

        t0 = time.perf_counter()
        dev_res, comp_res, proc_res = _search(query)
        elapsed = time.perf_counter() - t0

        total = len(dev_res) + len(comp_res) + len(proc_res)
        stats_label.configure(
            text=f"{total} result{'s' if total != 1 else ''} found in {elapsed * 1000:.1f} ms  "
                 f"({len(dev_res)} devices, {len(comp_res)} components, {len(proc_res)} procedures)"
        )

        if total == 0:
            ctk.CTkLabel(
                results_frame,
                text=f"No results found for \"{query}\"",
                font=("Segoe UI", 15), text_color=colors["text_dim"],
            ).pack(pady=40)
            app.update_status(f"Search \"{query}\" - no results")
            return

        # --- Devices group ---
        if dev_res:
            _render_group_header(results_frame, f"Devices ({len(dev_res)})", colors)
            for device in dev_res[:30]:
                _render_device_result(results_frame, device, app, colors)

        # --- Components group ---
        if comp_res:
            _render_group_header(results_frame, f"Components ({len(comp_res)})", colors)
            for item in comp_res[:30]:
                _render_component_result(results_frame, item, app, colors)

        # --- Procedures group ---
        if proc_res:
            _render_group_header(results_frame, f"Procedures ({len(proc_res)})", colors)
            for item in proc_res[:30]:
                _render_procedure_result(results_frame, item, app, colors)

        app.update_status(f"Search \"{query}\" - {total} results in {elapsed * 1000:.1f} ms")

    # Bind real-time search
    search_entry.bind("<KeyRelease>", _do_search)

    # Run initial search if a query was passed
    if initial_query:
        _do_search()


# ---------- rendering helpers -------------------------------------------------

def _render_group_header(parent, text, colors):
    header = ctk.CTkFrame(parent, fg_color="transparent")
    header.pack(fill="x", pady=(15, 5))
    ctk.CTkLabel(
        header, text=text, font=("Segoe UI", 16, "bold"),
        text_color=colors["accent"],
    ).pack(anchor="w")
    ctk.CTkFrame(header, height=2, fg_color=colors["border"]).pack(fill="x", pady=(3, 0))


def _render_device_result(parent, device, app, colors):
    card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10, height=70)
    card.pack(fill="x", pady=3)
    card.pack_propagate(False)

    left = ctk.CTkFrame(card, fg_color="transparent")
    left.pack(side="left", fill="y", padx=15, pady=10)

    ctk.CTkLabel(
        left, text=device.get("model", "Unknown"),
        font=("Segoe UI", 14, "bold"), text_color=colors["text"], anchor="w",
    ).pack(anchor="w")

    specs = device.get("specs", {})
    sub = f"{device.get('brand', '')}  |  {specs.get('processor', '')}  |  {specs.get('ram', '')}"
    ctk.CTkLabel(
        left, text=sub, font=("Segoe UI", 11), text_color=colors["text_dim"], anchor="w",
    ).pack(anchor="w")

    ctk.CTkButton(
        card, text="View Details", width=110, height=32,
        fg_color=colors["accent"], hover_color=colors["accent_hover"],
        font=("Segoe UI", 12, "bold"), corner_radius=8,
        command=lambda d=device: app.show_device_detail(d),
    ).pack(side="right", padx=15)


def _render_component_result(parent, item, app, colors):
    comp = item["component"]
    device = item["device"]

    card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10)
    card.pack(fill="x", pady=3)

    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="x", padx=15, pady=10)

    top = ctk.CTkFrame(inner, fg_color="transparent")
    top.pack(fill="x")

    ctk.CTkLabel(
        top, text=comp.get("name", "Unknown"),
        font=("Segoe UI", 13, "bold"), text_color=colors["info"],
    ).pack(side="left")
    ctk.CTkLabel(
        top, text=f"  [{comp.get('type', '')}]",
        font=("Segoe UI", 11), text_color=colors["text_dim"],
    ).pack(side="left")

    ctk.CTkButton(
        top, text=f"Go to {item['device_label']}", width=160, height=28,
        fg_color=colors["bg_light"], hover_color=colors["accent"],
        text_color=colors["text_dim"], font=("Segoe UI", 11),
        command=lambda d=device: app.show_device_detail(d),
    ).pack(side="right")

    details = []
    if comp.get("part_number"):
        details.append(f"Part#: {comp['part_number']}")
    if comp.get("location"):
        details.append(comp["location"])
    symptoms = comp.get("failure_symptoms", [])
    if symptoms:
        details.append(f"Symptoms: {', '.join(symptoms)}")
    if details:
        ctk.CTkLabel(
            inner, text="  |  ".join(details),
            font=("Segoe UI", 11), text_color=colors["text_dim"],
            wraplength=750, anchor="w",
        ).pack(anchor="w", pady=(3, 0))


def _render_procedure_result(parent, item, app, colors):
    proc = item["procedure"]
    device = item["device"]

    card = ctk.CTkFrame(parent, fg_color=colors["bg_card"], corner_radius=10)
    card.pack(fill="x", pady=3)

    inner = ctk.CTkFrame(card, fg_color="transparent")
    inner.pack(fill="x", padx=15, pady=10)

    top = ctk.CTkFrame(inner, fg_color="transparent")
    top.pack(fill="x")

    ctk.CTkLabel(
        top, text=proc.get("issue", "Unknown Issue"),
        font=("Segoe UI", 13, "bold"), text_color=colors["warning"],
    ).pack(side="left")

    difficulty = proc.get("difficulty", "")
    diff_colors = {
        "easy": colors["success"], "intermediate": colors["warning"],
        "advanced": colors["accent"], "expert": "#ff0000",
    }
    if difficulty:
        ctk.CTkLabel(
            top, text=f"  [{difficulty.upper()}]",
            font=("Segoe UI", 11, "bold"),
            text_color=diff_colors.get(difficulty.lower(), colors["text_dim"]),
        ).pack(side="left")

    ctk.CTkButton(
        top, text=f"Go to {item['device_label']}", width=160, height=28,
        fg_color=colors["bg_light"], hover_color=colors["accent"],
        text_color=colors["text_dim"], font=("Segoe UI", 11),
        command=lambda d=device: app.show_device_detail(d),
    ).pack(side="right")

    tools = proc.get("tools_required", [])
    if tools:
        ctk.CTkLabel(
            inner, text=f"Tools: {', '.join(tools)}",
            font=("Segoe UI", 11), text_color=colors["text_dim"], anchor="w",
        ).pack(anchor="w", pady=(3, 0))
