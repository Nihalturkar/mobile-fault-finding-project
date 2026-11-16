# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\91750\\Desktop\\mobile-repair-tool\\app', 'app'), ('C:\\Users\\91750\\Desktop\\mobile-repair-tool\\config', 'config'), ('C:\\Users\\91750\\Desktop\\mobile-repair-tool\\assets', 'assets')]
binaries = []
hiddenimports = ['customtkinter', 'serial', 'serial.tools', 'serial.tools.list_ports', 'PIL', 'PIL.Image', 'numpy', 'fpdf', 'usb', 'usb.core', 'usb.backend', 'usb.backend.libusb1', 'app', 'app.gui', 'app.gui.main_window', 'app.gui.pages', 'app.gui.pages.dashboard', 'app.gui.pages.full_diagnostic', 'app.gui.pages.hw_detect', 'app.gui.pages.adb_detect', 'app.gui.pages.power_test', 'app.gui.pages.display_test', 'app.gui.pages.clock_test', 'app.gui.pages.battery_test', 'app.gui.pages.sensor_test', 'app.gui.pages.audio_test', 'app.gui.pages.connectivity_test', 'app.gui.pages.storage_test', 'app.gui.pages.thermal_test', 'app.gui.pages.uart_analysis', 'app.gui.pages.frp_unlock', 'app.gui.pages.imei_page', 'app.gui.pages.firmware_flash', 'app.gui.pages.ai_log_analysis', 'app.gui.pages.history_page', 'app.gui.pages.export_page', 'app.gui.pages.add_device', 'app.gui.pages.device_list', 'app.gui.pages.search_page', 'app.gui.pages.device_detail', 'app.gui.pages.diagnostics', 'app.gui.pages.auto_detect', 'app.gui.pages.repair_history', 'app.gui.history_manager', 'app.hardware', 'app.hardware.adb_detector', 'app.hardware.battery_tester', 'app.hardware.clock_tester', 'app.hardware.display_tester', 'app.hardware.power_tester', 'app.hardware.sensor_tester', 'app.hardware.audio_tester', 'app.hardware.connectivity_tester', 'app.hardware.storage_tester', 'app.hardware.thermal_tester', 'app.hardware.uart_analyzer', 'app.hardware.imei_repair', 'app.hardware.firmware_flasher', 'app.hardware.frp_unlocker', 'app.hardware.ai_analyzer', 'app.hardware.fault_analyzer', 'app.hardware.device_detector', 'app.hardware.edl_detector', 'app.hardware.rule_engine', 'app.gui.pages.schematic_diagnostics', 'app.hardware.boardview_loader', 'app.hardware.schematic_diagnosis', 'app.hardware.camera_tester']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\91750\\Desktop\\mobile-repair-tool\\run_gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MobileRepairToolPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MobileRepairToolPro',
)
