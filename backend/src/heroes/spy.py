"""
Spy — infiltration hero with invisibility decoys.

Invisibility: Spy creates decoy entities at nearby positions.
Only the real Spy can be damaged, but enemies see all positions as equal.
When Spy moves, decoys move too. Attacking while invisible reveals Spy.
Decoys have 1 HP and can be destroyed by enemy attacks.
"""

from dataclasses import dataclass

from abilities import (
    Ability,
    ActionCost,
    Instruction,
    ActionContext,
)
from typing import Union
from point import Point
from valence import Valence
from instruction_library import DamageInstruction
from aimings import TargetEntity, TargetSelf, AimingResult
from engine import Engine
from entities import Hero, Entity
from events import after
from event_library import (
    ChangeLocationEvent,
    DamageEvent,
    DeathEvent,
)
from modifiers import Modifier
from point import Point

# todo this has little to do with the spy's definition in sample_heroes.yaml


class SpyDecoyEntity(Entity):
    """Entity that looks like a Spy to the enemy. 1 HP, no activation."""

    def __init__(self, engine: Engine, pos: Point, team: int, summoner_id: int):
        super().__init__(
            engine=engine, name="SpyDecoy", hp=1, speed=0, pos=pos, team=team
        )
        self.summoner_id = summoner_id


def is_enemy_or_decoy(engine: "Engine", actor: "Entity", point: "Point") -> bool:
    """Condition: target at point is an enemy OR a SpyDecoyEntity."""
    target = engine.entity_at(point)
    if target is None:
        return False
    if target.team != actor.team:
        return True
    return isinstance(target, SpyDecoyEntity)


@dataclass(kw_only=True)
class SpyInvisibilityManager(Modifier):
    """Manages Spy decoy entities — creates, moves, and cleans them up."""

    decoy_ids: list = None
    valence = Valence.GOOD

    def __post_init__(self):
        if self.decoy_ids is None:
            self.decoy_ids = []
        self._last_pos = None

    def create_decoys(self, engine: Engine, owner: Hero):
        """Create decoy entities at cells around the Spy (not on top of anyone)."""
        # Remove old decoys first
        self.remove_decoys(engine)
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
        for p in candidates:
            if len(chosen) >= 2:
                break
            if all(p.get_distance(c) >= 2 for c in chosen):
                chosen.append(p)
        # Fallback: just pick first 2
        while len(chosen) < 2 and candidates:
            p = candidates.pop(0)
            if p not in chosen:
                chosen.append(p)

        for pos in chosen[:2]:
            decoy = SpyDecoyEntity(
                engine=engine, pos=pos, team=owner.team, summoner_id=owner.id
            )
            self.decoy_ids.append(decoy.id)

    def remove_decoys(self, engine: Engine):
        """Remove all decoy entities."""
        for decoy_id in self.decoy_ids:
            decoy = engine.get_entity_by_id(decoy_id)
            if decoy:
                decoy.hp = 0
        self.decoy_ids = []

    def move_decoys(self, engine: Engine, old_pos: Point, new_pos: Point):
        """Move decoys along with Spy using the same relative offset."""
        dx = new_pos.x - old_pos.x
        dy = new_pos.y - old_pos.y
        for decoy_id in self.decoy_ids:
            decoy = engine.get_entity_by_id(decoy_id)
            if decoy and decoy.pos is not None:
                new_decoy_pos = Point(decoy.pos.x + dx, decoy.pos.y + dy)
                # Clamp to grid bounds
                new_decoy_pos = Point(
                    max(0, min(engine.grid.width - 1, new_decoy_pos.x)),
                    max(0, min(engine.grid.height - 1, new_decoy_pos.y)),
                )
                decoy.pos = new_decoy_pos

    @after(ChangeLocationEvent, only_self=False)
    def on_spy_move(self, engine: "Engine", event: ChangeLocationEvent):
        if event.subject_id != self.owner_id:
            return
        owner = engine.get_entity_by_id(self.owner_id)
        if not owner or not owner.pos:
            return
        if self._last_pos is not None:
            self.move_decoys(engine, self._last_pos, owner.pos)
        self._last_pos = owner.pos

    @after(DeathEvent)
    def on_spy_death(self, engine: "Engine", event: DeathEvent):
        if event.subject_id != self.owner_id:
            return
        self.remove_decoys(engine)


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


class RevolverAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Revolver",
            aiming=TargetEntity(in_range=4, condition=is_enemy_or_decoy),
            instructions=[DamageInstruction(amount=2)],
            is_default=True, requires_target=False, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                return 6.0
            if isinstance(target, SpyDecoyEntity):
                return 1.0  # Better than Do Nothing even if only decoy in range
        return 0.0


class KnifeAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Knife",
            aiming=TargetEntity(in_range=1, condition=is_enemy_or_decoy),
            instructions=[DamageInstruction(amount=4)],
            max_charges=1, requires_target=False, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target:
                if target.team != actor.team:
                    return 7.0  # High damage, limited use
                if isinstance(target, SpyDecoyEntity):
                    return 2.0
        return 0.0


class GoInvisibleAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Go Invisible", text="Re-gain your spy decoys.",
            aiming=TargetSelf(), instructions=[],
            max_charges=1, requires_target=False, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        # Check if decoys are missing (Spy was revealed)
        invis = actor.get_modifier(SpyInvisibilityManager) if hasattr(actor, 'get_modifier') else None
        if invis and len(invis.decoy_ids) < 2:
            return 2.0  # Valuable — re-gain decoys
        return 0.0


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

        self.abilities.append(RevolverAbility(owner_id=self.id))
        self.abilities.append(KnifeAbility(owner_id=self.id))
        self.abilities.append(GoInvisibleAbility(owner_id=self.id))
