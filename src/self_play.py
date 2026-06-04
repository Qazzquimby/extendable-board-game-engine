import json
from pathlib import Path

from tqdm import tqdm

from ai.feature_agent import get_example_feature_agent
from engine import Engine
from grid import Grid
from heroes import MeleeHero, RangedHero
from heroes.axe import Axe
from point import Point

# POSSIBLE_HEROES = [MeleeHero, RangedHero]
POSSIBLE_HEROES = [
    # MeleeHero,
    # RangedHero,
    Axe,
]

grid_size = 5


def setup_game():
    engine = Engine(grid=Grid(grid_size, grid_size), agents={0: agent, 1: agent})
    team_0_classes = [Axe]
    team_1_classes = [MeleeHero, RangedHero]

    for i, entity in enumerate(team_0_classes):
        team_0_classes[i](engine=engine, pos=Point(0, i), team=0)

    for i, entity in enumerate(team_1_classes):
        team_1_classes[i](
            engine=engine, pos=Point(grid_size - 1, grid_size - (i + 1)), team=1
        )
    engine.finalize_setup()
    return engine


if __name__ == "__main__":
    agent = get_example_feature_agent()
    all_games = []
    num_games = 10  # _000
    existing_game_logs = Path("../game_logs").glob("*.json")
    existing_game_log_Numbers = [int(f.stem) for f in existing_game_logs]

    file_idx = max(existing_game_log_Numbers) + 1 if existing_game_log_Numbers else 0
    for i in tqdm(range(num_games)):
        engine = setup_game()
        game_log = engine.run_game()
        all_games.append(game_log)

        if len(all_games) == 10:
            filename = f"../game_logs/{file_idx}.json"
            with open(filename, "w") as f:
                json.dump(
                    [game.model_dump(mode="json") for game in all_games], f, indent=2
                )
            all_games = []
            file_idx += 1

    if all_games:
        filename = f"game_logs/{file_idx}.json"
        with open(filename, "w") as f:
            json.dump([game.model_dump(mode="json") for game in all_games], f, indent=2)
        print(f"Saved {len(all_games)} games to {filename}")
