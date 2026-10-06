@echo off
rem  Makes plain copies that Claude can read for the mod audit. Changes nothing in the game.
rem  1) copies every installed plugin (.esp/.esm) - the game's copies are Vortex hardlinks Claude can't read
rem  2) unpacks the new .rar mods from Downloads with Windows' built-in tar
setlocal
set "OUT=%USERPROFILE%\Desktop\Games\_audit"
set "DATA=C:\Program Files (x86)\Steam\steamapps\common\Oblivion\Data"
set "DL=%USERPROFILE%\Downloads"
if not exist "%OUT%\installed_plugins" mkdir "%OUT%\installed_plugins"
if not exist "%OUT%\rar" mkdir "%OUT%\rar"
echo Copying installed plugins...
for %%F in ("%DATA%\*.esp" "%DATA%\*.esm") do (
  if /I not "%%~nxF"=="Oblivion.esm" copy /Y "%%~fF" "%OUT%\installed_plugins\" >nul
)
echo Unpacking new .rar mods...
for %%R in ("AFK_Weye Version 2_32-22828-2-32" "Dark Brotherhood- Continued beta-25689" "House Valranis 1_06-40496-1-06" "JoinTheMythicDawn - Main-55756-1-4-1777679206" "Elsweyr Anequina-25023-March-2014-1561735850" "Star's Extended Dialogue 54198 1.1 2026-08-15T06-21Z Jx9MEGCm") do (
  if not exist "%OUT%\rar\%%~R" mkdir "%OUT%\rar\%%~R"
  tar -xf "%DL%\%%~R.rar" -C "%OUT%\rar\%%~R" 2>>"%OUT%\rar_errors.txt"
)
dir /b "%OUT%\installed_plugins" > "%OUT%\done.txt"
echo.
echo Done. You can close this window and tell Claude.
pause
