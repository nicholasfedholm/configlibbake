# configlibbake

Vintage Story 1.22.7 content mod. It replaces configlib for one job: applying Better Ruins (betterruins 0.6.4) settings, as static JsonPatches.

Baked values:
- Structure spawn chance: x3 (chanceMultiplier 0.3 to 0.9)
- Village spawn chance: x2 (chanceMultiplier 0.08 to 0.16)
- Megastructure minimum group distance: 3000
- Megastructure minimum spawn distance: 2500 (Better Ruins default)

Do not run this together with configlib. Better Ruins' multiplier patches would apply on top of the baked values.

Patches use array indexes into Better Ruins' structures.json, so rebake after a Better Ruins update.

## Rebake

`tools/bake_all.py <outdir>` evaluates every configlib-patches.json it finds at the current ModConfig yaml values. It writes static patches plus report.csv. `tools/build_br.py` keeps only the betterruins ops and zips the mod.
