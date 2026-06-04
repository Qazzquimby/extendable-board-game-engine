from typing import List, TYPE_CHECKING

from abilities import (
    Ability,
    DamageInstruction,
    HealInstruction,
    TeleportInstruction,
    UseAnAbilityInstruction,
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
    # ID should have been removed from features? Was it not? Please remove it.
    entity_name_ids = {f"{e.name}_{e.id}" for e in entities}
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
            for name_id in entity_name_ids:
                if isinstance(instruction, DamageInstruction):
                    features.add(f"damage_dealt_to_{name_id}")
                    features.add(f"kills_{name_id}")
                elif isinstance(instruction, HealInstruction):
                    features.add(f"heal_dealt_to_{name_id}")
                elif isinstance(instruction, TeleportInstruction):
                    features.add(f"new_location_{name_id}")

    # TODO this is obviously not scalable enough. Any time any character writer needs a new choice they're going to come here and write a big nested for loop?
    #  This is also all really fragile to string changes
    # Features from UseAnAbilityInstruction
    for ability_with_instruction in all_abilities:
        source_entity = ability_with_instruction.owner
        if not source_entity:
            continue
        for instruction in ability_with_instruction.instructions:
            if isinstance(instruction, UseAnAbilityInstruction):
                for subject_entity in entities:
                    if hasattr(subject_entity, "abilities"):
                        valid_abilities = subject_entity.abilities
                        if instruction.default_only:
                            valid_abilities = [
                                a for a in valid_abilities if a.is_default
                            ]
                        for forced_ability in valid_abilities:
                            features.add(
                                f"{source_entity.name}_forced_use_ability_is_{forced_ability.name}"
                            )

    # Distance features
    entity_list = sorted(engine.entities, key=lambda e: e.id)
    for i in range(len(entity_list)):
        for j in range(i + 1, len(entity_list)):
            e1 = entity_list[i]
            e2 = entity_list[j]
            features.add(f"distance_{e1.name}_to_{e2.name}")

    return sorted(list(features))
