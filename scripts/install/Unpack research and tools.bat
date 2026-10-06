@echo off
rem Unpack research mods + tools for Claude. Nothing goes into Vortex or the game folders.
setlocal enabledelayedexpansion
set "DL=%USERPROFILE%\Downloads"
set "TD=%USERPROFILE%\Desktop\Games\Tool Downloads"
set "RX=%USERPROFILE%\Desktop\Games\research-extracts"
set "TX=%USERPROFILE%\Desktop\Games\tools-unpacked"
set "LOG=%USERPROFILE%\Desktop\Games\unpack_log.txt"
echo Started %date% %time% > "%LOG%"

rem 1) 7-Zip (handles rar/7z that Windows tar can't)
set "SZ=%ProgramFiles%\7-Zip\7z.exe"
if not exist "%SZ%" (
  if exist "%TD%\7z2604-x64.exe" (
    echo Installing 7-Zip... approve the Windows prompt if it appears.
    "%TD%\7z2604-x64.exe" /S
  ) else if exist "%DL%\7z2604-x64.exe" (
    "%DL%\7z2604-x64.exe" /S
  )
)
if exist "%SZ%" (echo 7-Zip OK>>"%LOG%") else (echo 7-Zip MISSING - using tar>>"%LOG%")

rem 2) research mods -> research-extracts\<archive name>
if not exist "%RX%" mkdir "%RX%"
for %%A in (
 "ProjectileMagicUpdate3-28948-3-0.zip" "Telekinetic Damage v6-22957.zip" "Supreme Magicka 0.66 Fixed-10791.zip"
 "FearsomeMagicka_0_2_RC -30973.7z" "PJsSpellCompendium-3892.zip" "Dimensional Pocket-1882.zip"
 "Pocket Dimension Player Home for Oblivion-49144-V7-1692676995.zip" "Demiplane House-18419.zip" "Portal v0-2-13673.rar"
 "Madness Portal 1point1-19180.rar" "True Necromancy-56199-0-2-1780729369.zip" "Weather Control Spells-30346.rar"
 "aoms_beta_036-31918.zip" "aoms_changelog_036-31918.zip" "Less Annoying Magic Experience English version-20371-1-8EV-1640005108.7z"
 "Spell Extension with indepented standalone modules ( not compatible with the main file )-51358-3-0-1633443416.rar"
) do call :unpack "%DL%\%%~A" "%RX%\%%~nA"

rem 3) tools -> tools-unpacked (zips only; installers are left alone)
if not exist "%TX%" mkdir "%TX%"
for %%A in ("ffmpeg-release-essentials.zip" "sqlite-tools-win-x64-3530400.zip" "ghidra_12.1.4_PUBLIC_20260921.zip" "io_scene_nifly-V29.1.0.zip") do call :unpack "%TD%\%%~A" "%TX%\%%~nA"
call :unpack "%DL%\Landscape LOD generator 5_15c-40549-5-15.7z" "%TX%\TES4LL 5.15c"
call :unpack "%DL%\TES4Edit 4.1.5f-11536-4-1-5f-1714279194.7z" "%TX%\TES4Edit 4.1.5f"

rem 4) list for Claude
dir /s /b "%RX%\*.esp" "%RX%\*.esm" >> "%LOG%" 2>nul
echo Finished %date% %time% >> "%LOG%"
echo.
echo Done. Tell Claude.
pause
exit /b

:unpack
if not exist "%~1" (echo MISSING %~nx1>>"%LOG%" & exit /b)
if exist "%~2" (echo SKIP already unpacked %~nx1>>"%LOG%" & exit /b)
mkdir "%~2"
if exist "%SZ%" ("%SZ%" x -y -o"%~2" "%~1" >nul) else (tar -xf "%~1" -C "%~2")
if errorlevel 1 (echo ERROR %~nx1>>"%LOG%") else (echo OK %~nx1>>"%LOG%")
exit /b
