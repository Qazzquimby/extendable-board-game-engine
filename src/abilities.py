from dataclasses import dataclass, field
from enum import Enum
from typing import (
    List,
    Optional,
    TYPE_CHECKING,
    Union,
    Type,
    Callable,
)

from aimings import Aiming, AimingResult, MultipleAimingResults
from event_library import (
    ChangeLocationEvent,
    PullEvent,
    DamageEvent,
    HealEvent,
    AddModifierEvent,
    RemoveModifierEvent,
    AddTokenEvent,
    RemoveTokenEvent,
)
from logger import log
from queries import QueryAvoidInclusion, QueryRoll
from util import UniqueTuple, DO_NOTHING, EntityId
from valence import Valence
from modifiers import Modifier, Token

if TYPE_CHECKING:
    from engine import (
        Engine,
        Entity,
    )
    from events import Event
    from point import Point


class ActionCost(Enum):
    FREE = "free"
    INSTANT = "instant"
    STANDARD = "standard"
    MOVE = "move"
    MOVE_AND_STANDARD = "move_and_standard"
    MOVE_OR_STANDARD = "move_or_standard"


@dataclass(slots=True)
class ActionContext:
    source_id: EntityId
    subject_point: "Point"  # The point currently being affected

    # all points with targets
    target_points: UniqueTuple["Point"] = field(default_factory=list)

    # all points included in areas
    included_points: UniqueTuple["Point"] = field(default_factory=list)
    ability: Optional["Ability"] = None
    is_hit: bool = True
    is_crit: bool = False

    _target: "Entity" = None

    @property
    def target_point(self):
        if len(self.target_points) != 1:
            raise ValueError("Cannot use `.target` when there are multiple targets.")
        return self.target_points[0]

    def get_target(self, engine: "Engine") -> Optional["Entity"]:
        if self._target is None:
            self._target = engine.entity_at(self.target_point)
        return self._target


DynamicInt = Union[int, Callable[[ActionContext], int]]
DynamicPoint = Union["Point", Callable[[ActionContext], "Point"]]


def resolve_int(val: DynamicInt, ctx: ActionContext) -> int:
    return val(ctx) if callable(val) else val


@dataclass(kw_only=True)  # Not frozen
class Instruction:
    """Base class for all ability effects."""

    aiming_name: Optional[str] = None
    valence: Valence = field(init=False, default=False)

    def __deepcopy__(self, memo):
        return self

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        pass


def default_reaction_condition(
    engine: "Engine", event: "Event", actor: "Entity", ability: "Ability"
) -> bool:
    from events import AbilityUseEvent
    from queries import QueryLegalAimings

    if ability.name == DO_NOTHING:
        return False
    if not isinstance(event, AbilityUseEvent):
        return False
    subject = engine.get_entity_by_id(event.subject_id)
    if subject.team == actor.team:
        return False

    trigger_targets = []
    if event.aiming_result.sub_aimings:
        for res in event.aiming_result.sub_aimings.values():
            trigger_targets.extend(res.target_points)
            trigger_targets.extend(res.included_points)
    elif event.aiming_result:
        trigger_targets.extend(event.aiming_result.target_points)
        trigger_targets.extend(event.aiming_result.included_points)

    raw_aimings = ability.aiming.get_all_aimings(
        engine=engine, actor=actor, start_pos=actor.pos, require_los=True
    )

    legal_aimings = engine.ask(
        QueryLegalAimings(subject=actor, ability=ability, base_result=raw_aimings)
    )

    for aiming_res in legal_aimings:
        ability_targets = list(aiming_res.target_points) + list(
            aiming_res.included_points
        )
        if any(t in trigger_targets for t in ability_targets):
            if ability.is_plausible_reaction(engine, event, actor):
                return True

    return False


@dataclass(frozen=True, slots=True)
class RollResult:
    roll: Optional[int]
    hit_points: UniqueTuple["Point"]
    crit_points: UniqueTuple["Point"]


