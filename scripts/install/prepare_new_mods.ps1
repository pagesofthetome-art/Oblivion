# Builds clean, Vortex-ready .zip files for the new Oblivion mods (picked and audited by Claude).
# Reads the archives in Downloads, keeps only the chosen files, and writes the zips to
#   Desktop\Games\_audit\vortex_ready
# Nothing in the game or in Vortex is changed by this script.
$ErrorActionPreference = 'Continue'
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$DL    = Join-Path $env:USERPROFILE 'Downloads'
$AUD   = Join-Path $env:USERPROFILE 'Desktop\Games\_audit'
$WORK  = Join-Path $AUD 'work'
$OUT   = Join-Path $AUD 'vortex_ready'
$RAR   = Join-Path $AUD 'rar'
$LOG   = Join-Path $AUD 'prepare_log.txt'
$INSP  = Join-Path $AUD 'inspect'
New-Item -ItemType Directory -Force -Path $WORK, $OUT, $INSP | Out-Null
# 7-Zip (Vortex ships one) handles RAR files that Windows tar fails on (Elsweyr CRC error)
$SEVENZ = $null
foreach ($root in @("$env:ProgramFiles\7-Zip", "${env:ProgramFiles(x86)}\7-Zip", "$env:ProgramFiles\Black Tree Gaming Ltd\Vortex", "$env:LOCALAPPDATA\Programs\vortex")) {
  if (-not $SEVENZ -and (Test-Path $root)) {
    $f = Get-ChildItem -LiteralPath $root -Recurse -Filter 7z.exe -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch 'ia32|\\x86\\' } | Select-Object -First 1
    if (-not $f) { $f = Get-ChildItem -LiteralPath $root -Recurse -Filter 7z.exe -ErrorAction SilentlyContinue | Select-Object -First 1 }
    if ($f) { $SEVENZ = $f.FullName }
  }
}
"Started $(Get-Date)" | Out-File $LOG -Encoding utf8
# remove the 1 GB scratch copies from the inspection run
Get-ChildItem -LiteralPath $WORK -Directory -Filter 'INSPECT *' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
"7-Zip: $SEVENZ" | Out-File $LOG -Append

