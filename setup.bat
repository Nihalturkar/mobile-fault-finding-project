@echo off
title Mobile Repair Tool - Setup
color 0A
echo.
echo  ====================================
echo   Mobile Repair Tool Pro - Setup
echo  ====================================
echo.
echo  [1] Checking Python installation...
python --version 2>nul
if errorlevel 1 (
    py --version 2>nul
    if errorlevel 1 (
        echo  [ERROR] Python not found!
        echo  Install Python 3.10+ from https://python.org
        echo  Make sure to check "Add Python to PATH" during install
        pause
        exit /b
    )
)
echo  [OK] Python found.
echo.
echo  [2] Installing dependencies...
echo  This may take 2-3 minutes...
pip install customtkinter fpdf2 rich click pyserial fuzzywuzzy python-Levenshtein fastapi uvicorn sqlalchemy pydantic pillow aiofiles jinja2 python-multipart websockets 2>nul || py -m pip install customtkinter fpdf2 rich click pyserial fuzzywuzzy python-Levenshtein fastapi uvicorn sqlalchemy pydantic pillow aiofiles jinja2 python-multipart websockets
echo.
echo  [OK] All dependencies installed.
echo.
echo  ====================================
echo   Setup Complete!
echo  ====================================
echo.
echo   To run the GUI app:    start.bat
echo   To run the CLI:        cli.bat
echo   To run the API server: api.bat
echo.
pause
