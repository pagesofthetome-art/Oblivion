"""playtest_manifest.json: the scripted in-game checks, and how they run.

Source: the spec's `test_plan` (or a JSON/YAML file given with --manifest):

    test_plan:
      cell: arena                  # arena | street | open | <vanilla InteriorEditorID> | marker:<Map marker>
      steps:
        - addspell: ForgeExampleFireboltSpell
        - check: {ref: player, fn: HasSpell, args: [ForgeExampleFireboltSpell], expect: "== 1"}
        - check: {ref: ForgeArenaDummyRef, fn: GetAV, args: [Health], save: hp}
        - cast: {spell: ForgeExampleFireboltSpell, target: ForgeArenaDummyRef}
        - wait: 3
        - check: {ref: ForgeArenaDummyRef, fn: GetAV, args: [Health], expect: "< $hp"}

Step kinds: additem, removeitem, equip, addspell, cast, spawn, setav, modav, moveto, weather,
console (raw command), wait (seconds of unpaused game time), check (a console function whose
result is compared after the run).

How it runs in game. Oblivion can't read JSON, and a compiled OBSE quest would need the
Construction Set for every new manifest. So the manifest is compiled into numbered console batch
files (fpt1.txt, fpt2.txt ...; one per `wait`), which the boot driver runs with the vanilla `bat`
command. Each line is compiled by the game as a one-line script, so references are named by their
EditorID (`ForgeArenaDummyRef.GetAV Health`). Each check value goes into a result global from
ForgeTestCells.esp (first set to a sentinel, so a failed line never counts as a value), and xOBSE's
PrintToFile writes markers and values to forge_test.log. The last batch also saves the game as
ForgePlaytestResult, whose globals are a second way to read the results. `forge test` then compares
the values with the expectations: a check with no value, or a missing END, is a failure. "It
launched" is never a pass.
"""

from __future__ import annotations

import json
import math
import re
import secrets
from pathlib import Path

MANIFEST_VERSION = 1
OPS = {"additem", "removeitem", "equip", "addspell", "cast", "spawn", "setav", "modav", "moveto", "weather",
       "console", "wait", "check"}
EXPECT_RE = re.compile(r"^\s*(==|!=|<=|>=|<|>)\s*(\$[A-Za-z_]\w*|[-+]?\d+(?:\.\d+)?)\s*$")
NAME_RE = re.compile(r"^[A-Za-z_][\w]*$")
FORMID_RE = re.compile(r"^(?:0x)?[0-9A-Fa-f]{1,8}$")
BATCH_PREFIX = "fpt"
LOG_NAME = "forge_test.log"
MAX_WAIT = 600


class ManifestError(ValueError):
    pass


# ---------------------------------------------------------------- parsing / normalising
def _one_step(i: int, raw) -> dict:
    if isinstance(raw, str):
        raise ManifestError(f"step {i}: {raw!r} is free text; automated steps need a kind "
                            f"(one of {sorted(OPS)}). Free-text notes go under test_plan.notes")
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ManifestError(f"step {i}: write each step as one key, e.g. '- wait: 3' (got {raw!r})")
    (op, val), = raw.items()
    op = str(op).lower()
    if op not in OPS:
        raise ManifestError(f"step {i}: unknown kind {op!r}; use one of {sorted(OPS)}")
    st: dict = {"n": i, "do": op}
    if op == "wait":
        try:
            secs = float(val)
        except (TypeError, ValueError):
            raise ManifestError(f"step {i}: wait needs seconds, got {val!r}") from None
        if not 0 < secs <= MAX_WAIT:
            raise ManifestError(f"step {i}: wait must be 0..{MAX_WAIT} seconds")
        st["seconds"] = secs
        return st
    if op == "console":
        cmd = str(val)
        if "\n" in cmd or "\r" in cmd or not cmd.strip():
            raise ManifestError(f"step {i}: console needs one command line")
        st["command"] = cmd.strip()
        return st
    if op in ("addspell", "equip", "moveto", "weather") and not isinstance(val, dict):
        val = {"form": val} if op != "moveto" else {"to": val}
    if op in ("additem", "removeitem", "spawn") and not isinstance(val, dict):
        val = {"form": val}
    if not isinstance(val, dict):
        raise ManifestError(f"step {i}: {op} needs a mapping, got {val!r}")
    st.update(val)
    need = {"additem": ["form"], "removeitem": ["form"], "equip": ["form"], "addspell": ["form"],
            "cast": ["spell", "target"], "spawn": ["form"], "setav": ["av", "value"], "modav": ["av", "value"],
            "moveto": ["to"], "weather": ["form"], "check": ["fn"]}[op]
    for k in need:
        if st.get(k) in (None, ""):
            raise ManifestError(f"step {i}: {op} needs '{k}'")
    if op == "check":
        if not NAME_RE.match(str(st["fn"])):
            raise ManifestError(f"step {i}: bad function name {st['fn']!r}")
        st.setdefault("ref", "player")
        st["args"] = [str(a) for a in (st.get("args") or [])]
        if "expect" in st and not EXPECT_RE.match(str(st["expect"])):
            raise ManifestError(f"step {i}: expect must look like '== 1', '< 50' or '< $saved' "
                                f"(got {st['expect']!r})")
        if "save" in st and not NAME_RE.match(str(st["save"])):
            raise ManifestError(f"step {i}: save name must be a word")
        if "expect" not in st and "save" not in st:
            raise ManifestError(f"step {i}: a check needs 'expect' (or 'save' to keep the value)")
    for k in ("count",):
        if k in st:
            st[k] = int(st[k])
    return st


