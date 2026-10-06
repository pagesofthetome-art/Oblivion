"""Build forge-kb.sqlite from committed facts, our notes, the research index, and (if present)
the PC-side exports. Every row carries `source` and `confidence`.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]
ROOT = TOOLS.parent
DATA = Path(__file__).resolve().parent / "data"
DEFAULT_DB = ROOT / "forge-kb.sqlite"
DEFAULT_VANILLA = ROOT / "vanilla_index.jsonl"
DEFAULT_COMMANDS = ROOT / "vanilla_commands.jsonl"
RESEARCH_INDEX = ROOT / "docs" / "14-research-mods-index.md"

XOBSE_REPO = "https://github.com/llde/xOBSE"
XOBSE_DOC = "https://htmlpreview.github.io/?https://github.com/llde/xOBSE/blob/master/obse_command_doc.html#{}"
UESP_FUNC = "https://en.uesp.net/wiki/Oblivion_Mod:{}"
UESP_RECORD = "https://en.uesp.net/wiki/Oblivion_Mod:Mod_File_Format/{}"
PERMISSIONS = ("CAN_DISTRIBUTE", "PATCH_ONLY", "REQUIRES_ORIGINAL_DOWNLOAD", "PRIVATE_RESEARCH_ONLY",
               "UNKNOWN_PERMISSION")

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE record_types (sig TEXT PRIMARY KEY, name TEXT, subrecord_count INT,
    source TEXT, url TEXT, confidence TEXT);
CREATE TABLE subrecords (sig TEXT, ord INT, sub_sig TEXT, name TEXT, kind TEXT, required INT, repeating INT,
    grp TEXT, formid INT, formid_targets TEXT, fixed_size INT, source TEXT, url TEXT, confidence TEXT,
    PRIMARY KEY (sig, ord));
CREATE TABLE subrecord_fields (sig TEXT, ord INT, sub_sig TEXT, field_ord INT, name TEXT, type TEXT,
    offset INT, size INT, formid INT, source TEXT, confidence TEXT);
CREATE TABLE functions (name TEXT PRIMARY KEY COLLATE NOCASE, alias TEXT COLLATE NOCASE, origin TEXT,
    category TEXT, ref_required INT, return_type TEXT, obse_version INT, condition_index INT,
    opcode INT, deprecated INT, summary TEXT, params_note TEXT, example TEXT,
    source TEXT, url TEXT, confidence TEXT);
CREATE TABLE function_params (func TEXT COLLATE NOCASE, ord INT, name TEXT, type TEXT, optional INT,
    source TEXT, confidence TEXT);
CREATE TABLE vanilla_forms (plugin TEXT, owner TEXT, objid TEXT, formid TEXT, sig TEXT,
    edid TEXT COLLATE NOCASE, full TEXT, override INT, deleted INT, source TEXT, confidence TEXT);
CREATE INDEX vf_edid ON vanilla_forms(edid);
CREATE INDEX vf_formid ON vanilla_forms(formid);
CREATE INDEX vf_sig ON vanilla_forms(sig);
CREATE TABLE techniques (id INTEGER PRIMARY KEY, specimen TEXT, nexus_id INT, archive TEXT, sha256 TEXT,
    author TEXT, version TEXT, runtime TEXT, technique TEXT, notes TEXT, functions_used TEXT,
    permission TEXT, source TEXT, url TEXT, confidence TEXT);
CREATE TABLE engine_classes (name TEXT, parent TEXT, size INT, vtable TEXT, runtime TEXT, notes TEXT,
    source TEXT, confidence TEXT);
CREATE TABLE engine_fields (class TEXT, field TEXT, offset INT, type TEXT, runtime TEXT, notes TEXT,
    source TEXT, confidence TEXT);
CREATE TABLE engine_functions (class TEXT, function TEXT, address TEXT, rva TEXT, signature TEXT,
    runtime TEXT, notes TEXT, source TEXT, confidence TEXT);
CREATE TABLE crash_signatures (id TEXT PRIMARY KEY, title TEXT, symptoms TEXT, cause TEXT, fix TEXT,
    components TEXT, source TEXT, confidence TEXT);
CREATE TABLE test_results (id TEXT PRIMARY KEY, test TEXT, subject TEXT, result TEXT, date TEXT,
    evidence TEXT, source TEXT, confidence TEXT);
CREATE VIRTUAL TABLE fts USING fts5(kind, key, title, body, tokenize='porter unicode61');
"""


def camel_words(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name.replace("_", " "))
    s = re.sub(r"([A-Za-z])([0-9])", r"\1 \2", s)
    return re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- loaders
