@echo off
rem TES4Forge phase 2: build the knowledge store on the PC and run the PC-side KB tests.
rem Reads the clean GOG copy (Oblivion\Data, Oblivion\Oblivion.exe). Writes only to the repo
rem root: vanilla_index.jsonl, vanilla_commands.jsonl, forge-kb.sqlite, kb_log.txt (all git-ignored).
setlocal
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "LOG=%ROOT%\kb_log.txt"
set "PYTHONPATH=%ROOT%\tools;%PYTHONPATH%"
set "DATA=%ROOT%\Oblivion\Data"
set "EXE=%ROOT%\Oblivion\Oblivion.exe"

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

echo.>> "%LOG%" & echo === 4. tests (20 questions + exporters + integrity) ===>> "%LOG%"
pushd "%ROOT%\tools"
python -m unittest forge.tests.test_kb_queries forge.tests.test_kb_export -v >> "%LOG%" 2>&1
if errorlevel 1 (echo TESTS FAILED >> "%LOG%") else (echo TESTS OK >> "%LOG%")
popd

type "%LOG%"
echo.
echo Log written to %LOG%. Send it to Claude.
pause
