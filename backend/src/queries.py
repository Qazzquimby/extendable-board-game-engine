from typing import List, Optional, TYPE_CHECKING, Type, TypeVar, Generic

from events import EventPhase
from mod_value import ModInt

if TYPE_CHECKING:
    from abilities import Ability
    from modifiers import Token
    from entities import Entity
    from aimings import AimingResult
    from engine import Engine


QueryResultT = TypeVar("QueryResultT")


class Query(Generic[QueryResultT]):
    def __init__(self, subject: "Entity", base_result: QueryResultT):
        self.subject_id = subject.id
        self.result: QueryResultT = base_result

    def resolve(self, engine: "Engine") -> QueryResultT:
        engine.router.publish(engine=engine, event=self, phase=EventPhase.QUERY)
        return self.result


class QueryIsAlive(Query[bool]):
    def __init__(self, subject: "Entity"):
        super().__init__(
            subject=subject,
            base_result=subject.pos is not None and subject.hp > 0,
        )


class QueryRoll(Query[int]):
    def __init__(self, rng, subject: "Entity"):
        super().__init__(subject=subject, base_result=rng.randint(1, 6))


class QueryHasArmor(Query[bool]):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject, base_result=False)


class QueryLegalAimings(Query[List["AimingResult"]]):
    def __init__(
        self,
        subject: "Entity",
        ability: "Ability",
        base_result: List["AimingResult"],
    ):
        super().__init__(subject=subject, base_result=base_result)
        self.ability = ability


class QueryAvoidInclusion(Query[bool]):
    def __init__(
        self,
        subject: "Entity",
        ability: "Ability",
    ):
        super().__init__(subject=subject, base_result=False)
        self.ability = ability


class QueryLegalActions(Query[List["Ability"]]):
    def __init__(self, subject: "Entity", base_result: List["Ability"]):
        super().__init__(subject=subject, base_result=base_result)


class QueryCanMove(Query[bool]):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject, base_result=True)


class QuerySpeed(Query[ModInt]):
    def __init__(self, subject: "Entity"):
        super().__init__(subject=subject, base_result=ModInt(subject._speed))


class QueryDefense(Query[ModInt]):
    def __init__(
        self,
        subject: "Entity",
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
        result: int = 0,
    ):
        super().__init__(subject=subject, base_result=ModInt(result))
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
        super().__init__(subject=subject, base_result=ModInt(result))
        self.attack_source = attack_source
        self.ability = ability


class GetTokenCountQuery(Query[int]):
    def __init__(self, subject: "Entity", token_class: Type["Token"]):
        self.token_class = token_class

        base_result = 0
        for modifier in subject.modifiers:
            if isinstance(modifier, self.token_class):
                modifier: "Token"
                base_result = modifier.amount
                break

        super().__init__(subject=subject, base_result=base_result)
