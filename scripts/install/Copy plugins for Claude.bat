@echo off
rem Copies the game's plugins (.esp/.esm) so Claude can read them. Changes nothing in the game.
set "OUT=%USERPROFILE%\Desktop\Games\_audit\installed_plugins"
set "DATA=C:\Program Files (x86)\Steam\steamapps\common\Oblivion\Data"
if not exist "%OUT%" mkdir "%OUT%"
for %%F in ("%DATA%\*.esp" "%DATA%\*.esm") do (
  if /I not "%%~nxF"=="Oblivion.esm" copy /Y "%%~fF" "%OUT%\" >nul
)
dir /b "%OUT%" > "%USERPROFILE%\Desktop\Games\_audit\done.txt"
echo Done.
