from typing import List, Tuple, TYPE_CHECKING

from einops import einops
from jaxtyping import Float
import torch
import torch.nn as nn
import torch.optim as optim
from torch import Tensor
import torch.nn.functional as F

from engine import Engine, Entity, EventPhase, Agent, Choice
from queries import QueryLegalAimings
from abilities import (
    Ability,
    DamageInstruction,
    HealInstruction,
)
from aimings import TargetSelf, TargetEntity, IncludeArea
from point import Point

MAX_ENTITY_TYPES = 1024  # increase
MAX_ABILITY_TYPES = MAX_ENTITY_TYPES * 4


class GameStateEncoder(nn.Module):
    def __init__(
        self,
        entity_vocab_size: int,
        emb_size: int = 64,
        num_heads: int = 4,
        num_layers: int = 4,
    ):
        super().__init__()
        self.id_embedding = nn.Embedding(entity_vocab_size, emb_size)
        self.other_features_size = 5  # [x, y, hp, team, is_actor]
        self.other_features_linear = nn.Linear(self.other_features_size, emb_size)
        self.final_linear = nn.Linear(emb_size, emb_size)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=emb_size, nhead=num_heads, batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

    def forward(
        self, entity_features: Float[Tensor, "batch entities features"]
    ) -> Tuple[Float[Tensor, "batch enc"], Float[Tensor, "batch enc"]]:
        entity_ids = entity_features[:, :, 0].long()
        entity_other_features = entity_features[:, :, 1:]

        id_emb = self.id_embedding(entity_ids)
        features_enc = self.other_features_linear(entity_other_features)
        combined_enc = id_emb + features_enc
        entities_encoded = self.final_linear(combined_enc)

        transformed: Float[Tensor, "batch entities enc"] = self.transformer(
            entities_encoded
        )
        pooled: Float[Tensor, "batch enc"] = transformed.mean(dim=1)
        return pooled, transformed

    if TYPE_CHECKING:
        __call__ = forward


class ActionEncoder(nn.Module):
    def __init__(self, ability_vocab_size: int, hidden_dim: int = 64):
        super().__init__()
        self.ability_embedding = nn.Embedding(ability_vocab_size, hidden_dim)
        # Action encoding: [move_x, move_y, target_x, target_y]
        self.other_features_linear = nn.Linear(4, hidden_dim)
        self.final_linear = nn.Linear(hidden_dim, hidden_dim)

    def forward(
        self, action_tensor: Float[Tensor, "batch action feature"]
    ) -> Float[Tensor, "batch action emb"]:
        ability_id = action_tensor[..., 0].long()
        action_other_features = action_tensor[..., 1:]

        ability_emb = self.ability_embedding(ability_id)
        feature_enc = self.other_features_linear(action_other_features)
        # combined_enc = torch.cat([ability_emb, feature_enc], dim=-1)
        combined_enc = ability_emb + feature_enc
        result = self.final_linear(combined_enc)
        return result

    if TYPE_CHECKING:
        __call__ = forward


class AIPolicyValueNet(nn.Module):
    def __init__(
        self, entity_vocab_size: int, ability_vocab_size: int, hidden_dim: int = 64
    ):
        super().__init__()
        self.state_encoder = GameStateEncoder(entity_vocab_size, hidden_dim)
        self.action_encoder = ActionEncoder(ability_vocab_size, hidden_dim)

        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(), nn.Linear(32, 1)
        )

        self.policy_head = nn.Sequential(  # global state, actor state, action
            nn.Linear(hidden_dim * 3, 32), nn.ReLU(), nn.Linear(32, 1)
        )

    def forward(
        self,
        entity_features: Float[Tensor, "batch entities features"],
        action_features: Float[Tensor, "batch actions features"],
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        state_emb, all_entities_emb = self.state_encoder(
            entity_features
        )  # both are batch, emb
        value: Float[Tensor, "batch 1"] = self.value_head(state_emb)

        actor_idx = torch.argmax(entity_features[:, :, -1], dim=1)
        batch_indices = torch.arange(entity_features.size(0))
        actor_emb = all_entities_emb[batch_indices, actor_idx]

        act_emb: Float[Tensor, "batch actions emb"] = self.action_encoder(
            action_features
        )
        context_emb = torch.cat([state_emb, actor_emb], dim=-1)
        context_expanded = einops.repeat(
            context_emb, "batch emb -> batch act emb", act=act_emb.shape[1]
        )
        combined = torch.cat([context_expanded, act_emb], dim=-1)
        policy_scores = self.policy_head(combined)
        return policy_scores, value

    if TYPE_CHECKING:
        __call__ = forward


def get_entity_features(
    engine: Engine, actor: Entity
) -> Float[Tensor, "batch entities features"]:
    # right now batch is 1
    entity_features = []
    for entity in engine.entities:
        entity_features.append(
            [
                float(entity.get_hash() % MAX_ENTITY_TYPES),
                float(entity.pos[0]) if entity.pos else -1.0,
                float(entity.pos[1]) if entity.pos else -1.0,
                float(entity.hp),
                float(entity.team),
                1.0 if entity == actor else 0.0,
            ],
        )
    return torch.tensor([entity_features], dtype=torch.float32)


def get_plausible_action_features(
    plausible_actions: List[PlausibleMoveAndAction],
) -> Float[Tensor, "batch actions features"]:
    # right now batch is 1
    action_features = []
    for plausible_action in plausible_actions:
        target_x = (
            float(plausible_action.target.pos[0])
            if plausible_action.target and plausible_action.target.pos
            else -1.0
        )
        target_y = (
            float(plausible_action.target.pos[1])
            if plausible_action.target and plausible_action.target.pos
            else -1.0
        )
        action_features.append(
            [
                float(plausible_action.ability.get_hash() % MAX_ABILITY_TYPES),
                float(plausible_action.move_pos[0]),
                float(plausible_action.move_pos[1]),
                target_x,
                target_y,
            ]
        )
    return torch.tensor([action_features], dtype=torch.float32)


class LinearWeightAgent(Agent):
    def __init__(self, default_weight: float = 0.0):
        super().__init__()
        self.weights: dict[str, float] = {}
        self.default_weight = default_weight

    def choose(self, choices: List[Choice]) -> int:
        if not choices:
            return 0
        if len(choices) == 1:
            return 0

        best_idx = 0
        best_score = float("-inf")

        for i, choice in enumerate(choices):
            score = 0.0
            if hasattr(choice, "features"):
                for key, val in choice.features.items():
                    weight = self.weights.get(key, self.default_weight)
                    score += weight * val

            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx
