@echo off
cd /d "%~dp0"
echo ============================================================
echo  ForzaWheel Windows Bridge - Setup
echo ============================================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [OK] Python found.
python --version

REM Install Python dependencies
echo.
echo Installing Python dependencies...
pip install PyQt5==5.15.11 pywin32
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.

REM Check vJoy DLL
echo.
if exist "vJoy\x64\vJoyInterface.dll" (
    echo [OK] vJoy DLL found.
) else (
    echo [WARNING] vJoy DLL not found.
)

REM Check if vJoy driver is installed
echo.
echo Checking vJoy driver installation...
reg query "HKLM\SYSTEM\CurrentControlSet\Services\vjoy" >nul 2>&1
if errorlevel 1 (
    echo [INFO] vJoy driver not detected. Launching vJoy installer...
    echo This requires Administrator privileges.
    echo After installation, configure vJoy device 1 with:
    echo   - Axes: X, Y, Z, Rx
    echo   - Buttons: at least 12
    echo   - POV Hats: 0
    echo.
    if exist "vJoy\vJoySetup.exe" (
        start "" "vJoy\vJoySetup.exe"
        echo vJoy installer launched. Please complete installation, then run this script again.
    ) else (
        echo Download vJoy from: https://sourceforge.net/projects/vjoystick/
        echo Or use the vJoy Setup button in the ForzaWheel Server app.
    )
    pause
    exit /b 0
) else (
    echo [OK] vJoy driver is installed.
)

echo.
echo ============================================================
echo  Setup complete! Starting ForzaWheel Server...
echo ============================================================
echo.
python ServerApp.py
