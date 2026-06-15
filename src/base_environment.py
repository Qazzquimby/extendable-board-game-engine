import abc
from collections import OrderedDict
from dataclasses import dataclass
from functools import wraps
from typing import Dict, List, Optional, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    pass

ActionType = TypeVar("ActionType")
StateType = "Engine"


class LRUCache(OrderedDict):
    """A simple LRU cache."""

    def __init__(self, max_size: int = 100_000, *args, **kwargs):
        self.max_size = max_size
        super().__init__(*args, **kwargs)

    def __getitem__(self, key):
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.max_size:
            self.popitem(last=False)


def _make_hashable_key(args, kwargs):
    key = []
    for arg in args:
        if isinstance(arg, dict):
            key.append(frozenset(arg.items()))
        else:
            key.append(arg)
    if kwargs:
        key.append(frozenset(kwargs.items()))
    return tuple(key)


def cached_method(func):
    func_name = func.__name__

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        cache_key = (func_name,) + _make_hashable_key(args, kwargs)

        # Check instance cache
        if cache_key in self._instance_cache:
            return self._instance_cache[cache_key]

        # Check global cache
        state_key = self.get_state_with_key().key
        if state_key in self._cache and cache_key in self._cache[state_key]:
            result = self._cache[state_key][cache_key]
            self._instance_cache[cache_key] = result
            return result

        # Compute result
        result = func(self, *args, **kwargs)

        # Store in caches
        self._instance_cache[cache_key] = result
        if state_key not in self._cache:
            self._cache[state_key] = {}
        self._cache[state_key][cache_key] = result

        return result

    return wrapper


@dataclass
class StateWithKey:
    state: StateType
    key: int

    @classmethod
    def from_state(cls, state: StateType):
        key = cls._get_key_for_state(state)
        return cls(state=state, key=key)

    @staticmethod
    def _get_key_for_state(state: StateType) -> int:
        return state.hash()


@dataclass
class SanityCheckState:
    """Holds data for a single sanity check case."""

    description: str
    state_with_key: StateWithKey
    expected_value: Optional[float] = None
    expected_action: Optional[ActionType] = None


@dataclass
class ActionResult:
    next_state_with_key: StateWithKey
    reward: float = 0.0  # The reward received by the player who just acted.
    done: bool = False


class BaseEnvironment(abc.ABC):
    """Abstract base class for game environments."""

    _cache = LRUCache(max_size=10_000)

    def __init__(self):
        self._dirty = True
        self._state_with_key: Optional[StateWithKey] = None
        self.state: Optional[StateType] = None
        self._instance_cache: dict = {}

    def reset(self) -> StateWithKey:
        """
        Reset the environment to its initial state.

        Returns:
            The initial state observation.
        """
        self._dirty = True
        self._instance_cache = {}
        state_with_key = self._reset()
        self.state = state_with_key.state
        return state_with_key

    @property
    def is_done(self) -> bool:
        return self.state.is_done()

    @abc.abstractmethod
    def _reset(self) -> StateWithKey:
        pass

    def step(self, action: ActionType) -> ActionResult:
        """
        Take a step in the environment using the given action.

        Args:
            action: The action taken by the current player.
        """
        reward, done = self._step(action)
        self._dirty = True
        self._instance_cache = {}

        result = ActionResult(
            next_state_with_key=self.get_state_with_key(), reward=reward, done=done
        )

        assert result.next_state_with_key.key == self.get_state_with_key().key
        return result

    @abc.abstractmethod
    def _step(self, action: ActionType):
        # -> reward, done
        pass

    def get_legal_actions(self) -> List[ActionType]:
        """
        Get a list of legal actions available in the current state.

        Returns:
            A list of valid actions.
        """
        return self._get_legal_actions()

    @abc.abstractmethod
    def _get_legal_actions(self) -> List[ActionType]:
        """
        Get a list of legal actions available in the current state.

        Returns:
            A list of valid actions.
        """
        pass

    @abc.abstractmethod
    def get_current_player(self) -> int:
        """
        Get the index of the player whose turn it is.

        Returns:
            The current player index (e.g., 0 or 1).
        """
        pass

    def get_state_with_key(self) -> StateWithKey:
        if self._dirty:
            self._state_with_key = StateWithKey.from_state(self._get_state())
            self._dirty = False
        return self._state_with_key

    @abc.abstractmethod
    def _get_state(self) -> StateType:
        pass

    @abc.abstractmethod
    def get_winning_player(self) -> Optional[int]:
        """
        Get the index of the winning player.

        Returns:
            The winner's index, or None if there is no winner (draw or game not over).
        """
        pass

    @property
    def num_players(self) -> int:
        """The number of players in the game."""
        if not self.state:
            raise RuntimeError("Environment state not initialized.")
        return len(self.state.agents)

    def get_reward_for_player(self, player=0) -> float:
        winner = self.get_winning_player()
        if winner is None:
            return 0.0  # Draw
        if winner == player:
            return 1.0
        else:
            return -1.0

    @abc.abstractmethod
    def copy(self) -> "BaseEnvironment":
        """
        Create a deep copy of the environment state.

        Returns:
            A new instance of the environment with the same state.
        """
        pass

    def set_state(self, state: StateType) -> None:
        self.state = state.copy()
        self._dirty = True
        self._instance_cache = {}

    def render(self, mode: str = "human") -> None:
        """
        Render the environment state (optional).

        Args:
            mode: The rendering mode (e.g., "human").
        """
        print("Rendering not implemented for this environment.")

    def close(self) -> None:
        """Clean up any resources (optional)."""
        pass

    def get_sanity_check_states(self) -> List[SanityCheckState]:
        """Returns a list of predefined states for sanity checking the environment."""
        return []

    @abc.abstractmethod
    def get_network_spec(self) -> Dict:
        """
        Returns a specification for the network architecture.
        This includes table schemas, feature cardinalities, and action space information.
        """
        pass
