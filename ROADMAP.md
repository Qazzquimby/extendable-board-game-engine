# Development Roadmap

All features must be tested and type hinted.

## Phase 1: Core Engine Completeness (Rules & Mechanics)
- **Math & Modifiers:** Implement "multiply before add", division/multiplication cancellation, and "always round up" rules in `ModValue`.
- **Grid & Movement:** Implement a proper 2D grid, non-diagonal movement, pathfinding, blocking terrain, and forced movement (push/pull).
- **Vision & Line of Sight:** Implement corner-to-corner LoS checking and cover mechanics (+2 defense).
- **Abilities & Targeting:** Expand the action system to support AoE (burst, line, path), ranges, and targeting empty spaces.
- **Event System Enhancements:** Add support for replacement events, deterministic ability ordering, and conditional modifiers.
- **Turn Management:** Implement the sequence of play (Rounds, Turns, Move/Standard/Free Actions, Tapping/Untapping).

## Phase 2: Observability & State Management (AlphaZero Prep)
- **State Serialization:** Implement deep copying and JSON/dict export of the full game state (entities, positions, modifiers, hp).
- **Action Space Definition:** Create a discrete, enumerable action space for RL agents (e.g., Move(x,y), UseAbility(id, target_x, target_y)).
- **Determinism & RNG:** Centralize and seed all random number generation (attack rolls, crits) to ensure reproducible rollouts.
- **Event Logging:** Build a history/replay system that logs all events and state changes for debugging and training analysis.

## Phase 3: AlphaZero Integration
- **Environment Wrapper:** Create an OpenAI Gym or PettingZoo compatible interface for the engine.
- **Heuristic Bots:** Develop simple rule-based bots (like the Axe bot in `sample_heroes.yaml`) for baseline testing and sanity checks.
- **MCTS & Neural Net:** Implement Monte Carlo Tree Search and a neural network architecture for state evaluation and policy prediction.
- **Self-Play Loop:** Build the self-play data generation and training pipeline.

## Phase 4: Godot Playability
- **API / Binding Layer:** Expose the Python engine to Godot (via WebSockets, REST, or GDExtension/Python bindings).
- **Visual Event Queue:** Modify the engine's router to yield animation-friendly events (e.g., `DamageEvent` triggers a visual hit reaction before state updates).
- **UI Translation:** Map Godot UI interactions (clicks, drags) to Engine `Action` objects.
- **State Synchronization:** Ensure the Godot client can perfectly reconstruct the visual board from the engine's serialized state.
