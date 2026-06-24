import math
from typing import (
    List,
    Optional,
    Dict,
    TYPE_CHECKING,
)
import abc
from dataclasses import dataclass

from choices import Choice, PlausibleMoveAndAction
from engine import Agent, Engine
from logger import log

if TYPE_CHECKING:
    from entities import Entity

DEBUG = True

EARLY_STOP_IF_CHANGE_IMPOSSIBLE_CHECK_FREQUENCY = 100
NUM_SIMS = 1000


@dataclass
class PathStep:
    """A single step in the MCTS selection path."""

    node: "MCTSNode"
    action_taken: Optional[int]  # action index, none iff first node


class SearchPath:
    """The path taken during one MCTS selection phase."""

    def __init__(self):
        self.steps: List[PathStep] = []
        self._visited_keys: set[int] = set()

    def add_node(self, node: "MCTSNode"):
        self.steps.append(PathStep(node=node, action_taken=None))
        self._visited_keys.add(node.key)

    def set_action_for_last_node(self, action_index: int):
        self.steps[-1].action_taken = action_index

    def has_visited_key(self, key: int) -> bool:
        return key in self._visited_keys

    @property
    def last_node(self) -> "MCTSNode":
        if not self.steps:
            raise IndexError("SearchPath is empty, cannot get last node.")
        return self.steps[-1].node


class Edge:
    """Represents an action from a state"""

    def __init__(
        self,
        prior: float,
        num_visits: int = 0,
        total_value: float = 0.0,
        # from perspective of player taking the action
    ):
        self.prior = prior
        self.num_visits = num_visits
        self.total_value = total_value

        # populated when simulated.One if deterministic.
        self.child_node_keys: set[int] = set()

    @property
    def value(self) -> float:
        if self.num_visits == 0:
            return 0.0
        return self.total_value / self.num_visits


class MCTSNode:
    def __init__(self, key: int, current_player_index: int, env=None):
        self.env = env
        self.key = key
        self.player_idx = current_player_index
        self.edges: Dict[int, Edge] = {}
        self.actions: List[Choice] = []
        self.is_expanded = False

        # for value estimate, not actually needed
        self.num_visits = 0
        self.total_value = 0.0

    @property
    def current_player_index(self):
        return self.player_idx


class MCTSNodeCache:
    def __init__(self):
        self._key_to_node: Dict[int, MCTSNode] = {}
        self.hits = 0
        self.misses = 0

    def get_matching_node(self, key: int) -> Optional[MCTSNode]:
        node = self._key_to_node.get(key, None)
        if node:
            self.hits += 1
        else:
            self.misses += 1
        return node

    def cache_node(self, key: int, node: MCTSNode):
        self._key_to_node[key] = node
        if len(self._key_to_node) > 2_000_000:
            self._key_to_node.clear()


class SelectionStrategy(abc.ABC):
    pass


class ExpansionStrategy(abc.ABC):
    @abc.abstractmethod
    def expand(
        self,
        node: "MCTSNode",
        env_at_node: Engine,
        pending_choices: Optional[List[Choice]] = None,
    ) -> None:
        """
        Expand a leaf node by adding children based on legal actions.

        Args:
            node: The leaf node to expand.
            env: The environment state corresponding to the leaf node.
                 Should not be modified by the expansion strategy itself.
        """
        pass


class EvaluationStrategy(abc.ABC):
    @abc.abstractmethod
    def evaluate(
        self,
        node: "MCTSNode",
    ) -> float:
        """
        Evaluate a leaf node to estimate its value.
        The value should be from the perspective of the player whose turn it is at the leaf node.

        Args:
            node: The leaf node to evaluate.
            env: The environment state corresponding to the leaf node.
                 Should not be modified by the evaluation strategy itself,
                 though internal copies might be made (e.g., for rollouts).

        Returns:
            The estimated value (float).
        """
        pass


