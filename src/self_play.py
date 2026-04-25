import random
from typing import List, Type

import torch

from engine import Engine, Entity
from grid import Grid
from heroes import MeleeHero, RangedHero
from ai_agent import (
    AIAgent,
    encode_state,
)
from point import Point


def run_game():
    engine = Engine(grid=Grid(20, 20))

    # Randomize teams slightly
    team_0_classes: List[Type[Entity]] = [
        random.choice([MeleeHero, RangedHero]) for _ in range(2)
    ]
    team_1_classes: List[Type[Entity]] = [
        random.choice([MeleeHero, RangedHero]) for _ in range(2)
    ]

    team_0_classes[0](engine=engine, name="H1", hp=10, speed=3, pos=Point(0, 0), team=0)
    team_0_classes[1](engine=engine, name="H2", hp=10, speed=3, pos=Point(0, 1), team=0)
    team_1_classes[0](engine=engine, name="H3", hp=10, speed=3, pos=Point(9, 9), team=1)
    team_1_classes[1](engine=engine, name="H4", hp=10, speed=3, pos=Point(9, 8), team=1)

    agent = AIAgent()
    logs = []

    engine.next_turn()
    while engine.round_num < 50:
        actor = engine.active_entity
        if actor.hp <= 0:
            engine.next_turn()
            continue

        chosen_action = agent.select_action(actor=actor, engine=engine)

        # Execute action (stub implementation)
        actor.pos = chosen_action.move_pos
        # todo actually perform the ability

        # Check win condition
        team_0_alive = any(e.hp > 0 for e in engine.entities if e.team == 0)
        team_1_alive = any(e.hp > 0 for e in engine.entities if e.team == 1)
        done = not (team_0_alive and team_1_alive)

        reward = 0.0
        if done:
            if team_0_alive:
                reward = 1.0 if actor.team == 0 else -1.0
            elif team_1_alive:
                reward = 1.0 if actor.team == 1 else -1.0

        next_state_tensor = encode_state(engine)
        # todo, no, we want interpretable logs for playback. Should be saved to json files, not pt
        logs.append(
            (
                state_tensor,
                action_tensors,
                chosen_idx,
                next_state_tensor,
                reward,
                done,
            )
        )

        if done:
            break

        engine.next_turn()

    return logs


if __name__ == "__main__":
    all_logs = []
    num_games = 10
    for i in range(num_games):
        print(f"Playing game {i+1}/{num_games}...")
        all_logs.extend(run_game())

    torch.save(all_logs, "game_logs.pt")
    print(f"Saved {len(all_logs)} steps to game_logs.pt")
