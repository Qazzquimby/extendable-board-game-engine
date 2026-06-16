from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TYPE_CHECKING, Union, Type, Tuple, Set, Callable

from aimings import Aiming, AimingResult, MultipleAimingResults
from events import PullEvent, DamageEvent, HealEvent, AddTokenEvent, ChangeLocationEvent
from ai.feature_definitions import (
    DAMAGE_DEALT,
    FORCED_USE_ABILITY,
    HEAL_DEALT,
    KILLS,
    NEW_LOCATION,
    Feature,
)
from valence import Valence
from modifiers import Modifier, Token

if TYPE_CHECKING:
    from engine import (
        Engine,
        Entity,
    )

    from point import Point


class ActionCost(Enum):
    FREE = "free"
    STANDARD = "standard"
    MOVE = "move"
    MOVE_AND_STANDARD = "move_and_standard"
    MOVE_OR_STANDARD = "move_or_standard"


@dataclass
class ActionContext:
    engine: "Engine"
    source: "Entity"
    subject_point: "Point"  # The point currently being affected

    # all points with targets
    target_points: List["Point"] = field(default_factory=list)

    # all points included in areas
    included_points: List["Point"] = field(default_factory=list)
    ability: Optional["Ability"] = None
    is_hit: bool = True
    is_crit: bool = False

    _target: "Entity" = None

    @property
    def target_point(self):
        if len(self.target_points) != 1:
            raise ValueError("Cannot use `.target` when there are multiple targets.")
        return self.target_points[0]

    @property
    def target(self):
        if self._target is None:
            self._target = self.engine.entity_at(self.target_point)
        return self._target


DynamicInt = Union[int, Callable[[ActionContext], int]]
DynamicPoint = Union["Point", Callable[[ActionContext], "Point"]]


def resolve_int(val: DynamicInt, ctx: ActionContext) -> int:
    return val(ctx) if callable(val) else val


@dataclass(kw_only=True)
class Instruction:
    """Base class for all ability effects."""

    aiming_name: Optional[str] = None
    valence: Valence = field(init=False, default=False)

    def execute(self, ctx: ActionContext) -> None:
        pass

    def get_features(self, ctx: "ActionContext") -> dict:
        return {}

    def get_feature_templates(self) -> List["Feature"]:
        return []


@dataclass
class Ability:
    name: str
    aiming: Aiming
    text: str = ""
    instructions: List[Instruction] = field(default_factory=list)
    owner: Optional["Entity"] = None
    is_default: bool = False
    action_cost: ActionCost = ActionCost.STANDARD

    modifiers: List["Modifier"] = field(default_factory=list)

    taps: bool = False
    is_tapped: bool = False
    tapped_this_turn: bool = False
    max_charges: Optional[int] = None
    is_ultimate: bool = False
    ultimate_turn: Optional[int] = None

    is_undefendable: bool = False
    defense: int = 0
    crit_chance: int = 0

    def __post_init__(self):
        self.charges = self.max_charges

    def is_available(self):
        if self.is_tapped:
            return False
        if self.charges is not None and self.charges <= 0:
            return False

        return True

    def execute(
        self,
        engine: "Engine",
        source: "Entity",
        aiming_result: Union[AimingResult, MultipleAimingResults],
    ) -> None:  # todo, execute is not used yet
        if self.charges is not None:
            self.charges -= 1
        if self.taps:
            self.is_tapped = True
            self.tapped_this_turn = True

        hit_target_points, crit_target_points = self._get_hit_and_crit_target_points(
            aiming_result=aiming_result, engine=engine, source=source
        )

        for instruction in self.instructions:
            if instruction.aiming_name:
                instruction_aiming_result = aiming_result.sub_aimings[
                    instruction.aiming_name
                ]
            else:
                instruction_aiming_result = aiming_result

            for target_point in instruction_aiming_result.target_points:
                is_hit = target_point in hit_target_points
                is_crit = target_point in crit_target_points

                ctx = ActionContext(
                    engine=engine,
                    source=source,
                    subject_point=target_point,
                    target_points=instruction_aiming_result.target_points,
                    included_points=instruction_aiming_result.included_points,
                    ability=self,
                    is_hit=is_hit,
                    is_crit=is_crit,
                )
                instruction.execute(ctx)

            for included_point in instruction_aiming_result.included_points:
                ctx = ActionContext(
                    engine=engine,
                    source=source,
                    subject_point=included_point,
                    target_points=instruction_aiming_result.target_points,
                    included_points=instruction_aiming_result.included_points,
                    ability=self,
                )
                instruction.execute(ctx)

    def get_hash(self) -> float:
        import hashlib

        owner_set = getattr(self.owner, "set", "unknown") if self.owner else "unknown"
        owner_name = getattr(self.owner, "name", "unknown") if self.owner else "unknown"
        key = f"{owner_set}__{owner_name}__{self.name}"
        hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
        return float(hash_int % 10000) / 100.0

    def _get_hit_and_crit_target_points(
        self,
        aiming_result: Union[AimingResult, MultipleAimingResults],
        engine: "Engine",
        source: "Entity",
    ) -> Tuple[Set["Point"], Set["Point"]]:
        if isinstance(aiming_result, dict):
            all_target_points = set()
            for aiming_result_set in aiming_result.values():
                all_target_points.update(aiming_result_set.target_points)
        else:
            all_target_points = aiming_result.target_points
        hit_target_points = set()
        crit_target_points = set()
        for target_point in all_target_points:
            target = engine.entity_at(target_point)
            if target:
                defense = target.get_defense(attack_source=source, ability=self)
                defense = min(4, defense)
                crit_chance = source.get_crit(subject=target, ability=self)

                if defense > 0 or crit_chance > 0:
                    roll = engine.rng.randint(1, 6)  # todo rolling should be an event
                    if roll > defense:
                        hit_target_points.add(target_point)
                    if roll >= 7 - crit_chance:
                        crit_target_points.add(target_point)
                else:
                    # No roll means auto hits
                    hit_target_points.add(target_point)

        return hit_target_points, crit_target_points


@dataclass
class DamageInstruction(Instruction):
    amount: DynamicInt
    undefendable: bool = False
    irreducible: bool = False
    valence = Valence.BAD

    def get_features(self, ctx: ActionContext) -> dict:
        features = {}
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject and ctx.is_hit:
            amount = resolve_int(self.amount, ctx)
            features[DAMAGE_DEALT(name=subject.name)] = amount
            if subject.hp > 0 and subject.hp - amount <= 0:
                features[KILLS(name=subject.name)] = True
        return features

    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            if ctx.is_crit:
                amount *= 2  # todo should be +1x damage multiplier. Use modvalue
            # todo crit handling will likely need to be more extensible later

            DamageEvent(
                source=ctx.source,
                subject=subject,
                amount=amount,
                ability=ctx.ability,
            ).resolve()

    def get_feature_templates(self) -> List["Feature"]:
        return [DAMAGE_DEALT, KILLS]


@dataclass
class HealInstruction(Instruction):
    amount: DynamicInt
    valence = Valence.GOOD

    def get_features(self, ctx: ActionContext) -> dict:
        features = {}
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            key = HEAL_DEALT(name=subject.name)
            features[key] = amount
        return features

    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            HealEvent(subject=subject, amount=amount).resolve()

    def get_feature_templates(self) -> List["Feature"]:
        return [HEAL_DEALT]


@dataclass
class GiveTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1

    def __post_init__(self):
        self.valence = self.token_class.valence

    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            AddTokenEvent(
                subject=subject,
                token_class=self.token_class,
                amount=amount,
            ).resolve()


