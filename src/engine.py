import random
import copy
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Type, Any, Dict

from grid import Grid
from mod_value import ModValue
from point import Point
from abilities import Ability

# ==========================================
# ENUMS & TYPES
# ==========================================


class EventPhase(Enum):
    BEFORE = auto()
    AFTER = auto()
    QUERY = auto()


# ==========================================
# ROUTER & SUBSCRIPTIONS
# ==========================================


@dataclass
class Subscription:
    modifier: "Modifier"
    event_type: Type
    phase: EventPhase
    target_self: bool
    func: Callable[[Any], None]


class Router:
    def __init__(self) -> None:
        self.subscribers: List[Subscription] = []

    def subscribe(self, modifier: "Modifier") -> None:
        for name in dir(modifier):
            method = getattr(modifier, name)
            if hasattr(method, "_listen_event"):
                self.subscribers.append(
                    Subscription(
                        modifier=modifier,
                        event_type=method._listen_event,
                        phase=method._listen_phase,
                        target_self=method._listen_target_self,
                        func=method,
                    )
                )

    def publish(self, event: Any, phase: EventPhase) -> None:
        for sub in list(self.subscribers):  # iterate copy
            if sub.event_type == type(event) and sub.phase == phase:
                if sub.target_self:
                    target = getattr(event, "target", None)
                    if target != sub.modifier.owner:
                        continue
                sub.func(event)


# ==========================================
# DECORATORS
# ==========================================


def before(event_type: Type, target_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event, func._listen_phase, func._listen_target_self = (
            event_type,
            EventPhase.BEFORE,
            target_self,
        )
        return func

    return decorator


def after(event_type: Type, target_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event, func._listen_phase, func._listen_target_self = (
            event_type,
            EventPhase.AFTER,
            target_self,
        )
        return func

    return decorator


def query(event_type: Type, target_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event, func._listen_phase, func._listen_target_self = (
            event_type,
            EventPhase.QUERY,
            target_self,
        )
        return func

    return decorator


# ==========================================
# CORE ENGINE & ENTITIES
# ==========================================


class Engine:
    def __init__(self, seed: int = 42, grid: Grid = None) -> None:
        self.router = Router()
        self.entities: List["Entity"] = []
        self.rng = random.Random(seed)
        self.round_num: int = 1
        self.current_team: int = 1
        self.grid: Grid = grid
        self.active_entity: Optional["Entity"] = None
        self._next_id: int = 1

    def generate_id(self) -> int:
        res = self._next_id
        self._next_id += 1
        return res

    def add_entity(self, entity: "Entity") -> None:
        self.entities.append(entity)

    def next_turn(self) -> None:
        if not self.entities:
            return
        if self.active_entity is None:
            self.active_entity = self.entities[0]
        else:
            idx = self.entities.index(self.active_entity)
            if idx + 1 < len(self.entities):
                self.active_entity = self.entities[idx + 1]
            else:
                self.active_entity = self.entities[0]
                self.round_num += 1
        self.current_team = self.active_entity.team
        self.active_entity.start_turn()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_num": self.round_num,
            "current_team": self.current_team,
            "active_entity": self.active_entity.id if self.active_entity else None,
            "entities": [e.to_dict() for e in self.entities],
        }

    def clone(self) -> "Engine":
        return copy.deepcopy(self)


class Entity:
    def __init__(
        self, engine: Engine, name: str, hp: int, speed: int, pos: Point, team: int
    ):
        self.engine = engine
        self.id = self.engine.generate_id()
        self.set = "development"
        self.name = name

        self.hp = hp
        self.speed = speed

        self.pos: Point = pos
        self.team = team

        self.modifiers: List["Modifier"] = []
        self.abilities: List["Ability"] = []

        self.move_actions: int = 0
        self.standard_actions: int = 0
        self.free_actions: int = 0
        self.engine.add_entity(self)

    def start_turn(self) -> None:
        self.move_actions = 1
        self.standard_actions = 1
        self.free_actions = 99  # Arbitrary large number

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "hp": self.hp,
            "pos": self.pos,
            "team": self.team,
            "move_actions": self.move_actions,
            "standard_actions": self.standard_actions,
            "free_actions": self.free_actions,
        }

    def get_hash(self) -> float:
        import hashlib

        key = f"{self.set}__{self.name}"
        hash_int = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
        return float(hash_int % 10000) / 100.0

    # --- Engine Query Helpers ---
    def has_armor(self) -> bool:
        q = QueryHasArmor(self)
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    def can_move(self) -> bool:
        q = QueryCanMove(self)
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    def has_adjacent_enemies(self) -> bool:
        for other in self.engine.entities:
            if other.team != self.team and self.distance_to(other) <= 1:
                return True
        return False

    def get_legal_actions(self) -> List[Ability]:
        # Returns all abilities the entity has. Modifiers can alter this list.
        # A "basic move" is not an ability in this list, but a capability checked via `can_move()`.
        q = QueryLegalActions(self, result=list(self.abilities))
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    # --- Utility Helpers ---
    def distance_to(self, other: "Entity") -> int:
        return abs(self.pos[0] - other.pos[0]) + abs(self.pos[1] - other.pos[1])

    def add_modifier(self, modifier: "Modifier") -> None:
        modifier.owner = self
        self.modifiers.append(modifier)
        self.engine.router.subscribe(modifier)


class Modifier:
    owner: Entity = field(init=False)


# ==========================================
# EVENTS
# ==========================================


class DamageEvent:
    def __init__(
        self, engine: Engine, source: Optional[Entity], target: Entity, amount: int
    ):
        self.engine = engine
        self.source = source
        self.target = target
        self.amount = ModValue(amount)

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)

        if self.target.has_armor():
            self.amount.add(-1)

        final_damage = max(0, self.amount.value)
        self.target.hp -= final_damage

        self.engine.router.publish(self, EventPhase.AFTER)


