@echo off
rem Builds clean Vortex-ready zips of the new mods into Desktop\Games\_audit\vortex_ready (changes nothing in the game)
powershell -NoProfile -ExecutionPolicy Bypass -File "%USERPROFILE%\Desktop\Games\_audit\prepare_new_mods.ps1"
pause
