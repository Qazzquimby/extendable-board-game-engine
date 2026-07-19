"""Zenyatta

Zenyatta - 8 health, 3 speed
- Slow heal
- Damage buff
- Burst damage
---

Snap Kick
Range 1, 2dmg, push 2
Orb of Destruction
Choose one --
- Range 4, +2def, 2dmg +1 crit
- At the beginning of your next turn: Move 1; Unlimited range, +1def, 6dmg, +2 crit, lose a Standard Action.
Orb of Harmony
Orb of Harmony
1/Turn, Free Action:
Unlimited range, give your Orb of Harmony (max 1, remove oldest).
Now and at the start of your turn, they Heal 2.
Orb of Discord
Orb of Discord
Free Action:
Unlimited range, give your Orb of Discord (max 1, remove oldest).
They receive +50% damage
Transcendence
Transcendence
Ultimate 3, Instant +2:
Heal to full. Clear any number of conditions.
Burst 1, allies Heal 5.
Until the start of your next turn, you are immune to damage conditions you don't want.
"""

from abilities import Ability
from instruction_library import (
    DamageInstruction,
    HealInstruction,
    ApplyModifierInstruction,
    PushInstruction,
)
from aimings import TargetEntity, IncludeArea, TargetSelf, is_ally_aim_condition
from areas import Burst
from entities import Hero
from modifiers import Modifier
from events import after, query
from event_library import TurnEndEvent, TurnStartEvent, ChangeLocationEvent
from queries import QueryDefense
from valence import Valence
from point import Point


class OrbOfDiscordModifier(Modifier):
    """Target takes -2 defense (easier to hit)."""

    valence = Valence.BAD

    @query(QueryDefense)
    def lower_defense(self, engine, q):
        if q.subject_id == self.owner_id:
            q.result.add(-2)


class OrbOfHarmonyModifier(Modifier):
    """Permanent until replaced or source dies. Heals 2 on turn end."""

    valence = Valence.GOOD

    @after(TurnEndEvent)
    def heal_owner(self, engine, event):
        owner = engine.get_entity_by_id(self.owner_id)
        if owner and owner.hp < owner.max_hp:
            with self.log_trigger(engine=engine, event=event):
                owner.heal(2, engine)


class SnapKickAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Snap Kick",
            aiming=TargetEntity(in_range=1),
            instructions=[DamageInstruction(amount=2), PushInstruction(distance=2)],
            owner_id=owner_id,
        )
    # Auto-priority: DamageInstruction.score + PushInstruction.score


class OrbOfDestructionAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Orb of Destruction",
            aiming=TargetEntity(in_range=4),
            instructions=[DamageInstruction(amount=2)],
            is_default=True,
            crit_chance=1,
            defense=2,
            owner_id=owner_id,
        )


class ChargedOrbModifier(Modifier):
    """At the start of the owner's activation, fire 6dmg +1 miss +2 crit, move 1, lose standard action."""

    valence = Valence.BAD

    @after(TurnStartEvent, only_self=False)
    def fire_charged_orb(self, engine, event):
        if event.subject_id != self.owner_id:
            return
        owner = engine.get_entity_by_id(self.owner_id)
        if not owner or not owner.pos:
            return

        enemies = [e for e in engine.living_entities if e.team != owner.team and e.pos]
        if not enemies:
            return

        nearest = min(enemies, key=lambda e: owner.pos.get_distance(e.pos))

        # Push owner 1 toward nearest enemy
        dx = nearest.pos.x - owner.pos.x
        dy = nearest.pos.y - owner.pos.y
        step = Point(
            owner.pos.x + (1 if dx > 0 else -1 if dx < 0 else 0),
            owner.pos.y + (1 if dy > 0 else -1 if dy < 0 else 0),
        )
        if engine.grid.is_in_bounds(step) and not engine.entity_at(step):
            engine.event_queue.enqueue(
                ChangeLocationEvent(subject=owner, new_pos=step)
            )

        # Fire: use DamageEvent — existing resolution handles defense, crit
        from event_library import DamageEvent
        engine.event_queue.enqueue(
            DamageEvent(source=owner, subject=nearest, amount=6)
        )

        # Consume a standard action
        owner.standard_actions = max(0, owner.standard_actions - 1)
        owner.remove_modifier(engine, self)


class ChargeOrbOfDestructionAbility(Ability):
    """Gain a Charged token. At start of next activation, fire 6dmg, move 1, lose standard action."""

    def __init__(self, owner_id):
        super().__init__(
            name="Charge Orb",
            aiming=TargetSelf(),
            instructions=[ApplyModifierInstruction(modifier_class=ChargedOrbModifier)],
            max_charges=1,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        # Priority when there's an enemy to shoot
        enemies = [e for e in engine.living_entities if e.team != actor.team and e.pos]
        if enemies:
            return 3.0  # Setup for big damage next turn
        return 0.0


class OrbOfHarmonyAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Orb of Harmony",
            aiming=TargetEntity(in_range=4, condition=is_ally_aim_condition),
            instructions=[HealInstruction(amount=2)],
            taps=True,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        from scoring import score_heal

        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target:
                return score_heal(2, target.max_hp - target.hp) * 1.5
        return 0.0


class OrbOfDiscordAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Orb of Discord",
            aiming=TargetEntity(in_range=4),
            instructions=[
                ApplyModifierInstruction(modifier_class=OrbOfDiscordModifier)
            ],
            taps=True,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        for pt in aiming_result.target_points:
            target = engine.entity_at(pt)
            if target and target.team != actor.team:
                has_discord = any(
                    isinstance(m, OrbOfDiscordModifier) for m in target.modifiers
                )
                if not has_discord:
                    return 2.5
        return 0.0


class TranscendenceAbility(Ability):
    def __init__(self, owner_id):
        super().__init__(
            name="Transcendence",
            aiming=IncludeArea(area=Burst(radius=1, in_range=0)),
            instructions=[HealInstruction(amount=5)],
            is_ultimate=True,
            ultimate_turn=3,
            owner_id=owner_id,
        )

    def get_priority(self, engine, actor, pos, aiming_result):
        included = aiming_result.included_points
        allies_hurt = sum(
            1
            for pt in included
            if engine.entity_at(pt)
            and engine.entity_at(pt).team == actor.team
            and engine.entity_at(pt).hp < engine.entity_at(pt).max_hp
        )
        if allies_hurt > 0:
            return allies_hurt * 3.0
        return 0.0


class Zenyatta(Hero):
    def __init__(self, engine, pos, team):
        super().__init__(
            engine=engine, name="Zenyatta", hp=8, speed=3, pos=pos, team=team
        )
        self.abilities.append(SnapKickAbility(owner_id=self.id))
        self.abilities.append(OrbOfDestructionAbility(owner_id=self.id))
        self.abilities.append(ChargeOrbOfDestructionAbility(owner_id=self.id))
        self.abilities.append(OrbOfHarmonyAbility(owner_id=self.id))
        self.abilities.append(OrbOfDiscordAbility(owner_id=self.id))
        self.abilities.append(TranscendenceAbility(owner_id=self.id))
