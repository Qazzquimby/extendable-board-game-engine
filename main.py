from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Type, Any, Union


# ==========================================
# ENUMS & TYPES
# ==========================================

class EventPhase(Enum):
    BEFORE = auto()
    AFTER = auto()
    QUERY = auto()


class ActionType(Enum):
    MOVE = auto()
    DEFAULT_ATTACK = auto()


@dataclass
class Action:
    action_type: ActionType
    target: Optional['Entity'] = None


# ==========================================
# ROUTER & SUBSCRIPTIONS
# ==========================================

@dataclass
class Subscription:
    modifier: 'Modifier'
    event_type: Type
    phase: EventPhase
    target_self: bool
    func: Callable[[Any], None]


class Router:
    def __init__(self) -> None:
        self.subscribers: List[Subscription] = []

    def subscribe(self, modifier: 'Modifier') -> None:
        for name in dir(modifier):
            method = getattr(modifier, name)
            if hasattr(method, "_listen_event"):
                self.subscribers.append(
                    Subscription(
                        modifier=modifier,
                        event_type=method._listen_event,
                        phase=method._listen_phase,
                        target_self=method._listen_target_self,
                        func=method
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
        func._listen_event, func._listen_phase, func._listen_target_self = event_type, EventPhase.BEFORE, target_self
        return func

    return decorator


def after(event_type: Type, target_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event, func._listen_phase, func._listen_target_self = event_type, EventPhase.AFTER, target_self
        return func

    return decorator


def query(event_type: Type, target_self: bool = True) -> Callable:
    def decorator(func: Callable) -> Callable:
        func._listen_event, func._listen_phase, func._listen_target_self = event_type, EventPhase.QUERY, target_self
        return func

    return decorator


# ==========================================
# CORE ENGINE & ENTITIES
# ==========================================

class Engine:
    def __init__(self) -> None:
        self.router = Router()
        self.entities: List['Entity'] = []

    def add_entity(self, entity: 'Entity') -> None:
        self.entities.append(entity)


class Entity:
    def __init__(self, engine: Engine, name: str, hp: int, pos: tuple[int, int],
                 team: int):
        self.engine = engine
        self.name = name
        self.hp = hp
        self.pos = pos
        self.team = team
        self.modifiers: List['Modifier'] = []
        self.engine.add_entity(self)

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

    def get_legal_actions(self) -> List[Action]:
        # Default behavior: Can move, can attack
        default_actions = [Action(ActionType.MOVE), Action(ActionType.DEFAULT_ATTACK)]
        q = QueryLegalActions(self, result=default_actions)
        self.engine.router.publish(q, EventPhase.QUERY)
        return q.result

    # --- Utility Helpers ---
    def distance_to(self, other: 'Entity') -> int:
        return abs(self.pos[0] - other.pos[0]) + abs(self.pos[1] - other.pos[1])

    def add_modifier(self, modifier: 'Modifier') -> None:
        modifier.owner = self
        self.modifiers.append(modifier)
        self.engine.router.subscribe(modifier)


class Modifier:
    owner: Entity = field(init=False)


# ==========================================
# MATH & EVENTS
# ==========================================

class ModValue:
    def __init__(self, base: int):
        self.base: int = base
        self._adds: List[Union[int, Callable[[], int]]] = []
        self._mults: List[Union[float, Callable[[], float]]] = []
        self._caps: List[Union[int, Callable[[int], int]]] = []
        self.is_irreducible: bool = False

    def add(self, val: Union[int, Callable[[], int]]) -> None:
        self._adds.append(val)

    def mult(self, val: Union[float, Callable[[], float]]) -> None:
        self._mults.append(val)

    def cap(self, val: Union[int, Callable[[int], int]]) -> None:
        self._caps.append(val)

    @property
    def value(self) -> int:
        v = float(self.base)
        for a in self._adds: v += a() if callable(a) else a
        for m in self._mults: v *= m() if callable(m) else m
        for c in self._caps: v = c(int(v)) if callable(c) else min(v, float(c))
        return int(v)


class DamageEvent:
    def __init__(self, engine: Engine, source: Optional[Entity], target: Entity,
                 amount: int):
        self.engine = engine
        self.source = source
        self.target = target
        self.amount = ModValue(amount)

    def resolve(self) -> None:
        self.engine.router.publish(self, EventPhase.BEFORE)

        # Cleanly encapsulated rule resolution
        if not self.amount.is_irreducible and self.target.has_armor():
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
    def __init__(self, target: Entity, result: List[Action]):
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
            if not self.owner.has_adjacent_enemies() and e.source.distance_to(
                    e.target) >= 3:
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
        # Overrides the default result entirely
        q.result = [Action(ActionType.DEFAULT_ATTACK, target=self.taunter)]

    @query(QueryCanMove)
    def prevent_move(self, q):
        q.result = False

# ==========================================
# PYTESTS
# ==========================================

def test_marksmanship_conditional_irreducible():
    engine = Engine()
    drow = Entity(engine, "Drow", hp=8, pos=(0, 0), team=1)
    axe = Entity(engine, "Axe", hp=10, pos=(0, 4), team=2)  # Range 4
    axe.add_modifier(InnateArmor())
    drow.add_modifier(Marksmanship())

    # Drow attacks Axe from range 4. Base dmg = 2.
    # Marksmanship adds +1 dmg and makes it irreducible. Axe's armor is ignored.
    # Total damage should be 3.
    DamageEvent(engine, source=drow, target=axe, amount=2).resolve()
    assert axe.hp == 7


def test_marksmanship_disabled_by_adjacent_enemy():
    engine = Engine()
    drow = Entity(engine, "Drow", hp=8, pos=(0, 0), team=1)
    flanker = Entity(engine, "Flanker", hp=5, pos=(0, 1),
                     team=2)  # Range 1, adjacent enemy
    axe = Entity(engine, "Axe", hp=10, pos=(0, 4), team=2)

    axe.add_modifier(InnateArmor())
    drow.add_modifier(Marksmanship())

    # Because Drow has an adjacent enemy, Marksmanship is disabled.
    # Base dmg 2 -> Armor reduces to 1.
    DamageEvent(engine, source=drow, target=axe, amount=2).resolve()
    assert axe.hp == 9


def test_shallow_grave_multipliers_and_caps():
    engine = Engine()
    dazzle = Entity(engine, "Dazzle", hp=5, pos=(0, 0), team=1)
    dazzle.add_modifier(ShallowGrave())

    # Heal for 2 -> +50% multiplier -> 3
    HealEvent(engine, target=dazzle, amount=2).resolve()
    assert dazzle.hp == 8

    # Take massive damage (50) -> Cap triggers preventing HP < 1.
    DamageEvent(engine, source=None, target=dazzle, amount=50).resolve()
    assert dazzle.hp == 1


def test_taunted_legal_actions_override():
    engine = Engine()
    axe = Entity(engine, "Axe", hp=10, pos=(0, 0), team=1)
    enemy = Entity(engine, "Enemy", hp=5, pos=(1, 0), team=2)

    # Before taunt: can move and attack
    actions = enemy.get_legal_actions()
    assert len(actions) == 2
    assert Action(ActionType.MOVE) in actions

    # Apply Taunt
    enemy.add_modifier(Taunted(taunter=axe))

    # After taunt: Only 1 legal action (Attack Axe)
    actions = enemy.get_legal_actions()
    assert len(actions) == 1
    assert actions[0].action_type == ActionType.DEFAULT_ATTACK
    assert actions[0].target == axe


def test_armor_and_damage():
    engine = Engine()
    axe = Entity(engine, "Axe", hp=10, pos=(0, 0), team=1)
    enemy = Entity(engine, "Enemy", hp=10, pos=(1, 0), team=2)

    axe.add_modifier(InnateArmor())

    # 3 damage attack -> reduced by 1 from armor -> 2 damage taken
    DamageEvent(engine, source=enemy, target=axe, amount=3).resolve()
    assert axe.hp == 8


def test_shallow_grave_cap():
    engine = Engine()
    dazzle = Entity(engine, "Dazzle", hp=8, pos=(0, 0), team=2)

    dazzle.add_modifier(ShallowGrave())

    # Massive 50 damage attack
    DamageEvent(engine, source=None, target=dazzle, amount=50).resolve()

    # Cap ensures HP doesn't drop below 1
    assert dazzle.hp == 1


def test_paladin_aura_affects_others():
    engine = Engine()
    reinhardt = Entity(engine, "Reinhardt", hp=12, pos=(0, 0), team=1)
    ally = Entity(engine, "Ally", hp=5, pos=(0, 1), team=1)  # Distance 1
    far_ally = Entity(engine, "FarAlly", hp=5, pos=(0, 3), team=1)  # Distance 3

    reinhardt.add_modifier(PaladinAura())

    # Attack adjacent ally (has armor from aura) -> 3 dmg becomes 2
    DamageEvent(engine, source=None, target=ally, amount=3).resolve()
    assert ally.hp == 3

    # Attack far ally (no aura) -> 3 dmg stays 3
    DamageEvent(engine, source=None, target=far_ally, amount=3).resolve()
    assert far_ally.hp == 2


def test_taunted_dataclass():
    engine = Engine()
    axe = Entity(engine, "Axe", hp=10, pos=(0, 0), team=2)
    enemy = Entity(engine, "Enemy", hp=5, pos=(1, 0), team=1)

    # Apply taunt using dataclass initialization
    enemy.add_modifier(Taunted(taunter=axe))

    assert enemy.can_move() is False
