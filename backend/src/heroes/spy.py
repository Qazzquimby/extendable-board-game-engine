"""
Spy — infiltration hero with invisibility decoys.

Invisibility: Spy creates decoy markers at nearby positions.
Only the real Spy can be damaged, but enemies see all positions as equal.
When Spy moves, decoys move too. Attacking while invisible reveals Spy.
"""

from dataclasses import dataclass

from abilities import (
    Ability,
    ActionCost,
)
from valence import Valence
from instruction_library import DamageInstruction
from aimings import (
    TargetEntity,
    TargetSelf,
    Aiming,
    AimingResult,
)
from engine import Engine
from entities import Hero, Marker
from events import after
from event_library import (
    ChangeLocationEvent,
    DamageEvent,
    DeathEvent,
)
from modifiers import Modifier
from point import Point


class SpyDecoyMarker(Marker):
    """Marker that looks like a Spy to the enemy."""

    def __init__(self, engine: Engine, pos: Point, team: int, summoner_id: int):
        super().__init__(
            engine=engine, name="Spy Decoy", pos=pos, team=team, summoner_id=summoner_id
        )


@dataclass(kw_only=True)
class SpyInvisibilityManager(Modifier):
    """Manages Spy decoy markers — creates, moves, and cleans them up."""

    decoy_ids: list = None
    valence = Valence.GOOD

    def __post_init__(self):
        if self.decoy_ids is None:
            self.decoy_ids = []
        self._last_pos = None

    def create_decoys(self, engine: Engine, owner: Hero):
        """Create decoy markers at cells around the Spy (not on top of anyone)."""
        self.decoy_ids = []
        if not owner.pos:
            return
        # Find empty cells within range 2 (not occupied by entities)
        candidates = []
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx == 0 and dy == 0:
                    continue
                p = Point(owner.pos.x + dx, owner.pos.y + dy)
                if 0 <= p.x < engine.grid.width and 0 <= p.y < engine.grid.height:
                    if not engine.entity_at(p):
                        candidates.append(p)
        # Pick up to 2 decoy positions, preferring ones far from each other
        chosen = []
        for p in candidates[:8]:  # limit candidates to adjacent
            if len(chosen) >= 2:
                break
            # Prefer far from existing chosen decoys
            if all(p.get_distance(c) >= 2 for c in chosen):
                chosen.append(p)
        # Fallback: just pick first 2
        while len(chosen) < 2 and candidates:
            p = candidates.pop(0)
            if p not in chosen:
                chosen.append(p)

        for pos in chosen[:2]:
            marker = SpyDecoyMarker(
                engine=engine, pos=pos, team=owner.team, summoner_id=owner.id
            )
            self.decoy_ids.append(marker.id)

    def remove_decoys(self, engine: Engine):
        """Remove all decoy markers."""
        engine.markers = [m for m in engine.markers if m.id not in self.decoy_ids]
        self.decoy_ids = []

    def move_decoys(self, engine: Engine, old_pos: Point, new_pos: Point):
        """Move decoys along with Spy using the same relative offset."""
        dx = new_pos.x - old_pos.x
        dy = new_pos.y - old_pos.y
        for marker_id in self.decoy_ids:
            marker = next((m for m in engine.markers if m.id == marker_id), None)
            if marker and marker.pos is not None:
                new_decoy_pos = Point(
                    marker.pos.x + dx, marker.pos.y + dy
                )
                # Clamp to grid bounds
                new_decoy_pos = Point(
                    max(0, min(engine.grid.width - 1, new_decoy_pos.x)),
                    max(0, min(engine.grid.height - 1, new_decoy_pos.y)),
                )
                marker.pos = new_decoy_pos

    @after(ChangeLocationEvent, only_self=False)
    def on_spy_move(self, engine: "Engine", event: ChangeLocationEvent):
        if event.subject_id != self.owner_id:
            return
        owner = engine.get_entity_by_id(self.owner_id)
        if not owner or not owner.pos:
            return
        # We don't have old_pos from the event, so store it
        if hasattr(self, '_last_pos') and self._last_pos is not None:
            self.move_decoys(engine, self._last_pos, owner.pos)
        self._last_pos = owner.pos

    @after(DeathEvent)
    def on_spy_death(self, engine: "Engine", event: DeathEvent):
        if event.subject_id != self.owner_id:
            return
        self.remove_decoys(engine)


class TargetSpyOrDecoys(Aiming):
    """Targets enemy entities OR Spy decoy markers (for targeting through invisibility)."""

    def __init__(self, in_range: int = None):
        super().__init__()
        self.in_range = in_range

    def get_all_aimings(
        self, engine: "Engine", actor: "Entity", start_pos=None, require_los=True,
    ) -> list:
        if not start_pos:
            start_pos = actor.pos

        results = []
        # Regular entities
        from aimings import get_blocked_points
        blocked = get_blocked_points(engine, actor) if require_los else set()
        targets = set()

        for e in engine.entities:
            if e.pos is None or e.team == actor.team:
                continue
            if self.in_range is not None:
                d = engine.grid.get_range(start_pos, e.pos)
                if d > self.in_range:
                    continue
            if require_los and e.pos in blocked:
                continue
            targets.add(e.pos)

        # Spy decoy markers (on enemy team from actor's perspective)
        for m in getattr(engine, "markers", []):
            if m.pos is None or m.team == actor.team:
                continue
            if not isinstance(m, SpyDecoyMarker):
                continue
            if self.in_range is not None:
                d = engine.grid.get_range(start_pos, m.pos)
                if d > self.in_range:
                    continue
            targets.add(m.pos)

        for pos in targets:
            results.append(AimingResult(target_points=[pos]))
        return results


class RevealOnHit(Modifier):
    """Reveals Spy when damaged — removes invisibility decoys."""
    valence = Valence.BAD

    @after(DamageEvent)
    def on_damage(self, engine: "Engine", event: DamageEvent):
        if event.subject_id != self.owner_id:
            return
        owner = engine.get_entity_by_id(self.owner_id)
        if owner:
            invis = owner.get_modifier(SpyInvisibilityManager)
            if invis:
                invis.remove_decoys(engine)


class Spy(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Spy", hp=6, speed=3, pos=pos, team=team)

        # Invisibility system
        self.invisibility = SpyInvisibilityManager()
        self.add_modifier(engine, self.invisibility)

        # Reveal on being hit
        self.add_modifier(engine, RevealOnHit())

        # Create decoys AFTER position is set (super().__init__ sets pos)
        self.invisibility.create_decoys(engine, self)

        # Revolver — basic attack that can target through decoys
        self.abilities.append(
            Ability(
                name="Revolver",
                aiming=TargetSpyOrDecoys(in_range=4),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )

        # Knife — backstab (high damage if target can't see you)
        self.abilities.append(
            Ability(
                name="Knife",
                aiming=TargetSpyOrDecoys(in_range=1),
                instructions=[DamageInstruction(amount=4)],
                max_charges=1,
                owner_id=self.id,
            )
        )

        # Go Invisible — regain decoys after being revealed
        self.abilities.append(
            Ability(
                name="Go Invisible",
                text="Re-gain your spy decoys.",
                aiming=TargetSelf(),
                instructions=[],
                max_charges=1,
                owner_id=self.id,
            )
        )
