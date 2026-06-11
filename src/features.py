from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from choices import PlausibleActionOrMoveAndAction
    from engine import Engine
    from entities import Entity
    from point import Point


class WeightedFeature(BaseModel):
    name: str
    eval_func: Callable[["FeatureContext"], Any] = Field(..., exclude=True)
    weight: float

    class Config:
        arbitrary_types_allowed = True


@dataclass
class FeatureContext:
    engine: "Engine"
    actor: "Entity"
    choice: "PlausibleActionOrMoveAndAction"
    core_features: Dict[str, Any]

    @property
    def allies(self) -> List["Entity"]:
        return [e for e in self.engine.entities if e.team == self.actor.team]

    @property
    def enemies(self) -> List["Entity"]:
        return [e for e in self.engine.entities if e.team != self.actor.team]

    def get_entities_by_name(self, name: str) -> List["Entity"]:
        return [e for e in self.engine.entities if e.name == name]

    def get_entity_by_name(self, name: str) -> Optional["Entity"]:
        entities = self.get_entities_by_name(name)
        return entities[0] if entities else None

    def get_enemies_by_name(self, name: str) -> List["Entity"]:
        return [e for e in self.enemies if e.name == name]

    def get_enemy_by_name(self, name: str) -> Optional["Entity"]:
        entities = self.get_enemies_by_name(name)
        return entities[0] if entities else None

    def get_allies_by_name(self, name: str) -> List["Entity"]:
        return [e for e in self.allies if e.name == name]

    def get_ally_by_name(self, name: str) -> Optional["Entity"]:
        entities = self.get_allies_by_name(name)
        return entities[0] if entities else None

    @property
    def hit_entities(self) -> List["Entity"]:
        hit_spaces = set(self.choice.aiming_result.target_points) | set(
            self.choice.aiming_result.included_points
        )
        return [entity for entity in self.engine.entities if entity.pos in hit_spaces]

    @property
    def hit_allies(self) -> List["Entity"]:
        return [e for e in self.hit_entities if e.team == self.actor.team]

    @property
    def hit_enemies(self) -> List["Entity"]:
        return [e for e in self.hit_entities if e.team != self.actor.team]

    def new_pos(self, entity: "Entity") -> Optional["Point"]:
        if not entity or not entity.pos:
            return None
        pos_key = f"{entity.name}_changed_position"
        return self.core_features.get(pos_key, entity.pos)

    def new_hp(self, entity: "Entity") -> Optional[int]:
        if not entity:
            return None

        damage_key = f"damage_dealt_to_{entity.name}_{entity.id}"
        damage = self.core_features.get(damage_key, 0)

        heal_key = f"heal_dealt_to_{entity.name}_{entity.id}"
        heal = self.core_features.get(heal_key, 0)

        return entity.hp - damage + heal

    def damage_dealt(self, entity: "Entity") -> int:
        if not entity:
            return 0
        damage_key = f"damage_dealt_to_{entity.name}_{entity.id}"
        return self.core_features.get(damage_key, 0)

    def heal_received(self, entity: "Entity") -> int:
        if not entity:
            return 0
        heal_key = f"heal_dealt_to_{entity.name}_{entity.id}"
        return self.core_features.get(heal_key, 0)

    def new_distance(self, e1: "Entity", e2: "Entity") -> Optional[int]:
        p1 = self.new_pos(e1)
        p2 = self.new_pos(e2)
        if p1 and p2:
            return self.engine.grid.get_range(p1, p2)
        return None


class ChoiceFeatureEvaluator:
    def __init__(self, weighted_features: List["WeightedFeature"]):
        self.weighted_features = weighted_features

    def evaluate(
        self,
        engine: "Engine",
        actor: "Entity",
        choice: "PlausibleActionOrMoveAndAction",
        core_features: Dict[str, Any],
    ) -> Dict[str, Any]:
        context = FeatureContext(
            engine=engine,
            actor=actor,
            choice=choice,
            core_features=core_features,
        )

        results = {}
        for weighted_feature in self.weighted_features:
            try:
                result = weighted_feature.eval_func(context)
                results[weighted_feature.name] = result
            except Exception as e:
                print(e)
                results[weighted_feature.name] = None
        return results
