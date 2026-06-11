from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from abilities import Ability, Instruction, UseAnAbilityInstruction
    from engine import Engine


@dataclass
class Feature:
    template: str
    param_domains: Dict[str, Callable[["Engine", Optional["Ability"]], List[str]]]

    def __call__(self, **kwargs: Any) -> str:
        return self.template.format(**kwargs)

    def get_all_variants(
        self,
        engine: "Engine",
        ability: Optional["Ability"],
        instruction: Optional["Instruction"],
    ) -> List[str]:
        import itertools

        param_values = {
            param: domain_func(engine, ability)
            for param, domain_func in self.param_domains.items()
        }

        param_names = list(param_values.keys())
        value_lists = list(param_values.values())

        variants = []
        for combo in itertools.product(*value_lists):
            kwargs = dict(zip(param_names, combo))
            variants.append(self.template.format(**kwargs))
        return variants


# --- Domain Functions ---


def all_entity_names(engine: "Engine", ability: Optional["Ability"]) -> List[str]:
    return sorted([e.name for e in engine.entities])  # todo also cover possible summons


# --- Feature Definitions ---

DAMAGE_DEALT = Feature("damage_dealt_to_{name}", {"name": all_entity_names})
KILLS = Feature("kills_{name}", {"name": all_entity_names})
HEAL_DEALT = Feature("heal_dealt_to_{name}", {"name": all_entity_names})
NEW_LOCATION = Feature("{name}_changed_position", {"name": all_entity_names})


class UseAbilityFeature(Feature):
    def get_all_variants(
        self,
        engine: "Engine",
        ability: "Ability",
        instruction: "UseAnAbilityInstruction",
    ) -> List[str]:
        variants = []
        source_entity = ability.owner
        if not source_entity:
            return []

        for subject_entity in sorted(engine.entities, key=lambda e: e.id):
            if hasattr(subject_entity, "abilities"):
                valid_abilities = subject_entity.abilities
                if instruction.default_only:
                    valid_abilities = [a for a in valid_abilities if a.is_default]

                valid_abilities.sort(key=lambda a: a.name)

                for forced_ability in valid_abilities:
                    variants.append(
                        self.template.format(
                            source_name=source_entity.name,
                            ability_name=forced_ability.name,
                        )
                    )
        return variants


FORCED_USE_ABILITY = UseAbilityFeature(
    "{source_name}_forced_use_ability_is_{ability_name}", {}
)
