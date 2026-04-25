from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine import Entity, Engine


@dataclass
class AbilityStep:
    """Base class for all ability effects."""

    pass


# todo, what, you're saying every step will choose its own target? Every step has a range and picks someone?
#  Please find a reasonable implementation for scripting abilities such that the abilities in the sample characters can be faithfully written.


@dataclass
class DamageStep(AbilityStep):
    amount: int
    attack_range: int = 1
    undefendable: bool = False
    irreducible: bool = False


@dataclass
class HealStep(AbilityStep):
    amount: int
    range: int = 1


@dataclass
class MoveStep(AbilityStep):
    distance: int


@dataclass
class ApplyModifierStep(AbilityStep):
    modifier_class: type
    range: int = 1


@dataclass
class Ability:
    name: str
    steps: List[AbilityStep] = field(default_factory=list)
    owner: Optional["Entity"] = None
    is_default: bool = False
    cost_standard_action: bool = True
    cost_move_action: bool = False
    target: Optional["Entity"] = None

    def get_hash(self) -> float:
        import hashlib

        owner_set = getattr(self.owner, "set", "unknown") if self.owner else "unknown"
        owner_name = getattr(self.owner, "name", "unknown") if self.owner else "unknown"
        key = f"{owner_set}__{owner_name}__{self.name}"
        hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
        return float(hash_int % 10000) / 100.0
