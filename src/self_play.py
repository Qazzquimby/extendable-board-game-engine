import json
import random
from typing import List, Type, Union

from engine import DamageEvent, Engine, Entity, HealEvent
from grid import Grid
from heroes import MeleeHero, RangedHero
from ai_agent import (
    AIAgent,
    generate_plausible_actions,
)
from point import Point
from abilities import DamageEffect, HealEffect
from schemas import LogEntry


def run_game(agent: AIAgent) -> List[LogEntry]:
    engine = Engine(grid=Grid(20, 20))

    # Randomize teams slightly
    team_0_classes: List[Type[Union[MeleeHero, RangedHero]]] = [
        random.choice([MeleeHero, RangedHero]) for _ in range(2)
    ]
    team_1_classes: List[Type[Union[MeleeHero, RangedHero]]] = [
        random.choice([MeleeHero, RangedHero]) for _ in range(2)
    ]

    t0_0 = team_0_classes[0](engine=engine, pos=Point(0, 0), team=0)
    t0_1 = team_0_classes[1](engine=engine, pos=Point(0, 1), team=0)

    t1_0 = team_1_classes[0](engine=engine, pos=Point(9, 9), team=1)
    t1_1 = team_1_classes[1](engine=engine, pos=Point(9, 8), team=1)

    logs: List[LogEntry] = []

    engine.next_turn()
    while engine.round_num < 50:
        actor = engine.active_entity
        if actor.hp <= 0:
            engine.next_turn()
            continue

        before_state_dict = engine.to_dict()
        plausible_actions = generate_plausible_actions(actor, engine)
        chosen_action = agent.select_action(
            actor=actor, engine=engine, plausible_actions=plausible_actions
        )

        path = engine.grid.get_path(actor.pos, chosen_action.move_pos)

        # Execute action
        actor.pos = chosen_action.move_pos
        ability = chosen_action.ability
        target = chosen_action.target
        for effect in ability.effects:
            if isinstance(effect, DamageEffect):
                DamageEvent(
                    engine=engine, source=actor, target=target, amount=effect.amount
                ).resolve()
            elif isinstance(effect, HealEffect):
                HealEvent(engine=engine, target=target, amount=effect.amount).resolve()

        # Check win condition
        time_up = engine.round_num > 6
        team_0_living_members = [e.hp > 0 for e in engine.entities if e.team == 0]
        team_1_living_members = [e.hp > 0 for e in engine.entities if e.team == 1]
        done = time_up or not team_0_living_members or not team_1_living_members

        reward = 0.0
        if done:
            if len(team_0_living_members) > len(team_1_living_members):
                reward = 1.0
            elif len(team_1_living_members) > len(team_0_living_members):
                reward = -1.0
            else:
                reward = 0.0

        target_id = None
        if chosen_action.ability.name != "Do nothing" and chosen_action.target:
            target_id = chosen_action.target.id

        log_entry = LogEntry(
            before_state=before_state_dict,
            action={  # todo use pydantic not dict. Everything should be typed.
                "actor": actor.id,
                "move_pos": chosen_action.move_pos,
                "path": path,
                "target": target_id,
                "ability": chosen_action.ability.name,
                "movement_name": chosen_action.movement_name,
            },
            after_state=engine.to_dict(),
            reward=reward,
            done=done,
        )
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
        json.dump([log.model_dump(mode="json") for log in all_logs], f, indent=2)
    print(f"Saved {len(all_logs)} steps to game_logs.json")
