@echo off
rem TES4Forge script compiler, step S0+S1: export the vanilla script corpus and survey the decompiler.
rem Usage: "Export script corpus.bat" ["C:\Users\Shadow\Desktop\Games\Oblivion"]
rem Reads the clean GOG copy (<game>\Data, <game>\Oblivion.exe), read-only. Writes only to the repo
rem root: vanilla_commands.jsonl, forge-script-corpus.jsonl.gz, script_log.txt (all git-ignored,
rem Bethesda-derived: never commit them).
setlocal
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "LOG=%ROOT%\script_log.txt"
set "PYTHONPATH=%ROOT%\tools;%PYTHONPATH%"
set "GAME=%~1"
if not "%GAME%"=="" goto havegame
for %%G in ("%ROOT%\Oblivion" "%ROOT%\..\Oblivion" "%USERPROFILE%\Desktop\Games\Oblivion") do (
  if not defined GAME if exist "%%~fG\Data\Oblivion.esm" set "GAME=%%~fG"
)
:havegame
if not defined GAME (
  echo Could not find the GOG Oblivion folder. Run:  "Export script corpus.bat" "C:\path\to\Oblivion"
  pause
  exit /b 1
)
if not exist "%GAME%\Data\Oblivion.esm" (
  echo "%GAME%\Data\Oblivion.esm" not found. Pass the Oblivion game folder as the first argument.
  pause
  exit /b 1
)
set "DATA=%GAME%\Data"
set "EXE=%GAME%\Oblivion.exe"

echo TES4Forge script corpus export, %DATE% %TIME% > "%LOG%"
echo Data: %DATA% >> "%LOG%"
echo Exe:  %EXE% >> "%LOG%"
git log --oneline -1 >> "%LOG%" 2>&1

echo.>> "%LOG%" & echo === 1. export-commands (script, console and block-type tables) ===>> "%LOG%"
python -m forge kb export-commands --exe "%EXE%" --out "%ROOT%\vanilla_commands.jsonl" >> "%LOG%" 2>&1
if errorlevel 1 echo export-commands FAILED >> "%LOG%"

echo.>> "%LOG%" & echo === 2. export-scripts ===>> "%LOG%"
python -m forge kb export-scripts --data "%DATA%" --exe "%EXE%" --out "%ROOT%\forge-script-corpus.jsonl.gz" >> "%LOG%" 2>&1
if errorlevel 1 echo export-scripts FAILED >> "%LOG%"
for %%F in ("%ROOT%\forge-script-corpus.jsonl.gz") do echo corpus size: %%~zF bytes >> "%LOG%"

echo.>> "%LOG%" & echo === 3. script-decode survey (S1 gate: 100%%) ===>> "%LOG%"
python -m forge script-decode "%ROOT%\forge-script-corpus.jsonl.gz" --fail 5 >> "%LOG%" 2>&1
echo exit code %ERRORLEVEL% >> "%LOG%"

echo.>> "%LOG%" & echo === 4. unit tests ===>> "%LOG%"
python -m unittest discover -s "%ROOT%\tools\forge\tests" -t "%ROOT%\tools" >> "%LOG%" 2>&1

echo Done. Log: %LOG%
endlocal
