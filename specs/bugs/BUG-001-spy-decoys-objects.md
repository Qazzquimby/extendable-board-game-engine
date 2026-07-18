---
id: BUG-001
status: open
severity: major
area: hero/spy
---

# BUG-001: Spy decoys use custom TargetSpyOrDecoys aiming hack instead of real objects

## Problem

The Spy's decoy system was implemented using a custom `TargetSpyOrDecoys` Aiming subclass (in `spy.py`) instead of making decoys real Entity objects. This is an unscalable pattern:

1. Every new hero that needs decoy-like mechanics would need its own custom Aiming subclass.
2. `TargetSpyOrDecoys` is not recognized by `choices.py`'s isinstance chain — it was silently dropped, causing Spy to never use any abilities (0 aimings from starting position).
3. Markers were not designed to be targetable — they have no HP, no activation, no `entity_at` lookup.
4. The workaround (`type(ability.aiming).__name__ == 'TargetSpyOrDecoys'` in choices.py) is fragile and ugly.

## Required Fix

Convert Spy decoys from `SpyDecoyMarker(Marker)` to a proper `SpyDecoy(Entity)` subclass:

1. `SpyDecoy(Entity)` — has HP (1hp), is targetable via `TargetEntity(in_range=X, condition=...)`, appears in `entity_at` lookups.
2. Remove `TargetSpyOrDecoys` — replace with standard `TargetEntity` targeting.
3. Decoys move with Spy via `ChangeLocationEvent` hook (keep this).
4. Decoys die when Spy is revealed or takes damage (keep this mechanic).
5. Remove the isinstance hack from `choices.py`.

## Acceptance Criteria

- [ ] Spy abilities target decoys AND enemies using `TargetEntity`, not custom aimings.
- [ ] choices.py has no special-case handling for Spy decoys.
- [ ] All existing Spy tests still pass.
- [ ] Spy uses Revolver and Knife in AI games.
- [ ] No custom `TargetSpyOrDecoys` class remains in codebase.
