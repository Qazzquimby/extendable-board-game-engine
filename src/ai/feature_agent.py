import pkgutil
import importlib
from typing import List

from choices import Choice
from engine import Agent
import feature_packs
from features import ChoiceFeatureEvaluator, WeightedFeature


def get_all_features(game_setup_id: str) -> List[WeightedFeature]:
    all_features = []
    # top_level_module_infos: List[pkgutil.ModuleInfo] = list(
    #     pkgutil.iter_modules(feature_packs.__path__)
    # )
    # for _, name, _ in top_level_module_infos:
    #     module = importlib.import_module(f"feature_packs.{name}")
    #     if hasattr(module, "FEATURES"):
    #         all_features.extend(module.FEATURES)

    tuning_dir_module_infos: List[pkgutil.ModuleInfo] = list(
        pkgutil.iter_modules([feature_packs.__path__[0] + f"/{game_setup_id}"])
    )
    for _, name, _ in tuning_dir_module_infos:
        module = importlib.import_module(f"feature_packs.{game_setup_id}.{name}")
        if hasattr(module, "FEATURES"):
            all_features.extend(module.FEATURES)

    return all_features


class FeatureWeightedAgent(Agent):
    def __init__(
        self,
        weighted_features: List[WeightedFeature],
    ):
        self.weighted_features = weighted_features
        self.feature_evaluator = ChoiceFeatureEvaluator(
            weighted_features=self.weighted_features
        )

    def choose(self, env: "Engine") -> int:
        choices = env.current_choices
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
    agent = FeatureWeightedAgent(weighted_features=get_all_features())
    return agent
