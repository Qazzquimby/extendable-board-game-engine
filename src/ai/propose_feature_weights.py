import ast
import importlib
import inspect
import json
import re
from pathlib import Path
from typing import Dict, List, TYPE_CHECKING

from pydantic import BaseModel, Field

from ai.feature_catalog import create_new_feature_catalog
from ai.llm import Conversation, STRONG_LLM, prompt
from choices import PlausibleMoveAndAction
from entities import Entity
from features import FeatureContext
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


def get_definitions(obj):
    source = inspect.getsource(obj)
    tree = ast.parse(source)

    defs = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ast.unparse(node.args)
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"

            try:
                return_type = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            except AttributeError:
                return_type = ""

            defs.append(f"\t{prefix} {node.name}({args}){return_type}")
        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            defs.append(
                f"class {node.name}({bases})" if bases else f"class {node.name}"
            )

    return defs


def get_general_rules_prompt():
    return """\
Teams start far away from each other.
The game ends after round 6.
"""


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
    feature_context_code = get_definitions(FeatureContext)
    entity_context = get_definitions(Entity)
    engine_context = get_definitions(Engine)
    choice_context = get_definitions(PlausibleMoveAndAction)

    # todo make sure plausbiblemoveandaction move_pos is included
    feature_gen_prompt = (
        "Propose choice-features for an AI in a turn-based strategy game.\n"
        "A feature is a python function that evaluates a game state after a potential action and returns a numeric or boolean value.\n"
        "The function signature must be `def my_feature_func(ctx: FeatureContext) -> int | float | bool | None:`\n"
        f"{get_general_rules_prompt()}\n"
        f"Game entities:\n{entity_rules}\n\n"
        f"Relevant definitions:\n"
        f"```python\n{feature_context_code}\n\n{choice_context}\n\n{entity_context}\n\n{engine_context}```\n"
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
        "Provide a descriptive name and the python code for each feature. "
        "Features names should be very clear, as users won't be able to see the body. "
        "Never write stub functions.",
    )
    feature_gen_conv.add_message(feature_gen_prompt)
    # todo improve prompting, no stub functions, name should literally describe behavior

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
        "Provide weights on how often an AI agent should favor actions with certain features in a turn based strategy game. "
        "Only weight features relevant to your strategy. "
        "Positive weights mean the AI should favor actions with that feature, and negative weights avoid. "
        "Absolute top priorities can have weights up to +- 20, while more common priorities should be at or below +- 5. "
        f"{get_general_rules_prompt()}\n"
        f"Game entities:\n{entity_rules}\n\n"
        f"All possible features:\n"
        f"{json.dumps(feature_catalog, indent=2)}\n\n"
        f"For your strategy, focus on being *{strategy}*.\n"
        f"Make sure that your features differentiate locations after moving (actor.move_pos), or the actor would behave randomly when no one is in range.\n"
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


def ensure_features_proposed(
    engine: "Engine", strategies: List[str], game_setup_id: str
):
    entity_rules = get_entity_rules(engine)
    for strategy in strategies:
        propose_new_features_for_strategy(entity_rules, strategy, game_setup_id)


def load_extended_feature_catalog(engine: "Engine", game_setup_id: str) -> List[str]:
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
    return sorted(list(set(feature_catalog)))


def get_proposed_weights_for_strategies(
    engine: "Engine",
    feature_catalog: List[str],
    strategies: List[str],
    game_setup_id: str,
) -> List[Dict[str, float]]:
    entity_rules = get_entity_rules(engine)
    all_weights = []

    weights_dir = Path("feature_packs") / game_setup_id / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)

    for strategy in strategies:
        sanitized_strategy = "".join(
            c for c in strategy if c.isalnum() or c in "_-"
        ).lower()
        weights_file = weights_dir / f"{sanitized_strategy}_weights.json"

        if weights_file.exists():
            with open(weights_file, "r") as f:
                weights = json.load(f)
        else:
            weights = propose_weights(entity_rules, feature_catalog, strategy)
            with open(weights_file, "w") as f:
                json.dump(weights, f, indent=2)

        all_weights.append(weights)

    return all_weights