class BackpropagationStrategy(abc.ABC):
    @abc.abstractmethod
    def backpropagate(
        self, path: SearchPath, player_to_value: Dict[int, float]
    ) -> None:
        pass


class MCTSSelectionStrategyBase(SelectionStrategy):
    """
    Abstract base class for MCTS selection strategies (UCB1, PUCT, etc.).
    Contains the generic MCTS traversal logic.
    """

    def _score_edge(self, edge: Edge, parent_node_num_visits: int) -> float:
        raise NotImplementedError

    def _select_action_index_from_edges(
        self,
        current_node: MCTSNode,
        start_node: MCTSNode,
        contender_actions: Optional[set],
    ) -> int:
        edges_to_consider = current_node.edges
        if current_node is start_node and contender_actions is not None:
            edges_to_consider = {
                action: edge
                for action, edge in current_node.edges.items()
                if action in contender_actions
            }

        best_score = -float("inf")
        best_action_index: Optional[int] = None

        # Use 1 if num_visits is 0 to avoid issues with log(0) in some UCB formulas if not handled by an IF statement
        parent_visits = current_node.num_visits if current_node.num_visits > 0 else 1

        for action_index, edge in edges_to_consider.items():
            score = self._score_edge(edge=edge, parent_node_num_visits=parent_visits)
            if score > best_score:
                best_score = score
                best_action_index = action_index

        assert (
            best_action_index is not None
        ), "Crash: No valid action index found during selection."
        return best_action_index


class UCB1Selection(MCTSSelectionStrategyBase):
    """Selects nodes using the UCB1 algorithm."""

    def __init__(self, exploration_constant: float):
        if exploration_constant < 0:
            raise ValueError("Exploration constant cannot be negative.")
        self.exploration_constant = exploration_constant

    def _score_edge(self, edge: Edge, parent_node_num_visits: int) -> float:
        """Calculates the UCB1 score for a child node."""

        # UCB Score = Avg_Reward + C * sqrt(log(N(parent)) / N(child))

        if edge.num_visits == 0:
            # Must return infinity to force selection of unvisited nodes first
            return float("inf")

        # The original UCB1 implementation typically does not use priors (edge.prior)
        # and assumes edge.value is the running average reward for that edge.
        exploitation_term = edge.value  # Assuming edge.value is already parent-relative

        exploration_term = self.exploration_constant * math.sqrt(
            math.log(parent_node_num_visits) / edge.num_visits
        )
        return exploitation_term + exploration_term


class PUCTSelection(MCTSSelectionStrategyBase):
    """Selects nodes using the AlphaZero PUCT algorithm."""

    def __init__(self, exploration_constant: float = 1.0):
        if exploration_constant < 0:
            raise ValueError("Exploration constant cannot be negative.")
        self.exploration_constant = exploration_constant

    def _score_edge(self, edge: Edge, parent_node_num_visits: int) -> float:
        """Calculates the PUCT score for a child edge."""
        # It's the same as UCB1 except it doesn't force explore every option
        # and it avoids div0 on unexplored options.

        exploitation_term = edge.value

        # Exploration term: C * P(s, a) * sqrt(N(s)) / (1 + N(s, a))
        # parent_node_num_visits here is N(s)
        exploration_term = (
            self.exploration_constant
            * edge.prior
            * (math.sqrt(parent_node_num_visits) / (1 + edge.num_visits))
        )

        return exploitation_term + exploration_term


class UniformExpansion(ExpansionStrategy):
    """Expands a node by creating children for all legal actions with uniform priors."""

    def expand(
        self,
        node: MCTSNode,
        env_at_node: Engine,
        pending_choices: Optional[List[Choice]] = None,
    ) -> None:
        if node.is_expanded or env_at_node.is_done:
            return

        if pending_choices is not None:
            legal_actions = pending_choices
        else:
            legal_actions = env_at_node.get_legal_actions()

        assert not node.edges
        node.actions = legal_actions
        for action_index, action in enumerate(legal_actions):
            node.edges[action_index] = Edge(prior=1.0)
        node.is_expanded = True


