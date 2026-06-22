from engine import Engine
from entities import Entity
from grid import Grid
from point import Point
from abilities import Ability, ActionCost, DamageInstruction, HealInstruction
from aimings import TargetSelf


def test_deterministic_step_same_hash():
    grid = Grid(width=3, height=3)
    engine1 = Engine(grid=grid)

    heal = Ability(
        name="Heal",
        aiming=TargetSelf(),
        action_cost=ActionCost.STANDARD,
        instructions=[HealInstruction(amount=1)],
    )

    react = Ability(
        name="ReactHeal",
        aiming=TargetSelf(),
        action_cost=ActionCost.INSTANT,
        instant_speed=0,
        max_charges=1,
        instructions=[HealInstruction(amount=1)],
    )

    e1 = Entity(engine=engine1, name="Hero1", hp=10, speed=3, pos=Point(0, 0), team=0)
    e1.activator = e1
    e1.abilities = [heal]

    e2 = Entity(engine=engine1, name="Hero2", hp=10, speed=3, pos=Point(1, 0), team=1)
    e2.activator = e2
    e2.abilities = [react]

    engine1.add_entity(e1)
    engine1.add_entity(e2)
    engine1.finalize_setup()

    engine1.next_turn()

    engine2 = engine1.copy()

    assert engine1.hash() == engine2.hash()

    actions1 = engine1.get_legal_actions()
    assert len(actions1) > 0

    action_to_take = actions1[0]
    action_idx = 0

    engine1.rng.stochastic_flag = False
    engine1.step(action_to_take, action_idx=action_idx)

    actions2 = engine2.get_legal_actions()
    action2_to_take = actions2[action_idx]

    engine2.rng.stochastic_flag = False
    engine2.step(action2_to_take, action_idx=action_idx)

    assert engine1._get_hash_info() == engine2._get_hash_info()
    assert engine1.hash() == engine2.hash()


def test_reaction_choice_same_hash():
    grid = Grid(width=3, height=3)
    engine1 = Engine(grid=grid)

    heal = Ability(
        name="Heal",
        aiming=TargetSelf(),
        action_cost=ActionCost.STANDARD,
        instructions=[HealInstruction(amount=2)],
    )

    react = Ability(
        name="ReactHeal",
        aiming=TargetSelf(),
        action_cost=ActionCost.INSTANT,
        instant_speed=0,
        max_charges=1,
        instructions=[HealInstruction(amount=1)],
    )

    e1 = Entity(engine=engine1, name="Hero1", hp=10, speed=3, pos=Point(0, 0), team=0)
    e1.activator = e1
    e1.abilities = [heal]

    e2 = Entity(engine=engine1, name="Hero2", hp=10, speed=3, pos=Point(1, 0), team=1)
    e2.activator = e2
    e2.abilities = [react]
    engine1.finalize_setup()
    engine1.next_turn()

    class MockAgent:
        def __init__(self):
            self.choices_seen = []

        def choose(self, choices):
            self.choices_seen.append(choices)
            return 0

    engine1.agents = {0: MockAgent(), 1: MockAgent()}
    engine2 = engine1.copy()
    engine2.agents = {0: MockAgent(), 1: MockAgent()}

    actions1 = engine1.get_legal_actions()
    strike_action = next(a for a in actions1 if a.ability.name == "Heal")
    strike_idx = actions1.index(strike_action)

    engine1.step(strike_action, action_idx=strike_idx)

    actions2 = engine2.get_legal_actions()
    strike_action2 = actions2[strike_idx]
    engine2.step(strike_action2, action_idx=strike_idx)

    assert engine1._get_hash_info() == engine2._get_hash_info()
    assert engine1.hash() == engine2.hash()
