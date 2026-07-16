# Game Runner: Setup & Visualize

## Problem Statement

The project has a working tactical game engine and a basic log visualizer, but there's no way to set up a game from the UI and watch it play out. Currently you must edit Python files to change teams, run a script, and drag-drop a JSON log file into a browser to step through it. The visualizer itself is functional but hard to follow — entities are text labels, there's no terrain or markers, reaction chains collapse into one frame, and the overall experience makes it difficult to study team synergies and counters.

## Solution

A two-part system:

1. **Python backend** (FastAPI) with a single endpoint `POST /run-game` that accepts a hero configuration and returns a complete game log.
2. **Frontend** (React) with two screens:
   - **Setup screen** — select heroes for each team and place them on a grid
   - **Playback screen** — step through the game log with arrow keys, showing animated movement, attack indicators, terrain, markers, entity facing, a written log, and per-action granularity so reaction chains are visible

This replaces the current drag-drop-log workflow entirely.

## User Stories

1. As a player, I want to see a roster of all available heroes, so that I know which heroes exist to pick from.
2. As a player, I want to add any hero to either team without restrictions, so that I can compose any matchup.
3. As a player, I want to place each hero on any unoccupied grid position, so that I can control deployment.
4. As a player, I want to see both teams' configurations before starting, so that I can verify my setup.
5. As a player, I want to press a "Play" button to run the game, so that the AI plays out the matchup.
6. As a player, I want to step through the game turn by turn with arrow keys, so that I can understand each action.
7. As a player, I want to see each individual action as its own step, so that I can follow chains of reactions.
8. As a player, I want to see entities rendered with distinct visuals (shapes, colors, icons), so that I can identify units at a glance.
9. As a player, I want to see terrain rendered on the grid, so that the battlefield state is clear.
10. As a player, I want to see markers (objects, barriers) rendered on the grid, so that I can track deployed objects.
11. As a player, I want to see direction indicators for entities that have facing, so that I understand positioning.
12. As a player, I want to see health bars and status effects on each entity, so that I can assess unit state quickly.
13. As a player, I want to see damage numbers, ability names, and attack animations play out, so that combat is legible.
14. As a player, I want to see a written log alongside the visual display, so that I can read a description of what happened.
15. As a player, I want animated movement and attacks, so that the game is more visually engaging.
16. As a player, I want to pause auto-play and step manually, so that I can examine key moments in detail.
17. As a player, I want the game to run from a single button press without file management, so that the setup-to-watch loop is frictionless.

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
  "seed": int,             // RNG seed for reproducibility (optional, default random)
  "grid_size": int,        // Grid dimensions (e.g., 5 = 5x5)
  "teams": [
    {
      "heroes": [
        { "class": "Axe", "pos": [0, 0] },
        { "class": "Necrophos", "pos": [0, 1] }
      ]
    },
    {
      "heroes": [
        { "class": "MeleeHero", "pos": [4, 3] },
        { "class": "Viktoria", "pos": [4, 4] }
      ]
    }
  ]
}

Response: GameLog (the existing GameLog schema, unchanged)
```

The `"class"` field maps to the hero class names in `src/heroes/`. Invalid class names or occupied positions return a 400 error.

### Setup Screen

- Left panel: hero roster with click-to-add buttons per team
- Center: grid display for placing heroes
- Each team has a distinct color (blue/red)
- Click a placed hero to remove and return to roster
- "Play" button is enabled when both teams have at least 1 hero

### Visualizer Improvements

- **Entity rendering**: Replace text labels with colored circles/shapes. Team color fills, distinct border for active entity.
- **Health bars**: Bar + numeric HP display.
- **Status effects**: Icons or abbreviated text above entity.
- **Terrain rendering**: Phaser grid supports colored tiles/cell fills for walls and hazards.
- **Marker rendering**: Objects rendered on the grid (e.g., turret icons, barrier lines).
- **Facing indicators**: Arrow or wedge showing entity facing direction.
- **Reaction granularity**: Each event in a reaction chain is a separate step. The written log side panel shows the full event chain.
- **Attack animation**: Arrow/thrown projectile from attacker to target, damage number popup.
- **Movement animation**: Tween entity across intermediate grid positions.
- **Auto-play**: Toggle auto-advance with configurable speed; pause and step revert to manual control.

### Backend Changes

- A new `backend/` directory at repo root containing `main.py` (FastAPI app) and a `requirements.txt` adding `fastapi` and `uvicorn`.
- The existing `src/` modules are imported directly — no restructuring.
- A `POST /heroes` endpoint returns the list of available hero classes for the roster.

### Setup Screen Data

- The hero roster is populated by reading hero classes from `src/heroes/`. This avoids duplicating hero definitions.
- Each hero class exposes: name, health, speed, and a list of abilities for tooltip display.

## Testing Decisions

### What makes a good test

Test external behavior at the seam boundary, not internal implementation details. The seam for the backend is the API endpoint. The seams for the frontend are the React component surfaces.

### Backend tests

- **API integration test**: `POST /run-game` with a valid team config returns 200 and a valid `GameLog` with non-empty logs.
- **API error case**: `POST /run-game` with an invalid hero class returns 400.
- **API error case**: `POST /run-game` with overlapping positions returns 400.

These sit in `tests/test_api.py` and use FastAPI's `TestClient`.

### Frontend tests

- **Setup screen renders hero roster**: mock hero data renders the expected number of hero cards.
- **Setup screen places hero on grid**: clicking a hero then clicking a grid cell places it.
- **Setup screen removes hero**: clicking a placed hero returns it to roster.
- **Visualizer renders game state**: given a mock `EngineState`, the playback screen shows the correct number of entities in the correct positions.

These use Vitest + React Testing Library in the `front/` directory. Since the visualizer uses Phaser directly, visualizer tests may test at the React wrapper level rather than deep Phaser internals.

### Unit tests

The existing `tests/` directory already covers engine internals. No new unit tests are needed for the engine — the API test validates integration.

## Out of Scope

- Economy systems (buy, sell, interest, leveling)
- Shop/reroll mechanics
- Synergy bonuses in the engine (bonuses for fielding multiple units of the same type)
- Multiplayer
- Save/load game states
- Build pipeline or deployment
- Styling polish beyond basic clarity

## Further Notes

- The existing `Agent` classes (rule-based, MCTS, random) are all usable. The default agent for auto-play is `RuleBasedAgent` since it's deterministic and fast. MCTS can be offered as an option later.
- The current grid size is 5x5 by default. The API accepts configurable grid sizes.
- The `GameLog` schema captures the full sequence of before/after state pairs. The frontend should cache the loaded log in memory — no need for state management beyond React state.
- Seed is exposed for reproducibility: the same seed + same team config = identical game.
