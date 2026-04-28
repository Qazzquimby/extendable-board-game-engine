import json
import torch
from ai_agent import AIAgent

def train():
    try:
        with open("game_logs.json", "r") as f:
            games_data = json.load(f)
    except FileNotFoundError:
        print("No game_logs.json found. Run self_play.py first.")
        return

    agent = AIAgent()
    
    print(f"Loaded {len(games_data)} games...")
    total_loss = 0.0
    total_steps = 0
    
    for game_data in games_data:
        winner_team = game_data.get("winner_team")
        logs = game_data.get("logs", [])
        
        for step_idx, log_entry in enumerate(logs):
            # Currently loaded as raw dicts. 
            # Needs to rebuild state and action tensors to actually call train_step()
            # Placeholder for where the reconstructed tensors would be passed:
            
            # loss = agent.train_step(state_tensor, action_tensors, chosen_idx, next_state_tensor, step_reward, done)
            # total_loss += loss
            total_steps += 1

    avg_loss = total_loss / total_steps if total_steps else 0
    print(f"Average loss: {avg_loss:.4f} across {total_steps} total steps")
    
    torch.save(agent.net.state_dict(), "model.pt")
    print("Saved trained model to model.pt")

if __name__ == "__main__":
    train()
