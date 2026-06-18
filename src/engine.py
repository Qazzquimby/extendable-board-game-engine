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
    TurnStartEvent,
    TurnEndEvent,
    EventPhase,
    query,
    Router,
    ChangeLocationEvent,
    RoundStartEvent,
    DeployEvent,
)
from grid import Grid
from logger import reset_logs, get_logs, log
from point import Point
from queries import QueryIsAlive, Query
from schemas import EngineState, GameLog, LogEntry, ActionState

ChoiceT = TypeVar("ChoiceT", bound="Choice")

NUM_TEAMS = 2
NUM_ROUNDS = 6


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
        self._entity_by_pos: Dict[Point, "Entity"] = {}
        self._markers_by_pos: Dict[Point, List["Marker"]] = {}

    @property
    def is_done(self):
        if self.round_num > NUM_ROUNDS:
            return True

        alive_teams = {e.team for e in self.living_entities}
        return len(alive_teams) <= 1

    def get_legal_actions(self) -> List[Choice]:
        entity = self.active_entity
        if self.is_done or not entity or entity.hp <= 0:
            return []
        agent = self.agents.get(entity.team)
        feature_evaluator = getattr(agent, "feature_evaluator", None) if agent else None
        moves = get_plausible_move_and_actions(entity, self, feature_evaluator)
        frees = get_plausible_free_actions(entity, self, feature_evaluator)
        return moves + frees

    def finalize_setup(self):
        self.team_heroes = [
            [e for e in self.entities if e.team == team and e.activator == e]
            for team in range(NUM_TEAMS)
        ]
        self.num_hero_rows = max([len(team) for team in self.team_heroes])
        for entity in self.entities:
            DeployEvent(entity).resolve()

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

        pbar = tqdm(total=NUM_ROUNDS * len(self.entities))
        self.next_turn()

        while not self.is_done:
            if self.is_done:
                break
            while self.active_entity is None:
                self.next_turn()  # todo unsure. Fragile.

            entity = self.active_entity
            pbar.update()
            if after_state:
                before_state = after_state
            else:
                before_state = self.to_model()

            if entity.hp <= 0:
                self.advance_to_next_activator()
                continue  # skip this turn, they're dead.

            chosen_action: PlausibleMoveAndAction = None
            turn_over = False
            while not turn_over:
                all_choices = self.get_legal_actions()
                if not all_choices:
                    self.advance_to_next_activator()
                    turn_over = True  # eg stunned
                    continue

                action_index = self.get_choice_index(
                    team=entity.team, choices=all_choices
                )
                action_choice = all_choices[action_index]

                self.step(
                    actor=entity,
                    action=action_choice,
                    action_idx=action_index,
                )

                if isinstance(action_choice, PlausibleMoveAndAction):
                    chosen_action = action_choice
                    turn_over = True
                    self.advance_to_next_activator()

            if not chosen_action:
                continue

            # Check win condition
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
                done=is_done,
                messages=get_logs(),
            )
            logs.append(log_entry)
            reset_logs()

            if is_done:
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
            actor = self.current_turn_hero

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

        if self.current_turn_hero is not None:
            TurnEndEvent(self.current_turn_hero).resolve()

        while not self.is_done:
            self._advance_hero_indices()
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
        while self.handle_reactions(
            triggering_ability=ability, roll_result=roll_result, phase="before"
        ):
            pass

        ability.execute_instructions(
            engine=self,
            source=source,
            aiming_result=aiming_result,
            roll_result=roll_result,
        )

        while self.handle_reactions(
            triggering_ability=ability, roll_result=roll_result, phase="after"
        ):
            pass

    def handle_reactions(
        self, triggering_ability, roll_result: "RollResult", phase
    ) -> bool:
        """
        Checks all entities for a single reaction and executes it if chosen.
        Returns True if a reaction occurred, False otherwise.
        """
        # todo consider just using event system to watch for ability use.

        # Check entities in a deterministic order.
        for entity in self.entities:
            if entity.hp <= 0:
                continue

            entity_reactions = []
            for ability in entity.abilities:
                if ability.action_cost == ActionCost.INSTANT and ability.is_available():
                    is_after = False
                    if ability.instant_speed > 0:
                        if (
                            roll_result.roll is not None
                            and roll_result.roll > ability.instant_speed
                        ):
                            is_after = True
                    reaction_phase = "after" if is_after else "before"

                    if reaction_phase == phase:
                        agent = self.agents.get(entity.team)
                        feature_evaluator = (
                            getattr(agent, "feature_evaluator", None) if agent else None
                        )
                        plausible_uses = _get_plausible_uses_of_ability_at_pos(
                            actor=entity,
                            engine=self,
                            pos=entity.pos,
                            ability=ability,
                            feature_evaluator=feature_evaluator,
                            choice_class=PlausibleFreeAction,
                        )
                        entity_reactions.extend(plausible_uses.values())

            if entity_reactions:
                # Agent can choose to not react
                pass_choice = Choice(features={"pass_reaction": 1})
                choices = entity_reactions + [pass_choice]

                choice_idx = self.get_choice_index(team=entity.team, choices=choices)
                chosen_action = choices[choice_idx]

                if chosen_action is pass_choice:
                    continue  # This entity passes, check next entity.

                # An action was chosen. Execute it. This will recurse into
                # resolve_ability_with_reactions, allowing for chained reactions.
                with log(f"Reaction from {entity.name}:"):
                    chosen_action.ability.execute(
                        engine=self,
                        source=entity,
                        aiming_result=chosen_action.aiming_result,
                    )

                # An action happened, so we need to re-evaluate reactions for everyone.
                return True
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
        result.router = Router()

        # Copy simple state
        result.initial_seed = self.initial_seed
        result.action_history = list(self.action_history)
        result.rng = copy.deepcopy(self.rng, memo)  # rng has its own state
        result.round_num = self.round_num
        result.num_hero_rows = self.num_hero_rows
        result.current_team = self.current_team
        result.current_hero_row_index = self.current_hero_row_index
        result.activation_index = self.activation_index
        result._next_id = self._next_id
        result._entity_by_pos = {}
        result._markers_by_pos = {}

        # --- Deep copy object graph. This is order-dependent.
        # This will call __deepcopy__ on each entity and modifier, populating the memo.
        result.entities = copy.deepcopy(self.entities, memo)
        result.markers = copy.deepcopy(self.markers, memo)

        # Now that all entities are in memo, we can copy lists that reference them.
        result.team_heroes = copy.deepcopy(self.team_heroes, memo)
        result.current_turn_hero = copy.deepcopy(self.current_turn_hero, memo)
        result.active_entity = copy.deepcopy(self.active_entity, memo)
        result.activation_queue = copy.deepcopy(self.activation_queue, memo)

        return result

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
        marker_states = frozenset((m.id, m.name, m.pos, m.team) for m in self.markers)
        return (
            self.round_num,
            self.current_hero_row_index,
            self.current_team,
            self.current_turn_hero.id if self.current_turn_hero else None,
            frozenset(entity_states),
            marker_states,
        )

    def hash(self) -> int:
        return hash(self._get_hash_info())
