import customtkinter as ctk
import threading
import datetime as _dt

from app.hardware.imei_repair import (
    read_imei, write_imei, check_baseband, check_network_lock, repair_baseband
)


# ---------------------------------------------------------------------------
# Luhn checksum validator for IMEI
# ---------------------------------------------------------------------------
def _luhn_check(imei_str):
    """Return True if the IMEI passes the Luhn / mod-10 check."""
    if not imei_str or not imei_str.isdigit() or len(imei_str) not in (15, 16):
        return False
    digits = [int(d) for d in imei_str]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def render_imei_page(app):
    """IMEI Repair page -- read / write / baseband / network lock tabs."""
    colors = app.colors

    # ── Page title ────────────────────────────────────────────────
    ctk.CTkLabel(
        app.content, text="IMEI Repair",
        font=("Segoe UI", 24, "bold"), text_color=colors["text"],
    ).pack(anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(
        app.content,
        text="Read, write and verify IMEI / baseband / network lock status via ADB or EDL",
        font=("Segoe UI", 13), text_color=colors["text_dim"],
    ).pack(anchor="w", padx=20, pady=(0, 15))

    # ── Warning card (red) ────────────────────────────────────────
    warn_card = ctk.CTkFrame(app.content, fg_color="#3a1020", corner_radius=12,
                              border_color="#ec4899", border_width=1)
    warn_card.pack(fill="x", padx=20, pady=(0, 15))
    ctk.CTkLabel(
        warn_card, text="WARNING",
        font=("Segoe UI", 14, "bold"), text_color="#ec4899",
    ).pack(anchor="w", padx=15, pady=(12, 2))
    ctk.CTkLabel(
        warn_card,
        text="IMEI modification may be illegal in some jurisdictions. "
             "This tool is for restoring original IMEI after motherboard repair only.",
        font=("Segoe UI", 12), text_color="#ff8a8a", wraplength=750, anchor="w", justify="left",
    ).pack(anchor="w", padx=15, pady=(0, 12))

    # ── Tab-like buttons ──────────────────────────────────────────
    tab_bar = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=10)
    tab_bar.pack(fill="x", padx=20, pady=(0, 10))
    tab_inner = ctk.CTkFrame(tab_bar, fg_color="transparent")
    tab_inner.pack(fill="x", padx=10, pady=8)

    tab_names = ["Read IMEI", "Write IMEI", "Baseband", "Network Lock"]
    tab_buttons = {}
    active_tab = {"name": tab_names[0]}

    # Body frame -- tab content rendered here
    body = ctk.CTkFrame(app.content, fg_color="transparent")
    body.pack(fill="x", padx=20, pady=(0, 5))

    # ── Progress bar ──────────────────────────────────────────────
    progress = ctk.CTkProgressBar(app.content, width=600, height=16,
                                   progress_color=colors["accent"],
                                   fg_color=colors["bg_light"])
    progress.set(0)
    progress.pack(padx=20, pady=(0, 3), anchor="w")
    msg_label = ctk.CTkLabel(app.content, text="",
                              font=("Segoe UI", 12), text_color=colors["text_dim"])
    msg_label.pack(anchor="w", padx=20, pady=(0, 5))

    # ── Status badge ──────────────────────────────────────────────
    status_frame = ctk.CTkFrame(app.content, fg_color=colors["bg_card"],
                                 corner_radius=10, height=40)
    status_frame.pack(fill="x", padx=20, pady=(0, 5))
    status_frame.pack_propagate(False)
    status_badge = ctk.CTkLabel(status_frame, text="  Idle",
                                 font=("Segoe UI", 13, "bold"),
                                 text_color=colors["text_dim"])
    status_badge.pack(side="left", padx=15, pady=8)

    # ── Buttons row (Copy / Save) ─────────────────────────────────
    btn_frame = ctk.CTkFrame(app.content, fg_color="transparent")
    btn_frame.pack(fill="x", padx=20, pady=(0, 5))

    # ── Report textbox with color tags ────────────────────────────
    report_box = ctk.CTkTextbox(app.content, fg_color=colors["bg_dark"],
                                 text_color=colors["success"],
                                 font=("Consolas", 11),
                                 border_color=colors["border"], border_width=1,
                                 height=420, wrap="none")
    report_box.pack(fill="both", expand=True, padx=20, pady=(0, 20))
    report_box.insert("1.0",
                      "Select a tab above and press the action button to begin.\n\n"
                      "Requirements:\n"
                      "  * Phone connected via USB\n"
                      "  * USB Debugging enabled OR phone in EDL mode\n"
                      "  * ADB / Qualcomm tools in PATH\n")

    # ── Color tag setup ───────────────────────────────────────────
    def _setup_tags():
        tb = report_box._textbox
        tb.tag_configure("ok",      foreground="#34d399")
        tb.tag_configure("warning", foreground="#fbbf24")
        tb.tag_configure("fault",   foreground="#ec4899")
        tb.tag_configure("info",    foreground="#a855f7")
        tb.tag_configure("header",  foreground="#ec4899",
                         font=("Consolas", 12, "bold"))
        tb.tag_configure("dim",     foreground="#9a93b5")

    _setup_tags()

    def _get_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "critical", "danger", "fail",
                                 "error", "locked", "invalid"]):
            return "fault"
        if any(k in t for k in ["warning", "caution", "attempts"]):
            return "warning"
        if any(k in t for k in ["ok", "pass", "valid", "success",
                                 "unlocked", "ready", "healthy"]):
            return "ok"
        if any(k in t for k in ["===", "---", "REPORT",
                                 "IMEI", "BASEBAND", "NETWORK"]):
            return "header"
        if any(k in t for k in ["checking", "reading", "scanning",
                                 "writing", "verifying"]):
            return "info"
        return None

    # ── Live append helpers (thread-safe) ─────────────────────────
    def _append_live(text):
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

    def _append_live_lines(lines):
        def _do():
            report_box.configure(state="normal")
            for line in lines:
                tag = _get_tag(line)
                if tag:
                    start = report_box._textbox.index("end-1c")
                    report_box.insert("end", line + "\n")
                    end = report_box._textbox.index("end-1c")
                    report_box._textbox.tag_add(tag, start, end)
                else:
                    report_box.insert("end", line + "\n")
            report_box.see("end")
        app.content.after(0, _do)

    def _clear_report():
        report_box.configure(state="normal")
        report_box.delete("1.0", "end")

    running = {"value": False}

    # ── Copy / Save helpers ───────────────────────────────────────
    def copy_report():
        try:
            text = report_box.get("1.0", "end").strip()
            app.clipboard_clear()
            app.clipboard_append(text)
            msg_label.configure(text="Report copied to clipboard!",
                                text_color=colors["success"])
        except Exception:
            pass

    def save_report():
        try:
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text", "*.txt")],
                initialfile="imei_report.txt",
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(report_box.get("1.0", "end"))
                msg_label.configure(text=f"Saved to: {path}",
                                    text_color=colors["success"])
        except Exception:
            pass

    ctk.CTkButton(btn_frame, text="Copy Report", width=130, height=40,
                  fg_color=colors["info"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=copy_report).pack(side="left", padx=(0, 10))

    ctk.CTkButton(btn_frame, text="Save Report", width=130, height=40,
                  fg_color=colors["success"], hover_color=colors["accent"],
                  font=("Segoe UI", 13, "bold"), corner_radius=10,
                  command=save_report).pack(side="left")

    # ==================================================================
    # Tab content renderers
    # ==================================================================

    def _clear_body():
        for w in body.winfo_children():
            w.destroy()

    # ----- helper: result field rows inside a card --------------------
    def _make_result_rows(parent, fields):
        """Create labelled result rows. Returns dict of key -> (val_label, dot_label)."""
        labels = {}
        for key, name in fields:
            row = ctk.CTkFrame(parent, fg_color=colors["bg_light"],
                               corner_radius=4, height=35)
            row.pack(fill="x", padx=15, pady=1)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=name, font=("Segoe UI", 11, "bold"),
                         text_color=colors["text"], width=200,
                         anchor="w").pack(side="left", padx=10)
            val = ctk.CTkLabel(row, text="---", font=("Consolas", 11),
                               text_color=colors["text_dim"], anchor="w")
            val.pack(side="left", fill="x", expand=True, padx=10)
            dot = ctk.CTkLabel(row, text="", font=("Segoe UI", 12),
                               text_color=colors["text_dim"], width=25)
            dot.pack(side="right", padx=10)
            labels[key] = (val, dot)
        ctk.CTkFrame(parent, fg_color="transparent", height=8).pack()
        return labels

    def _set_field(labels, key, value, ok=True):
        if key not in labels:
            return
        v, d = labels[key]
        clr = colors["success"] if ok else colors["warning"]
        app.content.after(0, lambda: v.configure(
            text=str(value), text_color=colors["text"]))
        app.content.after(0, lambda: d.configure(text_color=clr))

    # ==================================================================
    # TAB 1 -- Read IMEI
    # ==================================================================
    def _render_read_tab():
        _clear_body()

        card = ctk.CTkFrame(body, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card, text="Read IMEI Information",
                     font=("Segoe UI", 16, "bold"),
                     text_color=colors["accent"]).pack(anchor="w", padx=20,
                                                        pady=(15, 10))

        read_fields = [
            ("imei1",       "IMEI 1"),
            ("imei2",       "IMEI 2"),
            ("meid",        "MEID"),
            ("serial",      "Serial Number"),
            ("sv",          "SV Number"),
            ("baseband",    "Baseband Version"),
            ("method",      "Read Method"),
        ]
        field_labels = _make_result_rows(card, read_fields)

        def _do_read():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            progress.set(0)
            status_badge.configure(text="  Reading IMEI...",
                                    text_color=colors["info"])

            header = [
                "=" * 65,
                "  IMEI READ REPORT",
                "=" * 65,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 65,
                "",
            ]
            _append_live_lines(header)

            def run():
                try:
                    def cb(pct, msg):
                        app.content.after(0, lambda: progress.set(pct))
                        app.content.after(0, lambda: msg_label.configure(text=msg))
                        _append_live(f"  [READ] {msg}")

                    result = read_imei(callback=cb)

                    _append_live("")
                    _append_live("--- Results ---")
                    _append_live("")

                    imei1 = getattr(result, "imei1", None) or "N/A"
                    imei2 = getattr(result, "imei2", None) or "N/A"
                    meid = getattr(result, "meid", None) or "N/A"
                    serial = getattr(result, "serial", None) or "N/A"
                    sv = getattr(result, "sv_number", None) or "N/A"
                    bb = getattr(result, "baseband_version", None) or "N/A"
                    method = getattr(result, "method", None) or "ADB"

                    _set_field(field_labels, "imei1", imei1,
                               _luhn_check(str(imei1)))
                    _set_field(field_labels, "imei2", imei2,
                               _luhn_check(str(imei2)))
                    _set_field(field_labels, "meid", meid, meid != "N/A")
                    _set_field(field_labels, "serial", serial, serial != "N/A")
                    _set_field(field_labels, "sv", sv, sv != "N/A")
                    _set_field(field_labels, "baseband", bb, bb != "N/A")
                    _set_field(field_labels, "method", method, True)

                    lines = [
                        f"  IMEI 1:           {imei1}  "
                        f"{'[VALID]' if _luhn_check(str(imei1)) else '[INVALID]'}",
                        f"  IMEI 2:           {imei2}  "
                        f"{'[VALID]' if _luhn_check(str(imei2)) else '[INVALID]'}",
                        f"  MEID:             {meid}",
                        f"  Serial:           {serial}",
                        f"  SV Number:        {sv}",
                        f"  Baseband Version: {bb}",
                        f"  Read Method:      {method}",
                    ]
                    _append_live_lines(lines)

                    err = getattr(result, "error", None)
                    if err:
                        _append_live("")
                        _append_live(f"  ERROR: {err}")
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Error: {str(err)[:60]}",
                            text_color=colors["accent"]))
                    else:
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  IMEI1: {imei1}  |  IMEI2: {imei2}",
                            text_color=colors["success"]))

                    app.content.after(0, lambda: progress.set(1.0))

                except Exception as e:
                    _append_live(f"  ERROR: {e}")
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  Error: {str(e)[:60]}",
                        text_color=colors["accent"]))
                    app.content.after(0, lambda: progress.set(1.0))

                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(card, text="Read IMEI", width=220, height=44,
                      fg_color=colors["accent"],
                      hover_color=colors["accent_hover"],
                      font=("Segoe UI", 14, "bold"), corner_radius=10,
                      command=_do_read).pack(padx=20, pady=(5, 15))

    # ==================================================================
    # TAB 2 -- Write IMEI
    # ==================================================================
    def _render_write_tab():
        _clear_body()

        card = ctk.CTkFrame(body, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card, text="Write IMEI",
                     font=("Segoe UI", 16, "bold"),
                     text_color=colors["accent"]).pack(anchor="w", padx=20,
                                                        pady=(15, 5))
        ctk.CTkLabel(card,
                     text="Enter the IMEI values to write. Both fields are validated with Luhn check.",
                     font=("Segoe UI", 12),
                     text_color=colors["text_dim"]).pack(anchor="w", padx=20,
                                                          pady=(0, 10))

        # Input rows
        input_frame = ctk.CTkFrame(card, fg_color="transparent")
        input_frame.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(input_frame, text="IMEI 1:",
                     font=("Segoe UI", 13, "bold"),
                     text_color=colors["text"]).pack(side="left")
        imei1_var = ctk.StringVar(value="")
        imei1_entry = ctk.CTkEntry(input_frame, textvariable=imei1_var,
                                    width=200, height=38,
                                    fg_color=colors["bg_light"],
                                    border_color=colors["border"],
                                    font=("Consolas", 14),
                                    placeholder_text="15-digit IMEI")
        imei1_entry.pack(side="left", padx=(8, 20))

        ctk.CTkLabel(input_frame, text="IMEI 2:",
                     font=("Segoe UI", 13, "bold"),
                     text_color=colors["text"]).pack(side="left")
        imei2_var = ctk.StringVar(value="")
        imei2_entry = ctk.CTkEntry(input_frame, textvariable=imei2_var,
                                    width=200, height=38,
                                    fg_color=colors["bg_light"],
                                    border_color=colors["border"],
                                    font=("Consolas", 14),
                                    placeholder_text="15-digit IMEI")
        imei2_entry.pack(side="left", padx=(8, 0))

        # Validation result label
        valid_label = ctk.CTkLabel(card, text="",
                                    font=("Segoe UI", 12, "bold"),
                                    text_color=colors["text_dim"])
        valid_label.pack(anchor="w", padx=20, pady=(5, 5))

        # Write result fields
        write_fields = [
            ("w_imei1",  "Written IMEI 1"),
            ("w_imei2",  "Written IMEI 2"),
            ("w_verify", "Verification"),
            ("w_method", "Write Method"),
        ]
        w_labels = _make_result_rows(card, write_fields)

        def _validate():
            v1 = imei1_var.get().strip()
            v2 = imei2_var.get().strip()
            ok1 = _luhn_check(v1)
            ok2 = _luhn_check(v2) if v2 else True  # IMEI2 optional

            parts = []
            if v1:
                parts.append(f"IMEI1: {'VALID' if ok1 else 'INVALID Luhn'}")
            else:
                parts.append("IMEI1: empty")
            if v2:
                parts.append(f"IMEI2: {'VALID' if ok2 else 'INVALID Luhn'}")
            else:
                parts.append("IMEI2: empty (optional)")

            clr = colors["success"] if (ok1 and ok2 and v1) else colors["accent"]
            valid_label.configure(text="  |  ".join(parts), text_color=clr)
            return ok1 and bool(v1)

        def _do_write():
            if running["value"]:
                return
            if not _validate():
                valid_label.configure(text="IMEI 1 is required and must pass Luhn check",
                                       text_color=colors["accent"])
                return

            running["value"] = True
            _clear_report()
            progress.set(0)
            status_badge.configure(text="  Writing IMEI...",
                                    text_color=colors["warning"])

            v1 = imei1_var.get().strip()
            v2 = imei2_var.get().strip() or None

            header = [
                "=" * 65,
                "  IMEI WRITE REPORT",
                "=" * 65,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"  IMEI 1 to write: {v1}",
                f"  IMEI 2 to write: {v2 or '(not set)'}",
                "=" * 65,
                "",
            ]
            _append_live_lines(header)

            def run():
                try:
                    def cb(pct, msg):
                        app.content.after(0, lambda: progress.set(pct))
                        app.content.after(0, lambda: msg_label.configure(text=msg))
                        _append_live(f"  [WRITE] {msg}")

                    result = write_imei(imei1=v1, imei2=v2, callback=cb)

                    _append_live("")
                    _append_live("--- Write Results ---")
                    _append_live("")

                    written1 = getattr(result, "imei1", v1)
                    written2 = getattr(result, "imei2", v2 or "N/A")
                    verified = getattr(result, "verified", False)
                    method = getattr(result, "method", "AT Command")

                    _set_field(w_labels, "w_imei1", written1,
                               _luhn_check(str(written1)))
                    _set_field(w_labels, "w_imei2", written2,
                               _luhn_check(str(written2)))
                    _set_field(w_labels, "w_verify",
                               "PASS - Verified" if verified else "FAIL - Not verified",
                               verified)
                    _set_field(w_labels, "w_method", method, True)

                    verify_tag = "[VALID]" if verified else "[FAILED]"
                    lines = [
                        f"  Written IMEI 1:  {written1}  {verify_tag}",
                        f"  Written IMEI 2:  {written2}",
                        f"  Verification:    {'PASS' if verified else 'FAIL'}",
                        f"  Write Method:    {method}",
                    ]
                    _append_live_lines(lines)

                    err = getattr(result, "error", None)
                    if err:
                        _append_live("")
                        _append_live(f"  ERROR: {err}")
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Write error: {str(err)[:60]}",
                            text_color=colors["accent"]))
                    else:
                        tag = "success" if verified else "warning"
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Write {'OK' if verified else 'done (unverified)'}"
                                 f"  |  IMEI1: {written1}",
                            text_color=colors[tag]))

                    app.content.after(0, lambda: progress.set(1.0))

                except Exception as e:
                    _append_live(f"  ERROR: {e}")
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  Error: {str(e)[:60]}",
                        text_color=colors["accent"]))
                    app.content.after(0, lambda: progress.set(1.0))

                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        # Buttons inside card
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(btn_row, text="Validate", width=130, height=42,
                      fg_color=colors["info"],
                      hover_color=colors["accent"],
                      font=("Segoe UI", 13, "bold"), corner_radius=10,
                      command=_validate).pack(side="left", padx=(0, 10))

        ctk.CTkButton(btn_row, text="Write IMEI", width=180, height=42,
                      fg_color=colors["accent"],
                      hover_color=colors["accent_hover"],
                      font=("Segoe UI", 14, "bold"), corner_radius=10,
                      command=_do_write).pack(side="left")

    # ==================================================================
    # TAB 3 -- Baseband
    # ==================================================================
    def _render_baseband_tab():
        _clear_body()

        card = ctk.CTkFrame(body, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card, text="Baseband Information",
                     font=("Segoe UI", 16, "bold"),
                     text_color=colors["accent"]).pack(anchor="w", padx=20,
                                                        pady=(15, 10))

        bb_fields = [
            ("bb_version",  "Baseband Version"),
            ("bb_modem",    "Modem Version"),
            ("bb_rf",       "RF Chip"),
            ("bb_chipset",  "Chipset"),
            ("bb_bands",    "Supported Bands"),
        ]
        bb_labels = _make_result_rows(card, bb_fields)

        def _do_check():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            progress.set(0)
            status_badge.configure(text="  Checking Baseband...",
                                    text_color=colors["info"])

            header = [
                "=" * 65,
                "  BASEBAND CHECK REPORT",
                "=" * 65,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 65,
                "",
            ]
            _append_live_lines(header)

            def run():
                try:
                    def cb(pct, msg):
                        app.content.after(0, lambda: progress.set(pct))
                        app.content.after(0, lambda: msg_label.configure(text=msg))
                        _append_live(f"  [BASEBAND] {msg}")

                    result = check_baseband(callback=cb)

                    _append_live("")
                    _append_live("--- Baseband Results ---")
                    _append_live("")

                    version  = result.baseband_version or "N/A"
                    modem    = result.modem_version or "N/A"
                    rf       = result.rf_version or "N/A"
                    chipset  = result.chipset or "N/A"
                    bands_raw = result.bands_supported
                    bands    = ", ".join(bands_raw) if bands_raw else "N/A"
                    status   = result.status or "unknown"

                    _set_field(bb_labels, "bb_version", version,  version  != "N/A")
                    _set_field(bb_labels, "bb_modem",   modem,    modem    != "N/A")
                    _set_field(bb_labels, "bb_rf",      rf,       rf       != "N/A")
                    _set_field(bb_labels, "bb_chipset", chipset,  chipset  != "N/A")
                    _set_field(bb_labels, "bb_bands",   bands,    bands    != "N/A")

                    lines = [
                        f"  Baseband Version: {version}",
                        f"  Modem Version:    {modem}",
                        f"  RF Version:       {rf}",
                        f"  Chipset:          {chipset}",
                        f"  Status:           {status}",
                        f"  Supported Bands:  {bands}",
                    ]
                    _append_live_lines(lines)

                    err = result.error
                    if err:
                        _append_live("")
                        _append_live(f"  ERROR: {err}")
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Error: {str(err)[:60]}",
                            text_color=colors["accent"]))
                    elif status in ("missing", "unknown") or version == "N/A":
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Baseband MISSING — Click Fix Baseband",
                            text_color="#ffaa00"))
                    else:
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Baseband: {version}  |  Chipset: {chipset}",
                            text_color=colors["success"]))

                    app.content.after(0, lambda: progress.set(1.0))

                except Exception as e:
                    _append_live(f"  ERROR: {e}")
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  Error: {str(e)[:60]}",
                        text_color=colors["accent"]))
                    app.content.after(0, lambda: progress.set(1.0))

                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        def _do_fix():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            progress.set(0)
            status_badge.configure(text="  Fixing Baseband...", text_color=colors["info"])

            header = [
                "=" * 65,
                "  BASEBAND REPAIR — MTK/Qualcomm",
                "=" * 65,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "  Steps: restart rild → MTK ccci → sysfs reset → NVRAM → reboot",
                "=" * 65,
                "",
            ]
            _append_live_lines(header)

            def run_fix():
                try:
                    def cb(pct, msg):
                        app.content.after(0, lambda: progress.set(pct / 100.0))
                        app.content.after(0, lambda: msg_label.configure(text=msg))
                        _append_live(f"  [FIX] {msg}")

                    result = repair_baseband(callback=cb)

                    _append_live("")
                    _append_live("--- Repair Result ---")
                    for step in result.steps:
                        _append_live(f"  • {step}")
                    _append_live("")

                    if result.success:
                        _append_live(f"  ✓ Baseband recovered: {result.baseband_after}")
                        _append_live(f"  ✓ Method: {result.method_used}")
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Fixed! Baseband: {result.baseband_after}",
                            text_color=colors["success"]))
                        # Update field
                        _set_field(bb_labels, "bb_version", result.baseband_after, True)
                    else:
                        _append_live(f"  ✗ Repair failed: {result.error}")
                        _append_live("  → Firmware reflash (SP Flash Tool / Odin) required")
                        app.content.after(0, lambda: status_badge.configure(
                            text="  Fix failed — firmware flash needed",
                            text_color=colors["accent"]))

                    app.content.after(0, lambda: progress.set(1.0))

                except Exception as e:
                    _append_live(f"  ERROR: {e}")
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  Error: {str(e)[:60]}",
                        text_color=colors["accent"]))
                    app.content.after(0, lambda: progress.set(1.0))

                running["value"] = False

            threading.Thread(target=run_fix, daemon=True).start()

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(5, 15))

        ctk.CTkButton(btn_row, text="Check Baseband", width=200, height=44,
                      fg_color=colors["accent"],
                      hover_color=colors["accent_hover"],
                      font=("Segoe UI", 14, "bold"), corner_radius=10,
                      command=_do_check).pack(side="left", padx=(0, 10))

        ctk.CTkButton(btn_row, text="Fix Baseband", width=200, height=44,
                      fg_color="#e65c00",
                      hover_color="#cc4400",
                      font=("Segoe UI", 14, "bold"), corner_radius=10,
                      command=_do_fix).pack(side="left")

    # ==================================================================
    # TAB 4 -- Network Lock
    # ==================================================================
    def _render_network_tab():
        _clear_body()

        card = ctk.CTkFrame(body, fg_color=colors["bg_card"], corner_radius=12)
        card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(card, text="Network Lock Status",
                     font=("Segoe UI", 16, "bold"),
                     text_color=colors["accent"]).pack(anchor="w", padx=20,
                                                        pady=(15, 10))

        nw_fields = [
            ("nw_status",   "Lock Status"),
            ("nw_carrier",  "Carrier / Operator"),
            ("nw_nck",      "NCK Attempts Remaining"),
            ("nw_mck",      "MCK Attempts Remaining"),
            ("nw_spck",     "SPCK Attempts Remaining"),
            ("nw_sim",      "SIM Status"),
        ]
        nw_labels = _make_result_rows(card, nw_fields)

        def _do_check():
            if running["value"]:
                return
            running["value"] = True
            _clear_report()
            progress.set(0)
            status_badge.configure(text="  Checking Network Lock...",
                                    text_color=colors["info"])

            header = [
                "=" * 65,
                "  NETWORK LOCK CHECK REPORT",
                "=" * 65,
                f"  Date: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "=" * 65,
                "",
            ]
            _append_live_lines(header)

            def run():
                try:
                    def cb(pct, msg):
                        app.content.after(0, lambda: progress.set(pct))
                        app.content.after(0, lambda: msg_label.configure(text=msg))
                        _append_live(f"  [NETWORK] {msg}")

                    result = check_network_lock(callback=cb)

                    _append_live("")
                    _append_live("--- Network Lock Results ---")
                    _append_live("")

                    lock_status = getattr(result, "lock_status", None) or "N/A"
                    carrier = getattr(result, "carrier", None) or "N/A"
                    nck = getattr(result, "nck_remaining", None)
                    nck_str = str(nck) if nck is not None else "N/A"
                    mck = getattr(result, "mck_remaining", None)
                    mck_str = str(mck) if mck is not None else "N/A"
                    spck = getattr(result, "spck_remaining", None)
                    spck_str = str(spck) if spck is not None else "N/A"
                    sim_status = getattr(result, "sim_status", None) or "N/A"

                    is_unlocked = "unlock" in lock_status.lower()
                    _set_field(nw_labels, "nw_status", lock_status,
                               is_unlocked)
                    _set_field(nw_labels, "nw_carrier", carrier,
                               carrier != "N/A")

                    nck_ok = nck is None or (isinstance(nck, int) and nck > 0)
                    mck_ok = mck is None or (isinstance(mck, int) and mck > 0)
                    spck_ok = spck is None or (isinstance(spck, int) and spck > 0)
                    _set_field(nw_labels, "nw_nck", nck_str, nck_ok)
                    _set_field(nw_labels, "nw_mck", mck_str, mck_ok)
                    _set_field(nw_labels, "nw_spck", spck_str, spck_ok)
                    _set_field(nw_labels, "nw_sim", sim_status,
                               "ready" in sim_status.lower()
                               or "absent" not in sim_status.lower())

                    lines = [
                        f"  Lock Status:          {lock_status}  "
                        f"{'[UNLOCKED]' if is_unlocked else '[LOCKED]'}",
                        f"  Carrier / Operator:   {carrier}",
                        f"  NCK Attempts Left:    {nck_str}",
                        f"  MCK Attempts Left:    {mck_str}",
                        f"  SPCK Attempts Left:   {spck_str}",
                        f"  SIM Status:           {sim_status}",
                    ]
                    _append_live_lines(lines)

                    # Warn if attempts are low
                    for label, val in [("NCK", nck), ("MCK", mck), ("SPCK", spck)]:
                        if isinstance(val, int) and val <= 3:
                            _append_live("")
                            _append_live(f"  WARNING: {label} attempts remaining is LOW ({val})."
                                          " Incorrect attempts may permanently lock the device.")

                    err = getattr(result, "error", None)
                    if err:
                        _append_live("")
                        _append_live(f"  ERROR: {err}")
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Error: {str(err)[:60]}",
                            text_color=colors["accent"]))
                    else:
                        app.content.after(0, lambda: status_badge.configure(
                            text=f"  Network: {lock_status}  |  Carrier: {carrier}"
                                 f"  |  SIM: {sim_status}",
                            text_color=colors["success"] if is_unlocked
                            else colors["warning"]))

                    app.content.after(0, lambda: progress.set(1.0))

                except Exception as e:
                    _append_live(f"  ERROR: {e}")
                    app.content.after(0, lambda: status_badge.configure(
                        text=f"  Error: {str(e)[:60]}",
                        text_color=colors["accent"]))
                    app.content.after(0, lambda: progress.set(1.0))

                running["value"] = False

            threading.Thread(target=run, daemon=True).start()

        ctk.CTkButton(card, text="Check Network Lock", width=220, height=44,
                      fg_color=colors["accent"],
                      hover_color=colors["accent_hover"],
                      font=("Segoe UI", 14, "bold"), corner_radius=10,
                      command=_do_check).pack(padx=20, pady=(5, 15))

    # ==================================================================
    # Tab switching logic
    # ==================================================================
    _tab_renderers = {
        "Read IMEI":    _render_read_tab,
        "Write IMEI":   _render_write_tab,
        "Baseband":     _render_baseband_tab,
        "Network Lock": _render_network_tab,
    }

    def _switch_tab(name):
        if running["value"]:
            return  # don't switch while operation in progress
        active_tab["name"] = name
        # Re-style buttons
        for tname, btn in tab_buttons.items():
            if tname == name:
                btn.configure(fg_color=colors["accent"],
                              text_color="#ffffff")
            else:
                btn.configure(fg_color=colors["bg_light"],
                              text_color=colors["text"])
        # Render tab content
        _tab_renderers[name]()

    for tname in tab_names:
        btn = ctk.CTkButton(
            tab_inner, text=tname, width=150, height=38,
            fg_color=colors["bg_light"], text_color=colors["text"],
            hover_color=colors["accent_hover"],
            font=("Segoe UI", 13, "bold"), corner_radius=8,
            command=lambda n=tname: _switch_tab(n),
        )
        btn.pack(side="left", padx=4)
        tab_buttons[tname] = btn

    # Render default tab
    _switch_tab(tab_names[0])

    app.update_status("IMEI Repair -- Select a tab and run an operation")
