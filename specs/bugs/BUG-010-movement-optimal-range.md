---
id: BUG-010
status: open
severity: major
area: ai/movement
---

# BUG-010: Movement AI doesn't maintain optimal range

## Problem

Heroes with ranged attacks don't position themselves at optimal distance from enemies. The AI doesn't account for:
1. Staying just outside enemy attack range while inside own attack range ("kiting")
2. Preferring positions that keep enemies at a distance while allies close in
3. Fallback movement when no enemies are in range (currently just stays in place)

Evidence: all ranged heroes (Soldier 76, Scout, Spy, Zenyatta) move to adjacent range and get hit by melee counterattacks.

## Required Fix

Add a `get_movement` override or default behavior that:
- Proposes positions at exactly `self.range - 1` distance from nearest enemy (optimal attack range)
- Penalizes positions within enemy melee range (adjacent)
- Moves toward nearest enemy when no one is currently in range

## Acceptance Criteria

- [ ] Ranged heroes don't move adjacent to melee enemies unless their ability requires it.
- [ ] Ranged heroes maintain distance from multiple enemies.
- [ ] Movement priority considers both ability usage AND positional safety.
