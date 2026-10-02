@echo off
title YouTube Shorts AI Studio
cd /d "%~dp0"
echo =========================================================
echo       Starting YouTube Shorts AI Web Studio...
echo =========================================================
echo Opening browser at http://localhost:5050
start http://localhost:5050
py -3.13 studio.py
if errorlevel 1 (
    echo.
    echo Trying fallback python launcher...
    python studio.py
)
pause
