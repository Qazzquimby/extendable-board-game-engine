import json
import random
from typing import List, Type

from engine import DamageEvent, Engine, Entity, HealEvent
from grid import Grid
from heroes import MeleeHero, RangedHero
from ai_agent import (
    AIAgent,
    generate_plausible_actions,
)
from point import Point
from abilities import DamageEffect, HealEffect


def run_game(agent: AIAgent) -> List[dict]:
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

    logs = []

    engine.next_turn()
    while engine.round_num < 50:
        actor = engine.active_entity
        if actor.hp <= 0:
            engine.next_turn()
            continue

        before_state_dict = engine.to_dict()
        plausible_actions = generate_plausible_actions(actor, engine)
        if not plausible_actions:
            engine.next_turn()
            continue

        chosen_action, chosen_idx = agent.select_action(
            actor=actor, engine=engine, plausible_actions=plausible_actions
        )

        # Execute action
        actor.pos = chosen_action.move_pos
        ability = chosen_action.ability
        target = chosen_action.target
        for effect in ability.effects:
            if isinstance(effect, DamageEffect):
                DamageEvent(engine, actor, target, effect.amount).resolve()
            elif isinstance(effect, HealEffect):
                HealEvent(engine, target, effect.amount).resolve()

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

        log_entry = {
            "before_state": before_state_dict,
            "action": {
                "actor": actor.name,
                "move_pos": list(chosen_action.move_pos),
                "target": chosen_action.target.name,
                "ability": chosen_action.ability.name,
            },
            "after_state": engine.to_dict(),
            "reward": reward,
            "done": done,
        }
        logs.append(log_entry)

        if done:
            break

        engine.next_turn()

    return logs


if __name__ == "__main__":
    agent = AIAgent()
    all_logs = []
    num_games = 10
    for i in range(num_games):
        print(f"Playing game {i+1}/{num_games}...")
        all_logs.extend(run_game(agent))

    with open("game_logs.json", "w") as f:
        json.dump(all_logs, f, indent=2)
    print(f"Saved {len(all_logs)} steps to game_logs.json")
