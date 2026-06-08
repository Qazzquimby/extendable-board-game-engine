import json
import random
from pathlib import Path
from typing import List, Dict, Callable

import numpy as np

from ai.feature_agent import FeatureWeightedAgent
from feature_packs.default import FEATURES
from features import WeightedFeature


class PlayerPopulation:
    def __init__(
        self,
        population_size: int,
        feature_catalog: List[str],
        initial_weight_stats: Dict[str, tuple[float, float]] = None,
    ):
        self.population_size = population_size
        self.feature_catalog = feature_catalog
        if initial_weight_stats:
            self.population = self._initialize_population(initial_weight_stats)
        else:
            self.population = []

    def _initialize_population(
        self, initial_weight_stats: Dict[str, tuple[float, float]]
    ) -> List[Dict[str, float]]:
        population = []
        for _ in range(self.population_size):
            weights = {}
            for feature in self.feature_catalog:
                mean, std_dev = initial_weight_stats.get(feature, (0.0, 0.1))
                if std_dev == 0.0:
                    std_dev = 0.1
                weights[feature] = np.random.normal(mean, std_dev)
            population.append(weights)
        return population

    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.population, f, indent=2)

    @classmethod
    def load(cls, path: Path, feature_catalog: List[str]):
        with open(path, "r") as f:
            population_data = json.load(f)
        instance = cls(len(population_data), feature_catalog)
        instance.population = population_data
        return instance

    def evolve(
        self,
        scores: Dict[int, int],
        mutation_rate: float,
        mutation_strength: float,
        crossover_prob: float,
    ):
        # Tournament selection
        new_population = []
        for _ in range(self.population_size):
            p1_idx, p2_idx = random.sample(range(self.population_size), 2)
            winner_idx = (
                p1_idx if scores.get(p1_idx, 0) > scores.get(p2_idx, 0) else p2_idx
            )
            new_population.append(self.population[winner_idx].copy())

        # Crossover and Mutation
        next_gen = []
        for i in range(0, self.population_size, 2):
            parent1 = new_population[i]
            parent2 = new_population[i + 1]

            child1, child2 = self._crossover(parent1, parent2, crossover_prob)

            self._mutate(child1, mutation_rate, mutation_strength)
            self._mutate(child2, mutation_rate, mutation_strength)

            next_gen.append(child1)
            next_gen.append(child2)

        self.population = next_gen

    def _crossover(self, p1: Dict, p2: Dict, probability: float) -> (Dict, Dict):
        child1, child2 = p1.copy(), p2.copy()
        if random.random() < probability:
            keys = list(self.feature_catalog)
            random.shuffle(keys)
            crossover_point = random.randint(1, len(keys) - 1)
            for i in range(crossover_point):
                key = keys[i]
                child1[key], child2[key] = child2[key], child1[key]
        return child1, child2

    def _mutate(self, weights: Dict, rate: float, strength: float):
        for key in weights:
            if random.random() < rate:
                weights[key] += np.random.normal(0, strength)


def run_tournament(
    population0: PlayerPopulation,
    population1: PlayerPopulation,
    engine_setup_fn: Callable,
    run_game_fn: Callable,
    num_games_per_matchup: int = 2,
):
    scores0 = {i: 0 for i in range(population0.population_size)}
    scores1 = {i: 0 for i in range(population1.population_size)}

    for i in range(population0.population_size):
        for j in range(population1.population_size):
            weights0 = population0.population[i]
            features0 = [
                WeightedFeature(
                    name=f.name,
                    eval_func=f.eval_func,
                    weight=weights0.get(f.name, 0.0)
                )
                for f in FEATURES
            ]
            agent0 = FeatureWeightedAgent(weighted_features=features0)

            weights1 = population1.population[j]
            features1 = [
                WeightedFeature(
                    name=f.name,
                    eval_func=f.eval_func,
                    weight=weights1.get(f.name, 0.0)
                )
                for f in FEATURES
            ]
            agent1 = FeatureWeightedAgent(weighted_features=features1)

            for _ in range(num_games_per_matchup):
                engine = engine_setup_fn()
                winner = run_game_fn(engine, {0: agent0, 1: agent1}, (i, j))
                if winner == 0:
                    scores0[i] += 1
                elif winner == 1:
                    scores1[j] += 1
    return scores0, scores1
