import abc
import random
import copy
from typing import (
    Dict,
    List,
    Optional,
    TypeVar,
    Union,
)

from tqdm import tqdm

from choices import (
    Choice,
    PlausibleFreeAction,
    PlausibleMoveAndAction,
    get_plausible_free_actions,
    get_plausible_move_and_actions,
)
from entities import Entity, Marker, Hero
from events import (
    TurnStartEvent,
    TurnEndEvent,
    EventPhase,
    query,
    Router,
    ChangeLocationEvent,
    RoundStartEvent,
)
from grid import Grid
from logger import reset_logs, get_logs, log
from point import Point
from queries import QueryIsAlive, Query
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


class TrackedRandom(random.Random):
    def __init__(self, seed=None):
        super().__init__(seed)
        self.stochastic_flag = False

    def random(self):
        self.stochastic_flag = True
        return super().random()

    def randint(self, a, b):
        self.stochastic_flag = True
        return super().randint(a, b)

    def choice(self, seq):
        self.stochastic_flag = True
        return super().choice(seq)

    def shuffle(self, x, random=None):
        self.stochastic_flag = True
        super().shuffle(x, random)

    def sample(self, population, k, counts=None):
        self.stochastic_flag = True
        return super().sample(population, k, counts=counts)


class Engine:
    def __init__(
        self,
        seed: int = 42,
        grid: Grid = None,
        agents: Optional[Dict[int, Agent]] = None,
        setup: Optional["GameSetup"] = None,
    ) -> None:
        self.setup = setup
        self.initial_seed = seed
        self.action_history = []
        self.router = Router()
        self.agents: Dict[int, Agent] = agents or {}
        self.entities: List["Entity"] = []
        self.markers: List["Marker"] = []
        self.rng = TrackedRandom(seed)
        self.round_num: int = 0

        self.team_heroes: List[List[Hero]] = None  # run finalize
        self.num_hero_rows: int = None  # run finalize

        self.current_team: int = 0
        self.current_hero_row_index = 0

        self.grid: Grid = grid
        self.current_hero: Optional["Entity"] = None
        self._next_id: int = 1
        self._entity_by_pos: Dict[Point, "Entity"] = {}
        self._markers_by_pos: Dict[Point, List["Marker"]] = {}

    @property
    def is_done(self):
        if self.round_num > 6:
            return True

        alive_teams = {e.team for e in self.living_entities}
        return len(alive_teams) <= 1

    def get_legal_actions(self) -> List[Choice]:
        if self.is_done or not self.current_hero or self.current_hero.hp <= 0:
            return []
        agent = self.agents.get(self.current_hero.team)
        feature_evaluator = getattr(agent, "feature_evaluator", None) if agent else None
        moves = get_plausible_move_and_actions(
            self.current_hero, self, feature_evaluator
        )
        frees = get_plausible_free_actions(self.current_hero, self, feature_evaluator)
        return moves + frees

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

        pbar = tqdm(total=6 * len(self.entities))
        while self.round_num <= 6:
            pbar.update()
            self.next_turn()
            if after_state:
                before_state = after_state
            else:
                before_state = self.to_model()

            if self.current_hero.hp <= 0:
                continue  # skip this turn, they're dead.

            # agent = self.agents[self.current_hero.team]
            # feature_evaluator = getattr(agent, "feature_evaluator", None)
            chosen_action: PlausibleMoveAndAction = None
            turn_over = False
            while not turn_over:
                all_choices = self.get_legal_actions()
                if not all_choices:
                    turn_over = True  # eg stunned
                    continue

                action_index = self.get_choice_index(
                    team=self.current_hero.team, choices=all_choices
                )
                action_choice = all_choices[action_index]

                if isinstance(action_choice, PlausibleMoveAndAction):
                    self.step(
                        actor=self.current_hero,
                        action=action_choice,
                        action_idx=action_index,
                    )
                    chosen_action = action_choice
                    turn_over = True
                elif isinstance(action_choice, PlausibleFreeAction):
                    self.step(
                        actor=self.current_hero,
                        action=action_choice,
                        action_idx=action_index,
                    )

            if not chosen_action:
                continue

            # Check win condition
            time_up = self.round_num >= 7
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
                messages=get_logs(),
            )
            logs.append(log_entry)
            reset_logs()

            if done:
                break

        pbar.close()
        return GameLog(winner_team=winner_team, logs=logs)

    def step(
        self,
        action: Union[PlausibleMoveAndAction, PlausibleFreeAction],
        action_idx: int,
        actor: Optional[Entity] = None,
    ) -> None:
        self.action_history.append(action_idx)

        if actor is None:
            actor = self.current_hero

        target_str = f" on {action.target.name}" if action.target else ""

        if isinstance(action, PlausibleMoveAndAction):
            for point in action.move_path:
                ChangeLocationEvent(actor, point).resolve()

        # todo cover included entities. Make aiming_result __str__
        with log(f"{actor.name} used {action.ability.name}{target_str}."):
            # current_ability = next(
            #     (a for a in actor.abilities if a.name == action.ability.name),
            #     action.ability,
            # )  # todo why not use action.ability
            # assert action.ability.name == current_ability.name
            action.ability.execute(
                engine=self, source=actor, aiming_result=action.aiming_result
            )

    def _advance_hero_indices(self):
        self.current_team = (self.current_team + 1) % NUM_TEAMS
        if self.current_team == 0:  # just wrapped, get new hero index
            self.current_hero_row_index = (
                self.current_hero_row_index + 1
            ) % self.num_hero_rows
            if self.current_hero_row_index == 0:  # New round
                RoundStartEvent(self).resolve()

    def next_turn(self) -> None:
        self.action_history.append(-1)  # end turn
        will_be_first_turn = self.current_hero is None

        if not will_be_first_turn:
            TurnEndEvent(self.current_hero).resolve()
            self._advance_hero_indices()

        for i in range(99):
            new_current_hero = self._get_current_hero()
            if new_current_hero is None:
                self._advance_hero_indices()
            else:
                self.current_hero = new_current_hero
                TurnStartEvent(self.current_hero).resolve()
                return

    def _get_current_hero(self) -> Optional["Entity"]:
        try:
            return self.team_heroes[self.current_team][self.current_hero_row_index]
        except IndexError:
            return None

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
        if not self.is_done:
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

    def hash(self) -> int:
        entity_states = []
        for e in self.entities:
            abilities_state = tuple(
                (a.name, getattr(a, "is_tapped", False), getattr(a, "charges", None))
                for a in e.abilities
            )
            modifiers_state = tuple(m.__class__.__name__ for m in e.modifiers)
            entity_states.append(
                (
                    e.id,
                    e.hp,
                    e.pos,
                    e.move_actions,
                    e.standard_actions,
                    e.free_actions,
                    abilities_state,
                    modifiers_state,
                )
            )
        marker_states = frozenset((m.id, m.name, m.pos, m.team) for m in self.markers)
        return hash(
            (
                self.round_num,
                self.current_hero_row_index,
                self.current_team,
                self.current_hero.id if self.current_hero else None,
                frozenset(entity_states),
                marker_states,
            )
        )
