# TES4Forge's own script compiler: evaluation and plan

**Status:** approved by Yuri (2026-10-06). **S0 and S1 are done:** the corpus was exported on the PC (handoff 28; 26,624 scripts, 10,720 with bytecode), and the decompiler decodes **100%** of it with no leftover bytes. The format is in `tools/forge/script/bytecode.py`. **S2–S6 are done too:** `forge script-check` compiles every vanilla script's source and gets **99.86% byte-identical SCDA** (10,705 of 10,720). The 15 others are explained in §3d. Next: `scripts:` in `kind: plugin` specs.
**Decisions (Yuri, 2026-10-06):**
1. The plan is approved. The PC exports the vanilla script corpus (S0), and Yuri uploads it to the cloud session for local iteration. It is never committed.
2. The research mods' OBSE scripts may be used for validation (S7), **on the PC only**: pass rates and failure counts may come back to the cloud; script text and bytes stay on the PC.
**Direction (Yuri):** TES4Forge should be the AI's own construction kit and shouldn't depend on driving the CS window. The CS bridge stays only as an optional cross-check.

## 1. What has to be produced

For every script (SCPT records, plus the result scripts inside QUST stages, INFO and PACK), forge must write the same subrecords the CS writes:

| Subrecord | Content | Difficulty |
|---|---|---|
| `SCTX` | the source text | trivial (copied) |
| `SCHR` | ref count, compiled size, variable count, script type | easy once the rest exists |
| `SLSD` + `SCVR` | each local variable: index, type flag (short/long vs float/ref), name | easy; the index order rules need checking |
| `SCRO` / `SCRV` | the reference list: FormIDs (and local vars) the bytecode points to by index | medium: the **order** must match the CS (order of first use, de-duplication, quest-variable references) |
| `SCDA` | the compiled bytecode | **the real work** |

`SCDA` format, from what I know (to be confirmed against the corpus; confidence HIGH for the general shape, HYPOTHESIS for details):
- **Statements:** a 2-byte opcode plus a 2-byte length, followed by parameters.
- **Blocks:** `Begin`, `End`, `ScriptName`, `Return`.
- **Control flow:** `If`/`ElseIf`/`Else`/`EndIf` with jump lengths. `Set` and `If` carry an *expression*: a length-prefixed token stream that mixes literals stored as text, variable tokens (`s`/`l`/`f` + index), reference tokens (`r` + SCRO index), function-call tokens (opcode + parameters) and operators.
- **Parameter encoding** depends on each parameter's type. We know every vanilla command's parameter types exactly from the PC's `Oblivion.exe` export (369 script + 131 console commands), and the type ids from xOBSE. Types include actor-value codes, axis, animation group, form type, crime type, sex, quest stage and variable names, which mostly become 2-byte codes or SCRO indexes.

**OBSE syntax** (`let`, `eval`, `while`/`foreach`, arrays, strings, user functions, `SetEventHandler`) compiles through xOBSE's own expression compiler. It has its own versioned token format, documented in xOBSE's source, which we have locally. It's a second, separate compiler stage.

## 2. Honest size and risk

| Part | Size (Python, with tests) | Risk | Validation |
|---|---|---|---|
| Vanilla OBScript: lexer and parser, variables, blocks, if/set, function calls with typed parameters, reference calls (`ref.Func`), quest variables (`Quest.var`), SCRO/SLSD/SCHR | **~2.5–4k lines** | **Medium.** The format is regular, but the CS has quirks: number-to-text formatting, identifier case, implicit conversions, SCRO ordering, how it tolerates sloppy syntax (missing `endif`, stray tokens), and parameter types with odd encodings. | The vanilla corpus: 2,393 SCPT + ~1,900 quest-stage + ~5,500 INFO result scripts, compiled and compared byte for byte. |
| A decompiler (SCDA → readable tokens) | ~600 lines | Low | Same corpus. Built **first**: it proves we understand the format before we generate it, and it makes every mismatch readable. |
| OBSE syntax | **~2–4k lines** more | **High.** It's a different expression compiler with versioned formats, and there are no OBSE scripts in vanilla. | Needs a corpus of OBSE scripts from mods. The research specimens have plenty (e.g. Fearsome Magicka, 653 scripts), but they're PRIVATE_RESEARCH_ONLY. Compiling their text to compare bytes would be validation only: nothing copied into forge, nothing committed. **Your call.** |

**Effort:** realistically several working sessions, not one. The vanilla compiler should reach roughly 90%+ byte-identical in the first full pass, then a long tail of CS quirks. The **target** is ≥99% of the vanilla corpus identical, with every remaining case explained and listed. OBSE support comes after that, as a separate milestone.

