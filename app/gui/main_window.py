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

        # Color scheme — "Royal Violet" (deep indigo-black + violet + magenta)
        self.colors = {
            "bg_dark": "#0b0d1a",
            "bg_medium": "#10121f",
            "bg_light": "#1b1f38",
            "bg_card": "#151830",
            "accent": "#a855f7",        # violet — primary buttons
            "accent_hover": "#c084fc",
            "success": "#34d399",
            "warning": "#fbbf24",
            "info": "#818cf8",          # indigo
            "secondary": "#ec4899",     # magenta
            "text": "#ffffff",
            "text_dim": "#9a93b5",
            "border": "#262a45"
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
            hdr = ctk.CTkLabel(self.nav_scroll, text=title, font=("Segoe UI", 10, "bold"),
                               text_color=self._mix(C["text_dim"], C["bg_medium"], 0.25), height=18, anchor="w")
            hdr.pack(fill="x", padx=14, pady=(10, 2))
            self._nav_headers.append((hdr, title))
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

        self.status_label = ctk.CTkLabel(
            self.statusbar, text=f"Ready • {len(self.devices)} devices loaded",
            font=("Segoe UI", 11), text_color=self.colors["text_dim"]
        )
        self.status_label.pack(side="left", padx=15)

        self.connection_label = ctk.CTkLabel(
            self.statusbar, text="⚡ Hardware: Not Connected",
            font=("Segoe UI", 11), text_color=self.colors["warning"]
        )
        self.connection_label.pack(side="right", padx=15)

        # Auto-check connections every 5 seconds
        self._check_connections()

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
