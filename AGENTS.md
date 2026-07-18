## Agent skills

### Issue tracker

Issues live in `specs/bugs/`. See `docs/agents/issue-tracker.md`.

- Registry: `specs/bugs/registry.yaml`
- One file per bug: `specs/bugs/BUG-<NNN>-<slug>.md`
- Before any coding, file bugs for discovered defects FIRST.
- Never batch unrelated fixes in one commit.

### Triage labels

Status values: `open`, `accepted`, `in-progress`, `fixed`, `verified`, `deferred`, `wontfix`
Severity: `critical`, `major`, `minor`, `enhancement`
See `CONVENTIONS.md` for full policy.

### Domain docs

Single-context repo. See `docs/agents/domain.md`.

### Mandatory policies

**Read CONVENTIONS.md before any coding session.** It contains:
- Code standards (400-line file limit, function sizing, naming)
- Hero and ability design rules
- Issue tracking process
- Testing standards (all abilities must be used by AI)
- Branch and commit standards (one fix per commit)
- AI agent behaviour (survey before coding, file bugs first)

### Workflow

Before writing code:
1. `survey-context` → read state + existing issues
2. File bugs for any defects found
3. Plan work via `elaborate-spec` → `scope-work` → `slice-tasks` → `plan-work`
4. `kickoff-branch` → feature branch
5. `develop-tdd` → red-green-refactor
6. `verify-work` → UAT gate
7. `audit-code` → checklist
8. `commit-message` → conventional commit
9. `release-branch` → merge
