---
id: BUG-008
status: open
severity: major
area: hero/reinhardt
---

# BUG-008: Reinhardt Fire Strike, Earthshatter never used

## Problem

Reinhardt uses Rocket Hammer and Charge, but never uses:

1. **Fire Strike** — `IncludeArea(area=OrthogonalLine(...))` with `DamageInstruction`. The OrthogonalLine area works (it's been tested), but the ability has no `get_priority()` override. Base auto_priority should give some score for hitting enemies, but may return 0 if no enemies are in line at the current position.

2. **Earthshatter** (Ultimate) — `IncludeArea(area=Square(...))` with `AddModifierInstruction(StunnedModifier)`. Same issue — no get_priority, and AddModifierInstruction scores 0.0 by default.

## Required Fix

- Add `get_priority()` to Fire Strike: score based on enemies in the orthogonal line.
- Add `get_priority()` to Earthshatter: score based on enemies in the square, scaling with round number.

Also, Reinhardt's **Barrier Shield** isn't an ability at all — it's a modifier started in `__init__`. The AI never activates the shield. This is more complex and may need its own separate issue.

## Acceptance Criteria

- [ ] `analyze_ability_usage.py Reinhardt --games 5` shows Fire Strike and Earthshatter used.
- [ ] Fire Strike used when 2+ enemies in line.
- [ ] Earthshatter used by round 4+.
