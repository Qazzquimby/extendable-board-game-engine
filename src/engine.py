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
        self.markers: List["Marker"] = []
        self.rng = random.Random(seed)
        self.round_num: int = 1
        self.current_team: int = 1
        self.grid: Grid = grid
        self.active_entity: Optional["Entity"] = None
        self._next_id: int = 1
        self._entity_by_pos: Dict[Point, "Entity"] = {}
        self._markers_by_pos: Dict[Point, List["Marker"]] = {}

    def entity_at(self, pos: Point) -> Optional["Entity"]:
        return self._entity_by_pos.get(pos)

    def markers_at(self, pos: Point) -> List["Marker"]:
        return self._markers_by_pos.get(pos, [])

    @property
    def living_entities(self) -> List["Entity"]:
        alive = []
        for entity in self.entities:
            q = QueryIsAlive(entity)
            self.router.publish(q, EventPhase.QUERY)
            if q.result:
                alive.append(entity)
        return alive

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

        self._pos: Optional[Point] = None
        self.team = team

        self.modifiers: List["Modifier"] = []
        self.abilities: List["Ability"] = []

        self.move_actions: int = 0
        self.standard_actions: int = 0
        self.free_actions: int = 0
        self.engine.add_entity(self)
        self.pos = pos

    @property
    def pos(self) -> Optional[Point]:
        return self._pos

    @pos.setter
    def pos(self, value: Optional[Point]) -> None:
        if self._pos is not None:
            if self.engine.entity_at(self._pos) == self:
                del self.engine._entity_by_pos[self._pos]
        self._pos = value
        if value is not None:
            self.engine._entity_by_pos[value] = self

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
        legal = []
        for ability in self.abilities:
            if ability.is_tapped:
                continue
            if ability.charges is not None and ability.charges <= 0:
                continue
            if (
                ability.is_ultimate
                and ability.ultimate_turn is not None
                and self.engine.round_num < ability.ultimate_turn
            ):
                continue
            legal.append(ability)

        q = QueryLegalActions(self, result=legal)
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    def get_defense(
        self,
        attack_source: Optional["Entity"] = None,
        ability: Optional["Ability"] = None,
    ) -> int:
        q = QueryDefense(
            target=self, attack_source=attack_source, ability=ability, result=0
        )
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    def get_crit(self, receiver: "Entity", ability: Optional["Ability"] = None) -> int:
        q = QueryCrit(
            target=receiver,
            attack_source=self,
            ability=ability,
            result=ability.crit_chance,
        )
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


class Object(Summon):
    def __init__(
        self,
        engine: "Engine",
        name: str,
        hp: int,
        pos: Point,
        team: int,
        summoner: Entity,
    ):
        super().__init__(
            engine=engine,
            name=name,
            hp=hp,
            speed=0,
            pos=pos,
            team=team,
            summoner=summoner,
        )


class Marker:
    def __init__(self, engine: "Engine", name: str, pos: Point, team: int):
        self.engine = engine
        self.id = self.engine.generate_id()
        self.name = name
        self._pos: Optional[Point] = None
        self.team = team
        self.modifiers: List["Modifier"] = []
        self.engine.markers.append(self)
        self.pos = pos

    @property
    def pos(self) -> Optional[Point]:
        return self._pos

    @pos.setter
    def pos(self, value: Optional[Point]) -> None:
        if self._pos is not None:
            if self in self.engine._markers_by_pos.get(self._pos, []):
                self.engine._markers_by_pos[self._pos].remove(self)
                if not self.engine._markers_by_pos[self._pos]:
                    del self.engine._markers_by_pos[self._pos]
        self._pos = value
        if value is not None:
            self.engine._markers_by_pos.setdefault(value, []).append(self)


class Modifier:
    owner: Entity = field(init=False)


class SummonModifier(Modifier):
    owner: Summon = field(init=False)


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
class PushEvent:
    def __init__(
        self,
        engine: "Engine",
        recipient: "Entity",
        distance: int,
        source: Optional["Entity"] = None,
    ):
        self.engine = engine
        self.recipient = recipient
        self.distance = ModValue(distance)
        self.source = source
        self.canceled = False

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        if self.canceled:
            return
        # Pushing is calculated based on pathing away from the source
        if (
            getattr(self.recipient, "pos", None) is not None
            and self.source
            and getattr(self.source, "pos", None) is not None
        ):
            dist = max(0, self.distance.value)
            if dist > 0:
                path = self.engine.grid.get_push_path(  # todo
                    start=self.recipient.pos, target=None, push_from=self.source.pos
                )
                if path and len(path) >= dist:
                    self.recipient.pos = path[dist - 1]
        self.engine.router.publish(self, EventPhase.AFTER)


class PullEvent:
    def __init__(
        self,
        engine: "Engine",
        recipient: "Entity",
        distance: int,
        source: Optional["Entity"] = None,
    ):
        self.engine = engine
        self.recipient = recipient
        self.distance = ModValue(distance)
        self.source = source
        self.canceled = False

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        if self.canceled:
            return
        if (
            getattr(self.recipient, "pos", None) is not None
            and self.source
            and getattr(self.source, "pos", None) is not None
        ):
            dist = max(0, self.distance.value)
            if dist > 0:
                path = self.engine.grid.get_pull_path(
                    self.recipient.pos, self.source.pos, self.source.pos
                )
                if path and len(path) >= dist:
                    self.recipient.pos = path[dist - 1]
        self.engine.router.publish(self, EventPhase.AFTER)


