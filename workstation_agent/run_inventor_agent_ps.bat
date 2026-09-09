@echo off
TITLE Autodesk Inventor AI Workstation Agent (Port 8001)
COLOR 0B

echo ======================================================================
echo           Autodesk Inventor AI Workstation Agent (Port 8001)
echo ======================================================================
echo  Engine:        Native Windows PowerShell + .NET HttpListener
echo  Inventor COM:  Inventor.Application (Active Session)
echo  Listening on:  http://0.0.0.0:8001/
echo ======================================================================
echo.
echo Launching Workstation Agent (Zero dependencies required)...
echo Leave this window open while using the Text-to-CAD Workbench.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0inventor_agent.ps1" -Port 8001

pause
