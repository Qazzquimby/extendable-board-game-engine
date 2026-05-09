from dataclasses import dataclass, field
from typing import Optional, Union, List, Dict

from areas import Area
from point import Point

# Recipient: Anything being affected
# Target Point: A point that has been individually chosen
# Target: The entity or marker at the target point, if any.
# Included Point: A point that is in a chosen area. Not a target.
# Included Entity: An entity in an included point, if any.


@dataclass
class AimingResult:
    target_points: List[Point] = field(default_factory=list)
    included_points: List[Point] = field(default_factory=list)


MultipleAimingResults = Dict[str, AimingResult]


@dataclass
class Aiming:
    """Base class for how an ability finds its recipients."""

    pass


class MultipleAiming(Aiming):
    """Requires multiple aimings. The dict keys are just identifiers for the aimings, and can be used in instructions to refer to specific targets."""

    def __init__(self, aimings: Union[List[Aiming], Dict[str, Aiming]]):
        if isinstance(aimings, list):
            aimings = {f"{i}": t for i, t in enumerate(aimings)}
        self.aimings = aimings


@dataclass
class TargetSelf(Aiming):
    """Targets the owner's point."""

    pass


@dataclass
class TargetUnit(Aiming):
    """Targets a point containing a unit within a given range. None means unlimited."""

    in_range: Optional[int] = None


@dataclass
class TargetPoint(Aiming):
    """Targets a point on the grid. Optionally must be empty."""

    in_range: Optional[int] = None
    empty: bool = False


@dataclass
class IncludeArea(Aiming):
    """Targets an area on the grid."""

    area: "Area"