def load_records(db, fts):
    schemas = _json(DATA / "record_schemas.json")
    sys.path.insert(0, str(TOOLS / "merge-patch"))
    import tes4_plugin as tp
    try:
        import patchlib
        pl_formids = {k for k, v in patchlib.F.items() if v}
    except Exception:
        pl_formids = set()
    n_sub = 0
    for r in schemas:
        sig = r["sig"]
        name = r["name"] or tp.RECORD_NAMES.get(sig, "")
        url = UESP_RECORD.format(sig)
        db.execute("INSERT INTO record_types VALUES (?,?,?,?,?,?)",
                   (sig, name, len(r["subrecords"]), r["source"], url, "HIGH_CONFIDENCE"))
        fid_list = []
        for s in r["subrecords"]:
            sub = s["sig"]
            both = s["formid"] and (sig, sub) in pl_formids
            conf = "CONFIRMED_MULTI_SOURCE" if both else "HIGH_CONFIDENCE"
            src = r["source"] + (" + tools/merge-patch/patchlib.py F table" if both else "")
            fixed = sum(f["size"] for f in s["fields"]) if s["fields"] and all(f["size"] for f in s["fields"]) else None
            db.execute("INSERT INTO subrecords VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (sig, s["order"], sub, s["name"], s["kind"], int(s["required"]), int(s["repeating"]),
                        s["group"], int(s["formid"]), ",".join(s["formid_targets"]), fixed, src, url, conf))
            for i, f in enumerate(s["fields"]):
                db.execute("INSERT INTO subrecord_fields VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (sig, s["order"], sub, i, f["name"], f["type"], f["offset"], f["size"],
                            int(f["formid"]), r["source"], "HIGH_CONFIDENCE"))
            if s["formid"]:
                fid_list.append(sub)
            n_sub += 1
        # conditions (CTDA) hold FormIDs in their parameters when the function takes a form
        if any(s["sig"] == "CTDA" for s in r["subrecords"]):
            fid_list.append("CTDA (parameters, when the condition function takes a form)")
        body = (f"{name} record. Subrecords in order: " + " ".join(s["sig"] for s in r["subrecords"])
                + ". FormID subrecords: " + ", ".join(dict.fromkeys(fid_list)) + ". Required: "
                + ", ".join(s["sig"] for s in r["subrecords"] if s["required"]))
        fts.append(("record", sig, f"{sig} {name}", body))
    return len(schemas), n_sub


