"""Vanilla (CS) script function names from Vim's obse.vim syntax file (Vim licence).

Only the names in the `csFunction` keyword group are taken: the vanilla command set.
"""

from __future__ import annotations

import re
from pathlib import Path

URL = "https://github.com/vim/vim/blob/master/runtime/syntax/obse.vim"


def vanilla_names(vim_file: Path) -> list[str]:
    lines = Path(vim_file).read_text("utf-8", "replace").splitlines()
    out, on = [], False
    for ln in lines:
        if re.match(r"\s*syn keyword csFunction\b", ln):
            on = True
            continue
        if on:
            m = re.match(r"\s*\\\s+(\w+)", ln)
            if not m:
                break
            out.append(m.group(1))
    return out
