"""
Soldier 76 — mobile sustained ranged damage and self healing.

Heavy Pulse Rifle: Range 4, 3dmg (default)
Sprint: Move 3 (default — handled by speed system)
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
from entities import Hero, Object
from modifiers import Modifier
from events import after
from event_library import TurnStartEvent, HealEvent, SummonEvent
from valence import Valence
from point import Point


# ── Modifiers ──

class VisorModifier(Modifier):
    """Default abilities have unlimited range and are undefendable."""
    valence = Valence.GOOD
    def apply_undefendable(self) -> bool: return True
    def modify_range(self, base_range: int) -> int: return 999


@dataclass(kw_only=True)
class BioticFieldManager(Modifier):
    """Listens for TurnStart on the hero and heals allies in Biotic Field objects."""
    field_id: int = None
    valence = Valence.GOOD

    @after(TurnStartEvent, only_self=False)
    def on_summoner_turn(self, engine, event):
        if event.subject_id != self.owner_id:
            return
        if self.field_id is None:
            return
        field = engine.get_entity_by_id(self.field_id)
        if not field or field.hp <= 0:
            self.field_id = None
            return
        # Heal allies in 2x2 area around field
        half = 1
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                pt = Point(field.pos.x + dx, field.pos.y + dy)
                if not (0 <= pt.x < engine.grid.width and 0 <= pt.y < engine.grid.height):
                    continue
                entity = engine.entity_at(pt)
                if entity and entity.team == field.team and entity.hp < entity.max_hp:
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
        # Create BioticField object and register it with the manager
        field = BioticFieldObject(engine=engine, pos=source.pos, team=source.team, summoner=source)
        engine.event_queue.enqueue(SummonEvent(summoner=source, subject=field))
        manager = source.get_modifier(BioticFieldManager)
        if manager:
            manager.field_id = field.id


class BioticFieldObject(Object):
    def __init__(self, engine, pos, team, summoner):
        super().__init__(engine=engine, name="Biotic Field", hp=999,
            pos=pos, team=team, summoner=summoner)
        self.activator = None  # Don't activate in turn queue


class TacticalVisorAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Tactical Visor", aiming=TargetSelf(),
            instructions=[AddModifierInstruction(modifier_class=VisorModifier)],
            is_ultimate=True, ultimate_turn=4, action_cost=ActionCost.FREE, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        from scoring import score_ultimate
        return score_ultimate(self, engine)


# ── Hero ──

class Soldier76(Hero):
    def __init__(self, engine, pos, team):
        super().__init__(engine=engine, name="Soldier 76", hp=8, speed=3, pos=pos, team=team)
        self.add_modifier(engine, BioticFieldManager())
        self.abilities.append(HeavyPulseRifleAbility(owner_id=self.id))
        self.abilities.append(HelixRocketsAbility(owner_id=self.id))
        self.abilities.append(CreateBioticFieldAbility(owner_id=self.id))
        self.abilities.append(TacticalVisorAbility(owner_id=self.id))
