{
  Agent_CreateRecordsFromAssets - turn assetkit builds into plugin records.

  Input: <xEdit folder>\Agent-Reports\asset-records.txt  (written by
         python -m assetkit.build records <build dirs...> --plugin MyMod.esp)
  One line per record, '|' separated:
    TargetPlugin|Signature|NewEditorID|Name|TemplateEditorID|MODL|ICON|MODB
  For each line the script copies the WINNING override of the template record as a NEW record
  into TargetPlugin (created if not loaded), then sets EDID, FULL, Model\MODL, Model\MODB, ICON
  and removes the stale Model\MODT texture hashes. Stats stay those of the template - adjust them
  afterwards (balance against the template).

  Run it in the TES4Edit GUI with the user watching (it modifies a plugin; xEdit asks to save on
  exit). Load Oblivion.esm + the target plugin (if it exists). Apply it to any record.
}
unit userscript;

function FindWinningByEditorID(sig, edid: string): IInterface;
var
  i: integer;
  g, r: IInterface;
begin
  Result := nil;
  for i := Pred(FileCount) downto 0 do begin
    g := GroupBySignature(FileByIndex(i), sig);
    if not Assigned(g) then Continue;
    r := MainRecordByEditorID(g, edid);
    if Assigned(r) then begin
      Result := WinningOverride(r);
      Exit;
    end;
  end;
end;

function FindFile(name: string): IInterface;
var
  i: integer;
begin
  Result := nil;
  for i := 0 to Pred(FileCount) do
    if SameText(GetFileName(FileByIndex(i)), name) then begin
      Result := FileByIndex(i);
      Exit;
    end;
end;

function Initialize: integer;
var
  sl, parts: TStringList;
  i, made: integer;
  target, tmpl, r, g: IInterface;
  fn: string;
begin
  Result := 1;
  fn := ProgramPath + 'Agent-Reports\asset-records.txt';
  if not FileExists(fn) then begin
    AddMessage('Agent_CreateRecordsFromAssets: ' + fn + ' not found');
    Exit;
  end;
  sl := TStringList.Create;
  parts := TStringList.Create;
  parts.Delimiter := '|';
  parts.StrictDelimiter := True;
  sl.LoadFromFile(fn);
  made := 0;
  for i := 0 to Pred(sl.Count) do begin
    if (Trim(sl[i]) = '') or (Copy(sl[i], 1, 1) = '#') then Continue;
    parts.DelimitedText := sl[i];
    if parts.Count < 8 then begin
      AddMessage('skip malformed line ' + IntToStr(i + 1) + ': ' + sl[i]);
      Continue;
    end;
    target := FindFile(parts[0]);
    if not Assigned(target) then begin
      target := AddNewFileName(parts[0]);
      AddMessage('created new plugin ' + parts[0]);
    end;
    g := GroupBySignature(target, parts[1]);
    if Assigned(g) and Assigned(MainRecordByEditorID(g, parts[2])) then begin
      AddMessage('exists already, skipped: ' + parts[2]);
      Continue;
    end;
    tmpl := FindWinningByEditorID(parts[1], parts[4]);
    if not Assigned(tmpl) then begin
      AddMessage('template not found: ' + parts[1] + ' ' + parts[4]);
      Continue;
    end;
    AddRequiredElementMasters(tmpl, target, False);
    r := wbCopyElementToFile(tmpl, target, True, True);   // True = as NEW record
    SetElementEditValues(r, 'EDID', parts[2]);
    SetElementEditValues(r, 'FULL', parts[3]);
    SetElementEditValues(r, 'Model\MODL', parts[5]);
    if parts[7] <> '' then SetElementEditValues(r, 'Model\MODB', parts[7]);
    if ElementExists(ElementByPath(r, 'Model'), 'MODT') then
      RemoveElement(ElementByPath(r, 'Model'), 'MODT');
    if parts[6] <> '' then SetElementEditValues(r, 'ICON', parts[6]);
    AddMessage(Format('created %s %s "%s" from %s in %s', [parts[1], parts[2], parts[3], parts[4], parts[0]]));
    Inc(made);
  end;
  AddMessage(Format('Agent_CreateRecordsFromAssets: %d record(s) created. Review them, then save the plugin.', [made]));
  sl.Free;
  parts.Free;
end;

end.