def parse_plan(plan) -> dict:
    """Normalise a test_plan (dict with cell/steps, or a bare list of steps)."""
    if plan is None or plan == [] or plan == {}:
        return {"cell": None, "steps": [], "notes": []}
    if isinstance(plan, list):
        if all(isinstance(x, str) for x in plan):
            return {"cell": None, "steps": [], "notes": list(plan)}
        plan = {"steps": plan}
    if not isinstance(plan, dict):
        raise ManifestError("test_plan must be a mapping (cell, steps) or a list of steps")
    steps = [_one_step(i + 1, s) for i, s in enumerate(plan.get("steps") or [])]
    saved: set = set()
    for st in steps:
        if st["do"] == "check":
            m = EXPECT_RE.match(str(st.get("expect", "== 0")))
            if m and m.group(2).startswith("$") and m.group(2)[1:] not in saved:
                raise ManifestError(f"step {st['n']}: ${m.group(2)[1:]} is used before a check saves it")
            if st.get("save"):
                saved.add(st["save"])
    return {"cell": plan.get("cell"), "steps": steps, "notes": [str(n) for n in plan.get("notes") or []]}


# ---------------------------------------------------------------- forms
def console_id(fid: int) -> str:
    s = f"{fid:08X}"
    # an all-digit id with one E (e.g. 0001E500) reads as a number in the console: quote it
    return f'"{s}"' if re.fullmatch(r"\d+E\d+", s) else s


class FormTable:
    """Resolves step names to console FormIDs in the test load order.

    names: EditorID -> (owner plugin, FormID as stored in that plugin, record type)
    """

    def __init__(self, load_order: list[str], plugin_masters: dict[str, list[str]]):
        self.load_order = list(load_order)
        self.index = {p.lower(): i for i, p in enumerate(load_order)}
        self.masters = {k.lower(): v for k, v in plugin_masters.items()}
        self.names: dict[str, tuple[str, int, str]] = {}

    def add_plugin_records(self, plugin: str, records) -> None:
        for edid, fid, sig in records:
            if edid:
                self.names.setdefault(edid.lower(), (plugin, fid, sig))

    def resolve_fid(self, plugin: str, fid: int) -> int:
        """FormID as stored in `plugin` -> console FormID in the test load order."""
        masters = self.masters.get(plugin.lower(), [])
        hi = fid >> 24
        owner = masters[hi] if hi < len(masters) else plugin
        if owner.lower() not in self.index:
            raise ManifestError(f"{owner} (owner of {fid:08X} in {plugin}) is not in the test load order")
        return (self.index[owner.lower()] << 24) | (fid & 0xFFFFFF)

    def form(self, name) -> str:
        s = str(name).strip()
        if s.lower() == "player":
            return "player"
        if ":" in s:                                  # Plugin.esp:00ABCD
            plugin, oid = s.rsplit(":", 1)
            if plugin.lower() not in self.index:
                raise ManifestError(f"{plugin} is not in the test load order")
            return console_id((self.index[plugin.lower()] << 24) | int(oid, 16))
        hit = self.names.get(s.lower())
        if hit:
            return console_id(self.resolve_fid(hit[0], hit[1]))
        if FORMID_RE.match(s) and not NAME_RE.match(s) or s.lower().startswith("0x"):
            return console_id(int(s, 16))             # already a console FormID
        raise ManifestError(f"unknown form {s!r}: not an EditorID in the test plugins, not Plugin.esp:ID, "
                            "not a hex FormID")


