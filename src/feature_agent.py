import operator
from typing import List

from choices import Choice
from engine import Agent
from feature_packs.default import FEATURES
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
                feature_value = choice.features.get(weighted_feature.name)

                if feature_value is None:
                    continue

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
    agent = FeatureWeightedAgent(weighted_features=FEATURES)
    return agent
