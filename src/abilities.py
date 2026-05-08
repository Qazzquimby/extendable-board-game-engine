from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING, Union, Callable, Type

if TYPE_CHECKING:
    from engine import Engine, Entity, Token
    from point import Point
    from targeting import Area


@dataclass
class ActionContext:
    engine: "Engine"
    source: "Entity"
    target: Union["Entity", "Point"]
    targets: List[Union["Entity", "Point"]] = field(default_factory=list)
    ability: Optional["Ability"] = None
    is_hit: bool = True
    is_crit: bool = False


DynamicInt = Union[int, Callable[[ActionContext], int]]
DynamicPoint = Union["Point", Callable[[ActionContext], "Point"]]


def resolve_int(val: DynamicInt, ctx: ActionContext) -> int:
    return val(ctx) if callable(val) else val


# ==========================================
# TARGETING
# ==========================================


@dataclass
class Targeting:
    """Base class for how an ability finds its targets."""

    pass


@dataclass
class TargetSelf(Targeting):
    """Targets the ability's owner."""

    pass


@dataclass
class TargetUnit(Targeting):
    """Targets a single unit within a given range. None means unlimited."""

    in_range: Optional[int] = None


@dataclass
class TargetArea(Targeting):
    """Targets an area on the grid."""

    area: "Area"


# ==========================================
# EFFECTS
# ==========================================


@dataclass
class Instruction:
    """Base class for all ability effects."""

    def execute(self, ctx: ActionContext) -> None:
        pass


@dataclass
class DamageInstruction(Instruction):
    amount: DynamicInt
    undefendable: bool = False
    irreducible: bool = False

    def execute(self, ctx: ActionContext) -> None:
        from engine import (
            DamageEvent,
        )  # todo feels like events and effects should be kept together.

        amount = resolve_int(self.amount, ctx)
        if ctx.is_crit:
            amount *= 2  # Critical hit grants +1x damage multiplier
        # todo will likely need more extensible later

        if hasattr(ctx.target, "hp"):
            DamageEvent(
                engine=ctx.engine,
                source=ctx.source,
                target=ctx.target,
                amount=amount,
                ability=ctx.ability,
            ).resolve()


@dataclass
class HealInstruction(Instruction):
    amount: DynamicInt

    def execute(self, ctx: ActionContext) -> None:
        from engine import HealEvent

        amount = resolve_int(self.amount, ctx)
        if hasattr(ctx.target, "hp"):
            HealEvent(engine=ctx.engine, target=ctx.target, amount=amount).resolve()


@dataclass
class GiveTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1

    def execute(self, ctx: ActionContext) -> None:
        amt = resolve_int(self.amount, ctx)
        if hasattr(ctx.target, "add_token"):
            ctx.target.add_token(self.token_class, amt)


@dataclass
class RemoveTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1

    def execute(self, ctx: ActionContext) -> None:
        amt = resolve_int(self.amount, ctx)
        if hasattr(ctx.target, "remove_token"):
            ctx.target.remove_token(self.token_class, amt)


@dataclass
class PushInstruction(Instruction):
    distance: DynamicInt

    # todo probably want direction param and update resolution
    def execute(self, ctx: ActionContext) -> None:
        from engine import PushEvent

        dist = resolve_int(self.distance, ctx)
        if hasattr(ctx.target, "pos"):
            PushEvent(
                engine=ctx.engine, target=ctx.target, distance=dist, source=ctx.source
            ).resolve()


@dataclass
class PullInstruction(Instruction):
    distance: DynamicInt

    # todo probably want direction param and update resolution
    def execute(self, ctx: ActionContext) -> None:
        from engine import PullEvent

        dist = resolve_int(self.distance, ctx)
        if hasattr(ctx.target, "pos"):
            PullEvent(
                engine=ctx.engine, target=ctx.target, distance=dist, source=ctx.source
            ).resolve()


@dataclass
class RefreshAbilityInstruction(Instruction):
    def execute(self, ctx: ActionContext) -> None:
        if ctx.ability:
            ctx.ability.is_tapped = False
            ctx.ability.tapped_this_turn = False
            ctx.ability.charges = ctx.ability.max_charges


@dataclass
class TeleportInstruction(Instruction):
    destination: DynamicPoint

    def execute(self, ctx: ActionContext) -> None:
        dest = self.destination(ctx) if callable(self.destination) else self.destination
        if hasattr(ctx.target, "pos"):
            ctx.target.pos = dest


@dataclass
class ApplyModifierInstruction(Instruction):
    modifier_class: type


# ==========================================
# ABILITY
# ==========================================


@dataclass
class Ability:
    name: str
    targeting: Targeting
    instructions: List[Instruction] = field(default_factory=list)
    owner: Optional["Entity"] = None
    is_default: bool = False
    cost_standard_action: bool = True
    cost_move_action: bool = False
    cost_free_action: bool = False
    target: Optional[Union["Entity", "Point"]] = None
    taps: bool = False
    is_tapped: bool = False
    tapped_this_turn: bool = False
    max_charges: Optional[int] = None
    is_ultimate: bool = False
    ultimate_turn: Optional[int] = None
    crit_chance: int = 0

    def __post_init__(self):
        self.charges = self.max_charges

    def execute(
        self,
        engine: "Engine",
        source: "Entity",
        targets: List[Union["Entity", "Point"]],
    ) -> None:
        if self.charges is not None:
            self.charges -= 1
        if self.taps:
            self.is_tapped = True
            self.tapped_this_turn = True

        roll = engine.rng.randint(1, 6)  # todo rolling should be an event

        # Attack rolls apply to entity or point targets, not areas
        if not isinstance(self.targeting, TargetArea):
            for target in targets:
                defense = target.get_defense(attack_source=source, ability=self)
                defense = min(4, defense)
                is_hit = roll > defense

                crit_chance = source.get_crit(target=target, ability=self)
                is_crit = roll >= 7 - crit_chance

                ctx = ActionContext(
                    engine=engine,
                    source=source,
                    target=target,
                    targets=targets,
                    ability=self,
                    is_hit=is_hit,
                    is_crit=is_crit,
                )

                if is_hit:
                    for instruction in self.instructions:
                        instruction.execute(ctx)

    def get_hash(self) -> float:
        import hashlib

        owner_set = getattr(self.owner, "set", "unknown") if self.owner else "unknown"
        owner_name = getattr(self.owner, "name", "unknown") if self.owner else "unknown"
        key = f"{owner_set}__{owner_name}__{self.name}"
        hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
        return float(hash_int % 10000) / 100.0
