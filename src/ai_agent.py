import torch
import torch.nn as nn
import torch.optim as optim
import hashlib
from typing import List, Tuple, Optional

from engine import Engine, Entity, Ability
from heroes import MeleeHero, RangedHero


class PlausibleAction:
    def __init__(self, move_pos: Tuple[int, int], target: Entity, ability: Ability):
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

    speed = getattr(actor, "speed", 3)
    if hasattr(engine, "grid") and engine.grid is not None:
        reachable_points = engine.grid.get_points_in_range(actor.pos, speed)
    else:
        # Fallback if grid is not available
        reachable_points = set()
        for dx in range(-speed, speed + 1):
            for dy in range(-speed, speed + 1):
                if abs(dx) + abs(dy) <= speed:
                    reachable_points.add((actor.pos[0] + dx, actor.pos[1] + dy))

    for ability in actor.abilities:
        attack_range = ability.steps[0].attack_range if ability.steps else 1

        for enemy in enemies:
            target_x, target_y = enemy.pos

            if not reachable_points:
                continue

            # todo replace points with point object that supports add and subtract operator

            # As close as possible to enemy, prefer walking shorter distance
            best_close_to_enemy = min(
                reachable_points,
                key=lambda point: (
                    (abs(point[0] - target_x) + abs(point[1] - target_y)) * 100
                    + abs(point[0] - actor.pos[0])
                    + abs(point[1] - actor.pos[1])
                ),
            )

            # Closest to attack_range
            best_close_to_attack_range = min(
                reachable_points,
                key=lambda point: abs(
                    abs(point[0] - target_x) + abs(point[1] - target_y) - attack_range
                ),
            )

            proposed_moves = [best_close_to_enemy, best_close_to_attack_range]

            # As close to enemy as possible while being between ally and enemy
            for ally in allies:
                ally_dist_to_enemy = abs(ally.pos[0] - target_x) + abs(
                    ally.pos[1] - target_y
                )

                def betweenness_score(point):
                    dist_ally_to_p = abs(ally.pos[0] - point[0]) + abs(
                        ally.pos[1] - point[1]
                    )
                    dist_p_to_enemy = abs(point[0] - target_x) + abs(
                        point[1] - target_y
                    )
                    detour = (dist_ally_to_p + dist_p_to_enemy) - ally_dist_to_enemy
                    return detour * 10 + dist_p_to_enemy

                best_guard_ally = min(reachable_points, key=betweenness_score)
                proposed_moves.append(best_guard_ally)

            proposed_moves.append(actor.pos)
            unique_moves = list(set(proposed_moves))

            for move in unique_moves:
                actions.append(
                    PlausibleAction(move_pos=move, target=enemy, ability=ability)
                )

    return actions


class AIAgent:
    def __init__(self):
        self.net = AIPolicyValueNet()
        self.optimizer = optim.Adam(self.net.parameters(), lr=1e-3)

    def select_action(self, actor: Entity, engine: Engine) -> Optional[PlausibleAction]:
        actions = generate_plausible_actions(actor, engine)
        if not actions:
            return None

        state_tensor = encode_state(engine)
        action_tensors = [encode_plausible_action(a, actor.name) for a in actions]

        policy_scores, _ = self.net(state_tensor, action_tensors)

        best_idx = torch.argmax(policy_scores).item()
        return actions[best_idx]

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
