# Spy does literally nothing all game

**Status:** ready-for-agent
**Severity:** critical
**Reporter:** user

## Problem

Spy uses "Do Nothing" every turn and never moves, attacks, or uses any ability. In 5 test games, Revolver, Knife, and Go Invisible were never used.

## Root cause

All three abilities have issues:
1. **Revolver** (range 4): `requires_target=True` (default) checks for entities at target points. Starting 5 cells from enemy means no targets in range → priority 0.
2. **Knife** (range 1): Same issue, even shorter range.
3. **Go Invisible**: Uses `TargetSelf` but has empty instructions `[]`. Also `requires_target=True` may give low auto_priority.

No `get_movement` override to tell AI to close distance to enemies.

## Fix needed

1. Set `requires_target=False` on abilities that can target markers (not just entities)
2. Add `get_movement` override to close distance to enemies
3. Give Go Invisible actual instructions (create decoy markers)
