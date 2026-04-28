from typing import List, Tuple, TYPE_CHECKING

from einops import einops
from jaxtyping import Float

import torch
import torch.nn as nn
import torch.optim as optim
from torch import Tensor

from engine import Engine, Entity
from abilities import (
    Ability,
    TargetArea,
    TargetSelf,
    TargetUnit,
    DamageEffect,
    HealEffect,
)
from point import Point

MAX_ENTITY_TYPES = 1024  # increase
MAX_ABILITY_TYPES = MAX_ENTITY_TYPES * 4


class PlausibleAction:
    def __init__(
        self,
        move_pos: Point,
        target: Entity | None,
        ability: Ability,
        movement_name: str = "",
    ):
        # todo right now aoe uses target None.
        #  Probably better to have a list of targets. Ml will need adjusting
        self.move_pos = move_pos
        self.target = target
        self.ability = ability
        self.movement_name = movement_name


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
    ) -> Float[Tensor, "batch enc"]:
        entity_ids = entity_features[:, :, 0].long()
        entity_other_features = entity_features[:, :, 1:]

        id_emb = self.id_embedding(entity_ids)
        features_enc = self.other_features_linear(entity_other_features)
        # combined_enc = torch.cat([id_emb, features_enc], dim=-1)
        combined_enc = id_emb + features_enc
        entities_encoded = self.final_linear(combined_enc)

        transformed: Float[Tensor, "batch entities enc"] = self.transformer(
            entities_encoded
        )
        pooled: Float[Tensor, "batch enc"] = transformed.mean(dim=1)
        return pooled

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

        self.policy_head = nn.Sequential(
            nn.Linear(hidden_dim * 2, 32), nn.ReLU(), nn.Linear(32, 1)
        )

    def forward(
        self,
        entity_features: Float[Tensor, "batch entities features"],
        action_features: Float[Tensor, "batch actions features"],
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        state_emb: Float[Tensor, "batch emb"] = self.state_encoder(entity_features)
        value: Float[Tensor, "batch 1"] = self.value_head(state_emb)

        policy_scores = []
        act_emb: Float[Tensor, "batch actions emb"] = self.action_encoder(
            action_features
        )
        state_emb_expanded = einops.repeat(
            state_emb, "batch emb -> batch act emb", act=act_emb.shape[1]
        )
        combined = torch.cat([state_emb_expanded, act_emb], dim=-1)
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
    plausible_actions: List[PlausibleAction],
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


def generate_plausible_actions(actor: Entity, engine: Engine) -> List[PlausibleAction]:
    enemies = [e for e in engine.entities if e.team != actor.team and e.hp > 0]
    allies = [
        e for e in engine.entities if e.team == actor.team and e != actor and e.hp > 0
    ]

    occupied_points = {
        e.pos for e in engine.entities if e != actor and e.pos is not None
    }
    reachable_points = engine.grid.get_movable_spaces(
        actor.pos, actor.speed, occupied_points
    )
    reachable_points.add(actor.pos)

    # 1. Generate a set of interesting move positions.
    proposed_moves = {actor.pos: "Stay"}
    if reachable_points:
        # For each enemy, find a good position to approach
        for enemy in enemies:
            best_close_to_enemy = min(
                reachable_points,
                key=lambda point: (
                    point.get_distance(enemy.pos) * 100 + point.get_distance(actor.pos)
                ),
            )
            proposed_moves[best_close_to_enemy] = f"Approach {enemy.name} {enemy.id}"

            # For each ability that can target units/areas, find a spot at optimal range
            for ability in actor.abilities:
                attack_range = 0
                if isinstance(ability.targeting, TargetUnit):
                    attack_range = ability.targeting.in_range
                elif isinstance(ability.targeting, TargetArea):
                    attack_range = ability.targeting.area.in_range

                if attack_range > 0:
                    best_at_range = min(
                        reachable_points,
                        key=lambda point: abs(
                            point.get_distance(enemy.pos) - attack_range
                        )
                        * 100
                        + point.get_distance(actor.pos),
                    )
                    proposed_moves[best_at_range] = (
                        f"Range {attack_range} for {ability.name}"
                    )

        # For each ally, find a good position to "guard" them from nearest enemy
        for ally in allies:
            if enemies:
                nearest_enemy_to_ally = min(
                    enemies, key=lambda e: ally.pos.get_distance(e.pos)
                )
                ally_dist_to_enemy = ally.pos.get_distance(nearest_enemy_to_ally.pos)

                def betweenness_score(point: Point):
                    distance_to_ally = point.get_distance(ally.pos)
                    distance_to_enemy = point.get_distance(nearest_enemy_to_ally.pos)
                    detour = (distance_to_ally + distance_to_enemy) - ally_dist_to_enemy
                    return detour * 10 + distance_to_enemy

                best_guard_ally = min(reachable_points, key=betweenness_score)
                proposed_moves[best_guard_ally] = (
                    f"Guard {ally.name} {ally.id} from {nearest_enemy_to_ally.name} {nearest_enemy_to_ally.id}"
                )

    # 2. For each move position, find all possible actions
    actions_map = {}  # Use dict to store unique actions
    for move_pos, movement_name in proposed_moves.items():
        for ability in actor.abilities:
            is_positive = any(isinstance(e, HealEffect) for e in ability.effects)
            is_negative = any(isinstance(e, DamageEffect) for e in ability.effects)

            if isinstance(ability.targeting, TargetUnit):
                attack_range = ability.targeting.in_range
                # Target anyone in range. Could be friend or foe.
                for target in engine.entities:
                    if target == actor:
                        continue
                    if not is_positive and target.team == actor.team:
                        continue
                    if not is_negative and target.team != actor.team:
                        continue
                    if move_pos.get_distance(target.pos) <= attack_range:
                        key = (move_pos, target.pos, ability.get_hash())
                        if key not in actions_map:
                            actions_map[key] = PlausibleAction(
                                move_pos=move_pos,
                                target=target,
                                ability=ability,
                                movement_name=movement_name,
                            )
            elif isinstance(ability.targeting, TargetArea):
                area = ability.targeting.area
                for area_points in area.get_selections(engine.grid, move_pos):
                    affected_entities = {
                        e for e in engine.entities if e.pos in area_points
                    }
                    if not affected_entities:
                        continue

                    # One action per unique set of affected entities
                    key = (
                        move_pos,
                        frozenset(e.pos for e in affected_entities),
                        ability.get_hash(),
                    )
                    if key not in actions_map:
                        if is_positive:
                            valid_targets = [
                                e for e in affected_entities if e.team == actor.team
                            ]
                        elif is_negative:
                            valid_targets = [
                                e for e in affected_entities if e.team != actor.team
                            ]
                        else:
                            valid_targets = list(affected_entities)

                        if not valid_targets:
                            continue

                        actions_map[key] = PlausibleAction(
                            move_pos=move_pos,
                            target=None,
                            ability=ability,
                            movement_name=movement_name,
                        )
            elif isinstance(ability.targeting, TargetSelf):
                target = actor
                key = (move_pos, target.pos, ability.get_hash())
                if key not in actions_map:
                    actions_map[key] = PlausibleAction(
                        move_pos=move_pos,
                        target=target,
                        ability=ability,
                        movement_name=movement_name,
                    )

    actions = list(actions_map.values())
    assert actions
    return actions


class AIAgent:
    def __init__(self):
        self.net: AIPolicyValueNet = AIPolicyValueNet(
            entity_vocab_size=MAX_ENTITY_TYPES,
            ability_vocab_size=MAX_ABILITY_TYPES,
        )
        self.optimizer = optim.Adam(self.net.parameters(), lr=1e-3)

    def select_action(
        self,
        actor: Entity,
        engine: Engine,
        plausible_actions: List[PlausibleAction],
        temperature=1.0,
    ) -> PlausibleAction:
        entity_features = get_entity_features(engine, actor)
        action_features = get_plausible_action_features(plausible_actions)

        with torch.no_grad():
            policy_scores, _value = self.net(entity_features, action_features)
            assert policy_scores.shape[0] == 1  # only batch size 1 right now
            policy_scores = policy_scores.squeeze()
            if temperature <= 0:
                chosen_index = torch.argmax(policy_scores).item()
            else:
                probs = torch.softmax(policy_scores / temperature, dim=0)
                chosen_index = torch.multinomial(probs, 1).item()
        chosen_action = plausible_actions[chosen_index]
        return chosen_action

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
