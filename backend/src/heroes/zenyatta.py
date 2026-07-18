"""Zenyatta — slow heal, damage buff, burst damage."""

from abilities import Ability, score_damage
from instruction_library import DamageInstruction, HealInstruction, ApplyModifierInstruction, PushInstruction
from aimings import TargetEntity, TargetSelf, IncludeArea, is_ally_aim_condition
from areas import Burst
from engine import Engine
from entities import Hero, Entity
from modifiers import Modifier
from events import after
from event_library import TurnEndEvent
from valence import Valence
from point import Point


class OrbOfDiscordModifier(Modifier):
    valence = Valence.BAD
    duration: int = 2
    def apply_vulnerable(self) -> int: return 50


class OrbOfHarmonyModifier(Modifier):
    valence = Valence.GOOD
    duration: int = 2

    @after(TurnEndEvent)
    def heal_owner(self, engine, event):
        owner = engine.get_entity_by_id(self.owner_id)
        if owner and owner.hp < owner.max_hp:
            with self.log_trigger(engine=engine, event=event):
                owner.heal(2, engine)


class SnapKickAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Snap Kick", aiming=TargetEntity(in_range=1),
            instructions=[DamageInstruction(amount=2), PushInstruction(distance=2)],
            owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                return 2.5  # Melee push-back
        return 0.0


class OrbOfDestructionAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Orb of Destruction", aiming=TargetEntity(in_range=4),
            instructions=[DamageInstruction(amount=2)],
            is_default=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                return 6.0  # Default attack
        return 0.0


class OrbOfHarmonyAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Orb of Harmony", aiming=TargetEntity(in_range=4, condition=is_ally_aim_condition),
            instructions=[HealInstruction(amount=2)], taps=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        from scoring import score_heal
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target:
                return score_heal(2, target.max_hp - target.hp) * 1.5
        return 0.0


class OrbOfDiscordAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Orb of Discord", aiming=TargetEntity(in_range=4),
            instructions=[ApplyModifierInstruction(modifier_class=OrbOfDiscordModifier)],
            taps=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                has_discord = any(isinstance(m, OrbOfDiscordModifier) for m in target.modifiers)
                if not has_discord:
                    return 2.5  # Valuable debuff — +50% damage for team
        return 0.0


class TranscendenceAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Transcendence", aiming=IncludeArea(area=Burst(radius=1, in_range=0)),
            instructions=[HealInstruction(amount=5)],
            is_ultimate=True, ultimate_turn=3, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        from scoring import score_ultimate
        ult_score = score_ultimate(self, engine)
        if ult_score <= 0:
            return 0.0
        # Check if allies need healing
        included = aiming_result.included_points
        allies_hurt = sum(1 for pt in included
            if engine.entity_at(pt) and engine.entity_at(pt).team == actor.team
            and engine.entity_at(pt).hp < engine.entity_at(pt).max_hp)
        if allies_hurt > 0:
            return ult_score * allies_hurt * 3.0
        return 0.0


class Zenyatta(Hero):
    def __init__(self, engine, pos, team):
        super().__init__(engine=engine, name="Zenyatta", hp=8, speed=3, pos=pos, team=team)
        self.abilities.append(SnapKickAbility(owner_id=self.id))
        self.abilities.append(OrbOfDestructionAbility(owner_id=self.id))
        self.abilities.append(OrbOfHarmonyAbility(owner_id=self.id))
        self.abilities.append(OrbOfDiscordAbility(owner_id=self.id))
        self.abilities.append(TranscendenceAbility(owner_id=self.id))
