@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10 or newer from python.org with the "py launcher" option.
  pause
  exit /b 1
)
py -c "import pygame" >nul 2>nul
if errorlevel 1 (
  echo Installing pygame-ce ^(first run only^)...
  py -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Installing pygame-ce failed. Check the internet connection and try again.
    pause
    exit /b 1
  )
)
if /i "%~1"=="diagnose" (
  py oblivion_controller.py --diagnose
  pause
  exit /b 0
)
py oblivion_controller.py %*
if errorlevel 1 pause
