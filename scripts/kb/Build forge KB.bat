@echo off
rem TES4Forge phase 2: build the knowledge store on the PC and run the PC-side KB tests.
rem Usage: "Build forge KB.bat" ["C:\Users\Shadow\Desktop\Games\Oblivion"]
rem Reads the clean GOG copy (<game>\Data, <game>\Oblivion.exe). Writes only to the repo
rem root: vanilla_index.jsonl, vanilla_commands.jsonl, forge-kb.sqlite, kb_log.txt (all git-ignored).
setlocal
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "LOG=%ROOT%\kb_log.txt"
set "PYTHONPATH=%ROOT%\tools;%PYTHONPATH%"
rem Game folder: the first argument, else the first of these that holds Data\Oblivion.esm:
rem   <repo>\Oblivion, <repo>\..\Oblivion, %USERPROFILE%\Desktop\Games\Oblivion
set "GAME=%~1"
if not "%GAME%"=="" goto havegame
for %%G in ("%ROOT%\Oblivion" "%ROOT%\..\Oblivion" "%USERPROFILE%\Desktop\Games\Oblivion") do (
  if not defined GAME if exist "%%~fG\Data\Oblivion.esm" set "GAME=%%~fG"
)
:havegame
if not defined GAME (
  echo Could not find the GOG Oblivion folder. Run:  "Build forge KB.bat" "C:\path\to\Oblivion"
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

echo TES4Forge knowledge store build, %DATE% %TIME% > "%LOG%"
echo Data: %DATA% >> "%LOG%"
echo Exe:  %EXE% >> "%LOG%"

echo.>> "%LOG%" & echo === 1. export-vanilla ===>> "%LOG%"
python -m forge kb export-vanilla --data "%DATA%" --out "%ROOT%\vanilla_index.jsonl" >> "%LOG%" 2>&1
if errorlevel 1 echo export-vanilla FAILED >> "%LOG%"

echo.>> "%LOG%" & echo === 2. export-commands (optional) ===>> "%LOG%"
python -m forge kb export-commands --exe "%EXE%" --out "%ROOT%\vanilla_commands.jsonl" >> "%LOG%" 2>&1
if errorlevel 1 echo export-commands failed: q20 will be skipped, everything else still works >> "%LOG%"

echo.>> "%LOG%" & echo === 3. forge kb build ===>> "%LOG%"
python -m forge kb build >> "%LOG%" 2>&1
if errorlevel 1 echo kb build FAILED >> "%LOG%"

echo.>> "%LOG%" & echo === 4. tests (20 questions + exporters + integrity + ranking regression) ===>> "%LOG%"
pushd "%ROOT%\tools"
python -m unittest forge.tests.test_kb_queries forge.tests.test_kb_export forge.tests.test_kb_ranking_noise -v >> "%LOG%" 2>&1
if errorlevel 1 (echo TESTS FAILED >> "%LOG%") else (echo TESTS OK >> "%LOG%")
popd

type "%LOG%"
echo.
echo Log written to %LOG%. Send it to Claude.
pause
