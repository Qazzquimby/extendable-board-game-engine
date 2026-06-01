import operator
from typing import List, Dict

from choices import Choice
from engine import Agent
from features import ChoiceFeatureEvaluator, WeightedFeature


class FeatureWeightedAgent(Agent):
    def __init__(
        self,
        weighted_features: List[WeightedFeature],
    ):
        self.weighted_features = weighted_features
        self.feature_evaluator = ChoiceFeatureEvaluator(
            weighted_features=self.weighted_features
        )

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
            name="Damage to enemy Ranged",
            eval_string="damage_dealt(get_enemy('Ranged Hero'))",
            weight=1.2,
        ),
        WeightedFeature(
            name="Damage to enemies",
            eval_string="sum(damage_dealt(e) for e in enemies)",
            weight=1.0,
        ),
        WeightedFeature(
            name="Healing done to allies",
            eval_string="sum(heal_received(a) for a in allies)",
            weight=1.5,
        ),
        WeightedFeature(
            name="Enemies killed",
            eval_string="sum(1 for e in enemies if new_hp(e) is not None and new_hp(e) <= 0)",
            weight=100.0,
        ),
        WeightedFeature(name="Self HP", eval_string="new_hp(actor)", weight=0.1),
        WeightedFeature(
            name="Enemy Ranged Hero has HP <= 3",
            eval_string="any(new_hp(e) is not None and new_hp(e) <= 3 for e in get_enemy('Ranged Hero'))",
            weight=10.0,
        ),
        WeightedFeature(
            name="Do Nothing used on turn 4",
            eval_string="choice.ability.name == 'Do Nothing' and engine.round_num == 4",
            weight=-50.0,
        ),
        WeightedFeature(
            name="Allied Melee near enemy Ranged",
            eval_string="any(distance_after(am, er) is not None and distance_after(am, er) <= 2 for am in allied_melee for er in enemy_ranged)",
            weight=5.0,
        ),
        WeightedFeature(
            name="Used Ranged Attack",
            eval_string="choice.ability.name == 'Ranged Attack' and actor.name == 'Ranged Hero'",
            weight=1.5,
        ),
        WeightedFeature(
            name="Number of Enemies Hit",
            eval_string="len(get_hit_enemies())",
            weight=2.0,
        ),
    ]

    agent = FeatureWeightedAgent(weighted_features=weighted_features)
    return agent
