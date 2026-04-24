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
        self.entity_dim = 4  # [x, y, hp, team]
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
            e = engine.entities[i]
            features.extend(
                [float(e.pos[0]), float(e.pos[1]), float(e.hp), float(e.team)]
            )
        else:
            features.extend([0.0, 0.0, 0.0, 0.0])
    return torch.tensor(features, dtype=torch.float32)

# todo entities should also be hashed and embedded.

def get_ability_hash(
    ability: Ability, entity_name: str = "unknown", set_name: str = "development"
) -> float:
    """Generates a deterministic hash for an ability based on its set, unit, and name."""
    key = f"{set_name}__{entity_name}__{ability.name}"
    # Use MD5 to get a consistent integer, then normalize it to a reasonable float range
    hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
    return float(hash_int % 10000) / 100.0


def encode_action(action: PlausibleAction, actor_name: str = "unknown") -> torch.Tensor:
    ability_id = get_ability_hash(action.ability, actor_name)
    features = [
        float(action.move_pos[0]),
        float(action.move_pos[1]),
        float(action.target.pos[0]),
        float(action.target.pos[1]),
        ability_id,
    ]
    return torch.tensor(features, dtype=torch.float32)


def generate_plausible_actions(actor: Entity, engine: Engine) -> List[PlausibleAction]:
    actions = []
    enemies = [e for e in engine.entities if e.team != actor.team]
    allies = [e for e in engine.entities if e.team == actor.team and e != actor]

    for ability in actor.abilities:
        attack_range = ability.steps[0].attack_range if ability.steps else 1

        for enemy in enemies:
            target_x, target_y = enemy.pos
            # todo these are not accounting for speed or pathing limitations?? People can't just teleport wherever they want.

            # Heuristic 1: As close as possible to enemy (adjacent)
            proposed_moves = [
                (target_x + 1, target_y),
                (target_x - 1, target_y),
                (target_x, target_y + 1),
                (target_x, target_y - 1),
            ]

            # Heuristic 2: As far as possible from enemy while being in range
            proposed_moves.extend(
                [
                    (target_x + attack_range, target_y),
                    (target_x - attack_range, target_y),
                    (target_x, target_y + attack_range),
                    (target_x, target_y - attack_range),
                ]
            )

            # Heuristic 3: Between ally and enemy (simple midpoint approximation)
            # todo no, it should be as close to enemy as possible while being between ally and enemy.
            for ally in allies:
                mid_x = (target_x + ally.pos[0]) // 2
                mid_y = (target_y + ally.pos[1]) // 2
                proposed_moves.append((mid_x, mid_y))

            # Deduplicate moves
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
        action_tensors = [encode_action(a, actor.name) for a in actions]

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
