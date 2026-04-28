from typing import List, Optional

from pydantic import BaseModel

from point import Point


class EntityState(BaseModel):
    id: int
    name: str
    hp: int
    pos: Point
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
    move_pos: Point
    target: Optional[int]
    ability: str
    path: Optional[List[Point]] = None
    movement_name: str = ""


class LogEntry(BaseModel):
    before_state: EngineState
    action: ActionState
    after_state: EngineState
    reward: float
    done: bool
