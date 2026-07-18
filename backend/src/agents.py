"""
Agents — AI decision-makers for the game engine.

Extracted from engine.py to keep modules under 400 lines.
Contains the abstract Agent base class and built-in implementations.
"""

import abc
import random
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine import Engine


class Agent(abc.ABC):
    def __deepcopy__(self, memo):
        return self

    @abc.abstractmethod
    def choose(self, env: "Engine") -> int:
        pass


class RandomAgent(Agent):
    def choose(self, env: Optional["Engine"]) -> int:
        return random.randint(0, len(env.current_choices) - 1)


class RuleBasedAgent(Agent):
    def choose(self, env: "Engine") -> int:
        choices = env.current_choices
        if not choices:
            return 0

        max_priority = max(c.priority for c in choices)
        best_choices = [i for i, c in enumerate(choices) if c.priority == max_priority]

        actor = env.get_current_actor()
        if actor:
            def get_distance(choice_idx: int) -> int:
                choice = choices[choice_idx]
                pos = getattr(choice, "move_pos", actor.pos)
                return pos.get_distance(actor.pos) if pos else 0

            min_dist = min(get_distance(i) for i in best_choices)
            best_choices = [i for i in best_choices if get_distance(i) == min_dist]

        return env.rng.choice(best_choices)