def load_functions(db, fts, commands_path: Path | None):
    cur = _json(DATA / "curated.json")["functions"]
    obse = _json(DATA / "obse_functions.json")
    van = _json(DATA / "vanilla_functions.json")
    ptypes = _json(DATA / "param_types.json")
    rows: dict[str, dict] = {}

    for f in obse:
        rows[f["name"].lower()] = {
            "name": f["name"], "alias": f["alias"], "origin": "obse", "category": f["category"],
            "ref_required": f["ref_required"], "return_type": f["return_type"], "obse_version": f["obse_version"],
            "condition_index": None, "opcode": None, "deprecated": f["deprecated"],
            "params": f["params"], "params_unparsed": f.get("params_unparsed"),
            "source": f"{XOBSE_REPO}/blob/master/obse/obse/{f['file']}", "url": XOBSE_DOC.format(f["name"]),
            "confidence": "HIGH_CONFIDENCE", "help": ""}
    conds = {c["name"].lower(): c for c in van["condition_functions"]}
    vim_names = {n.lower(): n for n in van["vim_names"]}
    exe = {}
    if commands_path and commands_path.is_file():
        for line in commands_path.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if c.get("table") == "script":
                exe[c["name"].lower()] = c
    for key in set(vim_names) | set(conds) | set(exe):
        if key in rows and key not in exe:
            continue          # an OBSE command of the same name (e.g. condition-capable OBSE funcs)
        c, e = conds.get(key), exe.get(key)
        name = (e or {}).get("name") or (c or {}).get("name") or vim_names[key]
        srcs = []
        if key in vim_names:
            srcs.append("vim obse.vim csFunction list")
        if c:
            srcs.append("xEdit wbDefinitionsTES4.pas condition table")
        if e:
            srcs.append("Oblivion.exe command table (local export)")
        conf = "CONFIRMED_MULTI_SOURCE" if len(srcs) >= 2 or e else (
            "HIGH_CONFIDENCE" if c else "HYPOTHESIS")
        params = []
        if e:
            params = [{"name": p["name"], "type": ptypes.get(str(p["type_id"]), str(p["type_id"])),
                       "optional": p["optional"]} for p in e["params"]]
        elif c:
            params = [{"name": t, "type": t, "optional": False} for t in c["param_types"]]
        rows[key] = {
            "name": name, "alias": (e or {}).get("alias", ""), "origin": "vanilla", "category": "vanilla",
            "ref_required": (e or {}).get("ref_required"), "return_type": "number", "obse_version": None,
            "condition_index": c["index"] if c else None, "opcode": (e or {}).get("opcode"), "deprecated": False,
            "params": params, "params_unparsed": not (e or c),
            "source": " + ".join(srcs), "url": UESP_FUNC.format(name), "confidence": conf,
            "help": (e or {}).get("help", "")}
    # vanilla short aliases listed by vim as separate names: fold into their long name
    for e in exe.values():
        if e.get("alias") and e["alias"].lower() in rows and rows[e["alias"].lower()]["origin"] == "vanilla" \
                and e["alias"].lower() != e["name"].lower():
            del rows[e["alias"].lower()]

    for key, r in sorted(rows.items()):
        cu = cur.get(r["name"]) or next((v for k, v in cur.items() if k.lower() == key), None)
        summary = cu.get("summary", "") if cu else ""
        conf, src = r["confidence"], r["source"]
        if cu:
            src += " | notes: " + cu.get("source", "")
            conf = cu.get("confidence", conf)     # our note names its sources
        db.execute("INSERT INTO functions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (r["name"], r["alias"], r["origin"], r["category"],
                    None if r["ref_required"] is None else int(bool(r["ref_required"])), r["return_type"],
                    r["obse_version"], r["condition_index"], r["opcode"], int(bool(r["deprecated"])), summary,
                    (cu or {}).get("params_note", ""), (cu or {}).get("example", ""), src, r["url"], conf))
        for i, p in enumerate(r["params"]):
            db.execute("INSERT INTO function_params VALUES (?,?,?,?,?,?,?)",
                       (r["name"], i, p["name"], p["type"], int(bool(p["optional"])), r["source"], r["confidence"]))
        ptxt = " ".join(f"{p['name']} {p['type']}" for p in r["params"])
        origin = "OBSE function" if r["origin"] == "obse" else "vanilla script function"
        body = " ".join(x for x in (camel_words(r["name"]), origin, r["category"], r["alias"], summary,
                                     (cu or {}).get("params_note", ""), ptxt, r["help"]) if x)
        fts.append(("function", r["name"], f"{r['name']} {camel_words(r['name'])}", body))
    return len(rows)


_FIELD = re.compile(r"^- (Archive|SHA-256|Author|Version|Runtime needs|Technique|Notes): (.*)$")


def parse_research_index(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"^## (.+?)(?: — Nexus (\d+))?\s*$", line)
        if m:
            cur = {"specimen": m.group(1).strip(), "nexus_id": int(m.group(2)) if m.group(2) else None}
            out.append(cur)
            continue
        if cur is None:
            continue
        f = _FIELD.match(line.strip())
        if f:
            cur[f.group(1).lower().replace("-", "").replace(" ", "_")] = f.group(2).strip().strip("`")
        elif cur["specimen"] == "Cross-cutting findings" and line.startswith("- **"):
            m2 = re.match(r"- \*\*(.+?)\*\*\s*(.*)", line)
            if m2:
                out.append({"specimen": "Cross-cutting: " + m2.group(1).rstrip(".:"), "nexus_id": None,
                            "technique": m2.group(2).strip(), "cross": True})
    return [o for o in out if o.get("technique")]


