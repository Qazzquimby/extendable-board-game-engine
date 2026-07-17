# Game Engine — Domain Glossary

<!-- Resolved during 2025-07-16 grilling session on log splitting. -->

## Terms

### Action
An ability activation chosen by an agent. One `Action` = one ability used by one actor.
Represented by `ActionState` in the log.

### Event
A single state change within the engine (DamageEvent, HealEvent,
ChangeLocationEvent, etc.). Events are processed through a queue; one Action
typically triggers a chain of Events.

### Reaction
An Event that fires in response to another Event, registered via Modifier hooks
(e.g., `@after(DamageEvent)`). Reactions are processed synchronously within
the same Action's event-processing window.

### Frame
A single visual state shown in the frontend, corresponding to one `LogEntry`.
The user steps through Frames with arrow keys.

### Log Entry
A record of one atomic unit of gameplay for display. Contains a `state` (the
world after this entry's events) and a list of `events` describing what changed.

### Event Merge Key
A compound key `(type, source_id)` used for merging consecutive events into
one LogEntry. Two events merged if they have the same type AND same source
entity. This prevents events from different actors (e.g., Viktoria's attack
damage vs Axe's counter-attack damage) from being merged into one frame.

### Three-Phase Pipeline
Each Event passes through three processing phases: BEFORE (fires before-hooks
and modifiers), RESOLVE (applies the event's effect via `_resolve()`), and
AFTER (fires after-hooks). The event is re-enqueued between phases. The log
system captures descriptions only during the RESOLVE phase to avoid 3×
duplication.

### Initial Frame
The first Log Entry in a game log, containing only the starting board state
(with no events). The frontend renders this as the player's first view.

### Marker
A placed object on the grid that has no health, no actions, and is typically
untargetable. Tracked separately from Entities in the engine. Examples: Tracer's
Pulse Bomb, Symmetra's turret locations (as deployables).

### Object
A grid entity that has health but does not move or act. A cross between a
Marker and an Entity. Examples: Symmetra's barriers.

### Initial Frame
The first Log Entry in a game log, containing only the starting board state
(with no events). The frontend renders this as the player's first view.
