import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, TYPE_CHECKING

import numpy as np

from ai.feature_agent import get_all_features
from ai.propose_feature_weights import (
    ensure_features_proposed,
    get_proposed_weights_for_strategies,
    load_extended_feature_catalog,
)
from ai.tune_feature_weights import PlayerPopulation, run_tournament
from features import WeightedFeature
from game_setup import GameSetup
from heroes import MeleeHero, RangedHero
from heroes.axe import Axe

if TYPE_CHECKING:
    from engine import Engine

TEAM_0_DIR_NAME = "team0"
TEAM_1_DIR_NAME = "team1"
TEAM_DIR_NAMES = [TEAM_0_DIR_NAME, TEAM_1_DIR_NAME]


@dataclass
class TuningConfig:
    game_setup: GameSetup
    strategies: List[str]
    generations: int = 10
    population_size: int = 20
    mutation_rate: float = 0.05
    mutation_strength: float = 0.1
    crossover_prob: float = 0.7


def _get_or_create_initial_weight_stats(
    engine: "Engine",
    game_setup_id: str,
    tuning_dir: Path,
    feature_catalog_names: List[str],
    strategies: List[str],
) -> Dict[str, Tuple[float, float]]:
    initial_stats_file = tuning_dir / "initial_weight_stats.json"
    if initial_stats_file.exists():
        print(f"Loading initial weight stats from {initial_stats_file}")
        with open(initial_stats_file, "r") as f:
            return json.load(f)

    print("Proposing initial weights with LLM using strategies:", strategies)
    all_proposed_weights = get_proposed_weights_for_strategies(
        engine=engine,
        feature_catalog=feature_catalog_names,
        strategies=strategies,
        game_setup_id=game_setup_id,
    )

    feature_stats: Dict[str, Tuple[float, float]] = {}
    for feature in feature_catalog_names:
        weights_for_feature = [w.get(feature, 0.0) for w in all_proposed_weights]
        if weights_for_feature:
            mean = float(np.mean(weights_for_feature))
            std_dev = float(np.std(weights_for_feature))
            feature_stats[feature] = (mean, std_dev)

    with open(initial_stats_file, "w") as f:
        json.dump(feature_stats, f, indent=2)

    return feature_stats


