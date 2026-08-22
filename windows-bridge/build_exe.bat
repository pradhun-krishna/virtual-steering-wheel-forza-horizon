@echo off
cd /d "%~dp0"
echo ============================================================
echo  ForzaWheel - Build Standalone EXE
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

echo Installing pyinstaller...
pip install pyinstaller PyQt5 pywin32

echo.
echo Building EXE...
pyinstaller --noconfirm --onedir --windowed --name "ForzaWheelServer" --add-data "ViGEmClient.dll;." "ServerApp.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build Successful!
echo  Your executable is located at: dist\ForzaWheelServer\ForzaWheelServer.exe
echo ============================================================
pause
