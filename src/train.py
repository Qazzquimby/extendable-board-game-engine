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
import os

from pydantic import BaseModel, ConfigDict

from engine import Engine, Entity
from abilities import Ability, Targeting
from schemas import GameLog, EngineState

# First train value prediction
# Then train policy to prefer actions that lead to better value predictions


class TrainData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    state_tensor: torch.Tensor
    action_tensor: torch.Tensor
    next_states_tensor: torch.Tensor
    sim_dones: list[bool]
    sim_rewards: list[float]
    actual_reward: float


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

def preprocess(preprocessed_file: str) -> list[TrainData]:
    log_files = glob.glob("../game_logs/*.json")
    if not log_files:
        raise FileNotFoundError("No game_logs files found. Run self_play.py first.")

    logs_data = []
    for log_file in log_files[:-1]:
        with open(log_file, "r") as f:
            logs_data.extend(json.load(f))

    data = []

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
                TrainData(
                    state_tensor=state_tensor,
                    action_tensor=action_tensor,
                    next_states_tensor=next_states_tensor,
                    sim_dones=sim_dones,
                    sim_rewards=sim_rewards,
                    actual_reward=reward,
                )

            )

            print(f"Saving preprocessed data to {preprocessed_file}...")
            torch.save(data, preprocessed_file)
            return data

def train():
    agent = AIAgent()
    agent.load()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    agent.net.to(device)

    preprocessed_file = "preprocessed_train_data.pt"
    if os.path.exists(preprocessed_file):
        print(f"Loading preprocessed data from {preprocessed_file}...")
        data = torch.load(preprocessed_file, weights_only=False)
    else:
        data = preprocess(preprocessed_file)

    random.shuffle(data)
    split_idx = int(len(data) * 0.8)
    train_data = data[:split_idx]
    val_data = data[split_idx:]

    batch_size = 128
    EPOCHS = 20

    print("Training Network...")
    for epoch in range(EPOCHS):
        print(f"Epoch {epoch}")
        
        # Value
        losses = []
        for i in tqdm(range(0, len(train_data), batch_size), desc="Value"):
            batch = train_data[i : i + batch_size]
            states = torch.cat([d.state_tensor for d in batch], dim=0).to(device)
            rewards = torch.tensor(
                [[d.actual_reward] for d in batch], dtype=torch.float32
            ).to(device)
            v_loss = agent.train_value_step(states, rewards)
            losses.append(v_loss)
            
        print(f"value avg loss {sum(losses) / len(losses)}")

        # Policy
        losses = []
        for i in tqdm(range(0, len(train_data), batch_size), desc="Policy"):
            batch = train_data[i : i + batch_size]

            for d in batch:
                state_tensor = d.state_tensor.to(device)
                next_states_tensor = d.next_states_tensor.to(device)
                action_tensor = d.action_tensor.to(device)
                
                state_val = agent.get_value(state_tensor).item()
                next_vals = agent.get_value(next_states_tensor).squeeze(1)

                advantages = torch.zeros(len(d.sim_dones), dtype=torch.float32).to(device)
                for j, done in enumerate(d.sim_dones):
                    if done:
                        advantages[j] = d.sim_rewards[j] - state_val
                    else:
                        advantages[j] = next_vals[j].item() - state_val

                temperature = 0.1
                target_probs = F.softmax(advantages / temperature, dim=0)

                p_loss = agent.train_policy_step(
                    state_tensor, action_tensor, target_probs
                )
                losses.append(p_loss)
                
                del state_tensor, next_states_tensor, action_tensor, advantages, target_probs
            
            torch.cuda.empty_cache()

        print(f"avg policy loss {sum(losses) / len(losses)}")
        agent.save()

    print(f"Validation set size: {len(val_data)}")
    print("Training complete.")


if __name__ == "__main__":
    train()
