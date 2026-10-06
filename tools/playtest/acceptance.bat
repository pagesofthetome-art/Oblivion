@echo off
rem  TES4Forge Track E acceptance run. Close Oblivion (and the CS) first, then double-click this.
rem  Forge NEVER closes the game. Each step: forge does its part, BEEPS, and you quit the game with
rem  the pad when you are ready. The next step starts only after the game has closed.
rem    Step 1 (only if there is no test save yet): NEW game, any name, DONE, confirm; forge takes you
rem           to the Arena and saves. Quit when it beeps.
rem    Step 2: the test. At three beeps press Cross on CONTINUE. Play, then quit when it beeps again.
rem  acceptance.bat --no-pause   skips the final pause (for scripts).
rem  Everything it prints is saved to forge-builds\playtest\acceptance.txt - send that file back.
setlocal
cd /d "%~dp0..\.."
if not exist forge-builds\playtest mkdir forge-builds\playtest
set "OUT=forge-builds\playtest\acceptance.txt"
set "EX=tools\playtest\examples\example-firebolt.yaml"

echo TES4Forge playtest acceptance %DATE% %TIME%> "%OUT%"
python -c "import numpy, PIL, yaml" 2>nul || (
  echo Installing numpy, Pillow and PyYAML...
  python -m pip install -r tools\requirements-assetkit.txt -r tools\requirements-forge.txt
)
echo.>> "%OUT%" & echo === hashes BEFORE>> "%OUT%"
call forge.cmd playtest status >> "%OUT%" 2>&1

set "SAVE=%USERPROFILE%\Documents\My Games\Oblivion\Saves\ForgePlaytest\ForgePlaytestBase.ess"
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('MyDocuments')"`) do set "SAVE=%%D\My Games\Oblivion\Saves\ForgePlaytest\ForgePlaytestBase.ess"
if exist "%SAVE%" goto have_save
echo.>> "%OUT%" & echo === 1. make-save: NEW game, any name, DONE; quit when it beeps>> "%OUT%"
echo.
echo  STEP 1: the game opens. With the pad: NEW, skip the intro, type any name, DONE, confirm.
echo          Forge takes you to the Arena and saves. When it BEEPS, quit the game with the pad.
call forge.cmd playtest make-save >> "%OUT%" 2>&1
if errorlevel 1 (
  echo make-save did not make a test save - stopping here. See %OUT%
  echo make-save FAILED - stopped before the test>> "%OUT%"
  goto done
)
:have_save
echo.>> "%OUT%" & echo === 2. dry run: profile on, then off again, no game>> "%OUT%"
call forge.cmd playtest "%EX%" --dry-run >> "%OUT%" 2>&1
echo.>> "%OUT%" & echo === 3. the test: Continue at the beeps, quit when it beeps again>> "%OUT%"
echo.
echo  STEP 2: the game opens. At THREE BEEPS press Cross on CONTINUE. Forge runs the checks;
echo          when it beeps again you can play on, then quit the game with the pad.
call forge.cmd playtest "%EX%" >> "%OUT%" 2>&1
echo exit code %ERRORLEVEL% (0 = PASS)>> "%OUT%"
echo.>> "%OUT%" & echo === 4. forge test>> "%OUT%"
call forge.cmd test >> "%OUT%" 2>&1
:done
echo.>> "%OUT%" & echo === hashes AFTER (must equal BEFORE)>> "%OUT%"
call forge.cmd playtest status >> "%OUT%" 2>&1
type "%OUT%"
echo.
echo Saved to %OUT%
if /i not "%~1"=="--no-pause" pause
