"""forge playtest: real Oblivion, minimal load order, straight into a vanilla cell, checks, restore.

Boot (all automatic; Yuri only plays):
  1. obse_loader.exe in the clean GOG copy with the test profile (intro videos off).
  2. Main menu. Strategy A: open the console there and type the location's boot command
     (`coc <Interior>` or `cow <World> x y`); Oblivion starts a default character in that cell.
     Strategy B (if A doesn't start a load within 20 s and a test save exists): Continue, which
     loads the newest save in Saves\\ForgePlaytest\\ (made once with `forge playtest make-save`),
     then the boot command from the in-game console.
  3. After the load: `bat fpt1`, `bat fpt2`... (one per wait). The first batch moves the test
     actors next to the player and logs everything to forge_test.log.
  4. The game stays open to play with the pad (or quits with --quit). Restore runs when it exits.

Every run leaves a boot trace (boot-trace.jsonl: menu stack, menu mode, focus, twice a second)
and screenshots of each boot step (shots\\*.png) in its run folder, so a failure can be read
afterwards. While the game runs the driver watches for freezes (Controller\\oblivion_freeze.py
plus Windows' "not responding"; kill after --hang-seconds) and auto-dismisses the Persuasion
tutorial page that ignores the controller.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from playtest import manifest as mf, platform as plat, profile, testcells, testlog, vanilla

TOOLS = Path(__file__).resolve().parents[1]
HUD = {1004, 1005, 1006, 1010, 1045}
SAVE_NAME = "ForgePlaytestBase"


class PlaytestError(RuntimeError):
    pass


@dataclass
class Options:
    cell: str | None = None
    manifest: Path | None = None
    dry_run: bool = False                 # build + swap + stage, then restore at once (no launch)
    quit_when_done: bool = False
    boot_timeout: float = 120.0
    hang_seconds: float = 20.0
    companion: bool = True
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


def prepare(t: Target, opts: Options, m: profile.Machine) -> Prepared:
    data = m.data
    try:
        loc = vanilla.resolve(opts.cell or t.plan.get("cell"), vanilla_index(m))
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
    return Prepared(t, loc, active, stage, lay)


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

    def apply(self, prep: Prepared) -> list[str]:
        m, sess = self.m, self.sess
        sess.begin()
        sess.swap_in(m.plugins_txt, profile.plugins_txt(prep.active))
        sess.swap_in(m.ini, profile.test_ini(self.real_ini))
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

    def __exit__(self, *exc):
        try:
            profile.restore(self.m, log=self.log)
        finally:
            after = hashes(self.m)
            self.check = {k: {"before": self.before[k], "after": after[k], "same": self.before[k] == after[k]}
                          for k in self.before}
            if not all(v["same"] for v in self.check.values()):
                self.log("WARNING: Plugins.txt or Oblivion.ini differ from before the test; see result.json")
        return False


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
    result: dict = {"verdict": "NOT-RUN"}
    prof = _Profile(m, p, log, run_dir)
    try:
        with prof:
            t = resolve_target(target_path, opts, m)
            prep = prepare(t, opts, m)
            loc = prep.location
            log(f"location: {loc.label}: {loc.detail}  (boot: {loc.boot})")
            lo = prof.apply(prep)
            forms = _forms(prep, m, lo)
            man = mf.build(t.plan, forms, location=loc.to_dict(), bring=testcells.BRING.get(loc.key, []),
                           plugin=t.plugin.name if t.plugin else None, spec=t.spec_name)
            mf.save(man, run_dir / "playtest_manifest.json")
            for c in man["chunks"]:
                prof.sess.stage(m.game_dir / c["file"], data=("\r\n".join(c["lines"]) + "\r\n").encode("cp1252"))
            game_log = m.game_dir / mf.LOG_NAME
            prof.sess.collect(game_log)
            log(f"test profile on: {len(prep.active)} plugins: {', '.join(lo)}")
            extra = {"boot_seconds": None, "froze": False, "dry_run": opts.dry_run, "location": loc.to_dict()}
            if opts.dry_run:
                log("dry run: profile built and staged; not launching")
            else:
                extra.update(_play(m, p, prof.sess, man, loc, opts, t0, run_dir))
            if game_log.is_file():
                shutil.copy2(game_log, run_dir / mf.LOG_NAME)
            result = testlog.evaluate(man, run_dir / mf.LOG_NAME if (run_dir / mf.LOG_NAME).is_file() else None, extra)
            if opts.dry_run:
                result["verdict"] = "DRY-RUN"
    finally:
        result["restore_check"] = getattr(prof, "check", None)
        result["run_dir"] = str(run_dir)
        (run_dir / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        (m.state_dir / "last-run.txt").write_text(str(run_dir), encoding="utf-8")
    return result


def make_save(opts: Options, m: profile.Machine | None = None, p: plat.Platform | None = None,
              wait_minutes: float = 15.0) -> dict:
    """One-time: Yuri starts a New Game with the pad; forge then puts the character in the arena and
    saves it as Saves\\ForgePlaytest\\ForgePlaytestBase.ess (boot strategy B uses it)."""
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
        prof.apply(prep)
        try:
            drv = _launch(m, p, prof.sess, opts, t0, run_dir)["driver"]
        except PlaytestError as exc:
            res["error"] = str(exc)
            drv = None
        try:
            if drv is None:
                raise PlaytestError(res["error"])
            if not drv.wait_main_menu(opts.boot_timeout):
                raise PlaytestError("the main menu never appeared")
            log("\n  >>> With the pad: choose NEW, skip the intro (Cross), and finish the character screens any way"
                " you like.\n  >>> Then just wait: forge takes over as soon as you can walk.\n")
            if not drv.wait_in_game(wait_minutes * 60):
                raise PlaytestError("never reached the game world")
            drv.console(prep.location.boot)
            if not drv.wait_loaded(opts.boot_timeout):
                raise PlaytestError("the arena did not load")
            drv.console(f"save {SAVE_NAME}")
            drv.idle(5)
            save = m.save_dir / f"{SAVE_NAME}.ess"
            res["made"] = save.is_file()
            res["save"] = str(save)
            drv.shot("save-done")
            drv.console("qqq")
            drv.until_exit()
        except Exception as exc:
            res["error"] = str(exc)
            if drv is not None:
                drv.shot("error")
                if p.alive(drv.pid):
                    p.kill(drv.pid)
        finally:
            if drv is not None:
                drv.close_trace()
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
        _start_companion(p)
    return {"pid": pid, "events": events, "driver": Driver(p, pid, opts, note, run_dir, t0)}


def _play(m, p: plat.Platform, sess, man: dict, loc: vanilla.Location, opts: Options, t0: float,
          run_dir: Path) -> dict:
    log = opts.log
    out = {"boot_seconds": None, "froze": False}
    launch = _launch(m, p, sess, opts, t0, run_dir)
    out["events"] = launch["events"]
    drv: Driver = launch["driver"]
    pid = launch["pid"]
    game_log = m.game_dir / mf.LOG_NAME
    try:
        out["boot_strategy"] = drv.boot(loc.boot, has_save=(m.save_dir / f"{SAVE_NAME}.ess").is_file())
        out["boot_seconds"] = round(p.now() - t0, 2)
        drv.note(f"playing at {loc.label} after {out['boot_seconds']}s ({out['boot_strategy']})")
        drv.shot("in-game")
        for c in man["chunks"]:
            if c["wait_before"]:
                drv.idle(c["wait_before"])
            if not drv.run_batch(c["command"], game_log):
                drv.note(f"{c['command']}: nothing in the log yet (Oblivion may buffer it until `scof 0`)")
        drv.idle(1.0)
        drv.shot("checks-done")
        res = testlog.evaluate(man, game_log if game_log.is_file() else None)
        drv.note(f"checks done: {res['verdict']} ({res['passed']}/{res['checks']})")
        if opts.quit_when_done:
            drv.console("qqq")
            drv.note("quit")
        else:
            log("Keep playing with the pad. Your normal setup comes back when you exit the game.")
        drv.until_exit()
    except Exception as exc:
        drv.note(f"error: {exc}")
        out["error"] = str(exc)
        drv.shot("error")
        if p.alive(pid):
            p.kill(pid)
            drv.note("test game closed")
    finally:
        drv.close_trace()
    out["froze"] = drv.froze
    if drv.froze:
        out["freeze_report"] = str(plat.CONTROLLER / "freeze_report.txt")
    _wait(p, lambda: not p.alive(pid), 15)
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


def _start_companion(p: plat.Platform) -> None:
    script = plat.CONTROLLER / "oblivion_controller.py"
    if script.is_file():
        p.spawn_detached([profile.python_exe(), str(script), "--nogui"])


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
        reported = p.freeze_tick(win, p.focused(self.pid))
        hung = p.hung(win)
        now = p.now()
        if hung or reported:
            self._frozen_since = self._frozen_since or now
            self._last_bad = now
        elif self._frozen_since and now - (self._last_bad or now) > 8:
            self._frozen_since = None
        if self._frozen_since and now - self._frozen_since >= self.opts.hang_seconds:
            self.froze = True
            self.shot("frozen")
            self.note(f"frozen for {self.opts.hang_seconds:.0f}s: closing the test game")
            p.kill(self.pid)
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
            self.tick()
            self.p.sleep(0.5)

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
    def boot(self, command: str, has_save: bool) -> str:
        if not self.wait_main_menu(self.opts.boot_timeout):
            self.shot("no-main-menu")
            raise PlaytestError(f"the main menu never appeared (menus {self._menus()})")
        self.shot("main-menu")
        # Strategy A: console at the main menu
        self.phase = "boot-A-menu-console"
        self.console(command, at_menu=True)
        self.note(f"A: typed `{command}` at the main menu")
        if self.wait_load_start(20):
            if self.wait_loaded(self.opts.boot_timeout):
                if not has_save:
                    return "A: console at the main menu"
                # With a test save, the Enter could have hit Continue instead of the console:
                # repeat the command in game so the location is right either way.
                self.idle(1.0)
                self.console(command)
                if self.wait_load_start(15) and self.wait_loaded(self.opts.boot_timeout):
                    return "A: console at the main menu (+ again in game)"
                self.shot("A-recoc-timeout")
                raise PlaytestError(f"`{command}` from the in-game console did not load")
            self.shot("A-load-timeout")
            raise PlaytestError(f"the load after `{command}` never finished (menus {self._menus()})")
        self.shot("A-no-load")
        self.note(f"A failed: still at the main menu 20 s after `{command}` (menus {self._menus()})")
        if not has_save:
            raise PlaytestError("the main-menu console did not start a game, and there is no test save for "
                                "plan B. Run `forge playtest make-save` once, then try again. Screenshots: "
                                f"{self.shots}")
        # Strategy B: Continue (newest save in Saves\ForgePlaytest), then the console in game
        self.phase = "boot-B-continue"
        self._focus()
        self.p.press("esc")                               # close the console if A left it open
        self.p.sleep(0.5)
        self.p.press("enter")                             # NorthernUI: Enter activates the focused Continue
        self.note("B: pressed Enter (Continue) at the main menu")
        if not self.wait_load_start(10):
            self.p.press("down", "enter")
            self.note("B: pressed Down, Enter")
            if not self.wait_load_start(10):
                self.shot("B-no-load")
                raise PlaytestError(f"Continue did not load the test save (menus {self._menus()})")
        if not self.wait_loaded(self.opts.boot_timeout):
            self.shot("B-load-timeout")
            raise PlaytestError("the test save never finished loading")
        self.idle(1.0)
        self.console(command)
        if not (self.wait_load_start(15) and self.wait_loaded(self.opts.boot_timeout)):
            self.shot("B-coc-timeout")
            raise PlaytestError(f"`{command}` from the in-game console did not load")
        return "B: Continue + in-game console"

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

    def console(self, command: str, at_menu: bool = False) -> None:
        if not self._focus():
            self.shot("no-focus")
            raise PlaytestError("could not bring the test game to the front")
        if at_menu:
            self.p.press("tilde")
            self.p.sleep(0.5)
            self.shot("console-at-menu")
        elif not self._console_open():
            before = self.p.grab(self.p.window(self.pid))
            self.p.press("tilde")
            opened = _wait(self.p, self._console_open, 2.0, 0.1)
            if not opened:
                after = self.p.grab(self.p.window(self.pid))
                if self.p.console_visible(before, after):
                    opened = True
                    self._screen_console = True
                    self.note("console open (seen on screen; the menu probe did not show it)")
            if not opened:
                self.shot("console-not-open")
                if self.p.hung(self.p.window(self.pid)):
                    self.idle(self.opts.hang_seconds + 1)     # a freeze: let tick() confirm and close it
                raise PlaytestError(f"the console did not open; not typing into the game (state {self._state()})")
        if not self.p.focused(self.pid):
            raise PlaytestError("the test game lost focus while typing")
        self.p.type_text(command)
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
        """Run one batch once (never retried: a second run would repeat its steps)."""
        self.phase = f"batch {command}"
        size = game_log.stat().st_size if game_log.is_file() else 0
        self.console(command)
        ok = _wait(self.p, lambda: game_log.is_file() and game_log.stat().st_size > size, 3.0, 0.2)
        self.close_console()
        return bool(ok)
