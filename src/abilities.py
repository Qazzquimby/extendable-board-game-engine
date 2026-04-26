from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from engine import Entity
    from point import Point
    from targeting import Area


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
    """Targets a single unit within a given range."""

    in_range: int


@dataclass
class TargetArea(Targeting):
    """Targets an area on the grid."""

    area: "Area"


# ==========================================
# EFFECTS
# ==========================================


@dataclass
class Effect:
    """Base class for all ability effects."""

    pass


@dataclass
class DamageEffect(Effect):
    amount: int
    undefendable: bool = False
    irreducible: bool = False


@dataclass
class HealEffect(Effect):
    amount: int


@dataclass
class MoveEffect(Effect):
    distance: int


@dataclass
class ApplyModifierEffect(Effect):
    modifier_class: type


# ==========================================
# ABILITY
# ==========================================


@dataclass
class Ability:
    name: str
    targeting: Targeting
    effects: List[Effect] = field(default_factory=list)
    owner: Optional["Entity"] = None
    is_default: bool = False
    cost_standard_action: bool = True
    cost_move_action: bool = False
    target: Optional[Union["Entity", "Point"]] = (
        None  # For pre-determined targets like with Taunt
    )

    def get_hash(self) -> float:
        import hashlib

        owner_set = getattr(self.owner, "set", "unknown") if self.owner else "unknown"
        owner_name = getattr(self.owner, "name", "unknown") if self.owner else "unknown"
        key = f"{owner_set}__{owner_name}__{self.name}"
        hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
        return float(hash_int % 10000) / 100.0
