from typing import List, Optional

from pydantic import BaseModel

from point import Point


class MarkerState(BaseModel):
    id: int
    name: str
    pos: Optional[Point]
    team: int
    modifiers: List[str] = []


class EntityState(BaseModel):
    id: int
    name: str
    hp: int
    pos: Optional[Point]
    team: int
    move_actions: int
    standard_actions: int
    free_actions: int
    modifiers: List[str] = []
    is_object: bool = False


class EngineState(BaseModel):
    round_num: int
    current_team: int
    active_entity: Optional[int]
    entities: List[EntityState]
    markers: List[MarkerState] = []


class ActionState(BaseModel):
    actor: int
    target: Optional[int]
    ability: str
    move_path: Optional[List[Point]] = None
    movement_name: str = ""

    @classmethod
    def from_action_choice(cls, action_choice, current_actor):
        return cls(
            actor=(
                getattr(action_choice, "actor", current_actor).id
                if getattr(action_choice, "actor", current_actor)
                else -1
            ),
            target=(
                action_choice.target.id
                if getattr(action_choice, "target", None)
                else None
            ),
            ability=(
                action_choice.ability.name
                if getattr(action_choice, "ability", None)
                else "None"
            ),
            move_path=getattr(action_choice, "move_path", None),
            movement_name=getattr(action_choice, "movement_name", "None"),
        )


class EventDescription(BaseModel):
    type: str = ""
    actor_id: Optional[int] = None
    target_id: Optional[int] = None
    ability_name: Optional[str] = None
    amount: Optional[int] = None
    move_path: Optional[List[Point]] = None
    source_id: Optional[int] = None
    target_pos: Optional[Point] = None
    source_pos: Optional[Point] = None


class LogEntry(BaseModel):
    state: EngineState
    events: List[EventDescription] = []
    messages: List[str] = []
    action_logs: List[str] = []  # Hierarchical logger output for this action
    done: bool = False


class GameLog(BaseModel):
    winner_team: Optional[int]
    logs: List[LogEntry]
