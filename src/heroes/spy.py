from aimings import TargetEntity
from engine import (
    Engine,
    Hero,
    ActionContext,
)
from abilities import (
    Ability,
    DamageInstruction,
    RemoveTokenInstruction,
)
from point import Point


class Spy(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(engine=engine, name="Spy", hp=6, speed=3, pos=pos, team=team)
        # TODO:
        #  Missing query_is_ally
        #  Missing Redirect ability target
        #  Missing Reactions to enemy movement
        #  Missing Removal from board and hidden info (Face down markers)
        #  Missing Damage over Time (DoT)
        #  Missing Damage Resistance and conditional trigger prevention (Deadringer)

        def revolver_damage(ctx: ActionContext) -> int:
            if ctx.target.get_token_count(KillCounter) > 0:
                return 4
            return 2

        self.abilities.append(
            Ability(
                name="Revolver",
                aiming=TargetEntity(),
                instructions=[
                    DamageInstruction(amount=revolver_damage, irreducible=True),
                    RemoveTokenInstruction(token_class=KillCounter, amount=1),
                ],
                is_default=True,
                owner_id=self.id,
            )
        )
