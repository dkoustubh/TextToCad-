@echo off
TITLE Autodesk Inventor Workstation Agent (Port 8001)
COLOR 0A

echo ======================================================================
echo           Autodesk Inventor AI Workstation Agent (Port 8001)
echo ======================================================================
echo  Connecting to: Autodesk Inventor (Active Session)
echo  Listening on:  http://0.0.0.0:8001
echo ======================================================================
echo.

:: Check for Python
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python was not found in PATH!
    echo Please install Python 3.10+ and check "Add Python to PATH".
    pause
    exit /b 1
)

:: Install dependencies if needed
echo [INFO] Ensuring required Python libraries are installed...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet fastapi "uvicorn[standard]" pydantic pywin32 requests

:: Launch the Agent
echo.
echo [INFO] Starting Autodesk Inventor Agent on port 8001...
echo Leave this window open while using the Text-to-CAD Workbench.
echo.
python inventor_agent.py

pause
