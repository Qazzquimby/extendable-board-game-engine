---
id: BUG-012
status: open
severity: minor
area: hero/necrophos
---

# BUG-012: Necrophos Ghost Shroud used at wrong time

## Problem

Necrophos uses Ghost Shroud (damage immunity) at incorrect times. The AI should activate it when:
- Necrophos is at critically low HP (≤ 3)
- Multiple enemies are adjacent and about to attack

Instead, it's used randomly or not in response to actual threats.

## Required Fix

- Add `get_priority()` override to Ghost Shroud that considers:
  - Necrophos's remaining HP (higher priority when low)
  - Number of adjacent enemies (higher priority when surrounded)
  - Whether Necrophos has taken damage this turn
- May also need to mark Ghost Shroud as a `reaction` ability so it can activate in response to incoming damage.

## Acceptance Criteria

- [ ] Ghost Shroud activates when Necrophos has ≤ 3 HP and enemies are adjacent.
- [ ] Ghost Shroud not wasted when Necrophos is at full HP.
- [ ] Test: put Necrophos at 3 HP with adjacent enemy, verify Ghost Shroud activates.
