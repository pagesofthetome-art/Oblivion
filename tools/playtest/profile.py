"""The test profile: a throw-away Plugins.txt + Oblivion.ini, swapped in under a restore journal.

Method (and why). Oblivion has no switch for another Plugins.txt or Oblivion.ini: it always reads
%LOCALAPPDATA%\\Oblivion\\Plugins.txt and Documents\\My Games\\Oblivion\\Oblivion.ini, and on this
PC the Steam (Rebirth+) and GOG copies share both. So the profile is built in its own folder
(forge-builds\\playtest\\profile\\) and swapped in for the length of one test run:

  1. Refuse while any Oblivion.exe / OblivionLauncher.exe / obse_loader.exe / the CS is running.
  2. Copy the real Plugins.txt and Oblivion.ini into the profile's backup\\ folder and write
     restore-journal.json (with their SHA-256) to disk, fsynced, BEFORE anything changes.
  3. Replace them atomically with the test copies. Stage the test plugins, mesh kit and batch
     files into the clean GOG copy (Desktop\\Games\\Oblivion), recording every created file in
     the journal first. Existing files are never overwritten.
  4. Restore = put the originals back byte for byte, check their hashes, delete only the files we
     created (and only if unchanged), then delete the journal. It is idempotent.

Restore runs in a finally block when the game exits; a detached guardian process does it if forge
itself dies; and every `forge playtest` / `forge test` run first finishes any journal left over by
a power cut. `forge playtest restore` does it by hand.

The game is the clean GOG copy, never the Steam copy: no Vortex hardlinks to damage, no Steam
launcher route (the main-menu freezes in Controller\\_project_notes.md all came from that route).
Writes into the Steam folder, a folder with vortex.deployment.json, or any Vortex folder are
refused outright.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

JOURNAL = "restore-journal.json"
OFFICIAL_DLC = ["DLCShiveringIsles.esp", "Knights.esp", "DLCBattlehornCastle.esp", "DLCFrostcrag.esp",
                "DLCHorseArmor.esp", "DLCMehrunesRazor.esp", "DLCOrrery.esp", "DLCSpellTomes.esp",
                "DLCThievesDen.esp", "DLCVileLair.esp"]
GAME_PROCESSES = {"oblivion.exe", "oblivionlauncher.exe", "obse_loader.exe", "tesconstructionset.exe"}
SAVE_DIR = "Saves\\ForgePlaytest\\"
# ini changes for the test profile: no intro videos, separate save folder, no autosaves
INI_OVERRIDES = [
    ("General", "SIntroSequence", ""),
    ("General", "SMainMenuMovieIntro", ""),
    ("General", "SLocalSavePath", SAVE_DIR),
    ("GamePlay", "bSaveOnRest", "0"),
    ("GamePlay", "bSaveOnWait", "0"),
    ("GamePlay", "bSaveOnTravel", "0"),
    ("GamePlay", "bSaveOnInteriorExteriorSwitch", "0"),
]


class ProfileError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fsync_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".forge-tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


# ---------------------------------------------------------------- the machine
@dataclass
class Machine:
    plugins_txt: Path
    ini: Path
    game_dir: Path                       # the test game (clean GOG copy)
    state_dir: Path                      # forge-builds\playtest
    play_dirs: list[Path] = field(default_factory=list)     # play installs: read-only, never written
    vortex_dirs: list[Path] = field(default_factory=list)
    master_dirs: list[Path] = field(default_factory=list)   # where to copy missing masters FROM

    @property
    def data(self) -> Path:
        return self.game_dir / "Data"

    @property
    def profile_dir(self) -> Path:
        return self.state_dir / "profile"

    @property
    def journal(self) -> Path:
        return self.profile_dir / JOURNAL

    @property
    def save_dir(self) -> Path:
        """Where the test profile's saves go (SLocalSavePath in the test ini)."""
        return self.ini.parent / SAVE_DIR.rstrip("\\").replace("\\", "/")

    @classmethod
    def detect(cls, env=None, repo: Path | None = None) -> "Machine":
        """Paths on Yuri's PC; every one can be overridden with an environment variable."""
        env = os.environ if env is None else env
        repo = repo or Path(__file__).resolve().parents[2]
        home = Path(env.get("USERPROFILE") or Path.home())
        local = Path(env.get("LOCALAPPDATA") or home / "AppData" / "Local")
        roaming = Path(env.get("APPDATA") or home / "AppData" / "Roaming")
        steam = Path(env.get("FORGE_PLAYTEST_STEAM_DIR")
                     or r"C:\Program Files (x86)\Steam\steamapps\common\Oblivion")
        docs = _documents_dir() or home / "Documents"
        state = Path(env.get("FORGE_PLAYTEST_STATE_DIR") or repo / "forge-builds" / "playtest")
        cfg = {}
        cfg_path = state / "machine.json"
        if cfg_path.is_file():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except ValueError:
                raise ProfileError(f"{cfg_path} is not valid JSON") from None
        game = env.get("FORGE_PLAYTEST_GAME_DIR") or cfg.get("game_dir") or _find_gog(repo)
        if cfg.get("steam_dir") and not env.get("FORGE_PLAYTEST_STEAM_DIR"):
            steam = Path(cfg["steam_dir"])
        m = cls(
            plugins_txt=Path(env.get("FORGE_PLAYTEST_PLUGINS_TXT") or cfg.get("plugins_txt")
                             or local / "Oblivion" / "Plugins.txt"),
            ini=Path(env.get("FORGE_PLAYTEST_INI") or cfg.get("ini") or docs / "My Games" / "Oblivion" / "Oblivion.ini"),
            game_dir=Path(game),
            state_dir=state,
            play_dirs=[steam],
            vortex_dirs=[roaming / "Vortex"],
            master_dirs=[steam / "Data"],
        )
        return m

    def check_safe(self) -> None:
        """Refuse a test game that is (or could be) the Rebirth+ play setup."""
        g = self.game_dir.resolve()
        parts = [p.casefold() for p in g.parts]
        if "steamapps" in parts or "vortex" in parts:
            raise ProfileError(f"refusing to use {g} as the test game: it is the Steam/Vortex play copy")
        for p in self.play_dirs:
            if p.exists() and _same_or_inside(g, p.resolve()):
                raise ProfileError(f"refusing to use {g} as the test game: it is the play copy {p}")
        if (g / "Data" / "vortex.deployment.json").exists():
            raise ProfileError(f"refusing to use {g}: Vortex deploys into it (Data\\vortex.deployment.json)")
        if not (g / "Data" / "Oblivion.esm").is_file():
            raise ProfileError(f"test game not found: {g}\\Data\\Oblivion.esm is missing "
                               "(set FORGE_PLAYTEST_GAME_DIR to the clean GOG copy)")
        st = self.state_dir.resolve()
        if _same_or_inside(st, g) or any(_same_or_inside(st, p.resolve()) for p in self.play_dirs if p.exists()):
            raise ProfileError("the playtest state folder must not be inside a game folder")

    def check_writable(self, path: Path) -> None:
        """Every write outside the state folder goes through here."""
        p = path.resolve()
        allowed = [self.game_dir.resolve(), self.plugins_txt.resolve(), self.ini.resolve(), self.state_dir.resolve()]
        if any("vortex" == x.casefold() for x in p.parts) or "steamapps" in [x.casefold() for x in p.parts]:
            raise ProfileError(f"refusing to write {p}: Steam/Vortex folders are never written")
        for d in self.play_dirs + self.vortex_dirs:
            if d.exists() and _same_or_inside(p, d.resolve()):
                raise ProfileError(f"refusing to write {p}: inside {d}")
        if not any(p == a or _same_or_inside(p, a) for a in allowed):
            raise ProfileError(f"refusing to write {p}: outside the test game and the profile")


