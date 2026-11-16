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

        # Color scheme
        self.colors = {
            "bg_dark": "#0a0a1a",
            "bg_medium": "#12122a",
            "bg_light": "#1a1a3e",
            "bg_card": "#1e1e42",
            "accent": "#e94560",
            "accent_hover": "#ff6b81",
            "success": "#2ed573",
            "warning": "#ffa502",
            "info": "#1e90ff",
            "text": "#ffffff",
            "text_dim": "#8892b0",
            "border": "#2a2a5a"
        }

        self.configure(fg_color=self.colors["bg_dark"])

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

    def _create_sidebar(self):
        """Create left sidebar with navigation"""
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=self.colors["bg_medium"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # App title/logo
        title_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(20, 5))

        # Load logo image
        logo_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            from PIL import Image
            logo_img = ctk.CTkImage(
                light_image=Image.open(logo_path),
                dark_image=Image.open(logo_path),
                size=(80, 80),
            )
            ctk.CTkLabel(title_frame, image=logo_img, text="").pack(pady=(0, 5))
            # Keep reference to prevent garbage collection
            self._logo_img = logo_img
        else:
            ctk.CTkLabel(title_frame, text="🔧", font=("Segoe UI Emoji", 32)).pack()
        ctk.CTkLabel(title_frame, text="Mooxy AI", font=("Segoe UI", 22, "bold"), text_color=self.colors["accent"]).pack()
        ctk.CTkLabel(title_frame, text="Fault Detector", font=("Segoe UI", 16), text_color=self.colors["text_dim"]).pack()

        # Separator
        ctk.CTkFrame(self.sidebar, height=2, fg_color=self.colors["border"]).pack(fill="x", padx=15, pady=15)

        # Scrollable navigation area
        self.nav_scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color="transparent",
            scrollbar_button_color=self.colors["bg_light"],
            scrollbar_button_hover_color=self.colors["border"],
        )
        self.nav_scroll.pack(fill="both", expand=True)

        # Navigation buttons — only essential tools for technicians
        nav_items = [
            ("📊 Dashboard", self.show_dashboard),
            ("🔌 HW Detect", self.show_hw_detect),
            ("📱 ADB Detect", self.show_adb_detect),
            ("🔌 Fault Analyzer", self.show_uart_analysis),
            ("🧠 Smart Diagnostics", self.show_smart_diagnostics),
            ("🌍 Community Fixes", self.show_community),
            ("⚡ Auto Unlock", self.show_auto_unlock),
            ("🔓 FRP/Lock Unlock", self.show_frp_unlock),
            ("🤖 AI Analysis", self.show_ai_log_analysis),
            ("📜 History", self.show_history),
            ("📡 Network Diagnostic", self.show_network_diagnostic),
            ("🔬 Schematic Diagnosis", self.show_schematic_diagnostics),
            ("📤 Export PDF", self.show_export),
            ("⚡ EDL 9008 Detect", self.show_edl_detect),
        ]

        self.nav_buttons = []
        for text, command in nav_items:
            btn = ctk.CTkButton(
                self.nav_scroll, text=text, command=command,
                font=("Segoe UI", 14), height=38,
                fg_color="transparent", text_color=self.colors["text_dim"],
                hover_color=self.colors["bg_light"],
                anchor="w", corner_radius=8
            )
            btn.pack(fill="x", padx=4, pady=1)
            self.nav_buttons.append(btn)

        # Stop Scan button — visible at bottom of sidebar
        ctk.CTkFrame(self.sidebar, height=2, fg_color=self.colors["border"]).pack(
            side="bottom", fill="x", padx=15, pady=(0, 5))

        self._stop_event = None  # Will be set by scan pages

        self.stop_btn = ctk.CTkButton(
            self.sidebar, text="⏹ Stop Scan", height=42,
            font=("Segoe UI", 14, "bold"),
            fg_color=self.colors["accent"], hover_color="#ff6b81",
            text_color="#ffffff", corner_radius=8,
            command=self._stop_scan,
        )
        self.stop_btn.pack(side="bottom", fill="x", padx=10, pady=(0, 5))
        self.stop_btn.configure(state="disabled")  # disabled until scan starts

        # Version info at very bottom
        self.version_label = ctk.CTkLabel(self.sidebar, text=f"v1.0.0 • {len(self.devices)} Devices", font=("Segoe UI", 10), text_color=self.colors["text_dim"])
        self.version_label.pack(side="bottom", pady=10)

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
        self.stop_btn.configure(state="disabled", text="⏹ Stopping...")
        self.update_status("Scan stopped by user")
        # Re-enable after 2 seconds
        try:
            self.after(2000, lambda: self.stop_btn.configure(
                state="disabled", text="⏹ Stop Scan"))
        except Exception:
            pass

    def enable_stop_button(self, stop_event):
        """Called by scan pages when detection starts. Pass a threading.Event."""
        import threading
        self._stop_event = stop_event
        try:
            self.stop_btn.configure(state="normal", text="⏹ Stop Scan")
        except Exception:
            pass

    def disable_stop_button(self):
        """Called by scan pages when detection finishes."""
        self._stop_event = None
        try:
            self.stop_btn.configure(state="disabled", text="⏹ Stop Scan")
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
        """Highlight active navigation button"""
        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.configure(fg_color=self.colors["accent"], text_color=self.colors["text"])
            else:
                btn.configure(fg_color="transparent", text_color=self.colors["text_dim"])

    def clear_content(self):
        """Clear the main content area"""
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
        self.set_active_nav(12)
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
        from app.gui.pages.auto_unlock import render_auto_unlock
        render_auto_unlock(self)

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
