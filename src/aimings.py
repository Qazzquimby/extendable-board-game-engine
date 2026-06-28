import abc
import itertools
from dataclasses import dataclass, field
from typing import Optional, Union, List, Dict, TYPE_CHECKING, Callable

from areas import Area
from point import Point
from util import UniqueTuple

if TYPE_CHECKING:
    from engine import Engine
    from engine import Entity

# subject: Anything being affected
# Target Point: A point that has been individually chosen
# Target: The entity or marker at the target point, if any.
# Included Point: A point that is in a chosen area. Not a target.
# Included Entity: An entity in an included point, if any.

AimingCondition = Callable[["Engine", "Entity", Point], bool]


def is_enemy_aim_condition(engine: "Engine", actor: "Entity", point: "Point") -> bool:
    entity = engine.entity_at(point)
    return entity is not None and entity.team != actor.team


def is_ally_aim_condition(engine: "Engine", actor: "Entity", point: "Point") -> bool:
    entity = engine.entity_at(point)
    if not entity:
        return False
    return entity.team == actor.team


def is_ally_but_not_self_aim_condition(
    engine: "Engine", actor: "Entity", point: "Point"
) -> bool:
    is_ally = is_ally_aim_condition(engine, actor, point)
    entity = engine.entity_at(point)
    return is_ally and entity != actor


def has_any_entity_aim_condition(
    engine: "Engine", actor: "Entity", point: "Point"
) -> bool:
    return engine.entity_at(point) is not None


#


@dataclass(frozen=True)
class AimingResult:
    target_points: UniqueTuple[Point] = field(default_factory=list)
    included_points: UniqueTuple[Point] = field(default_factory=list)
    sub_aimings: Optional[Dict[str, "AimingResult"]] = None

    def __hash__(self):
        if self.sub_aimings:
            sub_aimings = self.sub_aimings
        else:
            sub_aimings = dict()
        return hash(
            (
                UniqueTuple(self.target_points),
                UniqueTuple(self.included_points),
                UniqueTuple((k, hash(v)) for k, v in sub_aimings.items()),
            )
        )

    def __eq__(self, other):
        if self is None or other is None:
            return self is other

        if self.sub_aimings or other.sub_aimings:
            if not (self.sub_aimings and other.sub_aimings) or set(
                self.sub_aimings.keys()
            ) != set(other.sub_aimings.keys()):
                return False
            return all(
                (self.sub_aimings[k] == other.sub_aimings[k]) for k in self.sub_aimings
            )

        a_targets = set(getattr(self, "target_points", []))
        b_targets = set(getattr(other, "target_points", []))
        a_included = set(getattr(self, "included_points", []))
        b_included = set(getattr(other, "included_points", []))

        return a_targets == b_targets and a_included == b_included


MultipleAimingResults = Dict[str, AimingResult]


class Aiming(abc.ABC):
    """Base class for how an ability finds its subjects."""

    def __init__(self, condition: Optional[AimingCondition] = None):
        self.condition = condition

    def __hash__(self):
        return hash((type(self), self.condition))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self.condition == other.condition

    @abc.abstractmethod
    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point = None,  # default subj current position
        require_los: bool = True,  # todo should be part of the init not the getter
    ) -> List[AimingResult]:
        raise NotImplementedError


class MultipleAiming(Aiming):
    """Requires multiple aimings. The dict keys are just identifiers for the aimings, and can be used in instructions to refer to specific targets."""

    def __init__(
        self,
        aimings: Union[List[Aiming], Dict[str, Aiming]],
        exclusions: Optional[Dict[str, str]] = None,
    ):
        # Exclusions is {"aiming": "has this aiming subtracted"}
        # For example 'all others than target in burst 1' -> {"burst": "target"}
        super().__init__()
        if isinstance(aimings, list):
            aimings = {f"{i}": t for i, t in enumerate(aimings)}
        self.aimings = aimings
        self.exclusions = exclusions or {}

    def __hash__(self):
        return hash(
            (
                type(self),
                self.condition,
                frozenset(self.aimings.items()),
                frozenset(self.exclusions.items()),
            )
        )

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return (
            self.condition == other.condition
            and self.aimings == other.aimings
            and self.exclusions == other.exclusions
        )

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point = None,
        require_los: bool = True,
    ) -> List[AimingResult]:
        if not start_pos:
            start_pos = actor.pos

        # Get all possible aimings for each sub-aiming
        all_sub_aimings = {}
        for name, aiming in self.aimings.items():
            sub_aims = aiming.get_all_aimings(engine, actor, start_pos, require_los)
            if not sub_aims:
                # If any sub-aiming has no valid targets, then no combinations are possible.
                return []
            all_sub_aimings[name] = sub_aims

        # Generate combinations of aimings
        aiming_names = list(all_sub_aimings.keys())
        aiming_lists = list(all_sub_aimings.values())

        res = []
        for combination in itertools.product(*aiming_lists):
            sub_aimings_dict = dict(zip(aiming_names, combination))

            # Apply exclusions - need to copy because AimingResult objects can be shared across combinations
            sub_aimings_dict = {
                name: AimingResult(
                    target_points=list(result.target_points),
                    included_points=list(result.included_points),
                    sub_aimings=result.sub_aimings,
                )
                for name, result in sub_aimings_dict.items()
            }

            for to_filter_name, from_filter_name in self.exclusions.items():
                if (
                    to_filter_name in sub_aimings_dict
                    and from_filter_name in sub_aimings_dict
                ):
                    to_filter_result = sub_aimings_dict[to_filter_name]
                    from_filter_result = sub_aimings_dict[from_filter_name]

                    points_to_exclude = set(from_filter_result.target_points) | set(
                        from_filter_result.included_points
                    )

                    new_to_filter_result = AimingResult(
                        target_points=UniqueTuple(
                            [
                                p
                                for p in to_filter_result.target_points
                                if p not in points_to_exclude
                            ]
                        ),
                        included_points=UniqueTuple(
                            [
                                p
                                for p in to_filter_result.included_points
                                if p not in points_to_exclude
                            ]
                        ),
                    )
                    sub_aimings_dict[to_filter_name] = new_to_filter_result

            combined_target_points = []
            combined_included_points = []
            for sub_aiming_result in sub_aimings_dict.values():
                combined_target_points.extend(sub_aiming_result.target_points)
                combined_included_points.extend(sub_aiming_result.included_points)

            res.append(
                AimingResult(
                    target_points=UniqueTuple(combined_target_points),
                    included_points=UniqueTuple(combined_included_points),
                    sub_aimings=sub_aimings_dict,
                )
            )
        return res


