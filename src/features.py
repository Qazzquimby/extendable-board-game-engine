from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from choices import PlausibleMoveAndAction
    from engine import Engine
    from entities import Entity


class ChoiceFeatureEvaluator:
    def __init__(self, feature_strings: List[str]):
        self.feature_strings = feature_strings
        self.compiled_features = [
            self._compile_feature(f) for f in self.feature_strings
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
            feature_string = self.feature_strings[i]
            try:
                # Using a restricted set of builtins for some safety.
                result = eval(compiled_feature, {"__builtins__": {}}, context)
                results[feature_string] = result
            except Exception:
                results[feature_string] = None  # Fail gracefully
        return results

    def _build_context(
        self,
        engine: "Engine",
        actor: "Entity",
        choice: "PlausibleMoveAndAction",
        core_features: Dict[str, Any],
    ) -> Dict[str, Any]:

        entities_by_id = {e.id: e for e in engine.entities}
        # This assumes names are unique, which may not be true.
        entities_by_name = {e.name: e for e in engine.entities}

        allies = [e for e in engine.entities if e.team == actor.team]
        enemies = [e for e in engine.entities if e.team != actor.team]

        def get_entity(id_or_name: Union[int, str]) -> Optional["Entity"]:
            if isinstance(id_or_name, int):
                return entities_by_id.get(id_or_name)
            return entities_by_name.get(id_or_name)

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

        context = {
            "engine": engine,
            "actor": actor,
            "choice": choice,
            "core_features": core_features,
            "allies": allies,
            "enemies": enemies,
            "get_entity": get_entity,
            "new_pos": new_pos,
            "new_hp": new_hp,
            "len": len,
            "sum": sum,
            "min": min,
            "max": max,
        }
        return context
