# Game Runner: Setup & Visualize

## Problem Statement

The project has a working tactical game engine and a basic log visualizer, but there's no way to set up a game from the UI and watch it play out. Currently you must edit Python files to change teams, run a script, and drag-drop a JSON log file into a browser to step through it. The visualizer itself is functional but hard to follow — entities are text labels, reaction chains collapse into one frame, and the overall experience makes it difficult to study team synergies and counters.

## Solution

A two-part system:

1. **Python backend** (FastAPI) with a single endpoint `POST /run-game` that accepts a hero configuration and returns a complete game log.
2. **Frontend** (React) with two screens:
   - **Setup screen** — select heroes for each team and place them on a grid
   - **Playback screen** — step through the game log with arrow keys, showing animated movement, attack indicators, a written log, and per-action granularity so reaction chains are visible

This replaces the current drag-drop-log workflow entirely.

## User Stories

1. As a player, I want to see a roster of all available heroes, so that I know which heroes exist to pick from.
2. As a player, I want to add any hero to either team without restrictions, so that I can compose any matchup.
3. As a player, I want to place each hero on any unoccupied grid position, so that I can control deployment.
4. As a player, I want to see both teams' configurations before starting, so that I can verify my setup.
5. As a player, I want to press a "Play" button to run the game, so that the AI plays out the matchup.
6. As a player, I want to step through the game turn by turn with arrow keys, so that I can understand each action.
7. As a player, I want to see each individual action as its own step, so that I can follow chains of reactions.
8. As a player, I want to see health bars and status effects on each entity, so that I can assess unit state quickly.
9. As a player, I want to see damage numbers, ability names, and attack animations play out, so that combat is legible.
10. As a player, I want to see a written log alongside the visual display, so that I can read a description of what happened.
11. As a player, I want animated movement and attacks, so that the game is more visually engaging.
12. As a player, I want to pause auto-play and step manually, so that I can examine key moments in detail.
13. As a player, I want the game to run from a single button press without file management, so that the setup-to-watch loop is frictionless.

## Implementation Decisions

### Architecture

- **Backend**: A FastAPI server that imports the existing `engine` module. No engine rewrites.
- **Frontend**: The existing React + Phaser frontend, extended with a setup screen.
- **Communication**: Single `POST /run-game` request. No streaming or WebSocket needed — the game runs instantly.

### API Contract

```
POST /run-game

Request body:
{
  "seed": int,
  "grid_size": int,
  "teams": [
    { "heroes": [{ "class": "Axe", "pos": [0, 0] }, ...] },
    { "heroes": [{ "class": "MeleeHero", "pos": [4, 3] }, ...] }
  ]
}

Response: GameLog
```

The `"class"` field maps to hero class names in `src/heroes/`. Invalid class names → 400. Occupied positions → 400.

### Log Format (Event-Based)

No before/after state pairs. Each `LogEntry` contains:
- `state: EngineState` — world state after this entry's events
- `events: EventDescription[]` — what happened (type, actor_id, target_id, amounts, positions)
- `messages: string[]` — human-readable descriptions
- `done: boolean`

**Merge logic**: Consecutive events with the same `(type, source_id)` merge into one entry. `AbilityUseEvent` always starts a new frame. This gives per-source granularity (Viktoria's damage ≠ Axe's counter-attack damage).

**De-duplication**: The 3-phase event pipeline (BEFORE→RESOLVE→AFTER) re-enqueues each event twice. The log only captures descriptions during the RESOLVE phase (after `_resolve()` runs, before AFTER hooks), so each event produces exactly one description.

**Initial frame**: Entry 0 has empty events array — the frontend shows the starting board.

### Setup Screen

- Left panel: hero roster with click-to-add buttons per team
- Center: grid display for placing heroes
- Each team has a distinct color (blue/red)
- Click a placed hero to remove and return to roster
- "Play" button enabled when both teams have ≥1 hero

### Visualizer Improvements

- **Entity rendering**: Colored circles/shapes with team fill, active-entity highlight ring (yellow).
- **Health bars**: Below entity name, proportional to tileSize (~1.6× radius wide, 8px tall, at y=14 from center).
- **Status effects**: Not yet implemented.
- **Event-driven animation** (not yet implemented):
  - `move` events: tween entity from `source_pos` to `target_pos` along path
  - `damage` events: show damage number popup on target, attack arrow from source→target
  - `ability_use` events: flash actor, show ability name
  - `heal` events: green heal number popup
  - `death` events: red flash / fade-out
- **Auto-play**: Toggle auto-advance with configurable speed (150–1500ms); pause reverts to manual.
- **Viewport lock**: The page uses `height: 100vh; overflow: hidden` — never scrolls. Log sidebar scrolls internally.

### Backend Changes

- `backend/main.py` — FastAPI app with `POST /run-game` and `GET /heroes`
- `backend/requirements.txt` — fastapi + uvicorn
- The existing `src/` modules are imported directly.

### Game Log Sidebar

The written log sidebar shows `messages` from the current `LogEntry`. Future enhancement: show full event chain with targeting info, source→target names, per-event detail rows.

## Testing Decisions

### What makes a good test

Test external behavior at the seam boundary, not internal implementation details. The seam for the backend is the API endpoint. The seams for the frontend are the React component surfaces.

### Backend tests

- **API integration test**: `POST /run-game` returns 200 + valid `GameLog`
- **API error case**: Invalid hero class → 400
- **API error case**: Overlapping positions → 400

These sit in `tests/test_api.py` and use FastAPI's `TestClient`.

### Frontend tests

- Setup screen renders hero roster, places hero, removes hero
- Playback screen renders game state from mock
- Uses Vitest + React Testing Library

### Unit tests

65 existing engine unit tests (pytest). No new unit tests needed for the engine.

## Out of Scope

- Economy systems (buy, sell, interest, leveling)
- Shop/reroll mechanics
- Synergy bonuses
- Multiplayer
- Save/load
- Build pipeline or deployment
- Styling polish beyond basic clarity

## Further Notes

- Default agent is `RuleBasedAgent` (deterministic, fast)
- Grid size configurable via API (5×5 default, up to 10×10)
- Seed exposed for reproducibility
- Engine's 3-phase event pipeline (BEFORE→RESOLVE→AFTER) is a core design — frontend log processors must handle de-duplication
