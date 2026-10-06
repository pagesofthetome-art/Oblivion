{
  Agent_ExportScripts - dump script source (SCTX) of target plugins to text files so an
  agent can read, grep and diff Oblivion scripts without opening the CS.

  Targets: same rules as Agent_PluginAudit (Agent-Reports\audit-targets.txt, else all
  non-official plugins). Put "Oblivion.esm" in the targets file to export vanilla scripts.

  Output: <xEdit folder>\Agent-Reports\scripts\<plugin>__<EditorID>.txt
  (the folder is created by tools\xedit_run.py). Only SCPT records are exported;
  quest-stage and dialogue result scripts live inside QUST/INFO records - read them in xEdit.
  Read-only.
}
unit userscript;

var
  slTargets: TStringList;

function Initialize: integer;
var
  i, j, n: integer;
  f, rec: IInterface;
  dir, src: string;
  sl: TStringList;
begin
  slTargets := TStringList.Create;
  if FileExists(ProgramPath + 'Agent-Reports\audit-targets.txt') then begin
    slTargets.LoadFromFile(ProgramPath + 'Agent-Reports\audit-targets.txt');
    for i := Pred(slTargets.Count) downto 0 do
      if Trim(slTargets[i]) = '' then slTargets.Delete(i)
      else slTargets[i] := LowerCase(Trim(slTargets[i]));
  end;
  sl := TStringList.Create;
  n := 0;
  for i := 0 to Pred(FileCount) do begin
    f := FileByIndex(i);
    if slTargets.Count > 0 then begin
      if slTargets.IndexOf(LowerCase(GetFileName(f))) < 0 then Continue;
    end else if MasterCount(f) = 0 then Continue;
    dir := ProgramPath + 'Agent-Reports\scripts\' + GetFileName(f) + '__';
    for j := 0 to Pred(RecordCount(f)) do begin
      rec := RecordByIndex(f, j);
      if Signature(rec) <> 'SCPT' then Continue;
      src := GetElementEditValues(rec, 'SCTX');
      if src = '' then Continue;
      sl.Text := src;
      sl.SaveToFile(dir + EditorID(rec) + '.txt');
      Inc(n);
    end;
  end;
  AddMessage(Format('Agent_ExportScripts: exported %d scripts to Agent-Reports\scripts', [n]));
  sl.Free;
  slTargets.Free;
  Result := 1;
end;

end.
