from typing import List

from engine import Agent, Choice


class LinearWeightAgent(Agent):
    def __init__(self, weights: dict[str, float]):
        super().__init__(self)
        self.weights: dict[str, float] = weights
        self.default_weight = 0.0

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
