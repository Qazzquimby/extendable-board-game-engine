from dataclasses import field, dataclass
from typing import TYPE_CHECKING

from events import query, before, TurnEndEvent
from logger import log
from queries import QueryCanMove, QueryLegalActions, QuerySpeed, QueryHasArmor
from valence import Valence

if TYPE_CHECKING:
    from entities import Entity, Summon


@dataclass(kw_only=True)
class Modifier:
    text: str = field(default=False, init=False)
    valence: Valence = field(default=False, init=False)
    owner: "Entity" = field(init=False)
    name: str = field(init=False)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.name = cls.__name__

    def __str__(self):
        return self.name

    def log_trigger(self, event):
        return log(
            f"{event.__class__.__name__} triggered {self.owner.name}'s {self.name}."
        )


class SummonModifier(Modifier):
    owner: "Summon" = field(init=False)
    valence: Valence = Valence.GOOD


class Token(Modifier):
    def __init__(self, amount: int = 1):
        self.amount = amount

    def add(self, amount: int) -> None:
        self.amount += amount

    def remove(self, amount: int) -> None:
        self.amount -= amount
        if self.amount <= 0:
            self.owner.remove_modifier(self)

    def __str__(self):
        return f"{self.name} x {self.amount}"


class ClearAtEndOfTurnMixin:
    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, event: TurnEndEvent) -> None:
        if self in self.owner.modifiers:
            self.owner.remove_modifier(self)


class Immobile(Modifier):
    valence = Valence.BAD

    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False


class ImmobileToken(Immobile, Token, ClearAtEndOfTurnMixin):
    pass


class Stunned(Modifier):
    valence = Valence.BAD

    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False

    @query(QueryLegalActions)
    def prevent_actions(self, q: QueryLegalActions) -> None:
        q.result = []


class StunnedToken(Stunned, Token, ClearAtEndOfTurnMixin):
    pass


class Slow(Modifier):
    valence = Valence.BAD

    def __init__(self, amount: int):
        self.amount = amount

    @query(QuerySpeed)
    def reduce_speed(self, q: QuerySpeed) -> None:
        q.result.add(-self.amount)


class SlowToken(Slow, Token, ClearAtEndOfTurnMixin):
    pass


class Armor(Modifier):
    valence = Valence.GOOD

    @query(QueryHasArmor)
    def grant_armor(self, q: QueryHasArmor) -> None:
        q.result = True


class ArmorToken(Armor, Token, ClearAtEndOfTurnMixin):
    pass
