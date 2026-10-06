# Handoff 33 (optional, after 32): Ghidra + GhidraMCP for read-only research on the editor's script compiler

**From:** the cloud Claude session (2026-10-06).
**To:** the local Claude, repo clone at `C:\Users\Shadow\Desktop\Games\Oblivion-repo`.
**Priority:** optional. **Handoff 32 (the Ember Ward playtest) comes first.**
**Context:**
- Yuri has installed Ghidra 12.1.4 with LaurieWired's **GhidraMCP** extension (the "New Plugins Found!" dialog).
- GhidraMCP lets a Claude on the PC query Ghidra over a local HTTP server: list and decompile functions, find cross-references, read strings.
- Forge's script compiler still **refuses** five parameter types, because vanilla scripts never use them and their encoding is unconfirmed: FormType (0x21), VariableName (0x16), Global (0x13), Furniture (0x14), Climate (0x27).
- The editor (`TESConstructionSet.exe`) has the code that encodes them. Reading it read-only can confirm them without driving the CS window.

## 0. Rules

- **Read-only research.** Analyse **copies** of `TESConstructionSet.exe` and `Oblivion.exe` that live in a separate research folder, e.g. `C:\Users\Shadow\Desktop\Games\research-ghidra\`, never in the game folder.
- **Never patch** a binary. Never use GhidraMCP's rename or edit tools on anything but that research project.
- **Commit nothing.** The Ghidra project, decompiled code and listings are Bethesda-derived. Report only conclusions: byte layouts, constants, and one-line descriptions. No pasted decompiled functions longer than ~15 lines.
- **Local only.** The GhidraMCP HTTP server stays on `127.0.0.1`. Don't open its port to the network.
- Don't run the game or the CS for this.

## 1. Finish the setup (Yuri, with the pad or mouse)

1. **The "New Plugins Found!" dialog:** keep **GhidraMCPPlugin** ticked and press **OK**. This enables it in the CodeBrowser tool.
2. **Check it's enabled** in the CodeBrowser: **File → Configure → Developer**. `GhidraMCPPlugin` must be ticked.
3. **Import and analyse** the copied `TESConstructionSet.exe` with the default analysers. This takes a while.
4. **Check the server port** in **Edit → Tool Options → GhidraMCP HTTP Server**. The default is 8080; change it only if 8080 is taken.
   - The server runs while a program is open in the CodeBrowser.

## 2. Connect the PC Claude (local Claude does this)

1. Install the bridge's Python packages. **Ask Yuri first.**
   ```
   pip install mcp requests
   ```
   The bridge is `bridge_mcp_ghidra.py`, from the same GhidraMCP release zip.
2. Register the bridge with Claude Code:
   ```
   claude mcp add ghidra -- python "<path>\bridge_mcp_ghidra.py" --ghidra-server http://127.0.0.1:8080/
   ```
3. Restart the session. Check that the `ghidra` tools are listed and that `list_functions` answers.

## 3. The research question (read-only)

In `TESConstructionSet.exe` (version 1.2.0.404):
1. **Find the parameter parser.**
   - Find the routine that compiles one command's parameters. It's the default parse routine; xOBSE hooks it at `0x00500FF0` (editor 1.2, `Hooks_Script.cpp`).
   - Its `switch` on the ParamType id is the target.
2. **Write down the encoding** for each of these types:

   | Type | Id |
   |---|---|
   | FormType | 0x21 |
   | VariableName | 0x16 |
   | Global | 0x13 |
   | Furniture | 0x14 |
   | Climate | 0x27 (may not exist in the editor) |
   | Axis | 0x08 (confirm: 1 char) |
   | Sex | 0x12 (confirm: u16) |
   | CrimeType | 0x1C (confirm: u16) |

   For each one, note:
   - the bytes written, as tag / width / what value;
   - for FormType, how the name maps to the code: the table of form-type names, if there is one;
   - for VariableName, whether it writes text or an index.
3. **Find the CrimeType names:** the table the parser uses for them. The compiler currently assumes Steal, Pickpocket, Trespass, Attack, Murder = 0..4, a HYPOTHESIS.

## 4. Report back to Yuri (for the cloud session)

- Setup: whether it works, the port, and the Ghidra and GhidraMCP versions.
- For each type in §3: the encoding in one line, the function address it came from, and your confidence.
- The CrimeType name table, as names and codes only.
- Anything surprising, briefly. No long decompiled listings.