# ---------------------------------------------------------------- compile
RESULT_SAVE = "ForgePlaytestResult"
MAX_CHECKS = 32
SENTINEL = -99999                                      # "no value": set first, so a failed line can't pass


def _ref(name, forms: FormTable) -> str:
    """How a batch line names a reference: `player`, or the persistent reference's EditorID.

    Run 5: `<FormID>.Command` is not accepted ("Script command 0C00080A.GetAV not found").
    Run 6: `prid` selects the reference, but the next batch line doesn't use the selection
    ("Function 'GetActorValue' requires a reference"). Every console line is compiled as a small
    script, and scripts name persistent references by EditorID, so that is what works."""
    s = str(name).strip()
    if s.lower() in ("player", "playerref"):
        return "player"
    hit = forms.names.get(s.lower())
    if not hit or hit[2] not in ("REFR", "ACHR", "ACRE"):
        raise ManifestError(f"{s!r} is not a placed reference with an EditorID in the test plugins "
                            "(console lines can only name persistent references by EditorID)")
    return s


def _target(name, forms: FormTable) -> str:
    """A parameter that is a reference if it can be, else a form (FormID)."""
    try:
        return _ref(name, forms)
    except ManifestError:
        return forms.form(name)


def _line(st: dict, forms: FormTable) -> list[str]:
    op = st["do"]
    if op == "cast":
        return [f"{_ref(st.get('caster', 'player'), forms)}.cast {forms.form(st['spell'])} {_target(st['target'], forms)}"]
    if op == "spawn":
        return [f"{_ref(st.get('at', 'player'), forms)}.placeatme {forms.form(st['form'])} {st.get('count', 1)}"]
    if op == "moveto":
        return [f"player.moveto {_target(st['to'], forms)}"]
    if op == "weather":
        return [f"fw {forms.form(st['form'])}"]
    if op == "console":
        return [st["command"]]
    ref = _ref(st.get("ref", "player"), forms)
    if op in ("additem", "removeitem"):
        return [f"{ref}.{op} {forms.form(st['form'])} {st.get('count', 1)}"]
    if op == "equip":
        return [f"{ref}.equipitem {forms.form(st['form'])}"]
    if op == "addspell":
        return [f"{ref}.addspell {forms.form(st['form'])}"]
    if op in ("setav", "modav"):
        return [f"{ref}.{op} {st['av']} {st['value']}"]
    if op == "check":
        args = " ".join(_arg(a, forms) for a in st["args"])
        return [f"{ref}.{st['fn']} {args}".rstrip()]
    raise ManifestError(f"cannot compile {op}")


def _arg(a: str, forms: FormTable) -> str:
    """Check arguments: actor value names / numbers stay as written, form names resolve."""
    if re.fullmatch(r"[-+]?\d+(\.\d+)?", a):
        return a
    hit = forms.names.get(a.lower())
    if hit and hit[2] == "CELL":
        return a                                       # GetInCell & co. take the cell's EditorID
    if hit and hit[2] in ("REFR", "ACHR", "ACRE"):
        return a                                       # references by EditorID
    try:
        return forms.form(a)
    except ManifestError:
        return a                                       # e.g. an actor value name (Health)


def run_stamp(run_id: str) -> int:
    """A number for the run, exact in a float global (< 2^24)."""
    import zlib
    return zlib.crc32(run_id.encode()) % 9_000_000 + 1


def marker(*parts) -> str:
    return "FORGE|" + "|".join(str(p) for p in parts)


