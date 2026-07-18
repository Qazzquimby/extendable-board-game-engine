---
id: BUG-007
status: open
severity: major
area: hero/soldier76
---

# BUG-007: Soldier 76 Helix Rockets, Biotic Field, Tactical Visor never used

## Problem

Soldier 76 only uses Heavy Pulse Rifle (his default). The AI never selects:

1. **Helix Rockets** — `taps=True`, `IncludeArea` with `Burst`. The base auto_priority only scores damage against entities in the included_points. The choices system may not properly include tap actions alongside standard actions.

2. **Biotic Field** — `taps=True`, `TargetSelf`. Only gets priority when Soldier 76 is damaged (correct behaviour at full HP, but should be used when damaged).

3. **Tactical Visor** (Ultimate 4) — `TargetSelf`, `AddModifierInstruction`. The auto_priority for `AddModifierInstruction` returns 0.0 because it doesn't deal damage or heal.

## Required Fix

- Add `get_priority()` to each ability in `soldier76.py`.
- Helix Rockets: priority based on number of enemies in burst radius (1.5 * enemies_hit).
- Biotic Field: priority based on missing HP (2.0 * missing_hp / max_hp).
- Tactical Visor: priority based on round number (1.0 when ultimate is available, scaling to 3.0 by max round).

## Acceptance Criteria

- [ ] `analyze_ability_usage.py Soldier76 --games 5` shows all 4 abilities used.
- [ ] Helix Rockets used when 2+ enemies in burst.
- [ ] Biotic Field used when damaged.
- [ ] Tactical Visor used by round 4+.
