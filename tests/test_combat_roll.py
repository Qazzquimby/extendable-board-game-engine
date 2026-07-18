"""Tests for the combat roll system: ability defense (miss chance), crit chance, and roll resolution.

These tests verify that:
- An ability's built-in defense (+2 miss) correctly makes attacks miss on low rolls
- An ability's built-in crit_chance correctly makes attacks crit on high rolls
- Target-based defense stacks with ability defense
"""

from abilities import Ability
from aimings import TargetEntity
from engine import Engine
from entities import Hero
from modifiers import Modifier
from point import Point
from grid import Grid
from queries import QueryDefense
from events import query
from valence import Valence


class TestHero(Hero):
    pass


class DefenseMod(Modifier):
    valence = Valence.GOOD

    def __init__(self, amount: int = 2):
        self.amount = amount
        super().__init__()

    @query(QueryDefense)
    def add_defense(self, engine: "Engine", event: QueryDefense):
        if event.subject_id == self.owner_id:
            event.result += self.amount


def test_ability_defense_miss_chance():
    """An ability with defense=2 has a built-in miss chance.

    Verify that over multiple runs with different seeds, we see both hits
    and misses, proving the ability defense is being incorporated into the roll.
    """
    hit_count = 0
    total_runs = 20

    for run in range(total_runs):
        engine = Engine(seed=42 + run, grid=Grid(width=5, height=5))
        atk = TestHero(
            engine=engine, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
        )
        defn = TestHero(
            engine=engine, name="Defender", hp=10, speed=3, pos=Point(1, 0), team=1
        )

        ability = Ability(
            name="Test Shot",
            aiming=TargetEntity(in_range=5),
            instructions=[],
            defense=2,
            owner_id=atk.id,
        )

        aiming_result = ability.aiming.get_all_aimings(
            engine=engine, actor=atk, start_pos=atk.pos, require_los=False
        )[0]
        roll_result = ability.get_roll_result(
            aiming_result=aiming_result, engine=engine, source=atk
        )
        if roll_result.hit_points:
            hit_count += 1

    # With defense=2, need roll > 2 (3-6), ~67% hit chance
    # Over 20 runs with different seeds, both hits and misses should occur
    assert 0 < hit_count < total_runs, (
        f"Expected some hits and some misses with defense=2, "
        f"got {hit_count}/{total_runs} hits"
    )


def test_no_defense_auto_hits():
    """An ability with no defense and no target defense always auto-hits."""
    engine = Engine(seed=42, grid=Grid(width=5, height=5))
    atk = TestHero(
        engine=engine, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
    )
    defn = TestHero(
        engine=engine, name="Defender", hp=10, speed=3, pos=Point(1, 0), team=1
    )

    ability = Ability(
        name="Auto Shot",
        aiming=TargetEntity(in_range=5),
        instructions=[],
        owner_id=atk.id,
    )

    aiming_result = ability.aiming.get_all_aimings(
        engine=engine, actor=atk, start_pos=atk.pos, require_los=False
    )[0]
    roll_result = ability.get_roll_result(
        aiming_result=aiming_result, engine=engine, source=atk
    )

    # No defense anywhere = auto hit, no roll generated
    assert roll_result.roll is None, "No roll should be generated when defense=0"
    assert len(roll_result.hit_points) > 0, "Should auto-hit when no defense"


