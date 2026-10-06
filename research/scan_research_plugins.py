import sys,os,re,json,collections
sys.path.insert(0,'/home/claude/Games/tools')
import tes4_plugin as tp
R='/home/claude/research/x'
KEY=r'\b(GetProjectile\w*|SetProjectile\w*|GetMagicProjectile\w*|SetMagicProjectile\w*|GetVelocity|SetVelocity|PushActorAway|SetRigidBodyMass|GetRigidBodyMass|PlaceAtMe|MoveTo|MoveToMarker|PositionCell|PositionWorld|SetPos|GetPos|SetAngle|ForceWeather|SetWeather|SetCurrentWeather\w*|GetCurrentWeather\w*|SetWeatherTransition|ResurrectActor|Resurrect|KillActor|Kill|CreateFullActorCopy|DeleteFullActorCopy|CloneForm|SetModelPath|SetRefEssential|SetGhost|SetRestrained|SetUnconscious|SetAlert|StopCombat|StartCombat|SetActorsAI|SetTimeScale|GetGameHour|SetGameHour|GetFirstRef|GetNextRef|GetNumRefs|GetSpellEffectiveness|AddSpell|Cast|SetMagicEffect\w*|ModMagicEffect\w*|SetSpellMagickaCost|AddEffectItem\w*|SetNthEffectItem\w*|Activate|Disable|Enable|PlayMagicShaderVisuals|PMS|SetSkyrimSky|ToggleSky|SetTelekinesis\w*|IsKeyPressed\w*|OnKeyDown|GetCrosshairRef|GetCombatTarget|SetActorValue|ModActorValue|SetScale|ScaleNode|SetCellWaterHeight|SetFog\w*|RunBatchScript|Con_\w+|SetPlayerProjectile|GetParentCell|GetParentWorldspace|SetHasTurnedPage)\b'
out={}
for dp,dn,fn in os.walk(R):
  for f in fn:
    if not f.lower().endswith(('.esp','.esm')) or '/Sound/' in dp: continue
    p=os.path.join(dp,f)
    try: h=tp.read_header(p)
    except Exception as e: print('ERR',p,e); continue
    cnt=collections.Counter(); scripts=[]; funcs=collections.Counter(); edids=collections.defaultdict(list)
    for pl,r in tp.iter_records(p):
        cnt[r.sig]+=1
        e=r.first('EDID'); e=e.rstrip(b'\0').decode('cp1252','replace') if e else ''
        if r.sig in('SPEL','MGEF','WTHR','PROJ','CREA','WRLD','QUST','ACTI','DOOR') and e: edids[r.sig].append(e)
        if r.sig=='SCPT':
            t=r.first('SCTX'); t=t.decode('cp1252','replace') if t else ''
            scripts.append((e,len(t)))
            for m in re.findall(KEY,t,re.I): funcs[m.lower()]+=1
    mast=h.masters
    rel=os.path.relpath(p,R)
    cnam=getattr(h,'author',None)
    out[rel]=dict(masters=mast,counts=dict(cnt),scripts=len(scripts),biggest=sorted(scripts,key=lambda x:-x[1])[:6],funcs=funcs.most_common(25),edids={k:v[:8] for k,v in edids.items()})
json.dump(out,open('/home/claude/research/scan.json','w'),indent=1)
for k,v in out.items():
  print('\n##',k); print(' masters',v['masters']); print(' counts',{a:b for a,b in v['counts'].items() if a not in('GRUP',)})
  print(' scripts',v['scripts'],'biggest',v['biggest']); print(' funcs',v['funcs']); print(' edids',v['edids'])
