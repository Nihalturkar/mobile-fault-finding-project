"""
Section 6 — Jack UI page.

  ┌──────────────────────────────────────────────────────────┐
  │ (orb)  JACK                     [device chip] [New chat] │
  │        status: Ready / Soch raha hoon / tool…            │
  ├──────────────────────────────────────────────────────────┤
  │ chat bubbles (scrollable)                                │
  ├──────────────────────────────────────────────────────────┤
  │ [quick chips…]                                           │
  │ [🎤] [ type here…                              ] [Send]  │
  └──────────────────────────────────────────────────────────┘

The brain + chat transcript live on `app.jack_state`, so memory survives page
switches. The page uses its own full-height frame instead of the app's
scrollable content area (a chat needs its own scroller).
"""

import math
import re
import threading
import time
import tkinter as tk
from collections import deque

import customtkinter as ctk

ORB_SIZE = 140
QUICK_PROMPTS = [
    "🔌 Connected device check karo",
    "📄 Last scan ka result batao",
    "💀 Phone dead hai, 0.00A le raha hai",
    "🔋 Charging nahi ho rahi",
]

STATE_COLORS = {          # orb core colour per state
    "idle": "#a855f7",
    "thinking": "#a78bfa",
    "tool": "#fbbf24",
    "speaking": "#34d399",
    "listening": "#ec4899",
    "error": "#f43f5e",
}


# ── helpers ────────────────────────────────────────────────────────────────