def test_ability_defense_stacks_with_target_defense():
    """Ability defense stacks additively with target's own defense modifiers."""

    engine = Engine(seed=42, grid=Grid(width=5, height=5))
    atk = TestHero(
        engine=engine, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
    )
    defn = TestHero(
        engine=engine, name="Defender", hp=10, speed=3, pos=Point(1, 0), team=1
    )

    # Add +2 target-based defense via modifier
    defn.add_modifier(engine, DefenseMod(amount=2))

    ability = Ability(
        name="Mediocre Shot",
        aiming=TargetEntity(in_range=5),
        instructions=[],
        defense=2,
        owner_id=atk.id,
    )

    # Verify total defense = ability.defense + target.get_defense()
    target_def = defn.get_defense(engine=engine, attack_source=atk, ability=ability)
    total_def = min(4, target_def + ability.defense)
    assert total_def == 4, f"Expected total defense 4, got {total_def}"

    # Over multiple runs, both hits and misses should occur
    hit_count = 0
    for run in range(30):
        engine2 = Engine(seed=42 + run, grid=Grid(width=5, height=5))
        atk2 = TestHero(
            engine=engine2, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
        )
        defn2 = TestHero(
            engine=engine2, name="Defender", hp=10, speed=3, pos=Point(1, 0), team=1
        )

        defn2.add_modifier(engine2, DefenseMod(amount=2))

        ability2 = Ability(
            name="Test Shot",
            aiming=TargetEntity(in_range=5),
            instructions=[],
            defense=2,
            owner_id=atk2.id,
        )

        aiming_result = ability2.aiming.get_all_aimings(
            engine2, actor=atk2, start_pos=atk2.pos, require_los=False
        )[0]
        roll_result = ability2.get_roll_result(
            aiming_result=aiming_result, engine=engine2, source=atk2
        )
        if roll_result.hit_points:
            hit_count += 1

    assert 0 < hit_count < 30, (
        f"Expected some hits and misses with total defense 4, got {hit_count}/30 hits"
    )


def test_ability_crit_chance():
    """An ability with crit_chance=2 can produce crits.

    Crit condition: roll >= 7 - crit_chance. With crit_chance=2, crit on 5+.
    We add +1 defense to force a roll, then verify crits occur.
    """
    hit_count = 0
    crit_count = 0
    total_runs = 60

    for run in range(total_runs):
        engine = Engine(seed=42 + run, grid=Grid(width=5, height=5))
        atk = TestHero(
            engine=engine, name="Attacker", hp=10, speed=3, pos=Point(0, 0), team=0
        )
        defn = TestHero(
            engine=engine, name="Defender", hp=10, speed=3, pos=Point(1, 0), team=1
        )

        # Give target +1 defense to force a roll
        defn.add_modifier(engine, DefenseMod(amount=1))

        ability = Ability(
            name="Crit Shot",
            aiming=TargetEntity(in_range=5),
            instructions=[],
            crit_chance=2,
            owner_id=atk.id,
        )

        aiming_result = ability.aiming.get_all_aimings(
            engine=engine, actor=atk, start_pos=atk.pos, require_los=False
        )[0]
        roll_result = ability.get_roll_result(
            aiming_result=aiming_result, engine=engine, source=atk
        )
        if roll_result.hit_points:
            hit_count += 1
        if roll_result.crit_points:
            crit_count += 1

    assert hit_count > 0, "Expected at least some hits"
    assert crit_count > 0, "Expected at least some crits"
    assert crit_count < hit_count, "Crits should be a subset of hits"


def test_photon_orb_charge_then_fire():
    """Verify Photon Orb is a charge-then-fire ability with +2 miss."""
    from heroes.symmetra import Symmetra, ChargedPhotonOrb

    engine = Engine(seed=42, grid=Grid(width=5, height=5))
    symm = Symmetra(engine=engine, pos=Point(1, 1), team=0)
    enemy = TestHero(
        engine=engine, name="Enemy", hp=10, speed=3, pos=Point(1, 2), team=1
    )

    # Ability is called "Charge Photon Orb", has TargetSelf aiming
    charge_orb = next(a for a in symm.abilities if a.name == "Charge Photon Orb")
    assert charge_orb is not None, "Symmetra should have Charge Photon Orb"
    assert charge_orb.is_default, "Charge Photon Orb should be default"
    assert charge_orb.aiming.__class__.__name__ == "TargetSelf", (
        "Charge Photon Orb should aim at self"
    )

    # +2 miss is in the ChargedPhotonOrb modifier's fire_orb method
    assert hasattr(ChargedPhotonOrb, "fire_orb"), "ChargedPhotonOrb needs fire_orb"

    # Verify ChargedPhotonOrb adds +2 to defense when firing
    import inspect
    source = inspect.getsource(ChargedPhotonOrb.fire_orb)
    assert "+ 2" in source, ("ChargedPhotonOrb should have +2 miss bonus")
    assert "target_def = min(4, target_def)" in source, "Defense should cap at 4"


def test_no_photon_orb_miss_chance_modifier():
    """Verify PhotonOrbMissChance modifier class no longer exists."""
    import heroes.symmetra as sym

    assert not hasattr(sym, "PhotonOrbMissChance"), (
        "PhotonOrbMissChance should be removed"
    )
