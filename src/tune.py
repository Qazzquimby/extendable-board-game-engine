import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Type, Dict

from ai.feature_agent import FeatureWeightedAgent
from ai.feature_catalog import get_feature_catalog
from ai.propose_feature_weights import propose_feature_weights
from ai.tune_feature_weights import PlayerPopulation
from engine import Engine
from entities import Entity
from grid import Grid
from heroes import MeleeHero, RangedHero
from heroes.axe import Axe
from point import Point


@dataclass
class GameSetup:
    team0_classes: List[Type[Entity]]
    team1_classes: List[Type[Entity]]
    grid_size: int = 5

    def get_id(self) -> str:
        team0_names = sorted([cls.__name__ for cls in self.team0_classes])
        team1_names = sorted([cls.__name__ for cls in self.team1_classes])
        return (
            f"g{self.grid_size}_t0_{'_'.join(team0_names)}_vs_t1_{'_'.join(team1_names)}"
        )

    def create_engine(self) -> Engine:
        engine = Engine(grid=Grid(self.grid_size, self.grid_size))

        for i, entity_class in enumerate(self.team0_classes):
            entity_class(engine=engine, pos=Point(0, i), team=0)

        for i, entity_class in enumerate(self.team1_classes):
            entity_class(
                engine=engine,
                pos=Point(self.grid_size - 1, self.grid_size - (i + 1)),
                team=1,
            )
        engine.finalize_setup()
        return engine


def tune_strategy(
    game_setup: GameSetup,
    strategy: str,
    generations: int = 10,
    population_size: int = 20,
    mutation_rate: float = 0.05,
    mutation_strength: float = 0.1,
    crossover_prob: float = 0.7,
):
    # Caching paths
    tuning_dir = Path(f"../tuning_results/{game_setup.get_id()}/{strategy}")
    tuning_dir.mkdir(parents=True, exist_ok=True)

    feature_catalog_file = tuning_dir / "feature_catalog.json"
    initial_weights_file = tuning_dir / "initial_weights.json"

    # 1. Get/Cache Feature Catalog
    if feature_catalog_file.exists():
        print("Loading feature catalog from cache.")
        with open(feature_catalog_file, "r") as f:
            feature_catalog = json.load(f)
    else:
        print("Generating feature catalog.")
        dummy_engine = game_setup.create_engine()
        feature_catalog = get_feature_catalog(dummy_engine)
        with open(feature_catalog_file, "w") as f:
            json.dump(feature_catalog, f, indent=2)

    # 2. Get/Cache Initial Weights
    if initial_weights_file.exists():
        print("Loading initial weights from cache.")
        with open(initial_weights_file, "r") as f:
            initial_weights = json.load(f)
    else:
        print("Proposing initial weights with LLM.")
        initial_weights = propose_feature_weights(feature_catalog, strategy)
        with open(initial_weights_file, "w") as f:
            json.dump(initial_weights, f, indent=2)

    # --- Tuning Loop ---
    for gen in range(generations):
        print(f"Generation {gen + 1}/{generations}")
        gen_dir = tuning_dir / f"gen_{gen}"
        gen_dir.mkdir(exist_ok=True)

        population_file = gen_dir / "population.json"
        scores_file = gen_dir / "scores.json"
        game_logs_dir = gen_dir / "game_logs"
        game_logs_dir.mkdir(exist_ok=True)

        # 3. Setup/Load Population for the current generation
        if population_file.exists():
            print(f"Loading population for gen {gen} from cache.")
            population = PlayerPopulation.load(population_file, feature_catalog)
        elif gen == 0:
            print("Initializing population for gen 0.")
            population = PlayerPopulation(
                population_size, feature_catalog, initial_weights
            )
            population.save(population_file)
        else:
            # Evolve from previous generation
            print(f"Evolving population for gen {gen}.")
            prev_gen_dir = tuning_dir / f"gen_{gen - 1}"
            prev_population_file = prev_gen_dir / "population.json"
            prev_scores_file = prev_gen_dir / "scores.json"

            if not prev_population_file.exists() or not prev_scores_file.exists():
                raise FileNotFoundError(
                    f"Cannot evolve for gen {gen}: missing population or scores from gen {gen - 1}"
                )

            population = PlayerPopulation.load(prev_population_file, feature_catalog)
            with open(prev_scores_file, "r") as f:
                scores = {int(k): v for k, v in json.load(f).items()}

            population.evolve(
                scores, mutation_rate, mutation_strength, crossover_prob
            )
            population.save(population_file)

        # 4. Run tournament if scores are not cached
        if scores_file.exists():
            print(f"Loading scores for gen {gen} from cache.")
            with open(scores_file, "r") as f:
                scores = json.load(f)
        else:
            print(f"Running tournament for gen {gen}.")

            def run_game_fn(engine, agents, player_indices):
                engine.agents = agents
                game_log = engine.run_game()
                p1_idx, p2_idx = player_indices
                log_path = game_logs_dir / f"p{p1_idx}_vs_p{p2_idx}.json"
                with open(log_path, "w") as f:
                    json.dump(game_log.model_dump(mode="json"), f, indent=2)
                return game_log.winner_team

            scores = population.run_tournament(
                engine_setup_fn=game_setup.create_engine,
                run_game_fn=run_game_fn,
                agent_class=FeatureWeightedAgent,
            )
            with open(scores_file, "w") as f:
                json.dump(scores, f, indent=2)

        best_player_idx = max(scores, key=scores.get, default=0)
        print(
            f"Best player of generation {gen + 1} had score {scores.get(best_player_idx, 0)}"
        )

    # After all generations, find the best player overall
    final_gen_dir = tuning_dir / f"gen_{generations - 1}"
    final_population_file = final_gen_dir / "population.json"
    final_scores_file = final_gen_dir / "scores.json"

    population = PlayerPopulation.load(final_population_file, feature_catalog)
    with open(final_scores_file, "r") as f:
        final_scores = {int(k): v for k, v in json.load(f).items()}

    best_player_idx = max(final_scores, key=final_scores.get, default=0)
    best_weights = population.population[best_player_idx]

    best_weights_file = tuning_dir / "best_weights.json"
    with open(best_weights_file, "w") as f:
        json.dump(best_weights, f, indent=2)

    print(f"\nTuning complete. Best weights saved to {best_weights_file}")
    return best_weights


if __name__ == "__main__":
    # Example usage
    game_setup = GameSetup(
        team0_classes=[Axe],
        team1_classes=[MeleeHero, RangedHero],
    )
    tune_strategy(game_setup, strategy="aggressive", generations=2)
