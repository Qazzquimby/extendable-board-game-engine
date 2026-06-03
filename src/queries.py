from typing import List, Optional, TYPE_CHECKING, Type

from abilities import Ability
from events import Query
from mod_value import ModInt

if TYPE_CHECKING:
    from engine import Engine
    from abilities import Ability
    from modifiers import Token
    from entities import Entity
    from aimings import AimingResult


class QueryIsAlive(Query[bool]):
    def __init__(self, engine: "Engine", subject: "Entity"):
        super().__init__(
            engine=engine,
            subject=subject,
            base_result=subject.pos is not None and subject.hp > 0,
        )


class QueryHasArmor(Query[bool]):
    def __init__(self, engine: "Engine", subject: "Entity"):
        super().__init__(engine=engine, subject=subject, base_result=False)


class QueryLegalAimings(Query["AimingResult"]):
    def __init__(
        self,
        engine: "Engine",
        subject: "Entity",
        ability: "Ability",
        result: List["AimingResult"],
    ):
        super().__init__(engine=engine, subject=subject, base_result=result)
        self.ability = ability


class QueryLegalActions(Query[List[Ability]]):
    def __init__(self, engine: "Engine", subject: "Entity", result: List[Ability]):
        super().__init__(engine=engine, subject=subject, base_result=result)


class QueryCanMove(Query[bool]):
    def __init__(self, engine: "Engine", subject: "Entity"):
        super().__init__(engine=engine, subject=subject, base_result=True)


class QuerySpeed(Query[ModInt]):
    def __init__(self, subject: "Entity", result: int):
        super().__init__(subject=subject, result=result)


class QueryDefense(Query[ModInt]):
    def __init__(
        self,
        engine: "Engine",
        subject: "Entity",
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
        result: int = 0,
    ):
        super().__init__(engine=engine, subject=subject, base_result=ModInt(result))
        self.attack_source = attack_source
        self.ability = ability


class QueryCrit(Query[ModInt]):
    def __init__(
        self,
        engine: "Engine",
        subject: "Entity",
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
        result: int = 0,
    ):
        super().__init__(engine=engine, subject=subject, base_result=ModInt(result))
        self.attack_source = attack_source
        self.ability = ability


class GetTokenCountQuery(Query[int]):
    def __init__(self, engine: "Engine", subject: "Entity", token_class: Type["Token"]):
        self.token_class = token_class

        base_result = 0
        for modifier in self.subject.modifiers:
            if isinstance(modifier, self.token_class):
                modifier: "Token"
                base_result = modifier.amount
                break

        super().__init__(engine=engine, subject=subject, base_result=base_result)