# name | source (archive in Downloads, or 'rar:<folder>' already unpacked) | paths to take (';'-separated, relative) | files to leave out (';')
$mods = @(
 @('Cobl 1.74 (core)',                   'Cobl-21104-174-1598559328.7z',                         '00 Cobl Core;01 StableCore',                    'Cobl Filter Late MERGE ONLY.esp'),
 @('Settlements of Cyrodiil - Meshes',  'Settlements of Cyrodiil Meshes.7z',                    'Settlements of Cyrodiil Meshes',                ''),
 @('Settlements of Cyrodiil - Textures 1','Settlements of Cyrodiil Textures 1.7z',              'Settlements of Cyrodiil Textures 1',            ''),
 @('Settlements of Cyrodiil - Textures 2','Settlements of Cyrodiil Textures 2.7z',              'Settlements of Cyrodiil Textures 2',            ''),
 @('SOC Clearwater Farms',              'SOC-Clearwater Farms v1.0.7z',                         'SOC-Clearwater Farms v1.0',                     ''),
 @('SOC Legion Outposts',               'SOC-Legion Outposts.7z',                               'SOC-Legion Outposts',                           ''),
 @('SOC Oranstad Township',             'SOC-Oranstad Township.7z',                             'SOC-Oranstad Township',                         ''),
 @('SOC Regional Farms and Inns',       'SOC-Regional Farms and Inns.7z',                       'SOC-Regional Farms and Inns',                   ''),
 @('SOC Silverfish Falls',              'SOC-Silverfish Falls.7z',                              'SOC-Silverfish Falls',                          ''),
 @('SOC White Rose Farm',               'SOC-White Rose Farm.7z',                               'SOC-White Rose Farm',                           ''),
 @('SOC Wickmere Farm',                 'SOC-Wickmere Farm.7z',                                 'SOC-Wickmere Farm',                             ''),
 @('Bounty Quests 3.0',                 'Bounty Quests Version 3.0 Installation Files-48330-3-0-1701382589.7z', 'Data',                    'Bounty Quests OOO Patch.esp;Bounty Quests OOO.ini'),
 @('Count Bravil 1.5.4',                'BravilCount -fixes minor bugs and the honorblade has been fixed-42454-1-5-4.7z', '.',            ''),
 @('Choices and Consequences 2.0',      'Choices and Consequences Updated 2_0-14560.7z',        '00 Main',                                       ''),
 @('Dark Brotherhood Additional Quests 1.4','DBAQ1dot4-23407-1-4.7z',                           'DBAQ',                                          'DBAQ_easy.esp'),
 @('Daedric Quests Revised 2.2',        'Daedric Quests Revised V2_2-52830-2-2-1752685627.7z',  '.',                                             'Daedric Quests Revised - no UOP.esp'),
 @('Dark Brotherhood Infinitum 3.0',    'Dark Brotherhood - Infinitum-56178-3-0-1780299226.zip','Data',                                          ''),
 @('EBMG Magnified 2.0',                'EBMGMagnified-50158-2-0-1741575410.7z',                '.',                                             ''),
 @('Join the Blackwood Company 1.3',    'JoinTheBlackwoodCompany - Main-55285-1-3-1773082552.zip','Data',                                       ''),
 @('Kovahn 1.1',                        'Kovahn-50132-1-1-1755512901.zip',                      '.',                                             ''),
 @('Mages Guild Quests 1.9',            'Mages Guild Quests 1_9-39591-1-9.7z',                  'Mages Guild Quests 1_9\Data',                   ''),
 @('Mannimarco Resurrection 2.5',       'Mannimarco Resurrection 2_5-15251.7z',                 'MannimarcoResurrection',                        ''),
 @('Ownable Tavern Redone 1.1',         'Ownable Tavern Redone-49359-1-1-1558639937.zip',       '.',                                             ''),
 @('Return of the Dark Brotherhood 1.0','ROTDB v1-0-40761-1.7z',                                'ROTDB v1.0',                                    ''),
 @('Region Revive - Lake Rumare 1.6.3', 'Region Revive - Lake Rumare Updated-48347-1-6-3-1692974128.7z', '.',                            ''),
 @('Repeatable Oblivion Quests 3.521',  'Repeatable Oblivion Quests 51245 3.521 2026-08-24T15-29Z 5VtB7ref.zip', 'Repeatable Oblivion quests', ''),
 @('Tears of the Fiend 1.22',           'TOTF_1_2_2-11598.7z',                                  'Data',                                          ''),
 @('Tales of Cyrodiil 1.04',            'Tales of Cyrodiil 1.04-48792-1-04-1572831613.zip',     '.',                                             ''),
 @('Thieves Guild Infinitum 3.02',      'Thieves Guild - Infinitum v3.02-56187-3-02-1780432044.zip', 'Data',                                     ''),
 @('Thieves Guild HQ - Unhealthy Competition','Thieves Guild HQ - Unhealthy Competition-34465.7z', '.',                                         ''),
 @('Time Enough At Last 1.1',           'Time Enough At Last-47159-1-1-1556324667.zip',         'Time Enough At Last 1_1',                       ''),
 @('Villages 1.1e',                     'Villages v1.1e-36522-1-1e-1692468616.7z',              '.',                                             ''),
 @('Wintermist 1.2',                    'Wintermist-50443-1-2-1659114076.zip',                  '.',                                             ''),
 @('AFK Weye 2.32 (Cobl)',              'rar:AFK_Weye Version 2_32-22828-2-32',                 '00 Core;01 COBL;02 Compatibility\Rumare-AFK_Weye Patch.esp;02 Compatibility\Rumare-AFK_Weye Patch.txt', ''),
 @('House Valranis 1.06',               'rar:House Valranis 1_06-40496-1-06',                   '.',                                             ''),
 @('Join the Mythic Dawn 1.4',          'rar:JoinTheMythicDawn - Main-55756-1-4-1777679206',    'Data',                                          ''),
 @("Star's Extended Dialogue 1.1",      "rar:Star's Extended Dialogue 54198 1.1 2026-08-15T06-21Z Jx9MEGCm", '.',                               ''),
 @('MTC Thieves Grotto V3',             'ThievesGrottoV3-22197.zip',                            'MTCThievesGrottoV3\Data',                       ''),
 @('OCO Elsweyr patch 1.0.2',           'OCO Elsweyr Deserts of Anequina patch-46057-1-0-2-1595399773.rar', 'OCO Elseweyr Patch\data',               '')
)