def _find_gog(repo: Path) -> Path:
    r"""The clean GOG copy: <repo>\Oblivion, else a sibling Oblivion folder (Desktop\Games\Oblivion
    next to a clone in Desktop\Games\Oblivion-repo). Override: FORGE_PLAYTEST_GAME_DIR or
    forge-builds\playtest\machine.json {"game_dir": ...}."""
    for cand in (repo / "Oblivion", repo.parent / "Oblivion"):
        data = cand / "Data"
        if (data / "Oblivion.esm").is_file() and not (data / "vortex.deployment.json").exists():
            return cand
    return repo / "Oblivion"


def _documents_dir() -> Path | None:
    """The real Documents folder (it can be moved, e.g. into OneDrive); Oblivion asks Windows the same way."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        import uuid
        from ctypes import wintypes
        guid = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")      # FOLDERID_Documents
        buf = ctypes.c_wchar_p()
        fn = ctypes.windll.shell32.SHGetKnownFolderPath
        fn.argtypes = [ctypes.c_char_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        if fn(guid.bytes_le, 0, None, ctypes.byref(buf)) != 0:
            return None
        try:
            return Path(buf.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(buf)
    except (OSError, AttributeError, ValueError):
        return None


def _same_or_inside(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------- ini / Plugins.txt
def ini_set(text: str, section: str, key: str, value: str) -> str:
    """Set key=value inside [section], keeping everything else (and the line endings) as is."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    sec_re = re.compile(r"^\s*\[(.+?)\]\s*$")
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*=", re.I)
    cur, sec_end, found = None, None, False
    for i, line in enumerate(lines):
        m = sec_re.match(line)
        if m:
            if cur is not None and cur.lower() == section.lower() and sec_end is None:
                sec_end = i
            cur = m.group(1)
            continue
        if cur is not None and cur.lower() == section.lower() and key_re.match(line):
            lines[i] = f"{key}={value}"
            found = True
    if found:
        return nl.join(lines)
    if cur is not None and cur.lower() == section.lower() and sec_end is None:
        sec_end = len(lines)
        while sec_end > 0 and lines[sec_end - 1] == "":
            sec_end -= 1
    if sec_end is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines[-1:] = [f"[{section}]", f"{key}={value}", ""]
        return nl.join(lines)
    lines.insert(sec_end, f"{key}={value}")
    return nl.join(lines)


