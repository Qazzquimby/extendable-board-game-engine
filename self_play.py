import json
from engine import RuleBasedAgent
from game_setup import GameSetup
from heroes import MeleeHero
from heroes.axe import Axe
from heroes.necrophos import Necrophos
from heroes.viktoria import Viktoria

if __name__ == "__main__":
    agent = RuleBasedAgent()

    game_setup = GameSetup(
        team0_classes=[Axe, Necrophos],
        team1_classes=[MeleeHero, Viktoria],
        grid_size=5,
    )
    engine = game_setup.create_engine(agents={0: agent, 1: agent})
    game_log = engine.run_game()
    log_json = json.dumps([game_log.model_dump()])
    print(log_json)
