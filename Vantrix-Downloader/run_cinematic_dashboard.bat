@echo off
title Vantrix-Downloader — Windows Dedicated Edition
cd /d "%~dp0"
chcp 65001 >nul

echo ======================================================================
echo   ⚡ Vantrix-Downloader — Dedicated Windows Media Suite (Windows 10/11)
echo   4K Ultra HD Video (2160p) & Lossless / Dolby Audio
echo ======================================================================
echo.

:: Check python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH!
    echo Please install Python 3.10+ from python.org and check "Add to PATH".
    pause
    exit /b 1
)

:: Launch the universal cross-platform dashboard runner
python run_cinematic_dashboard.py
if %errorlevel% neq 0 (
    echo.
    echo Application exited.
    pause
)
