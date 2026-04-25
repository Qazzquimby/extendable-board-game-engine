from engine import Entity, Engine
from abilities import Ability, DamageEffect, TargetUnit, TargetSelf


class MeleeHero(Entity):
    def __init__(
        self, engine: Engine, name: str, hp: int, pos: tuple[int, int], team: int
    ):
        super().__init__(engine, name, hp, pos, team)
        self.abilities.append(
            Ability(
                name="Melee Attack",
                targeting=TargetUnit(range=1),
                effects=[DamageEffect(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(name="Do Nothing", targeting=TargetSelf(), effects=[], owner=self)
        )


class RangedHero(Entity):
    def __init__(
        self, engine: Engine, name: str, hp: int, pos: tuple[int, int], team: int
    ):
        super().__init__(engine, name, hp, pos, team)
        self.abilities.append(
            Ability(
                name="Ranged Attack",
                targeting=TargetUnit(range=3),
                effects=[DamageEffect(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(name="Do Nothing", targeting=TargetSelf(), effects=[], owner=self)
        )
