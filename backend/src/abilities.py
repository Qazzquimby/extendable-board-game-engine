from dataclasses import dataclass, field
from enum import Enum
from typing import (
    List,
    Optional,
    TYPE_CHECKING,
    Union,
    Callable,
    Type,
)

from aimings import Aiming, AimingResult, MultipleAimingResults
from logger import log
from queries import QueryAvoidInclusion, QueryRoll
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


def best_move_for_score(
    reachable_points: set["Point"],
    actor_pos: "Point",
    score_fn: Callable[["Point"], float],
    reason: str,
) -> dict["Point", str]:
    """Score each reachable point and return the best one with a reason string.

    Uses the standard tiebreaker: prefer the point closest to the actor.
    Returns an empty dict if no point scores > 0.
    """
    if not reachable_points:
        return {}
    best = max(
        reachable_points,
        key=lambda pt: (score_fn(pt), -pt.get_distance(actor_pos)),
    )
    if score_fn(best) > 0:
        return {best: reason}
    return {}


def displacement_value(
    entity: "Entity",
    from_pos: "Point",
    to_pos: "Point",
    engine: "Engine",
) -> float:
    """How many movement-actions this displacement saves (or costs if negative).

    Positive = the entity ends up closer to its preferred position
    (its nearest enemy), saving future movement actions.
    Negative = the entity ends up farther away, needing extra actions to get back.

    Value = (old_distance - new_distance) / speed.
    """
    pref = entity.get_preferred_position(engine)
    if pref is None:
        return 0.0
    saved_distance = from_pos.get_distance(pref) - to_pos.get_distance(pref)
    speed = entity.get_speed(engine)
    if speed == 0:
        return 0.0
    return saved_distance / speed


def score_damage(amount: int, target_hp: int) -> float:
    """Score for dealing `amount` damage to a target with `target_hp`.

    Automatically values kills: damage is doubled if amount >= target_hp.
    Capped at target_hp (can't overkill for extra score).
    """
    effective = min(amount, target_hp)
    if amount >= target_hp:
        effective += 1.5  # killing is better than leaving low health
    return float(effective)


def score_heal(amount: int, missing_hp: int) -> float:
    """Score for healing `amount` on a target missing `missing_hp` HP.

    Capped at missing_hp (can't overheal for extra score).
    """
    return float(min(amount, missing_hp))


def score_add_token(token_class: "Type"):
    """Base priority for applying a token/modifier to a single target.

    Returns a simple default — specific abilities may want custom values.
    Bad tokens on enemies = +2, Good tokens on allies = +1.
    """
    from valence import Valence

    if token_class.valence == Valence.BAD:
        return 2.0
    elif token_class.valence == Valence.GOOD:
        return 1.0
    return 0.0


@dataclass(kw_only=True)  # Not frozen
class Instruction:
    """Base class for all ability effects."""

    aiming_name: Optional[str] = None
    valence: Valence

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "valence" not in cls.__dict__ and "__post_init__" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must define a class-level `valence` attribute. "
                f"Add `valence: Valence = Valence.<GOOD|BAD|MIXED>` to the class body."
            )

    def __deepcopy__(self, memo):
        return self

    def execute(self, engine: "Engine", ctx: ActionContext) -> None:
        pass

    def score(
        self,
        engine: "Engine",
        actor: "Entity",
        target: "Entity",
        ctx: ActionContext,
    ) -> float:
        """Priority contribution of this instruction for a single target entity."""
        raise NotImplemented


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
