from engine import Token, TurnEndEvent, QueryLegalActions, DamageEvent
from engine import before, query
from abilities import Ability, DamageEffect, TargetUnit, RemoveTokenEffect, TargetSelf


class PoisonToken(Token):
    @before(TurnEndEvent)  # Fired automatically only when owner ends turn
    def take_poison_damage(self, event: TurnEndEvent):
        DamageEvent(
            event.engine, source=None, target=self.owner, amount=self.amount
        ).resolve()
        self.remove(1)


# Attack scaling dynamically off tokens (Resolves Requirement #1)
venom_strike = Ability(
    name="Venom Strike",
    targeting=TargetUnit(in_range=1),
    effects=[
        # Dynamic Callable damage formula evaluated exactly at Execution Time
        DamageEffect(
            amount=lambda ctx: 2 + (ctx.target.get_token_count(PoisonToken) * 3)
        )
    ],
)


# 2. Token grants an ability (Resolves Requirement #2)
class RootToken(Token):
    @query(QueryLegalActions)
    def grant_rip_roots(self, q: QueryLegalActions):
        ability = Ability(
            name="Rip Free",
            targeting=TargetSelf(),
            effects=[RemoveTokenEffect(token_class=RootToken, amount=1)],
            cost_standard_action=True,
            owner=self.owner,
        )
        q.result.append(ability)
