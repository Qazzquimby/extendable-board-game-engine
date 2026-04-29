import json

import torch

from ai_agent import (
    AIAgent,
    get_entity_features,
    get_plausible_action_features,
    PlausibleAction,
)
from engine import Engine, Entity
from abilities import Ability, Targeting
from schemas import GameLog, EngineState

# First train value prediction
# Then train policy to prefer actions that lead to better value predictions


def state_to_engine(state: EngineState) -> Engine:
    engine = Engine()
    engine.round_num = state.round_num
    engine.current_team = state.current_team

    for ent_state in state.entities:
        ent = Entity(
            engine=engine,
            name=ent_state.name,
            hp=ent_state.hp,
            speed=0,
            pos=ent_state.pos,
            team=ent_state.team,
        )
        ent.id = ent_state.id
        if ent.id == state.active_entity:
            engine.active_entity = ent
    return engine


def train():
    agent = AIAgent()
    agent.load()

    try:
        with open("../game_logs.json", "r") as f:
            logs_data = json.load(f)
    except FileNotFoundError:
        print("No game_logs.json found. Run self_play.py first.")
        return

    for game_dict in logs_data:
        game = GameLog(**game_dict)

        for log in game.logs:
            engine = state_to_engine(log.before_state)
            actor = engine.active_entity
            state_tensor = get_entity_features(engine, actor)

            sim_actions = []
            next_state_tensors = []
            sim_dones = []
            sim_rewards = []

            for sim in log.simulations:
                target_ent = None
                if sim.action.target is not None:
                    for e in engine.entities:
                        if e.id == sim.action.target:
                            target_ent = e
                            break

                ability = Ability(name=sim.action.ability, targeting=Targeting())
                ability.owner = actor

                sim_action = PlausibleAction(
                    move_pos=sim.action.move_pos,
                    target=target_ent,
                    ability=ability,
                    movement_name=sim.action.movement_name,
                )
                sim_actions.append(sim_action)

                sim_next_engine = state_to_engine(sim.after_state)
                next_state_tensors.append(
                    get_entity_features(sim_next_engine, sim_next_engine.active_entity)
                )
                sim_dones.append(sim.done)
                sim_rewards.append(1.0 if sim.winner_team == actor.team else 0.0)

            if not sim_actions:
                continue

            action_tensor = get_plausible_action_features(sim_actions)
            next_states_tensor = torch.cat(next_state_tensors, dim=0)

            reward = 1.0 if game.winner_team == actor.team else 0.0

            # todo first fully train value, then train policy.
            #  separate train and val
            #  Put train items into batches rather than doing one step per game like this

            agent.train_step(
                state_tensor=state_tensor,
                action_tensor=action_tensor,
                next_states_tensor=next_states_tensor,
                sim_dones=sim_dones,
                sim_rewards=sim_rewards,
                actual_reward=reward,
            )

    agent.save()
    print("Training complete.")


if __name__ == "__main__":
    train()
