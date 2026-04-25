from engine import Entity, Engine
from abilities import Ability, DamageStep

class MeleeHero(Entity):
    def __init__(self, engine: Engine, name: str, hp: int, pos: tuple[int, int], team: int):
        super().__init__(engine, name, hp, pos, team)
        self.abilities.append(Ability(name="Melee Attack", steps=[DamageStep(amount=2, attack_range=1)], is_default=True, owner=self))
        self.abilities.append(Ability(name="Do Nothing", steps=[], owner=self))


class RangedHero(Entity):
    def __init__(self, engine: Engine, name: str, hp: int, pos: tuple[int, int], team: int):
        super().__init__(engine, name, hp, pos, team)
        self.abilities.append(Ability(name="Ranged Attack", steps=[DamageStep(amount=2, attack_range=3)], is_default=True, owner=self))
        self.abilities.append(Ability(name="Do Nothing", steps=[], owner=self))
