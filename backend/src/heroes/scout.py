"""Scout (TF2) — high mobility, low health, high melee damage."""

from abilities import Ability, score_damage
from instruction_library import DamageInstruction, ApplyModifierInstruction, PushInstruction
from aimings import TargetEntity, TargetSelf
from engine import Engine
from entities import Hero, Entity
from modifiers import Modifier
from events import before
from event_library import DamageEvent
from valence import Valence
from point import Point


class BonkedModifier(Modifier):
    valence = Valence.GOOD
    duration: int = 1

    def apply_immunity(self) -> bool:
        return True

    @before(DamageEvent)
    def block_damage(self, engine, event):
        if event.subject_id == self.owner_id:
            with self.log_trigger(engine=engine, event=event):
                event.canceled = True


class CritAColaDebuff(Modifier):
    valence = Valence.BAD
    duration: int = 1
    def apply_vulnerable(self) -> int: return 50


class CritAColaBuff(Modifier):
    valence = Valence.GOOD
    duration: int = 1
    def apply_damage_buff(self) -> int: return 50


class FanOWarDebuff(Modifier):
    valence = Valence.BAD
    duration: int = 2
    def apply_vulnerable(self) -> int: return 50


class ScattergunAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Scattergun", aiming=TargetEntity(in_range=1),
            instructions=[DamageInstruction(amount=4), PushInstruction(distance=1)],
            is_default=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                return 8.0
        return 0.0


class BonkAtomicPunchAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Bonk Atomic Punch", aiming=TargetSelf(),
            instructions=[ApplyModifierInstruction(modifier_class=BonkedModifier)],
            taps=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        from scoring import score_missing_hp
        if score_missing_hp(actor) >= 1.5:
            return 4.0
        return 0.0


class CritAColaAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Crit-a-Cola", aiming=TargetSelf(),
            instructions=[
                ApplyModifierInstruction(modifier_class=CritAColaBuff),
                ApplyModifierInstruction(modifier_class=CritAColaDebuff),
            ], taps=True, owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        from scoring import score_missing_hp
        if score_missing_hp(actor) < 0.5:
            enemies = [e for e in engine.living_entities if e.team != actor.team and e.pos]
            if enemies:
                dist = min(actor.pos.get_distance(e.pos) for e in enemies)
                if dist <= 2:
                    return 2.0
        return 0.0


class FanOWarAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(name="Fan O'War", aiming=TargetEntity(in_range=1),
            instructions=[ApplyModifierInstruction(modifier_class=FanOWarDebuff)],
            owner_id=owner_id)

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                has_debuff = any(isinstance(m, FanOWarDebuff) for m in target.modifiers)
                if not has_debuff:
                    return 3.0
        return 0.0


class Scout(Hero):
    def __init__(self, engine, pos, team):
        super().__init__(engine=engine, name="Scout", hp=6, speed=5, pos=pos, team=team)
        self.abilities.append(ScattergunAbility(owner_id=self.id))
        self.abilities.append(BonkAtomicPunchAbility(owner_id=self.id))
        self.abilities.append(CritAColaAbility(owner_id=self.id))
        self.abilities.append(FanOWarAbility(owner_id=self.id))
