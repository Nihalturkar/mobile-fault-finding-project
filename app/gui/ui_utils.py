"""Shared UI utilities for diagnostic test pages.

Extracts common patterns duplicated across all test pages:
- Color tag determination for log lines
- Tag setup on CTkTextbox widgets
- Thread-safe live text append with auto-coloring
- Clipboard copy and file-save helpers
- Safe main-thread scheduling
- Robotics HUD widgets (TechBanner, HudGauge, RadarSweep)
"""

import math
import tkinter as tk


def hud_mix(c1, c2, t):
    """Blend two #rrggbb colours (t=0 → c1, t=1 → c2)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def get_line_tag(text):
    """Determine color tag for a log line based on content keywords.

    Returns one of: 'fault', 'warning', 'ok', 'header', 'info', or None.
    """
    t = text.lower()
    if any(k in t for k in [
        "[xx]", "[!!]", "fault", "short", "critical", "leaky", "danger", "fail",
        "not found", "missing", "bad", "defective", "dead pixel",
    ]):
        return "fault"
    if any(k in t for k in [
        "warning", "open", "high", "low", "hot", "overcurrent",
        "suspect", "degraded", "worn",
    ]):
        return "warning"
    if any(k in t for k in [
        "[ok]", "ok", "good", "working", "normal", "healthy",
        "no fault", "clean", "pass", "detected", "active", "no issue",
    ]):
        return "ok"
    if any(k in t for k in [
        "===", "---", "========", "report", "summary", "analysis",
        "phase", "panel", "backlight", "touch", "dead pixel",
        "display", "battery", "sensor", "audio",
    ]):
        return "header"
    if any(k in t for k in [
        "checking", "reading", "scanning", "monitoring", "analysing",
        "detecting", "analyzing", "enumerating",
    ]):
        return "info"
    return None


def setup_report_tags(textbox, colors=None):
    """Setup color tags on a CTkTextbox for diagnostic output.

    Args:
        textbox: A CTkTextbox widget.
        colors: Optional dict of custom colors. Defaults are used if not provided.
    """
    default_colors = {
        "ok": "#34d399",
        "warning": "#fbbf24",
        "fault": "#ec4899",
        "info": "#a855f7",
        "header": "#ec4899",
        "dim": "#9a93b5",
    }
    if colors:
        default_colors.update(colors)

    tb = textbox._textbox
    tb.tag_configure("ok", foreground=default_colors["ok"])
    tb.tag_configure("warning", foreground=default_colors["warning"])
    tb.tag_configure("fault", foreground=default_colors["fault"])
    tb.tag_configure("info", foreground=default_colors["info"])
    tb.tag_configure("header", foreground=default_colors["header"],
                     font=("Consolas", 12, "bold"))
    tb.tag_configure("dim", foreground=default_colors["dim"])


def safe_after(app, fn):
    """Schedule fn on main thread only if widgets still exist.

    Wraps fn in a try/except so destroyed-widget errors are silently caught.

    Args:
        app: The main application object (must have app.content).
        fn: Callable to run on the main thread.
    """
    def _wrapped():
        try:
            fn()
        except Exception:
            pass
    try:
        if app.content.winfo_exists():
            app.content.after(0, _wrapped)
    except Exception:
        pass


def append_live(app, report_box, text, get_tag_fn=None):
    """Thread-safe append text to report box with auto-coloring.

    Must be called from any thread. Uses app.content.after(0, ...) for
    thread safety. Handles widget destruction gracefully.

    Args:
        app: The main application object (must have app.content).
        report_box: A CTkTextbox widget to append text to.
        text: The text line to append.
        get_tag_fn: Optional custom tag function. Defaults to get_line_tag.
    """
    tag_fn = get_tag_fn or get_line_tag

    def _do():
        try:
            report_box.configure(state="normal")
            tag = tag_fn(text)
            if tag:
                start = report_box._textbox.index("end-1c")
                report_box.insert("end", text + "\n")
                end = report_box._textbox.index("end-1c")
                report_box._textbox.tag_add(tag, start, end)
            else:
                report_box.insert("end", text + "\n")
            report_box.see("end")
        except Exception:
            pass

    try:
        app.content.after(0, _do)
    except Exception:
        pass


def append_live_lines(app, report_box, lines, get_tag_fn=None):
    """Thread-safe append multiple lines at once with auto-coloring.

    Args:
        app: The main application object (must have app.content).
        report_box: A CTkTextbox widget to append text to.
        lines: Iterable of text lines to append.
        get_tag_fn: Optional custom tag function. Defaults to get_line_tag.
    """
    tag_fn = get_tag_fn or get_line_tag

    def _do():
        try:
            report_box.configure(state="normal")
            for line in lines:
                tag = tag_fn(line)
                if tag:
                    start = report_box._textbox.index("end-1c")
                    report_box.insert("end", line + "\n")
                    end = report_box._textbox.index("end-1c")
                    report_box._textbox.tag_add(tag, start, end)
                else:
                    report_box.insert("end", line + "\n")
            report_box.see("end")
        except Exception:
            pass

    try:
        app.content.after(0, _do)
    except Exception:
        pass


def copy_report_to_clipboard(app, report_box, status_label=None, colors=None):
    """Copy report textbox content to clipboard.

    Args:
        app: The main application object.
        report_box: A CTkTextbox widget containing the report.
        status_label: Optional CTkLabel to show success message.
        colors: Optional color dict (needs 'success' key).
    """
    try:
        text = report_box.get("1.0", "end").strip()
        app.clipboard_clear()
        app.clipboard_append(text)
        if status_label and colors:
            status_label.configure(
                text="Report copied to clipboard!",
                text_color=colors.get("success", "#34d399"),
            )
    except Exception:
        pass


def save_report_to_file(app, report_box, default_prefix="report",
                        status_label=None, colors=None):
    """Save report textbox content to file with save dialog.

    Args:
        app: The main application object.
        report_box: A CTkTextbox widget containing the report.
        default_prefix: Default filename prefix (e.g. 'power_test_report').
        status_label: Optional CTkLabel to show success message.
        colors: Optional color dict (needs 'success' key).
    """
    try:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
            initialfile=f"{default_prefix}.txt",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report_box.get("1.0", "end"))
            if status_label and colors:
                status_label.configure(
                    text=f"Saved to: {path}",
                    text_color=colors.get("success", "#34d399"),
                )
    except Exception:
        pass


# ── robotics HUD widgets ─────────────────────────────────────────────────────

HUD_CYAN = "#22d3ee"
HUD_GRID = "#17223f"


class TechBanner:
    """An animated 'circuit board' banner: a scrolling grid with pulsing nodes,
    drifting data packets and a rotating core, with a title overlaid."""

    def __init__(self, parent, bg, accent=HUD_CYAN, title="", subtitle="", height=98):
        self.bg = bg
        self.accent = accent
        self.title = title
        self.subtitle = subtitle
        self.h = height
        self.phase = 0.0
        self.canvas = tk.Canvas(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        # fixed pseudo-random node lattice (so it doesn't jump every frame)
        self.nodes = [(0.12, 0.3), (0.22, 0.7), (0.34, 0.45), (0.46, 0.2),
                      (0.52, 0.75), (0.63, 0.5), (0.72, 0.28), (0.8, 0.66)]
        self._tick()

    def _tick(self):
        try:
            if not self.canvas.winfo_exists():
                return
        except Exception:
            return
        c = self.canvas
        w = self.canvas.winfo_width()
        if w <= 2:
            c.after(60, self._tick)
            return
        h = self.h
        c.delete("all")
        self.phase += 0.03
        acc = self.accent
        bg = self.bg

        # scrolling grid
        gsz = 28
        offx = (self.phase * 16) % gsz
        gcol = hud_mix(bg, acc, 0.09)
        x = -offx
        while x < w:
            c.create_line(x, 0, x, h, fill=gcol, width=1)
            x += gsz
        y = 0
        while y < h:
            c.create_line(0, y, w, y, fill=gcol, width=1)
            y += gsz

        # pulsing circuit nodes + short traces
        for i, (nx, ny) in enumerate(self.nodes):
            px, py = nx * w, ny * h
            pulse = 0.4 + 0.6 * ((math.sin(self.phase * 2.5 + i * 1.3) + 1) / 2)
            c.create_line(px - 18, py, px, py, fill=hud_mix(bg, acc, 0.2 + 0.2 * pulse), width=1)
            r = 2 + 1.6 * pulse
            c.create_oval(px - r, py - r, px + r, py + r,
                          fill=hud_mix(bg, acc, 0.35 + 0.5 * pulse), outline="")

        # drifting data packets along a mid trace
        ty = h * 0.5
        for k in range(4):
            dx = (self.phase * 60 + k * (w / 4)) % (w + 40) - 20
            c.create_rectangle(dx, ty - 1, dx + 10, ty + 1,
                               fill=hud_mix(bg, acc, 0.7), outline="")

        # rotating hex core on the right
        hx, hy, R = w - 56, h / 2, 26
        pts = []
        for k in range(6):
            a = self.phase * 0.8 + math.radians(60 * k)
            pts += [hx + R * math.cos(a), hy + R * math.sin(a)]
        c.create_polygon(*pts, outline=hud_mix(bg, acc, 0.55), fill="", width=1)
        c.create_oval(hx - 5, hy - 5, hx + 5, hy + 5, fill=hud_mix(acc, "#ffffff", 0.3), outline="")

        # title + subtitle
        if self.title:
            c.create_text(24, h / 2 - (10 if self.subtitle else 0), anchor="w", text=self.title,
                          fill="#ffffff", font=("Segoe UI", 22, "bold"))
        if self.subtitle:
            c.create_text(26, h / 2 + 16, anchor="w", text=self.subtitle,
                          fill=hud_mix(bg, acc, 0.85), font=("Consolas", 11, "bold"))

        c.after(50, self._tick)


class HudGauge:
    """A semicircular robotics dial — arc fill + needle + value readout."""

    def __init__(self, parent, bg, label, value, text, color, size=130):
        self.bg = bg
        self.label = label
        self.target = max(0.0, min(1.0, value))
        self.value = 0.0            # eases up to target
        self.text = text
        self.color = color
        self.size = size
        self.phase = 0.0
        self.canvas = tk.Canvas(parent, width=size, height=int(size * 0.92),
                                bg=bg, highlightthickness=0, bd=0)
        self._tick()

    def _tick(self):
        try:
            if not self.canvas.winfo_exists():
                return
        except Exception:
            return
        c = self.canvas
        c.delete("all")
        s = self.size
        cx, cy = s / 2, s * 0.58
        r = s * 0.38
        self.phase += 0.1
        self.value += (self.target - self.value) * 0.12       # needle easing
        col = self.color

        # background track (top semicircle)
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=0, extent=180,
                     style="arc", outline=hud_mix(self.bg, "#ffffff", 0.08), width=7)
        # ticks
        for k in range(11):
            a = math.radians(180 - k * 18)
            r1, r2 = r + 5, r + 9
            c.create_line(cx + r1 * math.cos(a), cy - r1 * math.sin(a),
                          cx + r2 * math.cos(a), cy - r2 * math.sin(a),
                          fill=hud_mix(self.bg, col, 0.4), width=1)
        # value arc (from left toward the needle)
        ang = 180 * (1 - self.value)
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=ang, extent=180 - ang,
                     style="arc", outline=col, width=7)
        # needle
        a = math.radians(ang)
        nx, ny = cx + (r - 4) * math.cos(a), cy - (r - 4) * math.sin(a)
        c.create_line(cx, cy, nx, ny, fill=hud_mix(col, "#ffffff", 0.3), width=2)
        glow = 0.5 + 0.5 * ((math.sin(self.phase) + 1) / 2)
        c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                      fill=hud_mix(self.bg, col, 0.5 + 0.5 * glow), outline="")
        # readouts
        c.create_text(cx, cy + 6, text=self.text, fill="#ffffff", font=("Segoe UI", 15, "bold"))
        c.create_text(cx, cy + 26, text=self.label, fill=hud_mix(self.bg, "#ffffff", 0.6),
                      font=("Consolas", 9, "bold"))

        c.after(45, self._tick)


class RadarSweep:
    """A compact sonar/radar dish — rotating sweep with a fading trail and blips.
    Set `.active = False` to drop to a slow idle spin."""

    def __init__(self, parent, bg, accent=HUD_CYAN, size=30):
        self.bg = bg
        self.accent = accent
        self.size = size
        self.phase = 0.0
        self.active = True
        self.blips = [(0.7, 40), (1.9, 70), (3.4, 25), (4.8, 60), (5.6, 85)]  # (angle, pct radius)
        self.canvas = tk.Canvas(parent, width=size, height=size, bg=bg,
                                highlightthickness=0, bd=0)
        self._tick()

    def _tick(self):
        try:
            if not self.canvas.winfo_exists():
                return
        except Exception:
            return
        c = self.canvas
        c.delete("all")
        s = self.size
        cx = cy = s / 2
        R = s / 2 - 2
        acc = self.accent
        self.phase += 0.22 if self.active else 0.05
        sweep = self.phase % (2 * math.pi)

        # rings + crosshair
        for rr in (R, R * 0.66, R * 0.33):
            c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                          outline=hud_mix(self.bg, acc, 0.3), width=1)
        c.create_line(cx - R, cy, cx + R, cy, fill=hud_mix(self.bg, acc, 0.2))
        c.create_line(cx, cy - R, cx, cy + R, fill=hud_mix(self.bg, acc, 0.2))

        # fading sweep trail
        for j in range(8):
            a = sweep - j * 0.12
            col = hud_mix(self.bg, acc, 0.6 * (1 - j / 8))
            c.create_line(cx, cy, cx + R * math.cos(a), cy + R * math.sin(a), fill=col, width=1)
        # leading edge
        c.create_line(cx, cy, cx + R * math.cos(sweep), cy + R * math.sin(sweep),
                      fill=hud_mix(acc, "#ffffff", 0.3), width=1)

        # blips glow when the sweep passes over them
        for ba, bp in self.blips:
            diff = (sweep - ba) % (2 * math.pi)
            lit = max(0.0, 1 - diff / 0.8) if diff < 0.8 else 0.0
            if lit > 0.02 and self.active:
                br = R * bp / 100
                bx, by = cx + br * math.cos(ba), cy + br * math.sin(ba)
                c.create_oval(bx - 2, by - 2, bx + 2, by + 2,
                              fill=hud_mix(self.bg, "#34d399", 0.4 + 0.6 * lit), outline="")

        c.after(50, self._tick)
