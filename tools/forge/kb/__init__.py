"""TES4Forge knowledge store: one SQLite file an agent can query in one call.

Committed: the code, plus facts extracted from open sources (`data/*.json`) and our own
curated notes (`data/curated.json`). Never committed: Bethesda-derived data
(`vanilla_index.jsonl`, `vanilla_commands.jsonl`) and the built `forge-kb.sqlite`.
"""

CONFIDENCE = ("CONFIRMED_MULTI_SOURCE", "HIGH_CONFIDENCE", "HYPOTHESIS")
