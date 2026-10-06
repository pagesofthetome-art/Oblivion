@echo off
rem  Verifies Steam, XInput and every button before you play. Writes controller_audit.txt
cd /d "%~dp0"
py input_audit.py
pause
