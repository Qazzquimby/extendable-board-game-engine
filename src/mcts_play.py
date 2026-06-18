import json
from ai.mcts import MCTSAgent
from game_setup import GameSetup
from heroes import MeleeHero, RangedHero
from heroes.axe import Axe
from heroes.viktoria import Viktoria

if __name__ == "__main__":
    agent = MCTSAgent()

    game_setup = GameSetup(
        team0_classes=[Axe, RangedHero],
        team1_classes=[MeleeHero, Viktoria],
        grid_size=5,
    )
    engine = game_setup.create_engine(agents={0: agent, 1: agent})
    game_log = engine.run_game()
    log_json = json.dumps([game_log.model_dump()])
    print(log_json)
