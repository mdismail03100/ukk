@echo off
title YouTube Shorts AI AutoPilot
cd /d "%~dp0"
echo =========================================================
echo       Running YouTube Shorts 100%% Autonomous Bot...
echo =========================================================
py -3.13 -m src.autopilot
if errorlevel 1 (
    echo.
    echo Trying fallback python launcher...
    python -m src.autopilot
)
pause
