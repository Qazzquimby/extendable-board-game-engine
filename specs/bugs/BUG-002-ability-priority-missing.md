---
id: BUG-002
status: open
severity: major
area: ai/priority
---

# BUG-002: Many abilities never used by AI — missing get_priority overrides

## Problem

Multiple heroes have abilities that the AI never selects because they lack `get_priority()` overrides. The base `_auto_priority` returns 0.0 for:
- Self-targeting buffs (Tactical Visor, BonkedModifier, Crit-a-Cola)
- Tap abilities that don't consume the standard action (Helix Rockets, Biotic Field)
- Abilities with no instructions (Go Invisible)
- Area abilities where no enemies are in range at decision time

## Affected Abilities

| Hero | Ability | Reason |
|------|---------|--------|
| Soldier 76 | Helix Rockets | taps=True, no priority override |
| Soldier 76 | Biotic Field | taps=True, only scores when damaged |
| Soldier 76 | Tactical Visor | TargetSelf + AddModifier, auto_priority=0 |
| Reinhardt | Fire Strike | No priority override |
| Reinhardt | Earthshatter | No priority override |
| Scout | Bonk Atomic Punch | taps=True + TargetSelf, no priority |
| Scout | Crit-a-Cola | taps=True + TargetSelf, no priority |
| Scout | Fan O'War | No priority override |
| Spy | Go Invisible | No instructions → no auto_priority |

## Required Fix

Every ability needs a `get_priority()` method. Pattern:

```python
def get_priority(self, engine, actor, pos, aiming_result):
    # Count enemies that would be hit
    targets = ...  # extract from aiming_result
    if targets:
        return 1.5  # or damage-based calculation
    return 0.5  # still prefer over Do Nothing (0.0)
```

## Acceptance Criteria

- [ ] Every hero's abilities have `get_priority()`.
- [ ] `analyze_ability_usage.py HeroName --games 5` shows all abilities used at least once.
- [ ] Abilities with no valid target still get 0.0 priority (don't force bad decisions).
