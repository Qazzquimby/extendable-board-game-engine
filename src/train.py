import torch
from ai_agent import AIAgent

def train():
    try:
        logs = torch.load("game_logs.pt")
    except FileNotFoundError:
        print("No game_logs.pt found. Run self_play.py first.")
        return

    agent = AIAgent()
    
    print(f"Training on {len(logs)} steps...")
    total_loss = 0.0
    
    for state, actions, chosen_idx, next_state, reward, done in logs:
        loss = agent.train_step(state, actions, chosen_idx, next_state, reward, done)
        total_loss += loss

    avg_loss = total_loss / len(logs) if logs else 0
    print(f"Average loss: {avg_loss:.4f}")
    
    torch.save(agent.net.state_dict(), "model.pt")
    print("Saved trained model to model.pt")

if __name__ == "__main__":
    train()
