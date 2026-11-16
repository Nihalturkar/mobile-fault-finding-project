import ctypes
import sys

# MUST be called before any tkinter window — tells Windows taskbar to use our icon, not python.exe's
if sys.platform == "win32":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mooxy.ai.fault.detector")

from app.gui.main_window import main

if __name__ == "__main__":
    main()
