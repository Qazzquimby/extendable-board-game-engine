from dataclasses import dataclass
from typing import Callable


# --- Decorators for Concise Syntax ---
def before(event_type, target_self=True):
    def decorator(func):
        func._listen_event, func._listen_phase, func._listen_target_self = event_type, 'before', target_self
        return func

    return decorator


def after(event_type, target_self=True):
    def decorator(func):
        func._listen_event, func._listen_phase, func._listen_target_self = event_type, 'after', target_self
        return func

    return decorator


def query(event_type, target_self=True):
    def decorator(func):
        func._listen_event, func._listen_phase, func._listen_target_self = event_type, 'query', target_self
        return func

    return decorator


# --- Core Engine & PubSub Router ---
class Router:
    def __init__(self):
        self.subscribers = []

    def subscribe(self, modifier):
        for name in dir(modifier):
            method = getattr(modifier, name)
            if hasattr(method, "_listen_event"):
                self.subscribers.append({
                    "modifier": modifier,
                    "event_type": method._listen_event,
                    "phase": method._listen_phase,
                    "target_self": method._listen_target_self,
                    "func": method
                })

    def publish(self, event, phase):
        # Filter and execute listeners
        for sub in list(self.subscribers):  # iterate copy in case of modification
            if sub["event_type"] == type(event) and sub["phase"] == phase:
                # Automatic Target Filtering!
                if sub["target_self"]:
                    target = getattr(event, "target", None)
                    if target != sub["modifier"].owner:
                        continue

                sub["func"](event)


class Engine:
    def __init__(self):
        self.router = Router()
        self.entities = []

    def add_entity(self, entity):
        self.entities.append(entity)


# --- Math & Values ---
class ModValue:
    def __init__(self, base: int):
        self.base = base
        self._adds = []
        self._caps = []

    def add(self, val: int | Callable[[], int]):
        self._adds.append(val)

    def cap(self, val: int | Callable[[int], int]):
        self._caps.append(val)

    @property
    def value(self):
        v = self.base
        for a in self._adds: v += a() if callable(a) else a
        for c in self._caps: v = c(v) if callable(c) else min(v, c)
        return v


# --- Events & Queries ---
class DamageEvent:
    def __init__(self, engine, source, target, amount):
        self.engine = engine
        self.source = source
        self.target = target
        self.amount = ModValue(amount)

    def resolve(self):
        self.engine.router.publish(self, 'before')

        # Core Rule: Armor resolves exactly when damage is calculated
        q_armor = QueryHasArmor(self.target)
        self.engine.router.publish(q_armor, 'query')
        if q_armor.result:
            self.amount.add(-1)

        final_damage = max(0, self.amount.value)
        self.target.hp -= final_damage

        self.engine.router.publish(self, 'after')


class QueryHasArmor:
    def __init__(self, target):
        self.target = target
        self.result = False  # Default state


class QueryCanMove:
    def __init__(self, target):
        self.target = target
        self.result = True  # Default state


# --- Entities & Modifiers ---
class Entity:
    def __init__(self, engine, name, hp, pos):
        self.engine = engine
        self.name = name
        self.hp = hp
        self.pos = pos
        self.modifiers = []
        self.engine.add_entity(self)

    def distance_to(self, other):
        return abs(self.pos[0] - other.pos[0]) + abs(self.pos[1] - other.pos[1])

    def add_modifier(self, modifier):
        modifier.owner = self
        self.modifiers.append(modifier)
        self.engine.router.subscribe(modifier)


class Modifier:
    owner: Entity = None  # Injected when added to entity


# ==========================================
# ABILITY IMPLEMENTATIONS (The "Developer" Interface)
# ==========================================

class InnateArmor(Modifier):
    @query(QueryHasArmor)  # target_self=True is implicit!
    def grant_armor(self, q):
        q.result = True


class ShallowGrave(Modifier):
    @before(DamageEvent)
    def prevent_death(self, e):
        # Evaluated lazily: locks damage max to HP - 1
        e.amount.cap(lambda val: min(val, self.owner.hp - 1))


class PaladinAura(Modifier):
    @query(QueryHasArmor, target_self=False)
    def grant_armor_to_adjacent(self, q):
        # Affects OTHERS: checks if the query target is near this aura's owner
        if q.target != self.owner and q.target.distance_to(self.owner) <= 1:
            q.result = True


@dataclass
class Taunted(Modifier):
    taunter: Entity  # "Cheatless" conciseness using standard Python dataclasses

    @query(QueryCanMove)
    def prevent_move(self, q):
        q.result = False


# ==========================================
# PYTESTS
# ==========================================

def test_armor_and_damage():
    engine = Engine()
    axe = Entity(engine, "Axe", hp=10, pos=(0, 0))
    enemy = Entity(engine, "Enemy", hp=10, pos=(1, 0))

    axe.add_modifier(InnateArmor())

    # 3 damage attack -> reduced by 1 from armor -> 2 damage taken
    DamageEvent(engine, source=enemy, target=axe, amount=3).resolve()
    assert axe.hp == 8


def test_shallow_grave_cap():
    engine = Engine()
    dazzle = Entity(engine, "Dazzle", hp=8, pos=(0, 0))

    dazzle.add_modifier(ShallowGrave())

    # Massive 50 damage attack
    DamageEvent(engine, source=None, target=dazzle, amount=50).resolve()

    # Cap ensures HP doesn't drop below 1
    assert dazzle.hp == 1


def test_paladin_aura_affects_others():
    engine = Engine()
    reinhardt = Entity(engine, "Reinhardt", hp=12, pos=(0, 0))
    ally = Entity(engine, "Ally", hp=5, pos=(0, 1))  # Distance 1
    far_ally = Entity(engine, "FarAlly", hp=5, pos=(0, 3))  # Distance 3

    reinhardt.add_modifier(PaladinAura())

    # Attack adjacent ally (has armor from aura) -> 3 dmg becomes 2
    DamageEvent(engine, source=None, target=ally, amount=3).resolve()
    assert ally.hp == 3

    # Attack far ally (no aura) -> 3 dmg stays 3
    DamageEvent(engine, source=None, target=far_ally, amount=3).resolve()
    assert far_ally.hp == 2


def test_taunted_dataclass():
    engine = Engine()
    axe = Entity(engine, "Axe", hp=10, pos=(0, 0))
    enemy = Entity(engine, "Enemy", hp=5, pos=(1, 0))

    # Apply taunt using dataclass initialization
    enemy.add_modifier(Taunted(taunter=axe))

    # Fire query
    q = QueryCanMove(target=enemy)
    engine.router.publish(q, 'query')

    assert q.result is False