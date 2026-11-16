"""Shared UI utilities for diagnostic test pages.

Extracts common patterns duplicated across all test pages:
- Color tag determination for log lines
- Tag setup on CTkTextbox widgets
- Thread-safe live text append with auto-coloring
- Clipboard copy and file-save helpers
- Safe main-thread scheduling
"""


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
        "ok": "#2ed573",
        "warning": "#ffa502",
        "fault": "#e94560",
        "info": "#1e90ff",
        "header": "#e94560",
        "dim": "#8892b0",
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
                text_color=colors.get("success", "#2ed573"),
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
                    text_color=colors.get("success", "#2ed573"),
                )
    except Exception:
        pass
