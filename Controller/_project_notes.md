# Oblivion agent workspace (set up 2026-10-04)

Location on Yuri's PC (a Shadow cloud PC): `C:\Users\Shadow\Desktop\Games`
- GOG Oblivion 1.2.0.416 (clean dev/CS copy)
- CS 1.2.0404
- TES4Edit 4.1.5f
- xOBSE 22.13
- Entry point for agents: `AGENTS.md`

## ROOT CAUSE of all controller trouble (found 2026-10-04)

Steam Input was ON for Oblivion (app 22330), with the **Keyboard (WASD) and Mouse** template:
- `Steam\steamapps\common\Steam Controller Configs\1126634429\config\configset_45e-28e-432713bd.vdf` held `"22330" template controller_xbox360_wasd.vdf`.
- `localconfig.vdf` had `SteamController_XBoxSupport=1`.
- Steam's `logs\controller.txt` showed `mapping uses xinput : false` for 22330.

So Steam hid the pad from the game and converted it to keys and mouse:
- digits in name boxes
- the mouse cursor
- a dead controller when the mouse was blocked

NorthernUI never got a gamepad.

**Fix:** `Controller\steam_check.py --fix` runs from `Play Oblivion.bat` on every launch. It needs Steam closed.
- It sets `localconfig.vdf` apps\22330 `"UseSteamControllerConfig" "0"` (0 = Steam Input disabled).
- It removes the 22330 template from `configset_*.vdf`.
- It keeps backups (`*.bak-oblivion-*`).
- The DayZ (221100) layout is untouched.

**Input chain:** PS5 pad (Bluetooth) → Shadow → virtual Xbox 360 controller (XInput, VID 045E PID 028E) → NorthernUI → game.

**Verify:** `Controller\Check controller.bat` (`input_audit.py`) writes `controller_audit.txt`. It checks:
- Steam
- the XInput slot count
- the NorthernUI Console scheme and ini
- conflicting mods
- every button, using observe-only keyboard/mouse hooks that flag any key or mouse event appearing while the pad is pressed

## Controls (console 1:1)

NorthernUI scheme "Console" in `Documents\My Games\Oblivion\NorthernUI.ctrl.txt` (`sUseSchemeName=Console`):
- RT Use, LT Block, RB Cast, LB Grab
- A Activate, B Big Four, X Draw, Y Jump
- LS Sneak, RS POV, Back Wait

Companion (`oblivion_controller.py`, config v3):
- Gameplay: 8-way D-pad = hotkeys 1-8.
- In menus it sends nothing.
- Inventory (1002) / Magic (1022): R3 opens the hotkey wheel overlay.
- Name boxes: Cross opens the on-screen keyboard, which takes focus so the game pauses. Text is typed in one go after Done.
- Single instance; auto-exits when the game closes.
- The mouse block was REMOVED: it killed Steam's mouse emulation of the pad.
- The L1+stick and R3+trigger extras are off.

## Play copy

The play copy is the Steam install (`steamapps\common\Oblivion`).
- Vortex deploys Oblivion Rebirth+ there as hardlinks.
- xOBSE was copied in by hand.

Patched files (when Vortex reports external changes, choose "Save change"):
- `NorthernUI.ini`: PS icons, `fAutoHideCursorDelay=0.1`, `bMenuConsumesDPad=TRUE`
- `race_sex_menu.xml`: Done-button fix
- `Textures\Menus\misc\cursor.dds`: transparent

Disabled in Vortex:
- Use WASD in Menus
- NorthernUI Hotkeys (Manual Install) and its Custom INI

Memory probe:
- InterfaceManager pointer `0x00B3A6E0`
- `+0xE0` menu stack, `+0x98` / `+0x88` active tile
- Tile name at `+0x08`, parent at `+0x10`
- Menu ids follow xOBSE `GameMenus.h`
