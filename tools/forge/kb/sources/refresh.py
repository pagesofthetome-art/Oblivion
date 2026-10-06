"""Regenerate kb/data/*.json from upstream sources (dev-time; needs local copies).

    forge kb refresh-sources --xobse <xOBSE clone> --xedit <wbDefinitionsTES4.pas> --vim <obse.vim>

Upstream copies are untrusted data: they are parsed as text, never executed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from forge.kb.sources import vim, xedit, xobse

DATA = Path(__file__).resolve().parents[1] / "data"


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _dump(name: str, obj) -> Path:
    p = DATA / name
    if isinstance(obj, list):    # one item per line: compact, but diffs stay readable
        text = "[\n" + ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in obj) + "\n]\n"
    else:
        text = json.dumps(obj, indent=1, ensure_ascii=False) + "\n"
    p.write_text(text, encoding="utf-8")
    return p


def refresh(xobse_root: Path | None, xedit_pas: Path | None, vim_file: Path | None) -> dict:
    DATA.mkdir(exist_ok=True)
    prov_path = DATA / "provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.is_file() else {}
    counts = {}
    if xobse_root:
        rows = xobse.extract(Path(xobse_root))
        _dump("obse_functions.json", rows)
        commit = ""
        head = Path(xobse_root) / ".git" / "HEAD"
        if head.is_file():
            ref = head.read_text().strip()
            commit = (Path(xobse_root) / ".git" / ref[5:]).read_text().strip() if ref.startswith("ref: ") and \
                (Path(xobse_root) / ".git" / ref[5:]).is_file() else ref
        prov["obse_functions.json"] = {"source": xobse.REPO_URL, "commit": commit,
                                       "command_table_sha256": _sha(Path(xobse_root) / "obse/obse/CommandTable.cpp"),
                                       "note": "Signatures only; help strings not exported."}
        counts["obse_functions"] = len(rows)
        _dump("param_types.json", xobse.param_type_ids(Path(xobse_root)))
    if xedit_pas or vim_file:
        names = vim.vanilla_names(vim_file) if vim_file else []
        conds = xedit.condition_functions(xedit_pas) if xedit_pas else []
        _dump("vanilla_functions.json", {"vim_names": names, "condition_functions": conds})
        counts["vanilla_names"] = len(names)
        counts["condition_functions"] = len(conds)
        if vim_file:
            prov["vanilla_functions.json/vim"] = {"source": vim.URL, "sha256": _sha(vim_file),
                                                  "license": "Vim licence"}
    if xedit_pas:
        common = Path(xedit_pas).with_name("wbDefinitionsCommon.pas")   # helper functions (wbVec3PosRot, ...)
        recs = xedit.extract(xedit_pas, common if common.is_file() else None)
        _dump("record_schemas.json", recs)
        prov["record_schemas.json"] = {"source": xedit.URL, "sha256": _sha(xedit_pas), "license": xedit.LICENSE}
        if common.is_file():
            prov["record_schemas.json"]["common_source"] = xedit.COMMON_URL
            prov["record_schemas.json"]["common_sha256"] = _sha(common)
        counts["record_types"] = len(recs)
    _dump("provenance.json", prov)
    return counts
