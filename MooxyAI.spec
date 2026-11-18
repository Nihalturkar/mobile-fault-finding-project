# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = 'C:/Users/marveldev/REPAIR/mobile-fault-finding-project'

# Ship source + data folders so the app's Path(__file__)-relative lookups
# (config/, assets/, loaders/) resolve the same way when frozen (onedir).
datas = [
    (ROOT + '/app', 'app'),
    (ROOT + '/config', 'config'),
    (ROOT + '/assets', 'assets'),
    (ROOT + '/loaders', 'loaders'),
]
binaries = []
hiddenimports = [
    'customtkinter', 'serial', 'serial.tools', 'serial.tools.list_ports',
    'PIL', 'PIL.Image', 'numpy', 'fpdf', 'usb', 'usb.core', 'usb.backend',
    'usb.backend.libusb1',
    # voice (Sections 4/5)
    'edge_tts', 'sounddevice', 'aiohttp', 'certifi',
]
# Pull in EVERY submodule of app/ (pages + hardware + jack) — covers the lazy
# `from app.gui.pages.X import ...` imports done inside functions.
hiddenimports += collect_submodules('app')

for pkg in ('customtkinter', 'edge_tts', 'sounddevice'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h


a = Analysis(
    [ROOT + '/run_gui.py'],
    pathex=[ROOT],
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
    name='MooxyAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ROOT + '/assets/logo.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MooxyAI',
)
