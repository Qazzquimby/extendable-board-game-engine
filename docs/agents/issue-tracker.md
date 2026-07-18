# Issue tracker: specs/bugs/

Issues and bug reports live at `specs/bugs/` with registry at `specs/bugs/registry.yaml`.

## Conventions

- One bug per file: `specs/bugs/BUG-<NNN>-<slug>.md`
- Sequential IDs starting at BUG-001
- Registry: `specs/bugs/registry.yaml` lists all bugs with status/severity/area

## Severity

- `critical` — crashes, wrong results, data loss
- `major` — feature broken, wrong behaviour
- `minor` — cosmetic, polish, nice-to-have
- `enhancement` — new capability or improvement

## Status values

- `open` — filed, needs triage
- `accepted` — confirmed, ready for work
- `in-progress` — being worked on
- `fixed` — fix committed (reference commit hash)
- `verified` — fix confirmed by test
- `deferred` — acknowledged but not scheduled
- `wontfix` — deliberately not fixing

## When a skill says "publish to the issue tracker"

1. Assign next available BUG-NNN number from `registry.yaml`
2. Create file `specs/bugs/BUG-<NNN>-<slug>.md`
3. Add entry to `registry.yaml`

## When a skill says "fetch the relevant ticket"

Read the file at `specs/bugs/<id>.md`.
