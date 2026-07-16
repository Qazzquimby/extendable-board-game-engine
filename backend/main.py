"""FastAPI server for running tactical board game simulations.

Provides endpoints to list available heroes and run full games.
"""

import importlib
import inspect
import sys
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Ensure backend/src/ is on the path so we can import engine modules
_src_path = str(Path(__file__).resolve().parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from engine import Engine, RuleBasedAgent
from entities import Hero
from game_setup import GameSetup
from grid import Grid
from point import Point
from schemas import GameLog

# ── Discover hero classes ──────────────────────────────────────────────


def _discover_hero_classes() -> Dict[str, type]:
    """Import all hero modules and return {class_name: class} mapping."""
    heroes = {}

    # todo automate dont duplicate
    # Known hero modules to scan
    hero_modules = [
        "heroes",  # __init__.py has MeleeHero, RangedHero
        "heroes.axe",
        "heroes.necrophos",
        "heroes.reinhardt",
        "heroes.spy",
        "heroes.symmetra",
        "heroes.tracer",
        "heroes.viktoria",
    ]

    for mod_name in hero_modules:
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue

        for name, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Hero) and obj is not Hero:
                heroes[name] = obj

    return heroes


_HERO_CLASSES = _discover_hero_classes()


# ── Request / Response schemas ─────────────────────────────────────────


class HeroPlacement(BaseModel):
    class_name: str = Field(alias="class")
    pos: List[int]  # [x, y]

    model_config = {"populate_by_name": True}


class TeamConfig(BaseModel):
    heroes: List[HeroPlacement]


class RunGameRequest(BaseModel):
    seed: int = 42
    grid_size: int = 5
    teams: List[TeamConfig]


# ── FastAPI app ────────────────────────────────────────────────────────

app = FastAPI(title="Game Runner API")


@app.get("/heroes")
def list_heroes() -> List[str]:
    """Return the list of available hero class names."""
    return sorted(_HERO_CLASSES.keys())


@app.post("/run-game", response_model=GameLog)
def run_game(req: RunGameRequest) -> GameLog:
    """Run a game with the given team configuration and return the game log."""
    # Validate hero classes
    for team_idx, team in enumerate(req.teams):
        for hero_placement in team.heroes:
            if hero_placement.class_name not in _HERO_CLASSES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown hero class '{hero_placement.class_name}' in team {team_idx}",
                )

    # Check for overlapping positions within a team
    for team_idx, team in enumerate(req.teams):
        positions = [tuple(h.pos) for h in team.heroes]
        if len(positions) != len(set(positions)):
            raise HTTPException(
                status_code=400,
                detail=f"Overlapping hero positions in team {team_idx}",
            )

    # Validate positions are within grid bounds
    for team_idx, team in enumerate(req.teams):
        for hero_placement in team.heroes:
            x, y = hero_placement.pos
            if not (0 <= x < req.grid_size and 0 <= y < req.grid_size):
                raise HTTPException(
                    status_code=400,
                    detail=f"Position {hero_placement.pos} out of bounds for grid size {req.grid_size}",
                )

    # Build engine with agents keyed by team index
    agent = RuleBasedAgent()
    agents = {0: agent, 1: agent}

    engine = Engine(
        grid=Grid(req.grid_size, req.grid_size),
        agents=agents,
        seed=req.seed,
    )

    for team_idx, team in enumerate(req.teams):
        for hero_placement in team.heroes:
            hero_class = _HERO_CLASSES[hero_placement.class_name]
            hero_class(
                engine=engine,
                pos=Point(hero_placement.pos[0], hero_placement.pos[1]),
                team=team_idx,
            )

    engine.finalize_setup()

    # Run the game
    game_log = engine.run_game()

    return game_log


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
