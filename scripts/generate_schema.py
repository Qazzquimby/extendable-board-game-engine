import json
import sys
import os

# Add src to path to allow importing schemas
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

from schemas import GameLog

if __name__ == "__main__":
    schema = GameLog.model_json_schema()
    with open("schema.json", "w") as f:
        json.dump(schema, f, indent=2)
    print("Generated schema.json")