@dataclass
class RemoveTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1

    def __post_init__(self):
        if self.token_class.valence == Valence.GOOD:
            self.valence = Valence.BAD
        elif self.token_class.valence == Valence.BAD:
            self.valence = Valence.GOOD
        else:
            self.valence = Valence.MIXED

    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            ctx.target.remove_token(self.token_class, amount=amount)


# @dataclass
# class PushInstruction(Instruction):
#     distance: DynamicInt
#
# def __post_init__(self):
#     self.plausibly_positive = True
#     self.plausibly_negative = True

#     # todo probably want direction param and update resolution
#     def execute(self, ctx: ActionContext) -> None:
#         subject = ctx.engine.entity_at(ctx.subject_point)
#         if subject:
#             dist = resolve_int(self.distance, ctx)
#             PushEvent(
#                 engine=ctx.engine,
#                 subject=ctx.target,
#                 distance=dist,
#                 source=ctx.source,
#             ).resolve()


@dataclass
class PullInstruction(Instruction):
    distance: DynamicInt
    valence = Valence.MIXED

    # todo probably want direction param and update resolution
    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            dist = resolve_int(self.distance, ctx)
            PullEvent(
                subject=ctx.target, distance=dist, toward_point=ctx.source.pos
            ).resolve()


@dataclass
class UseAnAbilityInstruction(Instruction):
    default_only: bool = False
    required_target: Optional["Point"] = None
    subject_chooses: bool = True
    valence = Valence.MIXED

    def get_feature_templates(self) -> List["Feature"]:
        return [FORCED_USE_ABILITY]

    def execute(self, ctx: ActionContext) -> None:
        from choices import Choice

        subject = ctx.engine.entity_at(ctx.subject_point)
        if not subject or not hasattr(subject, "abilities"):
            return

        valid_abilities = subject.abilities
        if self.default_only:
            valid_abilities = [
                ability for ability in valid_abilities if ability.is_default
            ]

        choices = [
            Choice(
                features={f"{ctx.source.name}_forced_use_ability_is_{ability.name}": 1}
            )
            for ability in valid_abilities
        ]
        if self.subject_chooses:
            choosing_team = subject.team
        else:
            choosing_team = ctx.source.team
        chosen_ability_index = ctx.engine.get_choice_index(
            team=choosing_team, choices=choices
        )
        chosen_ability = valid_abilities[chosen_ability_index]
        possible_aimings = chosen_ability.aiming.get_all_aimings(
            engine=ctx.engine, actor=subject, require_los=True
        )
        aiming = possible_aimings[0]

        chosen_ability.execute(
            engine=ctx.engine,
            source=subject,
            aiming_result=aiming,
        )


@dataclass
class RefreshAbilityInstruction(Instruction):
    valence = Valence.GOOD

    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            if ctx.ability:
                ctx.ability.is_tapped = False
                ctx.ability.tapped_this_turn = False
                ctx.ability.charges = ctx.ability.max_charges  # todo should be event


@dataclass
class TeleportInstruction(Instruction):
    destination: DynamicPoint
    valence = Valence.MIXED

    def get_features(self, ctx: ActionContext) -> dict:
        features = {}
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            dest = (
                self.destination(ctx)
                if callable(self.destination)
                else self.destination
            )
            features[NEW_LOCATION(name=subject.name)] = dest
        return features

    def execute(self, ctx: ActionContext) -> None:
        subject = ctx.engine.entity_at(ctx.subject_point)
        if subject:
            dest = (
                self.destination(ctx)
                if callable(self.destination)
                else self.destination
            )
            ChangeLocationEvent(subject=subject, new_pos=dest).resolve()

    def get_feature_templates(self) -> List["Feature"]:
        return [NEW_LOCATION]


@dataclass(kw_only=True)
class ApplyModifierInstruction(Instruction):
    modifier_class: Type[Modifier]

    def __post__init__(self):
        self.valence = self.modifier_class.valence
