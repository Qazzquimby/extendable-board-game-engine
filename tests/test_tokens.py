from engine import Token, TurnEndEvent, QueryLegalActions, DamageEvent
from engine import before, query
from abilities import (
    Ability,
    DamageInstruction,
    RemoveTokenInstruction,
)
from targeting import TargetSelf, TargetUnit


class PoisonToken(Token):
    @before(TurnEndEvent)
    def take_poison_damage(self, event: TurnEndEvent):
        DamageEvent(
            event.engine, source=None, target=self.owner, amount=self.amount
        ).resolve()
        self.remove(1)


venom_strike = Ability(
    name="Venom Strike",
    aiming=TargetUnit(in_range=1),
    instructions=[
        # Dynamic Callable damage formula evaluated exactly at Execution Time
        DamageInstruction(
            amount=lambda ctx: 2 + (ctx.target.get_token_count(PoisonToken) * 3)
        )
    ],
)


class RootToken(Token):
    @query(QueryLegalActions)
    def grant_rip_roots(self, q: QueryLegalActions):
        ability = Ability(
            name="Rip Free",
            aiming=TargetSelf(),
            instructions=[RemoveTokenInstruction(token_class=RootToken, amount=1)],
            cost_standard_action=True,
            owner=self.owner,
        )
        q.result.append(ability)
