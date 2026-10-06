"""The playtest command group for forge: playtest, test, preview.

    forge playtest <spec.yaml | Mod.esp> [--cell arena|street|open] [--manifest F] [--dry-run]
    forge playtest restore | status | cells | make-save | find <text>
    forge test [RUN_DIR] [--log forge_test.log --manifest playtest_manifest.json] [--json]
    forge preview <spec.yaml | Mod.esp | cells> [--cell NAME] [--out page.html] [--open]

Exit codes: 0 pass / ok, 1 usage or setup error, 2 checks failed (or no checks, froze, not run).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playtest import manifest as mf, profile, testlog

ACTIONS = {"restore", "status", "cells", "make-save", "find"}


def register(sub) -> None:
    p = sub.add_parser("playtest", help="quick-boot the test game into a test cell and run the checks")
    p.add_argument("target", help="spec (.yaml/.json), plugin (.esp/.esm), or restore | status | cells | "
                                  "make-save | find")
    p.add_argument("text", nargs="?", help="for find: text to search vanilla cells and map markers for")
    p.add_argument("--cell", help="arena | street | open | <vanilla InteriorEditorID> | marker:<Map marker> | "
                                  "cow:<World>:<x>:<y> (default: the spec's test_plan.cell, else arena)")
    p.add_argument("--manifest", help="test plan file (YAML/JSON) instead of the spec's test_plan")
    p.add_argument("--kill-on-freeze", action="store_true",
                   help="close a frozen test game after --hang-seconds (default: never close the game)")
    p.add_argument("--dry-run", action="store_true", help="build, swap and stage the profile, then restore; no launch")
    p.add_argument("--no-companion", action="store_true", help="do not start Controller\\oblivion_controller.py")
    p.add_argument("--bright", action="store_true", help="full-bright lighting in the test game (dark places)")
    p.add_argument("--boot-timeout", type=float, default=120.0)
    p.add_argument("--hang-seconds", type=float, default=20.0, help="confirmed freeze this long = kill the test game")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_playtest)
    p = sub.add_parser("test", help="read forge_test.log of a playtest run and print the report")
    p.add_argument("run_dir", nargs="?", help="a forge-builds\\playtest\\runs\\<run> folder (default: the last run)")
    p.add_argument("--log")
    p.add_argument("--manifest")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_test)
    p = sub.add_parser("preview", help="browser preview of the test cell or a mod's placed objects")
    p.add_argument("target", help="spec, plugin, or 'cells' for the test cells")
    p.add_argument("--cell", help="cell to start in (arena/street/open or a cell EditorID)")
    p.add_argument("--out", help="HTML file to write (default forge-builds\\playtest\\preview\\<name>.html)")
    p.add_argument("--open", action="store_true", help="open it in the default browser")
    p.set_defaults(fn=cmd_preview)


def cmd_playtest(a) -> int:
    from playtest import runner
    m = profile.Machine.detect()
    if a.target in ACTIONS:
        if a.target == "restore":
            notes = profile.restore(m)
            print("restored the real Plugins.txt and Oblivion.ini" if notes else "nothing to restore")
            return 0
        if a.target == "status":
            st = profile.status(m)
            st["sha256"] = {str(f): (profile.sha256(f) if f.is_file() else None) for f in (m.plugins_txt, m.ini)}
            if a.json:
                print(json.dumps(st, indent=1))
            else:
                print("test profile is ON (journal open since " + str(st["created"]) + ")" if st["open"] else
                      "test profile is off; the real Plugins.txt and Oblivion.ini are in place")
                for f, h in st["sha256"].items():
                    print(f"  sha256 {h or 'missing'}  {f}")
            return 0
        if a.target == "find":
            if not a.text:
                print("usage: forge playtest find <text>", file=sys.stderr)
                return 1
            from playtest import vanilla
            hits = vanilla.search(a.text, runner.vanilla_index(m))
            print("\n".join(hits) if hits else f"nothing matches {a.text!r}")
            return 0
        if a.target == "make-save":
            res = runner.make_save(runner.Options(cell=a.cell, boot_timeout=a.boot_timeout,
                                                  companion=not a.no_companion, bright=a.bright), m)
            print(json.dumps(res, indent=1) if a.json else
                  (f"test save made: {res['save']}" if res.get("made") else f"no save made: {res.get('error')}"))
            return 0 if res.get("made") else 2
        esp, lay = runner.testcells_build(m)
        print(f"{esp}\n  actors: " + ", ".join(lay["refs"]) +
              (f"\n  look like: {', '.join(lay['appearance'])}" if lay.get("appearance") else
               "\n  look: plain (no Oblivion.esm in the test game)"))
        try:
            from playtest import vanilla
            idx = runner.vanilla_index(m)
            for key in ("arena", "street", "open"):
                try:
                    loc = vanilla.resolve(key, idx)
                    print(f"  {key:<7} {loc.boot:<40} {loc.detail}")
                except vanilla.VanillaError as e:
                    print(f"  {key:<7} NOT FOUND: {e}")
        except runner.PlaytestError as e:
            print(f"  locations: {e}")
        return 0
    opts = runner.Options(cell=a.cell, manifest=Path(a.manifest) if a.manifest else None, dry_run=a.dry_run,
                          kill_on_freeze=a.kill_on_freeze, boot_timeout=a.boot_timeout, hang_seconds=a.hang_seconds,
                          companion=not a.no_companion, bright=a.bright,
                          log=(lambda s: None) if a.json else print)
    try:
        res = runner.run(a.target, opts, m)
    except (runner.PlaytestError, profile.ProfileError, mf.ManifestError, ValueError) as e:  # noqa: B014
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(res, indent=1) if a.json else _report(res))
    return 0 if res["verdict"] in ("PASS", "DRY-RUN") else 2


def _report(res: dict) -> str:
    text = testlog.report_text(res) if "results" in res else f"playtest: {res['verdict']}"
    rc = res.get("restore_check", {})
    text += "\n  restore: " + ", ".join(f"{k} {'identical' if v['same'] else 'DIFFERENT'} "
                                         f"(sha256 {str(v['after'])[:12]})" for k, v in rc.items())
    text += f"\n  run: {res.get('run_dir')}"
    return text


def cmd_test(a) -> int:
    m = profile.Machine.detect()
    restored = profile.restore(m)
    if restored:
        print("note: finished restoring an earlier playtest that did not close cleanly")
    if a.log or a.manifest:
        if not (a.log and a.manifest):
            print("error: --log and --manifest go together", file=sys.stderr)
            return 1
        man, log, extra = mf.load(Path(a.manifest)), Path(a.log), {}
    else:
        run = Path(a.run_dir) if a.run_dir else None
        if run is None:
            last = m.state_dir / "last-run.txt"
            if not last.is_file():
                print("error: no playtest run yet; run forge playtest first", file=sys.stderr)
                return 1
            run = Path(last.read_text(encoding="utf-8").strip())
        if not (run / "playtest_manifest.json").is_file():
            print(f"error: {run} has no playtest_manifest.json", file=sys.stderr)
            return 1
        man = mf.load(run / "playtest_manifest.json")
        log = run / mf.LOG_NAME
        extra = {}
        if (run / "result.json").is_file():
            old = json.loads((run / "result.json").read_text(encoding="utf-8"))
            extra = {k: old[k] for k in ("boot_seconds", "froze", "restore_check") if k in old}
    res = testlog.evaluate(man, log if log.is_file() else None, extra)
    print(json.dumps(res, indent=1) if a.json else testlog.report_text(res))
    return 0 if res["verdict"] == "PASS" else 2


def cmd_preview(a) -> int:
    from playtest import preview, runner, vanilla
    m = profile.Machine.detect()
    out_dir = m.state_dir / "preview"
    try:
        if a.target == "cells":
            idx = runner.vanilla_index(m)
            loc = vanilla.resolve(a.cell or "arena", idx)
            if not loc.cell_edid:
                raise preview.PreviewError("the preview draws vanilla interiors only; pick one with --cell <EditorID>")
            c = next(c for c in idx["interiors"] if c["edid"] == loc.cell_edid)
            data = preview.extract_vanilla_cell(m.data / "Oblivion.esm", c["fid"], c["edid"], c["name"])
            title = f"{c['name'] or c['edid']} (vanilla)"
            out = Path(a.out) if a.out else out_dir / f"{c['edid']}.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(preview.render(data, title, f"Vanilla interior {c['edid']} from Oblivion.esm, "
                                          "boxes sized from each object's bound radius."), encoding="utf-8")
            print(f"preview {out}")
            if a.open:
                import webbrowser
                webbrowser.open(out.resolve().as_uri())
            return 0
        t = runner.resolve_target(a.target, runner.Options(cell=a.cell), m)
        plugin, title = t.plugin, t.spec_name or t.plugin.stem
        out = Path(a.out) if a.out else out_dir / f"{Path(title).stem.replace(' ', '-')}.html"
        page = preview.build_page(plugin, out, title=title, first_cell=a.cell)
    except (preview.PreviewError, runner.PlaytestError, vanilla.VanillaError, ValueError, StopIteration) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"preview {page}")
    if a.open:
        import webbrowser
        webbrowser.open(page.resolve().as_uri())
    return 0