class TargetSelf(Aiming):
    """Targets the owner's point."""

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point = None,
        require_los: bool = True,
    ) -> List[AimingResult]:
        if not start_pos:
            start_pos = actor.pos
        return [AimingResult(target_points=[start_pos])]


class TargetEntity(Aiming):
    """Targets a point containing a unit within a given range. None means unlimited."""

    def __init__(
        self,
        in_range: Optional[int] = None,
        condition: Optional[AimingCondition] = None,
    ):
        super().__init__(condition=condition)
        self.in_range = in_range

    def __hash__(self):
        return hash((type(self), self.condition, self.in_range))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self.condition == other.condition and self.in_range == other.in_range

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point = None,
        require_los: bool = True,
    ) -> List[AimingResult]:
        if not start_pos:
            start_pos = actor.pos

        res = []
        for e in engine.entities:
            if e.pos is None:
                continue

            if self.in_range is not None:
                distance = engine.grid.get_range(start_pos, e.pos)
                if distance > self.in_range:
                    continue

            if require_los:
                visible, _has_cover = engine.grid.get_line_of_sight(start_pos, e.pos)
                if not visible:
                    continue

            if self.condition and not self.condition(engine, actor, e.pos):
                continue

            res.append(AimingResult(target_points=[e.pos]))
        return res


class TargetPoint(Aiming):
    """Targets a point on the grid. Optionally must be empty."""

    def __init__(
        self,
        in_range: Optional[int] = None,
        empty: bool = False,
        condition: Optional[AimingCondition] = None,
    ):
        super().__init__(condition=condition)
        self.in_range = in_range
        self.empty = empty

    def __hash__(self):
        return hash((type(self), self.condition, self.in_range, self.empty))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return (
            self.condition == other.condition
            and self.in_range == other.in_range
            and self.empty == other.empty
        )

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point = None,
        require_los: bool = True,
    ) -> List[AimingResult]:
        if not start_pos:
            start_pos = actor.pos

        res = []
        for x in range(engine.grid.width):
            for y in range(engine.grid.height):
                p = Point(x, y)
                if self.empty and engine.entity_at(p):
                    continue
                if self.in_range is not None:
                    if engine.grid.get_range(start_pos, p) > self.in_range:
                        continue
                if require_los:
                    visible, _ = engine.grid.get_line_of_sight(start_pos, p)
                    if not visible:
                        continue
                res.append(AimingResult(target_points=[p]))
        return res


class IncludeArea(Aiming):
    """Targets an area on the grid."""

    def __init__(
        self,
        area: "Area",
        condition: Optional[AimingCondition] = None,
    ):
        super().__init__(condition=condition)
        self.area = area

    def __hash__(self):
        return hash((type(self), self.condition, self.area))

    def __eq__(self, other):
        if type(self) is not type(other):
            return False
        return self.condition == other.condition and self.area == other.area

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point = None,
        require_los: bool = True,
    ) -> List[AimingResult]:
        if not start_pos:
            start_pos = actor.pos

        res = []
        # todo if require_los, only one point in the area requires los.
        for area_points in self.area.get_selections(engine.grid, start_pos):
            filtered_points = []
            for point in area_points:
                if not self.condition or self.condition(engine, actor, point):
                    filtered_points.append(point)
            if filtered_points:
                res.append(AimingResult(included_points=filtered_points))
        return res
