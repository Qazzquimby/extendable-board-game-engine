# Heroes with range do not position optimally

**Status:** ready-for-agent
**Severity:** medium
**Reporter:** user

## Problem

When a hero already has a target in range, they don't try to position at exactly their weapon's optimal range.

E.g., Soldier 76 has Heavy Pulse Rifle at range 4. He might move to range 2 or 3 instead of maintaining exactly range 4.

## Expected behavior

AI should prefer positions where the hero's optimal ability (usually the default weapon) is at max range to the nearest enemy, giving them maximum buffer while still being able to attack.

## Root cause

The movement scoring (`best_move_for_score` / `get_movement` in abilities) doesn't account for preferred engagement distance. It only considers "how many enemies can I hit" not "what's the ideal distance to stay at."