def test_ini(real_ini: bytes, extra: list[tuple[str, str, str]] = ()) -> bytes:
    text = real_ini.decode("cp1252", "replace")
    for section, key, value in list(INI_OVERRIDES) + list(extra):
        text = ini_set(text, section, key, value)
    return text.encode("cp1252", "replace")


def plugins_txt(active: list[str]) -> bytes:
    lines = ["# TES4Forge playtest profile. The real Plugins.txt is restored when the test game exits."]
    lines += active
    return ("\r\n".join(lines) + "\r\n").encode("cp1252")


def is_esm(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(12)
        return head[:4] == b"TES4" and bool(int.from_bytes(head[8:12], "little") & 1)
    except OSError:
        return path.suffix.lower() == ".esm"


def load_order(data: Path, active: list[str]) -> list[str]:
    """Oblivion's real order: master files first, then by file modification time."""
    files = []
    for name in active:
        p = data / name
        if not p.is_file():
            raise ProfileError(f"active plugin missing from the test game: {p}")
        files.append((0 if is_esm(p) else 1, p.stat().st_mtime, name.lower(), name))
    return [f[3] for f in sorted(files)]


# ---------------------------------------------------------------- journal
class Session:
    """One swap-in of the test profile. Use as a context manager or call apply()/restore()."""

    def __init__(self, machine: Machine, log=print):
        self.m = machine
        self.log = log
        self.j: dict | None = None

    # -- journal i/o
    def _save(self) -> None:
        self.m.profile_dir.mkdir(parents=True, exist_ok=True)
        _fsync_write(self.m.journal, json.dumps(self.j, indent=1).encode("utf-8"))

    def begin(self) -> None:
        if self.m.journal.exists():
            raise ProfileError(f"a restore journal is still open ({self.m.journal}); run `forge playtest restore`")
        backup = self.m.profile_dir / "backup"
        if backup.exists():
            shutil.rmtree(backup)
        backup.mkdir(parents=True)
        swaps = []
        for target in (self.m.plugins_txt, self.m.ini):
            entry = {"target": str(target), "existed": target.is_file()}
            if target.is_file():
                b = backup / target.name
                shutil.copy2(target, b)
                entry.update(backup=str(b), sha256=sha256(target))
                if sha256(b) != entry["sha256"]:
                    raise ProfileError(f"backup of {target} does not match the original")
            swaps.append(entry)
        self.j = {"version": 1, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "forge_pid": os.getpid(),
                  "game_pid": None, "swaps": swaps, "created_files": [], "created_dirs": [], "collect": []}
        self._save()

    def swap_in(self, target: Path, data: bytes) -> None:
        if not any(Path(s["target"]) == target for s in self.j["swaps"]):
            raise ProfileError(f"{target} is not journaled")
        self.m.check_writable(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        _fsync_write(target, data)

    def stage(self, dest: Path, data: bytes | None = None, src: Path | None = None, mtime: float | None = None) -> bool:
        """Create a new file in the test game. Returns False if an identical file was already there."""
        self.m.check_writable(dest)
        if data is None:
            data = src.read_bytes()
        h = hashlib.sha256(data).hexdigest()
        if dest.exists():
            if sha256(dest) == h:
                return False
            raise ProfileError(f"{dest} already exists with other content; not overwriting it")
        missing = []
        d = dest.parent
        while not d.exists():
            missing.append(d)
            d = d.parent
        for d in reversed(missing):
            self.j["created_dirs"].append(str(d))
        self.j["created_files"].append({"path": str(dest), "sha256": h})
        self._save()                                          # journal first, then the write
        dest.parent.mkdir(parents=True, exist_ok=True)
        _fsync_write(dest, data)
        if mtime is not None:
            os.utime(dest, (mtime, mtime))
        return True

    def collect(self, path: Path) -> None:
        """A file the game will create (e.g. forge_test.log): deleted on restore, whatever it holds."""
        self.m.check_writable(path)
        if path.exists():
            raise ProfileError(f"{path} already exists; delete it or run `forge playtest restore`")
        self.j["collect"].append(str(path))
        self._save()

    def set_game_pid(self, pid: int) -> None:
        self.j["game_pid"] = pid
        self._save()

    # -- restore
    def restore(self) -> list[str]:
        return restore(self.m, log=self.log)


def restore(m: Machine, log=print) -> list[str]:
    """Undo whatever the journal records. Safe to call any number of times. Returns notes."""
    if not m.journal.exists():
        return []
    j = json.loads(m.journal.read_text(encoding="utf-8"))
    notes, failures = [], []
    for s in j.get("swaps", []):
        t = Path(s["target"])
        if s.get("existed"):
            b = Path(s["backup"])
            if not b.is_file() or sha256(b) != s["sha256"]:
                failures.append(f"backup of {t} is missing or damaged: {b}")
                continue
            if not t.is_file() or sha256(t) != s["sha256"]:
                _fsync_write(t, b.read_bytes())
                shutil.copystat(b, t)
            if sha256(t) != s["sha256"]:
                failures.append(f"{t} could not be restored")
            else:
                notes.append(f"restored {t}")
        elif t.exists():
            t.unlink()
            notes.append(f"removed {t} (did not exist before)")
    for path in j.get("collect", []):
        p = Path(path)
        if p.exists():
            p.unlink()
    for f in reversed(j.get("created_files", [])):
        p = Path(f["path"])
        if not p.exists():
            continue
        if sha256(p) == f["sha256"]:
            p.unlink()
        else:
            notes.append(f"left {p}: it changed during the test (check it by hand)")
    for d in reversed(j.get("created_dirs", [])):
        p = Path(d)
        try:
            p.rmdir()
        except OSError:
            pass
    if failures:
        raise ProfileError("restore incomplete, journal kept: " + "; ".join(failures))
    m.journal.unlink()
    for n in notes:
        log(f"  {n}")
    return notes


def status(m: Machine) -> dict:
    if not m.journal.exists():
        return {"open": False}
    j = json.loads(m.journal.read_text(encoding="utf-8"))
    return {"open": True, "created": j.get("created"), "game_pid": j.get("game_pid"),
            "forge_pid": j.get("forge_pid"), "files": len(j.get("created_files", []))}


def python_exe() -> str:
    """pythonw on Windows for the detached guardian (no console window), else this interpreter."""
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "python.exe" and (exe.parent / "pythonw.exe").is_file():
        return str(exe.parent / "pythonw.exe")
    return str(exe)
