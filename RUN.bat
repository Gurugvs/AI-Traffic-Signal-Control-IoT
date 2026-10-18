@echo off
cd /d "%~dp0"
echo Installing Python packages...
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo.
echo Edit iot_controller.py and set ESP32_IP first.
echo Starting application...
py -3 app.py
pause
exit /b 0
:fail
echo Installation failed. Check Python and internet connection.
pause
