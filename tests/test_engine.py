from engine import (
    Engine,
    Entity,
    DamageEvent,
    HealEvent,
    InnateArmor,
    Modifier,
    query,
    QueryHasArmor,
    before,
    Taunted,
)
from mod_value import ModInt
from point import Point
from heroes import MeleeHero


def test_marksmanship_conditional_irreducible():
    engine = Engine()
    drow = Entity(engine, "Drow", hp=8, speed=3, pos=Point(0, 0), team=1)
    axe = Entity(engine, "Axe", hp=10, speed=3, pos=Point(0, 4), team=2)  # Range 4
    axe.add_modifier(InnateArmor())
    drow.add_modifier(Marksmanship())

    # Drow attacks Axe from range 4. Base dmg = 2.
    # Marksmanship adds +1 dmg and makes it irreducible. Axe's armor is ignored.
    # Total damage should be 3.
    DamageEvent(engine, source=drow, subject=axe, amount=2).resolve()
    assert axe.hp == 7


def test_marksmanship_disabled_by_adjacent_enemy():
    engine = Engine()
    drow = Entity(engine, "Drow", hp=8, speed=3, pos=Point(0, 0), team=1)
    flanker = Entity(
        engine, "Flanker", hp=5, speed=3, pos=Point(0, 1), team=2
    )  # Range 1, adjacent enemy
    melee_hero = MeleeHero(engine, pos=Point(0, 4), team=2)

    drow.add_modifier(Marksmanship())

    # Because Drow has an adjacent enemy, Marksmanship is disabled.
    DamageEvent(engine, source=drow, subject=melee_hero, amount=2).resolve()
    assert melee_hero.hp == 8


def test_shallow_grave_multipliers_and_caps():
    engine = Engine()
    dazzle = Entity(engine, "Dazzle", hp=5, speed=3, pos=Point(0, 0), team=1)
    dazzle.add_modifier(ShallowGrave())

    # Heal for 2 -> +50% multiplier -> 3
    HealEvent(engine, subject=dazzle, amount=2).resolve()
    assert dazzle.hp == 8

    # Take massive damage (50) -> Cap triggers preventing HP < 1.
    DamageEvent(engine, source=None, subject=dazzle, amount=50).resolve()
    assert dazzle.hp == 1


def test_taunted_legal_actions_override():
    engine = Engine()
    axe = Entity(engine=engine, name="Axe", hp=10, speed=3, pos=Point(0, 0), team=1)
    enemy = MeleeHero(engine=engine, pos=Point(1, 0), team=2)

    # Before taunt: can move, has 2 abilities
    assert enemy.can_move() is True
    actions = enemy.get_legal_actions()
    assert len(actions) == 2
    assert any(a.name == "Melee Attack" for a in actions)
    assert any(a.name == "Do Nothing" for a in actions)

    # Apply Taunt
    enemy.add_modifier(Taunted(taunter=axe))

    # After taunt: Only 1 legal action (default attack on Axe), cannot move
    assert enemy.can_move() is False
    actions = enemy.get_legal_actions()
    assert len(actions) == 1
    assert actions[0].name == "Melee Attack"
    # assert actions[0].target == axe
    # todo, actions do not have .target
    #  How to indicate the action can only target axe?


def test_armor_and_damage():
    engine = Engine()
    axe = Entity(engine, "Axe", hp=10, speed=3, pos=Point(0, 0), team=1)
    enemy = Entity(engine, "Enemy", hp=10, speed=3, pos=Point(1, 0), team=2)

    axe.add_modifier(InnateArmor())

    # 3 damage attack -> reduced by 1 from armor -> 2 damage taken
    DamageEvent(engine, source=enemy, subject=axe, amount=3).resolve()
    assert axe.hp == 8


def test_shallow_grave_cap():
    engine = Engine()
    dazzle = Entity(engine, "Dazzle", hp=8, speed=3, pos=Point(0, 0), team=2)

    dazzle.add_modifier(ShallowGrave())

    # Massive 50 damage attack
    DamageEvent(engine, source=None, subject=dazzle, amount=50).resolve()

    # Cap ensures HP doesn't drop below 1
    assert dazzle.hp == 1


def test_paladin_aura_affects_others():
    engine = Engine()
    reinhardt = Entity(engine, "Reinhardt", hp=12, speed=3, pos=Point(0, 0), team=1)
    ally = Entity(engine, "Ally", hp=5, speed=3, pos=Point(0, 1), team=1)  # Distance 1
    far_ally = Entity(
        engine, "FarAlly", hp=5, speed=3, pos=Point(0, 3), team=1
    )  # Distance 3

    reinhardt.add_modifier(PaladinAura())

    # Attack adjacent ally (has armor from aura) -> 3 dmg becomes 2
    DamageEvent(engine, source=None, subject=ally, amount=3).resolve()
    assert ally.hp == 3

    # Attack far ally (no aura) -> 3 dmg stays 3
    DamageEvent(engine, source=None, subject=far_ally, amount=3).resolve()
    assert far_ally.hp == 2


