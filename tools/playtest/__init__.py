"""TES4Forge Track E: quick-boot playtesting.

`forge playtest` boots a throw-away test profile of the clean GOG copy straight into a test cell,
runs the scripted checks from playtest_manifest.json, and restores Plugins.txt and Oblivion.ini
afterwards (even after a crash). `forge test` reads the result log. `forge preview` draws the
cells in a browser. See tools/playtest/README.md.
"""

VERSION = "0.1.0"
