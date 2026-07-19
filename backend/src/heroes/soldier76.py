"""Soldier 76 — mobile sustained ranged damage and self healing.

Heavy Pulse Rifle: Range 4, 3dmg (default)
Sprint: Move 3 (default)
Helix Rockets: 1/game, Range 4, +2 miss, 3dmg + burst 1 around target 1dmg
Biotic Field: 1/game, 2x2 marker, heals allies at start of creator's activation
Tactical Visor: Ultimate 4, Free Action, unlimited + undefendable defaults
"""

from dataclasses import dataclass

from abilities import Ability, ActionCost
from instruction_library import (
    DamageInstruction,
    AddModifierInstruction,
    SummonInstruction,
)
from aimings import TargetEntity, IncludeArea, TargetSelf
from areas import Burst
from engine import Engine
from entities import Hero, Marker
from modifiers import Modifier, ClearAtEndOfTurnMixin
from events import after, query
from event_library import TurnStartEvent, HealEvent, TurnEndEvent
from queries import QuerySpeed, QueryIsUndefendable
from valence import Valence
from point import Point
from scoring import displacement_value

# ── Modifiers ──


class VisorModifier(Modifier):
    """Default abilities from the owner are undefendable."""
    valence = Valence.GOOD

    @query(QueryIsUndefendable)
    def make_undefendable(self, engine, q):
        if (q.ability and q.ability.is_default
                and q.attack_source and q.attack_source.id == self.owner_id):
            q.result = True


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
                if not (
                    0 <= pt.x < engine.grid.width and 0 <= pt.y < engine.grid.height
                ):
                    continue
                entity = engine.entity_at(pt)
                if entity and entity.team == marker.team and entity.hp < entity.max_hp:
                    engine.event_queue.enqueue(HealEvent(subject=entity, amount=2))


class SprintBuff(Modifier, ClearAtEndOfTurnMixin):
    """Grants +3 speed until end of turn."""

    valence = Valence.GOOD

    @query(QuerySpeed)
    def add_speed(self, engine, q):
        q.result.add(3)


# ── Abilities ──


class HeavyPulseRifleAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Heavy Pulse Rifle",
            aiming=TargetEntity(in_range=4),
            instructions=[DamageInstruction(amount=3)],
            is_default=True,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                return 1.5
        return 0.0


class SprintAbility(Ability):
    """Move 3 spaces (standard action)."""

    def __init__(self, owner_id):
        super().__init__(
            name="Sprint",
            aiming=TargetSelf(),
            instructions=[AddModifierInstruction(modifier_class=SprintBuff)],
            is_default=True,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        pref = actor.get_preferred_position(engine)
        if not pref or not actor.pos:
            return 0.0
        # Sprint is useful if hero needs to get closer to enemies
        current_dist = actor.pos.get_distance(pref)
        if current_dist <= 2:
            return 0.0  # Close enough — don't waste the action
        return 1.0  # Always useful for repositioning

    def get_movement(self, engine, actor, reachable_points, enemies, allies):
        """Propose positions ONLY beyond normal reach (speed + 3).

        Skips positions already reachable by normal speed so standard
        abilities can't piggyback on Sprint's extra movement.
        """
        pref = actor.get_preferred_position(engine)
        if not pref:
            return {}
        speed = QuerySpeed(actor).resolve(engine).value
        extra = 3
        sprint_reachable = engine.grid.get_movable_spaces(
            engine=engine, actor=actor, max_movement=speed + extra
        )
        # Only keep positions that normal speed can't reach
        sprint_reachable = {p for p in sprint_reachable if p not in reachable_points}
        occupied = {
            e.pos for e in engine.living_entities if e != actor and e.pos is not None
        }
        valid = [p for p in sprint_reachable if p not in occupied and p != actor.pos]
        if not valid:
            return {}
        best = max(
            valid,
            key=lambda p: (
                displacement_value(actor, actor.pos, p, engine),
                -p.get_distance(actor.pos),
            ),
        )
        return {best: f"Sprint to range {best.get_distance(pref)} of enemy"}
        if not valid:
            return {}
        best = max(
            valid,
            key=lambda p: (
                displacement_value(actor, actor.pos, p, engine),
                -p.get_distance(actor.pos),
            ),
        )
        return {best: f"Sprint to range {best.get_distance(pref)} of enemy"}


class HelixRocketsAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Helix Rockets",
            aiming=IncludeArea(area=Burst(radius=1, in_range=4)),
            instructions=[DamageInstruction(amount=3), DamageInstruction(amount=1)],
            max_charges=1,
            defense=2,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        enemies_hit = sum(
            1
            for pt in aiming_result.included_points
            if engine.entity_at(pt) and engine.entity_at(pt).team != actor.team
        )
        return 1.5 * enemies_hit


class BioticFieldMarker(Marker):
    def __init__(self, engine, pos, team, summoner_id):
        super().__init__(
            engine=engine,
            name="Biotic Field",
            pos=pos,
            team=team,
            summoner_id=summoner_id,
        )


class CreateBioticFieldAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Create Biotic Field",
            aiming=TargetSelf(),
            instructions=[
                SummonInstruction(entity_factory=BioticFieldMarker, is_marker=True)
            ],
            max_charges=1,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        if not actor.pos:
            return 0.0
        half = 1
        allies_in_field = 0
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                pt = Point(actor.pos.x + dx, actor.pos.y + dy)
                if not (
                    0 <= pt.x < engine.grid.width and 0 <= pt.y < engine.grid.height
                ):
                    continue
                entity = engine.entity_at(pt)
                if entity and entity.team == actor.team and entity.hp < entity.max_hp:
                    allies_in_field += 1
        return allies_in_field * 2.0


class TacticalVisorAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Tactical Visor",
            aiming=TargetSelf(),
            instructions=[AddModifierInstruction(modifier_class=VisorModifier)],
            is_ultimate=True,
            ultimate_turn=4,
            action_cost=ActionCost.FREE,
            owner_id=owner_id,
        )

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
        super().__init__(
            engine=engine, name="Soldier 76", hp=8, speed=3, pos=pos, team=team
        )
        self.add_modifier(engine, BioticFieldManager())
        self.abilities.append(HeavyPulseRifleAbility(owner_id=self.id))
        self.abilities.append(SprintAbility(owner_id=self.id))
        self.abilities.append(HelixRocketsAbility(owner_id=self.id))
        self.abilities.append(CreateBioticFieldAbility(owner_id=self.id))
        self.abilities.append(TacticalVisorAbility(owner_id=self.id))
