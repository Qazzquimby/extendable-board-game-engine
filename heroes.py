from engine import Entity, Engine, Ability, AbilityStep

class MeleeHero(Entity):
    def __init__(self, engine: Engine, name: str, hp: int, pos: tuple[int, int], team: int):
        super().__init__(engine, name, hp, pos, team)
        self.abilities.append(Ability(name="Melee Attack", steps=[AbilityStep(attack_range=1)], is_default=True))


class RangedHero(Entity):
    def __init__(self, engine: Engine, name: str, hp: int, pos: tuple[int, int], team: int):
        super().__init__(engine, name, hp, pos, team)
        self.abilities.append(Ability(name="Ranged Attack", steps=[AbilityStep(attack_range=3)], is_default=True))
