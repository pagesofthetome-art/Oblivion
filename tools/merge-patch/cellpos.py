import sys,struct,math,json
sys.path.insert(0,'/home/claude/Games/tools'); import tes4_plugin as tp
VAN='/mnt/user-data/uploads/common--Oblivion/Data/Oblivion.esm'
def cell_objs(path, grids):
    recs=[];cells={};names={}
    for p,r in tp.iter_records(path):
        recs.append(r)
        if r.sig not in ('REFR','ACHR','ACRE','LAND','CELL'): 
            try: names[r.form_id]=r.editor_id
            except: pass
        if r.sig=='CELL':
            x=r.first('XCLC')
            if x: 
                g=struct.unpack('<ii',x[:8]); 
                wk=p.global_key(r.parent) if r.parent is not None else None
                if wk==('oblivion.esm',0x3C) and f'{g[0]},{g[1]}' in grids: cells[r.form_id]=f'{g[0]},{g[1]}'
    out={g:{'objs':[],'land':None} for g in grids}
    for r in recs:
        if r.parent in cells:
            g=cells[r.parent]
            if r.sig in ('REFR','ACHR','ACRE'):
                d=r.first('DATA'); nm=r.first('NAME')
                if d and nm:
                    x,y,z=struct.unpack('<fff',d[:12]); b=struct.unpack('<I',nm)[0]
                    out[g]['objs'].append((names.get(b,'%08X'%b),round(x),round(y),round(z),p.is_override(r), r.is_deleted or bool(r.first('XESP'))))
            elif r.sig=='LAND':
                v=r.first('VHGT')
                if v: out[g]['land']=v[:4+33*33]
    return out
def heights(v):
    off=struct.unpack('<f',v[:4])[0]; vals=struct.unpack('<'+'b'*(33*33),v[4:4+33*33])
    h=[];row=off
    for r in range(33):
        row+=vals[r*33]; acc=row; line=[acc]
        for c in range(1,33): acc+=vals[r*33+c]; line.append(acc)
        h.append(line)
    return [[x*8 for x in l] for l in h]
if __name__=='__main__':
    a,b=sys.argv[1],sys.argv[2]; grids=sys.argv[3].split(';')
    A=cell_objs(a,grids); B=cell_objs(b,grids); V=cell_objs(VAN,grids)
    for g in grids:
        print('== cell',g)
        na=[o for o in A[g]['objs'] if not o[4]]; nb=[o for o in B[g]['objs'] if not o[4]]
        def summ(l): 
            import collections; return collections.Counter(o[0] for o in l).most_common(8)
        print('  A new:',len(na),summ(na)); print('  B new:',len(nb),summ(nb))
        if na and nb:
            md=min(math.dist(p[1:4],q[1:4]) for p in na for q in nb); print('  closest A-B objects: %.0f units (%.1f m)'%(md,md/70))
        for nm,X in (('A',A),('B',B)):
            if X[g]['land'] and V[g]['land']:
                ha=heights(X[g]['land']); hv=heights(V[g]['land'])
                diffs=[abs(ha[i][j]-hv[i][j]) for i in range(33) for j in range(33)]
                print(f'  {nm} land change vs vanilla: max {max(diffs):.0f} units, avg {sum(diffs)/len(diffs):.1f}')
        if A[g]['land'] and B[g]['land']:
            ha=heights(A[g]['land']); hb=heights(B[g]['land'])
            d=[abs(ha[i][j]-hb[i][j]) for i in range(33) for j in range(33)]
            print(f'  A vs B land difference: max {max(d):.0f}, avg {sum(d)/len(d):.1f}')

VE=json.load(open('/home/claude/modscan/van_edid.json'))
def nm(x): return VE.get(x,x)
def hat(h,g,x,y):
    gx,gy=map(int,g.split(',')); lx=(x-gx*4096)/128; ly=(y-gy*4096)/128
    i=min(32,max(0,round(ly))); j=min(32,max(0,round(lx))); return h[i][j]
def detail(a,b,g):
    A=cell_objs(a,[g]);B=cell_objs(b,[g]);V=cell_objs(VAN,[g])
    for tag,X,Y in (('A',A,B),('B',B,A)):
        objs=[o for o in X[g]['objs'] if not o[4]]
        # terrain under X's objects: X's own land (or vanilla) vs the other plugin's land
        own=X[g]['land'] or V[g]['land']; oth=Y[g]['land']
        if not oth or not own: continue
        ho=heights(own); ht=heights(oth); bad=[]
        for o in objs:
            d=hat(ht,g,o[1],o[2])-hat(ho,g,o[1],o[2])
            if abs(d)>40: bad.append((nm(o[0]),round(d)))
        print(f'  {tag} objects affected if other plugin\'s terrain wins: {len(bad)}/{len(objs)}', bad[:10])
