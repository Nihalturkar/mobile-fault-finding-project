"""
schematic_diagnostics.py — "Schematic Diagnosis" page.

Workflow shown to the technician:

  1. Pick a board (config/boardviews/*.json flat-dump)
  2. Pick a fault pattern (camera_not_working, no_network_signal, ...)
     — or "Run camera evidence" to pull live ADB camera data
  3. Generate Test Plan  → the tool matches suspect nets on the actual board
  4. Probe each point, type the multimeter reading → live OK/ZERO/LOW/HIGH
  5. Read the verdict + export the report (board image with markers included)
"""

import json
import tempfile
from pathlib import Path

import customtkinter as ctk

from app.hardware.boardview_loader import BoardView
from app.hardware.schematic_diagnosis import SchematicDiagnoser

_BOARDVIEW_DIR = Path(__file__).resolve().parent.parent.parent.parent / "config" / "boardviews"


def _find_boards() -> list:
    if not _BOARDVIEW_DIR.exists():
        return []
    # index.json is documentation only — never offer it as a board
    return sorted([p for p in _BOARDVIEW_DIR.glob("*.json") if p.name.lower() != "index.json"])


def render_schematic_diagnostics(app):
    """Render the Schematic Diagnosis page."""
    colors = app.colors

    # ── Header ────────────────────────────────────────────────────────────
    ctk.CTkLabel(app.content, text="🔬 Schematic Diagnosis",
                 font=("Segoe UI", 24, "bold"), text_color=colors["text"]).pack(
                 anchor="w", padx=20, pady=(20, 5))
    ctk.CTkLabel(app.content,
                 text="Fault pattern → real test points on the board → multimeter reading → verdict",
                 font=("Segoe UI", 13), text_color=colors["text_dim"]).pack(
                 anchor="w", padx=20, pady=(0, 15))

    state = {"board": None, "diag": None, "points": [], "plan_png": ""}

    top = ctk.CTkFrame(app.content, fg_color=colors["bg_card"], corner_radius=12)
    top.pack(fill="x", padx=20, pady=(0, 10))

    boards = _find_boards()
    board_var = ctk.StringVar(value="(none found — open config/boardviews)")
    board_menu = ctk.CTkOptionMenu(top, values=[p.name for p in boards] or ["(no boards)"],
                                   variable=board_var, width=280,
                                   fg_color=colors["bg_medium"], button_color=colors["accent"])
    board_menu.grid(row=0, column=0, padx=(15, 10), pady=12, sticky="w")

    info_label = ctk.CTkLabel(top, text="", font=("Segoe UI", 12),
                              text_color=colors["text_dim"], anchor="w")
    info_label.grid(row=0, column=1, padx=10, pady=12, sticky="w")

    status_var = ctk.StringVar(value="Ready")
    status_label = ctk.CTkLabel(top, textvariable=status_var, font=("Segoe UI", 12),
                                text_color=colors["success"])
    status_label.grid(row=0, column=2, padx=15, pady=12, sticky="e")

    # ── Body: left (plan + measurements) / right (image + report) ─────────
    body = ctk.CTkFrame(app.content, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=20, pady=(0, 15))

    left = ctk.CTkFrame(body, fg_color=colors["bg_card"], corner_radius=12)
    left.pack(side="left", fill="y", expand=False, padx=(0, 10))

    right = ctk.CTkFrame(body, fg_color=colors["bg_card"], corner_radius=12)
    right.pack(side="right", fill="both", expand=True)

    # Layout: left fixed 420px, right flexible
    left.configure(width=430)
    left.pack_propagate(False)

    # ── LEFT: pattern + plan ─────────────────────────────────────────────
    ctk.CTkLabel(left, text="Fault pattern", font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(anchor="w", padx=15, pady=(14, 4))

    pat_frame = ctk.CTkFrame(left, fg_color="transparent")
    pat_frame.pack(fill="x", padx=15)

    diag = SchematicDiagnoser(BoardView.from_dict({"bbox": {}, "components": []}))
    pattern_ids = diag.pattern_ids()
    pattern_var = ctk.StringVar(value=pattern_ids[0] if pattern_ids else "")
    pattern_menu = ctk.CTkOptionMenu(pat_frame, values=pattern_ids,
                                     variable=pattern_var, width=240,
                                     fg_color=colors["bg_medium"], button_color=colors["accent"])
    pattern_menu.grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")

    def _gen_plan():
        if state["diag"] is None:
            status_var.set("Load a board first")
            return
        state["diag"].plan_for_pattern(pattern_var.get())
        _rebuild_measurements()
        status_var.set(f"Plan: {len(state['diag'].plan)} test points")

    ctk.CTkButton(pat_frame, text="Generate Test Plan", command=_gen_plan,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 13)).grid(row=0, column=1, pady=4, sticky="w")

    def _run_camera_evidence():
        from app.hardware.camera_tester import collect_camera_evidence
        status_var.set("Collecting camera evidence (ADB)…")
        app.update_idletasks()
        ev = collect_camera_evidence()
        txt = f"Camera evidence:\n  {ev.summary}\n"
        for e in ev.errors:
            txt += f"  ✗ {e}\n"
        for s in ev.provider_status:
            txt += f"  • {s}\n"
        report_box.delete("1.0", "end")
        report_box.insert("1.0", txt)
        status_var.set("Camera evidence collected")

    ctk.CTkButton(left, text="📷 Run Camera Evidence (ADB)", command=_run_camera_evidence,
                  fg_color=colors["bg_medium"], hover_color=colors["bg_light"],
                  font=("Segoe UI", 12, "bold")).pack(fill="x", padx=15, pady=(4, 8))

    ctk.CTkLabel(left, text="Measurements (multimeter readings in volts)",
                 font=("Segoe UI", 14, "bold"), text_color=colors["text"]).pack(
                 anchor="w", padx=15, pady=(6, 4))

    meas_scroll = ctk.CTkScrollableFrame(left, fg_color=colors["bg_medium"], corner_radius=10)
    meas_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 10))

    ctk.CTkLabel(left, text="Probe red-marked points on the board, enter readings,"
                            " press 'Update readings'.",
                 font=("Segoe UI", 11), text_color=colors["text_dim"],
                 wraplength=390, justify="left").pack(anchor="w", padx=15, pady=(0, 8))

    # ── RIGHT: image + net search + report ───────────────────────────────
    search_frame = ctk.CTkFrame(right, fg_color="transparent")
    search_frame.pack(fill="x", padx=12, pady=(10, 4))

    net_var = ctk.StringVar(value="AVDD")
    ctk.CTkEntry(search_frame, textvariable=net_var, width=180,
                 fg_color=colors["bg_medium"], border_color=colors["border"]).pack(
                 side="left", padx=(0, 8))

    def _highlight():
        if state["diag"] is None:
            status_var.set("Load a board first")
            return
        nets = state["board"].search_nets(net_var.get(), limit=10)
        if not nets:
            status_var.set(f"No net matches '{net_var.get()}'")
            return
        pts = state["board"].test_points_for_nets(nets[:6], max_per_net=1)
        png = state["board"].render_highlight(pts, _tmp_png())
        _show_image(png)
        status_var.set(f"Highlighted {len(pts)} points on {len(nets)} nets")

    ctk.CTkButton(search_frame, text="Highlight net", command=_highlight,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 12)).pack(side="left")

    image_box = ctk.CTkLabel(right, text="Load a board to see the schematic image.\n"
                                         "Highlight a net to mark its pads.",
                             font=("Segoe UI", 13), text_color=colors["text_dim"],
                             fg_color=(colors["bg_medium"], colors["bg_medium"]),
                             height=320)
    image_box.pack(fill="x", padx=12, pady=(4, 6))

    report_header = ctk.CTkFrame(right, fg_color="transparent")
    report_header.pack(fill="x", padx=12, pady=(4, 0))
    ctk.CTkLabel(report_header, text="Diagnosis report", font=("Segoe UI", 14, "bold"),
                 text_color=colors["text"]).pack(side="left")

    def _export():
        if state["diag"] is None or not state["diag"].pattern_id:
            status_var.set("Generate a plan first")
            return
        report = state["diag"].generate_report()
        out = Path(tempfile.gettempdir()) / "schematic_diagnosis_report.txt"
        out.write_text(report, encoding="utf-8")
        status_var.set(f"Report saved → {out}")
        report_box.delete("1.0", "end")
        report_box.insert("1.0", report)
        try:
            from app.gui import ui_utils
            ui_utils.notify(app, f"Saved: {out}")
        except Exception:
            pass

    ctk.CTkButton(report_header, text="Update readings", command=lambda: _apply_readings(),
                  fg_color=colors["bg_medium"], hover_color=colors["bg_light"],
                  font=("Segoe UI", 12, "bold")).pack(side="right", padx=(8, 0))
    ctk.CTkButton(report_header, text="Export report", command=_export,
                  fg_color=colors["accent"], hover_color=colors["accent_hover"],
                  font=("Segoe UI", 12, "bold")).pack(side="right")

    report_box = ctk.CTkTextbox(right, fg_color=colors["bg_medium"], corner_radius=10,
                                font=("Consolas", 12), text_color=colors["text"])
    report_box.pack(fill="both", expand=True, padx=12, pady=(6, 12))

    # ── helpers ───────────────────────────────────────────────────────────
    _entry_widgets = []  # (MeasuredPoint, CTkEntry, status label)

    def _tmp_png() -> str:
        return str(Path(tempfile.gettempdir()) / "mooxy_highlight.png")

    def _show_image(png_path: str):
        try:
            from PIL import Image
            img = Image.open(png_path)
            img.thumbnail((760, 420))
            photo = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            image_box.configure(image=photo, text="")
            image_box.image = photo
        except Exception:
            pass

    def _rebuild_measurements():
        for w in _entry_widgets:
            try:
                w[1].destroy()
                w[2].destroy()
                w[3].destroy()
            except Exception:
                pass
        _entry_widgets.clear()
        plan = state["diag"].plan
        if not plan:
            ctk.CTkLabel(meas_scroll, text="No test points matched on this board.",
                         text_color=colors["warning"]).pack(anchor="w", padx=6, pady=6)
            return
        for mp in plan:
            row = ctk.CTkFrame(meas_scroll, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=3)
            status_lbl = ctk.CTkLabel(row, text="○", width=3, font=("Segoe UI", 14),
                                      text_color=colors["text_dim"])
            status_lbl.grid(row=0, column=0, padx=(4, 4))
            t = f"{mp.point.net}  @{mp.point.component}.{mp.point.pin}"
            if mp.expected_v is not None:
                t += f"  (exp {mp.expected_v}V)"
            ctk.CTkLabel(row, text=t, width=180, anchor="w",
                         font=("Segoe UI", 12), text_color=colors["text"]).grid(
                         row=0, column=1, padx=(0, 6), sticky="w")
            entry = ctk.CTkEntry(row, width=72, placeholder_text="V",
                                 fg_color=colors["bg_medium"], border_color=colors["border"])
            entry.grid(row=0, column=2, padx=(0, 6))
            _entry_widgets.append((mp, entry, status_lbl, row))

    def _apply_readings():
        if state["diag"] is None:
            return
        for mp, entry, status_lbl, _row in _entry_widgets:
            raw = entry.get().strip()
            try:
                volts = float(raw)
            except ValueError:
                volts = None
            state["diag"].set_measurement(state["diag"].plan.index(mp), volts)
            status_lbl.configure(text=_status_icon(mp.status),
                                 text_color=_status_color(mp.status))
        report_box.delete("1.0", "end")
        report_box.insert("1.0", state["diag"].generate_report())
        status_var.set("Readings applied")

    def _status_icon(s: str) -> str:
        return {"OK": "✓", "ZERO": "✗", "LOW": "↘", "HIGH": "↗"}.get(s, "○")

    def _status_color(s: str) -> str:
        return ({"OK": "#2ed573", "ZERO": "#ff4757", "LOW": "#ffa502",
                 "HIGH": "#ff6b81"}.get(s) or colors["text_dim"])

    def _load_board():
        if not boards:
            status_var.set("No boardviews found in config/boardviews/")
            return
        path = _BOARDVIEW_DIR / board_var.get()
        try:
            bv = BoardView.load(path)
            state["board"] = bv
            state["diag"] = SchematicDiagnoser(bv)
            s = bv.summary()
            info_label.configure(
                text=f"{s['components']} comps · {s['pins']} pins · "
                     f"{s['nets_named']} nets · image {'✓' if s['image'] else '—'}")
            status_var.set(f"Board loaded: {path.name}")
            _gen_plan()
        except Exception as e:
            status_var.set(f"Load failed: {e}")

    board_menu.configure(command=lambda _v: _load_board())

    # Auto-load the first board if any exist
    if boards:
        board_var.set(boards[0].name)
        app.after(150, _load_board)
    else:
        info_label.configure(text="Put flat-dump JSONs in config/boardviews/ "
                                  "(e.g. POCO M2_flat.json, iphone12_flat_dump.json)")