import abc
import random
import copy
from dataclasses import dataclass, field
from typing import (
    List,
    Optional,
    Dict,
)

from entities import Entity, Summon
from events import (
    TurnStartEvent,
    TurnEndEvent,
    EventPhase,
    query,
    before,
    Router,
)
from grid import Grid
from point import Point
from abilities import Ability
from queries import (
    QueryIsAlive,
    QueryHasArmor,
    QueryLegalActions,
    QueryCanMove,
    QuerySpeed,
)
from schemas import EngineState
from base_environment import BaseEnvironment

# ==========================================
# CORE ENGINE & ENTITIES
# ==========================================


class Choice:
    def __init__(self, features: Optional[Dict[str, float]] = None):
        self.features = features or {}


class MoveAndActionChoice(Choice):
    def __init__(
        self,
        move_pos: Point,
        ability: Optional["Ability"] = None,
        target_point: Optional[Point] = None,
        features: Optional[Dict[str, float]] = None,
    ):
        super().__init__(features)
        self.move_pos = move_pos
        self.ability = ability
        self.target_point = target_point


class Agent(abc.ABC):
    @abc.abstractmethod
    def choose(self, choices: List[Choice]) -> int:
        pass


class Engine:
    def __init__(
        self,
        seed: int = 42,
        grid: Grid = None,
        agents: Optional[Dict[int, Agent]] = None,
    ) -> None:
        BaseEnvironment.__init__(self)
        self.router = Router()
        self.agents: Dict[int, Agent] = agents or {}
        self.entities: List["Entity"] = []
        self.markers: List["Marker"] = []
        self.rng = random.Random(seed)
        self.round_num: int = 1
        self.current_team: int = 1
        self.grid: Grid = grid
        self.active_entity: Optional["Entity"] = None
        self._next_id: int = 1
        self._entity_by_pos: Dict[Point, "Entity"] = {}
        self._markers_by_pos: Dict[Point, List["Marker"]] = {}

    def request_choice(self, team: int, choices: List[Choice]) -> int:
        if not choices:
            raise ValueError("Cannot request a choice from an empty list.")
        if len(choices) == 1:
            return 0
        if team in self.agents:
            return self.agents[team].choose(choices)
        return self.rng.randrange(len(choices))

    def entity_at(self, pos: Point) -> Optional["Entity"]:
        return self._entity_by_pos.get(pos)

    def markers_at(self, pos: Point) -> List["Marker"]:
        return self._markers_by_pos.get(pos, [])

    @property
    def living_entities(self) -> List["Entity"]:
        alive = []
        for entity in self.entities:
            q = QueryIsAlive(entity)
            self.router.publish(q, EventPhase.QUERY)
            if q.result:
                alive.append(entity)
        return alive

    def generate_id(self) -> int:
        res = self._next_id
        self._next_id += 1
        return res

    def add_entity(self, entity: "Entity") -> None:
        self.entities.append(entity)

    def next_turn(self) -> None:
        if not self.entities:
            return

        if self.active_entity is not None:
            TurnEndEvent(self, self.active_entity).resolve()
        if self.active_entity is None:
            self.active_entity = self.entities[0]
        else:
            idx = self.entities.index(self.active_entity)
            if idx + 1 < len(self.entities):
                self.active_entity = self.entities[idx + 1]
            else:
                self.active_entity = self.entities[0]
                self.round_num += 1

        self.current_team = self.active_entity.team

        TurnStartEvent(self, self.active_entity).resolve()

    def to_model(self) -> EngineState:
        return EngineState(
            round_num=self.round_num,
            current_team=self.current_team,
            active_entity=self.active_entity.id if self.active_entity else None,
            entities=[e.to_model() for e in self.entities],
        )

    def copy(self) -> "Engine":
        return copy.deepcopy(self)

    def get_current_player(self) -> int:
        return self.current_team

    def _get_state(self):
        return self

    def get_winning_player(self) -> Optional[int]:
        if not self.is_done():
            return None
        team_0 = [e for e in self.entities if e.team == 0 and e.hp > 0]
        team_1 = [e for e in self.entities if e.team == 1 and e.hp > 0]
        if len(team_0) > len(team_1):
            return 0
        elif len(team_1) > len(team_0):
            return 1
        return None

    def get_network_spec(self) -> Dict:
        return {}

    def is_done(self) -> bool:
        if self.round_num > 6:
            return True

        alive_teams = {e.team for e in self.living_entities}
        return len(alive_teams) <= 1

    def hash(self) -> int:
        entity_states = frozenset(
            (e.id, e.hp, e.pos, e.move_actions, e.standard_actions, e.free_actions)
            for e in self.entities
            if getattr(e, "hp", 0) > 0
        )
        return hash(
            (
                self.round_num,
                self.current_team,
                self.active_entity.id if self.active_entity else None,
                entity_states,
            )
        )


class Modifier:
    owner: Entity = field(init=False)


class SummonModifier(Modifier):
    owner: Summon = field(init=False)


class Token(Modifier):
    def __init__(self, amount: int = 1):
        self.amount = amount

    def add(self, amount: int) -> None:
        self.amount += amount

    def remove(self, amount: int) -> None:
        self.amount -= amount
        if self.amount <= 0:
            self.owner.remove_modifier(self)


class Immobile(Modifier):
    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False


class ImmobileToken(Immobile, Token):
    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, event: TurnEndEvent) -> None:
        if self in self.owner.modifiers:
            self.owner.remove_modifier(self)


class Stunned(Modifier):
    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False

    @query(QueryLegalActions)
    def prevent_actions(self, q: QueryLegalActions) -> None:
        q.result = []

    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, event: TurnEndEvent) -> None:
        # todo, we'd rather modify the modifier somehow
        #  Immobile().until(TurnEndEvent, target=self.owner) or something.
        #  Immobile doesn't inherently last one turn. Everything can have any duration or condition
        #  eg Nearby enemies are immobile
        if self in self.owner.modifiers:
            self.owner.remove_modifier(self)


class Slow(Modifier):
    def __init__(self, amount: int):
        self.amount = amount

    @query(QuerySpeed)
    def reduce_speed(self, q: QuerySpeed) -> None:
        q.result.add(-self.amount)


class SlowToken(Slow, Token):
    @before(TurnEndEvent)
    def clear_at_end_of_turn(self, event: TurnEndEvent) -> None:
        # todo, we'd rather modify the modifier somehow
        #  Immobile().until(TurnEndEvent, target=self.owner) or something.
        #  Immobile doesn't inherently last one turn. Everything can have any duration or condition
        #  eg Nearby enemies are immobile
        if self in self.owner.modifiers:
            self.owner.remove_modifier(self)


@dataclass
class Taunted(Modifier):
    taunter: Entity

    @query(QueryLegalActions)
    def force_attack(self, q: QueryLegalActions) -> None:
        forced_actions = []
        # for ability in self.owner.abilities:
        for (
            ability
        ) in (
            q.result
        ):  # It should start initialized to all legal actions including move.
            if ability.is_default:
                import copy

                action = copy.deepcopy(ability)
                action.subject = self.taunter
                forced_actions.append(action)
        q.result = forced_actions
        self.owner.remove_modifier(self)

    @query(QueryCanMove)
    def prevent_move(self, q: QueryCanMove) -> None:
        q.result = False


class InnateArmor(Modifier):
    @query(QueryHasArmor)
    def grant_armor(self, q: QueryHasArmor) -> None:
        q.result = True