class TurnStartEvent:
    def __init__(self, engine: "Engine", target: "Entity"):
        self.engine = engine
        self.target = target  # todo rename. Hero, for turn start? It's nice having a consistent name to check for == self though.

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

        for ability in self.target.abilities:
            if ability.taps:
                if not ability.tapped_this_turn:
                    ability.is_tapped = False
                ability.tapped_this_turn = False

        self.engine.router.publish(self, EventPhase.AFTER)


class DamageEvent:
    def __init__(
        self,
        engine: Engine,
        source: Optional[Entity],
        receiver: Entity,
        amount: int,
        ability: Optional["Ability"] = None,
    ):
        self.engine = engine
        self.source = source
        self.receiver = receiver
        self.amount = ModValue(amount)
        self.ability = ability

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        if self.receiver.has_armor():
            self.amount.add(-1)

        final_damage = max(0, self.amount.value)
        self.receiver.hp -= final_damage

        if self.receiver.hp <= 0:
            DeathEvent(
                self.engine, receiver=self.receiver, killer=self.source
            ).resolve()

        self.engine.router.publish(self, EventPhase.AFTER)


class DeathEvent:
    # For on-kill use on-death and filter by killer
    def __init__(
        self, engine: Engine, receiver: Entity, killer: Optional[Entity] = None
    ):
        self.engine = engine
        self.receiver = receiver
        self.killer = killer

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        self.receiver.pos = None
        self.engine.router.publish(self, EventPhase.AFTER)


class SummonEvent:
    def __init__(self, engine: Engine, summoner: Entity, summon: "Summon"):
        self.engine = engine
        self.summoner = summoner
        self.summon = summon

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        self.engine.router.publish(self, EventPhase.AFTER)


class HealEvent:
    def __init__(self, engine: Engine, receiver: Entity, amount: int):
        self.engine = engine
        self.target = receiver
        self.amount = ModValue(amount)

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)
        final_heal = max(0, self.amount.value)
        self.target.hp += final_heal
        self.engine.router.publish(self, EventPhase.AFTER)


# ==========================================
# QUERIES
# ==========================================


class QueryIsAlive:
    def __init__(self, entity: Entity):
        self.entity = entity
        self.result: bool = entity.pos is not None and entity.hp > 0


class QueryHasArmor:
    def __init__(self, entity: Entity):
        self.entity = entity
        self.result: bool = False


class QueryLegalAimings:
    def __init__(self, actor: "Entity", ability: "Ability", result: List["AimingResult"]):
        self.actor = actor
        self.ability = ability
        self.result = result


class QueryLegalActions:
    def __init__(self, entity: Entity, result: List[Ability]):
        self.entity = entity
        self.result = result


class QueryCanMove:
    def __init__(self, entity: Entity):
        self.entity = entity
        self.result: bool = True


class QuerySpeed:
    def __init__(self, entity: Entity, result: int):
        self.entity = entity
        self.result = result


class QueryDefense:
    def __init__(
        self,
        target: Entity,
        attack_source: Optional[Entity] = None,
        ability: Optional["Ability"] = None,
        result: int = 0,
    ):
        self.target = target
        self.attack_source = attack_source
        self.ability = ability
        self.result = result


class QueryCrit:
    def __init__(
        self,
        target: Entity,
        attack_source: Optional[Entity] = None,
        ability: Optional["Ability"] = None,
        result: int = 0,
    ):
        self.target = target
        self.attack_source = attack_source
        self.ability = ability
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


class ImmobileToken(Immobile, Token):
    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, event: TurnEndEvent) -> None:
        if self in self.owner.modifiers:
            self.owner.remove_modifier(self)


class Stunned(Modifier):
    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False

    @query(QueryLegalActions)
    def prevent_actions(self, q: QueryLegalActions) -> None:
        q.result = []

    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, event: TurnEndEvent) -> None:
        # todo, we'd rather modify the modifier somehow
        #  Immobile().until(TurnEndEvent, target=self.owner) or something.
        #  Immobile doesn't inherently last one turn. Everything can have any duration or condition
        #  eg Nearby enemies are immobile
        if self in self.owner.modifiers:
            self.owner.remove_modifier(self)


class Slow(Modifier):
    def __init__(self, amount: int):
        self.amount = amount

    @query(QuerySpeed)
    def reduce_speed(self, q: QuerySpeed) -> None:
        q.result = max(0, q.result - self.amount)


class SlowToken(Slow, Token):
    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, event: TurnEndEvent) -> None:
        # todo, we'd rather modify the modifier somehow
        #  Immobile().until(TurnEndEvent, target=self.owner) or something.
        #  Immobile doesn't inherently last one turn. Everything can have any duration or condition
        #  eg Nearby enemies are immobile
        if self in self.owner.modifiers:
            self.owner.remove_modifier(self)


@dataclass
class Taunted(Modifier):
    taunter: Entity

    @query(QueryLegalActions)
    def force_attack(self, q: QueryLegalActions) -> None:
        forced_actions = []
        # for ability in self.owner.abilities:
        for (
            ability
        ) in (
            q.result
        ):  # It should start initialized to all legal actions including move.
            if ability.is_default:
                import copy

                action = copy.deepcopy(ability)
                action.receiver = self.taunter
                forced_actions.append(action)
        q.result = forced_actions
        self.owner.remove_modifier(self)

    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False
