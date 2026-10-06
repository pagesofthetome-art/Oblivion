"""forge playtest: build the test profile, quick-boot into a test cell, run the checks, restore.

Boot sequence (all automatic; nothing waits for a key press from Yuri):
  1. obse_loader.exe in the clean GOG copy, with the test Oblivion.ini: intro videos off.
  2. At the main menu the driver opens the console and types `coc <test cell>`: Oblivion starts a
     game with a default character directly in that cell (no character creation, no tutorial dungeon).
  3. After the load it runs `bat fpt1` (then fpt2... after each wait); the batches log to
     forge_test.log. Boot time = command start until the cell has loaded and the player is in
     control (the log's GetInCell line confirms the cell).
  4. The game stays open to play with the pad (or quits with --quit). Restore runs when it exits.

While the game runs the driver watches: the freeze probe (Controller\\oblivion_freeze.py) and
Windows' "not responding" state, killing the game after --hang-seconds of a confirmed freeze; and
the vanilla Persuasion tutorial page that ignores the controller (auto-dismissed with Down, Enter).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from playtest import manifest as mf, platform as plat, profile, testcells, testlog

TOOLS = Path(__file__).resolve().parents[1]


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
    plugin: Path
    plan: dict
    spec_name: str | None
    spec_path: Path | None = None


@dataclass
class Prepared:
    target: Target
    cell_key: str
    active: list[str]
    stage: list[tuple[Path, Path | None, bytes | None]] = field(default_factory=list)  # dest, src, data
    testcells_dir: Path | None = None
    layout: dict | None = None


# ---------------------------------------------------------------- target
def resolve_target(path: str | Path, opts: Options, m: profile.Machine) -> Target:
    p = Path(path).resolve()
    plan_src = None
    if p.suffix.lower() in (".esp", ".esm"):
        if not p.is_file():
            raise PlaytestError(f"plugin not found: {p}")
        if opts.manifest:
            plan_src = _read_any(opts.manifest)
        else:
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
    if pt.get("plugin"):
        plugin = s.resolve(pt["plugin"])
    else:
        plugin = s.output_dir() / s.output_plugin
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


def testcells_build(m: profile.Machine, with_kit: bool = True) -> tuple[Path, dict]:
    """ForgeTestCells.esp + layout + mesh kit, cached in forge-builds\\playtest\\testcells."""
    out = m.state_dir / "testcells"
    esp, lj = testcells.write(out)
    kit = out / "Data"
    stamp = kit / "kit.ok"
    if with_kit and not stamp.is_file():
        files = testcells.build_kit(kit)
        stamp.write_text("\n".join(str(f.relative_to(kit)) for f in files), encoding="utf-8")
    return esp, json.loads(lj.read_text(encoding="utf-8"))


def prepare(t: Target, opts: Options, m: profile.Machine, with_kit: bool = True) -> Prepared:
    data = m.data
    cell = testcells.cell_key(opts.cell or t.plan.get("cell"))
    tc_esp, lay = testcells_build(m, with_kit)
    active = ["Oblivion.esm"] + [d for d in profile.OFFICIAL_DLC if (data / d).is_file()]
    stage: list[tuple[Path, Path | None, bytes | None]] = []
    # masters of the mod (recursively), staged from next to the plugin or the play copy (read-only)
    order: list[str] = []

    def need(plugin: Path):
        for name in _masters(plugin):
            if name.lower() in (x.lower() for x in active + order):
                continue
            src = data / name if (data / name).is_file() else _find_master(name, t.plugin.parent, m)
            if src is None:
                raise PlaytestError(f"master {name} of {plugin.name} not found in the test game, next to the "
                                    "plugin, or in the play copy's Data")
            need(src)
            order.append(name)
            if not (data / name).is_file():
                stage.append((data / name, src, None))

    need(t.plugin)
    if t.plugin.name.lower() == testcells.PLUGIN_NAME.lower():
        raise PlaytestError("pick a mod to test, not ForgeTestCells.esp itself")
    active += order + [t.plugin.name, testcells.PLUGIN_NAME]
    if (data / t.plugin.name).resolve() != t.plugin.resolve():
        stage.append((data / t.plugin.name, t.plugin, None))
    stage.append((data / testcells.PLUGIN_NAME, tc_esp, None))
    kit = m.state_dir / "testcells" / "Data"
    if with_kit:
        for f in sorted(kit.rglob("*")):
            if f.is_file() and f.suffix.lower() in (".nif", ".dds"):
                stage.append((data / f.relative_to(kit), f, None))
    return Prepared(t, cell, active, stage, kit.parent, lay)


def _forms(prep: Prepared, m: profile.Machine, lo: list[str]) -> mf.FormTable:
    import tes4_plugin as tp
    masters = {}
    recs = {}
    for name in lo:
        p = m.data / name
        if name.lower() in (prep.target.plugin.name.lower(), testcells.PLUGIN_NAME.lower()):
            pl = tp.load(p)
            masters[name] = list(pl.masters)
            recs[name] = [(r.editor_id, r.form_id, r.sig) for r in pl.records]
        else:
            masters[name] = list(tp.read_header(p).masters)
    ft = mf.FormTable(lo, masters)
    for name in (prep.target.plugin.name, testcells.PLUGIN_NAME):     # the mod's names win
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


def run(target_path: str | Path, opts: Options, m: profile.Machine | None = None,
        p: plat.Platform | None = None) -> dict:
    m = m or profile.Machine.detect()
    p = p or plat.default()
    log = opts.log
    t0 = p.now()
    leftover = profile.restore(m, log=log)
    if leftover:
        log("finished restoring an earlier playtest that did not close cleanly")
    notes = preflight(m, p)
    for n in notes:
        log(f"note: {n}")
    t = resolve_target(target_path, opts, m)
    prep = prepare(t, opts, m)
    cell = testcells.CELLS[prep.cell_key]
    run_dir = m.state_dir / "runs" / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    before = hashes(m)
    real_ini = m.ini.read_bytes() if m.ini.is_file() else b""
    sess = profile.Session(m, log=log)
    result: dict = {"verdict": "NOT-RUN"}
    man = None
    try:
        sess.begin()
        sess.swap_in(m.plugins_txt, profile.plugins_txt(prep.active))
        sess.swap_in(m.ini, profile.test_ini(real_ini))
        newest = max((m.data / n).stat().st_mtime for n in prep.active if (m.data / n).is_file())
        stamp = newest + 60
        for dest, src, data in prep.stage:
            mt = None
            if dest.suffix.lower() in (".esp", ".esm"):
                mt, stamp = stamp, stamp + 60                 # load after everything already there
            sess.stage(dest, data=data, src=src, mtime=mt)
        lo = profile.load_order(m.data, prep.active)
        forms = _forms(prep, m, lo)
        man = mf.build(t.plan, forms, cell_edid=cell["edid"], start_ref=cell["start"], plugin=t.plugin.name,
                       spec=t.spec_name)
        mf.save(man, run_dir / "playtest_manifest.json")
        for c in man["chunks"]:
            sess.stage(m.game_dir / c["file"], data=("\r\n".join(c["lines"]) + "\r\n").encode("cp1252"))
        game_log = m.game_dir / mf.LOG_NAME
        sess.collect(game_log)
        log(f"test profile on: {len(prep.active)} plugins ({', '.join(prep.active[-3:])}), cell {cell['edid']}")
        extra = {"boot_seconds": None, "froze": False, "dry_run": opts.dry_run}
        if opts.dry_run:
            log("dry run: profile built and staged; not launching")
        else:
            extra.update(_play(m, p, sess, man, cell, opts, t0, run_dir))
        if game_log.is_file():
            shutil.copy2(game_log, run_dir / mf.LOG_NAME)
        result = testlog.evaluate(man, run_dir / mf.LOG_NAME if (run_dir / mf.LOG_NAME).is_file() else None, extra)
        if opts.dry_run:
            result["verdict"] = "DRY-RUN"
    finally:
        try:
            profile.restore(m, log=log)
        finally:
            after = hashes(m)
            check = {k: {"before": before[k], "after": after[k], "same": before[k] == after[k]} for k in before}
            result["restore_check"] = check
            result["run_dir"] = str(run_dir)
            (run_dir / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
            (m.state_dir / "last-run.txt").write_text(str(run_dir), encoding="utf-8")
            if not all(v["same"] for v in check.values()):
                log("WARNING: Plugins.txt or Oblivion.ini differ from before the test; see result.json")
    return result


def _play(m, p: plat.Platform, sess: profile.Session, man: dict, cell: dict, opts: Options, t0: float,
          run_dir: Path) -> dict:
    log = opts.log
    out = {"boot_seconds": None, "froze": False, "events": []}
    ev = out["events"]

    def note(msg):
        ev.append([round(p.now() - t0, 2), msg])
        log(f"[{p.now() - t0:5.1f}s] {msg}")

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
    drv = Driver(p, pid, opts, note)
    game_log = m.game_dir / mf.LOG_NAME
    try:
        if not drv.wait_main_menu(opts.boot_timeout):
            raise PlaytestError("the main menu never appeared")
        drv.console(f"coc {cell['edid']}")
        note(f"coc {cell['edid']}")
        if not drv.wait_loaded(opts.boot_timeout):
            raise PlaytestError(f"{cell['edid']} did not finish loading")
        out["boot_seconds"] = round(p.now() - t0, 2)
        note(f"playing in {cell['edid']} after {out['boot_seconds']}s")
        for c in man["chunks"]:
            if c["wait_before"]:
                drv.idle(c["wait_before"])
            if not drv.run_batch(c["command"], game_log):
                note(f"{c['command']}: nothing in the log yet (Oblivion may buffer it until `scof 0`)")
        drv.idle(1.0)
        res = testlog.evaluate(man, game_log if game_log.is_file() else None)
        note(f"checks done: {res['verdict']} ({res['passed']}/{res['checks']})")
        if opts.quit_when_done:
            drv.console("qqq")
            note("quit")
        else:
            log("Keep playing with the pad. Your normal setup comes back when you exit the game.")
        drv.until_exit()
    except Exception as exc:
        note(f"error: {exc}")
        out["error"] = str(exc)
        if p.alive(pid):
            p.kill(pid)
            note("test game closed")
    out["froze"] = drv.froze
    if drv.froze:
        fr = plat.CONTROLLER / "freeze_report.txt"
        out["freeze_report"] = str(fr)
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
        if name.lower() == "oblivion.exe" and path.lower().startswith(root):
            return pid
    return None


def _start_companion(p: plat.Platform) -> None:
    script = plat.CONTROLLER / "oblivion_controller.py"
    if script.is_file():
        p.spawn_detached([profile.python_exe(), str(script), "--nogui"])


class Driver:
    """Types into the test game only (checks the window belongs to our pid before every key)."""

    def __init__(self, p: plat.Platform, pid: int, opts: Options, note):
        self.p, self.pid, self.opts, self.note = p, pid, opts, note
        self.froze = False
        self._frozen_since = None
        self._tut_since = None

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
        elif self._frozen_since and now - getattr(self, "_last_bad", now) > 8:
            self._frozen_since = None
        if self._frozen_since and now - self._frozen_since >= self.opts.hang_seconds:
            self.froze = True
            self.note(f"frozen for {self.opts.hang_seconds:.0f}s: closing the test game")
            p.kill(self.pid)
            raise PlaytestError("game froze")
        st = p.ui_state(self.pid)
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
        while self.p.alive(self.pid):
            self.tick()
            self.p.sleep(0.5)

    # -- states
    def _state(self) -> dict:
        return self.p.ui_state(self.pid)

    def wait_main_menu(self, timeout: float) -> bool:
        end = self.p.now() + timeout
        seen = None
        while self.p.now() < end:
            self.tick()
            win = self.p.window(self.pid)
            st = self._state()
            if plat.MENU_MAIN in st.get("menus", []):
                self.p.sleep(0.5)
                return True
            if win and seen is None:
                seen = self.p.now()
            if seen and self.p.now() - seen > 25 and plat.MENU_LOADING not in st.get("menus", []):
                return True                                # no menu probe: assume the menu is up
            self.p.sleep(0.25)
        return False

    def wait_loaded(self, timeout: float) -> bool:
        end = self.p.now() + timeout
        saw_loading = False
        while self.p.now() < end:
            self.tick()
            st = self._state()
            menus = st.get("menus", [])
            if plat.MENU_LOADING in menus or plat.MENU_MAIN in menus:
                saw_loading = saw_loading or plat.MENU_LOADING in menus
            elif not st.get("menu_mode") or saw_loading:
                self.p.sleep(1.0)
                return True
            self.p.sleep(0.25)
        return False

    def _focus(self) -> bool:
        if self.p.focused(self.pid):
            return True
        win = self.p.window(self.pid)
        return bool(win) and self.p.focus(win[0]) and self.p.focused(self.pid)

    def _console_open(self) -> bool:
        st = self._state()
        real = [x for x in st.get("menus", []) if x not in (1004, 1005, 1006, 1010, 1045)]
        return bool(st.get("menu_mode")) and not real

    def console(self, command: str) -> None:
        if not self._focus():
            raise PlaytestError("could not bring the test game to the front")
        at_menu = plat.MENU_MAIN in self._state().get("menus", [])
        if not at_menu and not self._console_open():
            self.p.press("tilde")
            if not _wait(self.p, self._console_open, 2.0, 0.1):
                if self.p.hung(self.p.window(self.pid)):
                    self.idle(self.opts.hang_seconds + 1)     # a freeze: let tick() confirm and close it
                raise PlaytestError("the console did not open; not typing into the game")
        elif at_menu:
            self.p.press("tilde")
            self.p.sleep(0.3)
        if not self.p.focused(self.pid):
            raise PlaytestError("the test game lost focus while typing")
        self.p.type_text(command)
        self.p.press("enter")
        self.p.sleep(0.3)

    def close_console(self) -> None:
        if self._console_open():
            self.p.press("tilde")
            _wait(self.p, lambda: not self._console_open(), 2.0, 0.1)

    def run_batch(self, command: str, game_log: Path) -> bool:
        """Run one batch once (never retried: a second run would repeat its steps)."""
        size = game_log.stat().st_size if game_log.is_file() else 0
        self.console(command)
        ok = _wait(self.p, lambda: game_log.is_file() and game_log.stat().st_size > size, 3.0, 0.2)
        self.close_console()
        return bool(ok)
