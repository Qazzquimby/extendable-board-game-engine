# Tech Stack & Architecture

## Stack

| Layer | Technology | Purpose |
| ------- | ----------- | --------- |
| Backend | Python 3.12 | Game engine logic |
| API | FastAPI | HTTP endpoints for simulation |
| Schemas | Pydantic BaseModel | Request/response validation |
| Frontend | React + Phaser | Game setup and playback UI |
| Build | Vite | Frontend bundling |
| Tests | pytest | Backend test suite |

## Architecture

### Backend Modules (`backend/src/`)

```
main.py              → FastAPI endpoints (run-game, heroes)
engine.py            → Core game loop, event processing, agent management
events.py            → Event base class, queue, 3-phase pipeline, Router
abilities.py         → Ability definitions, ActionCost, Instructions, reaction priority
entities.py          → Entity, Hero, Marker base classes
schemas.py           → Pydantic models (GameLog, LogEntry, EventDescription, etc.)
logger.py            → Hierarchical Logger with context manager scopes
grid.py              → Grid system with positions and pathfinding
point.py             → Point class for grid coordinates
aimings.py           → Targeting logic (single target, areas)
areas.py             → Area shapes (burst, line, path, NxN)
choices.py           → Action choices and plausible action generation
modifiers.py         → Modifier base class and modifier system
instruction_library.py → Instruction definitions (damage, heal, move, etc.)
event_library.py     → Concrete event types
features.py          → Feature/value system for abilities
mod_value.py         → Dynamic value computation for modifiers
queries.py           → Query system for information gathering
hero_registry.py     → Hero class registry and lookup
heroes/              → Per-hero modules (tracer, symmetra, axe, etc.)
valence.py           → Valence scoring (positive/negative effects)
game_setup.py        → Game setup configuration
util.py              → Utilities (UniqueTuple, EntityId)
```

### Frontend (`front/`)

```
src/                 → React components and Phaser game scenes
index.html           → Entry point
vite.config.ts       → Vite configuration
vitest.config.ts     → Test configuration
```

### Event Pipeline

```
Action chosen
  ↓
AbilityUseEvent (BEFORE)
  → Router publishes BEFORE phase
  → ReactionOpportunityEvent enqueued (if not a reaction)
  → Modifiers fire @before(AbilityUseEvent)
  ↓
AbilityUseEvent (RESOLVE)
  → _resolve() calls ability.execute_instructions()
  → Instructions generate events (DamageEvent, HealEvent, etc.)
  → Each instruction event goes through its own 3-phase cycle
  → DamageEvent RESOLVE: _resolve() applies damage to target
  ↓
AbilityUseEvent (AFTER)
  → Router publishes AFTER phase
  → ReactionOpportunityEvent enqueued (if not a reaction)
  → Modifiers fire @after(AbilityUseEvent)
```

### Log Capture Pipeline

```
step() begins → reset_logs()
  → Ability use (with log(...) scope):
    → Hierarchical tree built via Logger context managers
  → _process_events_into_log():
    → Event processing loop with merge/absorption
    → Each flush captures get_logs() snapshot
  → advance_until_choice():
    → Processes remaining events (damage, modifiers)
    → New logs appended to last entry
  → step() ends
```

### Reaction Architecture

1. `AbilityUseEvent.process(BEFORE)` enqueues `ReactionOpportunityEvent`
2. Engine hits `ReactionOpportunityEvent` in `_process_events_into_log`
3. If reaction choices exist → break for AI decision
4. AI picks reaction → `step()` executes the reaction via `ability.react()`
5. Reaction ability enqueues its own events (e.g., teleport/blink)
6. Processing resumes — original attack resolves, hits now-empty space → miss

### Key Design Decisions

- **3-phase pipeline** over flat processing: enables modifier hooks at all stages
- **Event merge by (type, source_id)**: prevents frame clutter from different actors
- **Ability absorption**: after an ability use, all subsequent events from the same
  action merge into one frame, ending at the next ability use
- **Logger as context manager**: produces hierarchical, scoped logs per action
  instead of flat text
- **Composable reaction priority**: each hero contributes priority scores;
  the highest-scored reaction is chosen by RuleBasedAgent
