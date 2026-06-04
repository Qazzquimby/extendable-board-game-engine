import json
from typing import Dict, List

from pydantic import BaseModel, Field

from ai.llm import Conversation, STRONG_LLM, prompt


class FeatureWeight(BaseModel):
    feature: str = Field(..., description="The name of the feature.")
    weight: float = Field(..., description="The weight for this feature.")


class FeatureWeights(BaseModel):
    weights: List[FeatureWeight]


def propose_feature_weights(
    feature_catalog: List[str], strategy: str
) -> Dict[str, float]:
    """
    Uses an LLM to propose starting weights for a list of features based on a strategy.
    """
    conv = Conversation()
    conv.add_message(
        "system",
        "Provide weights on how often an AI agent should favor actions with certain features in a turn based strategy game. "
        "Only weight features relevant to your strategy. "
        "Positive weights mean the AI should favor actions with that feature, and negative weights avoid. "
        "Absolute top priorities can have weights up to +- 20, while more common priorities should be at or below +- 5. ",
    )
    conv.add_message(
        "user",
        f"Here is the list of all possible features:\n"
        f"{json.dumps(feature_catalog, indent=2)}\n\n"
        f"For your strategy, focus on being *{strategy}*.\n"
        "For each relevant feature, provide the feature name and a weight.",
    )

    response = prompt(
        model=STRONG_LLM,
        messages=conv.messages,
        return_type=FeatureWeights,
    )

    if not response:
        raise ValueError("LLM failed to propose weights.")

    return {fw.feature: fw.weight for fw in response.weights}
