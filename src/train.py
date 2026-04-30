import json
import glob

import torch
import torch.nn.functional as F

import random

from tqdm import tqdm

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

    log_files = glob.glob("../game_logs/*.json")
    if not log_files:
        print("No game_logs files found. Run self_play.py first.")
        return

    logs_data = []
    for log_file in log_files[:-1]:
        with open(log_file, "r") as f:
            logs_data.extend(json.load(f))

    data = []

    # todo can this be made faster or preprocessed once?
    for game_dict in tqdm(logs_data, desc="Processing game logs"):
        game = GameLog(**game_dict)

        for log in game.logs:
            engine = state_to_engine(log.before_state)
            actor = engine.active_entity
            if not actor:
                continue

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

            data.append(
                {  # todo use pydantic
                    "state_tensor": state_tensor,
                    "action_tensor": action_tensor,
                    "next_states_tensor": next_states_tensor,
                    "sim_dones": sim_dones,
                    "sim_rewards": sim_rewards,
                    "actual_reward": reward,
                }
            )

    random.shuffle(data)
    split_idx = int(len(data) * 0.8)
    train_data = data[:split_idx]
    val_data = data[split_idx:]

    batch_size = 32

    VALUE_EPOCHS = 20
    POLICY_EPOCHS = 20

    # todo do value then policy each epoch. Save after each epoch
    # todo use cuda
    # todo avoid oom at policy optimizer step

    print("Training Value Network...")
    last_avg_loss = 999
    for value_epoch in range(VALUE_EPOCHS):
        print(f"val epoch {value_epoch}")
        losses = []
        for i in tqdm(range(0, len(train_data), batch_size)):
            batch = train_data[i : i + batch_size]
            states = torch.cat([d["state_tensor"] for d in batch], dim=0)
            rewards = torch.tensor(
                [[d["actual_reward"]] for d in batch], dtype=torch.float32
            )
            v_loss = agent.train_value_step(states, rewards)
            losses.append(v_loss)
        avg_loss = sum(losses) / len(losses)
        print(f"value avg loss {avg_loss}")
        if avg_loss + 0.001 > last_avg_loss:
            break
        last_avg_loss = avg_loss

    print("Training Policy Network...")
    last_avg_loss = 999
    for policy_epoch in range(POLICY_EPOCHS):
        print(f"policy epoch {policy_epoch}")
        losses = []
        for i in tqdm(range(0, len(train_data), batch_size)):
            batch = train_data[i : i + batch_size]

            for d in batch:
                state_val = agent.get_value(d["state_tensor"]).item()
                next_vals = agent.get_value(d["next_states_tensor"]).squeeze(1)

                advantages = torch.zeros(len(d["sim_dones"]), dtype=torch.float32)
                for j, done in enumerate(d["sim_dones"]):
                    if done:
                        advantages[j] = d["sim_rewards"][j] - state_val
                    else:
                        advantages[j] = next_vals[j].item() - state_val

                # Lower temperature makes the network strongly prefer the best moves
                temperature = 0.1  # todo what difference does this make in training?
                target_probs = F.softmax(advantages / temperature, dim=0)

                p_loss = agent.train_policy_step(
                    d["state_tensor"], d["action_tensor"], target_probs
                )
                losses.append(p_loss)

        avg_loss = sum(losses) / len(losses)
        print(f"avg policy loss {avg_loss}")
        if avg_loss + 0.001 > last_avg_loss:
            break
        last_avg_loss = avg_loss

    # Validation could be added here to compute loss on val_data
    print(f"Validation set size: {len(val_data)}")

    agent.save()
    print("Training complete.")


if __name__ == "__main__":
    train()
