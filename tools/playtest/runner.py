"""forge playtest: real Oblivion, minimal load order, straight into a vanilla cell, checks, restore.

Boot (Yuri presses one button, Continue; everything else is automatic):
  1. A test save must exist (made once with `forge playtest make-save`); otherwise forge stops
     before launching.
  2. obse_loader.exe in the clean GOG copy with the test profile (intro videos off).
  3. Main menu: forge beeps and Yuri presses Cross on CONTINUE (forge never types into the main
     menu). After the load, the location's boot command (`coc <Interior>` / `cow <World> x y`) runs
     from the in-game console.
  4. `bat fpt1`, `bat fpt2`... (one per wait). The first batch moves the test actors next to the
     player and logs everything to forge_test.log.
  5. Forge never closes the game. When its part is done it beeps and says so (in the console window
     and in game); Yuri plays on and quits with the pad. Restore runs after the process has exited.

Every run leaves a boot trace (boot-trace.jsonl: menu stack, menu mode, focus, twice a second)
and screenshots of each boot step (shots\\*.png) in its run folder, so a failure can be read
afterwards. While the game runs the driver watches for freezes (Controller\\oblivion_freeze.py
plus Windows' "not responding"; reported after --hang-seconds, killed only with --kill-on-freeze) and auto-dismisses the Persuasion
tutorial page that ignores the controller.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from playtest import manifest as mf, platform as plat, profile, testcells, testlog, vanilla

TOOLS = Path(__file__).resolve().parents[1]
HUD = {1004, 1005, 1006, 1010, 1045}
CHARGEN = {1029, 1030, 1031, 1032, 1033, 1036, 1051}     # birthsign, class, attributes, skills, race/name
SAVE_NAME = "ForgePlaytestBase"
QUIT_NOTE = "Forge: done. Quit the game when you are ready."


class PlaytestError(RuntimeError):
    pass


@dataclass
class Options:
    cell: str | None = None
    manifest: Path | None = None
    dry_run: bool = False                 # build + swap + stage, then restore at once (no launch)
    kill_on_freeze: bool = False          # Yuri's rule: forge never closes the game (opt-in for freezes only)
    boot_timeout: float = 120.0
    hang_seconds: float = 20.0
    companion: bool = True
    bright: bool = False                  # bFullBrightLighting=1 in the test ini (dark places)
    results: str | None = None            # "save": result-save globals only, no PrintToFile (beats the plan)
    log: object = print


@dataclass
class Target:
    plugin: Path | None
    plan: dict
    spec_name: str | None
    spec_path: Path | None = None


@dataclass
class Prepared:
    target: Target
    location: vanilla.Location
    active: list[str]
    stage: list[tuple[Path, Path | None, bytes | None]] = field(default_factory=list)
    layout: dict | None = None
    actors: dict | None = None                    # {"target": {...}, "caster": {...}} vanilla beggars


# ---------------------------------------------------------------- target
def resolve_target(path: str | Path, opts: Options, m: profile.Machine) -> Target:
    p = Path(path).resolve()
    if p.suffix.lower() in (".esp", ".esm"):
        if not p.is_file():
            raise PlaytestError(f"plugin not found: {p}")
        plan_src = _read_any(opts.manifest) if opts.manifest else None
        if plan_src is None:
            for side in (p.with_suffix(".playtest.yaml"), p.with_suffix(".playtest.json")):
                if side.is_file():
                    plan_src = _read_any(side)
                    break
        plan = mf.parse_plan((plan_src or {}).get("test_plan", plan_src))
        return Target(p, plan, None)
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from forge import spec as specmod
    s = specmod.load(p)
    errs = specmod.validate(s)
    if errs:
        raise PlaytestError("spec invalid: " + "; ".join(errs))
    pt = s.section("playtest")
    plugin = s.resolve(pt["plugin"]) if pt.get("plugin") else s.output_dir() / s.output_plugin
    if pt.get("build_example"):
        from playtest import examples
        builder = examples.BUILDERS.get(pt["build_example"])
        if not builder:
            raise PlaytestError(f"unknown playtest.build_example {pt['build_example']!r}")
        plugin = builder(m.state_dir / "examples" / s.output_plugin)
    if not plugin.is_file():
        raise PlaytestError(f"{plugin} not found: run `forge build {p}` first")
    raw_plan = _read_any(opts.manifest).get("test_plan") if opts.manifest else s.raw.get("test_plan")
    return Target(plugin, mf.parse_plan(raw_plan), s.name, p)


def _read_any(path: Path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml
        return yaml.safe_load(text) or {}
    return json.loads(text)


# ---------------------------------------------------------------- prepare
def _masters(plugin: Path) -> list[str]:
    import tes4_plugin as tp
    return list(tp.read_header(plugin).masters)


def _find_master(name: str, near: Path, m: profile.Machine) -> Path | None:
    for d in [near, *m.master_dirs]:
        p = d / name
        if p.is_file():
            return p
    return None


def testcells_build(m: profile.Machine) -> tuple[Path, dict]:
    """ForgeTestCells.esp (test actors, looks copied from the test game's Oblivion.esm)."""
    esm = m.data / "Oblivion.esm"
    esp, lj = testcells.write(m.state_dir / "testcells", esm if esm.is_file() else None)
    return esp, json.loads(lj.read_text(encoding="utf-8"))


def vanilla_index(m: profile.Machine) -> dict:
    esm = m.data / "Oblivion.esm"
    if not esm.is_file():
        raise PlaytestError(f"{esm} not found")
    return vanilla.load_index(esm, m.state_dir / "vanilla-index.json")


TEST_ROLES = {"testtarget", "testcaster"}


def uses_test_actors(plan: dict) -> bool:
    """Does any step name TestTarget or TestCaster (in any field, or inside a console line)?"""
    def walk(v):
        if isinstance(v, dict):
            return any(walk(x) for x in v.values())
        if isinstance(v, (list, tuple)):
            return any(walk(x) for x in v)
        return isinstance(v, str) and any(r in v.lower() for r in TEST_ROLES)
    return walk(plan.get("steps") or [])


def prepare(t: Target, opts: Options, m: profile.Machine) -> Prepared:
    data = m.data
    try:
        idx = vanilla_index(m)
        loc = vanilla.resolve(opts.cell or t.plan.get("cell"), idx)
        # the beggars are looked up only when the plan uses them (a self-cast test needs no actors)
        actors = vanilla.test_actors(idx) if uses_test_actors(t.plan) else None
    except vanilla.VanillaError as e:
        raise PlaytestError(str(e)) from None
    tc_esp, lay = testcells_build(m)
    active = ["Oblivion.esm"] + [d for d in profile.OFFICIAL_DLC if (data / d).is_file()]
    stage: list[tuple[Path, Path | None, bytes | None]] = []
    order: list[str] = []

    def need(plugin: Path):
        for name in _masters(plugin):
            if name.lower() in (x.lower() for x in active + order):
                continue
            src = data / name if (data / name).is_file() else _find_master(name, plugin.parent, m)
            if src is None:
                raise PlaytestError(f"master {name} of {plugin.name} not found in the test game, next to the "
                                    "plugin, or in the play copy's Data")
            need(src)
            order.append(name)
            if not (data / name).is_file():
                stage.append((data / name, src, None))

    if t.plugin is not None:
        if t.plugin.name.lower() == testcells.PLUGIN_NAME.lower():
            raise PlaytestError("pick a mod to test, not ForgeTestCells.esp itself")
        need(t.plugin)
        active += order + [t.plugin.name]
        if (data / t.plugin.name).resolve() != t.plugin.resolve():
            stage.append((data / t.plugin.name, t.plugin, None))
    active.append(testcells.PLUGIN_NAME)
    stage.append((data / testcells.PLUGIN_NAME, tc_esp, None))
    return Prepared(t, loc, active, stage, lay, actors)


def _forms(prep: Prepared, m: profile.Machine, lo: list[str]) -> mf.FormTable:
    import tes4_plugin as tp
    ours = {testcells.PLUGIN_NAME.lower()}
    if prep.target.plugin is not None:
        ours.add(prep.target.plugin.name.lower())
    masters, recs = {}, {}
    for name in lo:
        p = m.data / name
        if name.lower() in ours:
            pl = tp.load(p)
            masters[name] = list(pl.masters)
            recs[name] = [(r.editor_id, r.form_id, r.sig) for r in pl.records]
        else:
            masters[name] = list(tp.read_header(p).masters)
    ft = mf.FormTable(lo, masters)
    names = ([prep.target.plugin.name] if prep.target.plugin is not None else []) + [testcells.PLUGIN_NAME]
    for name in names:                                  # the mod's names win
        ft.add_plugin_records(name, recs.get(name, []))
    for role, a in (prep.actors or {}).items():
        ft.alias("Test" + role.capitalize(), a["edid"], "Oblivion.esm", int(a["ref"], 16))
    return ft


# ---------------------------------------------------------------- run
def preflight(m: profile.Machine, p: plat.Platform) -> list[str]:
    m.check_safe()
    running = [(pid, n) for pid, n, _ in p.processes() if n.lower() in profile.GAME_PROCESSES]
    if running:
        raise PlaytestError("Oblivion or the Construction Set is running (" + ", ".join(f"{n} pid {pid}" for pid, n in running)
                            + "). Playtest never acts while a game is open; close it and try again.")
    notes = []
    if not (m.game_dir / "obse_loader.exe").is_file():
        raise PlaytestError(f"xOBSE not found in the test game: {m.game_dir / 'obse_loader.exe'}")
    if not (m.data / "OBSE" / "Plugins" / "NorthernUI.dll").is_file():
        notes.append("NorthernUI is not installed in the test game, so the pad works only through the "
                     "controller companion. Install it there: py Controller\\install_northernui.py")
    if any(n.lower() == "discord.exe" for _, n, _ in p.processes()):
        notes.append("Discord is running: its in-game overlay pops up over the test game. Turn the overlay "
                     "off for Oblivion (Discord > Settings > Game Overlay).")
    return notes


def hashes(m: profile.Machine) -> dict:
    return {k: (profile.sha256(p) if p.is_file() else None) for k, p in (("plugins_txt", m.plugins_txt), ("ini", m.ini))}


class _Profile:
    """Swap the test profile in (journaled), stage files, and always restore + record hashes."""

    def __init__(self, m, p, log, run_dir):
        self.m, self.p, self.log, self.run_dir = m, p, log, run_dir

    def __enter__(self):
        m = self.m
        if profile.restore(m, log=self.log):
            self.log("finished restoring an earlier playtest that did not close cleanly")
        self.before = hashes(m)
        self.real_ini = m.ini.read_bytes() if m.ini.is_file() else b""
        self.sess = profile.Session(m, log=self.log)
        return self

    def apply(self, prep: Prepared, opts: Options) -> list[str]:
        m, sess = self.m, self.sess
        sess.begin()
        sess.swap_in(m.plugins_txt, profile.plugins_txt(prep.active))
        self.display = self._display(sess)
        sess.swap_in(m.ini, profile.test_ini(self.real_ini, profile.display_overrides(self.display["size"],
                                                                                      opts.bright)))
        # the pad should behave exactly as in the play setup: use its NorthernUI.ini for the run
        rel = Path("OBSE") / "Plugins" / "NorthernUI.ini"
        for play in m.play_dirs:
            src, dst = play / "Data" / rel, m.data / rel
            if src.is_file() and dst.is_file() and src.read_bytes() != dst.read_bytes():
                sess.swap_file(dst, src.read_bytes())
                self.log("using the play setup's NorthernUI.ini for this run (restored afterwards)")
                break
        shutil.copy2(m.plugins_txt, self.run_dir / "Plugins.test.txt")
        shutil.copy2(m.ini, self.run_dir / "Oblivion.test.ini")
        newest = max((m.data / n).stat().st_mtime for n in prep.active if (m.data / n).is_file())
        stamp = newest + 60
        for dest, src, data in prep.stage:
            mt = None
            if dest.suffix.lower() in (".esp", ".esm"):
                mt, stamp = stamp, stamp + 60                 # load after everything already there
            sess.stage(dest, data=data, src=src, mtime=mt)
        return profile.load_order(m.data, prep.active)

    def _display(self, sess) -> dict:
        """Pick the render size so the whole frame is on screen under Windows display scaling.

        Run 3: at 150 % scaling a DPI-unaware Oblivion.exe drew its 1920x1080 frame 1.5x larger
        (2/3 visible). If the play copy's Oblivion.exe carries a DPI compatibility flag, the test exe
        gets the same flag for the run (journaled) and renders at the physical size; otherwise the
        test renders at the logical size and Windows scales it up to fill the screen.
        """
        m, p = self.m, self.p
        phys = p.desktop_size()
        scale = p.dpi_scale()
        info = {"physical": list(phys) if phys else None, "scale": scale, "size": phys, "how": "desktop size"}
        if not phys or scale <= 1.01:
            return info
        flags = []
        for play in m.play_dirs:
            exe = str(play / "Oblivion.exe")
            flags = profile.dpi_flags(m.reg.get(exe)) or profile.dpi_flags(m.reg.get(exe, machine=True))
            if flags:
                break
        if flags:
            gog_exe = m.game_dir / "Oblivion.exe"
            for exe in dict.fromkeys([str(gog_exe), str(gog_exe.resolve())]):
                keep = [t for t in (m.reg.get(exe) or "").replace("~", " ").split() if t.upper() not in profile.DPI_TOKENS]
                sess.set_layer(exe, "~ " + " ".join(keep + flags))
            info.update(how=f"play copy's DPI flag {' '.join(flags)} set on the test exe for the run")
        else:
            info.update(size=(round(phys[0] / scale), round(phys[1] / scale)),
                        how=f"logical size at {round(scale * 100)} % scaling (Windows scales it up)")
        self.log(f"display: {info['size'][0]}x{info['size'][1]}, {info['how']}")
        return info

    def __exit__(self, *exc):
        self.check = None
        j = profile.status(self.m)
        pid = j.get("game_pid") if j.get("open") else None
        if pid and self.p.alive(pid):
            # forge was interrupted while the game runs: never restore under it; the guardian does it
            self.log("the test game is still running: your setup is restored as soon as it exits (guardian)")
            return False
        try:
            profile.restore(self.m, log=self.log)
        finally:
            after = hashes(self.m)
            self.check = {k: {"before": self.before[k], "after": after[k], "same": self.before[k] == after[k]}
                          for k in self.before}
            if not all(v["same"] for v in self.check.values()):
                self.log("WARNING: Plugins.txt or Oblivion.ini differ from before the test; see result.json")
        return False


def clean_test_saves(m: profile.Machine, log, keep_base: bool = True) -> list[str]:
    """Only in the test profile's own save folder (Saves\\ForgePlaytest): drop autosaves and
    quicksaves, so Continue always loads the test save."""
    gone = []
    if m.save_dir.is_dir():
        for f in sorted(m.save_dir.iterdir()):
            if f.suffix.lower() in (".ess", ".obse", ".bak") and not (keep_base and f.stem == SAVE_NAME):
                f.unlink()
                gone.append(f.name)
    if gone:
        log(f"removed from the test save folder: {', '.join(gone)}")
    return gone


def _batch_files(chunks: list[dict]) -> list[tuple[str, bytes]]:
    """Each batch as fptN.txt and as fptN: `bat fptN` finds it whether or not Oblivion adds .txt."""
    out = []
    for c in chunks:
        data = ("\r\n".join(c["lines"]) + "\r\n").encode("cp1252")
        out += [(c["file"], data), (c["file"][:-4], data)]
    return out


def find_run_log(m: profile.Machine, marker: str, since: float) -> Path | None:
    """The console log of this run, wherever the logger put it: forge_test.log in the game folder
    (xOBSE PrintToFile), or any .log/.txt written since the run started under the game folder or
    My Games\\Oblivion (e.g. an OBSE console-logging plugin) that contains this run's BEGIN marker."""
    direct = m.game_dir / mf.LOG_NAME
    if direct.is_file():
        return direct
    output = re.compile(r"^(?!.*\bprintc\b).*" + re.escape(marker), re.M | re.I)   # output, not the command
    for root in (m.game_dir, m.ini.parent):
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            try:
                if (f.suffix.lower() not in (".log", ".txt") or f.name.lower().startswith(mf.BATCH_PREFIX)
                        or not f.is_file() or f.stat().st_mtime < since):
                    continue
                if f.stat().st_size < 50_000_000 and output.search(f.read_text("cp1252", "replace")):
                    return f
            except OSError:
                continue
    return None


def _collect_results(m: profile.Machine, man: dict, prep: Prepared, run_dir: Path, since: float, log) -> dict:
    """After the game has exited: the PrintToFile log (wherever xOBSE put it), else the result
    globals from the ForgePlaytestResult save. Both are removed from the game/save folders."""
    out: dict = {}
    save_only = man["results"].get("route") == "save"
    found = None if save_only else find_run_log(m, f"FORGE|BEGIN|{man['run_id']}", since)
    if found and not any(">>" in l for l in testlog.read_lines(found)):
        out["log_without_values"] = str(found)            # markers only: let the result save decide
        found = None
    if found:
        shutil.copy2(found, run_dir / mf.LOG_NAME)
        out["log_source"] = str(found)
        if found.resolve() != (m.game_dir / mf.LOG_NAME).resolve() and m.game_dir.resolve() in found.resolve().parents:
            try:
                found.unlink()                            # written by the game for this run only
            except OSError:
                pass
    save = m.save_dir / f"{man['results']['save']}.ess"
    if save.is_file():
        try:
            from playtest import essglobals
            values = essglobals.plugin_globals(save, testcells.PLUGIN_NAME, (prep.layout or {}).get("globals", {}))
            out["save_values"] = values
            if not found:
                (run_dir / mf.LOG_NAME).write_text(testlog.log_from_globals(man, values), encoding="cp1252")
                out["log_source"] = f"result save {save.name}"
        except (OSError, ValueError) as e:
            out["save_error"] = str(e)
            log(f"could not read the result save: {e}")
        for f in m.save_dir.glob(f"{man['results']['save']}.*"):
            try:
                f.unlink()
            except OSError:
                pass
    return out


def _new_run_dir(m: profile.Machine) -> Path:
    base = m.state_dir / "runs" / time.strftime("%Y%m%d-%H%M%S")
    d, i = base, 1
    while d.exists():
        i += 1
        d = base.with_name(f"{base.name}-{i}")
    d.mkdir(parents=True)
    return d


def run(target_path: str | Path, opts: Options, m: profile.Machine | None = None,
        p: plat.Platform | None = None) -> dict:
    m = m or profile.Machine.detect()
    p = p or plat.default()
    log = opts.log
    t0 = p.now()
    for n in preflight(m, p):
        log(f"note: {n}")
    run_dir = _new_run_dir(m)
    started_wall = time.time() - 5
    result: dict = {"verdict": "NOT-RUN"}
    prof = _Profile(m, p, log, run_dir)
    try:
        with prof:
            t = resolve_target(target_path, opts, m)
            prep = prepare(t, opts, m)
            loc = prep.location
            log(f"location: {loc.label}: {loc.detail}  (boot: {loc.boot})")
            log("test actors: " + (", ".join(f"{role} = {a['edid']} ({a['name']}, {a['ref']})"
                                             for role, a in prep.actors.items()) if prep.actors
                                   else "none (the plan doesn't use TestTarget/TestCaster)"))
            lo = prof.apply(prep, opts)
            forms = _forms(prep, m, lo)
            man = mf.build(t.plan, forms, location=loc.to_dict(), bring=testcells.BRING.get(loc.key, []),
                           plugin=t.plugin.name if t.plugin else None, spec=t.spec_name, results=opts.results)
            log(f"results: {'result-save globals only (no PrintToFile)' if man['results']['route'] == 'save' else 'log file, then the result save'}")
            mf.save(man, run_dir / "playtest_manifest.json")
            for name, data in _batch_files(man["chunks"]):
                prof.sess.stage(m.game_dir / name, data=data)
            if not opts.dry_run:
                clean_test_saves(m, log)
            game_log = m.game_dir / mf.LOG_NAME
            prof.sess.collect(game_log)
            log(f"test profile on: {len(prep.active)} plugins: {', '.join(lo)}")
            extra = {"boot_seconds": None, "froze": False, "dry_run": opts.dry_run, "location": loc.to_dict(),
                     "test_actors": prep.actors,
                     "display": prof.display}
            if opts.dry_run:
                log("dry run: profile built and staged; not launching")
            elif not (m.save_dir / f"{SAVE_NAME}.ess").is_file():
                raise PlaytestError(f"no test save yet ({m.save_dir / (SAVE_NAME + '.ess')}). Run "
                                    "`forge playtest make-save` first (once).")
            else:
                extra.update(_play(m, p, prof.sess, man, loc, opts, t0, run_dir))
            if not opts.dry_run:
                extra.update(_collect_results(m, man, prep, run_dir, started_wall, log))
            result = testlog.evaluate(man, run_dir / mf.LOG_NAME if (run_dir / mf.LOG_NAME).is_file() else None, extra)
            if opts.dry_run:
                result["verdict"] = "DRY-RUN"
    finally:
        result["restore_check"] = getattr(prof, "check", None)
        result["run_dir"] = str(run_dir)
        (run_dir / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        (m.state_dir / "last-run.txt").write_text(str(run_dir), encoding="utf-8")
    return result


NEW_SAVE = "ForgePlaytestNew"


def make_save(opts: Options, m: profile.Machine | None = None, p: plat.Platform | None = None,
              wait_minutes: float = 15.0) -> dict:
    """One-time: Yuri starts a New Game with the pad and finishes the character screen. Forge then
    `coc`s to the arena and runs one batch that logs where the player is and saves as
    ForgePlaytestNew. Forge never closes the game: it beeps and waits for Yuri to quit. After the game
    has exited it checks the log; only if the player really was in the arena does the new save
    replace Saves\\ForgePlaytest\\ForgePlaytestBase.ess. Otherwise the old save stays untouched.

    Run 3: a save made before the race/name screen brings that screen back on every load, so forge
    waits until that screen was opened and closed again."""
    m = m or profile.Machine.detect()
    p = p or plat.default()
    log = opts.log
    t0 = p.now()
    preflight(m, p)
    run_dir = _new_run_dir(m)
    res = {"made": False, "run_dir": str(run_dir)}
    prof = _Profile(m, p, log, run_dir)
    with prof:
        prep = prepare(Target(None, mf.parse_plan(None), None), Options(cell=opts.cell), m)
        prof.apply(prep, opts)
        loc = prep.location
        lines = []
        if loc.setpos:
            x, y, z, _ = loc.setpos
            lines += [f"player.setpos x {x:.1f}", f"player.setpos y {y:.1f}", f"player.setpos z {z + 8:.1f}"]
        probe = f"GetInCell {loc.cell_edid}" if loc.cell_edid else f"GetInWorldspace {loc.world_edid}"
        lines += mf._value("ForgeRInPlace", probe.split()[0], f"player.{probe}")
        lines += [f"save {NEW_SAVE}", f'message "{QUIT_NOTE}"']
        for name, data in _batch_files([{"file": "fptsave.txt", "lines": lines}]):
            prof.sess.stage(m.game_dir / name, data=data)
        game_log = m.game_dir / mf.LOG_NAME
        prof.sess.collect(game_log)
        for f in m.save_dir.glob(f"{NEW_SAVE}.*") if m.save_dir.is_dir() else []:
            f.unlink()
        drv = None
        try:
            drv = _launch(m, p, prof.sess, opts, t0, run_dir)["driver"]
            try:
                if not drv.wait_main_menu(opts.boot_timeout):
                    raise PlaytestError("the main menu never appeared")
                p.beep()
                log("\n  >>> With the pad: NEW, skip the intro (Cross). On the character screen type any name,"
                    " choose DONE\n  >>> and confirm. Then wait: forge takes you to the Arena and saves.\n")
                if not drv.wait_chargen_done(wait_minutes * 60):
                    raise PlaytestError("the character screen was never finished")
                drv.console(loc.boot)
                if not (drv.wait_load_start(30) and drv.wait_loaded(opts.boot_timeout)):
                    raise PlaytestError(f"`{loc.boot}` did not load")
                drv.idle(3.0)
                drv.run_batch("bat fptsave", game_log)
                drv.idle(5.0)
                drv.shot("saved")
                drv.hand_over("Test save step done")
            except PlaytestError as exc:
                res["error"] = str(exc)
                drv.shot("error")
                drv.hand_over(f"make-save stopped: {exc}")
        except PlaytestError as exc:
            res["error"] = str(exc)
        finally:
            if drv is not None:
                drv.close_trace()
        # the game has exited: the new save's own ForgeRInPlace global says where the player was;
        # the PrintToFile log is the second opinion
        text = game_log.read_text("cp1252", "replace") if game_log.is_file() else ""
        if game_log.is_file():
            shutil.copy2(game_log, run_dir / mf.LOG_NAME)
        res["probe"] = [l for l in text.splitlines() if ">>" in l][-3:]
        answers = [re.search(r"GetIn(?:Cell|Worldspace).*>>\s*([-\d.]+)", l) for l in testlog.split_text(text)]
        answers = [float(a.group(1)) for a in answers if a]
        new = m.save_dir / f"{NEW_SAVE}.ess"
        if new.is_file():
            try:
                from playtest import essglobals
                g = essglobals.plugin_globals(new, testcells.PLUGIN_NAME, (prep.layout or {}).get("globals", {}))
                if "ForgeRInPlace" in g:
                    answers.append(g["ForgeRInPlace"])
                    res["save_in_place"] = g["ForgeRInPlace"]
            except (OSError, ValueError) as e:
                res["save_error"] = str(e)
        there = bool(answers) and answers[-1] == 1.0
        if not answers and new.is_file():
            # neither the log nor the save's own global answered, but the batch ran (the save line
            # comes after the location probe): keep the save and say the location is unconfirmed
            there = True
            res["warning"] = "no forge_test.log: location not confirmed by the log, the save was kept"
            log(f"warning: {res['warning']}")
        if there and new.is_file():
            for f in sorted(m.save_dir.glob(f"{NEW_SAVE}.*")):
                os.replace(f, f.with_name(SAVE_NAME + f.suffix))
            clean_test_saves(m, log)
            res["made"] = True
            res["save"] = str(m.save_dir / f"{SAVE_NAME}.ess")
        else:
            for f in m.save_dir.glob(f"{NEW_SAVE}.*") if m.save_dir.is_dir() else []:
                f.unlink()
            res.setdefault("error", "the player was not confirmed in the arena (log: "
                                    f"{res['probe'] or 'empty'}); the old test save, if any, is unchanged"
                           if new.is_file() or text else "no save was written")
    res["restore_check"] = prof.check
    (run_dir / "result.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


def _launch(m, p: plat.Platform, sess: profile.Session, opts: Options, t0: float, run_dir: Path) -> dict:
    events: list = []

    def note(msg):
        events.append([round(p.now() - t0, 2), msg])
        opts.log(f"[{p.now() - t0:5.1f}s] {msg}")

    p.launch(m.game_dir / "obse_loader.exe", m.game_dir)
    note("obse_loader.exe started")
    pid = _wait(p, lambda: _game_pid(p, m.game_dir), 30)
    if not pid:
        raise PlaytestError("Oblivion.exe did not start (see obse_loader.log in the test game)")
    sess.set_game_pid(pid)
    p.spawn_detached([profile.python_exe(), str(Path(__file__).with_name("guardian.py")), str(m.state_dir),
                      "--game", str(pid), "--forge", str(os.getpid())])
    if opts.companion:
        _start_companion(p, (m.data / "OBSE" / "Plugins" / "NorthernUI.dll").is_file())
    return {"pid": pid, "events": events, "driver": Driver(p, pid, opts, note, run_dir, t0)}


def _play(m, p: plat.Platform, sess, man: dict, loc: vanilla.Location, opts: Options, t0: float,
          run_dir: Path) -> dict:
    """Boot, run the batches, then hand the game to Yuri. Forge never closes the game; it returns
    only after Yuri has quit (the caller restores the setup after that)."""
    out = {"boot_seconds": None, "froze": False}
    launch = _launch(m, p, sess, opts, t0, run_dir)
    out["events"] = launch["events"]
    drv: Driver = launch["driver"]
    game_log = m.game_dir / mf.LOG_NAME
    try:
        try:
            out["boot_strategy"] = drv.boot(loc.boot)
            out["boot_seconds"] = round(p.now() - t0, 2)
            drv.note(f"playing at {loc.label} after {out['boot_seconds']}s ({out['boot_strategy']})")
            drv.shot("in-game")
            for c in man["chunks"]:
                if c["wait_before"]:
                    drv.idle(c["wait_before"])
                if not drv.run_batch(c["command"], game_log):
                    drv.note(f"{c['command']}: nothing in forge_test.log yet (the result save is read after you quit)")
            drv.idle(1.0)
            drv.shot("checks-done")
            res = testlog.evaluate(man, game_log if game_log.is_file() else None)
            drv.note(f"checks done: {res['verdict']} ({res['passed']}/{res['checks']})")
            drv.hand_over(f"Checks done ({res['verdict']}). Keep playing with the pad")
        except PlaytestError as exc:
            drv.note(f"error: {exc}")
            out["error"] = str(exc)
            drv.shot("error")
            drv.hand_over(f"Test stopped: {exc}")
    finally:
        drv.close_trace()
    out["froze"] = drv.froze
    if drv.froze:
        out["freeze_report"] = str(plat.CONTROLLER / "freeze_report.txt")
    return out


def _wait(p: plat.Platform, cond, timeout: float, step: float = 0.25):
    end = p.now() + timeout
    while p.now() < end:
        v = cond()
        if v:
            return v
        p.sleep(step)
    return None


def _game_pid(p: plat.Platform, game_dir: Path) -> int | None:
    root = str(game_dir.resolve()).lower()
    for pid, name, path in p.processes():
        if name.lower() == "oblivion.exe" and str(Path(path).resolve() if path else "").lower().startswith(root):
            return pid
    return None


def _start_companion(p: plat.Platform, northernui: bool) -> None:
    """The controller companion, in NorthernUI mode when the test game has it (pad only, no
    stick-driven mouse cursor: run 2's companion guessed from the Steam copy)."""
    script = plat.CONTROLLER / "oblivion_controller.py"
    if script.is_file():
        p.spawn_detached([profile.python_exe(), str(script), "--nogui", "--mode",
                          "northernui" if northernui else "standalone"])


class Driver:
    """Types into the test game only. Traces the menu state and screenshots each boot step."""

    def __init__(self, p: plat.Platform, pid: int, opts: Options, note, run_dir: Path, t0: float):
        self.p, self.pid, self.opts, self.note_fn, self.t0 = p, pid, opts, note, t0
        self.froze = False
        self._frozen_since = None
        self._last_bad = None
        self._tut_since = None
        self.shots = run_dir / "shots"
        self._nshot = 0
        self._trace = open(run_dir / "boot-trace.jsonl", "a", encoding="utf-8")
        self._last_trace = -1.0
        self.phase = "start"

    # -- diagnostics
    def note(self, msg):
        self.note_fn(msg)
        self._write({"note": msg})

    def _write(self, rec: dict):
        try:
            self._trace.write(json.dumps({"t": round(self.p.now() - self.t0, 2), "phase": self.phase, **rec}) + "\n")
            self._trace.flush()
        except (OSError, ValueError):
            pass

    def close_trace(self):
        try:
            self._trace.close()
        except OSError:
            pass

    def trace(self, st: dict | None = None, force: bool = False):
        now = self.p.now()
        if not force and now - self._last_trace < 0.5:
            return
        self._last_trace = now
        st = st if st is not None else self._state()
        win = self.p.window(self.pid)
        self._write({"menus": st.get("menus"), "menu_mode": st.get("menu_mode"),
                     "focused": self.p.focused(self.pid), "window": list(win[2]) if win else None})

    def shot(self, name: str) -> Path | None:
        self._nshot += 1
        path = self.shots / f"{self._nshot:02d}-{name}.png"
        try:
            self.shots.mkdir(parents=True, exist_ok=True)
            ok = self.p.screenshot(self.p.window(self.pid), path)
        except Exception as exc:                               # diagnostics never break the run
            self._write({"shot_error": str(exc)})
            return None
        self._write({"shot": path.name if ok else f"{path.name} (failed)"})
        return path if ok else None

    # -- watching
    def tick(self) -> None:
        p = self.p
        if not p.alive(self.pid):
            return
        win = p.window(self.pid)
        if win and not getattr(self, "_borderless", False):
            self._borderless = True
            if p.make_borderless(win):
                self.note("made the game window borderless at the desktop size")
        reported = p.freeze_tick(win, p.focused(self.pid))
        hung = p.hung(win)
        now = p.now()
        if hung or reported:
            self._frozen_since = self._frozen_since or now
            self._last_bad = now
        elif self._frozen_since and now - (self._last_bad or now) > 8:
            self._frozen_since = None
        if self._frozen_since and now - self._frozen_since >= self.opts.hang_seconds and not self.froze:
            self.froze = True
            self.shot("frozen")
            if self.opts.kill_on_freeze:
                self.note(f"frozen for {self.opts.hang_seconds:.0f}s: closing the test game (--kill-on-freeze)")
                p.kill(self.pid)
            else:
                p.beep()
                self.note(f"frozen for {self.opts.hang_seconds:.0f}s. Close it yourself (Task Manager); "
                          "forge restores your setup once it is gone")
            raise PlaytestError("game froze")
        st = p.ui_state(self.pid)
        self.trace(st)
        if st.get("menu") == plat.MENU_MESSAGE and plat.MENU_PERSUASION in st.get("menus", []):
            self._tut_since = self._tut_since or now
            if now - self._tut_since > 0.7 and self._focus():
                p.press("down", "enter")                 # the page that ignores the pad (Oct 5 fix)
                self.note("dismissed the Persuasion tutorial page")
                self._tut_since = None
        else:
            self._tut_since = None

    def idle(self, seconds: float) -> None:
        end = self.p.now() + seconds
        while self.p.now() < end:
            self.tick()
            self.p.sleep(0.25)

    def until_exit(self) -> None:
        self.phase = "playing"
        while self.p.alive(self.pid):
            try:
                self.tick()
            except PlaytestError:
                pass                                      # a freeze was reported; keep waiting
            self.p.sleep(0.5)
        self.p.sleep(2.0)                                 # let Oblivion let go of Plugins.txt / the ini

    def hand_over(self, what: str) -> None:
        """Forge's part is over: tell Yuri (beep + note), then wait until he quits the game."""
        self.p.beep()
        self.note(f"{what}. Quit the game when you are ready; forge waits and then restores your setup.")
        self.opts.log(f"\n  >>> {what}.\n  >>> Quit the game with the pad when you are ready.\n")
        self.until_exit()
        self.note("game closed by the player")

    # -- states
    def _state(self) -> dict:
        return self.p.ui_state(self.pid)

    def _menus(self) -> list:
        return self._state().get("menus", [])

    def wait_main_menu(self, timeout: float) -> bool:
        self.phase = "wait-main-menu"
        end = self.p.now() + timeout
        seen = None
        while self.p.now() < end:
            self.tick()
            st = self._state()
            if plat.MENU_MAIN in st.get("menus", []):
                self.idle(1.0)                             # let it finish drawing
                return True
            if self.p.window(self.pid) and seen is None:
                seen = self.p.now()
            if seen and self.p.now() - seen > 25 and plat.MENU_LOADING not in st.get("menus", []):
                self.note("menu probe never showed the main menu (1044); continuing after 25 s")
                return True
            self.p.sleep(0.25)
        return False

    def wait_load_start(self, timeout: float) -> bool:
        """True once a load begins: the loading menu shows up or the main menu goes away."""
        end = self.p.now() + timeout
        while self.p.now() < end:
            self.tick()
            menus = self._menus()
            if plat.MENU_LOADING in menus or plat.MENU_MAIN not in menus:
                return True
            self.p.sleep(0.25)
        return False

    def wait_loaded(self, timeout: float) -> bool:
        """True once neither the main menu nor the loading screen has been up for 1.5 s."""
        self.phase = "wait-loaded"
        end = self.p.now() + timeout
        clear_since = None
        while self.p.now() < end:
            self.tick()
            menus = self._menus()
            if plat.MENU_LOADING in menus or plat.MENU_MAIN in menus:
                clear_since = None
            else:
                clear_since = clear_since or self.p.now()
                if self.p.now() - clear_since >= 1.5:
                    return True
            self.p.sleep(0.25)
        self.trace(force=True)
        return False

    def wait_in_game(self, timeout: float) -> bool:
        """Player in control: only HUD menus, not in menu mode, for 5 s."""
        self.phase = "wait-in-game"
        end = self.p.now() + timeout
        since = None
        while self.p.now() < end:
            self.tick()
            st = self._state()
            ok = not st.get("menu_mode") and not [x for x in st.get("menus", []) if x not in HUD]
            since = (since or self.p.now()) if ok else None
            if since and self.p.now() - since >= 5:
                return True
            self.p.sleep(0.5)
        return False

    # -- boot
    def boot(self, command: str) -> str:
        """Main menu -> beep -> Yuri presses Continue -> boot command from the in-game console.
        Forge sends no keys in the main menu: typing there never started a game on the PC and only
        opened other menus (run 4: the Load menu, 1038)."""
        if not self.wait_main_menu(self.opts.boot_timeout):
            self.shot("no-main-menu")
            raise PlaytestError(f"the main menu never appeared (menus {self._menus()})")
        self.shot("main-menu")
        return self._boot_continue(command)

    def _boot_continue(self, command: str) -> str:
        """Plan B: Yuri presses Cross on CONTINUE (the test save), then the console in game.
        Forge never presses keys in the main menu (run 2: Down+Enter opened a message box)."""
        self.phase = "boot-B-continue"
        self._focus()
        self.p.beep()
        self.opts.log("\n  >>> BEEP: press Cross on CONTINUE (the test save). Forge does the rest.\n")
        self.note("B: waiting for Continue (Cross on the pad)")
        if not self.wait_load_start(120):
            self.shot("B-no-load")
            raise PlaytestError(f"nobody pressed Continue within 2 minutes (menus {self._menus()})")
        if not self.wait_loaded(self.opts.boot_timeout):
            self.shot("B-load-timeout")
            raise PlaytestError("the test save never finished loading")
        self.idle(1.0)
        if CHARGEN & set(self._menus()):
            self.shot("B-chargen")
            raise PlaytestError("the test save was made before character creation (the race/name screen "
                                "opened). Run `forge playtest make-save` again.")
        self.console(command)
        if not (self.wait_load_start(15) and self.wait_loaded(self.opts.boot_timeout)):
            self.shot("B-coc-timeout")
            raise PlaytestError(f"`{command}` from the in-game console did not load")
        return "B: Continue + in-game console"

    def wait_chargen_done(self, timeout: float) -> bool:
        """The race/name screen was open and is closed again, and the player is in control."""
        self.phase = "wait-chargen"
        end = self.p.now() + timeout
        seen = False
        while self.p.now() < end:
            self.tick()
            menus = set(self._menus())
            if menus & CHARGEN:
                if not seen:
                    self.note("character screen open")
                seen = True
            elif seen and self.wait_in_game(10) and not (set(self._menus()) & CHARGEN):
                self.note("character screen done")
                return True
            self.p.sleep(0.5)
        return False

    # -- console
    def _focus(self) -> bool:
        if self.p.focused(self.pid):
            return True
        win = self.p.window(self.pid)
        return bool(win) and self.p.focus(win[0]) and self.p.focused(self.pid)

    def _console_open(self) -> bool:
        st = self._state()
        real = [x for x in st.get("menus", []) if x not in HUD]
        return bool(st.get("menu_mode")) and not real

    def console(self, command: str) -> None:
        if not self._focus():
            self.shot("no-focus")
            raise PlaytestError("could not bring the test game to the front")
        if not self._console_open():
            opened = False
            for attempt in range(3):                      # run 4: the first press after a load got lost
                before = self.p.grab(self.p.window(self.pid))
                self.p.press("tilde")
                opened = bool(_wait(self.p, self._console_open, 2.0, 0.1))
                if not opened:
                    after = self.p.grab(self.p.window(self.pid))
                    if self.p.console_visible(before, after):
                        opened = True
                        self._screen_console = True
                        self.note("console open (seen on screen; the menu probe did not show it)")
                if opened:
                    break
                self.shot(f"console-try{attempt + 1}")
                self.idle(1.5)
            if not opened:
                self.shot("console-not-open")
                raise PlaytestError(f"the console did not open; not typing into the game (state {self._state()})")
        if not self.p.focused(self.pid) and not self._focus():
            raise PlaytestError("the test game lost focus while typing")
        self.p.type_text(command)
        self.shot("typed-" + command.split()[0])
        if not self.p.focused(self.pid):
            raise PlaytestError("the test game lost focus while typing (nothing was sent)")
        self.p.press("enter")
        self.p.sleep(0.3)

    def close_console(self) -> None:
        if self._console_open():
            self.p.press("tilde")
            _wait(self.p, lambda: not self._console_open(), 2.0, 0.1)
        elif getattr(self, "_screen_console", False):
            self.p.press("tilde")
            self._screen_console = False

    def run_batch(self, command: str, game_log: Path) -> bool:
        """Run one batch once (never retried: a second run would repeat its steps). The console is
        photographed before it closes: its last lines are the batch's output, the evidence when no
        log file gets written (run 5: scof wrote nothing)."""
        self.phase = f"batch {command}"
        size = game_log.stat().st_size if game_log.is_file() else 0
        self.console(command)
        ok = _wait(self.p, lambda: game_log.is_file() and game_log.stat().st_size > size, 3.0, 0.2)
        self.shot("output-" + command.split()[-1])
        self.close_console()
        return bool(ok)
