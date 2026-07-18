from dataclasses import dataclass, field
from typing import Type, Optional

from abilities import Instruction, DynamicInt, ActionContext, resolve_int, DynamicPoint
from abilities import score_damage, score_heal, score_add_token
from engine import Engine
from event_library import (
    DamageEvent,
    HealEvent,
    AddModifierEvent,
    RemoveModifierEvent,
    AddTokenEvent,
    RemoveTokenEvent,
    PullEvent,
    ChangeLocationEvent,
)
from modifiers import Modifier, Token
from point import Point
from util import UniqueTuple
from valence import Valence


@dataclass(kw_only=True)
class DamageInstruction(Instruction):
    amount: DynamicInt
    undefendable: bool = False
    irreducible: bool = False
    valence: Valence = Valence.BAD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            if ctx.is_crit:
                amount *= 2  # todo should be +1x damage multiplier. Use modvalue
            # todo crit handling will likely need to be more extensible later

            engine.event_queue.enqueue(
                DamageEvent(
                    source=engine.get_entity_by_id(ctx.source_id),
                    subject=subject,
                    amount=amount,
                    ability=ctx.ability,
                )
            )

    def score(self, engine, actor, target, ctx) -> float:
        if target.team == actor.team:
            return 0.0
        dmg = resolve_int(self.amount, ctx) if callable(self.amount) else self.amount
        return score_damage(dmg, target.hp) if isinstance(dmg, int) else 1.0


@dataclass(kw_only=True)
class HealInstruction(Instruction):
    amount: DynamicInt
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            engine.event_queue.enqueue(HealEvent(subject=subject, amount=amount))

    def score(self, engine, actor, target, ctx) -> float:
        if target.team != actor.team:
            return 0.0
        amt = resolve_int(self.amount, ctx) if callable(self.amount) else self.amount
        if isinstance(amt, int):
            return score_heal(amt, target.max_hp - target.hp)
        return 1.0


@dataclass(kw_only=True)
class AddModifierInstruction(Instruction):
    modifier_class: Type["Modifier"]
    modifier_kwargs: dict = field(default_factory=dict)
    valence: Valence = Valence.MIXED

    def __post_init__(self):
        self.valence = self.modifier_class.valence

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            engine.event_queue.enqueue(
                AddModifierEvent(
                    subject=subject,
                    modifier_class=self.modifier_class,
                    modifier_kwargs=self.modifier_kwargs,
                )
            )

    def score(self, engine, actor, target, ctx) -> float:
        return score_add_token(self.modifier_class)


@dataclass(kw_only=True)
class RemoveModifierInstruction(Instruction):
    modifier_class: Type["Modifier"]
    amount: DynamicInt = 1
    valence: Valence = Valence.MIXED

    def __post_init__(self):
        if self.modifier_class.valence == Valence.GOOD:
            self.valence = Valence.BAD
        elif self.modifier_class.valence == Valence.BAD:
            self.valence = Valence.GOOD
        else:
            self.valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            engine.event_queue.enqueue(
                RemoveModifierEvent(
                    subject=ctx.get_target(engine), modifier_class=self.modifier_class
                )
            )


@dataclass(kw_only=True)
class AddTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1
    token_kwargs: dict = field(default_factory=dict)
    valence: Valence = Valence.MIXED

    def __post_init__(self):
        self.valence = self.token_class.valence

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            engine.event_queue.enqueue(
                AddTokenEvent(
                    subject=subject,
                    token_class=self.token_class,
                    amount=amount,
                    token_kwargs=self.token_kwargs,
                )
            )

    def score(self, engine, actor, target, ctx) -> float:
        value = score_add_token(self.token_class) * resolve_int(self.amount, ctx)
        on_ally = target.team == actor.team
        if (on_ally and self.token_class.valence == Valence.BAD) or (
            not on_ally and self.token_class.valence == Valence.GOOD
        ):
            value = -value
        return value