def load_techniques(db, fts, func_names: list[str]):
    rows = parse_research_index(RESEARCH_INDEX)
    pat = re.compile(r"\b(" + "|".join(sorted((re.escape(n) for n in func_names if len(n) > 4),
                                              key=len, reverse=True)) + r")\b", re.I)
    canon = {n.lower(): n for n in func_names}
    for r in rows:
        text = " ".join(r.get(k, "") for k in ("technique", "notes", "runtime_needs"))
        used = sorted({canon[m.lower()] for m in pat.findall(text)})
        if r.get("cross"):
            perm = "PROJECT_OWNED (our finding across specimens)"
        elif "CAN_DISTRIBUTE" in text:
            perm = "CAN_DISTRIBUTE"
        else:
            perm = "UNKNOWN_PERMISSION (treat as PRIVATE_RESEARCH_ONLY)"
        url = f"https://www.nexusmods.com/oblivion/mods/{r['nexus_id']}" if r.get("nexus_id") else ""
        cur = db.execute("INSERT INTO techniques (specimen, nexus_id, archive, sha256, author, version, runtime, "
                         "technique, notes, functions_used, permission, source, url, confidence) "
                         "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (r["specimen"], r.get("nexus_id"), r.get("archive"), r.get("sha256"), r.get("author"),
                          r.get("version"), r.get("runtime_needs"), r["technique"], r.get("notes", ""),
                          ",".join(used), perm, "docs/14-research-mods-index.md (our analysis of the archives)",
                          url, "HIGH_CONFIDENCE"))
        fts.append(("technique", str(cur.lastrowid), r["specimen"],
                    " ".join(x for x in (r["technique"], r.get("notes", ""), r.get("runtime_needs", ""),
                                         " ".join(used), " ".join(camel_words(u) for u in used)) if x)))
    return len(rows)


def load_curated_tables(db, fts):
    cur = _json(DATA / "curated.json")
    for c in cur["crash_signatures"]:
        db.execute("INSERT INTO crash_signatures VALUES (?,?,?,?,?,?,?,?)",
                   (c["id"], c["title"], c["symptoms"], c["cause"], c["fix"], c["components"], c["source"],
                    c["confidence"]))
        fts.append(("crash", c["id"], c["title"], " ".join((c["symptoms"], c["cause"], c["fix"], c["components"]))))
    for t in cur["test_results"]:
        db.execute("INSERT INTO test_results VALUES (?,?,?,?,?,?,?,?)",
                   (t["id"], t["test"], t["subject"], t["result"], t["date"], t["evidence"], t["source"],
                    t["confidence"]))
        fts.append(("test", t["id"], t["subject"], " ".join((t["test"], t["result"], t["evidence"]))))
    return len(cur["crash_signatures"]), len(cur["test_results"])


def load_vanilla(db, fts, path: Path) -> int:
    if not path or not path.is_file():
        return 0
    n = 0
    with open(path, encoding="utf-8") as fh:
        batch = []
        for line in fh:
            v = json.loads(line)
            batch.append((v["plugin"], v["owner"], v["objid"], v["formid"], v["sig"], v["edid"], v["full"],
                          int(v["override"]), int(v.get("deleted", False)),
                          f"{v['plugin']} (local export, not committed)", "HIGH_CONFIDENCE"))
            if v["edid"] and not v["override"]:
                fts.append(("form", f"{v['plugin']}:{v['formid']}", f"{v['edid']} {v['full']}",
                            f"{v['sig']} {camel_words(v['edid'])} {v['full']}"))
            if len(batch) >= 5000:
                db.executemany("INSERT INTO vanilla_forms VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
                n += len(batch); batch = []
        db.executemany("INSERT INTO vanilla_forms VALUES (?,?,?,?,?,?,?,?,?,?,?)", batch)
        n += len(batch)
    return n


def build(db_path: Path = DEFAULT_DB, vanilla: Path | None = DEFAULT_VANILLA,
          commands: Path | None = DEFAULT_COMMANDS) -> dict:
    db_path = Path(db_path)
    tmp = db_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    try:
        db.executescript(SCHEMA)
        fts: list[tuple] = []
        rt, sub = load_records(db, fts)
        nf = load_functions(db, fts, commands)
        names = [r[0] for r in db.execute("SELECT name FROM functions")]
        nt = load_techniques(db, fts, names)
        nc, ntr = load_curated_tables(db, fts)
        nv = load_vanilla(db, fts, vanilla)
        db.executemany("INSERT INTO fts (kind, key, title, body) VALUES (?,?,?,?)", fts)
        counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
            "record_types", "subrecords", "subrecord_fields", "functions", "function_params", "vanilla_forms",
            "techniques", "engine_classes", "engine_fields", "engine_functions", "crash_signatures",
            "test_results", "fts")}
        counts["functions_obse"] = db.execute("SELECT COUNT(*) FROM functions WHERE origin='obse'").fetchone()[0]
        counts["functions_vanilla"] = db.execute("SELECT COUNT(*) FROM functions WHERE origin='vanilla'").fetchone()[0]
        meta = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "vanilla_index": str(vanilla) if nv else "", "vanilla_commands": str(commands)
                if commands and Path(commands).is_file() else "", "counts": json.dumps(counts),
                "provenance": (DATA / "provenance.json").read_text(encoding="utf-8")}
        db.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
        db.commit()
    finally:
        db.close()
    tmp.replace(db_path)
    return counts
