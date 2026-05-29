import json
import random
from pathlib import Path
from typing import List, Type, Union

from tqdm import tqdm

from engine import RandomAgent, Engine
from events import DamageEvent
from grid import Grid
from heroes import MeleeHero, RangedHero
from point import Point
from abilities import DamageInstruction, HealInstruction
from schemas import ActionState, LogEntry, GameLog, ActionSim


from ai.mcts import MCTSAgent

# def run_game(agent: MCTSAgent) -> GameLog:
#     engine = Engine(grid=Grid(6, 6), agents={0: agent, 1: agent})
#
#     # Randomize teams slightly
#     team_0_classes: List[Type[Union[MeleeHero, RangedHero]]] = [
#         random.choice([MeleeHero, RangedHero]) for _ in range(2)
#     ]
#     team_1_classes: List[Type[Union[MeleeHero, RangedHero]]] = [
#         random.choice([MeleeHero, RangedHero]) for _ in range(2)
#     ]
#
#     team_0_classes[0](engine=engine, pos=Point(0, 0), team=0)
#     team_0_classes[1](engine=engine, pos=Point(0, 1), team=0)
#
#     team_1_classes[0](engine=engine, pos=Point(5, 5), team=1)
#     team_1_classes[1](engine=engine, pos=Point(5, 4), team=1)
#
#     logs: List[LogEntry] = []
#
#     winner_team = None
#     engine.next_turn()
#     while engine.round_num <= 6:
#         actor = engine.active_entity
#         if actor.hp <= 0:
#             engine.next_turn()
#             continue
#
#         before_state = engine.to_model()
#         plausible_actions = generate_plausible_move_and_action(actor, engine)
#
#         simulations = []
#         for p_action in plausible_actions:
#             # todo use ability.execute()
#             sim_engine = engine.copy()
#             sim_actor = next(e for e in sim_engine.entities if e.id == actor.id)
#             sim_target = next(
#                 (
#                     e
#                     for e in sim_engine.entities
#                     if p_action.target and e.id == p_action.target.id
#                 ),
#                 None,
#             )
#
#             sim_actor.pos = p_action.move_pos
#             for instruction in p_action.ability.instructions:
#                 if isinstance(instruction, DamageInstruction):
#                     DamageEvent(
#                         engine=sim_engine,
#                         source=sim_actor,
#                         subject=sim_target,
#                         amount=instruction.amount,
#                     ).resolve()
#                 elif isinstance(instruction, HealInstruction):
#                     HealEvent(
#                         engine=sim_engine,
#                         subject=sim_target,
#                         amount=instruction.amount,
#                     ).resolve()
#
#             sim_time_up = sim_engine.round_num >= 6
#             sim_t0 = [e for e in sim_engine.entities if e.team == 0 and e.hp > 0]
#             sim_t1 = [e for e in sim_engine.entities if e.team == 1 and e.hp > 0]
#             sim_done = sim_time_up or not sim_t0 or not sim_t1
#
#             sim_winner = None
#             if sim_done:
#                 if len(sim_t0) > len(sim_t1):
#                     sim_winner = 0
#                 elif len(sim_t1) > len(sim_t0):
#                     sim_winner = 1
#
#             sim_path = sim_engine.grid.get_path(actor.pos, p_action.move_pos)
#             simulations.append(
#                 ActionSim(
#                     action=ActionState(
#                         actor=sim_actor.id,
#                         move_pos=p_action.move_pos,
#                         path=sim_path,
#                         target=sim_target.id if sim_target else None,
#                         ability=p_action.ability.name,
#                         movement_name=p_action.movement_name,
#                     ),
#                     after_state=sim_engine.to_model(),
#                     done=sim_done,
#                     winner_team=sim_winner,
#                 )
#             )
#
#         chosen_action = agent.select_action(choices=plausible_actions)
#
#         path = engine.grid.get_path(actor.pos, chosen_action.move_pos)
#
#         # Execute actual action using environment step
#         engine.step(chosen_action)
#
#         # Check win condition
#         time_up = engine.round_num >= 6
#         team_0_living_members = [e for e in engine.entities if e.team == 0 and e.hp > 0]
#         team_1_living_members = [e for e in engine.entities if e.team == 1 and e.hp > 0]
#         done = time_up or not team_0_living_members or not team_1_living_members
#         if done:
#             if len(team_0_living_members) > len(team_1_living_members):
#                 winner_team = 0
#             elif len(team_1_living_members) > len(team_0_living_members):
#                 winner_team = 1
#
#         target_id = None
#         if chosen_action.ability.name != "Do nothing" and chosen_action.target:
#             target_id = chosen_action.target.id
#
#         log_entry = LogEntry(
#             before_state=before_state,
#             action=ActionState(
#                 actor=actor.id,
#                 move_pos=chosen_action.move_pos,
#                 path=path,
#                 target=target_id,
#                 ability=chosen_action.ability.name,
#                 movement_name=chosen_action.movement_name,
#             ),
#             after_state=engine.to_model(),
#             done=done,
#             simulations=simulations,
#         )
#         logs.append(log_entry)
#
#         if done:
#             break
#
#     return GameLog(winner_team=winner_team, logs=logs)


def setup_game():
    engine = Engine(grid=Grid(4, 4), agents={0: agent, 1: agent})
    team_0_classes: List[Type[Union[MeleeHero, RangedHero]]] = [
        random.choice([MeleeHero, RangedHero]) for _ in range(2)
    ]
    team_1_classes: List[Type[Union[MeleeHero, RangedHero]]] = [
        random.choice([MeleeHero, RangedHero]) for _ in range(2)
    ]

    team_0_classes[0](engine=engine, pos=Point(0, 0), team=0)
    team_0_classes[1](engine=engine, pos=Point(0, 1), team=0)

    team_1_classes[0](engine=engine, pos=Point(5, 5), team=1)
    team_1_classes[1](engine=engine, pos=Point(5, 4), team=1)
    return engine


if __name__ == "__main__":
    agent = RandomAgent()  # MCTSAgent(num_simulations=50)
    all_games = []
    num_games = 10  # _000
    existing_game_logs = Path("../game_logs").glob("*.json")
    existing_game_log_Numbers = [int(f.stem) for f in existing_game_logs]

    file_idx = max(existing_game_log_Numbers) + 1 if existing_game_log_Numbers else 0
    for i in tqdm(range(num_games)):
        engine = setup_game()
        game_log = engine.run_game()
        all_games.append(game_log)

    #     if len(all_games) == 10:
    #         filename = f"../game_logs/{file_idx}.json"
    #         with open(filename, "w") as f:
    #             json.dump(
    #                 [game.model_dump(mode="json") for game in all_games], f, indent=2
    #             )
    #         all_games = []
    #         file_idx += 1
    #
    # if all_games:
    #     filename = f"game_logs/{file_idx}.json"
    #     with open(filename, "w") as f:
    #         json.dump([game.model_dump(mode="json") for game in all_games], f, indent=2)
    #     print(f"Saved {len(all_games)} games to {filename}")
