import sys
from pathlib import Path
from typing import List

# Ensure backend/src is on sys.path so engine modules can be imported directly
_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from hero_registry import get_hero_class, list_heroes

from engine import Engine, RuleBasedAgent
from grid import Grid
from point import Point
from schemas import GameLog


class HeroPlacement(BaseModel):
    class_name: str = Field(alias="class")
    pos: List[int]

    model_config = {"populate_by_name": True}


class TeamConfig(BaseModel):
    heroes: List[HeroPlacement]


class RunGameRequest(BaseModel):
    seed: int = 42
    grid_size: int = 5
    teams: List[TeamConfig]


app = FastAPI(title="Game Runner API")


@app.get("/heroes")
def list_available_heroes() -> List[str]:
    return list_heroes()


@app.post("/run-game", response_model=GameLog)
def run_game(req: RunGameRequest) -> GameLog:
    hero_classes = _resolve_hero_classes(req)
    _validate_positions(req)

    agents = {0: RuleBasedAgent(), 1: RuleBasedAgent()}
    engine = Engine(
        grid=Grid(req.grid_size, req.grid_size), agents=agents, seed=req.seed
    )
    _create_entities(engine, req, hero_classes)

    engine.finalize_setup()
    return engine.run_game()


def _resolve_hero_classes(req: RunGameRequest):
    result = []
    for team_idx, team in enumerate(req.teams):
        team_map = {}
        for h in team.heroes:
            try:
                team_map[h.class_name] = get_hero_class(h.class_name)
            except KeyError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown hero '{h.class_name}' in team {team_idx}",
                )
        result.append(team_map)
    return result


def _validate_positions(req: RunGameRequest):
    all_positions: dict[tuple[int, int], int] = {}  # pos -> team_idx
    for team_idx, team in enumerate(req.teams):
        for h in team.heroes:
            key = tuple(h.pos)
            if not (0 <= h.pos[0] < req.grid_size and 0 <= h.pos[1] < req.grid_size):
                raise HTTPException(
                    status_code=400,
                    detail=f"Position {h.pos} out of bounds for {req.grid_size}x{req.grid_size}",
                )
            if key in all_positions:
                other_team = all_positions[key]
                if other_team == team_idx:
                    detail = f"Overlapping positions in team {team_idx} at {h.pos}"
                else:
                    detail = f"Overlapping positions across teams at {h.pos}"
                raise HTTPException(status_code=400, detail=detail)
            all_positions[key] = team_idx


def _create_entities(engine, req, hero_classes):
    for team_idx, team in enumerate(req.teams):
        for h in team.heroes:
            hero_classes[team_idx][h.class_name](
                engine=engine,
                pos=Point(h.pos[0], h.pos[1]),
                team=team_idx,
            )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
