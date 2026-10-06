"""Dev-time extractors that turn upstream sources into `kb/data/*.json` (facts only).

Run `forge kb refresh-sources --xobse <clone> --xedit <wbDefinitionsTES4.pas> --vim <obse.vim>`.
The JSON they write is committed so `forge kb build` needs no network.
"""
