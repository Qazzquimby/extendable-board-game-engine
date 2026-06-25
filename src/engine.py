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

from abilities import Ability, ActionCost, RollResult
from aimings import AimingResult
from choices import (
    Choice,
    PlausibleFreeAction,
    PlausibleMoveAndAction,
    _get_plausible_uses_of_ability_at_pos,
    get_plausible_free_actions,
    get_plausible_move_and_actions,
)
from entities import Entity, Marker, Hero
from events import (
    EventPhase,
    query,
    Router,
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

ChoiceT = TypeVar("ChoiceT", bound="Choice")

NUM_TEAMS = 2
NUM_ROUNDS = 6


class Agent(abc.ABC):
    @abc.abstractmethod
    def choose(self, env: "Engine") -> int:
        pass


class RandomAgent(Agent):
    def choose(self, env: Optional["Engine"]) -> int:
        choices = env.current_choices
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
        self._reaction_declined_sets: List[set] = []
        self.current_choices = None
        self.is_resolving_action = False
        self.event_queue: List[tuple] = []
        self.current_reaction_choices: Optional[tuple[Choice]] = None
        self.current_reaction_team: Optional[int] = None
        self.current_reaction_entity: Optional["Entity"] = None
        self.current_reaction_key: Optional[tuple] = None

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
        return self.active_entity

    def get_legal_actions(self) -> tuple[Choice]:
        if self.current_reaction_choices is not None:
            return self.current_reaction_choices

        entity = self.active_entity
        if not entity or entity.hp <= 0 or self.is_done:
            return tuple()

        moves = get_plausible_move_and_actions(entity, self)
        frees = get_plausible_free_actions(entity, self)
        all_actions = moves + frees
        deduped = tuple(dict.fromkeys(all_actions))
        return deduped

    def finalize_setup(self):
        self.team_heroes = [
            [e for e in self.entities if e.team == team and e.activator == e]
            for team in range(NUM_TEAMS)
        ]
        self.num_hero_rows = max([len(team) for team in self.team_heroes])
        for entity in self.entities:
            DeployEvent(entity).resolve()

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

    def run_game(self) -> GameLog:
        logs: List[LogEntry] = []
        winner_team = None
        after_state = None
        RoundStartEvent(engine=self).resolve()

        pbar = tqdm(total=NUM_ROUNDS * len(self.entities))
        self.next_turn()

        while not self.is_done:
            if self.advance_event_queue():
                team = self.current_reaction_team
                choices = self.current_reaction_choices
                action_index = self.get_choice_index(team=team, choices=choices)
                action_choice = choices[action_index]
                self.step(action=action_choice, action_idx=action_index)
                continue

            entity = self.advance_until_active_entity()
            if self.is_done:
                break
            pbar.update()
            if after_state:
                before_state = after_state
            else:
                before_state = self.to_model()

            if entity.hp <= 0:
                self.advance_to_next_activator()
                continue

            all_choices = self.get_legal_actions()
            if not all_choices:
                self.advance_to_next_activator()
                continue

            action_index = self.get_choice_index(team=entity.team, choices=all_choices)
            action_choice = all_choices[action_index]

            self.step(
                actor=entity,
                action=action_choice,
                action_idx=action_index,
            )

            while self.event_queue:
                if self.advance_event_queue():
                    team = self.current_reaction_team
                    choices = self.current_reaction_choices
                    action_index = self.get_choice_index(team=team, choices=choices)
                    action_choice_react = choices[action_index]
                    self.step(action=action_choice_react, action_idx=action_index)

            if isinstance(action_choice, PlausibleMoveAndAction):
                self.advance_to_next_activator()

            is_done = self.is_done
            if is_done:
                team_0_living_members = [e for e in self.living_entities if e.team == 0]
                team_1_living_members = [e for e in self.living_entities if e.team == 1]
                if len(team_0_living_members) > len(team_1_living_members):
                    winner_team = 0
                elif len(team_1_living_members) > len(team_0_living_members):
                    winner_team = 1

            action_state = ActionState(
                actor=entity.id,
                target=(
                    action_choice.target.id
                    if getattr(action_choice, "target", None)
                    else None
                ),
                ability=(
                    action_choice.ability.name
                    if getattr(action_choice, "ability", None)
                    else "Pass"
                ),
                move_path=getattr(action_choice, "move_path", None),
                movement_name=getattr(action_choice, "movement_name", None),
            )
            after_state = self.to_model()
            log_entry = LogEntry(
                before_state=before_state,
                action=action_state,
                after_state=after_state,
                done=is_done,
                messages=get_logs(),
            )
            logs.append(log_entry)
            reset_logs()

        pbar.close()
        return GameLog(winner_team=winner_team, logs=logs)

    def step(
        self,
        action: Union[PlausibleMoveAndAction, PlausibleFreeAction, Choice],
        action_idx: int,
        actor: Optional[Entity] = None,
    ) -> None:
        self.action_history.append(action_idx)

        if self.current_reaction_choices is not None:
            self.current_reaction_choices = None
            self.current_reaction_team = None

            if action.features.get("pass_reaction"):
                self._reaction_declined_sets[-1].add(self.current_reaction_key)
                event = self.event_queue.pop()
                assert event[0] == "reaction_phase_wait"
                _, ability, source, aiming_result, roll_result, phase, entity_idx = (
                    event
                )
                self.event_queue.append(
                    (
                        "reaction_phase",
                        ability,
                        source,
                        aiming_result,
                        roll_result,
                        phase,
                        entity_idx + 1,
                    )
                )
            else:
                event = self.event_queue.pop()
                assert event[0] == "reaction_phase_wait"
                _, ability, source, aiming_result, roll_result, phase, entity_idx = (
                    event
                )

                self._reaction_declined_sets[-1].clear()
                self.event_queue.append(
                    (
                        "reaction_phase",
                        ability,
                        source,
                        aiming_result,
                        roll_result,
                        phase,
                        0,
                    )
                )

                react_actor = self.current_reaction_entity
                with log(f"Reaction from {react_actor.name}:"):
                    action.ability.execute(
                        engine=self,
                        source=react_actor,
                        aiming_result=action.aiming_result,
                    )
            self.current_reaction_entity = None
            self.current_reaction_key = None
            return

        was_resolving = self.is_resolving_action
        self.is_resolving_action = True

        try:
            if actor is None:
                actor = self.current_turn_hero

            target_str = (
                f" on {action.target.name}" if getattr(action, "target", None) else ""
            )

            if isinstance(action, PlausibleMoveAndAction):
                for point in action.move_path:
                    ChangeLocationEvent(actor, point).resolve()

            with log(f"{actor.name} used {action.ability.name}{target_str}."):
                action.ability.execute(
                    engine=self, source=actor, aiming_result=action.aiming_result
                )
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
                RoundStartEvent(self).resolve()

    def next_turn(self) -> None:
        self.action_history.append(-1)  # end turn

        if self.current_turn_hero is None:
            # First turn
            pass
        else:
            TurnEndEvent(self.current_turn_hero).resolve()
            self._advance_hero_indices()

        while not self.is_done:
            new_current_activator = self._get_current_activator()
            if new_current_activator is None:
                continue

            self.current_turn_hero = new_current_activator
            TurnStartEvent(self.current_turn_hero).resolve()

            self.setup_activation_queue()
            self.advance_to_next_activator()

            if self.active_entity is not None:
                return  # We found an active entity.

            # This hero's turn has no one to act (e.g. they and their summons are dead),
            # so end the turn and find the next.
            TurnEndEvent(self.current_turn_hero).resolve()
            self._advance_hero_indices()

        # Game is done.
        self.active_entity = None

    def _get_current_activator(self) -> Optional["Entity"]:
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
            active_entity=self.active_entity.id if self.active_entity else None,
            entities=[e.to_model() for e in self.entities],
        )

    def resolve_ability_with_reactions(
        self, ability: "Ability", source: "Entity", aiming_result: "AimingResult"
    ):
        roll_result = ability.get_roll_result(
            aiming_result=aiming_result, engine=self, source=source
        )
        self._reaction_declined_sets.append(set())

        self.event_queue.append(("pop_declined_set",))
        self.event_queue.append(
            ("reaction_phase", ability, source, aiming_result, roll_result, "after", 0)
        )
        self.event_queue.append(
            ("execute_instructions", ability, source, aiming_result, roll_result)
        )
        self.event_queue.append(
            ("reaction_phase", ability, source, aiming_result, roll_result, "before", 0)
        )

    def advance_event_queue(self) -> bool:
        """Processes events. Returns True if a choice is needed, False if queue is empty."""
        from choices import (
            Choice,
            PlausibleFreeAction,
            _get_plausible_uses_of_ability_at_pos,
        )
        from abilities import ActionCost

        while self.event_queue:
            event = self.event_queue.pop()
            event_type = event[0]

            if event_type == "pop_declined_set":
                self._reaction_declined_sets.pop()

            elif event_type == "execute_instructions":
                _, ability, source, aiming_result, roll_result = event
                ability.execute_instructions(
                    engine=self,
                    source=source,
                    aiming_result=aiming_result,
                    roll_result=roll_result,
                )

            elif event_type == "reaction_phase":
                _, ability, source, aiming_result, roll_result, phase, entity_idx = (
                    event
                )

                if entity_idx >= len(self.entities):
                    continue

                entity = self.entities[entity_idx]
                if entity.hp <= 0:
                    self.event_queue.append(
                        (
                            "reaction_phase",
                            ability,
                            source,
                            aiming_result,
                            roll_result,
                            phase,
                            entity_idx + 1,
                        )
                    )
                    continue

                reaction_key = (
                    entity.id,
                    phase,
                    ability.get_hash(),
                    hash(roll_result),
                )
                if (
                    self._reaction_declined_sets
                    and reaction_key in self._reaction_declined_sets[-1]
                ):
                    self.event_queue.append(
                        (
                            "reaction_phase",
                            ability,
                            source,
                            aiming_result,
                            roll_result,
                            phase,
                            entity_idx + 1,
                        )
                    )
                    continue

                entity_reactions = []
                for react_ability in entity.abilities:
                    if (
                        react_ability.action_cost == ActionCost.INSTANT
                        and react_ability.is_available()
                    ):
                        is_after = False
                        if react_ability.instant_speed > 0:
                            if (
                                roll_result.roll is not None
                                and roll_result.roll > react_ability.instant_speed
                            ):
                                is_after = True
                        reaction_phase = "after" if is_after else "before"

                        if reaction_phase == phase:
                            plausible_uses = _get_plausible_uses_of_ability_at_pos(
                                actor=entity,
                                engine=self,
                                pos=entity.pos,
                                ability=react_ability,
                                choice_class=PlausibleFreeAction,
                            )
                            entity_reactions.extend(plausible_uses.values())

                if entity_reactions:
                    pass_choice = Choice(features={"pass_reaction": 1})
                    choices = tuple(entity_reactions + [pass_choice])

                    self.current_reaction_choices = choices
                    self.current_reaction_team = entity.team
                    self.current_reaction_entity = entity
                    self.current_reaction_key = reaction_key

                    self.event_queue.append(
                        (
                            "reaction_phase_wait",
                            ability,
                            source,
                            aiming_result,
                            roll_result,
                            phase,
                            entity_idx,
                        )
                    )
                    return True
                else:
                    self.event_queue.append(
                        (
                            "reaction_phase",
                            ability,
                            source,
                            aiming_result,
                            roll_result,
                            phase,
                            entity_idx + 1,
                        )
                    )

        return False

    def copy(self) -> "Engine":
        return copy.deepcopy(self)

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result

        # --- Set up new engine instance
        # Shared/immutable objects
        result.setup = self.setup
        result.agents = self.agents
        result.grid = self.grid
        if result.grid:
            result.grid.engine = result

        # Copy simple state
        result.initial_seed = self.initial_seed
        result.action_history = list(self.action_history)
        result.rng = copy.deepcopy(self.rng, memo)  # rng has its own state
        result.round_num = self.round_num
        result.num_hero_rows = self.num_hero_rows
        result.current_team = self.current_team
        result.current_hero_row_index = self.current_hero_row_index
        result.activation_index = self.activation_index
        result.is_resolving_action = getattr(self, "is_resolving_action", False)
        result._next_id = self._next_id

        # --- Deep copy object graph. This is order-dependent.
        # This will call __deepcopy__ on each entity and modifier, populating the memo.
        result.entities = copy.deepcopy(self.entities, memo)
        result.markers = copy.deepcopy(self.markers, memo)

        # Now that all entities are in memo, we can copy lists that reference them.
        result.team_heroes = copy.deepcopy(self.team_heroes, memo)
        result.current_turn_hero = copy.deepcopy(self.current_turn_hero, memo)
        result.active_entity = copy.deepcopy(self.active_entity, memo)
        result.activation_queue = copy.deepcopy(self.activation_queue, memo)
        result._reaction_declined_sets = copy.deepcopy(
            self._reaction_declined_sets, memo
        )
        result.current_choices = copy.deepcopy(self.current_choices, memo)
        result.event_queue = copy.deepcopy(self.event_queue, memo)
        result.current_reaction_choices = copy.deepcopy(
            self.current_reaction_choices, memo
        )
        result.current_reaction_team = self.current_reaction_team
        result.current_reaction_entity = copy.deepcopy(
            self.current_reaction_entity, memo
        )
        result.current_reaction_key = copy.deepcopy(self.current_reaction_key, memo)
        if result.current_choices:
            assert hash(result.current_choices) == hash(self.current_choices)

        result.router = copy.deepcopy(self.router, memo)
        assert len(result.router.subscribers) == len(self.router.subscribers)
        # todo still missing pending events..?
        return result

    def get_current_player(self) -> int:
        if self.current_reaction_team is not None:
            return self.current_reaction_team
        if self.active_entity:
            return self.active_entity.team
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
            choices,
            UniqueTuple(entity_states),
            marker_states,
            # tuple(frozenset(s) for s in self._reaction_declined_sets),
        )

    def hash(self) -> int:
        return hash(self._get_hash_info())
