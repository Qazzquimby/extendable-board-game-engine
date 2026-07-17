# Game Runner Spec

## Overview

FastAPI backend runs tactical game simulations. React/Phaser frontend provides setup and playback.

## API

```
POST /run-game  →  GameLog
GET  /heroes    →  string[]
```

`GameLog` has `winner_team: int | None` and `logs: LogEntry[]`.

## Log Format

Each `LogEntry` contains:
- `state: EngineState` — world snapshot
- `events: EventDescription[]` — what happened (type, actor/target IDs, amounts, positions)
- `messages: string[]` — human-readable event descriptions
- `action_logs: string[]` — hierarchical combat log with crit/miss/damage/modifier details
- `done: bool`

**Merge**: Same `(type, source_id)` events merge into one frame. `AbilityUseEvent` always starts a new frame. Subsequent same-action events (damage, heals, moves) are absorbed into the ability's frame.

**No duplicate descriptions**: The 3-phase pipeline (BEFORE→RESOLVE→AFTER) re-enqueues events twice. Only `state == "BEFORE"` produces descriptions. `AbilityUseEvent` describes at BEFORE; damage/move events describe at RESOLVE.

## Animations

- **Move**: tween entity sprite `source_pos → target_pos` (400ms)
- **Damage**: red floating "-N" at target position
- **Heal**: green floating "+N"
- **Ability**: flash entity, show ability name
- **Death**: entity fades out

## Viewport

Page is `height: 100vh; overflow: hidden` — never scrolls. Both sidebars scroll internally.

## Reactions (Instant Abilities)

Instant abilities (`ActionCost.INSTANT`) can be used as reactions during enemy turns. The `ReactionOpportunityEvent` fires between BEFORE and RESOLVE phases. The reacting entity's blink/teleport is enqueued at the front and processed before the original attack resolves, so the attack hits the now-empty space and misses.

**Reaction priority** is composable across three functions in `abilities.py`:
- `reaction_value_of_instructions()` — scores all harmful instructions (damage, tokens, pulls) targeting the reactor
- `reaction_escapes_area()` — checks if destination is outside trigger's area
- `reaction_resource_conservation()` — universal penalty for using charged abilities based on scarcity + game progress

## Engine Details

- 3-phase event pipeline: BEFORE → RESOLVE → AFTER
- `advance_until_choice()` handles `ReactionOpportunityEvent` and `DecisionEvent`
- `RuleBasedAgent` picks highest-priority action; ties broken by lowest distance moved
- Ultimates check `ultimate_turn` via `is_available(round_num=round_num)`
