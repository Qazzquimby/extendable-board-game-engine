import abc
import random
from typing import (
    Dict,
    List,
    Optional,
    TypeVar,
    Union,
    TYPE_CHECKING,
)

import copium
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
    EventPhase,
    query,
    Router,
    EventQueue,
    ReactionOpportunityEvent,
    DecisionEvent,
)
from event_library import (
    ChangeLocationEvent,
    DeployEvent,
    TurnStartEvent,
    TurnEndEvent,
    RoundStartEvent,
)
from grid import Grid
from logger import reset_logs, get_logs, log
from point import Point
from queries import QueryIsAlive, Query
from schemas import EngineState, GameLog, LogEntry, ActionState
from util import UniqueTuple

if TYPE_CHECKING:
    pass


ChoiceT = TypeVar("ChoiceT", bound="Choice")

NUM_TEAMS = 2
NUM_ROUNDS = 6


class Agent(abc.ABC):
    def __deepcopy__(self, memo):
        return self

    @abc.abstractmethod
    def choose(self, env: "Engine") -> int:
        pass


class RandomAgent(Agent):
    def choose(self, env: Optional["Engine"]) -> int:
        return random.randint(0, len(env.current_choices) - 1)


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
        self.round_num: int = 1

        self.team_heroes: List[List[Hero]] = None  # run finalize
        self.num_hero_rows: int = None  # run finalize

        self.current_team: int = 0
        self.current_hero_row_index = 0

        self.grid: Grid = grid
        if self.grid:
            self.grid.engine = self
        self.current_turn_hero: Optional["Entity"] = None
        self.active_entity: Optional["Entity"] = None
        self.activation_queue: List["Entity"] = []
        self.activation_index: int = -1
        self._next_id: int = 1
        self.current_choices = None
        self.is_resolving_action = False
        self.event_queue = EventQueue()

    @property
    def is_done(self):
        if self.round_num > NUM_ROUNDS:
            return True

        alive_teams = {e.team for e in self.living_entities}
        return len(alive_teams) <= 1

    def advance_until_active_entity(self) -> "Entity":
        while self.active_entity is None:
            self.next_turn()
            if self.is_done:
                break
        assert self.active_entity is not None
        return self.active_entity

    def get_legal_actions(self) -> UniqueTuple[Choice]:
        entity = self.active_entity
        if not entity or entity.hp <= 0 or self.is_done:
            return UniqueTuple()

        moves = get_plausible_move_and_actions(entity, self)
        frees = get_plausible_free_actions(entity, self)
        all_actions = moves + frees
        return UniqueTuple(all_actions)

    def finalize_setup(self):
        self.team_heroes = [
            [e for e in self.entities if e.team == team and e.activator == e]
            for team in range(NUM_TEAMS)
        ]
        self.num_hero_rows = max([len(team) for team in self.team_heroes])
        for entity in self.entities:
            self.event_queue.enqueue(DeployEvent(subject=entity))

    def get_choice_index(self, team: int, choices: UniqueTuple[ChoiceT]) -> int:
        if not choices:
            raise ValueError("Cannot request a choice from an empty list.")
        if len(choices) == 1:
            return 0
        self.current_choices = UniqueTuple(choices)
        index = self.agents[team].choose(env=self)
        self.current_choices = tuple()
        assert 0 <= index < len(choices)
        return index

    def get_choice(self, team: int, choices: UniqueTuple[ChoiceT]) -> ChoiceT:
        index = self.get_choice_index(team=team, choices=choices)
        return choices[index]

    def get_entity_by_id(self, entity_id: int) -> Optional["Entity"]:
        return next(
            (entity for entity in self.entities if entity.id == entity_id), None
        )

    def entity_at(self, pos: Point) -> Optional["Entity"]:
        return next(
            (entity for entity in self.living_entities if entity.pos == pos), None
        )

    def markers_at(self, pos: Point) -> List["Marker"]:
        return [marker for marker in self.markers if marker.pos == pos]

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

    def advance_until_choice(self) -> UniqueTuple[Choice]:
        while not self.is_done:
            if self.event_queue._queue:
                event = self.event_queue._queue[0]
                if isinstance(event, ReactionOpportunityEvent):
                    choices, entity = event.get_choices(engine=self)
                    if choices:
                        return choices
                    else:
                        self.event_queue._queue.pop(0)
                        continue
                elif isinstance(event, DecisionEvent):
                    choices = event.get_choices()
                    if choices:
                        return choices
                    else:
                        self.event_queue._queue.pop(0)
                        continue

                self.event_queue.process_one(engine=self)
                continue

            entity = self.advance_until_active_entity()
            if self.is_done:
                return UniqueTuple()

            if entity.hp <= 0:
                self.advance_to_next_activator()
                continue

            choices = self.get_legal_actions()
            if not choices:
                self.advance_to_next_activator()
                continue

            return choices

    def run_game(self) -> GameLog:
        logs: List[LogEntry] = []
        winner_team = None
        after_state = None
        self.event_queue.enqueue(RoundStartEvent())

        pbar = tqdm(total=NUM_ROUNDS * len(self.entities))
        self.next_turn()
        next_choices = self.advance_until_choice()

        while not self.is_done:
            pbar.update()
            if after_state:
                before_state = after_state
            else:
                before_state = self.to_model()

            action_index = self.get_choice_index(
                team=self.get_current_player(), choices=next_choices
            )
            action_choice = next_choices[action_index]

            self.step(
                action=action_choice,
                action_idx=action_index,
            )
            next_choices = self.advance_until_choice()

            is_done = self.is_done
            if is_done:
                team_0_living_members = [e for e in self.living_entities if e.team == 0]
                team_1_living_members = [e for e in self.living_entities if e.team == 1]
                if len(team_0_living_members) > len(team_1_living_members):
                    winner_team = 0
                elif len(team_1_living_members) > len(team_0_living_members):
                    winner_team = 1

            after_state = self.to_model()
            log_entry = LogEntry(
                before_state=before_state,
                action=ActionState.from_action_choice(
                    action_choice=action_choice, current_actor=self.get_current_actor()
                ),
                after_state=after_state,
                done=is_done,
                messages=get_logs(),
            )
            logs.append(log_entry)
            reset_logs()

        if after_state:
            logs.append(
                LogEntry(
                    before_state=after_state,
                    action=ActionState(
                        actor=-1, target=None, ability="None", movement_name="Game Over"
                    ),
                    after_state=after_state,
                    done=True,
                    messages=["Game Over"],
                )
            )

        pbar.close()
        return GameLog(winner_team=winner_team, logs=logs)

    def step(
        self,
        action: Union[PlausibleMoveAndAction, PlausibleFreeAction, Choice],
        action_idx: int,
    ) -> None:
        from events import AbilityUseEvent

        self.action_history.append(action_idx)
        self.current_choices = None

        # todo well this seems sloppy and insufficient
        #  Rewrite without get_attr and such that any mid-action choice can be handled.
        #  Example choices
        #  "target picks one, take 3 damage or be stunned"
        #  "You may take 2 damage to repeat this effect"
        #  "Target moves 3 spaces in a direction of their choice"

        if self.event_queue._queue:
            first_event = self.event_queue._queue[0]
            if isinstance(first_event, ReactionOpportunityEvent):
                event: ReactionOpportunityEvent = first_event
                choices, react_actor = event.get_choices(engine=self)
                event.declined_entities.add(react_actor.id)
                if not action.features.get("pass_reaction"):
                    with log(f"Reaction from {react_actor.name}:"):
                        reaction_event = AbilityUseEvent(
                            source=react_actor,
                            ability=action.ability,
                            aiming_result=action.aiming_result,
                            is_reaction=True,
                        )
                        self.event_queue._queue.insert(0, reaction_event)
                return
            elif isinstance(first_event, DecisionEvent):
                event: DecisionEvent = first_event
                self.event_queue._queue.pop(0)
                event.resolve_choice(action)
                return

        was_resolving = self.is_resolving_action
        self.is_resolving_action = True

        try:
            actor = getattr(action, "actor", self.active_entity)

            target_str = (
                f" on {action.target.name}" if getattr(action, "target", None) else ""
            )

            if isinstance(action, PlausibleMoveAndAction):
                for point in action.move_path:
                    self.event_queue.enqueue(
                        ChangeLocationEvent(subject=actor, new_pos=point)
                    )

            if hasattr(action, "ability"):
                with log(f"{actor.name} used {action.ability.name}{target_str}."):
                    self.event_queue.enqueue(
                        AbilityUseEvent(
                            source=actor,
                            ability=action.ability,
                            aiming_result=action.aiming_result,
                        )
                    )

            if isinstance(action, PlausibleMoveAndAction):
                self.advance_to_next_activator()
        finally:
            self.is_resolving_action = was_resolving

    def setup_activation_queue(self):
        self.activation_queue = [self.current_turn_hero] + [
            e
            for e in self.entities
            if e.activator == self.current_turn_hero and e != self.current_turn_hero
        ]
        self.activation_index = -1

    def advance_to_next_activator(self) -> None:
        self.activation_index += 1
        if self.activation_index < len(self.activation_queue):
            entity = self.activation_queue[self.activation_index]
            if entity.hp > 0:
                self.active_entity = entity
                return

            # recursively call to skip dead entities
            self.advance_to_next_activator()
        else:
            self.active_entity = None

    def _advance_hero_indices(self):
        self.current_team = (self.current_team + 1) % NUM_TEAMS
        if self.current_team == 0:  # just wrapped, get new hero index
            self.current_hero_row_index = (
                self.current_hero_row_index + 1
            ) % self.num_hero_rows
            if self.current_hero_row_index == 0:  # New round
                self.event_queue.enqueue(RoundStartEvent())

    def next_turn(self) -> None:
        self.action_history.append(-1)  # end turn

        if self.current_turn_hero is None:
            # First turn
            pass
        else:
            self.event_queue.enqueue(TurnEndEvent(subject=self.current_turn_hero))
            self._advance_hero_indices()

        while not self.is_done:
            new_current_activator = self._get_current_activator()
            if new_current_activator is None:
                continue

            self.current_turn_hero = new_current_activator
            self.event_queue.enqueue(TurnStartEvent(subject=self.current_turn_hero))

            self.setup_activation_queue()
            self.advance_to_next_activator()

            if self.active_entity is not None:
                return  # We found an active entity.

            # This hero's turn has no one to act (e.g. they and their summons are dead),
            # so end the turn and find the next.
            self.event_queue.enqueue(TurnEndEvent(subject=self.current_turn_hero))
            self._advance_hero_indices()

        # Game is done.
        self.active_entity = None

    def _get_current_activator(self) -> Optional["Entity"]:
        try:
            return self.team_heroes[self.current_team][self.current_hero_row_index]
        except IndexError:
            return None

    def ask(self, query: "Query"):
        self.router.publish(event=query, phase=EventPhase.QUERY)
        return query.result

    def to_model(self) -> EngineState:
        return EngineState(
            round_num=self.round_num,
            current_team=self.current_team,
            active_entity=self.active_entity.id if self.active_entity else None,
            entities=[e.to_model() for e in self.entities],
        )

    def copy(self) -> "Engine":
        return copium.deepcopy(self)

    def get_current_actor(self) -> Optional["Entity"]:
        if self.event_queue._queue:
            event = self.event_queue._queue[0]
            if isinstance(event, ReactionOpportunityEvent):
                choices, entity = event.get_choices(engine=self)
                if entity:
                    return entity
        return self.active_entity

    def get_current_player(self) -> int:
        actor = self.get_current_actor()
        if actor:
            return actor.team
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

    def _get_hash_info(self):
        entity_states = []
        for e in self.entities:
            abilities_state = tuple(ability.get_hash_info() for ability in e.abilities)
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
        if self.current_choices:
            choices = UniqueTuple(self.current_choices)
            assert len(choices) == len(self.current_choices)
        else:
            choices = None
        marker_states = UniqueTuple((m.id, m.name, m.pos, m.team) for m in self.markers)
        return (
            self.round_num,
            self.current_hero_row_index,
            self.current_team,
            self.current_turn_hero.id if self.current_turn_hero else None,
            self.active_entity.id if self.active_entity else None,
            self.event_queue,
            choices,
            UniqueTuple(entity_states),
            marker_states,
        )

    def __hash__(self) -> int:
        return hash(self._get_hash_info())
