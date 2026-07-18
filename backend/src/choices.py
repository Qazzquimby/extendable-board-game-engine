from typing import List, Optional, Dict, Any, TYPE_CHECKING, Union

from aimings import AimingResult
from point import Point
from util import UniqueTuple, DO_NOTHING

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity


class Choice:
    def __init__(self, features: Dict[str, Any] = None, priority: float = 1.0):
        if features is None:
            features = {}
        self.features = features
        self.priority = priority

    def __hash__(self):
        try:
            return hash(frozenset(self.features.items()))
        except TypeError:
            return id(self)

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self.features == other.features


class PlausibleMoveAndAction(Choice):
    def __init__(
        self,
        move_path: List[Point],
        target: Optional["Entity"],
        ability: "Ability",
        movement_name: str = "",
        actor: "Entity" = None,
        aiming_result: "AimingResult" = None,
        priority: float = 1.0,
    ):
        self.move_path = move_path
        if move_path:
            self.move_pos = move_path[-1]
        else:
            self.move_pos = actor.pos
        self.target = target
        self.ability = ability
        self.movement_name = movement_name
        self.aiming_result = aiming_result
        self.actor = actor
        super().__init__(features={}, priority=priority)

    def __str__(self):
        return f"{self.ability.owner_id} go to {self.move_pos} and use {self.ability.name} on {self.target.pos if self.target else None}"

    def __hash__(self):
        return hash(
            (self.ability.name, self.movement_name, self.move_pos, self.aiming_result)
        )

    def __eq__(self, other):
        if not isinstance(other, PlausibleMoveAndAction):
            return False
        return (
            self.ability.name,
            self.movement_name,
            self.move_pos,
            self.aiming_result,
        ) == (
            other.ability.name,
            other.movement_name,
            other.move_pos,
            other.aiming_result,
        )


class PlausibleFreeAction(Choice):
    def __init__(
        self,
        target: Optional["Entity"],
        ability: "Ability",
        actor: "Entity",
        aiming_result: "AimingResult",
        priority: float = 1.0,
        **kwargs,
    ):
        self.target = target
        self.ability = ability
        self.aiming_result = aiming_result
        self.actor = actor
        super().__init__(priority=priority)

    def __hash__(self):
        return hash((self.ability.name, self.aiming_result))

    def __eq__(self, other):
        if not isinstance(other, PlausibleFreeAction):
            return False
        return (self.ability.name, self.aiming_result) == (
            other.ability.name,
            other.aiming_result,
        )

    @property
    def ends_turn(self) -> bool:
        return False


PlausibleActionOrMoveAndAction = Union[PlausibleFreeAction, PlausibleMoveAndAction]


def get_plausible_free_actions(
    actor: "Entity",
    engine: "Engine",
) -> List[PlausibleFreeAction]:
    from abilities import ActionCost
    from planner import _get_plausible_uses_of_ability_at_pos

    plausible_actions = {}
    for ability in actor.abilities:
        if (
            ability.action_cost not in (ActionCost.FREE, ActionCost.INSTANT)
            or not ability.is_available(round_num=engine.round_num)
        ):
            continue

        plausible_uses = _get_plausible_uses_of_ability_at_pos(
            actor=actor,
            engine=engine,
            pos=actor.pos,
            ability=ability,
            choice_class=PlausibleFreeAction,
        )
        plausible_actions.update(plausible_uses)

    return list(plausible_actions.values())
