# Story e01s01: Grid places entities and validates positions

## 1. Metadata

- **ID:** e01s01
- **Epic:** e01 (Core Engine)
- **BCPs:** 1
- **Risk:** P2 (utility, display-only — grid math, no data mut risk)
- **Type:** test (tests only, no new production code)
- **Delta:** MODIFIED

## 2. Countable Format (Maturity 3)

## 3. Narrative

The Grid is the spatial foundation of the entire engine — every ability targets a position, every entity occupies a space, every movement path traverses cells. The grid tests in `test_grid.py` were written against an older API and are entirely commented out. No unit tests verify grid initialization, pathfinding, push/pull movement, line-of-sight, or range calculations.

This story uncomments and rewrites those tests to match the current Grid API, then adds coverage for any gaps found during the rewrite.

## 4. Actors

- Developer running tests
- AI agents using Grid for pathfinding and LOS

## 5. Main Flow (Happy Path)

### MODIFIED: Grid initializes with correct dimensions

**Before:** `Grid()` used default constructor with no arguments.
**After:** `Grid(5, 5)` creates a 5×5 grid; `g.width == 5` and `g.height == 5`.

### MODIFIED: Pathfinding works on open grid

**Before:** `grid.get_path(Point(0,0), Point(2,2))` — 2-arg call.
**After:** `grid.get_path(engine=..., start=Point(0,0), target=Point(2,2), actor=...)` — requires engine and actor.

### MODIFIED: Push movement uses Direction enum

**Before:** `get_push_path(Point(1,0), Point(3,0), push_from=Point(0,0))`.
**After:** `get_push_path(subject=entity, direction=Direction.EAST, distance=2)`.

### MODIFIED: Pull movement parameter order

**Before:** `get_pull_path(Point(3,0), Point(1,0), pull_to=Point(0,0))`.
**After:** `get_pull_path(subject=entity, pull_to=Point(0,0), distance=2)`.

## 6. Alternative Flows

### Blocked pathfinding

When walls block the path, `get_path` returns `None` or a longer detour.

### Out-of-bounds movement

Push/pull stops at grid boundaries rather than returning invalid positions.

### Line-of-sight

- Clear LOS across a straight line → visible, no cover
- Wall blocking LOS → not visible
- Wall adjacent to target → visible with cover

## 7. Error / Edge Cases

- Start == target → path returns single-point tuple
- max_range < 0 → returns empty UniqueTuple
- Entity at invalid position → not reachable
- Diagonal movement blocked by corner walls

## 8. Constraints

- Must use the current `pytest` runner
- No new external test dependencies
- Tests must pass with `python -m pytest tests/test_grid.py -x -q`

## 9. Security

- None — grid is deterministic math with no data

## 10. Observability

- Test failures print the exact assertion that broke

## 11. Performance

- Grid pathfinding tests should complete in < 100ms each

## 12. Dependencies

- `tests/test_grid.py` — file to rewrite
- `backend/src/grid.py` — module under test
- `backend/src/point.py` — Point class
- `backend/src/engine.py` — Engine (needed for get_path integration)
- `backend/src/entities.py` — Entity (needed for push/pull tests)

## 13. Out of Scope

- LOS integration with enemy-entity blocking (covered by e02s03)
- Entity position validation (covered by e01s02)
- Visualization tests (the `visualize()` and `visualize_visibility()` HTML methods)

## 14. Test Plan

### Unit tests (direct Grid API, no engine needed)

| ID | Description | Priority |
| ---- | ------------- | ---------- |
| T1 | Grid initializes with correct dimensions | P2 |
| T2 | `is_movement_blocked` checks walls and edge walls | P2 |
| T3 | `get_range` calculates distance (first step diagonal) | P2 |
| T4 | `get_points_in_range` returns visible points within range | P2 |
| T5 | Push path follows direction, stops at walls/bounds | P2 |
| T6 | Pull path moves toward target, stops when blocked | P2 |
| T7 | LOS: clear line is visible with no cover | P2 |
| T8 | LOS: wall blocks visibility | P2 |
| T9 | LOS: wall adjacent to target gives cover | P2 |

### Integration tests (need Engine + Entity fixtures)

| ID | Description | Priority |
| ---- | ------------- | ---------- |
| T10 | `get_path` finds valid path on open grid | P2 |
| T11 | `get_path` detours around walls | P2 |
| T12 | `get_path` returns `None` when fully blocked | P2 |
| T13 | `get_movable_spaces` respects enemy blocking | P2 |
| T14 | Start == target returns single-point path | P2 |

## 15. Risks

- **Low:** Grid API may expose edge cases not caught by tests (e.g., corner cutting on diagonals with edge walls)
- **Low:** `get_points_in_range` uses LOS which may have edge-case performance issues with many points
- **Mitigation:** Run full test suite after changes to catch regressions

## 16. Assumptions

- No production code changes needed — tests only
- The existing Grid code is correct; tests just verify current behavior

## 17. Acceptance Criteria (Gherkin)

```gherkin
Scenario: Grid dimensions
  Given a Grid(5, 5)
  Then width is 5 and height is 5

Scenario: Open pathfinding
  Given a Grid(10, 10)
  When finding path from (0,0) to (2,2)
  Then a valid path exists with expected length

Scenario: Blocked pathfinding
  Given a Grid(10, 10) with wall at (1,0)
  When finding path from (0,0) to (2,0)
  Then the path detours around the wall

Scenario: Push movement
  Given a Grid(10, 10) and an entity at (5,5)
  When pushing EAST for 3 spaces
  Then the path is [(6,5), (7,5), (8,5)]

Scenario: Pull movement
  Given a Grid(10, 10) and an entity at (5,5)
  When pulling toward (5,2) for 2 spaces
  Then the path moves closer to (5,2)

Scenario: Clear line of sight
  Given a Grid(10, 10)
  When checking LOS from (0,0) to (3,0)
  Then visible is True and has_cover is False

Scenario: Blocked line of sight
  Given a Grid(10, 10) with wall at (1,0)
  When checking LOS from (0,0) to (2,0)
  Then visible is False

Scenario: Cover from adjacent wall
  Given a Grid(10, 10) with wall at (1,1)
  When checking LOS from (0,0) to (2,0)
  Then visible is True and has_cover is True
```

## 18. Pre-Implementation Checklist

- [x] Understand the Grid API (get_path requires engine+actor, push uses Direction enum, pull signature changed)
- [x] Identify test file location: `tests/test_grid.py`
- [x] No production code changes expected
- [ ] No external dependencies

## 19. Dependencies

- All tests should compile and pass on first attempt if Grid is correct

## 20. Definition of Done

- [ ] `test_grid.py` contains uncommented, passing tests
- [ ] All new tests pass: `python -m pytest tests/test_grid.py -v`
- [ ] Full suite still passes: `python -m pytest tests/ -x`
