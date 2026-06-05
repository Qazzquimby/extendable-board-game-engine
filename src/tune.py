import json
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np

from ai.feature_agent import FeatureWeightedAgent
from ai.feature_catalog import get_feature_catalog
from ai.propose_feature_weights import propose_feature_weights
from ai.tune_feature_weights import PlayerPopulation, run_tournament
from game_setup import GameSetup
from heroes import MeleeHero, RangedHero
from heroes.axe import Axe


def _get_or_create_initial_weight_stats(
    tuning_dir: Path, feature_catalog: List[str], strategies: List[str]
) -> Dict[str, Tuple[float, float]]:
    initial_stats_file = tuning_dir / "initial_weight_stats.json"
    if initial_stats_file.exists():
        print(f"Loading initial weight stats from {initial_stats_file}")
        with open(initial_stats_file, "r") as f:
            return json.load(f)

    print("Proposing initial weights with LLM using strategies:", strategies)
    all_proposed_weights = []
    for strategy in strategies:
        weights = propose_feature_weights(feature_catalog, strategy)
        all_proposed_weights.append(weights)

    feature_stats: Dict[str, Tuple[float, float]] = {}
    for feature in feature_catalog:
        weights_for_feature = [w.get(feature, 0.0) for w in all_proposed_weights]
        if weights_for_feature:
            mean = float(np.mean(weights_for_feature))
            std_dev = float(np.std(weights_for_feature))
            feature_stats[feature] = (mean, std_dev)

    with open(initial_stats_file, "w") as f:
        json.dump(feature_stats, f, indent=2)

    return feature_stats


def tune_weights(
    game_setup: GameSetup,
    generations: int = 10,
    population_size: int = 20,
    mutation_rate: float = 0.05,
    mutation_strength: float = 0.1,
    crossover_prob: float = 0.7,
):
    base_tuning_dir = Path(f"../tuning_results/{game_setup.get_id()}")
    base_tuning_dir.mkdir(parents=True, exist_ok=True)

    feature_catalog_file = base_tuning_dir / "feature_catalog.json"
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

    team0_tuning_dir = base_tuning_dir / "team0"
    team1_tuning_dir = base_tuning_dir / "team1"
    team0_tuning_dir.mkdir(exist_ok=True)
    team1_tuning_dir.mkdir(exist_ok=True)

    strategies = ["aggressive", "defensive", "balanced", "opportunistic"]
    initial_stats0 = _get_or_create_initial_weight_stats(
        team0_tuning_dir, feature_catalog, strategies
    )
    initial_stats1 = _get_or_create_initial_weight_stats(
        team1_tuning_dir, feature_catalog, strategies
    )

    population0, population1 = None, None

    for gen in range(generations):
        print(f"Generation {gen + 1}/{generations}")
        gen_dir0 = team0_tuning_dir / f"gen_{gen}"
        gen_dir1 = team1_tuning_dir / f"gen_{gen}"
        gen_dir0.mkdir(exist_ok=True)
        gen_dir1.mkdir(exist_ok=True)

        # Load or create populations
        for i, (pop, initial_stats, gen_dir, tuning_dir) in enumerate(
            [
                (population0, initial_stats0, gen_dir0, team0_tuning_dir),
                (population1, initial_stats1, gen_dir1, team1_tuning_dir),
            ]
        ):
            population_file = gen_dir / "population.json"
            if population_file.exists():
                print(f"Loading population for team {i} gen {gen} from cache.")
                pop = PlayerPopulation.load(population_file, feature_catalog)
            elif gen == 0:
                print(f"Initializing population for team {i} gen 0.")
                pop = PlayerPopulation(population_size, feature_catalog, initial_stats)
                pop.save(population_file)
            else:
                print(f"Evolving population for team {i} gen {gen}.")
                prev_gen_dir = tuning_dir / f"gen_{gen - 1}"
                prev_pop_file = prev_gen_dir / "population.json"
                prev_scores_file = prev_gen_dir / "scores.json"

                if not prev_pop_file.exists() or not prev_scores_file.exists():
                    raise FileNotFoundError(f"Missing data for evolution for team {i}")

                pop = PlayerPopulation.load(prev_pop_file, feature_catalog)
                with open(prev_scores_file, "r") as f:
                    scores = {int(k): v for k, v in json.load(f).items()}
                pop.evolve(scores, mutation_rate, mutation_strength, crossover_prob)
                pop.save(population_file)

            if i == 0:
                population0 = pop
            else:
                population1 = pop

        scores_file0 = gen_dir0 / "scores.json"
        scores_file1 = gen_dir1 / "scores.json"
        if scores_file0.exists() and scores_file1.exists():
            print(f"Loading scores for gen {gen} from cache.")
            with open(scores_file0, "r") as f:
                scores0 = json.load(f)
            with open(scores_file1, "r") as f:
                scores1 = json.load(f)
        else:
            print(f"Running tournament for gen {gen}.")
            game_logs_dir = base_tuning_dir / f"gen_{gen}_game_logs"
            game_logs_dir.mkdir(exist_ok=True)

            def run_game_fn(engine, agents, player_indices):
                engine.agents = agents
                game_log = engine.run_game()
                p0_idx, p1_idx = player_indices
                log_path = game_logs_dir / f"p0_{p0_idx}_vs_p1_{p1_idx}.json"
                with open(log_path, "w") as f:
                    json.dump(game_log.model_dump(mode="json"), f, indent=2)
                return game_log.winner_team

            scores0, scores1 = run_tournament(
                population0,
                population1,
                engine_setup_fn=game_setup.create_engine,
                run_game_fn=run_game_fn,
                agent_class=FeatureWeightedAgent,
            )
            with open(scores_file0, "w") as f:
                json.dump(scores0, f, indent=2)
            with open(scores_file1, "w") as f:
                json.dump(scores1, f, indent=2)

        best_player0_idx = max(scores0, key=scores0.get, default=0)
        best_player1_idx = max(scores1, key=scores1.get, default=0)
        print(
            f"Best player of gen {gen + 1} for team 0: score {scores0.get(best_player0_idx, 0)}"
        )
        print(
            f"Best player of gen {gen + 1} for team 1: score {scores1.get(best_player1_idx, 0)}"
        )

    # Save best weights
    for i, (pop, scores, tuning_dir) in enumerate(
        [
            (population0, scores0, team0_tuning_dir),
            (population1, scores1, team1_tuning_dir),
        ]
    ):
        if not scores:
            print(f"No scores available for team {i}, skipping save of best weights.")
            continue
        best_player_idx = max(scores, key=scores.get, default=0)
        best_weights = pop.population[best_player_idx]
        best_weights_file = tuning_dir / "best_weights.json"
        with open(best_weights_file, "w") as f:
            json.dump(best_weights, f, indent=2)
        print(f"Best weights for team {i} saved to {best_weights_file}")


if __name__ == "__main__":
    # Example usage
    game_setup = GameSetup(
        team0_classes=[Axe],
        team1_classes=[MeleeHero, RangedHero],
    )
    tune_weights(game_setup, generations=2, population_size=4)
