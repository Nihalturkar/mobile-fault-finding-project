"""
Build script for Mooxy AI Fault Detector EXE.
Creates a standalone executable that works on any Windows laptop.

Usage: python build_exe.py
"""
import PyInstaller.__main__
import os
import sys

# Get the project root directory
ROOT = os.path.dirname(os.path.abspath(__file__))

# PyInstaller arguments
args = [
    os.path.join(ROOT, "run_gui.py"),           # Entry point
    "--name=MooxyAI",                             # EXE name
    "--onedir",                                  # One directory (faster startup than --onefile)
    "--windowed",                                # No console window (GUI app)
    "--noconfirm",                               # Overwrite without asking
    f"--icon={os.path.join(ROOT, 'assets', 'logo.ico')}",  # App icon

    # Add all app modules
    f"--add-data={os.path.join(ROOT, 'app')}{'%sapp' % os.pathsep}",
    f"--add-data={os.path.join(ROOT, 'config')}{'%sconfig' % os.pathsep}",
    f"--add-data={os.path.join(ROOT, 'assets')}{'%sassets' % os.pathsep}",

    # Hidden imports that PyInstaller might miss
    "--hidden-import=customtkinter",
    "--hidden-import=serial",
    "--hidden-import=serial.tools",
    "--hidden-import=serial.tools.list_ports",
    "--hidden-import=PIL",
    "--hidden-import=PIL.Image",
    "--hidden-import=numpy",
    "--hidden-import=fpdf",
    "--hidden-import=usb",
    "--hidden-import=usb.core",
    "--hidden-import=usb.backend",
    "--hidden-import=usb.backend.libusb1",
    "--hidden-import=app",
    "--hidden-import=app.gui",
    "--hidden-import=app.gui.main_window",
    "--hidden-import=app.gui.pages",
    "--hidden-import=app.gui.pages.dashboard",
    "--hidden-import=app.gui.pages.full_diagnostic",
    "--hidden-import=app.gui.pages.hw_detect",
    "--hidden-import=app.gui.pages.adb_detect",
    "--hidden-import=app.gui.pages.power_test",
    "--hidden-import=app.gui.pages.display_test",
    "--hidden-import=app.gui.pages.clock_test",
    "--hidden-import=app.gui.pages.battery_test",
    "--hidden-import=app.gui.pages.sensor_test",
    "--hidden-import=app.gui.pages.audio_test",
    "--hidden-import=app.gui.pages.connectivity_test",
    "--hidden-import=app.gui.pages.storage_test",
    "--hidden-import=app.gui.pages.thermal_test",
    "--hidden-import=app.gui.pages.uart_analysis",
    "--hidden-import=app.gui.pages.frp_unlock",
    "--hidden-import=app.gui.pages.imei_page",
    "--hidden-import=app.gui.pages.firmware_flash",
    "--hidden-import=app.gui.pages.ai_log_analysis",
    "--hidden-import=app.gui.pages.history_page",
    "--hidden-import=app.gui.pages.export_page",
    "--hidden-import=app.gui.pages.add_device",
    "--hidden-import=app.gui.pages.device_list",
    "--hidden-import=app.gui.pages.search_page",
    "--hidden-import=app.gui.pages.device_detail",
    "--hidden-import=app.gui.pages.diagnostics",
    "--hidden-import=app.gui.pages.auto_detect",
    "--hidden-import=app.gui.pages.repair_history",
    "--hidden-import=app.gui.history_manager",
    "--hidden-import=app.hardware",
    "--hidden-import=app.hardware.adb_detector",
    "--hidden-import=app.hardware.battery_tester",
    "--hidden-import=app.hardware.clock_tester",
    "--hidden-import=app.hardware.display_tester",
    "--hidden-import=app.hardware.power_tester",
    "--hidden-import=app.hardware.sensor_tester",
    "--hidden-import=app.hardware.audio_tester",
    "--hidden-import=app.hardware.connectivity_tester",
    "--hidden-import=app.hardware.storage_tester",
    "--hidden-import=app.hardware.thermal_tester",
    "--hidden-import=app.hardware.uart_analyzer",
    "--hidden-import=app.hardware.imei_repair",
    "--hidden-import=app.hardware.firmware_flasher",
    "--hidden-import=app.hardware.frp_unlocker",
    "--hidden-import=app.hardware.ai_analyzer",
    "--hidden-import=app.hardware.fault_analyzer",
    "--hidden-import=app.hardware.device_detector",
    "--hidden-import=app.hardware.edl_detector",
    "--hidden-import=app.hardware.rule_engine",

    # Collect all customtkinter data (themes, etc.)
    "--collect-all=customtkinter",

    # Work directory
    f"--workpath={os.path.join(ROOT, 'build')}",
    f"--distpath={os.path.join(ROOT, 'dist')}",
    f"--specpath={ROOT}",
]

print("=" * 60)
print("  Building Mooxy AI Fault Detector EXE")
print("=" * 60)
print(f"  Entry: run_gui.py")
print(f"  Output: dist/MooxyAI/")
print("=" * 60)

PyInstaller.__main__.run(args)

print()
print("=" * 60)
print("  BUILD COMPLETE!")
print("=" * 60)
print(f"  EXE: dist/MooxyAI/MooxyAI.exe")
print()
print("  To distribute:")
print("  1. Copy the entire 'dist/MooxyAI' folder")
print("  2. Include 'adb.exe' in the folder (for ADB features)")
print("  3. Run MooxyAI.exe on any Windows PC")
print("=" * 60)
