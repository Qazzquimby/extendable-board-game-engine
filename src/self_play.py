import json
from pathlib import Path

from tqdm import tqdm

from ai.feature_agent import get_example_feature_agent
from game_setup import GameSetup
from heroes import MeleeHero, RangedHero
from heroes.axe import Axe

if __name__ == "__main__":
    agent = get_example_feature_agent()
    game_setup = GameSetup(
        team0_classes=[Axe],
        team1_classes=[MeleeHero, RangedHero],
        grid_size=5,
    )
    all_games = []
    num_games = 10  # _000
    existing_game_logs = Path("../game_logs").glob("*.json")
    existing_game_log_Numbers = [int(f.stem) for f in existing_game_logs]

    file_idx = max(existing_game_log_Numbers) + 1 if existing_game_log_Numbers else 0
    for i in tqdm(range(num_games)):
        engine = game_setup.create_engine(agents={0: agent, 1: agent})
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
