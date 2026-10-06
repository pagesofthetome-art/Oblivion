import sys,struct,collections
sys.path.insert(0,'/home/claude/modscan'); from recdiff import *
def parse_q(r, p):
    subs=r.subrecords(); head=[]; stages=collections.OrderedDict(); targets=[]; cur=None; mode='head'
    def norm(s):  # normalise FormIDs in known fields to global keys
        if s.sig in ('SCRO','SCRI') and len(s.data)==4:
            fid=struct.unpack('<I',s.data)[0]; return (s.sig, p.global_key(fid))
        if s.sig=='QSTA':
            fid=struct.unpack('<I',s.data[:4])[0]; return (s.sig, p.global_key(fid), s.data[4:])
        return (s.sig, s.data)
    for s in subs:
        if s.sig=='INDX': cur=struct.unpack('<h',s.data[:2])[0]; stages[cur]=[]; mode='stage'; continue
        if s.sig=='QSTA': mode='target'; targets.append([norm(s)]); continue
        if mode=='head': head.append(norm(s))
        elif mode=='stage': stages[cur].append(norm(s))
        else: targets[-1].append(norm(s))
    return head,stages,targets
def qdiff(van, mod):
    vh,vs,vt=parse_q(*van); mh,ms,mt=parse_q(*mod)
    ch=[k for k in ms if vs.get(k)!=ms[k]]
    return {'head':vh!=mh,'stages':ch,'targets':vt!=mt}
if __name__=='__main__':
    edids=set(sys.argv[1].split(',')); pls=sys.argv[2:]
    V=recs_by_edid(VAN,'QUST',edids)
    D={pl:recs_by_edid(path_of(pl),'QUST',edids) for pl in pls}
    for e in sorted(edids):
        if e not in V: continue
        print('==',e)
        for pl in pls:
            if e in D[pl]:
                p,r=D[pl][e]; d=qdiff((V[e][1],V[e][0]),(r,p))
                print(f'   {pl[:30]:30} head:{d["head"]} targets:{d["targets"]} stages changed:{d["stages"]}')