class HealEvent:
    def __init__(self, engine: Engine, target: Entity, amount: int):
        self.engine = engine
        self.target = target
        self.amount = ModValue(amount)

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        final_heal = max(0, self.amount.value)
        self.target.hp += final_heal
        self.engine.router.publish(self, EventPhase.AFTER)


# ==========================================
# QUERIES
# ==========================================


class QueryHasArmor:
    def __init__(self, target: Entity):
        self.target = target
        self.result: bool = False


class QueryLegalActions:
    def __init__(self, target: Entity, result: List[Ability]):
        self.target = target
        self.result = result


class QueryCanMove:
    def __init__(self, target: Entity):
        self.target = target
        self.result: bool = True


# ==========================================
# ABILITIES (Developer Implementations)
# ==========================================


class InnateArmor(Modifier):
    @query(QueryHasArmor)
    def grant_armor(self, q: QueryHasArmor) -> None:
        q.result = True


class PaladinAura(Modifier):
    @query(QueryHasArmor, target_self=False)
    def grant_armor_to_adjacent(self, q):
        # Affects OTHERS: checks if the query target is near this aura's owner
        if q.target != self.owner and q.target.distance_to(self.owner) <= 1:
            q.result = True


class Marksmanship(Modifier):
    @before(DamageEvent, target_self=False)
    def buff_long_range_attacks(self, e: DamageEvent) -> None:
        # Buff applies if owner or ally attacks an enemy from range 3+
        # and owner has no adjacent enemies.
        if e.source and e.source.team == self.owner.team:
            if (
                not self.owner.has_adjacent_enemies()
                and e.source.distance_to(e.target) >= 3
            ):
                e.amount.add(1)
                e.amount.is_irreducible = True


class ShallowGrave(Modifier):
    @before(DamageEvent)
    def prevent_death(self, e: DamageEvent) -> None:
        e.amount.cap(lambda val: min(val, self.owner.hp - 1))

    @before(HealEvent)
    def boost_healing(self, e: HealEvent) -> None:
        e.amount.mult(1.5)


@dataclass
class Taunted(Modifier):
    taunter: Entity

    @query(QueryLegalActions)
    def force_attack(self, q: QueryLegalActions) -> None:
        # Overrides the result to only allow default abilities targeting the taunter.
        forced_actions = []
        for ability in self.owner.abilities:
            if ability.is_default:
                # Create a copy to not modify the base ability
                import copy

                action = copy.deepcopy(ability)
                action.target = self.taunter
                forced_actions.append(action)
        q.result = forced_actions

    @query(QueryCanMove)
    def prevent_move(self, q):
        q.result = False
