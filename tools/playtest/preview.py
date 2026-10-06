"""forge preview: a walkable browser view of the test cell or a mod's placed objects.

Built from the shared template (preview/oblivion-preview-template.html): its engine (WebGL with
the software-canvas fallback, physics, player, pad/keyboard/touch input, HUD) is kept as is; the
template's TEST LOCATION and MOD blocks are replaced by a scene generated from plugin data.

What is drawn comes from the plugin bytes (tes4_plugin): every CELL with references, each REFR /
ACHR at its DATA position and rotation, bases sized from their MODB bound
radius. NPCs come with their packages (PKID -> PACK: type, location, PSDT schedule).

Controls: WASD / left stick walk, mouse drag / right stick look. Click an NPC or door, or aim at it
and press Cross / E, to see its packages and schedule. Circle / Esc closes. D-pad left/right or
1..9 / Q / F switch cells.
"""

from __future__ import annotations

import html
import json
import re
import struct
from pathlib import Path

from playtest import testcells  # noqa: F401  (package/service names)

REPO = Path(__file__).resolve().parents[2]
TEMPLATE = REPO / "preview" / "oblivion-preview-template.html"
UNITS_PER_M = 70.0
MARKER_BASES = {0x00000034, 0x0000003B, 0x00000001, 0x00000002, 0x00000010}
PACKAGE_NAMES = {v: k for k, v in testcells.PACKAGE_TYPES.items()}
LOCATION_NAMES = {0: "near", 1: "in cell", 2: "near current location", 3: "near editor location",
                  4: "near object", 5: "near object type"}
SERVICE_NAMES = {v: k for k, v in testcells.SERVICES.items()}


class PreviewError(RuntimeError):
    pass


# ---------------------------------------------------------------- plugin data
def _z(b: bytes | None) -> str:
    return b.split(b"\0", 1)[0].decode("cp1252", "replace") if b else ""


def _hours(hour: int, dur: int) -> str:
    if hour < 0:
        return "any time"
    if dur >= 24:
        return "all day"
    return f"{hour % 24:02d}:00-{(hour + dur) % 24:02d}:00"


