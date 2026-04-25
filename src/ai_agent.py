from typing import List, Tuple

import torch
import torch.nn as nn
import torch.optim as optim

from engine import Engine, Entity
from abilities import Ability, TargetArea, TargetSelf, TargetUnit
from point import Point


class PlausibleAction:
    def __init__(self, move_pos: Point, target: Entity, ability: Ability):
        self.move_pos = move_pos
        self.target = target
        self.ability = ability


class GameStateEncoder(nn.Module):
    def __init__(self, hidden_dim: int = 64, num_heads: int = 4, num_layers: int = 2):
        super().__init__()
        self.entity_dim = 5  # [x, y, hp, team, entity_hash]
        self.hidden_dim = hidden_dim

        self.embedding = nn.Linear(self.entity_dim, hidden_dim)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim, nhead=num_heads, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        # Pool the sequence into a single context vector
        self.pooling = nn.AdaptiveAvgPool1d(1)

    def forward(self, state_tensor: torch.Tensor) -> torch.Tensor:
        # state_tensor shape: (batch_size, num_entities * entity_dim) or (num_entities * entity_dim)
        if state_tensor.dim() == 1:
            state_tensor = state_tensor.unsqueeze(0)

        batch_size = state_tensor.size(0)
        # Reshape to (batch_size, num_entities, entity_dim)
        seq = state_tensor.view(batch_size, -1, self.entity_dim)

        embedded = self.embedding(seq)
        transformed = self.transformer(embedded)

        # Pool across the sequence dimension (entities)
        # transformed shape: (batch_size, num_entities, hidden_dim)
        # transpose for pooling: (batch_size, hidden_dim, num_entities)
        pooled = self.pooling(transformed.transpose(1, 2)).squeeze(-1)

        # Return shape: (hidden_dim) if original was 1D, else (batch_size, hidden_dim)
        if batch_size == 1 and state_tensor.dim() == 1:
            return pooled.squeeze(0)
        return pooled


class ActionEncoder(nn.Module):
    def __init__(self, hidden_dim: int = 64):
        super().__init__()
        # Action encoding: [move_x, move_y, target_x, target_y, ability_id]
        self.net = nn.Sequential(
            nn.Linear(5, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, hidden_dim)
        )

    def forward(self, action_tensor: torch.Tensor) -> torch.Tensor:
        return self.net(action_tensor)


