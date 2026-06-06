import importlib
import inspect
import json
import re
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

from pydantic import BaseModel, Field

from ai.feature_catalog import create_new_feature_catalog
from ai.llm import Conversation, STRONG_LLM, prompt
from features import FeatureContext

if TYPE_CHECKING:
    from engine import Engine


class FeatureWeight(BaseModel):
    feature: str = Field(..., description="The name of the feature.")
    weight: float = Field(..., description="The weight for this feature.")


class FeatureWeights(BaseModel):
    weights: List[FeatureWeight]


class NewFeature(BaseModel):
    name: str = Field(..., description="A descriptive name for the feature.")
    code: str = Field(
        ...,
        description="The Python code for the feature evaluation function. It must be a single function that takes a 'FeatureContext' as its only argument.",
    )


class NewFeatures(BaseModel):
    features: List[NewFeature]


def get_entity_rules(engine: "Engine") -> str:
    entity_rules_parts = []
    unique_entities = {e.name: e for e in engine.entities}.values()

    for entity in unique_entities:
        rules = f"Entity: {entity.name}\n"
        if hasattr(entity, "abilities"):
            for ability in entity.abilities:
                if hasattr(ability, "text") and ability.text:
                    rules += f"  Ability: {ability.name}\n"
                    rules += f"    {ability.text}\n"
        if hasattr(entity, "modifiers"):
            for modifier in entity.modifiers:
                if hasattr(modifier, "text") and modifier.text:
                    rules += f"  Modifier: {modifier.__class__.__name__}\n"
                    rules += f"    {modifier.text}\n"
        entity_rules_parts.append(rules)

    entity_rules = "\n\n".join(entity_rules_parts)
    return entity_rules


def propose_new_features_for_strategy(
    entity_rules: str, strategy: str, game_setup_id: str
):
    output_dir = Path("feature_packs") / game_setup_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir.parent.joinpath("__init__.py").touch(exist_ok=True)
    output_dir.joinpath("__init__.py").touch(exist_ok=True)

    sanitized_strategy = "".join(
        c for c in strategy if c.isalnum() or c in "_-"
    ).lower()
    output_file = output_dir / f"generated_{sanitized_strategy}.py"
    if output_file.exists():
        return

    feature_gen_conv = Conversation()
    feature_context_code = inspect.getsource(FeatureContext)

    feature_gen_prompt = (
        "Propose choice-features for an AI in a turn-based strategy game.\n"
        "A feature is a python function that evaluates a game state after a potential action and returns a numeric or boolean value.\n"
        "The function signature must be `def my_feature_func(ctx: FeatureContext) -> int | float | bool | None:`\n"
        f"Here are the rules for the entities in the game:\n{entity_rules}\n\n"
        f"Here is the definition of the `FeatureContext` class, which is passed to your function:\n"
        f"```python\n{feature_context_code}\n```\n"
        "Here are some example features:\n"
        "```python\n"
        "def damage_to_enemies(ctx: FeatureContext) -> int:\n"
        "    return sum(ctx.damage_dealt(e) for e in ctx.enemies)\n\n"
        "def enemies_killed(ctx: FeatureContext) -> int:\n"
        "    return sum(1 for e in ctx.enemies if ctx.new_hp(e) is not None and ctx.new_hp(e) <= 0)\n\n"
        "def self_hp(ctx: FeatureContext) -> int | None:\n"
        "    return ctx.new_hp(ctx.actor)\n"
        "```\n\n"
        f"Your task is to propose new features that would be useful for an AI with a '{strategy}' strategy.\n"
        "Provide a descriptive name and the python code for each feature."
    )
    feature_gen_conv.add_message(feature_gen_prompt)

    new_features_response = prompt(
        model=STRONG_LLM,
        messages=feature_gen_conv.messages,
        return_type=NewFeatures,
    )

    if new_features_response:
        with open(output_file, "w") as f:
            f.write("from features import FeatureContext, WeightedFeature\n")
            f.write("from typing import Any, List, Optional, TYPE_CHECKING, Union\n\n")
            f.write("if TYPE_CHECKING:\n")
            f.write("    from choices import PlausibleActionOrMoveAndAction\n")
            f.write("    from engine import Engine\n")
            f.write("    from entities import Entity\n")
            f.write("    from point import Point\n\n")

            func_names_map = {}
            for feature in new_features_response.features:
                match = re.search(r"def\s+([a-zA-Z_]\w*)\s*\(", feature.code)
                if not match:
                    continue
                func_name = match.group(1)
                func_names_map[feature.name] = func_name

                f.write(f"# Feature: {feature.name}\n")
                f.write(feature.code)
                f.write("\n\n")

            f.write("FEATURES = [\n")
            for feature in new_features_response.features:
                if feature.name in func_names_map:
                    f.write(
                        f"    WeightedFeature(name='{feature.name}', eval_func={func_names_map[feature.name]}, weight=0.0),\n"
                    )
            f.write("]\n")


def propose_weights(
    entity_rules: str, feature_catalog: List[str], strategy: str
) -> dict[str, float]:
    conv = Conversation()
    weight_prompt = (
        f"Here are the rules for the entities in the game:\n{entity_rules}\n\n"
        "Provide weights on how often an AI agent should favor actions with certain features in a turn based strategy game. "
        "Only weight features relevant to your strategy. "
        "Positive weights mean the AI should favor actions with that feature, and negative weights avoid. "
        "Absolute top priorities can have weights up to +- 20, while more common priorities should be at or below +- 5. "
        f"Here is the list of all possible features:\n"
        f"{json.dumps(feature_catalog, indent=2)}\n\n"
        f"For your strategy, focus on being *{strategy}*.\n"
        "For each relevant feature, provide the feature name and a weight."
    )
    conv.add_message(weight_prompt)

    response = prompt(
        model=STRONG_LLM,
        messages=conv.messages,
        return_type=FeatureWeights,
    )

    if not response:
        raise ValueError("LLM failed to propose weights.")

    return {fw.feature: fw.weight for fw in response.weights}


def get_proposed_features_and_weights(
    engine: "Engine", strategies: list[str], game_setup_id: str
) -> List[Dict[str, float]]:
    entity_rules = get_entity_rules(engine)

    # Propose features
    for strategy in strategies:
        propose_new_features_for_strategy(entity_rules, strategy, game_setup_id)

    # Build feature catalog
    feature_catalog = create_new_feature_catalog(engine)
    feature_pack_dir = Path("feature_packs") / game_setup_id
    if feature_pack_dir.exists():
        for f in feature_pack_dir.glob("generated_*.py"):
            module_name = f"feature_packs.{game_setup_id}.{f.stem}"
            try:
                module = importlib.import_module(module_name)
                importlib.reload(module)
                if hasattr(module, "FEATURES"):
                    feature_catalog.extend([wf.name for wf in module.FEATURES])
            except ImportError as e:
                print(f"Could not import {module_name}: {e}")
    feature_catalog = sorted(list(set(feature_catalog)))

    all_weights = []
    for strategy in strategies:
        weights = propose_weights(
            entity_rules=entity_rules,
            feature_catalog=feature_catalog,
            strategy=strategy,
        )
        all_weights.append(weights)
    return all_weights
