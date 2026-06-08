import json
from pathlib import Path
from typing import List, TYPE_CHECKING

from abilities import (
    Ability,
)
from aimings import MultipleAiming
from ai.feature_definitions import NEW_LOCATION

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity


def get_feature_catalog(engine: "Engine", feature_catalog_file_path: Path) -> List[str]:
    if feature_catalog_file_path.exists():
        print("Loading feature catalog from cache.")
        with open(feature_catalog_file_path, "r") as f:
            feature_catalog = json.load(f)
    else:
        print("Generating feature catalog.")
        feature_catalog = create_new_feature_catalog(engine)
        with open(feature_catalog_file_path, "w") as f:
            json.dump(feature_catalog, f, indent=2)
    return feature_catalog


def create_new_feature_catalog(engine: "Engine") -> List[str]:
    """
    Generates a list of all possible feature names for a given game setup.
    """
    features = set()
    entities: List["Entity"] = engine.entities

    entity_names = {e.name for e in entities}
    all_abilities: List["Ability"] = []
    for entity in entities:
        if hasattr(entity, "abilities"):
            all_abilities.extend(entity.abilities)

    # Features from PlausibleMoveAndAction
    features.update(NEW_LOCATION.get_all_variants(engine, None, None))

    # Features from _compute_ability_features
    for ability in all_abilities:
        features.add(f"use {ability.name}")
        for target_name in entity_names:
            features.add(f"use {ability.name} targeting {target_name}")
            if isinstance(ability.aiming, MultipleAiming):
                if ability.aiming.aimings:
                    for aiming_name in ability.aiming.aimings.keys():
                        features.add(f"{ability.name} {aiming_name} on {target_name}")

    # Features from instructions
    for ability in all_abilities:
        for instruction in ability.instructions:
            feature_templates = instruction.get_feature_templates()

            for feature_template in feature_templates:
                variants = feature_template.get_all_variants(
                    engine, ability, instruction
                )
                features.update(variants)

    # Distance features
    entity_list = sorted(engine.entities, key=lambda e: e.id)
    for i in range(len(entity_list)):
        for j in range(i + 1, len(entity_list)):
            e1 = entity_list[i]
            e2 = entity_list[j]
            features.add(f"distance_{e1.name}_to_{e2.name}")

    return sorted(list(features))


if __name__ == "__main__":
    from self_play import setup_game

    engine = setup_game()
    feature_catalog = create_new_feature_catalog(engine)
    print("\n".join(feature_catalog))
