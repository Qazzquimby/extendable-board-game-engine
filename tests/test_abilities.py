from abilities import Ability
from aimings import IncludeArea, TargetSelf
from areas import Burst, Square
from engine import Engine
from entities import Entity
from point import Point


def test_target_area_instantiation():
    burst_area = Burst(radius=2)
    target_area_no_range = IncludeArea(area=burst_area)
    assert target_area_no_range.area == burst_area
    assert target_area_no_range.area.in_range == 0

    square_area = Square(side_length=3, in_range=5)
    target_area_with_range = IncludeArea(area=square_area)
    assert target_area_with_range.area == square_area
    assert target_area_with_range.area.in_range == 5


def test_ability_hashing():
    ability1 = Ability(name="Slash", aiming=TargetSelf())
    ability2 = Ability(name="Shoot", aiming=TargetSelf())
    ability3 = Ability(name="Slash", aiming=TargetSelf())

    hash1 = ability1.get_hash()
    hash2 = ability2.get_hash()
    hash3 = ability3.get_hash()

    assert isinstance(hash1, float)
    assert hash1 != hash2
    assert hash1 == hash3
    assert hash1 == ability1.get_hash()  # Deterministic