@dataclass(kw_only=True)
class RemoveTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1
    valence: Valence = Valence.MIXED

    def __post_init__(self):
        if self.token_class.valence == Valence.GOOD:
            self.valence = Valence.BAD
        elif self.token_class.valence == Valence.BAD:
            self.valence = Valence.GOOD
        else:
            self.valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            engine.event_queue.enqueue(
                RemoveTokenEvent(
                    subject=ctx.get_target(engine),
                    token_class=self.token_class,
                    amount=self.amount,
                )
            )

    def score(self, engine, actor, target, ctx) -> float:
        # todo can add a value property on tokens rather than flat 2
        # Removing a bad token from ally = good, removing good token from enemy = good
        if self.token_class.valence == Valence.BAD and target.team == actor.team:
            return 2.0
        if self.token_class.valence == Valence.GOOD and target.team != actor.team:
            return 2.0
        return 0.0


@dataclass(kw_only=True)
class PullInstruction(Instruction):
    distance: DynamicInt
    valence: Valence = Valence.MIXED

    # todo probably want direction param and update resolution
    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            dist = resolve_int(self.distance, ctx)
            source = engine.get_entity_by_id(ctx.source_id)
            engine.event_queue.enqueue(
                PullEvent(
                    subject=ctx.get_target(engine),
                    distance=dist,
                    toward_point=source.pos,
                )
            )


@dataclass(kw_only=True)
class UseAnAbilityInstruction(Instruction):
    default_only: bool = False
    required_target: Optional["Point"] = None
    subject_chooses: bool = True
    valence: Valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        from choices import Choice

        subject = engine.entity_at(ctx.subject_point)
        if not subject or not hasattr(subject, "abilities"):
            return

        valid_abilities = subject.abilities
        if self.default_only:
            valid_abilities = [
                ability for ability in valid_abilities if ability.is_default
            ]

        source = engine.get_entity_by_id(ctx.source_id)
        choices = UniqueTuple(
            [
                Choice(
                    features={f"{source.name}_forced_use_ability_is_{ability.name}": 1}
                )
                for ability in valid_abilities
            ]
        )
        if not choices:
            return  # No valid abilities to choose from
        if self.subject_chooses:
            choosing_team = subject.team
        else:
            source = engine.get_entity_by_id(ctx.source_id)
            choosing_team = source.team
        chosen_ability_index = engine.get_choice_index(
            team=choosing_team, choices=choices
        )
        chosen_ability = valid_abilities[chosen_ability_index]
        possible_aimings = chosen_ability.aiming.get_all_aimings(
            engine=engine, actor=subject, require_los=True
        )
        if possible_aimings:
            aiming = possible_aimings[0]

            chosen_ability.execute(
                engine=engine,
                source=subject,
                aiming_result=aiming,
            )


@dataclass(kw_only=True)
class RefreshAbilityInstruction(Instruction):
    valence: Valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            if ctx.ability:
                ctx.ability.is_tapped = False
                ctx.ability.tapped_this_turn = False
                ctx.ability.charges = ctx.ability.max_charges  # todo should be event

    def score(self, engine, actor, target, ctx) -> float:
        return 2.0  # refreshing an ability has fixed value


@dataclass(kw_only=True)
class TeleportInstruction(Instruction):
    destination: DynamicPoint
    teleport_source: bool = False
    """If True, teleport the source entity instead of entity_at subject_point.
    Used for abilities like Blink that target an empty destination point."""
    valence: Valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        if self.teleport_source:
            subject = engine.get_entity_by_id(ctx.source_id)
        else:
            subject = engine.entity_at(ctx.subject_point)
        if subject:
            dest = (
                self.destination(ctx)
                if callable(self.destination)
                else self.destination
            )
            engine.event_queue.enqueue(
                ChangeLocationEvent(subject=subject, new_pos=dest)
            )


@dataclass(kw_only=True)
class ApplyModifierInstruction(Instruction):
    modifier_class: Type[Modifier]
    valence: Valence = Valence.MIXED

    def __post_init__(self):
        self.valence = self.modifier_class.valence

    def score(self, engine, actor, target, ctx) -> float:
        return score_add_token(self.modifier_class)


# @dataclass
# class PushInstruction(Instruction):
#     distance: DynamicInt
#
# add valence

#     # todo probably want direction param and update resolution
#     def execute(self, ctx: ActionContext) -> None:
#         subject = engine.entity_at(ctx.subject_point)
#         if subject:
#             dist = resolve_int(self.distance, ctx)
#             PushEvent(
#                 engine=engine,
#                 subject=ctx.target,
#                 distance=dist,
#                 source=ctx.source_id,
#             ).resolve()