def _say(text: str) -> list[str]:
    """On screen (printc) and into the log file (xOBSE PrintToFile; run 6: scof doesn't exist)."""
    return [f'printc "{text}"', f'PrintToFile "{LOG_NAME}" "{text}%r"']           # %r: OBSE line break


def _value(global_: str, label: str, expr: str) -> list[str]:
    """Store a value in a result global (also read back from the result save) and log it."""
    return [f"set {global_} to {SENTINEL}", f"set {global_} to {expr}",
            f'PrintToFile "{LOG_NAME}" "{label} >> %.2f%r" {global_}']


def build(plan: dict, forms: FormTable, *, location: dict, bring: list, plugin: str, spec: str | None,
          run_id: str | None = None) -> dict:
    """Return the manifest dict, including the compiled batch chunks.

    location: vanilla.Location.to_dict(): boot command, optional moveto ref, cell/world for the probe.
    bring: [(ref EditorID, dx, dy, dz)] test actors moved next to the player.
    """
    run_id = run_id or secrets.token_hex(4)
    chunks: list[dict] = [{"wait_before": 0.0, "lines": []}]
    stamp = run_stamp(run_id)
    head = _say(marker("BEGIN", run_id)) + [f"set ForgeRunStamp to {stamp}"]
    if location.get("moveto"):
        head.append(f"player.moveto {location['moveto']}")
    if location.get("setpos"):
        x, y, z, heading = location["setpos"]
        head += [f"player.setpos x {x:.1f}", f"player.setpos y {y:.1f}", f"player.setpos z {z + 8:.1f}",
                 f"player.setangle z {math.degrees(heading) % 360:.1f}"]
    for ref, dx, dy, dz in bring:
        head.append(f"{_ref(ref, forms)}.moveto player {dx} {dy} {dz}")
    head += _say(marker("CELL", location.get("cell_edid") or location.get("world_edid")))
    probe = (f"GetInCell {location['cell_edid']}" if location.get("cell_edid")
             else f"GetInWorldspace {location['world_edid']}")
    head += _value("ForgeRInPlace", probe.split()[0], f"player.{probe}")
    chunks[0]["lines"] += head
    result_globals: dict[str, str] = {}
    checks = [st for st in plan["steps"] if st["do"] == "check"]
    if len(checks) > MAX_CHECKS:
        raise ManifestError(f"at most {MAX_CHECKS} checks per run (the result globals); got {len(checks)}")
    for st in plan["steps"]:
        if st["do"] == "wait":
            chunks.append({"wait_before": st["seconds"], "lines": []})
            continue
        lines = _line(st, forms)
        st["console"] = " | ".join(lines)
        if st["do"] == "check":
            g = f"ForgeR{len(result_globals) + 1:02d}"
            result_globals[str(st["n"])] = g
            lines = _value(g, st["fn"], lines[0])
        chunks[-1]["lines"] += _say(marker("STEP", st["n"], st["do"])) + lines
    chunks[-1]["lines"] += _say(marker("END", run_id)) + [
        f"set ForgeRunDone to {stamp}", f"save {RESULT_SAVE}",
        'message "Forge: checks done. Play on, quit the game when you are ready."']
    for i, c in enumerate(chunks, 1):
        c["file"] = f"{BATCH_PREFIX}{i}.txt"
        c["command"] = f"bat {BATCH_PREFIX}{i}"
    return {
        "forge_playtest": MANIFEST_VERSION, "run_id": run_id, "spec": spec, "plugin": plugin,
        "cell": location.get("cell_edid") or location.get("world_edid"), "location": location,
        "load_order": forms.load_order, "log": LOG_NAME, "steps": plan["steps"], "notes": plan.get("notes", []),
        "results": {"save": RESULT_SAVE, "stamp": stamp, "probe": probe, "checks": result_globals},
        "chunks": chunks,
    }


def write_batches(manifest: dict, dest: Path) -> list[Path]:
    out = []
    for c in manifest["chunks"]:
        p = dest / c["file"]
        p.write_bytes(("\r\n".join(c["lines"]) + "\r\n").encode("cp1252"))
        out.append(p)
    return out


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(manifest: dict, path: Path) -> Path:
    path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return path
