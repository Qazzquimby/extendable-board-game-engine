import torch

from ai_agent import (
    GameStateEncoder,
    generate_plausible_actions,
    PlausibleAction,
)
from engine import Engine, Entity, Ability, AbilityStep
from grid import Grid
from point import Point


def test_game_state_encoder_transformer():
    encoder = GameStateEncoder(hidden_dim=32)
    # 10 entities * 5 features = 50
    dummy_state = torch.rand(50)
    output = encoder(dummy_state)

    assert output.shape == (1, 32)

    # Test batching
    dummy_batch = torch.rand(5, 50)
    output_batch = encoder(dummy_batch)
    assert output_batch.shape == (5, 32)


def test_ability_hashing():
    engine = Engine()
    warrior = Entity(
        engine=engine, name="Warrior", hp=10, speed=3, pos=Point(0, 0), team=1
    )
    mage = Entity(engine=engine, name="Mage", hp=10, speed=3, pos=Point(1, 1), team=1)

    ability1 = Ability(name="Slash", steps=[], owner=warrior)
    ability2 = Ability(name="Shoot", steps=[], owner=warrior)
    ability3 = Ability(name="Slash", steps=[], owner=mage)

    hash1 = ability1.get_hash()
    hash2 = ability2.get_hash()
    hash3 = ability3.get_hash()

    assert isinstance(hash1, float)
    assert hash1 != hash2
    assert hash1 != hash3
    assert hash1 == ability1.get_hash()  # Deterministic


def test_generate_plausible_actions():
    engine = Engine(grid=Grid(100, 100))

    actor = Entity(engine, "Hero1", hp=10, speed=3, pos=Point(0, 0), team=1)
    actor.abilities.append(Ability(name="Strike", steps=[AbilityStep(attack_range=2)]))

    enemy = Entity(engine, "Enemy1", hp=10, speed=3, pos=Point(5, 5), team=2)
    ally = Entity(engine, "Ally1", hp=10, speed=3, pos=Point(2, 2), team=1)

    actions = generate_plausible_actions(actor, engine)

    assert len(actions) > 0
    assert all(isinstance(a, PlausibleAction) for a in actions)

    # Check if heuristics generated expected moves
    moves = [a.move_pos for a in actions]
    # The actor is at (0,0) with default speed 3, so it can only reach points where abs(x)+abs(y) <= 3.
    # Enemy is at (5,5). The closest reachable point to (5,5) is (3,0), (2,1), (1,2), or (0,3).
    # We just assert that some valid moves were generated and they are within speed limits.
    for move in moves:
        assert move.get_distance(actor.pos) <= 3
