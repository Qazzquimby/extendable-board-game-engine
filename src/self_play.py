import random
import torch
from engine import Engine, DamageEvent
from heroes import MeleeHero, RangedHero
from ai_agent import (
    AIAgent,
    encode_state,
    encode_plausible_action,
    generate_plausible_actions,
)


def run_game():
    engine = Engine()

    # Randomize teams slightly
    team_0_classes = [random.choice([MeleeHero, RangedHero]) for _ in range(2)]
    team_1_classes = [random.choice([MeleeHero, RangedHero]) for _ in range(2)]

    team_0_classes[0](engine, "H1", 10, (0, 0), 0)
    team_0_classes[1](engine, "H2", 10, (0, 1), 0)

    team_1_classes[0](engine, "H3", 10, (9, 9), 1)
    team_1_classes[1](engine, "H4", 10, (9, 8), 1)

    agent = AIAgent()
    logs = []

    # TODO: Replace this simple loop with proper Sequence of Play (Rounds, Turns, Actions)
    for turn in range(50):  # Max 50 turns to prevent infinite loops
        for actor in engine.entities:
            if actor.hp <= 0:
                continue

            state_tensor = encode_state(engine)
            actions = generate_plausible_actions(actor, engine)
            if not actions:
                continue

            action_tensors = [encode_plausible_action(a) for a in actions]

            with torch.no_grad():
                policy_scores, _ = agent.net(state_tensor, action_tensors)
                temperature = 1.0
                probs = torch.softmax(policy_scores / temperature, dim=0)
                chosen_idx = torch.multinomial(probs, 1).item()
                chosen_action = actions[chosen_idx]

            # Execute action (stub implementation)
            # TODO: Replace stub execution with proper Engine event system (MoveAction, StandardAction)
            actor.pos = chosen_action.move_pos
            if chosen_action.ability.name != "Do Nothing":
                DamageEvent(engine, actor, chosen_action.target, 2).resolve()

            # Check win condition
            team_0_alive = any(e.hp > 0 for e in engine.entities if e.team == 0)
            team_1_alive = any(e.hp > 0 for e in engine.entities if e.team == 1)
            done = not (team_0_alive and team_1_alive)

            reward = 0.0
            if done:
                if team_0_alive:
                    reward = 1.0 if actor.team == 0 else -1.0
                elif team_1_alive:
                    reward = 1.0 if actor.team == 1 else -1.0

            next_state_tensor = encode_state(engine)
            logs.append(
                (
                    state_tensor,
                    action_tensors,
                    chosen_idx,
                    next_state_tensor,
                    reward,
                    done,
                )
            )

            if done:
                break
        if done:
            break

    return logs


if __name__ == "__main__":
    all_logs = []
    num_games = 10
    for i in range(num_games):
        print(f"Playing game {i+1}/{num_games}...")
        all_logs.extend(run_game())

    torch.save(all_logs, "game_logs.pt")
    print(f"Saved {len(all_logs)} steps to game_logs.pt")
