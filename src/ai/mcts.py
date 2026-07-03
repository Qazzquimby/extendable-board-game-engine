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
from util import UniqueTuple
from valence import Valence

if TYPE_CHECKING:
    from entities import Entity

DEBUG = True

EARLY_STOP_IF_CHANGE_IMPOSSIBLE_CHECK_FREQUENCY = 100
NUM_SIMS = 100  # _000


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
        self.is_deterministic = False

        # populated when simulated. One if deterministic.
        self.child_nodes: set["MCTSNode"] = set()

    @property
    def value(self) -> float:
        if self.num_visits == 0:
            return 0.0
        return self.total_value / self.num_visits

    def __str__(self):
        return f"{self.num_visits} - {self.value}"


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
    ) -> None:
        """
        Expand a leaf node by adding children based on legal actions.

        Args:
            node: The leaf node to expand.
            env_at_node: The environment state corresponding to the leaf node.
                 Should not be modified by the expansion strategy itself.
        """
        pass


class EvaluationStrategy(abc.ABC):
    @abc.abstractmethod
    def evaluate(self, node: "MCTSNode", env: "Engine") -> float:
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
    ) -> None:
        if node.is_expanded or env_at_node.is_done:
            return

        assert not node.edges
        node.actions = env_at_node.current_choices
        for action_index, action in enumerate(env_at_node.current_choices):
            node.edges[action_index] = Edge(prior=1.0)
        node.is_expanded = True


class HeuristicEvaluation(EvaluationStrategy):
    """Evaluates a node by a health-based heuristic."""

    def __init__(self, heuristic_weight: float = 0.3):
        self.heuristic_weight = heuristic_weight

    def evaluate(self, node: MCTSNode, env: Engine) -> float:
        """Calculates a score based on remaining health, dead entities, and modifiers."""
        current_player = node.current_player_index

        if env.is_done:
            winner = env.get_winning_player()
            if winner is None:
                return 0.0
            return 1.0 if winner == current_player else -1.0

        team_hp = [0.0, 0.0]
        team_dead = [0, 0]
        team_mod_score = [0.0, 0.0]

        entities = (
            env.entities.values()
            if isinstance(getattr(env, "entities", None), dict)
            else getattr(env, "entities", env.living_entities)
        )

        for entity in entities:
            if entity.hp <= 0:
                team_dead[entity.team] += 1
            else:
                team_hp[entity.team] += entity.hp
                for mod in entity.modifiers:
                    if mod.valence == Valence.GOOD:
                        team_mod_score[entity.team] += 1.0
                    elif mod.valence == Valence.BAD:
                        team_mod_score[entity.team] -= 1.0

        my_team_hp = team_hp[current_player]
        other_team_hp = team_hp[1 - current_player]

        my_team_dead = team_dead[current_player]
        other_team_dead = team_dead[1 - current_player]

        my_team_mods = team_mod_score[current_player]
        other_team_mods = team_mod_score[1 - current_player]

        total_hp = my_team_hp + other_team_hp
        if total_hp == 0:
            return 0.0  # Should be covered by is_done, but for safety.

        health_advantage = (my_team_hp - other_team_hp) / total_hp
        dead_advantage = (other_team_dead - my_team_dead) * 0.5
        mod_advantage = (my_team_mods - other_team_mods) * 0.1

        score = health_advantage + dead_advantage + mod_advantage
        return max(-1.0, min(1.0, score * self.heuristic_weight))


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


past_root_nodes = []


