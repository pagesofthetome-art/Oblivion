{
  Agent_ConflictReport - headless conflict report for AI agents.

  Lists every record that two or more loaded plugins override, with xEdit's own
  conflict status (the authoritative check, field-aware, FormID-aware).

  Run headless (from tools\xedit_run.py, or directly):
    TES4Edit.exe -TES4 -IKnowWhatImDoing -autoload -autoexit -script:"Agent_ConflictReport.pas"

  Output: <xEdit folder>\Agent-Reports\conflicts.tsv  (tab separated, UTF-8 not guaranteed)
  Columns: status, signature, loadorder_formid, editor_id, origin, override_chain, winner, note
  Read-only: never changes or saves any plugin.
}
unit userscript;

var
  slOut: TStringList;
  CountTotal, CountRed: integer;

function StatusName(c: integer): string;
begin
  Result := 'Unknown';
  if c = caOnlyOne then Result := 'OnlyOne'
  else if c = caNoConflict then Result := 'NoConflict'
  else if c = caConflictBenign then Result := 'ConflictBenign'
  else if c = caOverride then Result := 'Override'
  else if c = caConflict then Result := 'Conflict'
  else if c = caConflictCritical then Result := 'ConflictCritical';
end;

procedure HandleRecord(rec: IInterface);
var
  m, ovr, win: IInterface;
  i, c: integer;
  chain, note: string;
begin
  if IsMaster(rec) then Exit;
  m := MasterOrSelf(rec);
  if OverrideCount(m) < 2 then Exit;
  win := WinningOverride(m);
  // report each overridden record once: when we are visiting its winning override
  if not Equals(rec, win) then Exit;

  c := ConflictAllForMainRecord(m);
  Inc(CountTotal);
  if c < caConflict then Exit;
  Inc(CountRed);

  chain := '';
  note := '';
  for i := 0 to Pred(OverrideCount(m)) do begin
    ovr := OverrideByIndex(m, i);
    if chain <> '' then chain := chain + ' > ';
    chain := chain + GetFileName(GetFile(ovr));
    if GetIsDeleted(ovr) and (i < Pred(OverrideCount(m))) then
      note := note + 'DELETED in ' + GetFileName(GetFile(ovr)) + ' but overridden later (CTD risk); ';
  end;
  if GetIsDeleted(win) then
    note := note + 'winning override DELETES the record; ';

  slOut.Add(StatusName(c) + #9 + Signature(m) + #9 + IntToHex(GetLoadOrderFormID(m), 8) + #9 +
            EditorID(m) + #9 + GetFileName(GetFile(m)) + #9 + chain + #9 +
            GetFileName(GetFile(win)) + #9 + note);
end;

function Initialize: integer;
var
  i, j: integer;
  f: IInterface;
begin
  slOut := TStringList.Create;
  slOut.Add('status'#9'signature'#9'loadorder_formid'#9'editor_id'#9'origin'#9'override_chain'#9'winner'#9'note');
  for i := 0 to Pred(FileCount) do begin
    f := FileByIndex(i);
    // the game master and the hardcoded Oblivion.exe pseudo-file contain no overrides
    if MasterCount(f) = 0 then Continue;
    AddMessage('Agent_ConflictReport: scanning ' + GetFileName(f));
    for j := 0 to Pred(RecordCount(f)) do
      HandleRecord(RecordByIndex(f, j));
  end;
  slOut.SaveToFile(ProgramPath + 'Agent-Reports\conflicts.tsv');
  AddMessage(Format('Agent_ConflictReport: %d multi-override records, %d real conflicts (Conflict/ConflictCritical). Saved Agent-Reports\conflicts.tsv',
    [CountTotal, CountRed]));
  slOut.Free;
  Result := 1; // done; skip Process
end;

end.
