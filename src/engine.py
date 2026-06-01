import abc
import random
import copy
from dataclasses import dataclass, field
from typing import (
    List,
    Optional,
    Dict,
    TypeVar,
)

from choices import get_plausible_move_and_actions, Choice, PlausibleMoveAndAction
from entities import Entity, Summon, Marker
from events import (
    TurnStartEvent,
    TurnEndEvent,
    EventPhase,
    query,
    before,
    Router,
    Query,
    ChangeLocationEvent,
)
from grid import Grid
from point import Point
from queries import (
    QueryIsAlive,
    QueryHasArmor,
    QueryLegalActions,
    QueryCanMove,
    QuerySpeed,
)
from schemas import EngineState, GameLog, LogEntry, ActionState

ChoiceT = TypeVar("ChoiceT", bound="Choice")


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
        self.current_team: int = 1
        self.grid: Grid = grid
        self.active_entity: Optional["Entity"] = None
        self._next_id: int = 1
        self._entity_by_pos: Dict[Point, "Entity"] = {}
        self._markers_by_pos: Dict[Point, List["Marker"]] = {}

    def get_choice(self, team: int, choices: List[ChoiceT]) -> ChoiceT:
        if not choices:
            raise ValueError("Cannot request a choice from an empty list.")
        if len(choices) == 1:
            return choices[0]
        index = self.agents[team].choose(choices)
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
        self.next_turn()
        before_state = self.to_model()

        while self.round_num <= 6:
            if self.active_entity.hp <= 0:
                self.next_turn()  # todo doesn't work with summons
                continue

            agent = self.agents[self.active_entity.team]
            feature_evaluator = getattr(agent, "feature_evaluator", None)
            plausible_actions: List[PlausibleMoveAndAction] = (
                get_plausible_move_and_actions(
                    actor=self.active_entity,
                    engine=self,
                    feature_evaluator=feature_evaluator,
                )
            )
            chosen_action: PlausibleMoveAndAction = self.get_choice(
                team=self.active_entity.team, choices=plausible_actions
            )
            self.step(actor=self.active_entity, action=chosen_action)

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
                actor=self.active_entity.id,
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
            before_state = after_state

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