class MCTSAgent(Agent):
    """An agent that uses MCTS to select actions."""

    def __init__(self, num_simulations: int = NUM_SIMS):
        self.num_simulations = num_simulations
        self.selection = PUCTSelection(exploration_constant=1.0)
        self.expansion = UniformExpansion()
        self.evaluation = HeuristicEvaluation()
        self.backprop = StandardBackpropagation()
        self.cache = MCTSNodeCache()

    def choose(self, env: Engine) -> int:
        choices = env.current_choices
        if len(choices) <= 1:
            return 0

        root_key = hash(env)

        if past_root_nodes:  # temp debug check
            prev_root = past_root_nodes[-1]
            new_history = env.action_history[len(prev_root.env.action_history) :]
            if new_history:
                chosen_action_idx = new_history[0]
                edge = prev_root.edges.get(chosen_action_idx)
                if edge and edge.child_nodes:
                    matching_child = next(iter(edge.child_nodes))

                    current_env_actions = env.current_choices
                    past_env_actions = matching_child.env.current_choices
                    a = (
                        hash(current_env_actions) == hash(past_env_actions),
                        current_env_actions,
                        past_env_actions,
                    )

                    if hash(current_env_actions) != hash(past_env_actions):
                        b = (
                            hash(env.get_legal_actions()),
                            hash(matching_child.env.get_legal_actions()),
                            hash(env.current_choices),
                            hash(matching_child.env.current_choices),
                        )
                        c = (
                            env.get_legal_actions(),
                            matching_child.env.get_legal_actions(),
                            env.current_choices,
                            matching_child.env.current_choices,
                        )
                        print()

                        debug_actions_env = env.get_legal_actions()
                        print()
                        debug_actions_child = matching_child.env.get_legal_actions()
                        print()

        root_node = self.cache.get_matching_node(root_key)
        if not root_node:
            root_node = MCTSNode(
                key=root_key,
                current_player_index=env.get_current_player(),
                env=env.copy(),
            )
            self.cache.cache_node(root_key, root_node)
        past_root_nodes.append(root_node)

        if not root_node.is_expanded:
            self.expansion.expand(node=root_node, env_at_node=env)

        contender_actions = set(root_node.edges.keys())

        log.enabled = False
        try:
            for i in range(self.num_simulations):
                self._run_simulation(
                    root_node=root_node, contender_actions=contender_actions
                )
                self.assert_all_choices_still_accurate()

                contender_actions = self._get_contender_actions(
                    i=i, root_node=root_node, contender_actions=contender_actions
                )
                if len(contender_actions) <= 1:
                    break
        finally:
            log.enabled = True

        best_idx = 0
        best_visits = -1
        for action_idx, edge in root_node.edges.items():
            if edge.num_visits > best_visits:
                best_visits = edge.num_visits
                best_idx = action_idx

        assert sum(len(edge.child_nodes) for edge in root_node.edges.values())
        assert 0 <= best_idx < len(choices)

        self.assert_all_choices_still_accurate()
        return best_idx

    def _run_simulation(
        self, root_node: MCTSNode, contender_actions: Optional[set] = None
    ) -> None:
        self.assert_all_choices_still_accurate()
        previous_node = root_node
        sim_env: "Engine" = root_node.env.copy()

        path = SearchPath()
        path.add_node(root_node)

        while not sim_env.is_done:
            self.assert_all_choices_still_accurate()
            action_idx = self.selection._select_action_index_from_edges(
                current_node=previous_node,
                start_node=root_node,
                contender_actions=contender_actions,
            )
            path.set_action_for_last_node(action_idx)

            edge = previous_node.edges[action_idx]
            self.assert_all_choices_still_accurate()
            if edge.is_deterministic and edge.child_nodes:
                node = next(iter(edge.child_nodes))
                sim_env = node.env.copy()
            else:
                sim_env.rng.stochastic_flag = False
                action = sim_env.current_choices[action_idx]
                sim_env.step(action=action, action_idx=action_idx)
                self.assert_all_choices_still_accurate()
                new_choices = sim_env.advance_until_choice()
                # After this line the assert fails
                self.assert_all_choices_still_accurate()
                sim_env.current_choices = new_choices  # .todo ..?
                self.assert_all_choices_still_accurate()

                key = hash(sim_env)
                node = self.cache.get_matching_node(key)
                if not node:
                    self.assert_all_choices_still_accurate()
                    node = MCTSNode(
                        key=key,
                        current_player_index=sim_env.get_current_player(),
                        env=sim_env.copy(),
                    )
                    self.assert_all_choices_still_accurate()
                    self.cache.cache_node(key, node)
                    self.assert_all_choices_still_accurate()

                is_deterministic = not sim_env.rng.stochastic_flag
                if is_deterministic:
                    edge.is_deterministic = True

                    duplicate_of = None
                    for other_idx, other_edge in list(previous_node.edges.items()):
                        if other_idx != action_idx and other_edge.is_deterministic:
                            if any(
                                child.key == node.key
                                for child in other_edge.child_nodes
                            ):
                                duplicate_of = other_idx
                                break

                    if duplicate_of is not None:
                        del previous_node.edges[action_idx]
                        path.steps[-1].action_taken = duplicate_of
                        if contender_actions is not None and previous_node is root_node:
                            contender_actions.discard(action_idx)
                    else:
                        edge.child_nodes.add(node)
                        assert len(edge.child_nodes) < 20
                else:
                    edge.child_nodes.add(node)
                    assert len(edge.child_nodes) < 20

            previous_node = node

            if path.has_visited_key(node.key):
                break
            self.assert_all_choices_still_accurate()
            path.add_node(node)

            if not node.is_expanded:
                self.expansion.expand(node, sim_env)
                val = self.evaluation.evaluate(node, sim_env)
                player_to_value = {
                    node.current_player_index: val,
                    1 - node.current_player_index: -val,
                }
                self.backprop.backpropagate(path, player_to_value)
                return
        self.assert_all_choices_still_accurate()
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

    def select_action(
        self, choices: List[Choice], engine: Optional[Engine] = None
    ) -> Choice:
        idx = self.choose(env=engine)
        return choices[idx]

    def _get_contender_actions(self, i, root_node, contender_actions):
        if (i + 1) % EARLY_STOP_IF_CHANGE_IMPOSSIBLE_CHECK_FREQUENCY == 0:
            remaining_sims = self.num_simulations - (i + 1)

            best_visits = -1
            for action_idx in contender_actions:
                visits = root_node.edges[action_idx].num_visits
                if visits > best_visits:
                    best_visits = visits

            contender_actions = {
                action_idx
                for action_idx in contender_actions
                if root_node.edges[action_idx].num_visits + remaining_sims
                >= best_visits
            }

        return contender_actions

    def assert_all_choices_still_accurate(self):
        mismatched = []
        for node in self.cache._key_to_node.values():
            if node.env is None:
                continue
            legal_actions = node.env.get_legal_actions()
            current_choices = node.env.current_choices
            if hash(legal_actions) != hash(current_choices):
                mismatched.append(
                    (
                        node.key,
                        hash(legal_actions),
                        hash(current_choices),
                        legal_actions,
                        current_choices,
                    )
                )
        if mismatched:
            assert False
