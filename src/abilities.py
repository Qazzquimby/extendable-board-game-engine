from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, TYPE_CHECKING, Union, Callable, Type, Tuple, Set

from aimings import Aiming, AimingResult, MultipleAimingResults

if TYPE_CHECKING:
    from engine import (
        Engine,
        Entity,
        Token,
        DamageEvent,
        HealEvent,
        PushEvent,
        PullEvent,
        Modifier,
    )
    from point import Point


@dataclass
class ActionContext:
    engine: "Engine"
    source: "Entity"
    receiver_point: "Point"  # The point currently being affected

    # all points with targets
    target_points: List["Point"] = field(default_factory=list)

    # all points included in areas
    included_points: List["Point"] = field(default_factory=list)
    ability: Optional["Ability"] = None
    is_hit: bool = True
    is_crit: bool = False

    @property
    def target_point(self):
        if len(self.target_points) != 1:
            raise ValueError("Cannot use `.target` when there are multiple targets.")
        return self.target_points[0]

    @property
    def target(self):
        return self.engine.entity_at(self.target_point)


DynamicInt = Union[int, Callable[[ActionContext], int]]
DynamicPoint = Union["Point", Callable[[ActionContext], "Point"]]


def resolve_int(val: DynamicInt, ctx: ActionContext) -> int:
    return val(ctx) if callable(val) else val


@dataclass(kw_only=True)
class Instruction:
    """Base class for all ability effects."""

    aiming_name: Optional[str] = field(default=None)

    def execute(self, ctx: ActionContext) -> None:
        pass


@dataclass
class DamageInstruction(Instruction):
    amount: DynamicInt
    undefendable: bool = False
    irreducible: bool = False

    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            amount = resolve_int(self.amount, ctx)
            if ctx.is_crit:
                amount *= 2  # todo should be +1x damage multiplier. Use modvalue
            # todo crit handling will likely need to be more extensible later

            DamageEvent(
                engine=ctx.engine,
                source=ctx.source,
                receiver=receiver,
                amount=amount,
                ability=ctx.ability,
            ).resolve()


@dataclass
class HealInstruction(Instruction):
    amount: DynamicInt

    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            amount = resolve_int(self.amount, ctx)
            HealEvent(engine=ctx.engine, receiver=ctx.rec, amount=amount).resolve()


@dataclass
class GiveTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1

    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            amount = resolve_int(self.amount, ctx)
            # todo should be an event
            receiver.add_token(self.token_class, amount=amount)


@dataclass
class RemoveTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1

    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            amount = resolve_int(self.amount, ctx)
            ctx.target.remove_token(self.token_class, amount=amount)


@dataclass
class PushInstruction(Instruction):
    distance: DynamicInt

    # todo probably want direction param and update resolution
    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            dist = resolve_int(self.distance, ctx)
            PushEvent(
                engine=ctx.engine,
                recipient=ctx.target,
                distance=dist,
                source=ctx.source,
            ).resolve()


@dataclass
class PullInstruction(Instruction):
    distance: DynamicInt

    # todo probably want direction param and update resolution
    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            dist = resolve_int(self.distance, ctx)
            PullEvent(
                engine=ctx.engine,
                recipient=ctx.target,
                distance=dist,
                source=ctx.source,
            ).resolve()


# todo should really have an 'only affects entities' default flag to avoid the repeated filter logic.


@dataclass
class RefreshAbilityInstruction(Instruction):
    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            if ctx.ability:
                ctx.ability.is_tapped = False
                ctx.ability.tapped_this_turn = False
                ctx.ability.charges = ctx.ability.max_charges  # todo should be event


@dataclass
class TeleportInstruction(Instruction):
    destination: DynamicPoint

    def execute(self, ctx: ActionContext) -> None:
        receiver = ctx.engine.entity_at(ctx.receiver_point)
        if receiver:
            dest = (
                self.destination(ctx)
                if callable(self.destination)
                else self.destination
            )
            receiver.pos = dest  # todo should be event


@dataclass
class ApplyModifierInstruction(Instruction):
    modifier_class: type


# ==========================================
# ABILITY
# ==========================================


class ActionCost(Enum):
    FREE = "free"
    STANDARD = "standard"
    MOVE = "move"
    MOVE_AND_STANDARD = "move_and_standard"
    MOVE_OR_STANDARD = "move_or_standard"


@dataclass
class Ability:
    name: str
    aiming: Aiming
    instructions: List[Instruction] = field(default_factory=list)
    owner: Optional["Entity"] = None
    is_default: bool = False
    action_cost: ActionCost = ActionCost.STANDARD

    modifiers: List[Modifier] = field(default_factory=list)

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
                assert isinstance(aiming_result, MultipleAimingResults)
                instruction_aiming_result = aiming_result[instruction.aiming_name]
            else:
                instruction_aiming_result = aiming_result

            for target_point in instruction_aiming_result.target_points:
                is_hit = target_point in hit_target_points
                is_crit = target_point in crit_target_points

                ctx = ActionContext(
                    engine=engine,
                    source=source,
                    receiver_point=target_point,
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
                    receiver_point=included_point,
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
        if isinstance(aiming_result, MultipleAimingResults):
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
                roll = engine.rng.randint(1, 6)  # todo rolling should be an event
                defense = target.get_defense(attack_source=source, ability=self)
                defense = min(4, defense)
                if roll > defense:
                    hit_target_points.add(target_point)

                crit_chance = source.get_crit(receiver=target, ability=self)
                if roll >= 7 - crit_chance:
                    crit_target_points.add(target_point)
        return hit_target_points, crit_target_points
