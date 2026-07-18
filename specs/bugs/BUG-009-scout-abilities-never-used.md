---
id: BUG-009
status: open
severity: major
area: hero/scout
---

# BUG-009: Scout Bonk, Crit-a-Cola, Fan O'War never used

## Problem

Scout only uses Scattergun. The AI never selects:

1. **Bonk Atomic Punch** — `taps=True`, application of `BonkedModifier` (damage immunity). The auto_priority for AddModifierInstruction is 0.0. Even when surrounded by enemies, Scout never uses this survival tool.

2. **Crit-a-Cola** — `taps=True`, application of `CritAColaModifier` (deal +50%, take +50% damage). The modifier infrastructure exists (Damage pipeline reads apply_damage_buff/apply_vulnerable), but the AI never uses it because priority is 0.

3. **Fan O'War** — applies `MarkedForDeathModifier` (+50% damage taken). TargetEntity with range 1, melee debuff. Priority not set, so auto_priority returns 0.

## Required Fix

Add `get_priority()` overrides:
- Bonk Atomic Punch: priority based on Scout's remaining HP and number of adjacent enemies
- Crit-a-Cola: priority based on expected damage increase (1.5× next attack)
- Fan O'War: priority based on whether target already has the debuff

## Acceptance Criteria

- [ ] `analyze_ability_usage.py Scout --games 5` shows all 4 abilities used.
- [ ] Bonk used when HP is low (< 3).
- [ ] Crit-a-Cola used before engaging.
- [ ] Fan O'War used as setup before Scattergun.