class AIPolicyValueNet(nn.Module):
    def __init__(self, hidden_dim: int = 64):
        super().__init__()
        self.state_encoder = GameStateEncoder(hidden_dim)
        self.action_encoder = ActionEncoder(hidden_dim)

        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(), nn.Linear(32, 1)
        )

        self.policy_head = nn.Sequential(
            nn.Linear(hidden_dim * 2, 32), nn.ReLU(), nn.Linear(32, 1)
        )

    def forward(
        self, state_tensor: torch.Tensor, action_tensors: List[torch.Tensor]
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        state_emb = self.state_encoder(state_tensor)
        value = self.value_head(state_emb)

        policy_scores = []
        for act_tensor in action_tensors:
            act_emb = self.action_encoder(act_tensor)
            combined = torch.cat([state_emb, act_emb], dim=-1)
            score = self.policy_head(combined)
            policy_scores.append(score)

        if policy_scores:
            policy_scores_tensor = torch.cat(policy_scores)
        else:
            policy_scores_tensor = torch.tensor([])

        return policy_scores_tensor, value


def encode_state(engine: Engine) -> torch.Tensor:
    features = []
    for i in range(10):
        if i < len(engine.entities):
            entity = engine.entities[i]
            features.extend(
                [
                    float(entity.pos[0]),
                    float(entity.pos[1]),
                    float(entity.hp),
                    float(entity.team),
                    entity.get_hash(),
                ]
            )
        else:
            features.extend([0.0, 0.0, 0.0, 0.0, 0.0])
    return torch.tensor(features, dtype=torch.float32)


def encode_plausible_action(plausible_action: PlausibleAction) -> torch.Tensor:
    ability_id = plausible_action.ability.get_hash()
    features = [
        float(plausible_action.move_pos[0]),
        float(plausible_action.move_pos[1]),
        float(plausible_action.target.pos[0]),
        float(plausible_action.target.pos[1]),
        ability_id,
    ]
    return torch.tensor(features, dtype=torch.float32)


def generate_plausible_actions(actor: Entity, engine: Engine) -> List[PlausibleAction]:
    actions = []
    enemies = [e for e in engine.entities if e.team != actor.team]
    allies = [e for e in engine.entities if e.team == actor.team and e != actor]

    occupied_points = {e.pos for e in engine.entities if e != actor}
    reachable_points = engine.grid.get_movable_spaces(
        actor.pos, actor.speed, occupied_points
    )

    # todo, no. Get all the possible movements, and from each you get all the possible action-targetings. You can move towards one enemy and shoot another. Not all abilities even target enemies.
    for ability in actor.abilities:
        if isinstance(ability.targeting, (TargetUnit, TargetArea)):
            attack_range = ability.targeting.range
            for enemy in enemies:
                # As close as possible to enemy, prefer walking shorter distance
                best_close_to_enemy = min(
                    reachable_points,
                    key=lambda point: (
                        point.get_distance(enemy.pos) * 100
                        + point.get_distance(actor.pos)
                    ),
                )

                # Closest to attack_range
                best_close_to_attack_range = min(
                    reachable_points,
                    key=lambda point: abs(point.get_distance(enemy.pos) - attack_range)
                    * 100
                    + point.get_distance(actor.pos),
                )

                proposed_moves = [best_close_to_enemy, best_close_to_attack_range]

                # As close to enemy as possible while being between ally and enemy
                for ally in allies:
                    ally_dist_to_enemy = ally.pos.get_distance(enemy.pos)

                    def betweenness_score(point: Point):
                        distance_to_ally = point.get_distance(ally.pos)
                        distance_to_enemy = point.get_distance(enemy.pos)
                        detour = (
                            distance_to_ally + distance_to_enemy
                        ) - ally_dist_to_enemy
                        return detour * 10 + distance_to_enemy

                    best_guard_ally = min(reachable_points, key=betweenness_score)
                    proposed_moves.append(best_guard_ally)

                proposed_moves.append(actor.pos)
                unique_moves = list(set(proposed_moves))

                for move in unique_moves:
                    actions.append(
                        PlausibleAction(move_pos=move, target=enemy, ability=ability)
                    )
        elif isinstance(ability.targeting, TargetSelf):
            # For self-targeting, there's no specific enemy to move towards.
            # A simple heuristic: stay put. And maybe move towards nearest enemy.
            unique_moves = {actor.pos}
            if enemies:
                nearest_enemy = min(
                    enemies, key=lambda e: actor.pos.get_distance(e.pos)
                )

                best_move = min(
                    reachable_points,
                    key=lambda p: p.get_distance(nearest_enemy.pos) * 100
                    + p.get_distance(actor.pos),
                )
                unique_moves.add(best_move)

            for move in unique_moves:
                actions.append(
                    PlausibleAction(move_pos=move, target=actor, ability=ability)
                )

    assert actions
    return actions


class AIAgent:
    def __init__(self):
        self.net = AIPolicyValueNet()
        self.optimizer = optim.Adam(self.net.parameters(), lr=1e-3)

    def select_action(
        self,
        actor: Entity,
        engine: Engine,
        plausible_actions: List[PlausibleAction],
        temperature=1.0,
    ) -> Tuple[PlausibleAction, int]:
        if not plausible_actions:
            raise ValueError("Cannot select an action from an empty list.")

        state_tensor = encode_state(engine)
        action_tensors = [encode_plausible_action(a) for a in plausible_actions]

        with torch.no_grad():
            policy_scores, _ = self.net(state_tensor, action_tensors)
            if temperature <= 0:
                chosen_index = torch.argmax(policy_scores).item()
            else:
                probs = torch.softmax(policy_scores / temperature, dim=0)
                chosen_index = torch.multinomial(probs, 1).item()

        return plausible_actions[chosen_index], chosen_index

    def train_step(
        self,
        state_tensor: torch.Tensor,
        action_tensors: List[torch.Tensor],
        chosen_action_idx: int,
        next_state_tensor: torch.Tensor,
        reward: float,
        done: bool,
    ) -> float:
        self.optimizer.zero_grad()

        policy_scores, value = self.net(state_tensor, action_tensors)

        if done:
            target_value = torch.tensor([reward], dtype=torch.float32)
        else:
            _, next_value = self.net(next_state_tensor, [])
            target_value = reward + 0.99 * next_value.detach()

        value_loss = nn.MSELoss()(value, target_value)

        advantage = (target_value - value.detach()).item()

        probs = torch.softmax(policy_scores, dim=0)
        log_prob = torch.log(probs[chosen_action_idx] + 1e-8)
        policy_loss = -log_prob * advantage

        loss = value_loss + policy_loss
        loss.backward()
        self.optimizer.step()

        return loss.item()