**What could go wrong:**
- **A compiler that's "almost right" is dangerous.** Wrong bytecode can crash the game or silently misbehave, without any error at build time. Mitigation: forge refuses to ship a script unless (a) its constructs are all covered by the corpus-validated subset, or (b) it was cross-checked by the CS. Unknown constructs are a hard error, not a guess.
- **A small vanilla corpus for some features:** some commands or parameter types appear only a handful of times in vanilla. For those, new scripts get a CS cross-check until there's enough evidence.
- **The cloud can't see vanilla bytes:** the corpus is Bethesda data and stays on the PC, never committed. Iterating through handoffs alone would be slow (one PC round trip per fix). The fast loop is: the PC exports the corpus once, Yuri uploads that file to the cloud session, and the cloud iterates locally in its scratch space. **Your call** (same category as the dumps already shared in reports, just bigger).

## 3. Plan (each step ships only when its check passes)

| Step | What | Check |
|---|---|---|
| S0 | `forge kb export-scripts`: a corpus file (SCTX, SCDA, SCRO/SCRV, SLSD/SCVR, SCHR for every script in Oblivion.esm + DLC), git-ignored. Also extend `export-commands` to read the **block-type table** (GameMode, OnActivate, ScriptEffectStart, …) from `Oblivion.exe`, next to the 369 script commands. | Counts match `layout-check`. |
| S1 | Decompiler: SCDA → token listing. **Done: 100% (10,720/10,720).** | 100% of the corpus decodes with no leftover bytes. |
| S2 | Compiler, statements without expressions: blocks, calls with parameters, `return`, variables. | `forge script-check` (below), measured per construct. |
| S3 | Expressions: `set`/`if`/`elseif`, arithmetic, comparisons, function calls inside expressions. | |
| S4 | References: `ref.Func`, `Quest.var`, SCRO ordering; SCHR and SLSD exact. | |
| S5 | Result scripts in QUST/INFO/PACK. | |
| S6 | Gate: ≥99% of the vanilla corpus byte-identical, the rest explained. **Done: 99.86%.** Next, `kind: plugin` specs carry `scripts:` with no CS involved. | Phase 3b done. |
| S7 | OBSE syntax. | OBSE corpus check, run **on the PC only** against the research mods' scripts; only pass rates and failure counts come back. |

`forge script-check <plugin>` works like `layout-check`. It compiles every script's SCTX, compares SCDA/SCRO/SLSD/SCHR with what the plugin holds, and prints PASS rate, failures by construct, and the first differing byte with the decompiled context.

## 3b. What S0 and S1 deliver (built 2026-10-06)

- **`forge kb export-scripts --data <Data> [--exe <Oblivion.exe>] [--out forge-script-corpus.jsonl.gz]`** writes one gzip'd JSONL bundle. It holds:
  - a `meta` row;
  - `command` rows: the exe's script, console and **block-type** tables;
  - `form` rows: every EditorID'd record, with its script (SCRI) and a placed reference's base object, for name resolution;
  - one `script` row per script: SCHR fields, SCDA hex, SCTX (latin-1, lossless), variables (SLSD/SCVR), the reference list in order (SCRO resolved to EditorID/type, SCRV), the subrecord order, and its context (quest stage/log entry, dialogue topic).
- **The block-type table** is found like the command tables: the compiler matches `begin <name>` against CommandInfo names (xOBSE `Hooks_Script.cpp`). The table's opcode field is taken as the block code; the survey checks that against the `begin` names in the source text.
- **`forge script-decode <plugin|corpus>`** is the decompiler (`tools/forge/script/bytecode.py`). It runs on a corpus bundle or directly on a plugin.
  - Without options it prints the survey:
    - the pass rate, **S1 gate = 100%** decoded with no leftover bytes;
    - failures grouped by kind, with examples;
    - unknown opcodes;
    - SCHR consistency;
    - what the If/Else/ElseIf/Begin jump fields count. It measures every candidate meaning instead of assuming one.
  - `--show EDID|FormID [--source]` prints one listing.
  - `--fail N` prints the first N failing listings.
- **Where the format comes from:** the statement and parameter shapes are xOBSE's `GameAPI.cpp` bytecode reader (HIGH confidence). The expression token format is a HYPOTHESIS that the survey tests.

## 3c. What the corpus taught us (S1 result, 2026-10-06)

