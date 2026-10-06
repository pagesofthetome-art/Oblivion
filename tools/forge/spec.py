"""Mod spec: the single file that drives `forge build`.

A spec is YAML (needs PyYAML) or JSON. Shape, version 1:

    forge_spec: 1
    name: my-mod                     # slug, used for the build folder
    kind: merge_patch                # merge_patch (phase 1); plugin (phase 3: records + scripts)
    intent: "What the player should get, in plain words."
    vars: {STEAM_DATA: "C:/..."}     # ${STEAM_DATA} anywhere in the spec; ${env:NAME} reads the environment
    output: {plugin: X.esp, dir: ../forge-builds/my-mod}
    inputs:                          # provenance + permission for every external input
      - {id: oblivion-esm, path: ..., permission: REQUIRES_ORIGINAL_DOWNLOAD}
    dependencies: {...}  compatibility_targets: [...]  test_plan: [...]
    records: []  scripts: []  assets: []  placements: []   # used by kind: plugin (phase 3)
    merge_patch: {...}               # kind-specific section, see KIND_SECTIONS
    expect: {sha256: ..., same_records_as: path/to/old.esp}

Relative paths resolve against the spec file's folder. Override vars on the
command line with `--set NAME=VALUE`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

SPEC_VERSION = 1
KINDS = {
    "merge_patch": "implemented",
    "plugin": "implemented",     # records (3a); scripts (3b, forge's own compiler)
}
PERMISSIONS = {
    "PROJECT_OWNED", "CAN_DISTRIBUTE", "PATCH_ONLY", "REQUIRES_ORIGINAL_DOWNLOAD",
    "PRIVATE_RESEARCH_ONLY", "UNKNOWN_PERMISSION",
}
# capabilities each kind needs (checked against the registry before building)
KIND_CAPS = {
    "merge_patch": ["record.read", "record.merge", "record.write", "record.lint", "build.log", "package.vortex"],
    "plugin": ["record.read", "record.encode", "record.write", "record.lint", "build.log", "package.vortex"],
}
VAR_RE = re.compile(r"\$\{([^}]+)\}")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SpecError(ValueError):
    pass


@dataclass
class Spec:
    path: Path
    raw: dict                 # as written (after var substitution)
    base: Path                # folder relative paths resolve against
    sha256: str               # hash of the spec file bytes
    vars: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.raw["name"]

    @property
    def kind(self) -> str:
        return self.raw["kind"]

    def section(self, key: str) -> dict:
        return self.raw.get(key) or {}

    def resolve(self, p: str | os.PathLike | None) -> Path | None:
        if p is None or p == "":
            return None
        q = Path(os.path.expanduser(str(p)))
        return q if q.is_absolute() else (self.base / q).resolve()

    def output_dir(self, override: Path | None = None) -> Path:
        if override:
            return Path(override).resolve()
        d = self.section("output").get("dir")
        return self.resolve(d) if d else (repo_root() / "forge-builds" / self.name)

    @property
    def output_plugin(self) -> str:
        return self.section("output")["plugin"]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as e:
            raise SpecError("YAML specs need PyYAML: python -m pip install pyyaml "
                            "(or write the spec as .json)") from e
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SpecError(f"{path.name}: top level must be a mapping")
    return data


def _subst(obj, vars_: dict, missing: set):
    if isinstance(obj, str):
        def rep(m):
            k = m.group(1)
            if k.startswith("env:"):
                v = os.environ.get(k[4:])
            else:
                v = vars_.get(k)
            if v is None:
                missing.add(k)
                return m.group(0)
            return str(v)
        return VAR_RE.sub(rep, obj)
    if isinstance(obj, list):
        return [_subst(x, vars_, missing) for x in obj]
    if isinstance(obj, dict):
        return {_subst(k, vars_, missing): _subst(v, vars_, missing) for k, v in obj.items()}
    return obj


def load(path: str | os.PathLike, overrides: dict | None = None) -> Spec:
    path = Path(path).resolve()
    if not path.is_file():
        raise SpecError(f"spec not found: {path}")
    data = _read(path)
    vars_ = {k: str(v) for k, v in (data.get("vars") or {}).items()}
    vars_.update(overrides or {})
    # vars may reference env and each other (one level)
    missing: set = set()
    vars_ = {k: _subst(v, vars_, set()) for k, v in vars_.items()}
    vars_ = {k: _subst(v, vars_, missing) for k, v in vars_.items()}   # second pass: vars that use vars
    body = _subst({k: v for k, v in data.items() if k != "vars"}, vars_, missing)
    body["vars"] = vars_
    spec = Spec(path=path, raw=body, base=path.parent,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), vars=vars_)
    spec.raw["_unresolved_vars"] = sorted(missing)
    return spec


def validate(spec: Spec) -> list[str]:
    """Return a list of problems (empty = valid). Does not touch the file system."""
    r = spec.raw
    errs = []
    if r.get("forge_spec") != SPEC_VERSION:
        errs.append(f"forge_spec must be {SPEC_VERSION}")
    name = r.get("name")
    if not isinstance(name, str) or not SLUG_RE.match(name):
        errs.append("name must be a lower-case slug (a-z, 0-9, . _ -)")
    kind = r.get("kind")
    if kind not in KINDS:
        errs.append(f"kind must be one of {sorted(KINDS)}")
    if not str(r.get("intent") or "").strip():
        errs.append("intent is required (what the player should see, hear and experience)")
    out = r.get("output") or {}
    plugin = out.get("plugin", "")
    if not plugin or Path(plugin).suffix.lower() not in (".esp", ".esm"):
        errs.append("output.plugin must name an .esp or .esm")
    for i, inp in enumerate(r.get("inputs") or []):
        if not isinstance(inp, dict) or "id" not in inp:
            errs.append(f"inputs[{i}] needs an id")
            continue
        if inp.get("permission") not in PERMISSIONS:
            errs.append(f"inputs[{inp['id']}].permission must be one of {sorted(PERMISSIONS)}")
        if inp.get("permission") == "PRIVATE_RESEARCH_ONLY" and inp.get("role") != "reference":
            errs.append(f"inputs[{inp['id']}] is PRIVATE_RESEARCH_ONLY: it may only be a reference "
                        "(role: reference), never built into the output")
    if r.get("_unresolved_vars"):
        errs.append("unresolved variables: " + ", ".join(r["_unresolved_vars"])
                    + " (set them under vars:, in the environment, or with --set NAME=VALUE)")
    if kind == "merge_patch":
        mp = r.get("merge_patch") or {}
        for k in ("config", "vanilla", "installed_dir", "plugins_txt"):
            if not mp.get(k):
                errs.append(f"merge_patch.{k} is required")
    if kind == "plugin":
        recs = r.get("records")
        if recs is not None and not isinstance(recs, list):
            errs.append("records must be a list")
        for i, rec in enumerate(recs or []):
            if not isinstance(rec, dict) or not rec.get("sig") or not rec.get("edid"):
                errs.append(f"records[{i}] needs sig and edid")
        scr = r.get("scripts")
        if scr is not None and not isinstance(scr, list):
            errs.append("scripts must be a list")
        for i, sc in enumerate(scr or []):
            if not isinstance(sc, dict) or not sc.get("edid"):
                errs.append(f"scripts[{i}] needs edid")
            elif not (sc.get("source") or sc.get("file")):
                errs.append(f"scripts[{i}] ({sc['edid']}) needs source: or file:")
    return errs


def ids_path(spec: "Spec") -> Path:
    """The append-only EditorID -> FormID map for a plugin spec."""
    p = spec.raw.get("ids")
    return spec.resolve(p) if p else spec.path.with_name(spec.path.stem + ".ids.json")


def required_caps(spec: Spec) -> list[str]:
    caps = list(KIND_CAPS.get(spec.kind, []))
    if spec.kind == "plugin" and spec.raw.get("scripts"):
        caps += ["script.compile"]
    return caps


def merge_config(spec: Spec) -> tuple[dict, Path | None]:
    """The build_cfg dict (inline or from file) with relative paths resolved."""
    mp = spec.section("merge_patch")
    c = mp.get("config")
    if isinstance(c, dict):
        cfg, cfg_path = copy.deepcopy(c), None
    else:
        cfg_path = spec.resolve(c)
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    work = spec.resolve(mp.get("workdir") or ".")
    # relative paths inside build_cfg were relative to the legacy script's working folder
    cfg["extra_paths"] = [str(_under(work, p)) for p in cfg.get("extra_paths", [])]
    for job in cfg.get("world_edits", []):
        if job.get("type") == "port_patch":
            job["path"] = str(_under(work, job["path"]))
    return cfg, cfg_path


def _under(base: Path, p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else (base / q)
