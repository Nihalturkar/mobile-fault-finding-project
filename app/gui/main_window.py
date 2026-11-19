import customtkinter as ctk
import json
import os
import ctypes
from pathlib import Path

# Tell Windows this is its own app, not "python.exe" — so taskbar shows our icon
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mooxy.ai.fault.detector")
except Exception:
    pass

# Set theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class MobileRepairTool(ctk.CTk):
    """Main application window for Mooxy AI Fault Detector"""

    def __init__(self):
        super().__init__()

        # Window setup - full screen maximized
        self.title("Mooxy AI Fault Detector v1.0")
        self.minsize(1100, 700)

        # Set window icon (taskbar + title bar)
        _ico_path = Path(__file__).parent.parent.parent / "assets" / "logo.ico"
        if _ico_path.exists():
            try:
                self.iconbitmap(default=str(_ico_path.resolve()))
                self.after(100, lambda: self.iconbitmap(str(_ico_path.resolve())))
            except Exception:
                pass

        # Get screen size and center/maximize
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        self.geometry(f"{screen_w}x{screen_h}+0+0")
        self.after(100, lambda: self.state("zoomed"))

        # Load device database
        self.db_path = Path(__file__).parent.parent.parent / "config" / "devices_database.json"
        self.devices = self.load_database()
        self.filtered_devices = self.devices.copy()
        self.current_device = None

        # Color scheme — "Gunmetal Console" (slate blue-grey backdrop + violet core + cyan HUD)
        self.colors = {
            "bg_dark": "#202c34",       # dark slate — main content backdrop
            "bg_medium": "#27343c",     # panel (sidebar / topbar / statusbar) — a touch lighter
            "bg_light": "#31404a",      # raised control / input — lightest
            "bg_card": "#25323a",       # card
            "accent": "#a855f7",        # violet — primary buttons (brand core)
            "accent_hover": "#c084fc",
            "success": "#34d399",
            "warning": "#fbbf24",
            "info": "#818cf8",          # indigo
            "secondary": "#ec4899",     # magenta
            "text": "#ffffff",
            "text_dim": "#c4ccd6",      # light slate-grey — readable on the slate backdrop
            "border": "#3d4d57",        # hairline on slate
            # ── robotics HUD accents (used by the Neural-core chrome) ──
            "hud": "#22d3ee",           # cyan — scan/HUD lines
            "hud_dim": "#0e7490",       # deep cyan
            "grid": "#3b4b55",          # faint grid on slate
        }

        self.configure(fg_color=self.colors["bg_dark"])

        # Section 7 — Proactive Jack (reacts to connect/scan events)
        try:
            from app.jack.proactive import ProactiveManager
            self.proactive = ProactiveManager(self)
        except Exception as e:
            print(f"[Jack] proactive init failed: {e}")
            self.proactive = None

        # Build UI
        self._create_sidebar()
        self._create_main_area()
        self._create_statusbar()

        # Show dashboard by default
        self.show_dashboard()

        # Power-on sequence — robotics boot animation (plays once; click/key to skip)
        try:
            self.after(80, self._play_boot_sequence)
        except Exception:
            pass

    def load_database(self):
        """Load devices from JSON database"""
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("devices", [])
        except Exception as e:
            print(f"Error loading database: {e}")
            return []

    # ── sidebar ────────────────────────────────────────────────────────────
    SIDEBAR_W, SIDEBAR_W_MINI = 232, 78

    @staticmethod
    def _mix(c1, c2, t):
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))

    def _create_sidebar(self):
        """Left sidebar: brand, Jack card, live connection card, grouped nav, Stop Scan."""
        import math
        import tkinter as tk
        C = self.colors
        self._sidebar_collapsed = False
        self._active_nav = 0
        self._phase = 0.0
        self._conn = {"uart": False, "adb": False}

        self.sidebar = ctk.CTkFrame(self, width=self.SIDEBAR_W, corner_radius=0, fg_color=C["bg_medium"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        # thin glowing edge on the right of the sidebar
        self._sidebar_edge = ctk.CTkFrame(self.sidebar, width=1, corner_radius=0, fg_color=C["border"])
        self._sidebar_edge.pack(side="right", fill="y")

        # ── brand row: logo + name + collapse toggle ──
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=12, pady=(16, 4))
        logo_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            from PIL import Image
            self._logo_img = ctk.CTkImage(light_image=Image.open(logo_path),
                                          dark_image=Image.open(logo_path), size=(46, 46))
            ctk.CTkLabel(brand, image=self._logo_img, text="").pack(side="left")
        else:
            ctk.CTkLabel(brand, text="🔧", font=("Segoe UI Emoji", 28)).pack(side="left")
        self._brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        self._brand_text.pack(side="left", padx=(8, 0))
        name_row = ctk.CTkFrame(self._brand_text, fg_color="transparent")
        name_row.pack(anchor="w")
        ctk.CTkLabel(name_row, text="Mooxy", font=("Segoe UI", 19, "bold"),
                     text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(name_row, text=" AI ", font=("Segoe UI", 11, "bold"), text_color="#ffffff",
                     fg_color=C["accent"], corner_radius=6, height=18).pack(side="left", padx=(5, 0))
        ctk.CTkLabel(self._brand_text, text="Fault Detector", font=("Segoe UI", 12),
                     text_color=C["text_dim"], height=16).pack(anchor="w")

        # ── Jack card (animated mini orb + glowing border) ──
        self.jack_btn = ctk.CTkFrame(self.sidebar, corner_radius=12, fg_color=C["bg_light"],
                                     border_width=1, border_color=C["info"], cursor="hand2", height=56)
        self.jack_btn.pack(fill="x", padx=12, pady=(12, 0))
        self._jack_orb = tk.Canvas(self.jack_btn, width=34, height=34, bg=C["bg_light"],
                                   highlightthickness=0, cursor="hand2")
        self._jack_orb.pack(side="left", padx=(10, 8), pady=10)
        self._jack_text = ctk.CTkFrame(self.jack_btn, fg_color="transparent")
        self._jack_text.pack(side="left", fill="x", expand=True)
        self._jack_title = ctk.CTkLabel(self._jack_text, text="Talk to Jack", font=("Segoe UI", 14, "bold"),
                                        text_color=C["info"], height=18, cursor="hand2")
        self._jack_title.pack(anchor="w")
        self._jack_sub = ctk.CTkLabel(self._jack_text, text="AI assistant  •  Ctrl+J",
                                      font=("Segoe UI", 10), text_color=C["text_dim"], height=14,
                                      cursor="hand2")
        self._jack_sub.pack(anchor="w")
        self._jack_active = False
        self._jack_hover = False
        for w in (self.jack_btn, self._jack_orb, self._jack_text, self._jack_title, self._jack_sub):
            w.bind("<Button-1>", lambda e: self.show_jack())
            w.bind("<Enter>", lambda e: self._jack_set_hover(True))
            w.bind("<Leave>", lambda e: self._jack_set_hover(False))
        self.bind_all("<Control-j>", lambda e: self.show_jack())

        # ── live connection card ──
        self._conn_card = ctk.CTkFrame(self.sidebar, corner_radius=10, fg_color=C["bg_dark"],
                                       border_width=1, border_color=C["border"])
        self._conn_card.pack(fill="x", padx=12, pady=(10, 4))
        self._conn_rows = {}
        for key, label in (("uart", "UART / COM"), ("adb", "ADB")):
            row = ctk.CTkFrame(self._conn_card, fg_color="transparent", height=22)
            row.pack(fill="x", padx=10, pady=(6 if key == "uart" else 0, 6 if key == "adb" else 0))
            dot = ctk.CTkLabel(row, text="●", font=("Segoe UI", 12), text_color=C["text_dim"], width=14)
            dot.pack(side="left")
            name = ctk.CTkLabel(row, text=label, font=("Segoe UI", 11), text_color=C["text_dim"], height=18)
            name.pack(side="left", padx=(6, 0))
            state = ctk.CTkLabel(row, text="offline", font=("Segoe UI", 10), text_color=C["text_dim"], height=18)
            state.pack(side="right")
            self._conn_rows[key] = (dot, name, state)

        # ── grouped navigation ──
        self.nav_scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
            scrollbar_button_color=C["bg_medium"],
            scrollbar_button_hover_color=C["border"],
        )
        self.nav_scroll.pack(fill="both", expand=True, pady=(4, 0))

        # (original index, icon, label, command) — index is what show_*() passes to set_active_nav
        groups = [
            ("DIAGNOSE", [
                (0, "📊", "Dashboard", self.show_dashboard),
                (1, "🔌", "HW Detect", self.show_hw_detect),
                (2, "📱", "ADB Detect", self.show_adb_detect),
                (10, "📡", "Network Diagnostic", self.show_network_diagnostic),
                (13, "⚡", "EDL 9008 Detect", self.show_edl_detect),
            ]),
            ("KNOWLEDGE", [
                (5, "🌍", "Community Fixes", self.show_community),
            ]),
            ("UNLOCK", [
                (6, "🔓", "Unlock Tool", self.show_auto_unlock),
            ]),
            ("RECORDS", [
                (9, "📜", "History", self.show_history),
                (12, "📤", "Export PDF", self.show_export),
            ]),
        ]
        n = 1 + max(i for _, items in groups for i, *_ in items)
        self.nav_buttons = [None] * n
        self._nav_bars = [None] * n
        self._nav_meta = [None] * n
        self._nav_headers = []
        for title, items in groups:
            disp = f"◢ {title}"
            hdr = ctk.CTkLabel(self.nav_scroll, text=disp, font=("Consolas", 10, "bold"),
                               text_color=self._mix(C["hud"], C["text_dim"], 0.55), height=18, anchor="w")
            hdr.pack(fill="x", padx=14, pady=(10, 2))
            self._nav_headers.append((hdr, disp))
            for idx, icon, label, command in items:
                row = ctk.CTkFrame(self.nav_scroll, fg_color="transparent", height=38)
                row.pack(fill="x", padx=(2, 4), pady=1)
                bar = ctk.CTkFrame(row, width=4, height=22, corner_radius=2, fg_color=C["bg_medium"])
                bar.pack(side="left", padx=(0, 4))
                btn = ctk.CTkButton(
                    row, text=f"{icon}   {label}", command=command,
                    font=("Segoe UI", 13), height=36,
                    fg_color="transparent", text_color=C["text_dim"],
                    hover_color=C["bg_light"], anchor="w", corner_radius=9)
                btn.pack(side="left", fill="x", expand=True)
                btn.bind("<Enter>", lambda e, i=idx: self._nav_hover(i, True))
                btn.bind("<Leave>", lambda e, i=idx: self._nav_hover(i, False))
                self.nav_buttons[idx], self._nav_bars[idx] = btn, bar
                self._nav_meta[idx] = (icon, label)

        # ── bottom: version + Stop Scan ──
        self._stop_event = None  # Will be set by scan pages
        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=28)
        footer.pack(side="bottom", fill="x", padx=12, pady=(2, 8))
        self._collapse_btn = ctk.CTkButton(
            footer, text="«", width=28, height=24, corner_radius=8, font=("Segoe UI", 14, "bold"),
            fg_color=C["bg_light"], hover_color=C["border"], text_color=C["text_dim"],
            command=self.toggle_sidebar)
        self._collapse_btn.pack(side="right")
        self.version_label = ctk.CTkLabel(footer, text=f"v1.0.0 • {len(self.devices)} Devices",
                                          font=("Segoe UI", 10), text_color=C["text_dim"])
        self.version_label.pack(side="left")
        self.stop_btn = ctk.CTkButton(
            self.sidebar, text="⏹  Stop Scan", height=40,
            font=("Segoe UI", 13, "bold"),
            fg_color=C["bg_light"], hover_color="#c084fc",
            text_color="#ffffff", text_color_disabled=C["text_dim"], corner_radius=10,
            command=self._stop_scan,
        )
        self.stop_btn.pack(side="bottom", fill="x", padx=12, pady=(6, 2))
        self.stop_btn.configure(state="disabled")  # disabled until scan starts
        self._scan_running = False

        self._sidebar_tick()

    # sidebar animation: Jack orb, Jack border glow, live dots, Stop Scan pulse
    def _sidebar_tick(self):
        import math
        try:
            if not self.sidebar.winfo_exists():
                return
        except Exception:
            return
        C = self.colors
        self._phase += 0.08
        p = (math.sin(self._phase) + 1) / 2

        # mini orb
        c = self._jack_orb
        bg = C["info"] if self._jack_active else C["bg_light"]
        c.configure(bg=bg)
        c.delete("all")
        core = "#ffffff" if self._jack_active else "#a855f7"
        for i in range(4, 0, -1):
            r = 7 + i * 2.6 + p * 1.5
            c.create_oval(17 - r, 17 - r, 17 + r, 17 + r, outline="",
                          fill=self._mix(bg, core, 0.08 + (4 - i) * 0.1))
        a = self._phase * 2.2
        c.create_arc(3, 3, 31, 31, start=math.degrees(a) % 360, extent=70, style="arc",
                     outline=self._mix(bg, core, 0.8), width=2)
        # cyan HUD counter-ring + tick marks (robotics scanner feel)
        hud = self._mix(bg, C["hud"], 0.55)
        c.create_arc(5, 5, 29, 29, start=-math.degrees(a) * 0.7 % 360, extent=55, style="arc",
                     outline=hud, width=1)
        for k in range(8):
            ta = math.radians(self._phase * 20 + k * 45)
            r1, r2 = 15, 13
            c.create_line(17 + r1 * math.cos(ta), 17 + r1 * math.sin(ta),
                          17 + r2 * math.cos(ta), 17 + r2 * math.sin(ta), fill=hud, width=1)
        r = 5.5 + p * 1.2
        c.create_oval(17 - r, 17 - r, 17 + r, 17 + r, fill=self._mix(core, "#ffffff", 0.6), outline="")

        # Jack card border breathes blue → purple
        if not self._jack_active:
            glow = self._mix(C["info"], "#a78bfa", p) if self._jack_hover else self._mix(C["border"], C["info"], 0.35 + 0.65 * p)
            self.jack_btn.configure(border_color=glow)

        # live connection dots
        for key, (dot, name, st) in self._conn_rows.items():
            if self._conn.get(key):
                dot.configure(text_color=self._mix(C["success"], "#0a3d1f", 0.5 * (1 - p)))

        # Stop Scan pulses while a scan is running
        if self._scan_running:
            self.stop_btn.configure(fg_color=self._mix(C["accent"], "#d8b4fe", 0.45 * p))

        # sidebar right edge glows cyan (a live 'bus line')
        try:
            self._sidebar_edge.configure(fg_color=self._mix(C["border"], C["hud"], 0.25 + 0.5 * p))
        except Exception:
            pass

        # active nav item: accent bar breathes violet → cyan (neon)
        try:
            idx = self._active_nav
            if 0 <= idx < len(self._nav_bars) and self._nav_bars[idx] is not None:
                self._nav_bars[idx].configure(fg_color=self._mix(C["accent"], C["hud"], 0.3 + 0.55 * p))
        except Exception:
            pass

        # topbar ECG strip beats fast while a detection/scan is running
        if getattr(self, "_hud_strip", None) is not None:
            try:
                self._hud_strip.active = self._scan_running
            except Exception:
                pass

        # animated system tag in the topbar (if built)
        if getattr(self, "_sys_dot", None) is not None:
            try:
                self._sys_dot.configure(text_color=self._mix(C["bg_medium"], C["success"], 0.4 + 0.6 * p))
            except Exception:
                pass

        self.after(60, self._sidebar_tick)

    def _jack_set_hover(self, on):
        self._jack_hover = on
        if not self._jack_active:
            self.jack_btn.configure(fg_color=self._mix(self.colors["bg_light"], self.colors["info"], 0.15)
                                    if on else self.colors["bg_light"])

    def _set_jack_active(self, active):
        C = self.colors
        self._jack_active = active
        self.jack_btn.configure(fg_color=C["info"] if active else C["bg_light"],
                                border_color=C["info"])
        self._jack_title.configure(text_color="#ffffff" if active else C["info"])
        self._jack_sub.configure(text_color="#f3e8ff" if active else C["text_dim"])

    def _nav_hover(self, idx, on):
        if idx == self._active_nav:
            return
        C = self.colors
        self.nav_buttons[idx].configure(text_color=C["text"] if on else C["text_dim"])
        self._nav_bars[idx].configure(fg_color=C["border"] if on else C["bg_medium"])

    def _update_conn_card(self, uart_ok, adb_ok):
        C = self.colors
        self._conn = {"uart": uart_ok, "adb": adb_ok}
        for key, ok in self._conn.items():
            dot, name, st = self._conn_rows[key]
            dot.configure(text_color=C["success"] if ok else C["text_dim"])
            name.configure(text_color=C["text"] if ok else C["text_dim"])
            st.configure(text="" if self._sidebar_collapsed else ("live" if ok else "offline"),
                         text_color=C["success"] if ok else C["text_dim"])
        self._conn_card.configure(border_color=self._mix(C["border"], C["success"], 0.5)
                                  if (uart_ok or adb_ok) else C["border"])

    def toggle_sidebar(self):
        """Collapse to an icon rail (more room for pages) or expand back."""
        C = self.colors
        mini = self._sidebar_collapsed = not self._sidebar_collapsed
        self.sidebar.configure(width=self.SIDEBAR_W_MINI if mini else self.SIDEBAR_W)
        self._collapse_btn.configure(text="»" if mini else "«")
        if mini:
            self._brand_text.pack_forget()
            self._jack_text.pack_forget()
            self.version_label.pack_forget()
            self._collapse_btn.pack_configure(side="top")
        else:
            self._brand_text.pack(side="left", padx=(8, 0))
            self._jack_text.pack(side="left", fill="x", expand=True)
            self._collapse_btn.pack_configure(side="right")
            self.version_label.pack(side="left")
        for hdr, title in self._nav_headers:
            hdr.configure(text="" if mini else title, height=6 if mini else 18)
        for idx, btn in enumerate(self.nav_buttons):
            if btn is None:
                continue
            icon, label = self._nav_meta[idx]
            btn.configure(text=icon if mini else f"{icon}   {label}", anchor="center" if mini else "w")
        for key, (dot, name, st) in self._conn_rows.items():
            if mini:
                name.pack_forget()
            else:
                name.pack(side="left", padx=(6, 0), after=dot)
        self.stop_btn.configure(text="⏹" if mini else "⏹  Stop Scan")
        self._update_conn_card(self._conn["uart"], self._conn["adb"])

    def _create_main_area(self):
        """Create main content area"""
        self.main_area = ctk.CTkFrame(self, fg_color=self.colors["bg_dark"], corner_radius=0)
        self.main_area.pack(side="right", fill="both", expand=True)

        # Top bar with search
        self.topbar = ctk.CTkFrame(self.main_area, height=60, fg_color=self.colors["bg_medium"], corner_radius=0)
        self.topbar.pack(fill="x")
        self.topbar.pack_propagate(False)

        # Search entry in topbar
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(
            self.topbar, placeholder_text="🔍 Search devices, components, issues...",
            textvariable=self.search_var, width=400, height=38,
            fg_color=self.colors["bg_light"], border_color=self.colors["border"],
            font=("Segoe UI", 13)
        )
        self.search_entry.pack(side="left", padx=20, pady=11)
        self.search_entry.bind("<Return>", lambda e: self.perform_search())

        search_btn = ctk.CTkButton(
            self.topbar, text="Search", width=100, height=38,
            fg_color=self.colors["accent"], hover_color=self.colors["accent_hover"],
            command=self.perform_search
        )
        search_btn.pack(side="left", padx=(0, 20), pady=11)

        # ── robotics system tag (right of topbar) ──
        sys_tag = ctk.CTkFrame(self.topbar, fg_color="transparent")
        sys_tag.pack(side="right", padx=18)
        self._sys_dot = ctk.CTkLabel(sys_tag, text="●", font=("Consolas", 13),
                                     text_color=self.colors["success"], width=14)
        self._sys_dot.pack(side="left")
        ctk.CTkLabel(sys_tag, text="NEURAL DIAGNOSTIC CONSOLE", font=("Consolas", 11, "bold"),
                     text_color=self.colors["hud"]).pack(side="left", padx=(4, 0))

        # ── live HUD diagnostic strip — shown on every page, under the topbar ──
        try:
            from app.gui.pages.jack_page import HudBand
            self._hud_strip = HudBand(self.main_area, bg=self.colors["bg_dark"],
                                      accent=self.colors["hud"], label="SYSTEM BUS")
            self._hud_strip.canvas.pack(fill="x", padx=16, pady=(4, 0))
        except Exception as e:
            print(f"[UI] HUD strip skipped: {e}")

        # Content frame (this is where pages are loaded)
        self.content = ctk.CTkScrollableFrame(
            self.main_area, fg_color=self.colors["bg_dark"],
            scrollbar_button_color=self.colors["bg_light"]
        )
        self.content.pack(fill="both", expand=True, padx=0, pady=0)

    def _create_statusbar(self):
        """Create bottom status bar"""
        self.statusbar = ctk.CTkFrame(self.main_area, height=30, fg_color=self.colors["bg_medium"], corner_radius=0)
        self.statusbar.pack(side="bottom", fill="x")
        self.statusbar.pack_propagate(False)

        ctk.CTkLabel(self.statusbar, text="◢", font=("Consolas", 11, "bold"),
                     text_color=self.colors["hud"]).pack(side="left", padx=(15, 4))
        self.status_label = ctk.CTkLabel(
            self.statusbar, text=f"READY · {len(self.devices)} devices loaded",
            font=("Consolas", 11), text_color=self.colors["text_dim"]
        )
        self.status_label.pack(side="left")

        self.connection_label = ctk.CTkLabel(
            self.statusbar, text="⚡ HARDWARE: NOT CONNECTED",
            font=("Consolas", 11, "bold"), text_color=self.colors["warning"]
        )
        self.connection_label.pack(side="right", padx=15)

        # Auto-check connections every 5 seconds
        self._check_connections()

    def _play_boot_sequence(self):
        """One-time 'Neural Core' power-on overlay. Click / any key to skip."""
        import tkinter as tk, math, time
        C = self.colors
        try:
            ov = tk.Canvas(self, bg=C["bg_dark"], highlightthickness=0, bd=0)
            ov.place(relx=0, rely=0, relwidth=1, relheight=1)
            # NOTE: on a tk.Canvas, lift()/tkraise() are aliased to tag_raise (an item op),
            # so use the low-level Tk 'raise' to stack the widget above its siblings.
            try:
                ov.tk.call("raise", ov._w)
            except Exception:
                pass
            ov.focus_set()
        except Exception:
            return
        done = {"v": False, "sched": False}

        def finish(_e=None):
            if done["v"]:
                return
            done["v"] = True
            try:
                ov.destroy()
            except Exception:
                pass

        ov.bind("<Button-1>", finish)
        ov.bind("<Key>", finish)

        t0 = time.time()
        DUR = 2.3
        logs = [
            (0.06, "◢ BOOTING NEURAL FAULT ENGINE …"),
            (0.26, "  loading device database … %d phones" % len(self.devices)),
            (0.46, "  calibrating diagnostic bus … OK"),
            (0.64, "  arming UART / ADB / EDL probes … OK"),
            (0.82, "  neural core sync … 100%"),
        ]

        def frame():
            if done["v"]:
                return
            try:
                if not ov.winfo_exists():
                    return
            except Exception:
                return
            w, h = self.winfo_width(), self.winfo_height()
            if w <= 2:
                w = self.winfo_screenwidth()
            if h <= 2:
                h = self.winfo_screenheight()
            el = time.time() - t0
            t = min(1.0, el / DUR)
            ph = el * 3.2
            ease = 1 - (1 - t) ** 3
            ov.delete("all")
            cx, cy = w / 2, h / 2 - 50

            # sweeping scan-line across the whole screen
            sy = (el * 320) % h
            ov.create_line(0, sy, w, sy, fill=self._mix(C["bg_dark"], C["hud"], 0.1))

            # converging rings (settle inward as it powers up)
            for i in range(6):
                rr = (250 - i * 28) * (1.0 - 0.55 * ease) + (64 - i * 7)
                ov.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                               outline=self._mix(C["bg_dark"], C["hud"], 0.09 + i * 0.05), width=1)
            # rotating hexagon
            R = 88
            pts = []
            for k in range(6):
                a = ph * 0.6 + math.radians(60 * k)
                pts += [cx + R * math.cos(a), cy + R * math.sin(a)]
            ov.create_polygon(*pts, outline=self._mix(C["bg_dark"], C["hud"], 0.55), fill="", width=2)
            # counter-spinning violet arcs
            for k in range(3):
                ov.create_arc(cx - 68, cy - 68, cx + 68, cy + 68,
                              start=(-ph * 45 + k * 120) % 360, extent=48, style="arc",
                              outline=self._mix(C["bg_dark"], C["accent"], 0.75), width=2)
            # pulsing core
            pr = 24 + 6 * math.sin(ph * 2)
            ov.create_oval(cx - pr, cy - pr, cx + pr, cy + pr,
                           fill=self._mix(C["accent"], "#ffffff", 0.22), outline=self._mix(C["accent"], "#ffffff", 0.5))
            ov.create_oval(cx - pr * 0.45, cy - pr * 0.45, cx + pr * 0.45, cy + pr * 0.45, fill="#ffffff", outline="")

            # title
            ov.create_text(cx, cy + 128, text="M O O X Y", fill="#ffffff", font=("Segoe UI", 32, "bold"))
            ov.create_text(cx, cy + 162, text="NEURAL FAULT ENGINE",
                           fill=self._mix(C["bg_dark"], C["hud"], 0.9), font=("Consolas", 13, "bold"))

            # boot log block
            lx, ly = cx - 210, cy + 200
            for thr, line in logs:
                if t >= thr:
                    ov.create_text(lx, ly, anchor="w", text=line,
                                   fill=self._mix(C["bg_dark"], C["hud"], 0.6), font=("Consolas", 11))
                    ly += 20

            # progress bar
            bw, by = 380, cy + 310
            bx = cx - bw / 2
            ov.create_rectangle(bx, by, bx + bw, by + 6, outline=self._mix(C["bg_dark"], C["hud"], 0.3), width=1)
            ov.create_rectangle(bx, by, bx + bw * t, by + 6, fill=C["hud"], outline="")
            if t >= 1.0:
                blink = int(el * 3) % 2 == 0
                ov.create_text(cx, by + 24, text="◢ NEURAL CORE ONLINE" + ("  ▮" if blink else ""),
                               fill=self._mix(C["bg_dark"], C["success"], 0.95), font=("Consolas", 12, "bold"))
                if not done["sched"]:
                    done["sched"] = True
                    self.after(550, finish)
            else:
                ov.create_text(cx, by + 24, text=f"{int(t * 100):3d}%   INITIALISING",
                               fill=self._mix(C["bg_dark"], C["hud"], 0.7), font=("Consolas", 11))
                ov.create_text(cx, h - 26, text="click / press any key to skip",
                               fill=self._mix(C["bg_dark"], C["text_dim"], 0.6), font=("Consolas", 9))

            ov.after(33, frame)

        frame()

    def _stop_scan(self):
        """Stop any running scan/detection."""
        import threading
        if self._stop_event and isinstance(self._stop_event, threading.Event):
            self._stop_event.set()
        self._scan_running = False
        self.stop_btn.configure(state="disabled", text="…" if self._sidebar_collapsed else "⏹  Stopping...",
                                fg_color=self.colors["bg_light"])
        self.update_status("Scan stopped by user")
        # Re-enable after 2 seconds
        try:
            self.after(2000, lambda: self.stop_btn.configure(
                state="disabled", text=self._stop_text()))
        except Exception:
            pass

    def _stop_text(self):
        return "⏹" if getattr(self, "_sidebar_collapsed", False) else "⏹  Stop Scan"

    def enable_stop_button(self, stop_event):
        """Called by scan pages when detection starts. Pass a threading.Event."""
        self._stop_event = stop_event
        self._scan_running = True          # sidebar tick makes it pulse red
        try:
            self.stop_btn.configure(state="normal", text=self._stop_text(), fg_color=self.colors["accent"])
        except Exception:
            pass

    def disable_stop_button(self):
        """Called by scan pages when detection finishes."""
        self._stop_event = None
        self._scan_running = False
        try:
            self.stop_btn.configure(state="disabled", text=self._stop_text(), fg_color=self.colors["bg_light"])
        except Exception:
            pass

    def _check_connections(self):
        """Check FTDI and ADB connections periodically."""
        import threading

        def check():
            ftdi_ok = False
            adb_ok = False

            # Check FTDI serial ports
            try:
                import serial.tools.list_ports
                for port in serial.tools.list_ports.comports():
                    if "FTDI" in port.description or "0403:6001" in port.hwid.upper():
                        ftdi_ok = True
                        break
            except Exception as e:
                print(f"[ConnectionCheck] FTDI check failed: {e}")

            # Check ADB
            try:
                import subprocess
                result = subprocess.run("adb devices", capture_output=True, text=True,
                                       timeout=3, shell=True)
                if result.stdout and "device" in result.stdout.split("\n", 1)[-1]:
                    adb_ok = True
            except Exception as e:
                print(f"[ConnectionCheck] ADB check failed: {e}")

            # Update UI — wrapped in try/except for app shutdown safety
            def update():
                try:
                    self._update_conn_card(ftdi_ok, adb_ok)
                except Exception:
                    pass
                try:
                    if self.proactive:
                        self.proactive.on_connection(ftdi_ok, adb_ok)
                except Exception:
                    pass
                try:
                    if ftdi_ok and adb_ok:
                        self.connection_label.configure(
                            text="✅ Device + ADB Connected", text_color=self.colors["success"])
                    elif ftdi_ok:
                        self.connection_label.configure(
                            text="✅ Device Connected", text_color=self.colors["success"])
                    elif adb_ok:
                        self.connection_label.configure(
                            text="✅ ADB Connected", text_color=self.colors["success"])
                    else:
                        self.connection_label.configure(
                            text="⚡ Hardware: Not Connected", text_color=self.colors["warning"])
                except Exception:
                    pass

            try:
                self.after(0, update)
            except (RuntimeError, Exception):
                return  # App is closing, stop silently

        threading.Thread(target=check, daemon=True).start()

        # Check again after 5 seconds
        try:
            self.after(5000, self._check_connections)
        except (RuntimeError, Exception):
            pass  # App is closing

    def set_active_nav(self, index):
        """Highlight active navigation button (index -1 = none, used by the Jack page)"""
        C = self.colors
        self._active_nav = index
        for i, btn in enumerate(self.nav_buttons):
            if btn is None:
                continue
            active = i == index
            btn.configure(fg_color=self._mix(C["bg_medium"], C["accent"], 0.22) if active else "transparent",
                          text_color=C["text"] if active else C["text_dim"],
                          font=("Segoe UI", 13, "bold") if active else ("Segoe UI", 13))
            self._nav_bars[i].configure(fg_color=C["accent"] if active else C["bg_medium"])
        if hasattr(self, "jack_btn"):
            self._set_jack_active(False)

    def clear_content(self):
        """Clear the main content area"""
        # The Jack page replaces the scrollable content frame — tear it down and restore.
        jack_frame = getattr(self, "jack_page_frame", None)
        if jack_frame is not None:
            jack_frame.destroy()
            self.jack_page_frame = None
            self.content.pack(fill="both", expand=True, padx=0, pady=0, before=self.statusbar)
        for widget in self.content.winfo_children():
            widget.destroy()

    def perform_search(self):
        """Execute search"""
        query = self.search_var.get().strip()
        if query:
            self.show_search(query)

    def save_database(self):
        """Save current devices list back to JSON file"""
        try:
            data = {
                "_info": "Mooxy AI Fault Detector - Device Database",
                "_note": "Devices added via hardware detection or manually by technician.",
                "devices": self.devices
            }
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving database: {e}")
            return False

    def add_device_to_db(self, device_data):
        """Add a new device to the database and save"""
        self.devices.append(device_data)
        self.filtered_devices = self.devices.copy()
        self.save_database()
        self.version_label.configure(text=f"v1.0.0 • {len(self.devices)} Devices")
        self.update_status(f"Device added: {device_data.get('brand', '')} {device_data.get('model', '')} • {len(self.devices)} total devices")

    def delete_device_from_db(self, device_id):
        """Remove a device from the database"""
        self.devices = [d for d in self.devices if d.get("id") != device_id]
        self.filtered_devices = self.devices.copy()
        self.save_database()
        self.version_label.configure(text=f"v1.0.0 • {len(self.devices)} Devices")
        self.update_status(f"Device removed • {len(self.devices)} devices remaining")

    # --- PAGE METHODS ---

    def show_jack(self):
        if getattr(self, "jack_page_frame", None) is not None:
            return  # already open
        self.set_active_nav(-1)
        self._set_jack_active(True)
        self.clear_content()
        from app.gui.pages.jack_page import render_jack_page
        render_jack_page(self)

    def show_dashboard(self):
        self.set_active_nav(0)
        self.clear_content()
        from app.gui.pages.dashboard import render_dashboard
        render_dashboard(self)

    def show_hw_detect(self):
        self.set_active_nav(1)
        self.clear_content()
        from app.gui.pages.hw_detect import render_hw_detect
        render_hw_detect(self)

    def show_adb_detect(self):
        self.set_active_nav(2)
        self.clear_content()
        from app.gui.pages.adb_detect import render_adb_detect
        render_adb_detect(self)

    def show_power_test(self):
        self.set_active_nav(3)
        self.clear_content()
        from app.gui.pages.power_test import render_power_test
        render_power_test(self)

    def show_display_test(self):
        self.set_active_nav(4)
        self.clear_content()
        from app.gui.pages.display_test import render_display_test
        render_display_test(self)

    def show_clock_test(self):
        self.set_active_nav(5)
        self.clear_content()
        from app.gui.pages.clock_test import render_clock_test
        render_clock_test(self)

    def show_battery_test(self):
        self.set_active_nav(6)
        self.clear_content()
        from app.gui.pages.battery_test import render_battery_test
        render_battery_test(self)

    def show_sensor_test(self):
        self.set_active_nav(7)
        self.clear_content()
        from app.gui.pages.sensor_test import render_sensor_test
        render_sensor_test(self)

    def show_audio_test(self):
        self.set_active_nav(8)
        self.clear_content()
        from app.gui.pages.audio_test import render_audio_test
        render_audio_test(self)

    def show_connectivity_test(self):
        self.set_active_nav(9)
        self.clear_content()
        from app.gui.pages.connectivity_test import render_connectivity_test
        render_connectivity_test(self)

    def show_storage_test(self):
        self.set_active_nav(10)
        self.clear_content()
        from app.gui.pages.storage_test import render_storage_test
        render_storage_test(self)

    def show_thermal_test(self):
        self.set_active_nav(11)
        self.clear_content()
        from app.gui.pages.thermal_test import render_thermal_test
        render_thermal_test(self)

    def show_uart_analysis(self):
        self.set_active_nav(3)
        self.clear_content()
        from app.gui.pages.uart_analysis import render_uart_analysis
        render_uart_analysis(self)

    def show_edl_detect(self):
        self.set_active_nav(13)
        self.clear_content()
        from app.gui.pages.edl_detect import render_edl_detect
        render_edl_detect(self)

    def show_smart_diagnostics(self):
        self.set_active_nav(4)
        self.clear_content()
        from app.gui.pages.smart_diagnostics import render_smart_diagnostics
        render_smart_diagnostics(self)

    def show_community(self):
        self.set_active_nav(5)
        self.clear_content()
        from app.gui.pages.community_page import render_community_page
        render_community_page(self)

    def show_auto_unlock(self):
        self.set_active_nav(6)
        self.clear_content()
        from app.gui.pages.unlock_tool import render_unlock_tool
        render_unlock_tool(self)

    def show_frp_unlock(self):
        self.set_active_nav(7)
        self.clear_content()
        from app.gui.pages.frp_unlock import render_frp_unlock
        render_frp_unlock(self)

    def show_imei_repair(self):
        self.set_active_nav(14)
        self.clear_content()
        from app.gui.pages.imei_page import render_imei_page
        render_imei_page(self)

    def show_firmware_flash(self):
        self.set_active_nav(15)
        self.clear_content()
        from app.gui.pages.firmware_flash import render_firmware_flash
        render_firmware_flash(self)

    def show_ai_log_analysis(self):
        self.set_active_nav(8)
        self.clear_content()
        from app.gui.pages.ai_log_analysis import render_ai_log_analysis
        render_ai_log_analysis(self)

    def show_history(self):
        self.set_active_nav(9)
        self.clear_content()
        from app.gui.pages.history_page import render_history
        render_history(self)

    def show_network_diagnostic(self):
        self.set_active_nav(10)
        self.clear_content()
        from app.gui.pages.network_diagnostic import render_network_diagnostic
        render_network_diagnostic(self)

    def show_schematic_diagnostics(self):
        self.set_active_nav(11)
        self.clear_content()
        from app.gui.pages.schematic_diagnostics import render_schematic_diagnostics
        render_schematic_diagnostics(self)

    def show_export(self):
        self.set_active_nav(12)
        self.clear_content()
        from app.gui.pages.export_page import render_export
        render_export(self)

    def show_add_device(self):
        self.clear_content()
        from app.gui.pages.add_device import render_add_device
        render_add_device(self)

    def show_devices(self):
        self.clear_content()
        from app.gui.pages.device_list import render_device_list
        render_device_list(self)

    def show_search(self, query=None):
        self.clear_content()
        from app.gui.pages.search_page import render_search
        render_search(self, query)

    def show_device_detail(self, device):
        """Show detailed view for a specific device"""
        self.current_device = device
        self.clear_content()
        from app.gui.pages.device_detail import render_device_detail
        render_device_detail(self, device)

    def update_status(self, message):
        """Update status bar message"""
        self.status_label.configure(text=message)


def main():
    app = MobileRepairTool()
    app.mainloop()

if __name__ == "__main__":
    main()
