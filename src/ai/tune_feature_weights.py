import random
from typing import List, Dict, Callable
import numpy as np


class PlayerPopulation:
    def __init__(
        self,
        population_size: int,
        feature_catalog: List[str],
        initial_weights: Dict[str, float],
    ):
        self.population_size = population_size
        self.feature_catalog = feature_catalog
        self.population = self._initialize_population(initial_weights)

    def _initialize_population(
        self, initial_weights: Dict[str, float]
    ) -> List[Dict[str, float]]:
        population = []
        for _ in range(self.population_size):
            weights = {}
            for feature in self.feature_catalog:
                mean = initial_weights.get(feature, 0.0)
                std_dev = 0.1  # Standard deviation for initial population spread
                weights[feature] = np.random.normal(mean, std_dev)
            population.append(weights)
        return population

    def run_tournament(
        self, engine_setup_fn: Callable, run_game_fn: Callable, agent_class: type
    ):
        scores = {i: 0 for i in range(self.population_size)}

        for i in range(self.population_size):
            for j in range(i + 1, self.population_size):
                agent1 = agent_class(weights=self.population[i])
                agent2 = agent_class(weights=self.population[j])

                # Game 1
                engine1 = engine_setup_fn()
                winner1 = run_game_fn(engine1, {0: agent1, 1: agent2})
                if winner1 == 0:
                    scores[i] += 1
                elif winner1 == 1:
                    scores[j] += 1

                # Game 2 (swapped teams)
                agent1_swapped = agent_class(weights=self.population[i])
                agent2_swapped = agent_class(weights=self.population[j])
                engine2 = engine_setup_fn()
                winner2 = run_game_fn(engine2, {0: agent2_swapped, 1: agent1_swapped})
                if winner2 == 0:
                    scores[j] += 1
                elif winner2 == 1:
                    scores[i] += 1
        return scores

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


# todo unused, unsaved
def tune_weights(
    engine_setup_fn: Callable,
    run_game_fn: Callable,
    agent_class: type,
    initial_weights: Dict[str, float],
    feature_catalog: List[str],
    generations: int = 10,
    population_size: int = 20,
    mutation_rate: float = 0.05,
    mutation_strength: float = 0.1,
    crossover_prob: float = 0.7,
):
    population = PlayerPopulation(population_size, feature_catalog, initial_weights)

    for gen in range(generations):
        print(f"Generation {gen+1}/{generations}")
        scores = population.run_tournament(engine_setup_fn, run_game_fn, agent_class)
        population.evolve(scores, mutation_rate, mutation_strength, crossover_prob)

        best_player_idx = max(scores, key=scores.get, default=0)
        print(
            f"Best player of generation {gen+1} had score {scores.get(best_player_idx, 0)}"
        )

    # Return the weights of the best player from the final generation
    final_scores = population.run_tournament(engine_setup_fn, run_game_fn, agent_class)
    best_player_idx = max(final_scores, key=final_scores.get, default=0)
    return population.population[best_player_idx]
