import json
from pathlib import Path

from tqdm import tqdm

from ai.feature_agent import get_example_feature_agent
from ai.mcts import MCTSAgent
from game_setup import GameSetup
from heroes import MeleeHero, RangedHero
from heroes.axe import Axe

if __name__ == "__main__":
    agent = MCTSAgent()

    game_setup = GameSetup(
        team0_classes=[Axe],
        team1_classes=[MeleeHero, RangedHero],
        grid_size=5,
    )
    engine = game_setup.create_engine(agents={0: agent, 1: agent})
    game_log = engine.run_game()
    print("done")
