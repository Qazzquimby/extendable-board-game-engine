# CONVENTIONS.md — Game Engine Project

## Code Standards

### File Size
- No code file may exceed **400 lines**. Split into modules when approaching this limit.
- Each module should have one clear responsibility.

### Function Size
- Functions should be 4–20 lines. Split if longer.
- Functions should descend exactly one level of abstraction (Stepdown Rule).
- Max 2 levels of indentation. Use early returns to reduce nesting.

### Naming
- Names must be specific and unique. `grep` should return < 5 matches for each name.
- No abbreviations unless universally understood (`hp`, `id`, `pos`).
- Boolean parameters are forbidden (flag arguments = function does > 1 thing).

### Imports
- No wildcard imports (`from x import *`). Import only what you need.
- No unused imports — clean them up.

### Types
- All public functions must have type annotations.
- No `Any` types unless absolutely necessary and documented.
- Use dataclasses or typed dicts, not raw dicts/lists for structured data.

## Hero & Ability Standards

### Hero Creation
- Every hero goes in `backend/src/heroes/<name>.py` (one file per hero).
- Hero files must stay under 400 lines.
- Heroes auto-register via `pkgutil.iter_modules` — just create the file with a `Hero` subclass.

### Ability Design
- Every ability must have a `get_priority()` method override. No exceptions.
- `Base auto_priority` is a fallback, not a substitute — always set explicit priorities.
- `taps=True` abilities must still set priority (they compete with standard actions).
- `is_ultimate=True` auto-sets `max_charges=1` via `Ability.__post_init__`.

### Aiming
- Do NOT create custom Aiming subclasses to hack around missing entity types.
- If you need to target summons/objects, make them real Entity subclasses with `TargetEntity(in_range=X, condition=...)`.
- Custom Aiming types must be registered in `choices.py` `_get_plausible_uses_of_ability_at_pos` isinstance chain.

### Summons & Objects
- Use `Entity` subclass, not `Marker` for anything that can be targeted, has HP, or blocks movement.
- `Marker` = visual-only decoration. No HP, no targeting, no activation, no blocking.
- Summons get `DoNothing` automatically via `Entity.__init__`.

## Issue Tracking

### Issues live in specs/bugs/
- Every bug or design debt gets a file at `specs/bugs/BUG-<NNN>-<slug>.md`
- Registry at `specs/bugs/registry.yaml` tracks all issues
- Template:

```markdown
---
id: BUG-001
status: open
severity: major
area: hero/spy
---

# BUG-001: Spy decoys should be real objects

...
```

### Severity levels
- `critical` — crashes, wrong results, data loss
- `major` — feature broken, wrong behaviour
- `minor` — cosmetic, polish, nice-to-have
- `enhancement` — new capability or improvement

### Status values
- `open` — filed, needs triage
- `accepted` — confirmed, ready for work
- `in-progress` — being worked on
- `fixed` — fix committed (reference commit hash)
- `verified` — fix confirmed by test
- `deferred` — acknowledged but not scheduled
- `wontfix` — deliberately not fixing

### Before committing
1. File a bug for every defect found during development
2. Fix bugs in their own branch, one issue per fix
3. Never batch unrelated fixes in one commit

## Testing Standards

### Test Coverage
- Every ability must have at least one test verifying it is used by the AI.
- Every bug fix must have a regression test that would have caught it.
- Tests verify behaviour through public interfaces, not implementation details.

### Running Tests
```bash
python -m pytest tests/ -q --ignore=tests/test_heroes.py
```
- All tests must pass before commit. No exceptions.
- Slow tests (>100ms each) go in a separate integration test file.

### Ability Usage Verification
Before shipping any new hero:
```bash
python analyze_ability_usage.py HeroName --games 10
```
- Every ability must be used in at least 1/10 games.
- If an ability is never used, file a bug before shipping.

## Branch & Commit Standards

### Branching
- One feature per branch: `feat/e<NN>-<slug>`
- One bug fix per branch: `fix/bug-<NNN>-<slug>`
- Never batch unrelated changes in one branch.

### Commits
- Use Conventional Commits: `type(scope): description`
- Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `perf`
- One logical change per commit. No "fix everything" commits.
- Verify all tests pass before every commit.

### Releases
- Only merge to master after verify-work and audit-code pass.
- Use `release-branch` skill for merge/PR decisions.

## AI Agent Behaviour

### Before writing any code
1. Survey context (`survey-context`)
2. File issues for discovered defects first
3. Plan work in `specs/epics/` with `verify:` on every task
4. Create branch with `kickoff-branch`

### During development
1. Develop with `develop-tdd` (red-green-refactor)
2. Verify with `verify-work` (cold-start smoke, build, typecheck, lint, tests)
3. Audit with `audit-code` (self-review checklist)
4. Review with `request-review` (independent reviewer agent)

### Never
- Batch unrelated fixes in one commit
- Push unfinished work without documenting known issues
- Skip filing bugs for discovered defects
- Fix without a regression test