class Tuner:
    def __init__(
        self,
        config: TuningConfig,
        base_tuning_dir: Path,
        feature_catalog: List[WeightedFeature],
        initial_stats_list: List[Dict[str, Tuple[float, float]]],
        team_tuning_dirs: List[Path],
    ):
        self.config = config
        self.base_tuning_dir = base_tuning_dir
        self.feature_catalog = feature_catalog
        self.initial_stats_list = initial_stats_list
        self.team_tuning_dirs = team_tuning_dirs
        self.populations: List[PlayerPopulation] = []
        self.scores_list: List[Dict[int, float]] = []

    def run(self):
        for gen in range(self.config.generations):
            print(f"Generation {gen + 1}/{self.config.generations}")
            self.run_generation(gen)
        self.save_best_weights()

    def run_generation(self, gen: int):
        gen_dirs = [d / f"gen_{gen}" for d in self.team_tuning_dirs]
        for gen_dir in gen_dirs:
            gen_dir.mkdir(exist_ok=True)

        self.populations = self._get_or_evolve_populations(gen, gen_dirs)
        self.scores_list = self._get_or_run_tournament(gen, gen_dirs)

        for i, scores in enumerate(self.scores_list):
            best_player_idx = max(scores, key=scores.get, default=0)
            print(
                f"Best player of gen {gen} for team {i}: score {scores.get(best_player_idx, 0)}"
            )

    def _get_or_evolve_populations(
        self, gen: int, gen_dirs: List[Path]
    ) -> List[PlayerPopulation]:
        populations = []
        for i, team_tuning_dir in enumerate(self.team_tuning_dirs):
            population_file = gen_dirs[i] / "population.json"
            if population_file.exists():
                print(f"Loading population for team {i} gen {gen} from cache.")
                pop = PlayerPopulation.load(population_file, self.feature_catalog)
            elif gen == 0:
                print(f"Initializing population for team {i} gen 0.")
                pop = PlayerPopulation(
                    self.config.population_size,
                    self.feature_catalog,
                    self.initial_stats_list[i],
                )
                pop.save(population_file)
            else:
                print(f"Evolving population for team {i} gen {gen}.")
                prev_gen_dir = team_tuning_dir / f"gen_{gen - 1}"
                prev_pop_file = prev_gen_dir / "population.json"
                prev_scores_file = prev_gen_dir / "scores.json"

                if not prev_pop_file.exists() or not prev_scores_file.exists():
                    raise FileNotFoundError(f"Missing data for evolution for team {i}")

                pop = PlayerPopulation.load(prev_pop_file, self.feature_catalog)
                with open(prev_scores_file, "r") as f:
                    scores = {int(k): v for k, v in json.load(f).items()}
                pop.evolve(
                    scores,
                    self.config.mutation_rate,
                    self.config.mutation_strength,
                    self.config.crossover_prob,
                )
                pop.save(population_file)
            populations.append(pop)
        return populations

    def _get_or_run_tournament(
        self, gen: int, gen_dirs: List[Path]
    ) -> List[Dict[int, float]]:
        scores_files = [d / "scores.json" for d in gen_dirs]
        if all(f.exists() for f in scores_files):
            print(f"Loading scores for gen {gen} from cache.")
            scores_list = []
            for scores_file in scores_files:
                with open(scores_file, "r") as f:
                    scores_list.append({int(k): v for k, v in json.load(f).items()})
            return scores_list

        print(f"Running tournament for gen {gen}.")
        game_logs_dir = self.base_tuning_dir / f"gen_{gen}_game_logs"
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
            self.populations[0],
            self.populations[1],
            engine_setup_fn=self.config.game_setup.create_engine,
            run_game_fn=run_game_fn,
        )
        scores_list = [scores0, scores1]
        for i, scores in enumerate(scores_list):
            with open(scores_files[i], "w") as f:
                json.dump(scores, f, indent=2)
        return scores_list

    def save_best_weights(self):
        for i, (pop, scores, tuning_dir) in enumerate(
            zip(self.populations, self.scores_list, self.team_tuning_dirs)
        ):
            if not pop or not scores:
                print(
                    f"No scores available for team {i}, skipping save of best weights."
                )
                continue
            best_player_idx = max(scores, key=scores.get, default=0)
            best_weights = pop.population[best_player_idx]
            best_weights_file = tuning_dir / "best_weights.json"
            with open(best_weights_file, "w") as f:
                json.dump(best_weights, f, indent=2)
            print(f"Best weights for team {i} saved to {best_weights_file}")


def tune_weights(config: TuningConfig):
    game_setup_id = config.game_setup.get_id()
    base_tuning_dir = Path(f"../tuning_results/{game_setup_id}")
    base_tuning_dir.mkdir(parents=True, exist_ok=True)

    dummy_engine = config.game_setup.create_engine()

    ensure_features_proposed(dummy_engine, config.strategies, game_setup_id)

    feature_catalog_file_path = base_tuning_dir / "feature_catalog.json"
    if feature_catalog_file_path.exists():
        with open(feature_catalog_file_path, "r") as f:
            feature_catalog_names = json.load(f)
    else:
        feature_catalog_names = load_extended_feature_catalog(
            dummy_engine, game_setup_id
        )
        with open(feature_catalog_file_path, "w") as f:
            json.dump(feature_catalog_names, f, indent=2)

    feature_catalog = get_all_features(game_setup_id=game_setup_id)

    team_tuning_dirs = [
        base_tuning_dir / team_dir_name for team_dir_name in TEAM_DIR_NAMES
    ]
    initial_stats_list = []
    for team_tuning_dir in team_tuning_dirs:
        team_tuning_dir.mkdir(exist_ok=True)
        initial_stats = _get_or_create_initial_weight_stats(
            engine=dummy_engine,
            game_setup_id=game_setup_id,
            tuning_dir=team_tuning_dir,
            feature_catalog_names=feature_catalog_names,
            strategies=config.strategies,
        )
        initial_stats_list.append(initial_stats)

    tuner = Tuner(
        config=config,
        base_tuning_dir=base_tuning_dir,
        feature_catalog=feature_catalog,
        initial_stats_list=initial_stats_list,
        team_tuning_dirs=team_tuning_dirs,
    )
    tuner.run()


if __name__ == "__main__":
    # Example usage
    game_setup = GameSetup(
        team0_classes=[Axe],
        team1_classes=[MeleeHero, RangedHero],
    )
    config = TuningConfig(
        game_setup=game_setup,
        generations=10,
        population_size=4,
        strategies=["aggressive", "careful"],
    )
    # optimal, clever, combo-oriented, balanced

    tune_weights(config)
