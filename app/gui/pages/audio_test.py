import customtkinter as ctk
import threading
from app.gui.ui_utils import (
    get_line_tag, setup_report_tags, append_live, append_live_lines,
    safe_after, copy_report_to_clipboard, save_report_to_file,
)


def render_audio_test(app):
    """Audio Testing page — codec, speaker, microphone, headphone jack, amplifier IC diagnostics.
    Shows detections LIVE as they happen — real-time append with color-coded output."""
    colors = app.colors

    # ── Title ──
    ctk.CTkLabel(app.content, text="\U0001f50a Audio Subsystem Testing",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Audio codec, speaker, microphone, headphone jack, amplifier IC diagnostics",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Info card ──
    info = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    info.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(info, text="\U0001f50d Audio Testing Can Detect:",
                 font=("Segoe UI", 16, "bold"), text_color=colors["info"]).pack(anchor="w", padx=20, pady=(15, 8))

    detect_items = [
        "\u2705 Audio Codec \u2014 IC identification, sample rate, bit depth, channels",
        "\u2705 Speaker \u2014 Count, amplifier IC, impedance, status",
        "\u2705 Microphone \u2014 Primary/secondary/noise-cancel detection",
        "\u2705 Headphone Jack \u2014 3.5mm/USB-C presence, DAC chip detection",
        "\u2705 Audio Routes \u2014 Active output/input paths",
        "\u2705 Volume Levels \u2014 Current stream volumes",
        "\u2705 IC Database \u2014 Qualcomm WCD, Cirrus Logic, TI, Maxim, NXP",
    ]
    for item in detect_items:
        ctk.CTkLabel(info, text=f"  {item}", font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20, pady=1)
    ctk.CTkFrame(info, fg_color="transparent", height=12).pack()

    # ── Overall Health Badge ──
    badge_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12, height=55)
    badge_frame.pack(fill="x", padx=20, pady=(0, 10))
    badge_frame.pack_propagate(False)
    badge_inner = ctk.CTkFrame(badge_frame, fg_color="transparent")
    badge_inner.pack(fill="x", padx=20, pady=10)
    ctk.CTkLabel(badge_inner, text="Overall Audio Health:",
                 font=("Segoe UI", 14, "bold"), text_color=colors["text"]).pack(side="left")
    health_badge = ctk.CTkLabel(badge_inner, text="  \u23f8 Not Tested",
                                 font=("Segoe UI", 14, "bold"), text_color=colors["text_dim"])
    health_badge.pack(side="left", padx=(10, 0))

    # ── Progress bar + message ──
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"], fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 10))

    # ── Buttons row ──
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 10))

    running = {"value": False}

    # ── Result cards container ──
    cards_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    cards_frame.pack(fill="x", padx=20, pady=(0, 10))

    cards_left = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_left.pack(side="left", fill="both", expand=True, padx=(0, 5))
    cards_right = ctk.CTkFrame(cards_frame, fg_color="transparent")
    cards_right.pack(side="left", fill="both", expand=True, padx=(5, 0))

    # ── Audio Codec card ──
    codec_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    codec_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(codec_card, text="\U0001f3b5 Audio Codec",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    codec_fields = [
        ("codec_name", "Codec Name"),
        ("codec_mfg", "Manufacturer"),
        ("codec_type", "Codec Type"),
        ("sample_rate", "Sample Rate"),
        ("bit_depth", "Bit Depth"),
        ("channels", "Channels"),
        ("codec_status", "Status"),
    ]
    codec_labels = {}
    for key, name in codec_fields:
        row = ctk.CTkFrame(codec_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        codec_labels[key] = (val, dot)
    ctk.CTkFrame(codec_card, fg_color="transparent", height=8).pack()

    # ── Speaker card ──
    spk_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    spk_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(spk_card, text="\U0001f50a Speaker",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    spk_fields = [
        ("spk_present", "Present"),
        ("spk_count", "Speaker Count"),
        ("spk_amplifier", "Amplifier IC"),
        ("spk_impedance", "Impedance"),
        ("spk_status", "Status"),
    ]
    spk_labels = {}
    for key, name in spk_fields:
        row = ctk.CTkFrame(spk_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        spk_labels[key] = (val, dot)
    ctk.CTkFrame(spk_card, fg_color="transparent", height=8).pack()

    # ── Volume Levels card ──
    vol_card = ctk.CTkFrame(cards_left, fg_color=colors["bg_card"], corner_radius=12)
    vol_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(vol_card, text="\U0001f39a\ufe0f Volume Levels",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    vol_fields = [
        ("vol_music", "Music"),
        ("vol_ring", "Ring"),
        ("vol_notification", "Notification"),
        ("vol_alarm", "Alarm"),
    ]
    vol_labels = {}
    for key, name in vol_fields:
        row = ctk.CTkFrame(vol_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        vol_labels[key] = (val, dot)
    ctk.CTkFrame(vol_card, fg_color="transparent", height=8).pack()

    # ── Microphone card ──
    mic_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    mic_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(mic_card, text="\U0001f3a4 Microphone",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    mic_fields = [
        ("mic_present", "Present"),
        ("mic_count", "Mic Count"),
        ("mic_types", "Types"),
        ("mic_status", "Status"),
    ]
    mic_labels = {}
    for key, name in mic_fields:
        row = ctk.CTkFrame(mic_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        mic_labels[key] = (val, dot)
    ctk.CTkFrame(mic_card, fg_color="transparent", height=8).pack()

    # ── Headphone card ──
    hp_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    hp_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(hp_card, text="\U0001f3a7 Headphone",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    hp_fields = [
        ("hp_jack_present", "Jack Present"),
        ("hp_jack_type", "Jack Type"),
        ("hp_connected", "Connected"),
        ("hp_dac", "DAC Chip"),
        ("hp_status", "Status"),
    ]
    hp_labels = {}
    for key, name in hp_fields:
        row = ctk.CTkFrame(hp_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        hp_labels[key] = (val, dot)
    ctk.CTkFrame(hp_card, fg_color="transparent", height=8).pack()

    # ── Audio Routes card ──
    route_card = ctk.CTkFrame(cards_right, fg_color=colors["bg_card"], corner_radius=12)
    route_card.pack(fill="x", pady=(0, 10))
    ctk.CTkLabel(route_card, text="\U0001f500 Audio Routes",
                 font=("Segoe UI", 14, "bold"), text_color=colors["accent"]).pack(anchor="w", padx=15, pady=(12, 5))

    route_fields = [
        ("route_output", "Output Path"),
        ("route_input", "Input Path"),
        ("route_status", "Status"),
    ]
    route_labels = {}
    for key, name in route_fields:
        row = ctk.CTkFrame(route_card, fg_color=colors["bg_light"], corner_radius=4, height=30)
        row.pack(fill="x", padx=12, pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                     text_color=colors["text"], width=120, anchor="w").pack(side="left", padx=8)
        val = ctk.CTkLabel(row, text="\u2014", font=("Consolas", 11),
                            text_color=colors["text_dim"], anchor="w")
        val.pack(side="left", fill="x", expand=True, padx=8)
        dot = ctk.CTkLabel(row, text="\u25cf", font=("Segoe UI", 10),
                            text_color=colors["text_dim"], width=20)
        dot.pack(side="right", padx=8)
        route_labels[key] = (val, dot)
    ctk.CTkFrame(route_card, fg_color="transparent", height=8).pack()

    # ── Live append helpers (using shared utilities) ──
    def _append_live(text):
        append_live(app, report_box, text)

    def _append_live_lines(lines):
        append_live_lines(app, report_box, lines)

    def _set_field(labels_dict, key, value, ok=True):
        if key in labels_dict:
            v, d = labels_dict[key]
            app.content.after(0, lambda: v.configure(text=str(value), text_color=colors["text"]))
            color = colors["success"] if ok else colors["warning"]
            app.content.after(0, lambda: d.configure(text_color=color))

    # ── Start detection ──
    def start_detection():
        if running["value"]:
            return
        running["value"] = True

        report_box.configure(state="normal")
        report_box.delete("1.0", "end")
        progress.set(0)
        health_badge.configure(text="  \U0001f504 Testing...", text_color=colors["info"])
        msg_label.configure(text="Initializing audio detection...", text_color=colors["text_dim"])

        for labels_dict in [codec_labels, spk_labels, vol_labels, mic_labels, hp_labels, route_labels]:
            for key, (v, d) in labels_dict.items():
                v.configure(text="\u2014", text_color=colors["text_dim"])
                d.configure(text_color=colors["text_dim"])

        full_report = {"lines": []}

        def _track(text):
            full_report["lines"].append(text)
            _append_live(text)

        def _track_lines(lines):
            full_report["lines"].extend(lines)
            _append_live_lines(lines)

        def run():
            import datetime as _dt

            header = [
                "=" * 70,
                "  MOOXY AI FAULT DETECTOR \u2014 AUDIO TEST REPORT",
                "=" * 70,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 70, "",
            ]
            _track_lines(header)

            result = None
            try:
                from app.hardware.audio_tester import detect_audio_status

                def cb(pct, msg):
                    app.content.after(0, lambda: progress.set(pct / 100.0 if pct > 1 else pct))
                    app.content.after(0, lambda: msg_label.configure(text=msg))

                _track("\U0001f50d Scanning audio subsystem...")
                _track("")

                result = detect_audio_status(callback=cb)

                # ═══ PHASE 1: AUDIO CODEC ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 1: AUDIO CODEC \u2550\u2550\u2550")
                _track("")

                codec = getattr(result, "codec_info", None)
                if codec and getattr(codec, "name", None):
                    _track(f"  \u2705 Audio Codec Detected")
                    _track(f"  Name:         {codec.name}")
                    _track(f"  Manufacturer: {codec.manufacturer}")
                    _track(f"  Type:         {codec.codec_type}")
                    _track(f"  Sample Rate:  {codec.sample_rate}")
                    _track(f"  Bit Depth:    {codec.bit_depth}")
                    _track(f"  Channels:     {codec.channels}")
                    _track(f"  Status:       {codec.status}")
                    _set_field(codec_labels, "codec_name", codec.name)
                    _set_field(codec_labels, "codec_mfg", codec.manufacturer)
                    _set_field(codec_labels, "codec_type", codec.codec_type)
                    _set_field(codec_labels, "sample_rate", codec.sample_rate)
                    _set_field(codec_labels, "bit_depth", codec.bit_depth)
                    _set_field(codec_labels, "channels", codec.channels)
                    _set_field(codec_labels, "codec_status", codec.status,
                               ok=str(codec.status).lower() in ("ok", "active", "working"))
                else:
                    _track("  \u274c Audio Codec NOT FOUND")
                    _set_field(codec_labels, "codec_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.20))

                # ═══ PHASE 2: SPEAKER INFO ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 2: SPEAKER INFO \u2550\u2550\u2550")
                _track("")

                spk = getattr(result, "speaker_info", None)
                if spk and getattr(spk, "present", False):
                    _track(f"  \u2705 Speaker Detected")
                    _track(f"  Present:      {spk.present}")
                    _track(f"  Count:        {spk.count}")
                    _track(f"  Amplifier IC: {spk.amplifier_ic}")
                    _track(f"  Impedance:    {spk.impedance}")
                    _track(f"  Status:       {spk.status}")
                    _set_field(spk_labels, "spk_present", "Yes" if spk.present else "No")
                    _set_field(spk_labels, "spk_count", spk.count)
                    _set_field(spk_labels, "spk_amplifier", spk.amplifier_ic)
                    _set_field(spk_labels, "spk_impedance", spk.impedance)
                    _set_field(spk_labels, "spk_status", spk.status,
                               ok=str(spk.status).lower() in ("ok", "active", "working"))
                else:
                    _track("  \u274c Speaker NOT FOUND")
                    _set_field(spk_labels, "spk_present", "No", ok=False)
                    _set_field(spk_labels, "spk_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.40))

                # ═══ PHASE 3: MICROPHONE ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 3: MICROPHONE \u2550\u2550\u2550")
                _track("")

                mic = getattr(result, "microphone_info", None)
                if mic and getattr(mic, "present", False):
                    _track(f"  \u2705 Microphone Detected")
                    _track(f"  Present:  {mic.present}")
                    _track(f"  Count:    {mic.count}")
                    _track(f"  Types:    {mic.types}")
                    _track(f"  Status:   {mic.status}")
                    _set_field(mic_labels, "mic_present", "Yes" if mic.present else "No")
                    _set_field(mic_labels, "mic_count", mic.count)
                    types_str = ", ".join(mic.types) if isinstance(mic.types, (list, tuple)) else str(mic.types)
                    _set_field(mic_labels, "mic_types", types_str)
                    _set_field(mic_labels, "mic_status", mic.status,
                               ok=str(mic.status).lower() in ("ok", "active", "working"))
                else:
                    _track("  \u274c Microphone NOT FOUND")
                    _set_field(mic_labels, "mic_present", "No", ok=False)
                    _set_field(mic_labels, "mic_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.55))

                # ═══ PHASE 4: HEADPHONE ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 4: HEADPHONE \u2550\u2550\u2550")
                _track("")

                hp = getattr(result, "headphone_info", None)
                if hp:
                    jack_present = getattr(hp, "jack_present", False)
                    _track(f"  {'\u2705' if jack_present else '\u26a0\ufe0f'} Headphone Jack: {'Present' if jack_present else 'Not Present'}")
                    _track(f"  Jack Type:   {getattr(hp, 'jack_type', 'N/A')}")
                    _track(f"  Connected:   {getattr(hp, 'connected', False)}")
                    _track(f"  DAC Chip:    {getattr(hp, 'dac_ic', 'N/A')}")
                    _track(f"  Status:      {getattr(hp, 'status', 'Unknown')}")
                    _set_field(hp_labels, "hp_jack_present", "Yes" if jack_present else "No",
                               ok=jack_present)
                    _set_field(hp_labels, "hp_jack_type", getattr(hp, "jack_type", "N/A"))
                    _set_field(hp_labels, "hp_connected",
                               "Yes" if getattr(hp, "connected", False) else "No")
                    _set_field(hp_labels, "hp_dac", getattr(hp, "dac_ic", "N/A"))
                    _set_field(hp_labels, "hp_status", getattr(hp, "status", "Unknown"),
                               ok=str(getattr(hp, "status", "")).lower() in ("ok", "active", "working"))
                else:
                    _track("  \u26a0\ufe0f Headphone info not available")
                    _set_field(hp_labels, "hp_jack_present", "N/A", ok=False)
                    _set_field(hp_labels, "hp_status", "Not Found", ok=False)

                app.content.after(0, lambda: progress.set(0.70))

                # ═══ PHASE 5: AUDIO ROUTES & VOLUME ═══
                _track("")
                _track("\u2550\u2550\u2550 PHASE 5: AUDIO ROUTES & VOLUME \u2550\u2550\u2550")
                _track("")

                routes = getattr(result, "audio_routes", None)
                if routes:
                    out_path = getattr(routes, "output", "Unknown")
                    in_path = getattr(routes, "input", "Unknown")
                    r_status = getattr(routes, "status", "Unknown")
                    _track(f"  \u2705 Audio Routes Detected")
                    _track(f"  Output: {out_path}")
                    _track(f"  Input:  {in_path}")
                    _track(f"  Status: {r_status}")
                    _set_field(route_labels, "route_output", out_path)
                    _set_field(route_labels, "route_input", in_path)
                    _set_field(route_labels, "route_status", r_status,
                               ok=str(r_status).lower() in ("ok", "active", "working"))
                else:
                    _track("  \u26a0\ufe0f Audio routes not available")
                    _set_field(route_labels, "route_status", "Not Found", ok=False)

                _track("")

                volumes = getattr(result, "volume_levels", None)
                if volumes and isinstance(volumes, dict):
                    _track("  \U0001f39a\ufe0f Volume Levels:")
                    music = volumes.get("music", "N/A")
                    ring = volumes.get("ring", "N/A")
                    notif = volumes.get("notification", "N/A")
                    alarm = volumes.get("alarm", "N/A")
                    _track(f"    Music:        {music}")
                    _track(f"    Ring:          {ring}")
                    _track(f"    Notification:  {notif}")
                    _track(f"    Alarm:         {alarm}")
                    _set_field(vol_labels, "vol_music", music)
                    _set_field(vol_labels, "vol_ring", ring)
                    _set_field(vol_labels, "vol_notification", notif)
                    _set_field(vol_labels, "vol_alarm", alarm)
                else:
                    _track("  \u26a0\ufe0f Volume levels not available")
                    _set_field(vol_labels, "vol_music", "N/A", ok=False)

                app.content.after(0, lambda: progress.set(0.90))

                # ═══ AUDIO HEALTH SUMMARY ═══
                _track("")
                _track("\u2550\u2550\u2550 AUDIO HEALTH SUMMARY \u2550\u2550\u2550")
                _track("")

                score = getattr(result, "health_score", 0)
                overall = getattr(result, "overall_health", "Unknown")
                _track(f"  Health Score:  {score}/100")
                _track(f"  Overall:       {overall}")

                warnings = getattr(result, "warnings", [])
                if warnings:
                    _track("")
                    _track("  \u26a0\ufe0f Warnings:")
                    for w in warnings:
                        _track(f"    \u2022 {w}")

                overall_str = str(overall).upper()
                if overall_str in ("GOOD", "HEALTHY", "OK"):
                    _track("")
                    _track(f"  \u2705 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \u2705 {overall_str} ({score}/100)", text_color=colors["success"]))
                elif overall_str in ("DEGRADED", "FAIR", "PARTIAL"):
                    _track("")
                    _track(f"  \U0001f7e1 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \U0001f7e1 {overall_str} ({score}/100)", text_color=colors["warning"]))
                elif overall_str in ("POOR", "BAD", "CRITICAL"):
                    _track("")
                    _track(f"  \U0001f534 OVERALL: {overall_str}")
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \U0001f534 {overall_str} ({score}/100)", text_color=colors["accent"]))
                else:
                    app.content.after(0, lambda: health_badge.configure(
                        text=f"  \u26a0\ufe0f {overall_str}", text_color=colors["text_dim"]))

            except ImportError:
                _track("  \u274c Audio tester module not found")
                _track("  Install: app/hardware/audio_tester.py required")
                app.content.after(0, lambda: health_badge.configure(
                    text="  \u274c Module Error", text_color=colors["accent"]))
            except Exception as e:
                _track(f"  \u274c Audio detection error: {str(e)}")
                app.content.after(0, lambda: health_badge.configure(
                    text="  \u274c Error", text_color=colors["accent"]))

            _track("")
            _track("=" * 70)
            _track("  Report generated by Mooxy AI Fault Detector v1.0")
            _track("=" * 70)

            report_text = "\n".join(full_report["lines"])

            app.content.after(0, lambda: progress.set(1.0))
            app.content.after(0, lambda: msg_label.configure(
                text="Audio test complete \u2014 full report above", text_color=colors["success"]))

            try:
                from app.gui.history_manager import get_unique_log_path, add_detection
                log_path = get_unique_log_path("audio_report")
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(report_text)
                add_detection(
                    detection_type="AUDIO",
                    device_name="Audio Test",
                    summary=f"Health: {getattr(result, 'overall_health', 'Unknown')} | Score: {getattr(result, 'health_score', 0)}/100",
                    faults_count=len(getattr(result, 'warnings', [])),
                    faults_summary="; ".join(getattr(result, 'warnings', [])[:3]),
                    report_file=str(log_path),
                    extra={"health_score": getattr(result, 'health_score', 0)} if result else {}
                )
            except Exception:
                pass

            running["value"] = False

        threading.Thread(target=run, daemon=True).start()

    def copy_report():
        copy_report_to_clipboard(app, report_box, status_label=msg_label, colors=colors)

    def save_report():
        save_report_to_file(app, report_box, default_prefix="audio_report",
                            status_label=msg_label, colors=colors)

    # ── Buttons ──
    ctk.CTkButton(btn_frame, text="\U0001f50a Start Audio Detection", width=300, height=46,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 15, "bold"), corner_radius=10,
                  command=start_detection).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="\U0001f4cb Copy", width=100, height=46,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="\U0001f4be Save", width=100, height=46,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # ── Report textbox ──
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"], font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=500, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0",
                      "Press 'Start Audio Detection' to begin.\n\n"
                      "Requirements:\n"
                      "\u2022 Device connected via USB with ADB enabled\n\n"
                      "Tests performed:\n"
                      "  1. Audio codec detection & IC identification\n"
                      "  2. Speaker enumeration & amplifier IC check\n"
                      "  3. Microphone detection (primary/secondary/noise-cancel)\n"
                      "  4. Headphone jack & DAC chip detection\n"
                      "  5. Audio route path analysis\n"
                      "  6. Volume level readout (music, ring, notification, alarm)\n"
                      "  7. IC matching (Qualcomm WCD, Cirrus Logic, TI, Maxim, NXP)\n")
    setup_report_tags(report_box)

    app.update_status("Audio Test \u2014 Connect device and press Start")
