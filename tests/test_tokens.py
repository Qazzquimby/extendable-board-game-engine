from aimings import TargetSelf, TargetEntity
from modifiers import Token
from queries import QueryLegalActions
from event_library import TurnEndEvent, DamageEvent
from engine import before, query
from abilities import (
    Ability,
    DamageInstruction,
    RemoveTokenInstruction,
)


class PoisonToken(Token):
    @before(TurnEndEvent)
    def take_poison_damage(self, engine: "Engine", event: TurnEndEvent):
        DamageEvent(
            event.engine, source=None, subject=self.owner, amount=self.amount
        ).resolve()
        self.remove(1)


venom_strike = Ability(
    name="Venom Strike",
    aiming=TargetEntity(in_range=1),
    instructions=[
        # Dynamic Callable damage formula evaluated exactly at Execution Time
        DamageInstruction(
            amount=lambda ctx: 2 + (ctx.subject.get_token_count(PoisonToken) * 3)
        )
    ],
)


class RootToken(Token):
    @query(QueryLegalActions)
    def grant_rip_roots(self, engine: "Engine", q: QueryLegalActions):
        ability = Ability(
            name="Rip Free",
            aiming=TargetSelf(),
            instructions=[RemoveTokenInstruction(token_class=RootToken, amount=1)],
            owner=self.owner,
        )
        q.result.append(ability)
