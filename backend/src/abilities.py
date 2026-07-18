from __future__ import annotations
from dataclasses import dataclass, field
from typing import (
    List,
    Optional,
    TYPE_CHECKING,
    Union,
    Callable,
)

from ability_base import (
    ActionCost,
    ActionContext,
    DynamicInt,
    DynamicPoint,
    Instruction,
    RollResult,
    default_reaction_condition,
)
from scoring import (
    resolve_int,
    best_move_for_score,
    displacement_value,
    score_damage,
    score_expected_damage,
    score_heal,
    score_add_token,
    reaction_value_of_instructions,
    point_is_in_aiming_result,
    reaction_resource_conservation,
)


from aimings import Aiming, AimingResult, MultipleAimingResults
from queries import QueryAvoidInclusion
from util import UniqueTuple, DO_NOTHING, EntityId
from valence import Valence
from modifiers import Modifier

if TYPE_CHECKING:
    from engine import (
        Engine,
        Entity,
    )
    from events import Event
    from point import Point


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
        # Collect candidates by valence
        candidates = []
        if self.valence in (Valence.BAD, Valence.MIXED):
            candidates.extend(enemies)
        if self.valence in (Valence.GOOD, Valence.MIXED):
            candidates.extend(allies)

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # Pick the target with highest priority at current position
        best = None
        best_score = -float("inf")
        for candidate in candidates:
            if not candidate.pos:
                continue
            score = self._target_priority(engine, actor, candidate)
            if score > best_score:
                best_score = score
                best = candidate

        return best or candidates[0]

    def _target_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        target: "Entity",
    ) -> float:
        """Estimate priority if this entity were the target.

        Creates a minimal AimingResult for the target and evaluates it.
        Override in subclasses for complex aiming types.
        """
        from aimings import AimingResult

        # Build a minimal aiming result
        aiming = AimingResult(
            target_points=[target.pos],
            included_points=[],
            sub_aimings={},
        )
        return self.evaluate_priority(engine, actor, actor.pos, aiming)

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

    def evaluate_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        if self.requires_target and getattr(aiming_result, "target_points", None):
            if not any(engine.entity_at(pt) for pt in aiming_result.target_points):
                return 0.0
        return self.get_priority(engine, actor, pos, aiming_result)

    def get_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        pos: "Point",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        return self._auto_priority(engine, actor, aiming_result)

    def _auto_priority(
        self,
        engine: "Engine",
        actor: "Entity",
        aiming_result: Union["AimingResult", "MultipleAimingResults"],
    ) -> float:
        """Score each instruction against each target/included point.

        Each instruction's .score() method handles its own contribution.
        Sums across all points and all instructions.
        """
        score = 0.0
        for instruction in self.instructions:
            # Determine which aiming result applies to this instruction
            if instruction.aiming_name and isinstance(
                aiming_result, MultipleAimingResults
            ):
                inst_aiming = aiming_result.sub_aimings[instruction.aiming_name]
            else:
                inst_aiming = aiming_result

            for pt in list(inst_aiming.target_points) + list(
                inst_aiming.included_points
            ):
                target = engine.entity_at(pt)
                if target:
                    ctx = ActionContext(
                        source_id=actor.id,
                        subject_point=pt,
                        target_points=inst_aiming.target_points,
                        included_points=inst_aiming.included_points,
                        ability=self,
                    )
                    score += instruction.score(engine, actor, target, ctx)
        return score

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
        if self.is_ultimate and self.max_charges is None:
            self.max_charges = 1
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

    def is_available(self, round_num: Optional[int] = None):
        if self.is_tapped:
            return False
        if self.charges is not None and self.charges <= 0:
            return False
        if (
            self.is_ultimate
            and self.ultimate_turn is not None
            and round_num is not None
        ):
            if round_num < self.ultimate_turn:
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
        from scoring import resolve_roll_result
        return resolve_roll_result(self, aiming_result, engine, source)

