import abc
import random
import copy
from typing import (
    List,
    Optional,
    Dict,
    TypeVar,
)

from choices import get_plausible_move_and_actions, Choice, PlausibleMoveAndAction
from entities import Entity, Marker, Hero
from events import (
    TurnStartEvent,
    TurnEndEvent,
    EventPhase,
    query,
    Router,
    Query,
    ChangeLocationEvent,
    RoundEndEvent,
    RoundStartEvent,
)
from grid import Grid
from point import Point
from queries import (
    QueryIsAlive,
)
from schemas import EngineState, GameLog, LogEntry, ActionState

ChoiceT = TypeVar("ChoiceT", bound="Choice")

NUM_TEAMS = 2


class Agent(abc.ABC):
    @abc.abstractmethod
    def choose(self, choices: List["Choice"]) -> int:
        pass


class RandomAgent(Agent):
    def choose(self, choices: List["Choice"]) -> int:
        return random.randint(0, len(choices) - 1)


class Engine:
    def __init__(
        self,
        seed: int = 42,
        grid: Grid = None,
        agents: Optional[Dict[int, Agent]] = None,
    ) -> None:
        self.router = Router()
        self.agents: Dict[int, Agent] = agents or {}
        self.entities: List["Entity"] = []
        self.markers: List["Marker"] = []
        self.rng = random.Random(seed)
        self.round_num: int = 1

        self.team_heroes: List[List[Hero]] = None  # run finalize
        self.num_hero_rows: int = None  # run finalize

        self.current_team: int = 0
        self.current_hero_row_index = 0

        self.grid: Grid = grid
        self.current_hero: Optional["Entity"] = None
        self._next_id: int = 1
        self._entity_by_pos: Dict[Point, "Entity"] = {}
        self._markers_by_pos: Dict[Point, List["Marker"]] = {}

    def finalize_setup(self):
        self.team_heroes = [
            [e for e in self.entities if e.team == team] for team in range(NUM_TEAMS)
        ]
        self.num_hero_rows = max([len(team) for team in self.team_heroes])

    def get_choice_index(self, team: int, choices: List[ChoiceT]) -> int:
        if not choices:
            raise ValueError("Cannot request a choice from an empty list.")
        if len(choices) == 1:
            return 0
        index = self.agents[team].choose(choices)
        return index

    def get_choice(self, team: int, choices: List[ChoiceT]) -> ChoiceT:
        index = self.get_choice_index(team=team, choices=choices)
        return choices[index]

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

    def run_game(self) -> GameLog:
        logs: List[LogEntry] = []

        winner_team = None

        after_state = None

        RoundStartEvent(engine=self).resolve()

        while self.round_num <= 6:
            self.next_turn()
            if after_state:
                before_state = after_state
            else:
                before_state = self.to_model()

            if self.current_hero.hp <= 0:
                self.next_turn()  # todo doesn't work with summons
                continue

            agent = self.agents[self.current_hero.team]
            feature_evaluator = getattr(agent, "feature_evaluator", None)
            plausible_actions: List[PlausibleMoveAndAction] = (
                get_plausible_move_and_actions(
                    actor=self.current_hero,
                    engine=self,
                    feature_evaluator=feature_evaluator,
                )
            )
            chosen_action: PlausibleMoveAndAction = self.get_choice(
                team=self.current_hero.team, choices=plausible_actions
            )
            self.step(actor=self.current_hero, action=chosen_action)

            # Check win condition
            time_up = self.round_num >= 6
            team_0_living_members = [
                e for e in self.entities if e.team == 0 and e.hp > 0
            ]
            team_1_living_members = [
                e for e in self.entities if e.team == 1 and e.hp > 0
            ]
            done = time_up or not team_0_living_members or not team_1_living_members
            if done:
                if len(team_0_living_members) > len(team_1_living_members):
                    winner_team = 0
                elif len(team_1_living_members) > len(team_0_living_members):
                    winner_team = 1

            action_state = ActionState(
                actor=self.current_hero.id,
                target=chosen_action.target.id if chosen_action.target else None,
                ability=chosen_action.ability.name,
                move_path=chosen_action.move_path,
                movement_name=chosen_action.movement_name,
            )
            after_state = self.to_model()
            log_entry = LogEntry(
                before_state=before_state,
                action=action_state,
                after_state=after_state,
                done=done,
            )
            logs.append(log_entry)

            if done:
                break

        return GameLog(winner_team=winner_team, logs=logs)

    def step(self, actor: Entity, action: PlausibleMoveAndAction) -> None:
        for point in action.move_path:
            ChangeLocationEvent(self, actor, point).resolve()
        action.ability.execute(
            engine=self, source=actor, aiming_result=action.aiming_result
        )

    def next_turn(self) -> None:
        will_be_first_turn = self.current_hero is None

        if not will_be_first_turn:
            TurnEndEvent(self, self.current_hero).resolve()

            self.current_team = (self.current_team + 1) % NUM_TEAMS
            if self.current_team == 0:  # just wrapped, get new hero index
                self.current_hero_row_index = (
                    self.current_hero_row_index + 1
                ) % self.num_hero_rows
                if self.current_hero_row_index == 0:  # New round
                    RoundEndEvent(self).resolve()
                    RoundStartEvent(self).resolve()

        self.current_hero = self._get_current_hero()
        TurnStartEvent(self, self.current_hero).resolve()

    def _get_current_hero(self):
        return self.team_heroes[self.current_team][self.current_hero_row_index]

    def ask(self, query: "Query"):
        self.router.publish(query, EventPhase.QUERY)
        return query.result

    def to_model(self) -> EngineState:
        return EngineState(
            round_num=self.round_num,
            current_team=self.current_team,
            active_entity=self.current_hero.id if self.current_hero else None,
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
                self.current_hero.id if self.current_hero else None,
                entity_states,
            )
        )
