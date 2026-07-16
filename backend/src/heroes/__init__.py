from aimings import TargetEntity
from engine import Engine
from abilities import Ability
from instruction_library import DamageInstruction
from entities import Hero
from point import Point


class MeleeHero(Hero):
    def __init__(self, engine: Engine, pos: Point, team: int):
        super().__init__(
            engine=engine, name="Melee Hero", hp=12, speed=2, pos=pos, team=team
        )
        self.abilities.append(
            Ability(
                name="Melee Attack",
                text="Target in range 1: 3 damage",
                aiming=TargetEntity(in_range=1),
                instructions=[DamageInstruction(amount=3)],
                is_default=True,
                owner_id=self.id,
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
                text="Target in range 3: 2 damage",
                aiming=TargetEntity(in_range=3),
                instructions=[DamageInstruction(amount=2)],
                is_default=True,
                owner_id=self.id,
            )
        )
