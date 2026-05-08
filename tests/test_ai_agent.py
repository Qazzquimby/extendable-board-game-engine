import torch

from ai_agent import (
    GameStateEncoder,
    generate_plausible_actions,
    PlausibleAction,
)
from abilities import Ability, DamageInstruction
from targeting import TargetUnit
from engine import Engine, Entity
from grid import Grid
from point import Point


def test_game_state_encoder_transformer():
    encoder = GameStateEncoder(entity_vocab_size=128, emb_size=32)
    # 10 entities * 5 features = 50
    dummy_state = torch.rand((10, 20, 6))
    pooled, transformed = encoder(dummy_state)

    assert pooled.shape == (10, 32)
    assert transformed.shape == (10, 20, 32)


def test_generate_plausible_actions():
    engine = Engine(grid=Grid(100, 100))

    actor = Entity(engine, "Hero1", hp=10, speed=3, pos=Point(0, 0), team=1)
    actor.abilities.append(
        Ability(
            name="Strike",
            targeting=TargetUnit(in_range=2),
            instructions=[DamageInstruction(amount=5)],
        )
    )

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