@dataclass(slots=True)
class Ability:
    name: str
    aiming: Aiming
    text: str = ""
    instructions: List[Instruction] = field(default_factory=list)
    owner_id: Optional[EntityId] = None
    is_default: bool = False
    action_cost: ActionCost = ActionCost.STANDARD
    instant_speed: int = 0

    modifiers: List["Modifier"] = field(default_factory=list)

    taps: bool = False
    is_tapped: bool = False
    tapped_this_turn: bool = False
    max_charges: Optional[int] = None
    charges: Optional[int] = field(init=False, default=None)
    is_ultimate: bool = False
    ultimate_turn: Optional[int] = None

    is_undefendable: bool = False
    defense: int = 0
    crit_chance: int = 0
    reaction_condition: Optional[
        Callable[["Event", "Engine", "Entity", "Ability"], bool]
    ] = default_reaction_condition
    requires_target: bool = True

    def get_target(
        self,
        engine: "Engine",
        actor: "Entity",
        enemies: List["Entity"],
        allies: List["Entity"],
    ) -> Optional["Entity"]:
        if self.valence == Valence.MIXED:
            raise ValueError(f"Ability {self.name} needs a custom get_target")
        targets = []
        if self.valence == Valence.BAD:
            targets.extend(enemies)
        if self.valence == Valence.GOOD:
            targets.extend(allies)

        if not targets:
            return None
        return min(targets, key=lambda e: e.hp)

    def get_movement(
        self,
        engine: "Engine",
        actor: "Entity",
        reachable_points: set["Point"],
        enemies: List["Entity"],
        allies: List["Entity"],
    ) -> dict["Point", str]:
        proposed_moves = {}
        attack_range = 0
        from aimings import TargetEntity, IncludeArea

        if isinstance(self.aiming, TargetEntity):
            attack_range = self.aiming.in_range
        elif isinstance(self.aiming, IncludeArea):
            attack_range = self.aiming.area.in_range

        if attack_range > 0 and reachable_points:
            reachable_enemies = [
                e
                for e in enemies
                if any(
                    pt.get_distance(e.pos) <= attack_range for pt in reachable_points
                )
            ]
            reachable_allies = [
                a
                for a in allies
                if any(
                    pt.get_distance(a.pos) <= attack_range for pt in reachable_points
                )
            ]

            target = self.get_target(engine, actor, reachable_enemies, reachable_allies)
            if target:
                valid_points = [
                    pt
                    for pt in reachable_points
                    if pt.get_distance(target.pos) <= attack_range
                ]
                if valid_points:
                    best_at_range = min(
                        valid_points,
                        key=lambda point: (
                            abs(point.get_distance(target.pos) - attack_range) * 100
                            + point.get_distance(actor.pos),
                            point.x,
                            point.y,
                        ),
                    )
                    proposed_moves[best_at_range] = (
                        f"Range {attack_range} of {target.name} {target.id} for {self.name}"
                    )
        return proposed_moves

    def is_plausible_reaction(
        self, engine: "Engine", event: "Event", actor: "Entity"
    ) -> bool:
        return True

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        if self.requires_target and getattr(aiming_result, "target_points", None):
            if not any(engine.entity_at(pt) for pt in aiming_result.target_points):
                return 0.0
        return self._get_priority(
            engine=engine, actor=actor, pos=pos, aiming_result=aiming_result
        )

    def _get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return 1

    def get_hash_info(self):
        return (
            self.name,
            self.aiming,
            self.owner_id,
            self.is_tapped,
            self.charges,
        )

    def __hash__(self):
        return hash(self.get_hash_info())

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return hash(self) == hash(other)

    def __post_init__(self):
        self.charges = self.max_charges

    @property
    def valence(self):
        has_good = any(
            instruction.valence in (Valence.GOOD, Valence.MIXED)
            for instruction in self.instructions
        )
        has_bad = any(
            instruction.valence in (Valence.BAD, Valence.MIXED)
            for instruction in self.instructions
        )
        if has_good and has_bad:
            return Valence.MIXED
        if has_good:
            return Valence.GOOD
        if has_bad:
            return Valence.BAD
        assert False

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
    ) -> None:
        self._mark_usage()

        from events import AbilityUseEvent

        engine.event_queue.enqueue(
            AbilityUseEvent(source=source, ability=self, aiming_result=aiming_result)
        )

    def react(
        self,
        engine: "Engine",
        source: "Entity",
        aiming_result: Union[AimingResult, MultipleAimingResults],
    ):

        from events import AbilityUseEvent

        engine.event_queue.enqueue_front(
            AbilityUseEvent(
                source=source,
                ability=self,
                aiming_result=aiming_result,
                is_reaction=True,
            ),
        )

    def _mark_usage(self):
        if self.charges is not None:
            self.charges -= 1
        if self.taps:
            self.is_tapped = True
            self.tapped_this_turn = True

    def execute_instructions(
        self,
        engine: "Engine",
        source: "Entity",
        aiming_result: Union[AimingResult, MultipleAimingResults],
        roll_result: "RollResult",
    ):
        for instruction in self.instructions:
            if instruction.aiming_name:
                instruction_aiming_result = aiming_result.sub_aimings[
                    instruction.aiming_name
                ]
            else:
                instruction_aiming_result = aiming_result

            for target_point in instruction_aiming_result.target_points:
                is_hit = target_point in roll_result.hit_points
                is_crit = target_point in roll_result.crit_points

                ctx = ActionContext(
                    source_id=source.id,
                    subject_point=target_point,
                    target_points=instruction_aiming_result.target_points,
                    included_points=instruction_aiming_result.included_points,
                    ability=self,
                    is_hit=is_hit,
                    is_crit=is_crit,
                )
                instruction.execute(engine=engine, ctx=ctx)

            for included_point in instruction_aiming_result.included_points:
                entity = engine.entity_at(included_point)
                if entity:
                    is_avoided = QueryAvoidInclusion(
                        subject=entity,
                        ability=self,
                    ).resolve(engine=engine)
                    if is_avoided:
                        continue
                ctx = ActionContext(
                    source_id=source.id,
                    subject_point=included_point,
                    target_points=instruction_aiming_result.target_points,
                    included_points=instruction_aiming_result.included_points,
                    ability=self,
                )
                instruction.execute(engine=engine, ctx=ctx)

    def get_hash(self) -> float:
        import hashlib

        key = f"{self.owner_id}__{self.name}"
        hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
        return float(hash_int % 10000) / 100.0

    def get_roll_result(
        self,
        aiming_result: Union[AimingResult, MultipleAimingResults],
        engine: "Engine",
        source: "Entity",
    ) -> RollResult:
        if isinstance(aiming_result, dict):
            all_target_points = []
            for aiming_result_set in aiming_result.values():
                all_target_points += aiming_result_set.target_points
                all_target_points = UniqueTuple(all_target_points)
        else:
            all_target_points = aiming_result.target_points
        hit_target_points = []
        crit_target_points = []

        roll = None
        for target_point in all_target_points:
            target = engine.entity_at(target_point)
            if target:
                defense = target.get_defense(
                    engine=engine, attack_source=source, ability=self
                )
                defense = min(4, defense)
                crit_chance = source.get_crit(
                    engine=engine, subject=target, ability=self
                )

                if defense > 0 or crit_chance > 0:
                    if not roll:
                        roll = QueryRoll(rng=engine.rng, subject=source).resolve(
                            engine=engine
                        )

                    if roll > defense:
                        hit_target_points.append(target_point)
                        if roll >= 7 - crit_chance:
                            crit_target_points.append(target_point)
                            log(
                                f"Crit {target} with a roll of {roll} on crit chance {crit_chance}"
                            )
                    else:
                        log(
                            f"Missed {target} with a roll of {roll} less than defense {defense}"
                        )
                else:
                    # No roll means auto hits
                    hit_target_points.append(target_point)

        return RollResult(
            roll=roll,
            hit_points=UniqueTuple(hit_target_points),
            crit_points=UniqueTuple(crit_target_points),
        )


