import torch
from ai_agent import (
    GameStateEncoder,
    get_ability_hash,
    encode_plausible_action,
    generate_plausible_actions,
    PlausibleAction,
)
from engine import Engine, Entity, Ability, AbilityStep


def test_game_state_encoder_transformer():
    encoder = GameStateEncoder(hidden_dim=32)
    # 10 entities * 5 features = 50
    dummy_state = torch.rand(50)
    output = encoder(dummy_state)

    assert output.shape == (32,)

    # Test batching
    dummy_batch = torch.rand(5, 50)
    output_batch = encoder(dummy_batch)
    assert output_batch.shape == (5, 32)


def test_ability_hashing():
    ability1 = Ability(name="Slash", steps=[])
    ability2 = Ability(name="Shoot", steps=[])

    hash1 = get_ability_hash(ability1, "Warrior")
    hash2 = get_ability_hash(ability2, "Warrior")
    hash3 = get_ability_hash(ability1, "Mage")

    assert isinstance(hash1, float)
    assert hash1 != hash2
    assert hash1 != hash3
    assert hash1 == get_ability_hash(ability1, "Warrior")  # Deterministic


def test_generate_plausible_actions():
    engine = Engine()
    actor = Entity(engine, "Hero1", hp=10, pos=(0, 0), team=1)
    actor.abilities.append(Ability(name="Strike", steps=[AbilityStep(attack_range=2)]))

    enemy = Entity(engine, "Enemy1", hp=10, pos=(5, 5), team=2)
    ally = Entity(engine, "Ally1", hp=10, pos=(2, 2), team=1)

    actions = generate_plausible_actions(actor, engine)

    assert len(actions) > 0
    assert all(isinstance(a, PlausibleAction) for a in actions)

    # Check if heuristics generated expected moves
    moves = [a.move_pos for a in actions]
    # The actor is at (0,0) with default speed 3, so it can only reach points where abs(x)+abs(y) <= 3.
    # Enemy is at (5,5). The closest reachable point to (5,5) is (3,0), (2,1), (1,2), or (0,3).
    # We just assert that some valid moves were generated and they are within speed limits.
    for move in moves:
        assert abs(move[0] - actor.pos[0]) + abs(move[1] - actor.pos[1]) <= 3
