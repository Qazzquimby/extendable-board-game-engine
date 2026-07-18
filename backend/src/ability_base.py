"""
Ability base types — ActionCost, ActionContext, Instruction, RollResult.

Extracted from abilities.py to keep modules under 400 lines.
Contains the base types and interfaces that abilities and
instructions depend on.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import (
    List,
    Optional,
    TYPE_CHECKING,
    Union,
    Callable,
)

from util import UniqueTuple, DO_NOTHING, EntityId
from valence import Valence

if TYPE_CHECKING:
    from engine import Engine, Entity
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
    subject_point: "Point"

    target_points: UniqueTuple["Point"] = field(default_factory=list)
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


DynamicInt = Union[int, Callable[["ActionContext"], int]]
DynamicPoint = Union["Point", Callable[["ActionContext"], "Point"]]


@dataclass(kw_only=True)
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
        raise NotImplementedError


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
