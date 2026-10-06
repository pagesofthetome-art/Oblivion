# TES4Forge's own script compiler: evaluation and plan

**Status:** proposal for Yuri (2026-10-06). Nothing is built yet.
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
| S1 | Decompiler: SCDA → token listing. | 100% of the corpus decodes with no leftover bytes. |
| S2 | Compiler, statements without expressions: blocks, calls with parameters, `return`, variables. | `forge script-check` (below), measured per construct. |
| S3 | Expressions: `set`/`if`/`elseif`, arithmetic, comparisons, function calls inside expressions. | |
| S4 | References: `ref.Func`, `Quest.var`, SCRO ordering; SCHR and SLSD exact. | |
| S5 | Result scripts in QUST/INFO/PACK. | |
| S6 | Gate: ≥99% of the vanilla corpus byte-identical, the rest explained. `kind: plugin` specs can then carry `scripts:` with no CS involved. | Phase 3b done. |
| S7 | OBSE syntax (only after your decision on the mod corpus). | OBSE corpus check. |

`forge script-check <plugin>` works like `layout-check`. It compiles every script's SCTX, compares SCDA/SCRO/SLSD/SCHR with what the plugin holds, and prints PASS rate, failures by construct, and the first differing byte with the decompiled context.

## 4. The CS bridge after this

- **Optional cross-check:** for scripts using constructs the corpus doesn't cover, and for spot checks of new scripts.
- **Not on the build path.**
- **CS recon take 3 (handoff 27): worth finishing, but not urgent.** It's one short run, and the bridge code for it (toolbar/menu commands) is already written. It gives the cross-check oracle: the only independent way to check scripts that vanilla never exercises. If the PC time is better spent on the corpus export, it can wait. It's not needed to start S0–S1.
