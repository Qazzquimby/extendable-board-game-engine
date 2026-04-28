from engine import Entity, Engine
from abilities import Ability, DamageEffect, TargetUnit, TargetSelf
from point import Point


class MeleeHero(Entity):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Melee Hero", hp=10, speed=3, pos=pos, team=team
        )
        self.abilities.append(
            Ability(
                name="Melee Attack",
                targeting=TargetUnit(in_range=1),
                effects=[DamageEffect(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(name="Do Nothing", targeting=TargetSelf(), effects=[], owner=self)
        )


class RangedHero(Entity):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Ranged Hero", hp=6, speed=3, pos=pos, team=team
        )
        self.abilities.append(
            Ability(
                name="Ranged Attack",
                targeting=TargetUnit(in_range=3),
                effects=[DamageEffect(amount=2)],
                is_default=True,
                owner=self,
            )
        )
        self.abilities.append(
            Ability(name="Do Nothing", targeting=TargetSelf(), effects=[], owner=self)
        )
