from typing import List, TYPE_CHECKING

from abilities import (
    Ability,
    UseAnAbilityInstruction,
    Instruction,
)
from aimings import MultipleAiming

if TYPE_CHECKING:
    from engine import Engine
    from entities import Entity


def get_feature_catalog(engine: "Engine") -> List[str]:
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
    for name in entity_names:
        features.add(f"new_location_{name}")

    # Features from _compute_ability_features
    for ability in all_abilities:
        features.add(f"use {ability.name}")
        for target_name in entity_names:
            features.add(f"{ability.name} on {target_name}")
            if isinstance(ability.aiming, MultipleAiming):
                if ability.aiming.aimings:
                    for aiming_name in ability.aiming.aimings.keys():
                        features.add(f"{ability.name} {aiming_name} on {target_name}")

    # Features from instructions
    for ability in all_abilities:
        for instruction in ability.instructions:
            templates = instruction.get_feature_templates()

            for template in templates:
                if isinstance(instruction, UseAnAbilityInstruction):
                    source_entity = ability.owner
                    if not source_entity:
                        continue
                    for subject_entity in entities:
                        if hasattr(subject_entity, "abilities"):
                            valid_abilities = subject_entity.abilities
                            if instruction.default_only:
                                valid_abilities = [
                                    a for a in valid_abilities if a.is_default
                                ]
                            for forced_ability in valid_abilities:
                                features.add(
                                    template.format(
                                        source_name=source_entity.name,
                                        ability_name=forced_ability.name,
                                    )
                                )
                elif "{name}" in template:
                    for name in entity_names:
                        features.add(template.format(name=name))

    # Distance features
    entity_list = sorted(engine.entities, key=lambda e: e.id)
    for i in range(len(entity_list)):
        for j in range(i + 1, len(entity_list)):
            e1 = entity_list[i]
            e2 = entity_list[j]
            features.add(f"distance_{e1.name}_to_{e2.name}")

    return sorted(list(features))
