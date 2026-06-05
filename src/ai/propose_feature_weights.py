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
    conv = Conversation()

    # TODO needs to see rules for all entities. See axe definition for text on modifiers and abilities
    # TODO first have each 'strategy' llm create new features, (maybe dedup somehow?)
    #  These need to create files that go in the feature packs folder. They'll need sufficient context to write the code for those files.
    #  then the the below weight proposals on the set of all features.

    conv.add_message(
        "Provide weights on how often an AI agent should favor actions with certain features in a turn based strategy game. "
        "Only weight features relevant to your strategy. "
        "Positive weights mean the AI should favor actions with that feature, and negative weights avoid. "
        "Absolute top priorities can have weights up to +- 20, while more common priorities should be at or below +- 5. "
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
