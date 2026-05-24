from typing import List, Optional, TYPE_CHECKING

from abilities import Ability
from events import Query
from mod_value import ModInt

if TYPE_CHECKING:
    from entities import Entity
    from aimings import AimingResult


class QueryIsAlive(Query[bool]):
    def __init__(self, subject: "Entity"):
        super().__init__(
            subject=subject, result=subject.pos is not None and subject.hp > 0
        )


class QueryHasArmor(Query[bool]):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject, result=False)


class QueryLegalAimings(Query["AimingResult"]):
    def __init__(
        self, subject: "Entity", ability: "Ability", result: List["AimingResult"]
    ):
        super().__init__(subject=subject, result=result)
        self.ability = ability


class QueryLegalActions(Query[List[Ability]]):
    def __init__(self, subject: "Entity", result: List[Ability]):
        super().__init__(subject=subject, result=result)


class QueryCanMove(Query[bool]):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject, result=True)


class QuerySpeed(Query[ModInt]):
    def __init__(self, subject: "Entity", result: int):
        super().__init__(subject=subject, result=result)


class QueryDefense(Query[ModInt]):
    def __init__(
        self,
        subject: "Entity",
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
        result: int = 0,
    ):
        super().__init__(subject=subject, result=ModInt(result))
        self.attack_source = attack_source
        self.ability = ability


class QueryCrit(Query[ModInt]):
    def __init__(
        self,
        subject: "Entity",
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
        result: int = 0,
    ):
        super().__init__(subject=subject, result=ModInt(result))
        self.attack_source = attack_source
        self.ability = ability
