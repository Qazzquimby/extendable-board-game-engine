"""Tests for damage modifiers stacking (e02s02) and charges (e04s03)."""

from src.mod_value import ModInt


def test_mod_int_add():
    """ModInt addition works."""
    mv = ModInt(5)
    mv.add(3)
    assert int(mv) == 8


def test_mod_int_multiply():
    """ModInt multiplication works."""
    mv = ModInt(4)
    mv.mult(1.5)
    mv.mult(2.0)
    val = int(mv)
    assert val > 4
