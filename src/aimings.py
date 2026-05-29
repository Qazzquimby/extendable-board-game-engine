from dataclasses import dataclass, field
from typing import Optional, Union, List, Dict, TYPE_CHECKING

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


# todo aimings should have their logic in the class, not in the agent.


@dataclass
class AimingResult:
    target_points: List[Point] = field(default_factory=list)
    included_points: List[Point] = field(default_factory=list)


MultipleAimingResults = Dict[str, AimingResult]


@dataclass
class Aiming:
    """Base class for how an ability finds its subjects."""

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point,
        require_los: bool = True,
    ) -> List[AimingResult]:
        raise NotImplementedError


class MultipleAiming(Aiming):
    """Requires multiple aimings. The dict keys are just identifiers for the aimings, and can be used in instructions to refer to specific targets."""

    def __init__(self, aimings: Union[List[Aiming], Dict[str, Aiming]]):
        if isinstance(aimings, list):
            aimings = {f"{i}": t for i, t in enumerate(aimings)}
        self.aimings = aimings


@dataclass
class TargetSelf(Aiming):
    """Targets the owner's point."""

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point,
        require_los: bool = True,
    ) -> List[AimingResult]:
        return [AimingResult(target_points=[start_pos])]


@dataclass
class TargetEntity(Aiming):
    """Targets a point containing a unit within a given range. None means unlimited."""

    in_range: Optional[int] = None

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point,
        require_los: bool = True,
    ) -> List[AimingResult]:
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

            res.append(AimingResult(target_points=[e.pos]))
        return res


@dataclass
class TargetPoint(Aiming):
    """Targets a point on the grid. Optionally must be empty."""

    in_range: Optional[int] = None
    empty: bool = False

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point,
        require_los: bool = True,
    ) -> List[AimingResult]:
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


@dataclass
class IncludeArea(Aiming):
    """Targets an area on the grid."""

    area: "Area"

    def get_all_aimings(
        self,
        engine: "Engine",
        actor: "Entity",
        start_pos: Point,
        require_los: bool = True,
    ) -> List[AimingResult]:
        res = []
        # todo if require_los, only one point in the area requires los.
        for area_points in self.area.get_selections(engine.grid, start_pos):
            res.append(AimingResult(included_points=list(area_points)))
        return res