@dataclass
class DamageInstruction(Instruction):
    amount: DynamicInt
    undefendable: bool = False
    irreducible: bool = False
    valence = Valence.BAD

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


@dataclass
class HealInstruction(Instruction):
    amount: DynamicInt
    valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            amount = resolve_int(self.amount, ctx)
            engine.event_queue.enqueue(HealEvent(subject=subject, amount=amount))


@dataclass
class AddModifierInstruction(Instruction):
    modifier_class: Type["Modifier"]
    modifier_kwargs: dict = field(default_factory=dict)

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


@dataclass
class RemoveModifierInstruction(Instruction):
    modifier_class: Type["Modifier"]
    amount: DynamicInt = 1

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


@dataclass
class AddTokenInstruction(Instruction):
    token_class: Type["Token"]
    amount: DynamicInt = 1
    token_kwargs: dict = field(default_factory=dict)

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


@dataclass
class PullInstruction(Instruction):
    distance: DynamicInt
    valence = Valence.MIXED

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


@dataclass
class UseAnAbilityInstruction(Instruction):
    default_only: bool = False
    required_target: Optional["Point"] = None
    subject_chooses: bool = True
    valence = Valence.MIXED

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


@dataclass
class RefreshAbilityInstruction(Instruction):
    valence = Valence.GOOD

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        subject = engine.entity_at(ctx.subject_point)
        if subject:
            if ctx.ability:
                ctx.ability.is_tapped = False
                ctx.ability.tapped_this_turn = False
                ctx.ability.charges = ctx.ability.max_charges  # todo should be event


@dataclass
class TeleportInstruction(Instruction):
    destination: DynamicPoint
    valence = Valence.MIXED

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
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

    def __post__init__(self):
        self.valence = self.modifier_class.valence
