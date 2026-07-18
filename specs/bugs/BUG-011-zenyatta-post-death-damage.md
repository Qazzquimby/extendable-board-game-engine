---
id: BUG-011
status: open
severity: major
area: hero/zenyatta
---

# BUG-011: Zenyatta damage persists after death

## Problem

Zenyatta's Orb of Discord applies a modifier that increases damage taken by the target. When Zenyatta dies, the modifier should be removed. Currently it persists, meaning the debuff stays on the target for the rest of the game even after Zenyatta is dead.

## Required Fix

- Add a death handler to Zenyatta that removes all applied modifiers when he dies.
- Pattern: use `@after(DamageEvent)` to detect Zenyatta's death and clean up modifiers.
- Alternatively, give modifiers an `source_id` field and auto-remove when source dies.

## Acceptance Criteria

- [ ] When Zenyatta dies, his Orb of Discord debuff is removed from all targets.
- [ ] Test: apply Orb of Discord, kill Zenyatta, verify debuff is gone.
- [ ] All existing tests still pass.
