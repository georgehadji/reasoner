# /update-maps — Refresh the folder map skills

Bring `.claude/skills/map-*/SKILL.md` and `CLAUDE.md` §3.1 back in sync with the tree.

## 1. Find the drift

```bash
python scripts/check_skill_maps.py
```

Exit 0 and "skill maps match the tree" means nothing to do — stop here.

Otherwise the output names each stale map and the exact files that were added
(`+`, not described anywhere in the map) or removed (`-`, still listed but gone).

## 2. Fix only what drifted

For each stale map, open its `SKILL.md` and:

- **Added files** — read the file, then add a row to the table for the section it
  belongs to. Say what the file *does*, not what it is named. If the file starts a
  new group (a new subpackage, a new route family), add a section, and check whether
  the "Key entry points & gotchas" list at the bottom needs a line.
- **Removed files** — delete the row. If a whole section emptied out, delete the section.
- **Renamed files** — these appear as one `+` and one `-`. Edit the existing row rather
  than adding and deleting.

Keep the existing format: one markdown table row per file, `| file | what it does |`.
Do not restate the folder's purpose; that paragraph is already at the top.

## 3. Update CLAUDE.md only if the map changed shape

Edit the §3.1 table only when a *new folder* got a map, a map was retired, or the
"Task / area" phrasing no longer matches what the folder holds. Adding a file to an
existing folder never needs a CLAUDE.md edit.

If a map's coverage changed, also update its `folders:` frontmatter list.

## 4. Accept the new baseline

```bash
python scripts/check_skill_maps.py --update
```

This rewrites `.claude/skills/.map-manifest.json`. Only run it after the SKILL.md
edits are done — it is the record of what the maps were written against.
