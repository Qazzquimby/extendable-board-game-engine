import json
import random
from pathlib import Path
from typing import List, Dict, Callable

import numpy as np

from ai.feature_agent import FeatureWeightedAgent
from features import WeightedFeature


class PlayerPopulation:
    def __init__(
        self,
        population_size: int,
        feature_catalog: List[WeightedFeature],
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
                mean, std_dev = initial_weight_stats.get(feature.name, (0.0, 0.1))
                if std_dev == 0.0:
                    std_dev = 0.1
                weights[feature.name] = np.random.normal(mean, std_dev * 1.5)
            population.append(weights)
        return population

    def save(self, path: Path):
        with open(path, "w") as f:
            json.dump(self.population, f, indent=2)

    @classmethod
    def load(cls, path: Path, feature_catalog: List[WeightedFeature]):
        with open(path, "r") as f:
            population_data = json.load(f)
        instance = cls(len(population_data), feature_catalog)
        instance.population = population_data
        return instance

    def evolve(
        self,
        scores: Dict[int, float],
        mutation_rate: float,
        mutation_strength: float,
        crossover_prob: float,
    ):
        # Tournament selection
        new_population = []
        for i in range(self.population_size):
            p1_idx = i
            p2_idx = random.sample(range(self.population_size), k=1)[0]

            if scores.get(p1_idx, 0) > scores.get(p2_idx, 0):
                winner_idx = p1_idx
            else:
                winner_idx = p2_idx
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
            keys = [f.name for f in self.feature_catalog]
            random.shuffle(keys)
            crossover_point = random.randint(1, len(keys) - 1)
            for i in range(crossover_point):
                key = keys[i]
                child1[key], child2[key] = child2.get(key, 0), child1.get(key, 0)
        return child1, child2

    def _mutate(self, weights: Dict, rate: float, strength: float):
        for key in weights:
            if random.random() < rate:
                old_weight = weights.get(key, 0)
                delta = np.random.normal(0, max(0.1, old_weight / 3))
                weights[key] = old_weight + delta


def run_tournament(
    population0: PlayerPopulation,
    population1: PlayerPopulation,
    engine_setup_fn: Callable,
    run_game_fn: Callable,
    num_games_per_matchup: int = 2,
):
    scores0 = {i: 0 for i in range(population0.population_size)}
    scores1 = {i: 0 for i in range(population1.population_size)}
    
    elo0 = {i: 1000.0 for i in range(population0.population_size)}
    elo1 = {i: 1000.0 for i in range(population1.population_size)}
    
    K = 32

    for i in range(population0.population_size):
        for j in range(population1.population_size):
            weights0 = population0.population[i]
            features0 = [
                WeightedFeature(
                    name=f.name, eval_func=f.eval_func, weight=weights0.get(f.name, 0.0)
                )
                for f in population0.feature_catalog
            ]
            agent0 = FeatureWeightedAgent(weighted_features=features0)

            weights1 = population1.population[j]
            features1 = [
                WeightedFeature(
                    name=f.name, eval_func=f.eval_func, weight=weights1.get(f.name, 0.0)
                )
                for f in population1.feature_catalog
            ]
            agent1 = FeatureWeightedAgent(weighted_features=features1)

            for _ in range(num_games_per_matchup):
                engine = engine_setup_fn()
                winner = run_game_fn(engine, {0: agent0, 1: agent1}, (i, j))
                
                actual0 = 0.5
                actual1 = 0.5
                if winner == 0:
                    scores0[i] += 1
                    actual0 = 1.0
                    actual1 = 0.0
                elif winner == 1:
                    scores1[j] += 1
                    actual0 = 0.0
                    actual1 = 1.0
                
                expected0 = 1 / (1 + 10 ** ((elo1[j] - elo0[i]) / 400))
                expected1 = 1 / (1 + 10 ** ((elo0[i] - elo1[j]) / 400))
                
                elo0[i] += K * (actual0 - expected0)
                elo1[j] += K * (actual1 - expected1)
                
    return scores0, scores1, elo0, elo1
