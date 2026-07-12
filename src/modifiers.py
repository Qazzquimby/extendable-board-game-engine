from dataclasses import field, dataclass
from typing import TYPE_CHECKING

from events import query, before
from event_library import TurnEndEvent
from logger import log
from queries import QueryCanMove, QueryLegalActions, QuerySpeed, QueryHasArmor
from valence import Valence

from util import EntityId

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity, Summon


@dataclass(kw_only=True)
class Modifier:
    text: str = field(default=False, init=False)
    valence: Valence = field(default=False, init=False)
    owner_id: EntityId = field(init=False)
    name: str = field(init=False)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.name = cls.__name__

    def __str__(self):
        return self.name

    def log_trigger(self, engine, event):
        owner = engine.get_entity_by_id(self.owner_id)
        return log(f"{event.__class__.__name__} triggered {owner.name}'s {self.name}.")


class SummonModifier(Modifier):
    owner: "Summon" = field(init=False)
    valence: Valence = Valence.GOOD


@dataclass(kw_only=True)
class Token(Modifier):
    amount: int = 1

    def add(self, amount: int) -> None:
        self.amount += amount

    def remove(self, engine: "Engine", amount: int) -> None:
        self.amount -= amount
        if self.amount <= 0:
            owner = engine.get_entity_by_id(self.owner_id)
            owner.remove_modifier(engine=engine, modifier=self)

    def __str__(self):
        return f"{self.name} x {self.amount}"


class ClearAtEndOfTurnMixin:
    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, engine: "Engine", event: TurnEndEvent) -> None:
        owner = engine.get_entity_by_id(self.owner_id)
        if self in owner.modifiers:
            owner.remove_modifier(engine=engine, modifier=self)


class Immobile(Modifier):
    valence = Valence.BAD

    @query(QueryCanMove)
    def prevent_move(self, engine: "Engine", q: QueryCanMove) -> None:
        q.result = False


class ImmobileToken(Immobile, Token, ClearAtEndOfTurnMixin):
    pass


class Stunned(Modifier):
    valence = Valence.BAD

    @query(QueryCanMove)
    def prevent_move(self, engine: "Engine", q: QueryCanMove) -> None:
        q.result = False

    @query(QueryLegalActions)
    def prevent_actions(self, engine: "Engine", q: QueryLegalActions) -> None:
        q.result = []


class StunnedToken(Stunned, Token, ClearAtEndOfTurnMixin):
    pass


class Slow(Modifier):
    valence = Valence.BAD

    def __init__(self, amount: int):
        self.amount = amount

    @query(QuerySpeed)
    def reduce_speed(self, engine: "Engine", q: QuerySpeed) -> None:
        q.result.add(-self.amount)


class SlowToken(Slow, Token, ClearAtEndOfTurnMixin):
    pass


class Armor(Modifier):
    valence = Valence.GOOD

    @query(QueryHasArmor)
    def grant_armor(self, engine: "Engine", q: QueryHasArmor) -> None:
        q.result = True


class ArmorToken(Armor, Token, ClearAtEndOfTurnMixin):
    pass