def _blend(c1: str, c2: str, t: float) -> str:
    """Mix two #rrggbb colours (t=0 → c1, t=1 → c2)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text.strip()


_INLINE_RE = re.compile(r"(\*\*(.+?)\*\*|`([^`]+)`)")


def _inline_runs(s, runs):
    pos = 0
    for m in _INLINE_RE.finditer(s):
        if m.start() > pos:
            runs.append((s[pos:m.start()], None))
        if m.group(2) is not None:
            runs.append((m.group(2), "bold"))
        else:
            runs.append((m.group(3), "code"))
        pos = m.end()
    if pos < len(s):
        runs.append((s[pos:], None))


def _md_runs(text):
    """Parse Jack's reply into (text, tag) runs + a list of fenced command blocks.

    Tags: 'h' heading, 'bold', 'code' inline, 'codeblock' fenced, 'bullet' marker, None plain.
    """
    runs, codes, code_buf, in_code = [], [], [], False
    for line in (text or "").replace("\r", "").split("\n"):
        if line.lstrip().startswith("```"):
            if in_code:
                block = "\n".join(code_buf).rstrip()
                if block:
                    codes.append(block)
                    runs.append((block + "\n", "codeblock"))
                code_buf, in_code = [], False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        mh = re.match(r"^(#{1,3})\s+(.*)$", line)
        if mh:
            runs.append((mh.group(2) + "\n", "h"))
            continue
        mb = re.match(r"^\s*[-*•]\s+(.*)$", line)
        if mb:
            runs.append(("  •  ", "bullet"))
            _inline_runs(mb.group(1), runs)
            runs.append(("\n", None))
            continue
        mn = re.match(r"^\s*(\d+)[.)]\s+(.*)$", line)
        if mn:
            runs.append((f"  {mn.group(1)}.  ", "bullet"))
            _inline_runs(mn.group(2), runs)
            runs.append(("\n", None))
            continue
        _inline_runs(line, runs)
        runs.append(("\n", None))
    if in_code and code_buf:
        block = "\n".join(code_buf).rstrip()
        if block:
            codes.append(block)
            runs.append((block + "\n", "codeblock"))
    while runs and runs[-1][0] == "\n":        # trim trailing blank lines
        runs.pop()
    return runs, codes


def _get_state(app):
    if not hasattr(app, "jack_state"):
        try:
            from app.jack.config import load_settings
            s = load_settings()
        except Exception:
            s = {}
        app.jack_state = {"brain": None, "messages": [], "busy": False, "device": "",
                          # voice (Sections 4+5) — survives page switches
                          "voice_on": bool(s.get("voice_reply", True)),
                          "wake_on": bool(s.get("wake_word_enabled", False)),
                          "listening": False, "listen_stop": None,
                          "speaker": None, "wake": None,
                          "ui": {}}          # callbacks of the currently shown Jack page
    return app.jack_state


def _save_voice_setting(key: str, value) -> None:
    try:
        from app.jack.config import load_settings, save_settings
        s = load_settings()
        s[key] = value
        save_settings(s)
    except Exception as e:
        print(f"[Jack] could not save {key}: {e}")


def _ui_call(app, name: str, *args):
    """Run a callback of the live Jack page on the Tk thread (no-op if page closed)."""
    def go():
        fn = app.jack_state["ui"].get(name)
        if fn:
            try:
                fn(*args)
            except Exception as e:
                print(f"[Jack] ui {name} failed: {e}")
    try:
        app.after(0, go)
    except Exception:
        pass


def _ensure_voice(app):
    """Create the speaker + wake-word loop once per app run."""
    state = _get_state(app)
    if state["speaker"] is None:
        from app.jack.voice import Speaker
        state["speaker"] = Speaker(on_start=lambda: _ui_call(app, "speaking", True),
                                   on_end=lambda: _ui_call(app, "speaking", False))
        if state.get("voice_on"):
            state["speaker"].prewarm()      # hide the first-call network lag
    if state["wake"] is None:
        from app.jack.voice import WakeWordLoop

        def on_wake(cmd):
            def go():
                page = getattr(app, "jack_page_frame", None)
                try:
                    shown = page is not None and page.winfo_exists()
                except Exception:
                    shown = False
                if not shown:                      # Jarvis-style: works from any page
                    app.show_jack()
                    app.after(500, lambda: _ui_call(app, "wake", cmd))
                else:
                    _ui_call(app, "wake", cmd)
            app.after(0, go)

        def on_error(msg):
            _ui_call(app, "voice_error", msg)
            if msg.startswith("Wake word band"):
                state["wake_on"] = False
                _ui_call(app, "wake_refresh")

        sp = state["speaker"]
        state["wake"] = WakeWordLoop(
            on_wake=on_wake, on_error=on_error,
            is_paused=lambda: state["busy"] or state["listening"] or sp.speaking or not state["wake_on"])
    return state["speaker"], state["wake"]


# ── animated orb ───────────────────────────────────────────────────────────

class JackOrb:
    """A pulsing 'arc reactor' style orb drawn on a tk.Canvas."""

    BARS = 36

    def __init__(self, parent, bg: str):
        self.bg = bg
        self.canvas = tk.Canvas(parent, width=ORB_SIZE, height=ORB_SIZE, bg=bg,
                                highlightthickness=0, bd=0, cursor="hand2")
        self.state = "idle"
        self.phase = 0.0
        self.level = 0.0            # 0..1 — mic level while listening (set from any thread)
        self._lvl = 0.0             # smoothed
        self._col = STATE_COLORS["idle"]
        self.hover = False
        self.canvas.bind("<Enter>", lambda e: setattr(self, "hover", True))
        self.canvas.bind("<Leave>", lambda e: setattr(self, "hover", False))
        self._tick()

    def set_state(self, state: str):
        self.state = state if state in STATE_COLORS else "idle"

    def _tick(self):
        try:
            if not self.canvas.winfo_exists():
                return
        except Exception:
            return
        c = self.canvas
        c.delete("all")
        cx = cy = ORB_SIZE / 2
        # colour glides to the new state's colour instead of jumping
        self._col = _blend(self._col, STATE_COLORS[self.state], 0.15)
        core = self._col
        speed = {"idle": 0.05, "thinking": 0.16, "tool": 0.2, "speaking": 0.28,
                 "listening": 0.22, "error": 0.08}[self.state]
        self.phase += speed
        pulse = (math.sin(self.phase) + 1) / 2          # 0..1

        # audio level: real mic level while listening, synthetic voice while speaking
        if self.state == "listening":
            target = self.level
        elif self.state == "speaking":
            target = 0.35 + 0.3 * abs(math.sin(self.phase * 1.7)) * abs(math.sin(self.phase * 0.6 + 1))
        else:
            target = 0.0
        self._lvl += (target - self._lvl) * 0.35

        # soft glow
        for i in range(7, 0, -1):
            r = 24 + i * 5 + pulse * 3 + self._lvl * 8
            col = _blend(self.bg, core, 0.06 + (7 - i) * 0.05 * (0.6 + 0.4 * pulse))
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=col, outline="")

        # outer HUD ring with ticks, slowly rotating
        R = ORB_SIZE / 2 - 4
        hud = _blend(self.bg, core, 0.55 if self.hover else 0.35)
        rot = self.phase * 6
        for k in range(4):
            c.create_arc(cx - R, cy - R, cx + R, cy + R, start=rot + k * 90 + 8, extent=60,
                         style="arc", outline=hud, width=2)
        for k in range(24):
            a = math.radians(-rot * 0.6 + k * 15)
            r1, r2 = R - 7, R - (11 if k % 6 == 0 else 9)
            c.create_line(cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                          cx + r2 * math.cos(a), cy + r2 * math.sin(a), fill=hud, width=1)

        # equalizer bars around the core (voice), or spinning arcs (thinking / tool)
        if self._lvl > 0.02:
            base = 34
            for k in range(self.BARS):
                a = 2 * math.pi * k / self.BARS + self.phase * 0.15
                wobble = 0.55 + 0.45 * math.sin(self.phase * 2.3 + k * 1.3) * math.cos(self.phase + k * 0.7)
                ln = 4 + self._lvl * 22 * abs(wobble)
                c.create_line(cx + base * math.cos(a), cy + base * math.sin(a),
                              cx + (base + ln) * math.cos(a), cy + (base + ln) * math.sin(a),
                              fill=_blend(core, "#ffffff", 0.3), width=3, capstyle="round")
        elif self.state in ("thinking", "tool"):
            deg = (self.phase * 40) % 360
            for k, (rad, extent, w) in enumerate(((50, 80, 3), (43, 50, 2))):
                start = deg * (1 if k == 0 else -1.4)
                for off in (0, 180):
                    c.create_arc(cx - rad, cy - rad, cx + rad, cy + rad, start=start + off, extent=extent,
                                 style="arc", outline=_blend(core, "#ffffff", 0.35), width=w)
            # orbiting particles
            for k in range(3):
                a = self.phase * (0.9 + k * 0.35) + k * 2.1
                pr = 38 + 6 * math.sin(self.phase + k)
                px, py = cx + pr * math.cos(a), cy + pr * math.sin(a)
                c.create_oval(px - 2.5, py - 2.5, px + 2.5, py + 2.5, fill="#ffffff", outline="")
        else:
            c.create_oval(cx - 48, cy - 48, cx + 48, cy + 48, outline=_blend(self.bg, core, 0.5), width=1)

        # core
        r = 21 + pulse * 3 + self._lvl * 5
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=_blend(core, "#ffffff", 0.25), outline="")
        r2 = r * 0.55
        c.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, fill=_blend(core, "#ffffff", 0.75), outline="")
        if self.hover and self.state == "speaking":
            c.create_text(cx, cy + 52, text="click = chup", fill=_blend(core, "#ffffff", 0.6),
                          font=("Segoe UI", 8))

        c.after(40, self._tick)


# ── page ───────────────────────────────────────────────────────────────────

def render_jack_page(app):
    colors = app.colors
    state = _get_state(app)

    # Full-height page: hide the app's scrollable content while Jack is open.
    app.content.pack_forget()
    page = ctk.CTkFrame(app.main_area, fg_color=colors["bg_dark"], corner_radius=0)
    page.pack(fill="both", expand=True, before=app.statusbar)
    app.jack_page_frame = page

    # ── header ──
    header = ctk.CTkFrame(page, fg_color=colors["bg_medium"], corner_radius=14)
    header.pack(fill="x", padx=20, pady=(16, 10))

    orb = JackOrb(header, bg=colors["bg_medium"])
    orb.canvas.pack(side="left", padx=(14, 6), pady=8)

    title_box = ctk.CTkFrame(header, fg_color="transparent")
    title_box.pack(side="left", fill="y", pady=16)
    ctk.CTkLabel(title_box, text="J A C K", font=("Segoe UI", 30, "bold"),
                 text_color=colors["text"]).pack(anchor="w")
    ctk.CTkLabel(title_box, text="Mooxy AI repair assistant", font=("Segoe UI", 13),
                 text_color=colors["text_dim"]).pack(anchor="w")
    status_lbl = ctk.CTkLabel(title_box, text="● Starting…", font=("Segoe UI", 13, "bold"),
                              text_color=colors["info"])
    status_lbl.pack(anchor="w", pady=(6, 0))
    pill_row = ctk.CTkFrame(title_box, fg_color="transparent")
    pill_row.pack(anchor="w", pady=(6, 0))

    right = ctk.CTkFrame(header, fg_color="transparent")
    right.pack(side="right", padx=16, pady=16, fill="y")
    device_lbl = ctk.CTkLabel(right, text="🔌 Device check ho raha hai…", font=("Segoe UI", 12),
                              text_color=colors["text_dim"], fg_color=colors["bg_light"],
                              corner_radius=8, padx=10, pady=4)
    device_lbl.pack(anchor="e")
    btn_row = ctk.CTkFrame(right, fg_color="transparent")
    btn_row.pack(anchor="e", pady=(10, 0))

    # ── chat area ──
    chat = ctk.CTkScrollableFrame(page, fg_color=colors["bg_dark"],
                                  scrollbar_button_color=colors["bg_light"])
    chat.pack(fill="both", expand=True, padx=20)

    # floating "jump to latest" button — shows only when scrolled up
    jump_btn = ctk.CTkButton(page, text="⤓  Latest", width=96, height=30, corner_radius=15,
                             font=("Segoe UI", 11, "bold"), fg_color=colors["info"],
                             hover_color="#c084fc", text_color="#ffffff",
                             command=lambda: (chat._parent_canvas.yview_moveto(1.0)))

    def _watch_scroll():
        try:
            if not chat.winfo_exists():
                return
            _, bot = chat._parent_canvas.yview()
            if bot < 0.985:
                jump_btn.place(relx=0.93, rely=0.90, anchor="se")
            else:
                jump_btn.place_forget()
        except Exception:
            pass
        page.after(350, _watch_scroll)
    page.after(600, _watch_scroll)

    # ── input area ──
    bottom = ctk.CTkFrame(page, fg_color="transparent")
    bottom.pack(fill="x", padx=20, pady=(6, 14))
    scan_row = ctk.CTkFrame(bottom, fg_color="transparent")
    scan_row.pack(fill="x", pady=(0, 6))
    chips = ctk.CTkFrame(bottom, fg_color="transparent")
    chips.pack(fill="x", pady=(0, 8))
    input_row = ctk.CTkFrame(bottom, fg_color=colors["bg_medium"], corner_radius=14)
    input_row.pack(fill="x")

    mic_btn = ctk.CTkButton(input_row, text="🎤", width=46, height=42, font=("Segoe UI Emoji", 18),
                            fg_color=colors["bg_light"], hover_color=colors["border"])
    mic_btn.pack(side="left", padx=(10, 6), pady=10)
    entry = ctk.CTkEntry(input_row, placeholder_text="Jack se poocho…  (Enter = send)",
                         height=42, font=("Segoe UI", 14), fg_color=colors["bg_light"],
                         border_color=colors["border"])
    entry.pack(side="left", fill="x", expand=True, pady=10)
    send_btn = ctk.CTkButton(input_row, text="Send ➤", width=96, height=42, font=("Segoe UI", 14, "bold"),
                             fg_color=colors["accent"], hover_color=colors["accent_hover"])
    send_btn.pack(side="left", padx=10, pady=10)

    # ── UI helpers (all must run on the Tk thread) ──
    def alive() -> bool:
        try:
            return page.winfo_exists()
        except Exception:
            return False

    def set_status(text: str, kind: str = "idle"):
        if not alive():
            return
        col = {"idle": colors["success"], "thinking": "#a78bfa", "tool": colors["warning"],
               "error": colors["accent"]}.get(kind, colors["info"])
        status_lbl.configure(text=f"● {text}", text_color=col)
        orb.set_state(kind if kind in STATE_COLORS else "idle")

    def scroll_bottom():
        try:
            chat.after(60, lambda: chat._parent_canvas.yview_moveto(1.0))
        except Exception:
            pass

    bodies = []          # [{"w","kind","user"}] — re-flowed when the window is resized

    def wrap_px(is_user: bool = False) -> int:
        w = chat.winfo_width()
        w = w if w > 50 else 900
        return max(320, int(w * (0.55 if is_user else 0.72)))

    def rewrap(_e=None):
        if rewrap_job[0]:
            try:
                chat.after_cancel(rewrap_job[0])
            except Exception:
                pass

        def go():
            for ent in list(bodies):
                w = ent["w"]
                try:
                    if not w.winfo_exists():
                        bodies.remove(ent)
                        continue
                    if ent["kind"] == "label":
                        w.configure(wraplength=wrap_px(ent["user"]))
                    else:
                        w.configure(width=jack_chars())
                        _fit(w)
                except Exception:
                    pass
        rewrap_job[0] = chat.after(140, go)
    rewrap_job = [None]
    chat.bind("<Configure>", rewrap, add="+")

    import tkinter.font as _tkfont
    _jack_font = _tkfont.Font(family="Segoe UI", size=14)

    def jack_chars() -> int:
        cw = _jack_font.measure("0") or 8
        return max(30, min(96, wrap_px(False) // cw))

    def _fit(tb):
        try:
            tb.configure(state="normal")
            tb.update_idletasks()
            cnt = tb.count("1.0", "end-1c", "displaylines")
            lines = cnt[0] if isinstance(cnt, (tuple, list)) else (cnt or 1)
        except Exception:
            try:
                lines = int(tb.index("end-1c").split(".")[0])
            except Exception:
                lines = 1
        try:
            tb.configure(height=max(1, int(lines)), state="disabled")
        except Exception:
            pass

    def _rich_tags(tb):
        tb.tag_configure("bold", font=("Segoe UI", 14, "bold"))
        tb.tag_configure("h", font=("Segoe UI", 15, "bold"), foreground="#c4b2ff", spacing1=5, spacing3=2)
        tb.tag_configure("code", font=("Consolas", 12), foreground="#f3b765")
        tb.tag_configure("codeblock", font=("Consolas", 12), foreground="#e3dcff",
                         background=colors["bg_dark"], lmargin1=12, lmargin2=12, spacing1=3, spacing3=3)
        tb.tag_configure("bullet", foreground="#f472b6", font=("Segoe UI", 14, "bold"))

    def render_rich(tb, runs, animate, done):
        _rich_tags(tb)
        if not animate:
            tb.configure(state="normal")
            for t, tag in runs:
                tb.insert("end", t, (tag,) if tag else ())
            _fit(tb)
            if done:
                done()
            return
        total = sum(len(t) for t, _ in runs) or 1
        step = max(2, total // 80)
        idx, n = [0, 0], [0]

        def tick():
            try:
                if not tb.winfo_exists():
                    return
            except Exception:
                return
            tb.configure(state="normal")
            budget, ri, off = step, idx[0], idx[1]
            while budget > 0 and ri < len(runs):
                t, tag = runs[ri]
                take = t[off:off + budget]
                tb.insert("end", take, (tag,) if tag else ())
                off += len(take)
                budget -= len(take)
                if off >= len(t):
                    ri, off = ri + 1, 0
            idx[0], idx[1], n[0] = ri, off, n[0] + 1
            if n[0] % 3 == 0:
                _fit(tb)
                scroll_bottom()
            else:
                tb.configure(state="disabled")
            if ri < len(runs):
                tb.after(16, tick)
            else:
                _fit(tb)
                scroll_bottom()
                if done:
                    done()
        tick()

    def add_bubble(role: str, text: str, meta: str = "", animate: bool = False, speech: str = ""):
        is_user = role == "user"
        clear_hero()
        row = ctk.CTkFrame(chat, fg_color="transparent")
        row.pack(fill="x", pady=7)
        if not is_user:                       # avatar
            av = tk.Canvas(row, width=34, height=34, bg=colors["bg_dark"], highlightthickness=0)
            av.create_oval(2, 2, 32, 32, fill=_blend(colors["bg_dark"], "#a855f7", 0.35), outline="#a855f7")
            av.create_oval(11, 11, 23, 23, fill="#d8c7ff", outline="")
            av.pack(side="left", anchor="n", padx=(4, 6), pady=4)
        bubble = ctk.CTkFrame(row, corner_radius=16,
                              fg_color=colors["accent"] if is_user else colors["bg_card"],
                              border_width=0 if is_user else 1,
                              border_color=_blend(colors["bg_card"], "#a855f7", 0.35))
        bubble.pack(side="right" if is_user else "left", padx=(120, 6) if is_user else (0, 70))

        if is_user:
            body = ctk.CTkLabel(bubble, text=text, font=("Segoe UI", 14), text_color="#ffffff",
                                justify="left", anchor="w", wraplength=wrap_px(True))
            body.pack(anchor="w", padx=14, pady=10)
            bodies.append({"w": body, "kind": "label", "user": True})
            scroll_bottom()
            return bubble

        head = ctk.CTkFrame(bubble, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(head, text="Jack", font=("Segoe UI", 12, "bold"),
                     text_color=colors["info"]).pack(side="left")
        ctk.CTkLabel(head, text="  " + time.strftime("%H:%M"), font=("Segoe UI", 10),
                     text_color=colors["text_dim"]).pack(side="left")

        runs, codes = _md_runs(text)
        tb = tk.Text(bubble, wrap="word", bd=0, highlightthickness=0, relief="flat",
                     bg=colors["bg_card"], fg=colors["text"], font=("Segoe UI", 14),
                     padx=0, pady=0, cursor="arrow", width=jack_chars(), height=1,
                     spacing1=2, spacing3=3, insertwidth=0, selectbackground="#4c3d7a")
        tb.pack(anchor="w", padx=14, pady=(4, 6))
        bodies.append({"w": tb, "kind": "text", "user": False})

        foot = ctk.CTkFrame(bubble, fg_color="transparent")
        if meta:
            ctk.CTkLabel(foot, text=meta, font=("Segoe UI", 10),
                         text_color=colors["text_dim"]).pack(side="left", padx=4)

        def action(icon, tip, cmd):
            b = ctk.CTkButton(foot, text=icon, width=30, height=24, font=("Segoe UI Emoji", 12),
                              fg_color="transparent", hover_color=colors["bg_light"], command=cmd)
            b.pack(side="right", padx=1)
            b.bind("<Enter>", lambda e: app.update_status(tip))

        action("📋", "Copy pura jawab", lambda t=text: _copy_text(t))
        action("🔊", "Dobara suno", lambda s=speech or text: speak(s, force=True))
        action("🔄", "Dobara jawab do", lambda: regenerate())
        if codes:
            action("⌨", "Command copy karo", lambda c="\n".join(codes): _copy_text(c, "Command copy ✓"))

        def show_foot():
            try:
                foot.pack(fill="x", padx=10, pady=(0, 8))
            except Exception:
                pass

        render_rich(tb, runs, animate, show_foot)
        scroll_bottom()
        return bubble

    def _copy_text(t, msg="Copy ho gaya ✓"):
        try:
            app.clipboard_clear()
            app.clipboard_append(t)
            set_status(msg, "idle")
        except Exception:
            pass

    def add_activity_bubble():
        """Temporary 'thinking' bubble — animated dots + elapsed time + live steps."""
        clear_hero()
        row = ctk.CTkFrame(chat, fg_color="transparent")
        row.pack(fill="x", pady=7)
        box = ctk.CTkFrame(row, corner_radius=16, fg_color=colors["bg_medium"],
                           border_width=1, border_color="#a78bfa")
        box.pack(side="left", padx=(44, 80))
        top = ctk.CTkFrame(box, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 0))
        dots = tk.Canvas(top, width=44, height=14, bg=colors["bg_medium"], highlightthickness=0)
        dots.pack(side="left")
        title = ctk.CTkLabel(top, text="Jack soch raha hai", font=("Segoe UI", 13, "bold"),
                             text_color="#c4b5fd")
        title.pack(side="left", padx=(6, 10))
        timer = ctk.CTkLabel(top, text="0.0s", font=("Consolas", 11), text_color=colors["text_dim"])
        timer.pack(side="left")
        lbl = ctk.CTkLabel(box, text="", font=("Segoe UI", 12),
                           text_color=colors["text_dim"], justify="left", anchor="w")
        lbl.pack(anchor="w", padx=14, pady=(2, 10))
        t0 = time.time()
        ph = [0.0]

        def anim():
            try:
                if not dots.winfo_exists():
                    return
            except Exception:
                return
            ph[0] += 0.35
            dots.delete("all")
            for k in range(3):
                y = 7 - 3.5 * max(0.0, math.sin(ph[0] - k * 0.9))
                col = _blend(colors["bg_medium"], "#c4b5fd", 0.45 + 0.55 * max(0.0, math.sin(ph[0] - k * 0.9)))
                dots.create_oval(4 + k * 14 - 4, y - 4, 4 + k * 14 + 4, y + 4, fill=col, outline="")
            timer.configure(text=f"{time.time() - t0:.1f}s")
            dots.after(50, anim)
        anim()
        scroll_bottom()
        return row, lbl

    def set_busy(busy: bool):
        state["busy"] = busy
        if not alive():
            return
        send_btn.configure(state="disabled" if busy else "normal")
        entry.configure(state="disabled" if busy else "normal")
        for b in scan_buttons:
            b.configure(state="disabled" if busy else "normal")
        if not busy:
            entry.focus_set()

    # ── live scan log (same colours as HW Detect / ADB Detect pages) ──
    def _line_tag(text):
        t = text.lower()
        if any(k in t for k in ["fault", "🔴", "critical", "danger", "❌", "[xx]"]):
            return "fault"
        if any(k in t for k in ["warning", "🟡", "⚠️", "[!!]"]):
            return "warning"
        if any(k in t for k in ["✅", "[ok]", "ok", "pass", "working", "healthy", "clean boot"]):
            return "ok"
        if any(k in t for k in ["═══", "===", "───", "phase", "report"]):
            return "header"
        if any(k in t for k in ["🔍", "listening", "boot the phone"]):
            return "info"
        return None

    def add_scan_log(title):
        """Bubble with a live, colour-coded report box + progress bar."""
        row = ctk.CTkFrame(chat, fg_color="transparent")
        row.pack(fill="x", pady=6)
        box = ctk.CTkFrame(row, corner_radius=14, fg_color=colors["bg_card"],
                           border_width=1, border_color=colors["warning"])
        box.pack(fill="x", padx=(6, 40))
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(head, text=f"📟 {title}", font=("Segoe UI", 13, "bold"),
                     text_color=colors["warning"]).pack(side="left")
        line_count = ctk.CTkLabel(head, text="0 lines", font=("Segoe UI", 11), text_color=colors["text_dim"])
        line_count.pack(side="right")
        bar = ctk.CTkProgressBar(box, height=10, progress_color=colors["warning"], fg_color=colors["bg_light"])
        bar.set(0)
        bar.pack(fill="x", padx=14, pady=(2, 2))
        msg = ctk.CTkLabel(box, text="Starting…", font=("Segoe UI", 11), text_color=colors["text_dim"])
        msg.pack(anchor="w", padx=14)
        tb = ctk.CTkTextbox(box, height=300, font=("Consolas", 12), fg_color=colors["bg_dark"],
                            text_color=colors["text"], wrap="none")
        tb.pack(fill="x", padx=14, pady=(4, 12))
        t = tb._textbox
        t.tag_configure("ok", foreground="#34d399")
        t.tag_configure("warning", foreground="#fbbf24")
        t.tag_configure("fault", foreground="#ec4899")
        t.tag_configure("info", foreground="#a855f7")
        t.tag_configure("header", foreground="#ec4899", font=("Consolas", 12, "bold"))
        scroll_bottom()
        return {"tb": tb, "bar": bar, "msg": msg, "count": line_count, "box": box, "n": 0, "queue": []}

    def scan_flush(log):
        """Append queued lines in one batch (keeps the UI smooth on big reports)."""
        if not alive() or not log["tb"].winfo_exists():
            return
        lines, log["queue"] = log["queue"], []
        tb = log["tb"]
        tb.configure(state="normal")
        for line in lines:
            if len(line) > 4000:   # e.g. the giant "Raw Text" dump — full copy is in the saved report
                line = line[:4000] + "  …[truncated — full report saved in config/logs]"
            tag = _line_tag(line)
            start = tb._textbox.index("end-1c")
            tb.insert("end", line + "\n")
            if tag:
                tb._textbox.tag_add(tag, start, tb._textbox.index("end-1c"))
            log["n"] += 1
        tb.see("end")
        tb.configure(state="disabled")
        log["count"].configure(text=f"{log['n']} lines")

    # ── running a job (chat message or scan) ──
    def start_job(display_text: str, job):
        """display_text → user bubble; job(on_event) → JackReply, run in a thread."""
        if state["busy"]:
            return
        if state["brain"] is None:
            set_status("Brain abhi load ho raha hai…", "thinking")
            return
        state["messages"].append({"role": "user", "text": display_text, "meta": ""})
        add_bubble("user", display_text)
        set_busy(True)
        set_status("Soch raha hoon…", "thinking")
        act = {"row": None, "lbl": None}
        act["row"], act["lbl"] = add_activity_bubble()
        steps = []
        scan = {"log": None, "pending": deque(), "flush_scheduled": False}

        def drain():
            scan["flush_scheduled"] = False
            log = scan["log"]
            if log is None:                       # log box not created yet — try again shortly
                if scan["pending"]:
                    scan["flush_scheduled"] = True
                    app.after(80, drain)
                return
            while scan["pending"]:
                log["queue"].append(scan["pending"].popleft())
            scan_flush(log)

        def ui(fn, *a):
            try:
                app.after(0, lambda: fn(*a))
            except Exception:
                pass

        def on_event(kind, data):
            if kind == "tool":
                steps.append(f"🔧 {data.get('label') or data.get('name')}")
                ui(update_activity, "\n".join(steps[-6:]), "tool", data.get("label", ""))
            elif kind == "status":
                ui(set_status, data, "thinking")
            elif kind == "error":
                steps.append(f"⚠️ {data} — doosra model try kar raha hoon")
                ui(update_activity, "\n".join(steps[-6:]), "thinking", "")
            elif kind == "scan_start":
                ui(on_scan_start, data)
            elif kind == "line":
                # Worker thread: only queue. The UI thread drains it in batches —
                # lines arriving before the log box exists are kept, not lost.
                scan["pending"].append(data)
                if not scan["flush_scheduled"]:
                    scan["flush_scheduled"] = True
                    try:
                        app.after(80, drain)
                    except Exception:
                        pass
            elif kind == "progress":
                ui(on_scan_progress, *data)
            elif kind == "scan_end":
                ui(on_scan_end)

        def on_scan_start(data):
            if not alive():
                return
            # the activity bubble goes below the log so the order reads naturally
            try:
                act["row"].destroy()
            except Exception:
                pass
            scan["log"] = add_scan_log(data.get("label", "Scan"))
            act["row"], act["lbl"] = None, None
            is_uart = data.get("name") == "run_hw_detect"
            set_status("BOOT THE PHONE NOW — sun raha hoon…" if is_uart else data.get("label", "Scan…"),
                       "listening" if is_uart else "tool")
            try:
                app.enable_stop_button(data.get("stop_event"))
            except Exception:
                pass

        def on_scan_progress(pct, msg):
            log = scan["log"]
            if alive() and log and log["bar"].winfo_exists():
                log["bar"].set(max(0.0, min(1.0, float(pct))))
                if msg:
                    log["msg"].configure(text=msg)

        def on_scan_end():
            try:
                app.disable_stop_button()
            except Exception:
                pass
            if not alive():
                return
            log = scan["log"]
            if log:
                drain()
                log["box"].configure(border_color=colors["border"])
            act["row"], act["lbl"] = add_activity_bubble()
            set_status("Report samajh raha hoon…", "thinking")

        def update_activity(text, kind, label):
            lbl = act["lbl"]
            if alive() and lbl is not None and lbl.winfo_exists():
                lbl.configure(text=text)
                scroll_bottom()
            if label and not scan["log"]:
                set_status(label + "…", kind)

        def worker():
            try:
                reply = job(on_event)
                meta = f"{reply.provider} • {reply.seconds}s"
                if reply.tools_used:
                    meta += f" • {len(reply.tools_used)} tools"
                msg = {"role": "jack", "text": reply.text, "meta": meta, "speech": reply.speech}
            except Exception as e:
                msg = {"role": "jack", "text": f"Boss, kuch gadbad ho gayi: {e}", "meta": "error"}
            state["messages"].append(msg)   # saved even if Boss left the page
            ui(finish, msg)

        def finish(msg):
            set_busy(False)
            if not alive():
                return
            try:
                if act["row"] is not None:
                    act["row"].destroy()
            except Exception:
                pass
            add_bubble("jack", msg["text"], msg["meta"], animate=True, speech=msg.get("speech", ""))
            set_status("Ready", "error" if msg["meta"] == "error" else "idle")
            speak(msg.get("speech") or "")       # Section 5 — voice output
            set_chips(followups(msg["text"], display_text))
            if state.get("convo"):       # hands-free: speech khatam hote hi dobara suno
                app.after(500, convo_after_reply)

        threading.Thread(target=worker, daemon=True).start()

    def send(text: str = None):
        text = (text if text is not None else entry.get()).strip()
        if not text or state["busy"]:
            return
        entry.delete(0, "end")
        start_job(text, lambda ev: state["brain"].chat(text, on_event=ev))

    def run_scan(tool_name: str, label: str, args: dict = None):
        start_job(label, lambda ev: state["brain"].run_scan(tool_name, args or {}, on_event=ev))

    def regenerate():
        if state["busy"]:
            return
        last_user = next((m["text"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
        if last_user:
            set_status("Dobara jawab de raha hoon…", "thinking")
            send(last_user)

    def new_chat():
        if state["busy"]:
            return
        if state["brain"]:
            state["brain"].reset()
        state["messages"].clear()
        for w in chat.winfo_children():
            w.destroy()
        bodies.clear()
        greet()
        set_chips([p.split(" ", 1)[1] for p in QUICK_PROMPTS])

    def greet():
        hour = time.localtime().tm_hour
        part = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        hello = (f"{part} Boss, main Jack hoon. Phone ka model aur problem batao, ya neeche se koi kaam chuno. "
                 "Main database, connected device aur scans sab dekh sakta hoon. "
                 "Bolkar poochna ho to 🎤 dabao ya Ctrl+Space.")
        add_bubble("jack", hello, animate=True)
        show_hero()

    # ── welcome cards (shown until the first question) ──
    hero = {"frame": None}
    HERO_CARDS = [
        ("🔌", "Connected device", "COM / ADB / Fastboot / EDL check", lambda: send("Connected device check karo")),
        ("📟", "HW Detect (UART)", "Boot log se chipset + fault", lambda: hw_btn.invoke()),
        ("📱", "ADB Detect", "Chalu phone ka full health scan", lambda: adb_btn.invoke()),
        ("📄", "Last scan", "Pichhli report samjhao", lambda: send("Last scan ka result batao")),
        ("💀", "Dead phone", "0.00A / no power diagnosis", lambda: send("Phone dead hai, 0.00A le raha hai")),
        ("🔋", "Charging fault", "Charging IC, PMIC, port", lambda: send("Charging nahi ho rahi")),
    ]

    def clear_hero():
        if hero["frame"] is not None:
            try:
                hero["frame"].destroy()
            except Exception:
                pass
            hero["frame"] = None

    def show_hero():
        clear_hero()
        wrap = ctk.CTkFrame(chat, fg_color="transparent")
        wrap.pack(fill="x", padx=(44, 20), pady=(4, 10))
        ctk.CTkLabel(wrap, text="MAIN KYA KAR SAKTA HOON", font=("Segoe UI", 11, "bold"),
                     text_color=colors["text_dim"]).pack(anchor="w", pady=(0, 6))
        grid = ctk.CTkFrame(wrap, fg_color="transparent")
        grid.pack(fill="x")
        for i, (icon, title, sub, cmd) in enumerate(HERO_CARDS):
            card = ctk.CTkFrame(grid, corner_radius=14, fg_color=colors["bg_medium"],
                                border_width=1, border_color=colors["border"], cursor="hand2")
            card.grid(row=i // 3, column=i % 3, padx=5, pady=5, sticky="nsew")
            grid.grid_columnconfigure(i % 3, weight=1, uniform="c")
            ic = ctk.CTkLabel(card, text=icon, font=("Segoe UI Emoji", 20), width=34)
            ic.grid(row=0, column=0, rowspan=2, padx=(12, 6), pady=8)
            t = ctk.CTkLabel(card, text=title, font=("Segoe UI", 13, "bold"), text_color=colors["text"],
                             height=18)
            t.grid(row=0, column=1, sticky="sw", pady=(8, 0))
            s = ctk.CTkLabel(card, text=sub, font=("Segoe UI", 11), text_color=colors["text_dim"], height=16)
            s.grid(row=1, column=1, sticky="nw", pady=(0, 8), padx=(0, 10))

            def enter(_e, c=card):
                c.configure(border_color="#a855f7", fg_color=_blend(colors["bg_medium"], "#a855f7", 0.12))

            def leave(_e, c=card):
                c.configure(border_color=colors["border"], fg_color=colors["bg_medium"])

            def click(_e, f=cmd):
                if not state["busy"]:
                    f()
            for w in (card, ic, t, s):
                w.bind("<Enter>", enter)
                w.bind("<Leave>", leave)
                w.bind("<Button-1>", click)
        hero["frame"] = wrap
        scroll_bottom()

    # ── smart follow-up chips ──
    def followups(reply: str, asked: str):
        r, a = reply.lower(), asked.lower()
        out = []
        if "hw detect" in a or "adb detect" in a or "scan" in a:
            out += ["Is fault ka repair step-by-step batao", "Kaunse test points measure karun?",
                    "Is chipset ke common faults?"]
        if any(k in r for k in ("pmic", "charging ic", "ic ", "rail", "voltage")):
            out.append("Is IC ke voltage rails aur test points?")
        if any(k in r for k in ("dead", "short", "0.00a", "current")):
            out.append("Short kaise dhoondhu? (thermal / rosin)")
        if "edl" in r or "qualcomm" in r or "snapdragon" in r:
            out.append("EDL test point batao")
        if any(k in r for k in ("database mein nahi", "verify")):
            out.append("Community fixes mein dhoondho")
        if "connected" in a or "device" in a:
            out += ["HW detect chalao", "ADB detect chalao"]
        out += ["Isse related pehle kaunse phone aaye the?", "Connected device check karo"]
        seen, final = set(), []
        for o in out:
            if o not in seen and o.lower() != a:
                seen.add(o)
                final.append(o)
        return final[:4]

    def set_chips(items):
        if not alive():
            return
        for w in chips.winfo_children():
            w.destroy()
        ctk.CTkLabel(chips, text="✨", font=("Segoe UI Emoji", 13)).pack(side="left", padx=(2, 6))
        for p in items:
            def run(t=p):
                if t == "HW detect chalao":
                    hw_btn.invoke()
                elif t == "ADB detect chalao":
                    adb_btn.invoke()
                else:
                    send(t)
            ctk.CTkButton(chips, text=p, height=30, font=("Segoe UI", 12), corner_radius=15,
                          fg_color=colors["bg_light"], hover_color=_blend(colors["bg_light"], "#a855f7", 0.35),
                          border_width=1, border_color=colors["border"], text_color=colors["text"],
                          command=run).pack(side="left", padx=(0, 8))

    # ── wire up widgets ──
    scan_buttons = []
    ctk.CTkLabel(scan_row, text="Scans:", font=("Segoe UI", 12, "bold"),
                 text_color=colors["text_dim"]).pack(side="left", padx=(2, 8))
    hw_btn = ctk.CTkButton(scan_row, text="🔌 HW Detect (UART)", height=32, width=170,
                           font=("Segoe UI", 12, "bold"), corner_radius=8,
                           fg_color=colors["warning"], hover_color="#fcd34d", text_color="#1a1a1a",
                           command=lambda: run_scan("run_hw_detect", f"🔌 HW Detect chalao ({dur_var.get()}s)",
                                                    {"duration": int(dur_var.get())}))
    hw_btn.pack(side="left")
    dur_var = ctk.StringVar(value="90")
    ctk.CTkOptionMenu(scan_row, values=["45", "60", "90", "120", "180", "240"], variable=dur_var,
                      width=70, height=32, fg_color=colors["bg_light"],
                      button_color=colors["border"]).pack(side="left", padx=(4, 2))
    ctk.CTkLabel(scan_row, text="sec", font=("Segoe UI", 11),
                 text_color=colors["text_dim"]).pack(side="left", padx=(0, 14))
    adb_btn = ctk.CTkButton(scan_row, text="📱 ADB Detect", height=32, width=130,
                            font=("Segoe UI", 12, "bold"), corner_radius=8,
                            fg_color=colors["success"], hover_color="#6ee7b7", text_color="#1a1a1a",
                            command=lambda: run_scan("run_adb_detect", "📱 ADB Detect chalao"))
    adb_btn.pack(side="left")
    ctk.CTkLabel(scan_row, text="  ⏹ Scan rokne ke liye sidebar ka Stop Scan dabao",
                 font=("Segoe UI", 11), text_color=colors["text_dim"]).pack(side="left", padx=10)
    scan_buttons += [hw_btn, adb_btn]

    send_btn.configure(command=send)
    entry.bind("<Return>", lambda e: send())

    def recall_last(_e=None):            # ↑ = previous question back in the box
        for m in reversed(state["messages"]):
            if m["role"] == "user":
                entry.delete(0, "end")
                entry.insert(0, m["text"])
                break
        return "break"
    entry.bind("<Up>", recall_last)
    entry.bind("<Escape>", lambda e: speaker and speaker.stop())
    entry.bind("<FocusIn>", lambda e: input_row.configure(border_width=2, border_color="#a855f7"))
    entry.bind("<FocusOut>", lambda e: input_row.configure(border_width=1, border_color=colors["border"]))
    input_row.configure(border_width=1, border_color=colors["border"])

    def on_typing(_e=None):
        n = len(entry.get())
        hint_lbl.configure(text=f"{n} chars • Enter = send • ↑ = last • Esc = chup" if n else
                           "Enter = send  •  ↑ = pichla sawaal  •  Ctrl+Space = bolo  •  Esc = chup")
    entry.bind("<KeyRelease>", on_typing, add="+")
    hint_lbl = ctk.CTkLabel(bottom, text="", font=("Segoe UI", 10), text_color=colors["text_dim"])
    hint_lbl.pack(anchor="e", pady=(4, 0))
    on_typing()
    ctk.CTkButton(btn_row, text="🧹 New chat", width=110, height=32, font=("Segoe UI", 12),
                  fg_color=colors["bg_light"], hover_color=colors["border"],
                  command=new_chat).pack(side="left", padx=(0, 8))
    ctk.CTkButton(btn_row, text="🔄 Device", width=90, height=32, font=("Segoe UI", 12),
                  fg_color=colors["bg_light"], hover_color=colors["border"],
                  command=lambda: refresh_device()).pack(side="left")

    # ── voice: Section 5 (speak) + Section 4 (mic, hotkey, wake word) ──
    try:
        speaker, wake = _ensure_voice(app)
    except Exception as e:
        print(f"[Jack] voice init failed: {e}")
        speaker, wake = None, None

    def speak(text: str, force: bool = False):
        """force=True: the 🔊 button on a bubble — speaks even if auto-voice is OFF."""
        if speaker and (state["voice_on"] or force) and text.strip():
            speaker.speak(text)

    def on_speaking(active: bool):
        if not alive() or state["busy"] or state["listening"]:
            return
        if active:
            set_status("Bol raha hoon…  (orb dabao = chup)", "speaking")
        else:
            set_status("Ready", "idle")

    def maybe_listen_again():
        """Conversation mode: Jack ke free hote hi apne aap dobara sunta hai."""
        if state.get("convo") and alive() and not state["busy"] and not state["listening"]:
            app.after(350, lambda: (state.get("convo") and not state["busy"]
                                    and not state["listening"] and toggle_listen()))

    def convo_after_reply():
        """Jawab ke baad: Jack ki awaaz khatam hone ka wait karo, phir dobara suno."""
        if not state.get("convo") or not alive() or state["busy"] or state["listening"]:
            return
        spk = state.get("speaker")
        if spk is not None and getattr(spk, "speaking", False):
            app.after(300, convo_after_reply)      # abhi bol raha hai — ruko
            return
        maybe_listen_again()

    def mic_look(listening: bool):
        if alive():
            mic_btn.configure(text="⏹" if listening else "🎤",
                              fg_color=colors["accent"] if listening else colors["bg_light"])
        if listening:
            ph = [0.0]

            def pulse():                       # mic button breathes while recording
                if not alive() or not state["listening"]:
                    return
                ph[0] += 0.25
                t = (math.sin(ph[0]) + 1) / 2
                mic_btn.configure(fg_color=_blend(colors["accent"], "#d8b4fe", t * 0.5))
                mic_btn.after(50, pulse)
            mic_btn.after(50, pulse)

    def toggle_listen():
        """Mic button / Ctrl+Space: start listening, or stop if already listening."""
        if state["listening"]:
            if state["listen_stop"]:
                state["listen_stop"].set()
            return
        if state["busy"] or state["brain"] is None:
            return
        from app.jack.voice import mic_available, record_phrase, transcribe, VoiceError
        reason = mic_available()
        if reason:
            set_status(f"🎤 {reason}", "error")
            return
        if speaker:
            speaker.stop()                     # barge-in: Boss speaks, Jack stops talking
        stop = threading.Event()
        state["listening"], state["listen_stop"] = True, stop
        mic_look(True)
        set_status("Sun raha hoon… bolo Boss  (dobara dabao = stop)", "listening")

        def work():
            text, err = "", ""
            try:
                wav = record_phrase(stop_event=stop, start_timeout=7, max_seconds=15,
                                    on_level=lambda v: setattr(orb, "level", v))   # orb bars follow your voice
                orb.level = 0.0
                if wav:
                    _ui_call(app, "status", "Samajh raha hoon…", "thinking")
                    text = transcribe(wav)
                elif not stop.is_set():
                    err = "Kuch suna nahi, Boss — dobara bolo"
            except VoiceError as e:
                err = str(e)
            except Exception as e:
                err = f"Mic error: {e}"
            state["listening"], state["listen_stop"] = False, None
            _ui_call(app, "heard", text, err)

        threading.Thread(target=work, daemon=True).start()

    def on_heard(text: str, err: str):
        mic_look(False)
        if text:
            state["convo_empties"] = 0
            send(text)
            return
        # kuch suna nahi (silence ya error)
        if state.get("convo"):
            state["convo_empties"] = state.get("convo_empties", 0) + 1
            if state["convo_empties"] >= 3:
                stop_convo("Baat mode band — kuch suna nahi, Boss")
                return
            set_status("Haan Boss? sun raha hoon…", "listening")
            maybe_listen_again()
            return
        set_status(err or "Ready", "error" if err else "idle")

    def on_wake(cmd: str):
        """'Hey Jack …' heard. With a command → run it; just 'Hey Jack' → beep and listen."""
        if state["busy"]:
            return
        if cmd and len(cmd) > 2:
            send(cmd)
            return
        try:
            import winsound
            winsound.Beep(1046, 120)
        except Exception:
            pass
        toggle_listen()

    def voice_error(msg: str):
        if alive() and not state["busy"]:
            set_status(f"🎤 {msg}", "error")

    def toggle_voice():
        state["voice_on"] = not state["voice_on"]
        _save_voice_setting("voice_reply", state["voice_on"])
        if not state["voice_on"] and speaker:
            speaker.stop()
        voice_btn.configure(text="🔊" if state["voice_on"] else "🔇",
                            fg_color=colors["success"] if state["voice_on"] else colors["bg_light"])

    def wake_refresh():
        if not alive():
            return
        wake_btn.configure(text="👂", fg_color=colors["info"] if state["wake_on"] else colors["bg_light"])

    def toggle_wake():
        if wake is None:
            set_status("Voice module load nahi hua", "error")
            return
        if not state["wake_on"]:
            from app.jack.voice import mic_available
            reason = mic_available()
            if reason:
                set_status(f"🎤 {reason}", "error")
                return
        state["wake_on"] = not state["wake_on"]
        _save_voice_setting("wake_word_enabled", state["wake_on"])
        if state["wake_on"]:
            wake.start()
            set_status("Bolo \"Hey Jack\" — main sun raha hoon", "idle")
        else:
            wake.stop()
            set_status("Wake word band", "idle")
        wake_refresh()

    def _tip(btn, msg):
        btn.bind("<Enter>", lambda e: app.update_status(msg))

    voice_btn = ctk.CTkButton(btn_row, text="", width=42, height=32, font=("Segoe UI Emoji", 15),
                              hover_color=colors["border"], command=toggle_voice)
    voice_btn.pack(side="left", padx=(0, 6), before=btn_row.winfo_children()[0])
    _tip(voice_btn, "🔊 Jack ki awaaz ON/OFF")
    wake_btn = ctk.CTkButton(btn_row, text="", width=42, height=32, font=("Segoe UI Emoji", 15),
                             hover_color=colors["border"], command=toggle_wake)
    wake_btn.pack(side="left", padx=(0, 6), after=voice_btn)
    _tip(wake_btn, "👂 'Hey Jack' wake word — hamesha sunta rahe")
    state["voice_on"] = not state["voice_on"]   # toggle_voice flips it back and paints the button
    toggle_voice()
    wake_refresh()

    # Section 7 — proactive toggle
    def proactive_refresh():
        on = bool(getattr(app, "proactive", None) and app.proactive.enabled)
        pro_btn.configure(text="📡", fg_color=colors["success"] if on else colors["bg_light"])

    def toggle_proactive():
        if getattr(app, "proactive", None):
            app.proactive.set_enabled(not app.proactive.enabled)
            proactive_refresh()
            set_status("Auto mode ON — phone/scan pe khud batau ga" if app.proactive.enabled
                       else "Auto mode OFF", "idle")

    pro_btn = ctk.CTkButton(btn_row, text="", width=42, height=32, font=("Segoe UI Emoji", 15),
                            hover_color=colors["border"], command=toggle_proactive)
    pro_btn.pack(side="left", padx=(0, 6), after=wake_btn)
    _tip(pro_btn, "📡 Auto alerts — phone connect / scan pe Jack khud bole")
    proactive_refresh()

    # hands-free conversation mode — Jack jawab de ke khud dobara sunta hai (mic baar-baar nahi)
    state.setdefault("convo", False)
    state.setdefault("convo_empties", 0)
    state["convo"] = False       # har render pe fresh (no surprise listening)

    def conv_refresh():
        on = state.get("convo")
        conv_btn.configure(text="🎙", fg_color=colors["secondary"] if on else colors["bg_light"])

    def stop_convo(msg="Baat mode OFF"):
        state["convo"] = False
        if state["listening"] and state["listen_stop"]:
            state["listen_stop"].set()
        conv_refresh()
        if alive():
            set_status(msg, "idle")

    def toggle_convo():
        if state.get("convo"):
            stop_convo("Baat mode OFF")
            return
        from app.jack.voice import mic_available
        reason = mic_available()
        if reason:
            set_status(f"🎤 {reason}", "error")
            return
        if not state["voice_on"]:        # convo bina awaaz adhoora hai — khud on kar do
            toggle_voice()
        state["convo"], state["convo_empties"] = True, 0
        conv_refresh()
        set_status("Baat mode ON — bolo Boss, mic baar-baar dabane ki zaroorat nahi", "listening")
        if not state["busy"] and not state["listening"]:
            maybe_listen_again()

    conv_btn = ctk.CTkButton(btn_row, text="", width=42, height=32, font=("Segoe UI Emoji", 15),
                             hover_color=colors["border"], command=toggle_convo)
    conv_btn.pack(side="left", padx=(0, 6), after=voice_btn)
    _tip(conv_btn, "🎙 Baat mode — hands-free, mic baar-baar dabane ki zaroorat nahi")
    conv_refresh()

    mic_btn.configure(command=toggle_listen)
    orb.canvas.bind("<Button-1>", lambda e: speaker and speaker.stop())

    state["ui"] = {"speaking": on_speaking, "heard": on_heard, "wake": on_wake, "listen": toggle_listen,
                   "voice_error": voice_error, "wake_refresh": wake_refresh, "status": set_status,
                   "ask": lambda t: send(t)}

    if not getattr(app, "_jack_hotkey_bound", False):     # Ctrl+Space from anywhere in the app
        def hotkey(_e=None):
            page_ = getattr(app, "jack_page_frame", None)
            try:
                shown = page_ is not None and page_.winfo_exists()
            except Exception:
                shown = False
            if shown:
                _ui_call(app, "listen")
            else:
                app.show_jack()
                app.after(500, lambda: _ui_call(app, "listen"))
            return "break"
        app.bind_all("<Control-space>", hotkey)
        app._jack_hotkey_bound = True

    if state["wake_on"] and wake is not None and not wake.running:
        wake.start()

    # ── restore previous conversation ──
    if state["messages"]:
        for m in state["messages"]:
            add_bubble("user" if m["role"] == "user" else "jack", m["text"], m.get("meta", ""),
                       speech=m.get("speech", ""))
        last_user = next((m["text"] for m in reversed(state["messages"]) if m["role"] == "user"), "")
        last_jack = next((m["text"] for m in reversed(state["messages"]) if m["role"] == "jack"), "")
        set_chips(followups(last_jack, last_user))
    else:
        greet()
        set_chips([p.split(" ", 1)[1] for p in QUICK_PROMPTS])
    if state["busy"]:
        set_busy(True)
        set_status("Pichla sawaal abhi process ho raha hai…", "thinking")

    # ── background: load brain + check device ──
    def refresh_device():
        if alive():
            device_lbl.configure(text="🔌 Device check ho raha hai…")

        def work():
            try:
                from app.jack.actions import check_connected_devices
                summary = check_connected_devices().get("summary", "")
            except Exception as e:
                summary = f"Check failed: {e}"
            state["device"] = summary
            connected = not summary.startswith(("Kuch", "Check failed"))
            app.after(0, lambda: alive() and device_lbl.configure(
                text=f"{'●' if connected else '○'}  {summary}",
                text_color=colors["success"] if connected else colors["text_dim"]))
            device_live[0] = connected
        threading.Thread(target=work, daemon=True).start()

    device_live = [False]

    def blink_device(on=[True]):
        """Connected device chip breathes green."""
        if not alive():
            return
        if device_live[0]:
            on[0] = not on[0]
            device_lbl.configure(text_color=colors["success"] if on[0] else _blend(colors["success"],
                                                                                  colors["bg_light"], 0.55))
        page.after(900, blink_device)
    page.after(900, blink_device)

    def load_brain():
        try:
            if state["brain"] is None:
                from app.jack.brain import JackBrain
                state["brain"] = JackBrain()
            providers = state["brain"].settings.get("provider_order", [])
            has_key = bool(state["brain"]._clients("groq"))
            msg, kind = (("Ready — Groq online", "idle") if has_key else
                         ("Groq key nahi mili — database mode", "error"))
            if "groq" not in providers:
                msg, kind = ("Ready — " + ", ".join(providers), "idle")
            b = state["brain"]
            pills = [("🧠 Groq AI" if has_key else "🧠 Offline DB", "#a78bfa"),
                     (f"🔧 {len(b.tools.tools)} tools", colors["warning"]),
                     (f"📚 {b.kb.stats().get('phones', 0)} phones", colors["info"]),
                     ("🎙 Voice", colors["success"])]
        except Exception as e:
            msg, kind = (f"Brain load failed: {e}", "error")
            pills = []
        app.after(0, lambda: alive() and not state["busy"] and set_status(msg, kind))
        app.after(0, lambda: alive() and show_pills(pills))

    def show_pills(pills):
        for w in pill_row.winfo_children():
            w.destroy()
        for text, col in pills:
            ctk.CTkLabel(pill_row, text=text, font=("Segoe UI", 10, "bold"), text_color=col,
                         fg_color=_blend(colors["bg_medium"], col, 0.14), corner_radius=8,
                         padx=8, pady=1).pack(side="left", padx=(0, 6))

    threading.Thread(target=load_brain, daemon=True).start()
    refresh_device()
    app.update_status("Jack AI • Enter dabao ya quick button chuno")
    entry.focus_set()
