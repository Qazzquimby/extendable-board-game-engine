import operator
from typing import List, Dict

from pydantic import BaseModel

from choices import Choice
from engine import Agent


class WeightedFeature(BaseModel):
    name: str
    eval_string: str
    weight: float


class FeatureWeightedAgent(Agent):
    def __init__(
        self,
        weighted_features: List[WeightedFeature],
    ):
        self.weighted_features = weighted_features

    def choose(self, choices: List[Choice]) -> int:
        if not choices:
            return 0

        scores = []
        for choice in choices:
            score = 0.0
            for weighted_feature in self.weighted_features:
                feature_value = choice.features[weighted_feature.name]

                numeric_value = 0
                if isinstance(feature_value, bool):
                    numeric_value = int(feature_value)
                elif isinstance(feature_value, (int, float)):
                    numeric_value = feature_value

                score += weighted_feature.weight * numeric_value
            scores.append(score)

        if not scores:
            return 0

        best_index = max(range(len(scores)), key=scores.__getitem__)
        return best_index


def get_example_feature_agent():
    weighted_features = [
        WeightedFeature(
            name="Damage Dealt to enemies",
            eval_string="sum(core_features.get(f'damage_dealt_to_{e.name}_{e.id}', 0) for e in enemies)",
            weight=1.0,
        ),
        WeightedFeature(
            name="Healing done to allies",
            eval_string="sum(core_features.get(f'heal_dealt_to_{a.name}_{a.id}', 0) for a in allies)",
            weight=0.7,
        ),
        WeightedFeature(
            name="Enemies killed",
            eval_string="sum(1 for e in enemies if new_hp(e) is not None and hypothetical_hp(e) <= 0)",
            weight=100.0,
        ),
        WeightedFeature(
            name="self HP", eval_string="hypothetical_hp(actor)", weight=0.5
        ),
        WeightedFeature(
            name="Min Range to Enemies",
            eval_string="min([engine.grid.get_range(get_future_pos(actor), get_future_pos(e)) for e in enemies if get_future_pos(e) and get_future_pos(actor)] or [99])",
            weight=-0.1,
        ),
        WeightedFeature(
            name="Number of Enemies Hit",
            eval_string="""\
            hit_enemies = 0
            all_points = set(choice.aiming_result.target_points) | set(
                choice.aiming_result.included_points
            )
            for point in all_points:
                entity = engine.entity_at(point)
                if entity and entity.team != actor.team:
                    hit_enemies += 1
            return hit_enemies""",
            weight=2.0,
        ),
    ]

    agent = FeatureWeightedAgent(weighted_features=weighted_features)
    return agent
