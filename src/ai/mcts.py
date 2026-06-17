import math
import random
from typing import (
    List,
    Tuple,
    Optional,
    Dict,
    Iterator,
)
import abc
from dataclasses import dataclass

from choices import Choice, PlausibleMoveAndAction
from engine import Agent, Engine
from logger import log

DEBUG = True

EARLY_STOP_IF_CHANGE_IMPOSSIBLE_CHECK_FREQUENCY = 50
NUM_SIMS = 50  # 1_000


@dataclass
class PathStep:
    """A single step in the MCTS selection path."""

    node: "MCTSNode"
    # None iff first node
    action_taken_to_reach_this_node: Optional[Choice]


class SearchPath:
    """The path taken during one MCTS selection phase."""

    def __init__(self, initial_node: "MCTSNode"):
        self._steps: List[PathStep] = []
        self._visited_keys: set[int] = set()
        self.add(node=initial_node, action_leading_to_node=None)

    def add(self, node: "MCTSNode", action_leading_to_node: Optional[Choice]):
        self._visited_keys.add(node.key)
        self._steps.append(PathStep(node, action_leading_to_node))

    def has_visited_key(self, key: int) -> bool:
        return key in self._visited_keys

    def __iter__(self) -> Iterator[PathStep]:
        return reversed(self._steps)

    def __len__(self) -> int:
        return len(self._steps)

    @property
    def last_node(self) -> "MCTSNode":
        if not self._steps:
            raise IndexError("SearchPath is empty, cannot get last node.")
        return self._steps[-1].node

    def get_step_details(
        self, steps_from_end: int
    ) -> Tuple["MCTSNode", Optional[Choice], Optional["MCTSNode"]]:
        """
        Helper for backpropagation. Gets current node, action that led to it, and its parent.
        steps_from_end=0 is the leaf, index_from_end=1 is its parent, etc.
        Returns: (current_node, action_to_current, parent_node_of_current)
        Parent is None if current_node is root.
        Action is None if current_node is root.
        """
        actual_index = len(self._steps) - 1 - steps_from_end
        if actual_index < 0:
            raise IndexError("Index out of bounds for path steps.")

        current_step = self._steps[actual_index]
        current_node = current_step.node
        action_to_current = current_step.action_taken_to_reach_this_node

        parent_node = None
        if actual_index > 0:  # If not the root node
            parent_node = self._steps[actual_index - 1].node

        return current_node, action_to_current, parent_node


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

    @property
    def value(self) -> float:
        if self.num_visits == 0:
            return 0.0
        return self.total_value / self.num_visits


class DeterministicEdge(Edge):
    """Edge with only one child node"""

    def __init__(
        self,
        prior: float,
        num_visits: int = 0,
        total_value: float = 0.0,  # from perspective of player taking the action
    ):
        super().__init__(prior=prior, num_visits=num_visits, total_value=total_value)
        self.child_node_key: Optional[int] = None
        # todo how could a 1 child edge have no child..? Fix if wrong


class MCTSNode:
    def __init__(
        self,
        key: int,
        current_player_index: int,
    ):
        self.key = key
        self.player_idx = current_player_index
        self.edges: Dict[int, DeterministicEdge] = {}
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


@dataclass
class SelectionResult:
    """Holds the results of the MCTS selection phase."""

    path: SearchPath
    leaf_env: Engine
    # todo worried these may be large and waste memory. Not needed?

    @property
    def leaf_node(self):
        return self.path.last_node


class SelectionStrategy(abc.ABC):
    @abc.abstractmethod
    def select(
        self,
        node: "MCTSNode",
        remaining_sims: int,
        contender_actions: Optional[set],
    ) -> SelectionResult:
        pass


