"""Auto-discovers Hero subclasses by scanning the heroes package directory.

Adding a new hero = drop a .py file in backend/src/heroes/. That's it.
"""

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Dict, Type

from entities import Hero


def _discover() -> Dict[str, Type]:
    heroes_pkg = Path(__file__).resolve().parent / "heroes"
    heroes = {}

    def _scan_module(mod_name):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            return
        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Hero) and obj is not Hero:
                heroes[name] = obj

    # Scan __init__.py for heroes defined there (MeleeHero, RangedHero)
    _scan_module("heroes")

    # Scan individual hero modules
    for importer, modname, is_pkg in pkgutil.iter_modules([str(heroes_pkg)]):
        if is_pkg or modname == "__init__":
            continue
        _scan_module(f"heroes.{modname}")

    return heroes


HERO_CLASSES = _discover()


def get_hero_class(name: str) -> Type:
    if name not in HERO_CLASSES:
        raise KeyError(f"Unknown hero '{name}'. Available: {list(HERO_CLASSES.keys())}")
    return HERO_CLASSES[name]


def list_heroes() -> list:
    return sorted(HERO_CLASSES.keys())
