@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.10+ from python.org with the "py launcher" option.
  pause
  exit /b 1
)
py install_northernui.py %*
pause
