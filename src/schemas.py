from typing import List, Optional

from pydantic import BaseModel

from point import Point


class EntityState(BaseModel):
    id: int
    name: str
    hp: int
    pos: Optional[Point]
    team: int
    move_actions: int
    standard_actions: int
    free_actions: int


class EngineState(BaseModel):
    round_num: int
    current_team: int
    active_entity: Optional[int]
    entities: List[EntityState]


class ActionState(BaseModel):
    actor: int
    target: Optional[int]
    ability: str
    move_path: Optional[List[Point]] = None
    movement_name: str = ""


class ActionSim(BaseModel):
    action: ActionState
    after_state: EngineState
    done: bool
    winner_team: Optional[int] = None


class LogEntry(BaseModel):
    before_state: EngineState
    action: ActionState
    after_state: EngineState
    done: bool
    simulations: List[ActionSim] = []


class GameLog(BaseModel):
    winner_team: Optional[int]
    logs: List[LogEntry]