| Question | Answer from the corpus |
|---|---|
| Expression order | **Postfix (RPN)**: `IsActionRef player 1 ==`. The compiler must turn infix source into postfix tokens, separated by spaces. Numbers and operators are stored as ASCII text; `~` is unary minus. |
| Jump fields | If/ElseIf/Else: the number of **statements between** this one and the next branch of the same level. Begin: bytes from after the Begin statement **through** the End statement. |
| Reference as a value | `Z` + u16 reference index (`== SEYngvarRef`). |
| Message / MessageBox / EssentialDeathReload | Custom layout: text, format-variable count + variables, then buttons (MessageBox) or display seconds + 0 (Message). |
| Block types | 31 in the exe table; the codes match the `begin` names in source for every script (26 types used). |
| SCHR variable count | A high-water mark: 432 scripts have gaps, 171 a stale higher count. For new scripts the count = the highest index. For byte-identical vanilla recompiles it can't be derived from the source, so `script-check` takes it from the original record. |
| Sloppy nesting | 48 stray `endif`s, 8 `else`s and 6 `elseif`s without an `if`: the CS compiles them anyway, and so must forge, for the corpus check. |
| Never used in vanilla | Parameter types FormType (0x21), VariableName (0x16), Global (0x13), Furniture (0x14) and Climate (0x27). Forge refuses to compile them until something confirms their encoding (a CS cross-check). |
| Cross-check | Every command the decoder finds appears by name in that script's source text. All quest/reference variables resolve to names. |

## 3d. The compiler (S2–S6, 2026-10-06)

`tools/forge/script/compiler.py` and `forge script-check <corpus|plugin>` (`tools/forge/script/check.py`).

**Result on the vanilla corpus:** 10,705 of 10,720 scripts (99.86%) compile to byte-identical SCDA. By type: SCPT 3,040/3,046, QUST result scripts 1,863/1,870, INFO result scripts 5,802/5,804. **Gate (≥ 99%) passed.**

**More rules the corpus fixed:**
- **Reference-list order:** a statement's calling references (`X.Func`) come first, in order of first such use. Then reference variables (SCRV), by variable index. Then every other reference, in first-use order. On every identical script this reproduces the vanilla list exactly (10,615), or differs only by stale leftover entries (90). `script-check` pins the original order, so the bytecode is compared on its own merits.
- **Variable tags:** `short`, `int` and `long` all compile to `s`; `float` and `ref` to `f`. Vanilla never writes `l`.
- **Operator precedence:** `||` binds tighter than `&&`. Comparisons are above them, then `+ -`, then `* /`, then unary minus `~`.
- **A command writes its u16 parameter count only when it defines parameters.** Words after a command without parameters are ignored.
- **CS tolerances forge reproduces:**
  - stray `endif`/`else`;
  - repeated declarations (the first wins);
  - punctuation-only lines;
  - `Ref. Func` with a space after the dot;
  - quoted names as parameters;
  - a local of any type used as a reference;
  - a form name beats a same-named number variable in a form parameter.
- **Variable indices** follow declaration order for new scripts. `script-check` pins the original indices, since 642 vanilla scripts carry gaps from editing history.

**The 15 that differ, all explained:**

| Count | Cause |
|---|---|
| 8 | **Stale compiled data:** the source names an object that was renamed or deleted after the last compile (`SE02FIN`, `ND10BattleMarker01REF`, …), or the compiled reference points elsewhere (`DL9ChampAxe01` compiled as `WeapDaedricWarAxe`). |
| 4 | **`PlayerRef`:** the CS gives it its own list entry even though it's the same form as `player`. Rare and ordering-dependent. Forge maps it to `player`. |
| 2 | **TGExpelled:** the quest script's variable indices changed after these dialogue scripts were compiled (stale). |
| 1 | **`GetIsID 7`:** a raw FormID number used as a form parameter. Not supported: forge requires names. |

**Still refused (CompileError, never a guess):**
- parameter types Global, Furniture, Climate, FormType and VariableName (vanilla never uses them);
- variables of a reference variable's script (`myRef.var`);
- unknown names, commands and block types.

## 4. The CS bridge after this

- **Optional cross-check:** for scripts using constructs the corpus doesn't cover, and for spot checks of new scripts.
- **Not on the build path.**
- **CS recon take 3 (handoff 27): worth finishing, but not urgent.** It's one short run, and the bridge code for it (toolbar/menu commands) is already written. It gives the cross-check oracle: the only independent way to check scripts that vanilla never exercises. If the PC time is better spent on the corpus export, it can wait. It's not needed to start S0–S1.
