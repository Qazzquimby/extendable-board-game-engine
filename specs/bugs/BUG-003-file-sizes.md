---
id: BUG-003
status: open
severity: minor
area: code-quality
---

# BUG-003: Several source files exceed 400-line limit

## Problem

Multiple source files exceed the 400-line standard for module size:

| File | Lines | Issue |
|------|-------|-------|
| `backend/src/abilities.py` | 780+ | Holds Ability class, instruction scoring, all Aiming types |
| `backend/src/choices.py` | 440+ | Choice generation for AI |
| `backend/src/engine.py` | 700+ | Game engine with event loop, agents, game runner |
| `backend/src/events.py` | 250+ | Event base, turn events, ability events |
| `backend/src/instruction_library.py` | 360+ | All instruction types |

## Required Fix

Split large files:
- `abilities.py` → split Aiming types into `aimings.py` (already exists), move instruction scoring functions
- `engine.py` → extract `agents.py`, `game_runner.py`, or `game_log.py`
- `choices.py` → extract movement planning, action evaluation
- `instruction_library.py` → within limits (360), but could split if more instructions added

## Acceptance Criteria

- [ ] No source file exceeds 400 lines.
- [ ] All imports updated after splits.
- [ ] All tests still pass.
