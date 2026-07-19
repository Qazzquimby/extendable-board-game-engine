"""Scout (TF2) — high mobility, low health, high melee damage."""

from abilities import Ability
from instruction_library import (
    DamageInstruction,
    ApplyModifierInstruction,
    PushInstruction,
)
from aimings import TargetEntity, TargetSelf
from engine import Engine
from entities import Hero, Entity
from modifiers import Modifier, ClearAtStartOfTurnMixin, ClearAfterTurnsMixin
from events import before, query
from event_library import DamageEvent
from queries import QueryDefense, QueryVulnerable, QueryDamageBuff
from valence import Valence
from point import Point


class BonkedModifier(Modifier, ClearAtStartOfTurnMixin):
    valence = Valence.GOOD

    @before(DamageEvent)
    def block_damage(self, engine, event):
        if event.subject_id == self.owner_id:
            with self.log_trigger(engine=engine, event=event):
                event.canceled = True


class CritAColaDebuff(Modifier, ClearAtStartOfTurnMixin):
    """Scout takes +50% damage while active."""
    valence = Valence.BAD

    @query(QueryVulnerable)
    def extra_damage_taken(self, engine, q):
        if q.subject_id == self.owner_id:
            q.result.add(50)


class CritAColaBuff(Modifier, ClearAtStartOfTurnMixin):
    """Scout deals +50% damage while active."""
    valence = Valence.GOOD

    @query(QueryDamageBuff)
    def extra_damage_dealt(self, engine, q):
        if q.subject_id == self.owner_id:
            q.result.add(50)


class FanOWarDebuff(Modifier, ClearAfterTurnsMixin, ClearAtStartOfTurnMixin):
    """Target takes +50% damage for 2 turns."""
    valence = Valence.BAD

    def __init__(self):
        self.turns_remaining = 2

    @query(QueryVulnerable)
    def extra_damage_taken(self, engine, q):
        if q.subject_id == self.owner_id:
            q.result.add(50)


class ScattergunAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Scattergun",
            aiming=TargetEntity(in_range=1),
            instructions=[DamageInstruction(amount=4), PushInstruction(distance=1)],
            is_default=True,
            owner_id=owner_id,
        )
    # Auto-priority from DamageInstruction.score + PushInstruction.score handles scoring


class BonkAtomicPunchAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Bonk Atomic Punch",
            aiming=TargetSelf(),
            instructions=[ApplyModifierInstruction(modifier_class=BonkedModifier)],
            taps=True,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        """Prefer when 3+ enemies in range 3, or very low HP with enemies nearby."""
        if not actor.pos:
            return 0.0
        missing_hp = actor.max_hp - actor.hp
        enemies_nearby = [
            e for e in engine.living_entities
            if e.team != actor.team and e.pos
            and actor.pos.get_distance(e.pos) <= 3
        ]
        nearby_count = len(enemies_nearby)

        # 3+ in range 3 → high priority
        if nearby_count >= 3:
            return nearby_count * 2.0
        # 1-2 in range 3 + low HP → moderate priority
        if nearby_count > 0 and missing_hp >= 2.0:
            return 3.0 + missing_hp
        return 0.0


class CritAColaAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Crit-a-Cola",
            aiming=TargetSelf(),
            instructions=[
                ApplyModifierInstruction(modifier_class=CritAColaBuff),
                ApplyModifierInstruction(modifier_class=CritAColaDebuff),
            ],
            taps=True,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        """Prefer when 5+ spaces from nearest enemy, scale with total enemy HP."""
        if not actor.pos:
            return 0.0
        enemies = [
            e for e in engine.living_entities if e.team != actor.team and e.pos
        ]
        if not enemies:
            return 0.0
        nearest_dist = min(actor.pos.get_distance(e.pos) for e in enemies)
        total_enemy_hp = sum(e.hp for e in enemies)

        # Prefer when far from enemies (safe to debuff self)
        if nearest_dist >= 5:
            return 1.5 + total_enemy_hp * 0.1
        return 0.0


class FanOWarAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Fan O'War",
            aiming=TargetEntity(in_range=1),
            instructions=[ApplyModifierInstruction(modifier_class=FanOWarDebuff)],
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        """Prioritize targets that don't already have the debuff."""
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                has_debuff = any(
                    isinstance(m, FanOWarDebuff) for m in target.modifiers
                )
                if not has_debuff:
                    return 2.0  # Auto priority handles scoring via score_add_token
        return 0.0


class Scout(Hero):
    def __init__(self, engine, pos, team):
        super().__init__(engine=engine, name="Scout", hp=6, speed=5, pos=pos, team=team)
        self.abilities.append(ScattergunAbility(owner_id=self.id))
        self.abilities.append(BonkAtomicPunchAbility(owner_id=self.id))
        self.abilities.append(CritAColaAbility(owner_id=self.id))
        self.abilities.append(FanOWarAbility(owner_id=self.id))