def extract(plugin: Path) -> dict:
    import tes4_plugin as tp
    pl = tp.load(plugin)
    if pl.errors:
        raise PreviewError(f"{plugin.name}: " + "; ".join(pl.errors[:3]))
    names: dict[int, str] = {}
    bases: dict[int, dict] = {}
    packs: dict[int, dict] = {}
    npcs: dict[int, dict] = {}
    cells: dict[int, dict] = {}
    refs: list[tuple[int, dict]] = []
    for r in pl.records:
        if r.editor_id:
            names[r.form_id] = r.editor_id
    for r in pl.records:
        s = {x.sig: x.data for x in r.subrecords()}
        if r.sig == "CELL":
            flags = s.get("DATA", b"\0")[0]
            cells[r.form_id] = {"edid": r.editor_id, "name": r.full_name or r.editor_id,
                                "interior": bool(flags & 1), "exterior_like": bool(flags & 0x80) or not (flags & 1),
                                "refs": []}
        elif r.sig in ("REFR", "ACHR", "ACRE"):
            d = s.get("DATA")
            if not d or len(d) < 24 or "NAME" not in s:
                continue
            x, y, z, rx, ry, rz = struct.unpack_from("<6f", d)
            ref = {"sig": r.sig, "edid": r.editor_id, "formid": f"{r.form_id:08X}",
                   "base": struct.unpack("<I", s["NAME"][:4])[0], "pos": [x, y, z], "rot": rz,
                   "scale": struct.unpack("<f", s["XSCL"])[0] if "XSCL" in s else 1.0}
            if "XTEL" in s:
                ref["teleport"] = struct.unpack_from("<I", s["XTEL"])[0]
            refs.append((r.parent, ref))
        elif r.sig == "PACK":
            pk = s.get("PKDT", b"\0" * 8)
            flags, ptype = (struct.unpack_from("<IB", pk) if len(pk) >= 5 else (struct.unpack_from("<H", pk)[0], pk[2]))
            loc = struct.unpack_from("<iIi", s["PLDT"]) if len(s.get("PLDT", b"")) >= 12 else None
            sch = struct.unpack_from("<bbBbi", s["PSDT"]) if len(s.get("PSDT", b"")) >= 8 else None
            packs[r.form_id] = {"edid": r.editor_id, "type": PACKAGE_NAMES.get(ptype, f"type {ptype}"),
                                "flags": flags, "location": loc, "schedule": sch}
        elif r.sig in ("NPC_", "CREA"):
            acbs = s.get("ACBS", b"\0" * 16)
            aidt = s.get("AIDT", b"\0" * 12)
            data = s.get("DATA", b"")
            npcs[r.form_id] = {
                "edid": r.editor_id, "name": r.full_name or r.editor_id, "sig": r.sig,
                "level": struct.unpack_from("<h", acbs, 10)[0] if len(acbs) >= 12 else None,
                "essential": bool(struct.unpack_from("<I", acbs)[0] & 2) if len(acbs) >= 4 else False,
                "health": struct.unpack_from("<I", data, 21)[0] if r.sig == "NPC_" and len(data) >= 25 else None,
                "aggression": aidt[0] if aidt else None, "confidence": aidt[1] if len(aidt) > 1 else None,
                "services": struct.unpack_from("<I", aidt, 4)[0] if len(aidt) >= 8 else 0,
                "packages": [struct.unpack("<I", x.data[:4])[0] for x in r.subrecords() if x.sig == "PKID"],
            }
            bases[r.form_id] = {"sig": r.sig, "edid": r.editor_id, "name": r.full_name}
        else:
            modb = s.get("MODB")
            bases[r.form_id] = {"sig": r.sig, "edid": r.editor_id, "name": r.full_name,
                                "radius": struct.unpack("<f", modb[:4])[0] if modb and len(modb) >= 4 else None}
    for parent, ref in refs:
        if parent in cells:
            cells[parent]["refs"].append(ref)
    out_cells = []
    for fid, c in cells.items():
        if not c["refs"]:
            continue
        out_cells.append(_cell_view(fid, c, bases, npcs, packs, names))
    return {"plugin": plugin.name, "masters": list(pl.masters), "cells": out_cells}


def extract_vanilla_cell(esm: Path, cell_fid: int, edid: str, name: str) -> dict:
    """One vanilla interior from Oblivion.esm (read only): its refs, sized from each base's MODB."""
    import tes4_plugin as tp
    refs = []
    for _, r in tp.iter_records(esm, {"REFR", "ACHR", "ACRE"}):
        if r.parent != cell_fid:
            continue
        s = {x.sig: x.data for x in r.subrecords()}
        if "DATA" not in s or "NAME" not in s:
            continue
        x, y, z, rx, ry, rz = struct.unpack_from("<6f", s["DATA"])
        ref = {"sig": r.sig, "edid": r.editor_id, "formid": f"{r.form_id:08X}",
               "base": struct.unpack("<I", s["NAME"][:4])[0], "pos": [x, y, z], "rot": rz}
        if "XTEL" in s:
            ref["teleport"] = struct.unpack_from("<I", s["XTEL"])[0]
        refs.append(ref)
    want = {r["base"] for r in refs}
    bases, npcs = {}, {}
    for _, r in tp.iter_records(esm, None, want):
        modb = r.first("MODB")
        bases[r.form_id] = {"sig": r.sig, "edid": r.editor_id, "name": r.full_name,
                            "radius": struct.unpack("<f", modb[:4])[0] if modb and len(modb) >= 4 else None}
        if r.sig in ("NPC_", "CREA"):
            npcs[r.form_id] = {"edid": r.editor_id, "name": r.full_name or r.editor_id, "level": None,
                               "essential": False, "health": None, "aggression": None, "confidence": None,
                               "services": 0, "packages": []}
    cell = {"edid": edid, "name": name, "interior": True, "exterior_like": False, "refs": refs}
    view = _cell_view(cell_fid, cell, bases, npcs, {}, {})
    return {"plugin": esm.name, "masters": [], "cells": [view]}


