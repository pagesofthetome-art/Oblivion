# Oblivion with a PS5 controller (NorthernUI + companion), v3

Two pieces work together:

| Piece | What it does |
|---|---|
| **NorthernUI** (the files in this folder: `Fonts\ menus\ Meshes\ OBSE\ Textures\`) | An OBSE plugin and a console-style interface. It gives Oblivion **native controller support**: analog movement, camera, and menus you navigate with the stick. It shows PlayStation button icons. It reads the controller as an **Xbox (XInput) pad**. |
| **`oblivion_controller.py`** (companion) | Adds what NorthernUI lacks: **hotkeys 1–8**, **mouse-wheel scrolling** and an **on-screen keyboard** for name boxes. With NorthernUI installed it touches nothing else. Without NorthernUI it falls back to full keyboard+mouse emulation (*standalone* mode). |

## How the controller reaches the game (audited 2026-10-04)

`PS5 pad (Bluetooth) → your device → Shadow → virtual Xbox 360 controller (XInput, VID 045E PID 028E) → NorthernUI → Oblivion`

Nothing else may sit in that chain:

- **Steam Input must be OFF for Oblivion.** It was ON with Steam's *Keyboard (WASD) and Mouse* layout (`controller_xbox360_wasd.vdf`). Steam hid the controller from the game and turned it into keys and mouse movement. That caused the digits in name boxes, the mouse cursor and the clicks you didn't make. NorthernUI never got a gamepad. `Play Oblivion.bat` now runs `steam_check.py --fix` every time. It sets Oblivion's Steam Input to *Disabled* and removes that layout (backups `*.bak-oblivion-*`). If Steam is running when a fix is needed, it asks you to exit Steam first. Your DayZ layout is untouched.
- **Exactly one XInput controller.** Two (e.g. Shadow + a Steam virtual pad) would give double input.
- **No remappers.** Close DS4Windows, Xpadder, reWASD and the like. Turn off Shadow's *Gamepad as mouse*.
- **Controls are NorthernUI's *Console* scheme,** the Xbox 360 / PS3 layout, set in `Documents\My Games\Oblivion\NorthernUI.ctrl.txt`:

| PS5 | Console action |
|---|---|
| Left stick / right stick | Move / look |
| R2 / L2 | Attack / block |
| R1 / L1 | Cast / grab |
| Cross / Circle | Activate / menus (journal) |
| Square / Triangle | Ready weapon / jump |
| L3 / R3 | Sneak / toggle view |
| Create / Options | Wait / pause |
| D-pad | Hotkeys 1–8 (the companion) |
| L2 + Triangle / L2 + Cross | Dodge / yield |

**Verify everything with `Check controller.bat`.** It checks Steam, the XInput controller count, the NorthernUI scheme and conflicting mods. Then it asks you to press every button and move both sticks. For each input it records whether any keyboard or mouse event appeared at the same time (there must be none). The result goes to `controller_audit.txt`.

## Setup

1. **Shadow: present the PS5 controller as an Xbox controller.** NorthernUI only understands Xbox-style input. Check it in Windows: `Win+R` → `joy.cpl` should list an Xbox / XInput controller.
2. **Install NorthernUI:** double-click `install_northernui.bat`. It copies the files into `Oblivion\Data` (nothing of yours is overwritten; anything it would replace is backed up). It also sets two NorthernUI options:
   - `bUsePlaystationButtonIcons=TRUE`: PS button icons and names.
   - `bMenuConsumesDPad=FALSE`: the D-pad is left for hotkeys and typing. Menus are navigated with the left stick.

   Undo everything with `install_northernui.bat --uninstall`. See what's installed with `--check`.
3. **Start the companion:** double-click `run_oblivion_controller.bat` (the first run installs `pygame-ce`). The window should say **NORTHERNUI mode**.
4. **Start the game with `Oblivion\obse_loader.exe`.** NorthernUI is an OBSE plugin, so it only loads that way. In the game, pick a control scheme in NorthernUI's controls menu. *Dutiful* (R2 attack, L2 block, R1 cast) is the closest to the console layout.

## Oblivion Rebirth+ (Steam copy, deployed by Vortex)

Vortex deploys the Rebirth+ collection into `C:\Program Files (x86)\Steam\steamapps\common\Oblivion`. The companion and `Play Oblivion.bat` use that install automatically. They pick it because it has `Data\vortex.deployment.json` and xOBSE. To force a folder, set `"game_dir"` in `oblivion_controller_config.json`. Check which one is used with `py oblivion_controller.py --print-game-dir`.

What was added to the Steam copy, outside Vortex:
- **xOBSE 22.13:** `obse_loader.exe`, `obse_1_2_416.dll`, `obse_steam_loader.dll`, `obse_editor_1_2.dll` and `Data\OBSE\obse.ini`. The collection needs it for NorthernUI, Oblivion Reloaded, MenuQue, Blockhead and its other script-extender plugins. Keep Steam running when you launch.
- **`Data\OBSE\Plugins\NorthernUI.ini`:** only `bUsePlaystationButtonIcons=TRUE`. `bMenuConsumesDPad` stays at the collection's `TRUE`.
- **`Data\Textures\Menus\misc\cursor.dds`:** a fully transparent mouse cursor, so no pointer ever shows (console style). NorthernUI's `fAutoHideCursorDelay` is also set to 0.1 s. The world/local map keeps NorthernUI's stick-driven map cursor, as on console. To get the pointer back, reinstall *Smaller Cursor for Imperial NorthernUI* in Vortex.
- **`Data\menus\chargen\race_sex_menu.xml`:** the Done-button fix.

These are Vortex-managed files. On the next deploy, Vortex may report *external changes*. Choose **Save change** (keep) so the fixes stay.

**Start Steam before the game (the companion does it for you).** When Steam is not running, xOBSE hands the start to a freshly started Steam: `steam -applaunch 22330`, then `OblivionLauncher.exe`, then `Oblivion.exe`, with the Steam overlay injected. Steam's own logs show what happened on 2026-10-05:
- **Freezes:** all three main-menu freezes (12:55, 13:01, 13:34) went that way. In each, the game stopped drawing about 30 s after start, right as the main menu came up. Steam's overlay logged *"The game hasn't rendered a frame in over 10 seconds"* from then on, before any button was pressed. The music kept playing.
- **Good sessions:** the working sessions that day (12:16, 12:49) started with Steam already running. Oblivion was then launched directly.

So *Save settings & start Oblivion* now first checks for Steam. If Steam is not running, the companion starts it silently in the background (`steam.exe -silent`, no window), waits until it is logged in, then launches xOBSE.

**Freeze probe.** If Oblivion ever stops while it is the window in front, the companion records where the game is stuck. That covers Windows' *Not Responding*, or the game's main thread doing nothing for 6 s.
- **What it records:** the main thread's call stack as `module+offset` (e.g. `NorthernUI.dll+0x1A2B3`), plus every window Oblivion owns.
- **Hidden message box:** a Windows message box hidden behind the borderless game window looks exactly like a freeze. The probe brings such a box to the front and logs its text.
- **Where it goes:** the result is written to `freeze_report.txt` and `controller_log.txt`. The log from the run before is kept as `controller_log.previous.txt`.
- **Read-only:** the game's main thread is paused for well under a millisecond to copy its registers and stack, then resumed. Nothing in the game is changed. See `oblivion_freeze.py`.

**NorthernUI Hotkeys is disabled** (in Vortex: *NorthernUI Hotkeys (Manual Install)* and its *Custom INI*). It turned every D-pad press into a number key, even inside menus, which put random digits into name boxes. The companion now does hotkeys the way the console games do:

| Where | Input | Action |
|---|---|---|
| In game | D-pad, 8 directions | Hotkeys 1–8: up = 1, then clockwise (up-right 2, right 3, down-right 4, down 5, down-left 6, left 7, up-left 8) |
| In game | Hold L1 + right stick direction | Hotkeys 1–8, same directions |
| Inventory / magic menu | Highlight the item or spell, press **Triangle** | The game's own console quick-key menu opens (NorthernUI shows *Quickkey* on Triangle). Pick a slot and confirm |
| Any other menu | – | The companion sends nothing. NorthernUI handles all navigation |

**No cursor:** the mouse cursor is invisible (transparent texture). The mouse itself is not blocked, because blocking it also blocked Steam Input's controller-to-mouse output and killed the pad.

**Running copies:** `Play Oblivion.bat` first closes any controller program still running from an earlier session. A new copy also tells an older one to close, and the program exits by itself about 8 s after Oblivion closes.

**Menus are pure console-style.** NorthernUI handles all navigation: D-pad or left stick to move, Cross to select, Circle to go back. No cursor is involved. While any menu is open, the companion sends nothing (no hotkeys, no wheel), so nothing can leak into a menu. Its extras only work in gameplay. The one exception is the on-screen keyboard: press Cross on a name box, and the game pauses while you type.

## Companion controls (NorthernUI mode)

| Input | Action |
|---|---|
| D-pad, 8 directions | Hotkeys: up = 1, up-right = 2, right = 3, down-right = 4, down = 5, down-left = 6, left = 7, up-left = 8 (the layout from your Xpadder profile) |
| Hold L1 + push the right stick in a direction | Hotkeys 1–8, same directions |
| Hold R3 + L2 / R2 | Mouse wheel up / down |
| **Cross on a text box** (or hold D-pad left 0.6 s) | **On-screen keyboard** (below) |

**On-screen keyboard (name boxes).** When you highlight a text box and press **Cross**, a keyboard appears over the game. This works for the character name, spell name, enchanted item name, potion name, and any "enter text" prompt. Text prompts open the keyboard by themselves. The program detects the box by reading which menu and box are highlighted from the running game (read-only; see `oblivion_osk.py`).

While the keyboard is open, **it has the window focus**. The game pauses and gets no controller input. The text builds up in the keyboard's own line. When you finish, the program switches back to Oblivion, clears the name box and types the whole text in one go.

| Input (keyboard open) | Action |
|---|---|
| D-pad | Move around the keys (hold to repeat) |
| Cross | Press the highlighted key (Shift, Space, Delete, Enter and Done are keys too) |
| Square / Triangle | Delete / space |
| L1 | Shift (applies to the next letter; the first letter is capital) |
| R1 | Jump to **Done** |
| Options, R3 or the **Done** key | Finish: type the text into the game |
| Circle | Cancel (nothing is typed) |

Only one copy of the companion can run. A second start shows a message instead (two copies typed every key twice).

Then confirm in the game as usual. In the race menu, **Circle** is NorthernUI's *Done* for the whole menu; it closes the menu, so the keyboard closes too. You can also open the keyboard by hand: **hold D-pad left** for half a second.

The keyboard can only be drawn over a **windowed** game, so `Play Oblivion.bat` now sets Oblivion to borderless-window at your desktop resolution. `Oblivion.ini` is backed up first, and the program removes the window border. To go back to exclusive fullscreen, run `py oblivion_controller.py --fullscreen`. In fullscreen, holding D-pad left falls back to the blind typing mode: D-pad up/down picks letters directly in the box, right keeps the letter, Square deletes, Cross finishes.

**Character name (race menu):** push the left stick **up** until the *Name* box is highlighted, press **Cross**, and type. This folder's `menus\chargen\race_sex_menu.xml` has a local fix for a NorthernUI bug that disabled the Done button.

Every run writes `controller_log.txt` (mode, controller, menus, keyboard events), so Claude can see what happened.

## Standalone mode (no NorthernUI)

If `NorthernUI.dll` isn't installed, or you set `"mode": "standalone"` in `oblivion_controller_config.json` (or start with `--mode standalone`), the companion emulates keyboard and mouse:

- **Game layer:** Cross activate · Triangle jump · Square ready weapon · Circle menus · R2 attack · L2 block · R1 cast · L1 grab · L3 sneak · R3 view · D-pad = hotkeys 1–4 · Create + D-pad = hotkeys 5–8 · Create (tap) = wait · Options = pause menu.
- **Menu layer** (touchpad click to switch): left/right stick = cursor · Cross click · Circle back.
- **On-screen keyboard:** Cross on a text box, or hold Create and press Options.

In standalone mode, also turn off Oblivion's own joystick input. The button in the window does it, or run `--native-joystick off`. Your `Oblivion.ini` currently has it on.

## Settings and troubleshooting

`oblivion_controller_config.json` (written by *Save settings*) holds `mode`, `nui_dpad_hotkeys`, `nui_l1_stick_hotkeys`, `nui_r3_trigger_wheel`, `typing_hold_seconds`, the standalone layout and sensitivities.

| Problem | Fix |
|---|---|
| Old Oblivion interface appears | Start via `obse_loader.exe`. Check `Oblivion\Data\OBSE\Plugins\NorthernUI.log` and `obse.log` in the Oblivion folder. |
| NorthernUI doesn't react to the controller | The pad isn't showing up as Xbox/XInput. Change the Shadow controller setting, then check `joy.cpl`. |
| Buttons fire twice or do odd things with NorthernUI | Try turning off Oblivion's built-in joystick: `py oblivion_controller.py --native-joystick off` (backs up `Oblivion.ini`; undo with `on`). |
| Hotkeys don't fire | The companion only acts while the Oblivion window is in front. Check its status line. Hotkeys fire when you **release** the D-pad, so diagonals have time to register. |
| You want D-pad menu navigation back | Set `bMenuConsumesDPad=TRUE` in `Oblivion\Data\OBSE\Plugins\NorthernUI.ini` and `"nui_dpad_hotkeys": false` in the companion config. Use L1 + right stick for hotkeys instead. |

Xpadder is not needed. The companion reproduces your Xpadder profile (8-way D-pad hotkeys, L1 + right stick hotkeys, R3 + triggers wheel). Don't run Xpadder and the companion at the same time.

Files: `oblivion_controller.py`, `run_oblivion_controller.bat`, `diagnose_controller.bat`, `install_northernui.py` / `.bat`, `requirements.txt`, NorthernUI's files, and your Xpadder profile (kept for reference).
