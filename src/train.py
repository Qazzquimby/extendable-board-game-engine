import json

from ai_agent import (
    AIAgent,
    get_entity_features,
    get_plausible_action_features,
    PlausibleAction,
)
from engine import Engine, Entity
from abilities import Ability
from schemas import GameLog, EngineState


def state_to_engine(state: EngineState) -> Engine:
    engine = Engine()
    engine.round_num = state.round_num
    engine.current_team = state.current_team

    for ent_state in state.entities:
        ent = Entity(
            engine=engine,
            name=ent_state.name,
            hp=ent_state.hp,
            speed=0,
            pos=ent_state.pos,
            team=ent_state.team,
        )
        ent.id = ent_state.id
        if ent.id == state.active_entity:
            engine.active_entity = ent
    return engine


def train():
    agent = AIAgent()

    try:
        with open("game_logs.json", "r") as f:
            logs_data = json.load(f)
    except FileNotFoundError:
        print("No game_logs.json found. Run self_play.py first.")
        return

    for game_dict in logs_data:
        game = GameLog(**game_dict)
        winner = game.winner_team

        for log in game.logs:
            engine = state_to_engine(log.before_state)
            next_engine = state_to_engine(log.after_state)

            actor = engine.active_entity

            state_tensor = get_entity_features(engine, actor)
            next_state_tensor = get_entity_features(
                next_engine, next_engine.active_entity
            )

            target_ent = None
            if log.action.target is not None:
                for e in engine.entities:
                    if e.id == log.action.target:
                        target_ent = e
                        break

            ability = Ability(name=log.action.ability, targeting=None)
            ability.owner = actor

            action = PlausibleAction(
                move_pos=log.action.move_pos,
                target=target_ent,
                ability=ability,
                movement_name=log.action.movement_name,
            )

            action_tensor = get_plausible_action_features([action])

            # Assign reward based on winner if game is done
            reward = log.reward
            if log.done and winner is not None:
                if actor and actor.team == winner:
                    reward += 1.0
                else:
                    reward -= 1.0

            agent.train_step(
                state_tensor=state_tensor,
                action_tensor=action_tensor,
                chosen_action_idx=0,
                next_state_tensor=next_state_tensor,
                reward=reward,
                done=log.done,
            )

    print("Training complete.")


if __name__ == "__main__":
    train()