class HeuristicEvaluation(EvaluationStrategy):
    """Evaluates a node by a health-based heuristic."""

    def __init__(self, heuristic_weight: float = 0.1):
        self.heuristic_weight = heuristic_weight

    def evaluate(self, node: MCTSNode, env: Engine) -> float:
        """Calculates a score based on remaining health of both teams."""
        current_player = node.current_player_index

        if env.is_done:
            winner = env.get_winning_player()
            if winner is None:
                return 0.0
            return 1.0 if winner == current_player else -1.0

        team_hp = [0.0, 0.0]
        for entity in env.living_entities:
            team_hp[entity.team] += entity.hp

        my_team_hp = team_hp[current_player]
        other_team_hp = team_hp[1 - current_player]

        total_hp = my_team_hp + other_team_hp
        if total_hp == 0:
            return 0.0  # Should be covered by is_done, but for safety.

        health_advantage = (my_team_hp - other_team_hp) / total_hp
        return health_advantage * self.heuristic_weight


class StandardBackpropagation(BackpropagationStrategy):
    """Updates node statistics by backpropagating the evaluation value."""

    def backpropagate(
        self, path: SearchPath, player_to_value: Dict[int, float]
    ) -> None:
        for step in path.steps:
            node = step.node
            node.num_visits += 1
            node.total_value += player_to_value.get(node.current_player_index, 0.0)

            if step.action_taken is not None:
                edge_to_update = node.edges[step.action_taken]
                edge_to_update.num_visits += 1
                edge_to_update.total_value += player_to_value.get(
                    node.current_player_index, 0.0
                )


class SimulationComplete(Exception):
    pass


class TreeSearchAgent(Agent):
    def __init__(
        self,
        mcts: "MCTSAgent",
        sim_env: Engine,
        path: "SearchPath",
        team: int,
        root_node: Optional[MCTSNode] = None,
    ):
        self.mcts = mcts
        self.sim_env = sim_env
        self.path = path
        self.team = team
        self.root_node = root_node

    def choose(self, choices: List[Choice], engine: Optional[Engine] = None) -> int:
        if len(choices) <= 1:
            return 0

        key = self.sim_env.hash()

        if not self.path.steps and self.root_node is not None:
            node = self.root_node
            key = node.key
        else:
            node = self.mcts.cache.get_matching_node(key)
            if not node:
                node = MCTSNode(key=key, current_player_index=self.team, env=engine)
                self.mcts.cache.cache_node(key, node)

        if node.is_expanded:
            assert len(node.actions) == len(choices)

        if self.path.steps:
            last_step = self.path.steps[-1]
            if last_step.action_taken is not None:
                last_node = last_step.node
                edge = last_node.edges[last_step.action_taken]
                edge.child_node_keys.add(key)

        if self.path.has_visited_key(key):
            # Cycle detected, abort simulation
            player_to_value = {0: 0.0, 1: 0.0}
            self.mcts.backprop.backpropagate(self.path, player_to_value)
            raise SimulationComplete()

        self.path.add_node(node)

        if not node.is_expanded:
            self.mcts.expansion.expand(node, self.sim_env, pending_choices=choices)
            val = self.mcts.evaluation.evaluate(node, self.sim_env)

            player_to_value = {
                node.current_player_index: val,
                1 - node.current_player_index: -val,
            }
            self.mcts.backprop.backpropagate(self.path, player_to_value)
            raise SimulationComplete()

        best_action_index = self.mcts.selection._select_action_index_from_edges(
            current_node=node, start_node=None, contender_actions=None
        )
        assert len(choices) == len(node.actions) == len(node.env.current_choices)
        assert len(node.edges) <= len(choices)
        self.path.set_action_for_last_node(best_action_index)
        return best_action_index