foreach ($m in $mods) {
  $name, $src, $paths, $skip = $m
  $zip = Join-Path $OUT ($name + '.zip')
  if (Test-Path $zip) { "SKIP (already built) $name" | Out-File $LOG -Append; continue }
  Write-Host "Preparing $name ..."
  if ($src.StartsWith('rar:')) {
    $root = Join-Path $RAR $src.Substring(4)
  } else {
    $root = Join-Path $WORK $name
    if (Test-Path $root) { Remove-Item $root -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $root | Out-Null
    $arch = Join-Path $DL $src
    if (-not (Test-Path $arch)) { "MISSING archive $src" | Out-File $LOG -Append; continue }
    if ($SEVENZ -and ($arch -match '\.(rar|7z)$')) {
      & $SEVENZ x -y "-o$root" $arch | Out-Null
      if ($LASTEXITCODE -ne 0) { "7Z-ERROR $LASTEXITCODE $name" | Out-File $LOG -Append }
    } else {
      & tar.exe -xf $arch -C $root 2>> $LOG
      if ($LASTEXITCODE -ne 0) { "TAR-ERROR $LASTEXITCODE $name" | Out-File $LOG -Append }
    }
  }
  if ($name.StartsWith('INSPECT ')) {
    $dst = Join-Path $INSP $name.Substring(8)
    New-Item -ItemType Directory -Force -Path $dst | Out-Null
    Get-ChildItem -LiteralPath $root -Recurse -File | ForEach-Object { "{0}`t{1}" -f $_.FullName.Substring($root.Length+1), $_.Length } | Out-File (Join-Path $dst 'files.txt') -Encoding utf8
    Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object { $_.Extension -match '^\.(esp|esm|txt|ini|xml|rtf|htm|html)$' } | ForEach-Object {
      $rel = $_.FullName.Substring($root.Length+1); $t = Join-Path $dst $rel
      New-Item -ItemType Directory -Force -Path (Split-Path $t) | Out-Null; Copy-Item -LiteralPath $_.FullName -Destination $t -Force }
    "INSPECT copied $name" | Out-File $LOG -Append
    continue
  }
  $pkg = Join-Path $WORK ('pkg_' + $name)
  if (Test-Path $pkg) { Remove-Item $pkg -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $pkg | Out-Null
  foreach ($p in $paths.Split(';')) {
    $sp = if ($p -eq '.') { $root } else { Join-Path $root $p }
    if (-not (Test-Path -LiteralPath $sp)) { "MISSING path '$p' in $name" | Out-File $LOG -Append; continue }
    if ((Get-Item -LiteralPath $sp).PSIsContainer) {
      Get-ChildItem -LiteralPath $sp -Force | Copy-Item -Destination $pkg -Recurse -Force
    } else {
      Copy-Item -LiteralPath $sp -Destination $pkg -Force
    }
  }
  foreach ($s in $skip.Split(';')) { if ($s) { Get-ChildItem -LiteralPath $pkg -Recurse -Force -Filter $s | Remove-Item -Force -Recurse } }
  $items = @(Get-ChildItem -LiteralPath $pkg -Force | ForEach-Object { $_.Name })
  & tar.exe -a -cf $zip -C $pkg @items 2>> $LOG
  $n = (Get-ChildItem -LiteralPath $pkg -Recurse -File).Count
  $mb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
  "OK $name : $n files, $mb MB, top: $($items -join ', ')" | Out-File $LOG -Append
  Remove-Item $pkg -Recurse -Force
  if (-not $src.StartsWith('rar:')) { Remove-Item $root -Recurse -Force }
}
"Finished $(Get-Date)" | Out-File $LOG -Append
Write-Host ''
Write-Host 'Done. Tell Claude.'
