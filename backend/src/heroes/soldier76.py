"""Soldier 76 — mobile sustained ranged damage and self healing.

Heavy Pulse Rifle: Range 4, 3dmg (default)
Sprint: Move 3 (default)
Helix Rockets: 1/game, Range 4, +2 miss, 3dmg + burst 1 around target 1dmg
Biotic Field: 1/game, 2x2 marker, heals allies at start of creator's activation
Tactical Visor: Ultimate 4, Free Action, unlimited + undefendable defaults
"""

from dataclasses import dataclass

from abilities import Ability, ActionCost
from instruction_library import DamageInstruction, AddModifierInstruction, SummonInstruction
from aimings import TargetEntity, IncludeArea, TargetSelf
from areas import Burst
from engine import Engine
from entities import Hero, Marker
from modifiers import Modifier
from events import after
from event_library import TurnStartEvent, HealEvent
from valence import Valence
from point import Point
from scoring import displacement_value


# ── Modifiers ──

class VisorModifier(Modifier):
    valence = Valence.GOOD
    def apply_undefendable(self) -> bool: return True
    def modify_range(self, base_range: int) -> int: return 999


@dataclass(kw_only=True)
class BioticFieldManager(Modifier):
    field_id: int = None
    valence = Valence.GOOD

    @after(TurnStartEvent, only_self=False)
    def on_summoner_turn(self, engine, event):
        if event.subject_id != self.owner_id or self.field_id is None:
            return
        marker = next((m for m in engine.markers if m.id == self.field_id), None)
        if not marker or marker.pos is None:
            self.field_id = None
            return
        half = 1
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                pt = Point(marker.pos.x + dx, marker.pos.y + dy)
                if not (0 <= pt.x < engine.grid.width and 0 <= pt.y < engine.grid.height):
                    continue
                entity = engine.entity_at(pt)
                if entity and entity.team == marker.team and entity.hp < entity.max_hp:
                    engine.event_queue.enqueue(HealEvent(subject=entity, amount=2))


class SprintBuff(Modifier):
    """Grants +3 speed for the turn. Applied by Sprint ability."""
    valence = Valence.GOOD
    duration: int = 1


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
    """Move 3 spaces (standard action)."""
    def __init__(self, owner_id):
        super().__init__(name="Sprint", aiming=TargetSelf(),
            instructions=[AddModifierInstruction(modifier_class=SprintBuff)],
            is_default=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        pref = actor.get_preferred_position(engine)
        if not pref:
            return 0.0
        return displacement_value(actor, actor.pos, pref, engine) * 0.5

    def get_movement(self, engine, actor, reachable_points, enemies, allies):
        """Propose positions up to speed + 3 away (normal move + sprint move)."""
        pref = actor.get_preferred_position(engine)
        if not pref or not reachable_points:
            return {}
        from queries import QuerySpeed
        speed = QuerySpeed(actor).resolve(engine).value  # 3
        extra = 3  # sprint gives +3
        valid = [p for p in reachable_points
                 if p.get_distance(actor.pos) <= speed + extra and p != actor.pos]
        if not valid:
            return {}
        best = max(valid, key=lambda p: (
            displacement_value(actor, actor.pos, p, engine),
            -p.get_distance(actor.pos),
        ))
        return {best: f"Sprint to range {best.get_distance(pref)} of enemy"}


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


class BioticFieldMarker(Marker):
    def __init__(self, engine, pos, team, summoner_id):
        super().__init__(engine=engine, name="Biotic Field", pos=pos, team=team,
            summoner_id=summoner_id)


class CreateBioticFieldAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Create Biotic Field", aiming=TargetSelf(),
            instructions=[SummonInstruction(entity_factory=BioticFieldMarker, is_marker=True)],
            max_charges=1, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        if not actor.pos:
            return 0.0
        half = 1
        allies_in_field = 0
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                pt = Point(actor.pos.x + dx, actor.pos.y + dy)
                if not (0 <= pt.x < engine.grid.width and 0 <= pt.y < engine.grid.height):
                    continue
                entity = engine.entity_at(pt)
                if entity and entity.team == actor.team and entity.hp < entity.max_hp:
                    allies_in_field += 1
        return allies_in_field * 2.0


class TacticalVisorAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Tactical Visor", aiming=TargetSelf(),
            instructions=[AddModifierInstruction(modifier_class=VisorModifier)],
            is_ultimate=True, ultimate_turn=4, action_cost=ActionCost.FREE,
            owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        enemies = [e for e in engine.living_entities if e.team != actor.team and e.pos]
        if not enemies:
            return 0.0
        valuable_targets = 0
        for e in enemies:
            d = actor.pos.get_distance(e.pos)
            valuable_targets += 2 if d > 4 else 1
        return valuable_targets * 1.0


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
