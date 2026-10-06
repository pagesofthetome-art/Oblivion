@echo off
rem TES4Forge launcher: forge <command> ...   (see tools\forge\README.md)
setlocal
set "PYTHONPATH=%~dp0tools;%PYTHONPATH%"
python -m forge %*
exit /b %ERRORLEVEL%