class ExpansionStrategy(abc.ABC):
    @abc.abstractmethod
    def expand(
        self,
        node: "MCTSNode",
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

    def _score_edge(
        self, edge: DeterministicEdge, parent_node_num_visits: int
    ) -> float:
        """Abstract method to calculate the score for a single edge."""
        raise NotImplementedError

    def select(
        self,
        node: MCTSNode,
        sim_env: Engine,
        cache: "MCTSNodeCache",
        remaining_sims: int,
        contender_actions: Optional[set],
    ) -> SelectionResult:
        """
        Generic traversal logic: Select child node with highest score until a leaf
        node is reached or a cycle is detected. Modifies sim_env.
        """
        path = SearchPath(initial_node=node)
        current_node: MCTSNode = node

        while not sim_env.is_done:
            if not current_node.is_expanded:
                return SelectionResult(path=path, leaf_env=sim_env)

            best_action_index = self._select_action_index_from_edges(
                current_node=current_node,
                start_node=node,
                contender_actions=contender_actions,
            )
            best_action = current_node.actions[best_action_index]

            sim_env.rng.stochastic_flag = False

            edge = current_node.edges[best_action_index]
            sim_env.step(best_action, action_idx=best_action_index)

            if not sim_env.rng.stochastic_flag and edge.child_node_key is not None:
                next_key = edge.child_node_key
                sim_env.next_turn()
                while sim_env.current_hero and sim_env.current_hero.hp <= 0:
                    if sim_env.is_done:
                        break
                    sim_env.next_turn()
            else:
                sim_env.next_turn()
                while sim_env.current_hero and sim_env.current_hero.hp <= 0:
                    if sim_env.is_done:
                        break
                    sim_env.next_turn()
                next_key = sim_env.hash()

                if not sim_env.rng.stochastic_flag:
                    edge.child_node_key = next_key

            if path.has_visited_key(next_key):
                # Cycle detected
                return SelectionResult(path=path, leaf_env=sim_env)

            next_node = cache.get_matching_node(key=next_key)
            if not next_node:
                next_node = MCTSNode(
                    key=next_key, current_player_index=sim_env.get_current_player()
                )
                cache.cache_node(key=next_key, node=next_node)

            path.add(
                node=next_node, action_leading_to_node=best_action_index
            )  # FIX TYPE
            current_node = next_node

        # Reached a terminal state
        return SelectionResult(path=path, leaf_env=sim_env)

    def _select_action_index_from_edges(
        self,
        current_node: MCTSNode,
        start_node: MCTSNode,
        contender_actions: Optional[set],
    ) -> int:
        """Helper to find the action index with the maximum score using the abstract _score_edge."""
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
            # Calls the specific _score_edge implemented in child classes (PUCT or UCB1)
            score = self._score_edge(edge=edge, parent_node_num_visits=parent_visits)
            if score > best_score:
                best_score = score
                best_action_index = action_index

        assert best_action_index is not None
        return best_action_index


class UCB1Selection(MCTSSelectionStrategyBase):
    """Selects nodes using the UCB1 algorithm."""

    def __init__(self, exploration_constant: float):
        if exploration_constant < 0:
            raise ValueError("Exploration constant cannot be negative.")
        self.exploration_constant = exploration_constant

    def _score_edge(
        self, edge: DeterministicEdge, parent_node_num_visits: int
    ) -> float:
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

    def _score_edge(
        self, edge: DeterministicEdge, parent_node_num_visits: int
    ) -> float:
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

    def expand(self, node: MCTSNode, env_at_node: Engine) -> None:
        if node.is_expanded or env_at_node.is_done:
            return
        # todo, pretty sure this will have to be reworked to allow for mid-turn choices
        legal_actions = env_at_node.get_legal_actions()
        assert not node.edges
        node.actions = legal_actions
        for action_index, action in enumerate(legal_actions):
            node.edges[action_index] = DeterministicEdge(prior=1.0)
        node.is_expanded = True


class RandomRolloutEvaluation(EvaluationStrategy):
    """Evaluates a node by performing a random rollout simulation."""

    def __init__(self, max_rollout_depth: int = 50, discount_factor: float = 1.0):
        self.max_rollout_depth = max_rollout_depth
        self.discount_factor = discount_factor  # Usually 1.0 for MCTS terminal rewards

    def evaluate(self, node: MCTSNode, env: Engine) -> float:
        """Simulate game from the given environment state using random policy."""
        player_at_start = env.get_current_player()

        if env.is_done:
            winner = env.get_winning_player()
            if winner is None:
                return 0.0
            return 1.0 if winner == player_at_start else -1.0

        current_step = 0

        while current_step < self.max_rollout_depth:
            if env.is_done:
                break

            legal_actions = env.get_legal_actions()  # can avoid recomputing these?
            if not legal_actions:
                break
            action_idx = random.randrange(len(legal_actions))
            action = legal_actions[action_idx]

            env.step(action, action_idx=action_idx)
            if type(action).__name__ == "PlausibleMoveAndAction":
                env.next_turn()
                while env.current_hero and env.current_hero.hp <= 0:
                    if env.is_done:
                        break
                    env.next_turn()

            current_step += 1

        if current_step >= self.max_rollout_depth:
            return 0.0

        winner = env.get_winning_player()
        value = 0.0
        if winner is not None:
            value = 1.0 if winner == player_at_start else -1.0

        value *= self.discount_factor**current_step

        return value


class StandardBackpropagation(BackpropagationStrategy):
    """Updates node statistics by backpropagating the evaluation value."""

    def backpropagate(
        self, path: SearchPath, player_to_value: Dict[int, float]
    ) -> None:
        for i in range(len(path)):
            node, action_to_node, parent_of_node = path.get_step_details(
                steps_from_end=i
            )

            node.num_visits += 1
            node.total_value += player_to_value.get(node.current_player_index, 0.0)

            if parent_of_node and action_to_node is not None:
                # not start of path
                action_key = (
                    tuple(action_to_node)
                    if isinstance(action_to_node, list)
                    else action_to_node
                )

                edge_to_update = parent_of_node.edges[action_key]
                edge_to_update.num_visits += 1

                value = player_to_value.get(parent_of_node.current_player_index)
                edge_to_update.total_value += value


class MCTSAgent(Agent):
    """An agent that uses MCTS to select actions."""

    def __init__(self, num_simulations: int = NUM_SIMS):
        self.num_simulations = num_simulations
        self.selection = PUCTSelection(exploration_constant=1.0)
        self.expansion = UniformExpansion()
        self.evaluation = RandomRolloutEvaluation(max_rollout_depth=20)
        self.backprop = StandardBackpropagation()
        self.cache = MCTSNodeCache()

    def choose(self, choices: List[Choice]) -> int:
        if len(choices) <= 1:
            return 0

        first_choice: PlausibleMoveAndAction = choices[0]
        actor = first_choice.ability.owner
        env = actor.engine

        root_key = env.hash()
        root_node = self.cache.get_matching_node(root_key)
        if not root_node:
            root_node = MCTSNode(
                key=root_key, current_player_index=env.get_current_player()
            )
            self.cache.cache_node(root_key, root_node)

        history_to_replay = list(env.action_history)

        # Precompute actions to replay to avoid expensive get_legal_actions() calls
        actions_to_replay = []
        log.enabled = False
        try:
            # Get actions to replay
            replay_env = env.setup.create_engine(
                agents=env.agents, seed=env.initial_seed
            )
            replay_env.rng.stochastic_flag = False
            for action_idx in history_to_replay:
                if action_idx == -1:
                    replay_env.next_turn()
                    actions_to_replay.append(None)
                elif action_idx >= 0:
                    legal = replay_env.get_legal_actions()
                    action = legal[action_idx]
                    replay_env.step(action, action_idx=action_idx)
                    actions_to_replay.append(action)

            # sims
            for _ in range(self.num_simulations):
                sim_env = env.setup.create_engine(
                    agents=env.agents, seed=env.initial_seed
                )
                sim_env.rng.stochastic_flag = False

                for action_idx, action in zip(history_to_replay, actions_to_replay):
                    if action_idx == -1:
                        sim_env.next_turn()
                    elif action_idx >= 0:
                        sim_env.step(action, action_idx=action_idx)

                result = self.selection.select(
                    root_node, sim_env, self.cache, self.num_simulations, None
                )

                if not result.leaf_env.is_done:
                    self.expansion.expand(result.leaf_node, result.leaf_env)
                    val = self.evaluation.evaluate(result.leaf_node, result.leaf_env)
                else:
                    winner = result.leaf_env.get_winning_player()
                    curr_player = result.leaf_node.current_player_index
                    if winner is None:
                        val = 0.0
                    else:
                        val = 1.0 if winner == curr_player else -1.0

                player_to_value = {
                    result.leaf_node.current_player_index: val,
                    1 - result.leaf_node.current_player_index: -val,
                }
                self.backprop.backpropagate(result.path, player_to_value)
        finally:
            log.enabled = True

        best_idx = 0
        best_visits = -1
        for action_idx, edge in root_node.edges.items():
            if edge.num_visits > best_visits:
                best_visits = edge.num_visits
                best_idx = action_idx

        # In case the best index tracked by MCTS logic isn't aligned with choices bounds
        if best_idx >= len(choices):
            best_idx = 0

        return best_idx

    def select_action(self, choices: List[Choice]) -> Choice:
        idx = self.choose(choices)
        return choices[idx]
