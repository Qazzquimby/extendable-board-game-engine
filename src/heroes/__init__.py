from aimings import TargetEntity, TargetSelf
from engine import Engine
from abilities import Ability, DamageInstruction
from entities import Hero
from point import Point


class MeleeHero(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Melee Hero", hp=10, speed=3, pos=pos, team=team
        )
        self.abilities.append(
            Ability(
                name="Melee Attack",
                aiming=TargetEntity(in_range=1),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )


class RangedHero(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Ranged Hero", hp=4, speed=3, pos=pos, team=team
        )
        self.abilities.append(
            Ability(
                name="Ranged Attack",
                aiming=TargetEntity(in_range=3),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner=self,
            )
        )
