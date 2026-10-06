@echo off
rem  One-click start: controller companion + Oblivion through xOBSE (needed for NorthernUI).
rem  Use this instead of the old "The Elder Scrolls IV - Oblivion" shortcuts - they point to
rem  C:\GOG Games\Oblivion, an old location, and the normal launcher never loads xOBSE.
setlocal
set "GAMES=%~dp0"
rem  Works from anywhere (e.g. a copy on the Desktop): fall back to the workspace folder.
if not exist "%GAMES%Controller\oblivion_controller.py" set "GAMES=%USERPROFILE%\Desktop\Games\"
set "GAMEDIR=%GAMES%Oblivion"
rem  Vortex deploys Oblivion Rebirth+ into the Steam copy; the controller program picks that one when it has xOBSE.
for /f "usebackq delims=" %%D in (`py "%GAMES%Controller\oblivion_controller.py" --print-game-dir 2^>nul`) do set "GAMEDIR=%%D"
echo Game folder: %GAMEDIR%

if not exist "%GAMEDIR%\obse_loader.exe" (
  echo xOBSE is missing: "%GAMEDIR%\obse_loader.exe" not found.
  pause
  exit /b 1
)

rem 0a) Steam Input must be OFF for Oblivion - otherwise Steam turns the controller into keyboard/mouse
py "%GAMES%Controller\steam_check.py" --fix
if errorlevel 2 (
  echo.
  pause
  exit /b 1
)
rem 0) borderless-window display so the controller's on-screen keyboard can appear over the game
if exist "%GAMES%Controller\oblivion_controller.py" (
  py "%GAMES%Controller\oblivion_controller.py" --prepare-display
)

rem 1) controller window. Oblivion starts only when you click "Save settings & start Oblivion" in it.
if not exist "%GAMES%Controller\run_oblivion_controller.bat" (
  echo Controller program not found - starting the game directly.
  cd /d "%GAMEDIR%"
  obse_loader.exe
  exit /b 0
)
rem  close any controller program left running from an earlier session (also older versions)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name like 'py%%'\" | Where-Object { $_.CommandLine -like '*oblivion_controller.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>nul
start "Oblivion controller" /min /d "%GAMES%Controller" "%GAMES%Controller\run_oblivion_controller.bat" --launch-game
echo.
echo The controller window is opening. Check your settings there, then click
echo   "Save settings ^& start Oblivion"
echo to launch the game. (Its log: Controller\controller_log.txt)
timeout /t 8 >nul
