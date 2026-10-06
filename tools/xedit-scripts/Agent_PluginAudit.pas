{
  Agent_PluginAudit - headless quality audit of one or more plugins for AI agents.

  Targets: plugin names listed one per line in <xEdit folder>\Agent-Reports\audit-targets.txt.
  If that file is missing or empty, every loaded plugin that is not an official
  Bethesda file is audited.

  For each target it reports:
    ITM      override identical to its master (ConflictThis = IdenticalToMaster)
    UDR      deleted placed reference (REFR/ACHR/ACRE) - CTD risk
    DELETED  deleted non-reference record that a master defines - CTD risk
    LOSES    this plugin's edit is overridden by a later plugin (ConflictThis = ConflictLoses)
    ERROR    xEdit "Check for errors" result (unresolved FormIDs, bad data, etc.)

  Run headless:
    TES4Edit.exe -TES4 -IKnowWhatImDoing -autoload -autoexit -script:"Agent_PluginAudit.pas"
  Output: <xEdit folder>\Agent-Reports\audit.tsv  (kind, plugin, signature, formid, editor_id, detail)
  Read-only: never changes or saves any plugin.
}
unit userscript;

var
  slOut, slTargets: TStringList;
  CountErr: integer;

function IsOfficial(s: string): boolean;
begin
  s := LowerCase(s);
  Result := (s = 'oblivion.esm') or (s = 'oblivion.exe') or (s = 'dlcshiveringisles.esp') or (s = 'knights.esp') or
    (s = 'dlchorsearmor.esp') or (s = 'dlcmehrunesrazor.esp') or (s = 'dlcvilelair.esp') or
    (s = 'dlcfrostcrag.esp') or (s = 'dlcbattlehorncastle.esp') or (s = 'dlcspelltomes.esp') or
    (s = 'dlcthievesden.esp') or (s = 'dlcorrery.esp');
end;

procedure Emit(kind: string; rec: IInterface; detail: string);
begin
  slOut.Add(kind + #9 + GetFileName(GetFile(rec)) + #9 + Signature(rec) + #9 +
            IntToHex(GetLoadOrderFormID(rec), 8) + #9 + EditorID(rec) + #9 + detail);
end;

procedure CheckErrors(root, e: IInterface; depth: integer);
var
  s: string;
  i: integer;
begin
  if CountErr > 5000 then Exit;
  s := Check(e);
  if s <> '' then begin
    Inc(CountErr);
    Emit('ERROR', root, Path(e) + ' -> ' + s);
  end;
  if depth > 12 then Exit;
  for i := 0 to Pred(ElementCount(e)) do
    CheckErrors(root, ElementByIndex(e, i), depth + 1);
end;

procedure AuditRecord(rec: IInterface);
var
  sig: string;
  ct: integer;
begin
  sig := Signature(rec);
  if sig = 'TES4' then Exit;
  if GetIsDeleted(rec) then begin
    if (sig = 'REFR') or (sig = 'ACHR') or (sig = 'ACRE') then
      Emit('UDR', rec, 'deleted reference - undelete and disable it (QAC does this)')
    else if not IsMaster(rec) then
      Emit('DELETED', rec, 'deletes a master record - anything referencing it may CTD');
    Exit;
  end;
  if not IsMaster(rec) then begin
    ct := ConflictThisForMainRecord(rec);
    if ct = ctIdenticalToMaster then
      Emit('ITM', rec, 'identical to master - remove (QAC)')
    else if ct = ctConflictLoses then
      Emit('LOSES', rec, 'overridden by ' + GetFileName(GetFile(WinningOverride(rec))));
  end;
  CheckErrors(rec, rec, 0);
end;

function Wanted(f: IInterface): boolean;
var
  n: string;
begin
  n := GetFileName(f);
  if slTargets.Count > 0 then
    Result := slTargets.IndexOf(LowerCase(n)) >= 0
  else
    Result := (MasterCount(f) > 0) and not IsOfficial(n);
end;

function Initialize: integer;
var
  i, j: integer;
  f: IInterface;
  tf: string;
begin
  slOut := TStringList.Create;
  slTargets := TStringList.Create;
  tf := ProgramPath + 'Agent-Reports\audit-targets.txt';
  if FileExists(tf) then begin
    slTargets.LoadFromFile(tf);
    for i := Pred(slTargets.Count) downto 0 do
      if Trim(slTargets[i]) = '' then slTargets.Delete(i)
      else slTargets[i] := LowerCase(Trim(slTargets[i]));
  end;
  slOut.Add('kind'#9'plugin'#9'signature'#9'loadorder_formid'#9'editor_id'#9'detail');
  for i := 0 to Pred(FileCount) do begin
    f := FileByIndex(i);
    if not Wanted(f) then Continue;
    AddMessage('Agent_PluginAudit: auditing ' + GetFileName(f));
    for j := 0 to Pred(RecordCount(f)) do
      AuditRecord(RecordByIndex(f, j));
  end;
  slOut.SaveToFile(ProgramPath + 'Agent-Reports\audit.tsv');
  AddMessage(Format('Agent_PluginAudit: %d findings saved to Agent-Reports\audit.tsv', [slOut.Count - 1]));
  slOut.Free;
  slTargets.Free;
  Result := 1;
end;

end.
