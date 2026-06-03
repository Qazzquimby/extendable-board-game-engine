from dataclasses import dataclass, field
from typing import Optional, Union, List, Dict, TYPE_CHECKING, Callable

from areas import Area
from point import Point

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


# todo aimings should have their logic in the class, not in the agent.


@dataclass
class AimingResult:
    target_points: List[Point] = field(default_factory=list)
    included_points: List[Point] = field(default_factory=list)


MultipleAimingResults = Dict[str, AimingResult]


class Aiming:
    """Base class for how an ability finds its subjects."""

    def __init__(self, condition: Optional[AimingCondition] = None):
        self.condition = condition

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

    def __init__(self, aimings: Union[List[Aiming], Dict[str, Aiming]]):
        super().__init__()
        if isinstance(aimings, list):
            aimings = {f"{i}": t for i, t in enumerate(aimings)}
        self.aimings = aimings


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
                res.append(AimingResult(included_points=list(area_points)))
        return res