def _describe_pack(p: dict, names: dict) -> dict:
    loc = p["location"]
    where = ""
    if loc:
        ltype, target, radius = loc
        tname = names.get(target, f"{target:08X}") if ltype in (0, 1, 4) and target else ""
        where = f"{LOCATION_NAMES.get(ltype, ltype)} {tname}".strip() + (f" (radius {radius})" if radius else "")
    sch = p["schedule"]
    hour, dur = (sch[3], sch[4]) if sch else (-1, 24)
    return {"edid": p["edid"], "type": p["type"], "where": where, "hours": _hours(hour, dur),
            "start": hour, "duration": dur, "offers_services": bool(p["flags"] & 1)}


def _cell_view(fid, c, bases, npcs, packs, names) -> dict:
    items = []
    for ref in c["refs"]:
        b = ref["base"]
        base = bases.get(b, {})
        it = {"x": ref["pos"][0], "y": ref["pos"][1], "z": ref["pos"][2], "rot": ref["rot"],
              "edid": ref["edid"], "formid": ref["formid"], "base": base.get("edid") or f"{b:08X}"}
        if b in npcs:
            n = npcs[b]
            it.update(kind="npc", name=n["name"], npc={
                "level": n["level"], "health": n["health"], "essential": n["essential"],
                "aggression": n["aggression"], "confidence": n["confidence"],
                "services": [SERVICE_NAMES[f] for f in sorted(SERVICE_NAMES) if n["services"] & f],
                "packages": [_describe_pack(packs[p], names) if p in packs else
                             {"edid": f"{p:08X}", "type": "(in a master)", "where": "", "hours": "?",
                              "start": -1, "duration": 0, "offers_services": False} for p in n["packages"]]})
        elif b in MARKER_BASES or "marker" in (base.get("edid") or "").lower():
            it.update(kind="marker", name=ref["edid"] or "marker")
        else:
            r = base.get("radius") or 32.0
            side = max(8.0, r * 1.15)
            it.update(kind="door" if base.get("sig") == "DOOR" else "object", size=[side, side, side],
                      origin="bottom", name=base.get("name") or base.get("edid") or f"{b:08X}")
        if "teleport" in ref:
            it["teleport"] = names.get(ref["teleport"], f"{ref['teleport']:08X}")
        items.append(it)
    xs = [i["x"] for i in items]
    ys = [i["y"] for i in items]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    start = next((i for i in items if i["kind"] == "marker" and "start" in (i["edid"] or "").lower()), None)
    return {"edid": c["edid"], "name": c["name"], "formid": f"{fid:08X}", "exterior": c["exterior_like"],
            "center": [cx, cy], "half": [max(256.0, (max(xs) - min(xs)) / 2 + 128), max(256.0, (max(ys) - min(ys)) / 2 + 128)],
            "start": {"x": start["x"], "y": start["y"], "rot": start["rot"]} if start else {"x": cx, "y": cy, "rot": 0.0},
            "items": items}


# ---------------------------------------------------------------- page
def _split_template(text: str) -> tuple[str, str]:
    banner = re.compile(r"/\* =+\s*\n\s*(TEST LOCATION|MOD:|BOOT \+ MAIN LOOP)")
    marks = {m.group(1): m.start() for m in banner.finditer(text)}
    if not {"TEST LOCATION", "BOOT + MAIN LOOP"} <= set(marks):
        raise PreviewError(f"{TEMPLATE.name}: TEST LOCATION / BOOT + MAIN LOOP sections not found")
    return text[:marks["TEST LOCATION"]], text[marks["BOOT + MAIN LOOP"]:]


CLAMP_OLD = "const pp=player.body.position,pr=Math.hypot(pp.x,pp.z);if(pr>40){pp.x*=40/pr;pp.z*=40/pr;}"
CLAMP_NEW = "const pp=player.body.position;E.clamp(pp);"


