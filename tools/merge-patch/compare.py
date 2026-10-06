import json, collections, os
new=json.load(open('new.json')); new.update(json.load(open('rarnew.json'))); inst=json.load(open('installed.json'))
want=['Cobl Main.esm','Cobl Glue.esp','Cobl Si.esp','SettlementsOfCyrodiil.esm','ClearwaterFarms.esp','LegionOutposts.esp','Oranstad.esp','SilverfishFalls.esp','WhiteRoseFarm.esp',
 'Bounty Quests.esp','CountBravil.esp','Choices and Consequences.esp','DBAQ.esp','Daedric Quests Revised.esp','DarkBrotherhoodInfinitum.esp','EBMGMagnified.esp','JoinTheBlackwoodCompany.esp',
 'Kovahn.esp','Mages Guild Quests.esp','MannimarcoComplete.esp','OwnableTavernRedone.esp','TheReturnOfTheDarkBrotherhood.esp','Region Revive - Lake Rumare.esp','ReplayableRandomQuests.esp',
 'TOTF.esp','Tales of Cyrodiil.esp','ThievesGuildInfinitum.esp','Steve - Thieves Guils HQ.esp','MTCThievesGrotto.esp','TimeEnough.esp','Villages1.1.esp','aaachzCastleMystery.esp',
 'AFK_Weye.esp','DBContinuedBeta 0.7.esp','House Valranis.esp','JoinTheMythicDawn.esp','Extended Dialogue.esp']
sel={}
for k,v in new.items():
    if 'err' in v: continue
    n=v['name']
    if n in want and n not in sel:
        if n=='WickmereFarm.esp' and 'Milewood' in k: continue
        if n=='AFK_Weye.esp' and 'Non-COBL' in k: continue
        if n=='SOC-RegionalFarms.esp' and 'Weynon' in k: continue
        sel[n]=v
for k,v in new.items():
    if v.get('name') in ('WickmereFarm.esp','SOC-RegionalFarms.esp') and 'Milewood' not in k and 'Weynon' not in k and v['name'] not in sel: sel[v['name']]=v
print('selected',len(sel), sorted(set(want)-set(sel)))
instd={v['name']:v for v in inst.values()}
def keys(v):
    s={}
    for own,i,sig,e in v['overrides']: s[(own,i)]=(sig,e)
    for own,i,e,c in v['int_cells_ovr']: s[(own,i)]=('CELL',e)
    return s
ik={n:keys(v) for n,v in instd.items()}; nk={n:keys(v) for n,v in sel.items()}
idx=collections.defaultdict(list)
for n,ks in ik.items():
    for k in ks: idx[k].append(n)
nidx=collections.defaultdict(list)
for n,ks in nk.items():
    for k in ks: nidx[k].append(n)
rep={}
for n,ks in nk.items():
    hits=collections.defaultdict(list)
    for k,(sig,e) in ks.items():
        for o in idx.get(k,[]):
            if o in (n,): continue
            hits[o].append(f'{sig}:{e or k[1]}')
        for o in nidx.get(k,[]):
            if o!=n: hits['NEW:'+o].append(f'{sig}:{e or k[1]}')
    rep[n]={o:l for o,l in hits.items()}
json.dump(rep,open('rec_conflicts.json','w'),indent=1)
for n in sorted(rep):
    r=rep[n]
    if not r: print('##',n,': no record overlaps'); continue
    print('##',n)
    for o,l in sorted(r.items(),key=lambda x:-len(x[1]))[:12]:
        sigs=collections.Counter(x.split(':')[0] for x in l)
        print('   ',o,len(l),dict(sigs),'e.g.',l[:4])