class MCTSAgent(Agent):
    """An agent that uses MCTS to select actions."""

    def __init__(self, num_simulations: int = NUM_SIMS):
        self.num_simulations = num_simulations
        self.selection = PUCTSelection(exploration_constant=1.0)
        self.expansion = UniformExpansion()
        self.evaluation = HeuristicEvaluation()
        self.backprop = StandardBackpropagation()
        self.cache = MCTSNodeCache()

    def _run_simulation(self, env: Engine, root_node: MCTSNode) -> None:
        sim_env = env.copy()
        sim_env.rng.stochastic_flag = False

        path = SearchPath()
        agent0 = TreeSearchAgent(self, sim_env, path, team=0, root_node=root_node)
        agent1 = TreeSearchAgent(self, sim_env, path, team=1, root_node=root_node)
        sim_env.agents = {0: agent0, 1: agent1}

        try:
            while not sim_env.is_done:
                while sim_env.active_entity is None:  # todo 'get_active_entity'
                    sim_env.next_turn()
                    if sim_env.is_done:
                        break
                if sim_env.is_done:
                    break

                entity: "Entity" = sim_env.active_entity
                if entity.hp <= 0:
                    sim_env.advance_to_next_activator()
                    continue

                all_choices = sim_env.get_legal_actions()
                if not all_choices:
                    sim_env.advance_to_next_activator()
                    continue

                action_index = sim_env.get_choice_index(
                    team=entity.team, choices=all_choices
                )
                action_choice = all_choices[action_index]

                sim_env.step(
                    actor=entity,
                    action=action_choice,
                    action_idx=action_index,
                )

                if isinstance(action_choice, PlausibleMoveAndAction):
                    sim_env.advance_to_next_activator()

            # If we reach here, the game finished without hitting an unexpanded node
            if path.steps:
                winner = sim_env.get_winning_player()
                curr_player = path.last_node.current_player_index
                if winner is None:
                    val = 0.0
                else:
                    val = 1.0 if winner == curr_player else -1.0

                player_to_value = {
                    curr_player: val,
                    1 - curr_player: -val,
                }
                self.backprop.backpropagate(path, player_to_value)
        except SimulationComplete:
            pass

    def choose(self, choices: List[Choice], engine: Optional[Engine] = None) -> int:
        if len(choices) <= 1:
            return 0

        env = engine
        if env is None:
            raise ValueError("MCTSAgent requires the engine to be passed to choose()")

        root_key = env.hash()
        root_node = self.cache.get_matching_node(root_key)
        if not root_node:
            root_node = MCTSNode(
                key=root_key, current_player_index=env.get_current_player()
            )
            self.cache.cache_node(root_key, root_node)

        # Fix: Expand the root node immediately with the exact choices provided by the engine.
        # This prevents mid-turn reactive abilities from being overwritten by standard legal actions.
        if not root_node.is_expanded:
            self.expansion.expand(
                node=root_node, env_at_node=env, pending_choices=choices
            )

        if not env.is_resolving_action:
            log.enabled = False
            try:
                for _ in range(self.num_simulations):
                    self._run_simulation(env, root_node)
            finally:
                log.enabled = True

        # should actually equal sims but at least have some visits
        assert sum([e.num_visits for e in root_node.edges.values()])

        best_idx = 0
        best_visits = -1
        for action_idx, edge in root_node.edges.items():
            if edge.num_visits > best_visits:
                best_visits = edge.num_visits
                best_idx = action_idx

        assert 0 <= best_idx < len(choices), (
            f"Crash: MCTS selected an invalid index: {best_idx} for {len(choices)} choices. "
            "Action bounds are corrupted."
        )

        return best_idx

    def select_action(
        self, choices: List[Choice], engine: Optional[Engine] = None
    ) -> Choice:
        idx = self.choose(choices, engine=engine)
        return choices[idx]