def render(data: dict, title: str, subtitle: str, first_cell: str | None = None,
           template: Path = TEMPLATE) -> str:
    text = template.read_text(encoding="utf-8")
    head, boot = _split_template(text)
    if CLAMP_OLD not in boot:
        raise PreviewError("template main loop changed: player clamp line not found")
    boot = boot.replace(CLAMP_OLD, CLAMP_NEW)
    first = 0
    if first_cell:
        for i, c in enumerate(data["cells"]):
            if c["edid"].lower() == first_cell.lower():
                first = i
    js = SCENE_JS.replace("__DATA__", json.dumps(data, separators=(",", ":"))).replace("__FIRST__", str(first))
    page = head + js + boot
    esc = html.escape
    page = re.sub(r"<title>.*?</title>", f"<title>{esc(title)}</title>", page, count=1, flags=re.S)
    page = re.sub(r'<div class="eyebrow" id="eyebrow">.*?</div>',
                  f'<div class="eyebrow" id="eyebrow">TES4Forge preview · {esc(data["plugin"])} · layout check</div>',
                  page, count=1, flags=re.S)
    page = re.sub(r"<h1>.*?</h1>", f"<h1>{esc(title)}</h1>", page, count=1, flags=re.S)
    page = re.sub(r'<p class="lede" id="lede">.*?</p>', f'<p class="lede" id="lede">{esc(subtitle)}</p>',
                  page, count=1, flags=re.S)
    page = re.sub(r'<button class="btn r1" id="b-r1"[^>]*>.*?</button>',
                  '<button class="btn r1" id="b-r1" aria-pressed="false">R1 · inspect</button>', page, count=1, flags=re.S)
    page = re.sub(r'<button class="btn" id="b-r2">.*?</button>',
                  '<button class="btn" id="b-r2">R2 · next cell</button>', page, count=1, flags=re.S)
    page = re.sub(r'<button class="btn" id="b-l2">.*?</button>',
                  '<button class="btn" id="b-l2">L2 · previous cell</button>', page, count=1, flags=re.S)
    page = re.sub(r'<span class="hint" id="hint">.*?</span>',
                  '<span class="hint" id="hint">WASD walks, drag looks. Click an NPC or door, or aim and press E / '
                  'Cross, to inspect it. Esc / Circle closes. 1-9, Q / F or the D-pad switch cells.</span>',
                  page, count=1, flags=re.S)
    page = re.sub(r'<section class="build" aria-label="How it works in Oblivion">.*?</section>',
                  '<section class="build" aria-label="Inspector"><h2 id="insp-title">Inspector</h2>'
                  '<div id="insp" class="insp" tabindex="-1"><p>Aim at an NPC, a door or a marker and press E / '
                  'Cross, or click it.</p></div><h2>Cells</h2><ul id="cell-list"></ul>'
                  '<div class="note"><b>Layout check only.</b> Boxes stand in for meshes; sizes come from '
                  'each base\'s bound radius (MODB). NPCs stand still here; their packages and '
                  'schedules are listed as the game will run them.</div></section>', page, count=1, flags=re.S)
    page = page.replace("</style>", PREVIEW_CSS + "</style>", 1)
    return page


PREVIEW_CSS = """
.insp table{width:100%;border-collapse:collapse;font:13px var(--mono)}
.insp td{border-bottom:1px solid var(--line);padding:4px 6px;vertical-align:top}
.insp .day{position:relative;height:14px;background:var(--stone);border:1px solid var(--line);margin:4px 0 2px}
.insp .day i{position:absolute;top:0;bottom:0;background:var(--ember);opacity:.75}
.insp .ticks{display:flex;justify-content:space-between;font:11px var(--mono);color:var(--ash)}
#cell-list{margin:0 0 14px;padding-left:20px}
#cell-list button{background:none;border:0;color:var(--vellum);font:inherit;cursor:pointer;text-decoration:underline}
#cell-list button[aria-current="true"]{color:var(--ember)}
"""

