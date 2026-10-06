@echo off
rem  TES4Forge Track E acceptance run. Close Oblivion (and the CS) first, then double-click this.
rem  Hands off the keyboard while the game boots: the test types into the game console for ~30 s.
rem  If it says "Run forge playtest make-save once": run  forge playtest make-save  (New Game with the pad), then this again.
rem  acceptance.bat --no-pause   skips the final pause (for scripts).
rem  Everything it prints is saved to forge-builds\playtest\acceptance.txt - send that file back.
setlocal
cd /d "%~dp0..\.."
if not exist forge-builds\playtest mkdir forge-builds\playtest
set "OUT=forge-builds\playtest\acceptance.txt"
set "EX=tools\playtest\examples\example-firebolt.yaml"

echo TES4Forge playtest acceptance %DATE% %TIME%> "%OUT%"
python -c "import numpy, PIL, yaml" 2>nul || (
  echo Installing numpy, Pillow and PyYAML ^(mesh kit + specs^)...
  python -m pip install -r tools\requirements-assetkit.txt -r tools\requirements-forge.txt
)
echo.>> "%OUT%" & echo === hashes BEFORE>> "%OUT%"
call forge.cmd playtest status >> "%OUT%" 2>&1
echo.>> "%OUT%" & echo === 1. dry run: profile on, then off again, no game>> "%OUT%"
call forge.cmd playtest "%EX%" --dry-run >> "%OUT%" 2>&1
echo.>> "%OUT%" & echo === 2. real run: boot into the arena, run the checks, quit>> "%OUT%"
echo Starting the test game. Hands off the keyboard. If it BEEPS, press Cross on CONTINUE.
call forge.cmd playtest "%EX%" --quit >> "%OUT%" 2>&1
echo exit code %ERRORLEVEL% (0 = PASS)>> "%OUT%"
echo.>> "%OUT%" & echo === 3. forge test>> "%OUT%"
call forge.cmd test >> "%OUT%" 2>&1
echo.>> "%OUT%" & echo === hashes AFTER (must equal BEFORE)>> "%OUT%"
call forge.cmd playtest status >> "%OUT%" 2>&1
type "%OUT%"
echo.
echo Saved to %OUT%
if /i not "%~1"=="--no-pause" pause
