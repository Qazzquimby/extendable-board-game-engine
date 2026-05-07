import random
import copy
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Type, Any, Dict

from grid import Grid
from mod_value import ModValue
from point import Point
from abilities import Ability
from schemas import EngineState, EntityState

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

    def unsubscribe(self, modifier: "Modifier") -> None:
        self.subscribers = [sub for sub in self.subscribers if sub.modifier != modifier]

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
        func._listen_event = event_type
        func._listen_phase = EventPhase.BEFORE
        func._listen_target_self = target_self
        return func

    return decorator


def after(event_type: Type, target_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event = event_type
        func._listen_phase = EventPhase.AFTER
        func._listen_target_self = target_self
        return func

    return decorator


def query(event_type: Type, target_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event = event_type
        func._listen_phase = EventPhase.QUERY
        func._listen_target_self = target_self
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

        if self.active_entity is not None:
            TurnEndEvent(self, self.active_entity).resolve()
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

        TurnStartEvent(self, self.active_entity).resolve()

    def to_model(self) -> EngineState:
        return EngineState(
            round_num=self.round_num,
            current_team=self.current_team,
            active_entity=self.active_entity.id if self.active_entity else None,
            entities=[e.to_model() for e in self.entities],
        )

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

    def to_model(self) -> EntityState:
        return EntityState(
            id=self.id,
            name=self.name,
            hp=self.hp,
            pos=self.pos,
            team=self.team,
            move_actions=self.move_actions,
            standard_actions=self.standard_actions,
            free_actions=self.free_actions,
        )

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

    def distance_to(self, other: "Entity") -> int:
        return abs(self.pos[0] - other.pos[0]) + abs(self.pos[1] - other.pos[1])

    def add_modifier(self, modifier: "Modifier") -> None:
        modifier.owner = self
        self.modifiers.append(modifier)
        self.engine.router.subscribe(modifier)

    def remove_modifier(self, modifier: "Modifier") -> None:
        if modifier in self.modifiers:
            self.modifiers.remove(modifier)
            self.engine.router.unsubscribe(modifier)

    def add_token(self, token_class: Type["Token"], amount: int = 1) -> None:
        for mod in self.modifiers:
            if isinstance(mod, token_class):
                mod.add(amount)
                return
        new_token = token_class(amount)
        self.add_modifier(new_token)

    def remove_token(self, token_class: Type["Token"], amount: int = 1) -> None:
        for mod in self.modifiers:
            if isinstance(mod, token_class):
                mod.remove(amount)
                return

    def get_token_count(self, token_class: Type["Token"]) -> int:
        for mod in self.modifiers:
            if isinstance(mod, token_class):
                return mod.amount
        return 0


class Modifier:
    owner: Entity = field(init=False)


class Token(Modifier):
    def __init__(self, amount: int = 1):
        self.amount = amount

    def add(self, amount: int) -> None:
        self.amount += amount

    def remove(self, amount: int) -> None:
        self.amount -= amount
        if self.amount <= 0:
            self.owner.remove_modifier(self)


# ==========================================
# EVENTS
# ==========================================
class TurnStartEvent:
    def __init__(self, engine: "Engine", target: "Entity"):
        self.engine = engine
        self.target = target

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        self.engine.active_entity.start_turn()
        self.engine.router.publish(self, EventPhase.AFTER)


class TurnEndEvent:
    def __init__(self, engine: "Engine", target: "Entity"):
        self.engine = engine
        self.target = target

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        self.engine.router.publish(self, EventPhase.AFTER)


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

        if self.target.hp <= 0:
            DeathEvent(self.engine, target=self.target, killer=self.source).resolve()

        self.engine.router.publish(self, EventPhase.AFTER)


class DeathEvent:
    def __init__(self, engine: Engine, target: Entity, killer: Optional[Entity] = None):
        self.engine = engine
        self.target = target
        self.killer = killer

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        self.target.pos = None


# For on-kill use on-death and filter by killer


class SummonEvent:
    def __init__(self, engine: Engine, summoner: Entity, summon: "Summon"):
        self.engine = engine
        self.summoner = summoner
        self.summon = summon

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
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


class QuerySpeed:
    def __init__(self, target: Entity, result: int):
        self.target = target
        self.result = result


class QueryDefense:
    def __init__(
        self, target: Entity, attack_source: Optional[Entity], result: int = 0
    ):
        self.target = target
        self.attack_source = attack_source
        self.result = result


# ==========================================
# ABILITIES (Developer Implementations)
# ==========================================


class InnateArmor(Modifier):
    @query(QueryHasArmor)
    def grant_armor(self, q: QueryHasArmor) -> None:
        q.result = True


class Immobile(Modifier):
    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False


class Stunned(Modifier):
    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False

    @query(QueryLegalActions)
    def prevent_actions(self, q: QueryLegalActions) -> None:
        q.result = []


class Slow(Modifier):
    def __init__(self, amount: int):
        self.amount = amount

    @query(QuerySpeed)
    def reduce_speed(self, q: QuerySpeed) -> None:
        q.result = max(0, q.result - self.amount)


class Hero(Entity):
    def __init__(
        self, engine: "Engine", name: str, hp: int, speed: int, pos: Point, team: int
    ):
        super().__init__(
            engine=engine, name=name, hp=hp, speed=speed, pos=pos, team=team
        )


class Summon(Entity):
    def __init__(
        self,
        engine: "Engine",
        name: str,
        hp: int,
        speed: int,
        pos: Point,
        team: int,
        summoner: Entity,
    ):
        super().__init__(
            engine=engine, name=name, hp=hp, speed=speed, pos=pos, team=team
        )
        self.summoner = summoner
        SummonEvent(self.engine, summoner=self.summoner, summon=self).resolve()
