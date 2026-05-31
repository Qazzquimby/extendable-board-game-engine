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

        def get_entity(id_or_name: Union[int, str]) -> Optional["Entity"]:
            if isinstance(id_or_name, int):
                return entities_by_id.get(id_or_name)
            return entities_by_name.get(id_or_name)

        def hypothetical_hp(entity_id: int) -> Optional[int]:
            entity = entities_by_id.get(entity_id)
            if not entity:
                return None

            damage_key = f"damage_dealt_to_{entity.name}_{entity.id}"
            damage = core_features.get(damage_key, 0)

            heal_key = f"heal_dealt_to_{entity.name}_{entity.id}"
            heal = core_features.get(heal_key, 0)

            return entity.hp - damage + heal

        def num_enemies_hit() -> int:
            hit_enemies = 0
            all_points = set(choice.aiming_result.target_points) | set(
                choice.aiming_result.included_points
            )
            for point in all_points:
                entity = engine.entity_at(point)
                if entity and entity.team != actor.team:
                    hit_enemies += 1
            return hit_enemies

        def target_is_within_dist_of_enemy(dist: int) -> bool:
            if not choice.target:
                return False

            target_pos_key = f"new_location_{choice.target.name}_{choice.target.id}"
            target_pos = core_features.get(target_pos_key, choice.target.pos)
            if not target_pos:
                return False

            enemies = [
                e
                for e in engine.entities
                if e.team != actor.team and e.id != choice.target.id
            ]
            for enemy in enemies:
                enemy_pos_key = f"new_location_{enemy.name}_{enemy.id}"
                enemy_pos = core_features.get(enemy_pos_key, enemy.pos)
                if not enemy_pos:
                    continue
                if engine.grid.get_range(target_pos, enemy_pos) <= dist:
                    return True
            return False

        context = {
            "engine": engine,
            "actor": actor,
            "choice": choice,
            "core_features": core_features,
            "get_entity": get_entity,
            "hypothetical_hp": hypothetical_hp,
            "num_enemies_hit": num_enemies_hit,
            "target_is_within_dist_of_enemy": target_is_within_dist_of_enemy,
            "len": len,
            "sum": sum,
            "min": min,
            "max": max,
        }
        return context


# todo, we want the string to be able to define arbitrary features *without* needing to write in specific context items for them like "target_is_within_dist_of_enemy" which is obviously ridiculous.