def test_taunted_dataclass():
    engine = Engine()
    axe = Entity(engine, "Axe", hp=10, speed=3, pos=Point(0, 0), team=2)
    enemy = Entity(engine, "Enemy", hp=5, speed=3, pos=Point(1, 0), team=1)

    # Apply taunt using dataclass initialization
    enemy.add_modifier(Taunted(taunter=axe))

    assert enemy.can_move() is False


def test_modvalue_multiply_before_add():
    mod = ModInt(2)
    mod.add(1)
    mod.mult(2.0)  # +100%
    # 2 * 2.0 + 1 = 5
    assert mod.value == 5


def test_modvalue_cancellation():
    mod = ModInt(2)
    mod.mult(2.0)  # +100%
    mod.add_resistance()  # Resistance
    # Cancel out -> 2
    assert mod.value == 2


def test_modvalue_round_up():
    mod = ModInt(3)
    mod.add_resistance()
    # 3 * 0.5 = 1.5 -> rounds up to 2
    assert mod.value == 2


def test_modvalue_additive_multipliers():
    mod = ModInt(2)
    mod.mult(1.5)  # +50%
    mod.mult(2.0)  # +100%
    # 1.0 + 0.5 + 1.0 = 2.5
    # 2 * 2.5 = 5
    assert mod.value == 5


def test_modvalue_irreducible():
    mod = ModInt(4)
    mod.add(-2)
    mod.add_resistance()
    mod.is_irreducible = True
    # Irreducible ignores the -2 and the resistance
    assert mod.value == 4


def test_engine_turn_management():
    engine = Engine()
    e1 = Entity(engine, "Hero1", hp=10, speed=3, pos=Point(0, 0), team=1)
    e2 = Entity(engine, "Hero2", hp=10, speed=3, pos=Point(1, 1), team=2)

    assert engine.round_num == 1
    assert engine.active_entity is None

    # First turn
    engine.next_turn()
    assert engine.active_entity == e1
    assert engine.current_team == 1
    assert e1.move_actions == 1
    assert e1.standard_actions == 1

    # Second turn
    engine.next_turn()
    assert engine.active_entity == e2
    assert engine.current_team == 2

    # Next round
    engine.next_turn()
    assert engine.active_entity == e1
    assert engine.round_num == 2


def test_engine_serialization():
    engine = Engine()
    e1 = Entity(engine, "Hero1", hp=10, speed=3, pos=Point(0, 0), team=1)
    engine.next_turn()

    state = engine.to_model()
    assert state.round_num == 1
    assert state.current_team == 1
    assert state.active_entity == 1
    assert len(state.entities) == 1

    e1_state = state.entities[0]
    assert e1_state.name == "Hero1"
    assert e1_state.hp == 10
    assert e1_state.pos == (0, 0)
    assert e1_state.move_actions == 1


def test_engine_clone():
    engine = Engine()
    e1 = Entity(engine, "Hero1", hp=10, speed=3, pos=Point(0, 0), team=1)
    engine.next_turn()

    cloned_engine = engine.clone()
    assert cloned_engine is not engine
    assert len(cloned_engine.entities) == 1
    assert cloned_engine.entities[0] is not e1
    assert cloned_engine.entities[0].name == "Hero1"
    assert cloned_engine.active_entity == cloned_engine.entities[0]


def test_engine_rng_seed():
    engine1 = Engine(seed=42)
    engine2 = Engine(seed=42)
    engine3 = Engine(seed=99)

    assert engine1.rng.random() == engine2.rng.random()
    assert engine1.rng.random() != engine3.rng.random()


class PaladinAura(Modifier):
    @query(QueryHasArmor, only_self=False)
    def grant_armor_to_adjacent(self, q: QueryHasArmor):
        # Affects OTHERS: checks if the query target is near this aura's owner
        if q.subject != self.owner and q.subject.distance_to(self.owner) <= 1:
            q.result = True


class Marksmanship(Modifier):
    @before(DamageEvent, only_self=False)
    def buff_long_range_attacks(self, e: DamageEvent) -> None:
        # Buff applies if owner or ally attacks an enemy from range 3+
        # and owner has no adjacent enemies.

        if not e.source or e.source.team != self.owner.team:
            return

        if e.source.distance_to(e.subject) < 3:
            return

        has_adjacent_enemies = False
        for other in self.owner.engine.entities:
            if other.team != self.owner.team and self.owner.distance_to(other) <= 1:
                has_adjacent_enemies = True

        if has_adjacent_enemies:
            return

        e.amount.add(1)
        e.amount.is_irreducible = True


class ShallowGrave(Modifier):
    @before(DamageEvent)
    def prevent_death(self, e: DamageEvent) -> None:
        e.amount.cap(lambda val: min(val, self.owner.hp - 1))

    @before(HealEvent)
    def boost_healing(self, e: HealEvent) -> None:
        e.amount.mult(1.5)