SCENE_JS = r"""/* ==========================================================================
   TEST LOCATION: generated by forge preview from plugin data
   ========================================================================== */
const PV=__DATA__;const U=70;
const toW=(x,y)=>({x:x/U,z:-y/U});
let welk={rotation:{y:0}},welkL={intensity:0},fire=[],fireL={intensity:0};E.clouds=[];
{const g=new THREE.SphereGeometry(600,32,16),c=[],p=g.attributes.position,a=new THREE.Color(HORIZON),b=new THREE.Color(ZENITH);
  for(let i=0;i<p.count;i++){const k=Math.pow(Math.max(0,p.getY(i)/600),.55);const col=a.clone().lerp(b,k);c.push(col.r,col.g,col.b);}
  g.setAttribute('color',new THREE.Float32BufferAttribute(c,3));
  E.sky=new THREE.Mesh(g,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.BackSide,fog:false,depthWrite:false}));E.sky.renderOrder=-10;scene.add(E.sky);}
const KC={floor:0x8d8a83,wall:0x6f6b63,block:0x7a5a3a,door:0x8a5a2b,trinket:0xc8a050,object:0x5f7f9a};
const CELL={i:0,group:null,bodies:[],bounds:null,npcs:[]};
E.clamp=pp=>{const b=CELL.bounds;if(!b)return;pp.x=Math.max(b.x0,Math.min(b.x1,pp.x));pp.z=Math.max(b.z0,Math.min(b.z1,pp.z));};
function clearCell(){if(CELL.group)scene.remove(CELL.group);CELL.bodies.forEach(b=>world.removeBody(b));CELL.bodies=[];E.occluders.length=0;}
function box(it,color){const s=it.size,w=s[0]/U,d=s[1]/U,h=s[2]/U,P=toW(it.x,it.y);
  const m=mesh(new THREE.BoxGeometry(w,h,d),M(color));const y=it.origin==='top'?-h/2:h/2+it.z/U;
  m.position.set(P.x,y,P.z);m.rotation.y=-it.rot;CELL.group.add(m);
  if(it.kind!=='floor'){CELL.bodies.push(solid(P.x,y,P.z,w/2,h/2,d/2,-it.rot));E.occluders.push(m);}return m;}
function marker(it){const P=toW(it.x,it.y);const g=new THREE.Group();
  const c=mesh(new THREE.ConeGeometry(.18,.5,8),new THREE.MeshLambertMaterial({color:0xf08a4b,transparent:true,opacity:.75}),false);c.rotation.x=-Math.PI/2;c.position.set(0,.3,-.2);g.add(c);
  const r=mesh(new THREE.CylinderGeometry(.35,.35,.04,16),new THREE.MeshLambertMaterial({color:0xf08a4b,transparent:true,opacity:.45}),false);r.position.y=.02;g.add(r);
  g.position.set(P.x,0,P.z);g.rotation.y=-it.rot;CELL.group.add(g);return g;}
function loadCell(i){clearCell();CELL.i=(i+PV.cells.length)%PV.cells.length;const c=PV.cells[CELL.i];CELL.group=new THREE.Group();scene.add(CELL.group);
  const ext=c.exterior;renderer.setClearColor(ext?HORIZON:0x14100f);scene.fog.color.set(ext?HORIZON:0x14100f);scene.fog.near=ext?35:20;scene.fog.far=ext?170:80;E.sky.visible=ext&&!SOFT;
  hemi.intensity=ext?.7:.55;sun.intensity=ext?.95:.35;
  const C=toW(c.center[0],c.center[1]),hx=c.half[0]/U,hz=c.half[1]/U;
  if(!c.items.some(it=>it.kind==='floor')){const f=mesh(new THREE.PlaneGeometry(hx*2+4,hz*2+4),M(ext?0x56722f:0x3a3330),false);f.rotation.x=-Math.PI/2;f.position.set(C.x,.001,C.z);CELL.group.add(f);}
  CELL.bounds={x0:C.x-hx,x1:C.x+hx,z0:C.z-hz,z1:C.z+hz};
  c.items.forEach(it=>{let o=null;
    if(it.kind==='npc')return;
    if(it.kind==='marker')o=marker(it);else o=box(it,KC[it.kind]||KC.object);
    if(it.kind==='door'||it.kind==='marker'||it.kind==='object')o.traverse(x=>x.userData.thing={kind:it.kind,name:it.name,item:it});
    if(it.kind==='marker')E.occluders.push(o);});
  const S=toW(c.start.x,c.start.y);START.x=S.x;START.z=S.z;START.yaw=-c.start.rot;
  renderCells();showCellInfo(c);}
function spawnTargets(){}
function renderCells(){const ul=$('cell-list');ul.innerHTML='';PV.cells.forEach((c,i)=>{const li=document.createElement('li'),b=document.createElement('button');
  b.textContent=(i+1)+'. '+c.name+' ('+c.edid+')';b.setAttribute('aria-current',i===CELL.i);b.onclick=()=>switchCell(i);li.appendChild(b);ul.appendChild(li);});}
function switchCell(i){loadCell(i);E.reset(true);E.toast(PV.cells[CELL.i].name);showCellInfo(PV.cells[CELL.i]);}
function td(k,v){return '<tr><td>'+esc(k)+'</td><td>'+esc(v)+'</td></tr>';}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));}
function dayBar(pk){if(pk.start<0)return '';const segs=[];const s=pk.start,e=s+Math.min(24,pk.duration);
  const add=(a,b)=>segs.push('<i style="left:'+(a/24*100)+'%;width:'+((b-a)/24*100)+'%"></i>');if(e<=24)add(s,e);else{add(s,24);add(0,e-24);}
  return '<div class="day" aria-hidden="true">'+segs.join('')+'</div><div class="ticks"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>';}
function inspect(t){if(!t)return;const it=t.item||{};let h='',title=t.name||it.name||'?';
  if(t.kind==='actor'||it.kind==='npc'){const n=it.npc||{};
    h+='<table>'+td('Reference',(it.edid||'')+' '+it.formid)+td('Base',it.base)+td('Level',n.level)+td('Health',n.health)+td('Essential',n.essential?'yes':'no')+td('Aggression / confidence',n.aggression+' / '+n.confidence)+td('Services',(n.services||[]).join(', ')||'none')+'</table>';
    h+='<h3>Packages and schedule</h3>';
    if(!(n.packages||[]).length)h+='<p>No AI packages: the NPC stands where it was placed.</p>';
    (n.packages||[]).forEach(pk=>{h+='<p><b>'+esc(pk.hours)+'</b> · '+esc(pk.type)+' '+esc(pk.where)+(pk.offers_services?' · offers services':'')+'<br><code>'+esc(pk.edid)+'</code></p>'+dayBar(pk);});}
  else if(it.kind==='door'){h+='<table>'+td('Reference',(it.edid||'')+' '+it.formid)+td('Base',it.base)+td('Leads to',it.teleport||'(not a load door)')+'</table>';}
  else{h+='<table>'+td('Reference',(it.edid||'(no EditorID)')+' '+(it.formid||''))+td('Base',it.base)+td('Position',[it.x,it.y,it.z].map(v=>Math.round(v)).join(', '))+'</table>';}
  $('insp-title').textContent=title;$('insp').innerHTML=h;E.toast(title);}
function showCellInfo(c){$('school').textContent=(c.exterior?'Behaves like an exterior':'Interior')+' · '+PV.plugin;$('tome-title').textContent=c.name;$('spellname').textContent=c.name;
  const n=k=>c.items.filter(i=>i.kind===k).length;$('tome').innerHTML='';
  [['Cell EditorID',c.edid],['References',c.items.length],['NPCs',n('npc')],['Doors',n('door')],['Markers',n('marker')],['Size (units)',Math.round(c.half[0]*2)+' × '+Math.round(c.half[1]*2)]].forEach(([k,v])=>{const tr=document.createElement('tr'),a=document.createElement('td'),b=document.createElement('td');a.textContent=k;b.textContent=v;tr.append(a,b);$('tome').appendChild(tr);});
  $('flavor').textContent='Placed objects read from '+PV.plugin+'; masters: '+PV.masters.join(', ');}
const ray2=new THREE.Raycaster();
function pick(nx,ny){ray2.setFromCamera(new THREE.Vector2(nx,ny),cam);ray2.far=40;const list=E.occluders.slice();E.things.forEach(t=>list.push(...t.meshes));
  const h=ray2.intersectObjects(list,true)[0];if(!h)return null;let o=h.object;while(o&&!o.userData.thing)o=o.parent;return o?o.userData.thing:null;}
{let down=null;cv.addEventListener('pointerdown',e=>{down={x:e.clientX,y:e.clientY,t:performance.now()};});
  cv.addEventListener('pointerup',e=>{if(!down)return;const d=Math.hypot(e.clientX-down.x,e.clientY-down.y),dt=performance.now()-down.t;down=null;
    if(d<6&&dt<350&&e.button===0){const r=cv.getBoundingClientRect();const t=pick((e.clientX-r.left)/r.width*2-1,-((e.clientY-r.top)/r.height*2-1));if(t)inspect(t);}});}
addEventListener('keydown',e=>{if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;
  if(e.code==='KeyE'){inspect(pick(0,0));}
  if(e.code==='Escape'){$('insp-title').textContent='Inspector';$('insp').innerHTML='<p>Closed.</p>';}
  const m=/^Digit([1-9])$/.exec(e.code);if(m&&+m[1]<=PV.cells.length)switchCell(+m[1]-1);});

/* ==========================================================================
   MOD: layout preview (no spell; the engine's cast/throw/drop become inspect / next / previous cell)
   ========================================================================== */
const MOD={name:'Layout preview',school:'',color:0xf08a4b,flavor:'',params:{},tome:[],s:{cast:false},
  pad:[],
  init(E){E.stopDemo();$('t-demo').checked=false;showCellInfo(PV.cells[CELL.i]);},
  spawn(E){CELL.npcs=[];PV.cells[CELL.i].items.filter(i=>i.kind==='npc').forEach(it=>{const P=toW(it.x,it.y);
    const t=E.addActor(it.name,P.x,P.z,Math.PI-it.rot);t.item=it;CELL.npcs.push(t);});},
  action(E,n,down){if(!down)return;if(n==='cast')inspect(pick(0,0));if(n==='throw')switchCell(CELL.i+1);if(n==='drop')switchCell(CELL.i-1);},
  update(E,dt){const gp=(navigator.getGamepads?[...navigator.getGamepads()]:[]).find(g=>g&&g.connected);
    if(gp){const b=i=>!!(gp.buttons[i]&&gp.buttons[i].pressed);const edge=i=>{const v=b(i),was=this.pad[i];this.pad[i]=v;return v&&!was;};
      if(edge(0))inspect(pick(0,0));if(edge(1)){$('insp-title').textContent='Inspector';$('insp').innerHTML='<p>Closed.</p>';}
      if(edge(15))switchCell(CELL.i+1);if(edge(14))switchCell(CELL.i-1);}
    const a=E.aim(30);E.hud.target=a&&a.thing?(a.thing.name||''):'';E.hud.hot=!!(a&&a.thing);E.hud.drain='';},
  demo:[],
};
loadCell(__FIRST__);

"""


def build_page(plugin: Path, out: Path, title: str | None = None, first_cell: str | None = None,
               extra_plugins: list[Path] = ()) -> Path:
    data = extract(plugin)
    for p in extra_plugins:
        more = extract(p)
        data["cells"] += more["cells"]
    if not data["cells"]:
        raise PreviewError(f"{plugin.name} places no objects in any cell")
    title = title or plugin.stem
    sub = (f"{len(data['cells'])} cell(s) from {plugin.name}. Walk the layout before a real launch: "
           "NPCs, doors and markers can be inspected.")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data, title, sub, first_cell), encoding="utf-8")
    return out
