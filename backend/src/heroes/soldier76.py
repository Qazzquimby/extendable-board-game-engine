"""Soldier 76 — mobile sustained ranged damage and self healing.

Heavy Pulse Rifle: Range 4, 3dmg (default)
Sprint: Move 3 (default)
Helix Rockets: 1/game, Range 4, +2 miss, 3dmg + burst 1 around target 1dmg
Biotic Field: 1/game, 2x2 marker, heals allies at start of creator's activation
Tactical Visor: Ultimate 4, Free Action, unlimited + undefendable defaults
"""

from dataclasses import dataclass

from abilities import Ability, ActionCost
from instruction_library import DamageInstruction, AddModifierInstruction
from aimings import TargetEntity, IncludeArea, TargetSelf
from areas import Burst
from engine import Engine
from entities import Hero, Marker
from modifiers import Modifier
from events import after
from event_library import TurnStartEvent, HealEvent
from valence import Valence
from point import Point
from typing import Union
from aimings import AimingResult, MultipleAimingResults
from queries import QuerySpeed


# ── Modifiers ──

class VisorModifier(Modifier):
    valence = Valence.GOOD
    def apply_undefendable(self) -> bool:
        return True
    def modify_range(self, base_range: int) -> int:
        return 999


@dataclass(kw_only=True)
class BioticFieldManager(Modifier):
    field_id: int = None
    valence = Valence.GOOD

    @after(TurnStartEvent, only_self=False)
    def on_summoner_turn(self, engine, event):
        if event.subject_id != self.owner_id or self.field_id is None:
            return
        # Find the marker
        marker = next((m for m in engine.markers if m.id == self.field_id), None)
        if not marker or marker.pos is None:
            self.field_id = None
            return
        # Heal allies in 2x2 area around marker
        half = 1
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                pt = Point(marker.pos.x + dx, marker.pos.y + dy)
                if not (0 <= pt.x < engine.grid.width and 0 <= pt.y < engine.grid.height):
                    continue
                entity = engine.entity_at(pt)
                if entity and entity.team == marker.team and entity.hp < entity.max_hp:
                    engine.event_queue.enqueue(HealEvent(subject=entity, amount=2))


# ── Abilities ──

class HeavyPulseRifleAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Heavy Pulse Rifle", aiming=TargetEntity(in_range=4),
            instructions=[DamageInstruction(amount=3)], is_default=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                return 1.5
        return 0.0


class SprintAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Sprint", aiming=TargetSelf(),
            instructions=[], is_default=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        # Sprint is useful when we need to reposition
        return 0.3  # Lower than attacking but higher than Do Nothing

    def get_movement(self, engine, actor, reachable_points, enemies, allies):
        """Move up to 3 spaces toward a preferred position."""
        pref = actor.get_preferred_position(engine)
        if not pref or not reachable_points:
            return {}
        proposed_moves = {}
        speed = QuerySpeed(actor).resolve(engine).value
        valid = [pt for pt in reachable_points if pt.get_distance(actor.pos) <= speed and pt != actor.pos]
        if valid:
            # Prefer moving toward preferred position
            best = min(valid, key=lambda p: (p.get_distance(pref), p.get_distance(actor.pos)))
            proposed_moves[best] = f"Sprint toward enemy"
        return proposed_moves


class HelixRocketsAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Helix Rockets",
            aiming=IncludeArea(area=Burst(radius=1, in_range=4)),
            instructions=[DamageInstruction(amount=3), DamageInstruction(amount=1)],
            max_charges=1, defense=2, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        enemies_hit = sum(1 for pt in aiming_result.included_points
            if engine.entity_at(pt) and engine.entity_at(pt).team != actor.team)
        return 1.5 * enemies_hit


class CreateBioticFieldAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Create Biotic Field",
            aiming=TargetSelf(), instructions=[], max_charges=1, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        allies_hurt = [e for e in engine.living_entities if e.team == actor.team and e.hp < e.max_hp]
        return 2.0 if allies_hurt else 0.0

    def execute(self, engine, source, aiming_result):
        self._mark_usage()
        from events import AbilityUseEvent
        engine.event_queue.enqueue(AbilityUseEvent(source=source, ability=self, aiming_result=aiming_result))
        # Create marker at player position
        marker = BioticFieldMarker(engine=engine, pos=source.pos, team=source.team, summoner_id=source.id)
        # Register with manager
        manager = source.get_modifier(BioticFieldManager)
        if manager:
            manager.field_id = marker.id


class BioticFieldMarker(Marker):
    def __init__(self, engine, pos, team, summoner_id):
        super().__init__(engine=engine, name="Biotic Field", pos=pos, team=team, summoner_id=summoner_id)


class TacticalVisorAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Tactical Visor", aiming=TargetSelf(),
            instructions=[AddModifierInstruction(modifier_class=VisorModifier)],
            is_ultimate=True, ultimate_turn=4, action_cost=ActionCost.FREE, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        from scoring import score_ultimate
        # Visor is very valuable once available — it upgrades all default attacks
        return score_ultimate(self, engine) * 3.0


# ── Hero ──

class Soldier76(Hero):
    def __init__(self, engine, pos, team):
        super().__init__(engine=engine, name="Soldier 76", hp=8, speed=3, pos=pos, team=team)
        self.add_modifier(engine, BioticFieldManager())
        self.abilities.append(HeavyPulseRifleAbility(owner_id=self.id))
        self.abilities.append(SprintAbility(owner_id=self.id))
        self.abilities.append(HelixRocketsAbility(owner_id=self.id))
        self.abilities.append(CreateBioticFieldAbility(owner_id=self.id))
        self.abilities.append(TacticalVisorAbility(owner_id=self.id))
