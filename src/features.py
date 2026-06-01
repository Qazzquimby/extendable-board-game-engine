import random
from collections import defaultdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

from pydantic import BaseModel

if TYPE_CHECKING:
    from choices import PlausibleMoveAndAction
    from engine import Engine
    from entities import Entity


class WeightedFeature(BaseModel):
    name: str
    eval_string: str
    weight: float


class ChoiceFeatureEvaluator:
    def __init__(self, weighted_features: List["WeightedFeature"]):
        self.weighted_features = weighted_features
        self.compiled_features = [
            self._compile_feature(f.eval_string) for f in self.weighted_features
        ]

    def _compile_feature(self, feature_string: str):
        try:
            return compile(feature_string, feature_string, "eval")
        except SyntaxError as e:
            raise ValueError(f"Invalid feature expression: {feature_string}") from e

    def evaluate(
        self,
        engine: "Engine",
        actor: "Entity",
        choice: "PlausibleMoveAndAction",
        core_features: Dict[str, Any],
    ) -> Dict[str, Any]:

        context = self._build_context(engine, actor, choice, core_features)

        results = {}
        for i, compiled_feature in enumerate(self.compiled_features):
            weighted_feature = self.weighted_features[i]
            try:
                # Using a restricted set of builtins for some safety.
                result = eval(compiled_feature, {"__builtins__": {}}, context)
                results[weighted_feature.name] = result
            except Exception as e:
                print(e)
                results[weighted_feature.name] = None
        return results

    def _build_context(
        self,
        engine: "Engine",
        actor: "Entity",
        choice: "PlausibleMoveAndAction",
        core_features: Dict[str, Any],
    ) -> Dict[str, Any]:
        entities_by_name = defaultdict(list)
        for entity in engine.entities:
            entities_by_name[entity.name].append(entity)

        allies = [e for e in engine.entities if e.team == actor.team]
        enemies = [e for e in engine.entities if e.team != actor.team]

        def get_entity(name: str) -> Optional["Entity"]:
            entities = entities_by_name.get(name, [])
            if entities:
                return random.choice(entities)
            else:
                return None

        def get_enemy(name: str) -> Optional["Entity"]:
            entities = entities_by_name.get(name, [])
            entities = [e for e in entities if e.team != actor.team]
            if entities:
                return random.choice(entities)
            else:
                return None

        def get_ally(name: str) -> Optional["Entity"]:
            entities = entities_by_name.get(name, [])
            entities = [e for e in entities if e.team == actor.team]
            if entities:
                return random.choice(entities)
            else:
                return None

        def get_hit_entities() -> List["Entity"]:
            hit_spaces = set(choice.aiming_result.target_points) | set(
                choice.aiming_result.included_points
            )
            hit_entities = [
                entity for entity in engine.entities if entity.pos in hit_spaces
            ]
            return hit_entities

        def get_hit_allies() -> List["Entity"]:
            hit_entities = get_hit_entities()
            hit_allies = [e for e in hit_entities if e.team == actor.team]
            return hit_allies

        def get_hit_enemies() -> List["Entity"]:
            hit_entities = get_hit_entities()
            hit_enemies = [e for e in hit_entities if e.team != actor.team]
            return hit_enemies

        def new_pos(entity: "Entity"):
            if not entity or not entity.pos:
                return None
            pos_key = f"new_location_{entity.name}_{entity.id}"
            return core_features.get(pos_key, entity.pos)

        def new_hp(entity: "Entity") -> Optional[int]:
            if not entity:
                return None

            damage_key = f"damage_dealt_to_{entity.name}_{entity.id}"
            damage = core_features.get(damage_key, 0)

            heal_key = f"heal_dealt_to_{entity.name}_{entity.id}"
            heal = core_features.get(heal_key, 0)

            return entity.hp - damage + heal

        def damage_dealt(entity: "Entity") -> int:
            if not entity:
                return 0
            damage_key = f"damage_dealt_to_{entity.name}_{entity.id}"
            return core_features.get(damage_key, 0)

        def heal_received(entity: "Entity") -> int:
            if not entity:
                return 0
            heal_key = f"heal_dealt_to_{entity.name}_{entity.id}"
            return core_features.get(heal_key, 0)

        def new_distance(e1: "Entity", e2: "Entity") -> Optional[int]:
            p1 = new_pos(e1)
            p2 = new_pos(e2)
            if p1 and p2:
                return engine.grid.get_range(p1, p2)
            return None

        context = {
            "engine": engine,
            "actor": actor,
            "choice": choice,
            "core_features": core_features,
            "allies": allies,
            "enemies": enemies,
            "get_entity": get_entity,
            "get_ally": get_ally,
            "get_enemy": get_enemy,
            "get_hit_entities": get_hit_entities(),
            "get_hit_enemies": get_hit_enemies(),
            "get_hit_allies": get_hit_allies(),
            "new_pos": new_pos,
            "new_hp": new_hp,
            "damage_dealt": damage_dealt,
            "heal_received": heal_received,
            "new_distance": new_distance,
            "len": len,
            "sum": sum,
            "min": min,
            "max": max,
        }
        return context
