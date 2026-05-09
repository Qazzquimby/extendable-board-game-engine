import math
from typing import Callable, List, Union

# todo integrate with dynamicint in the event system


def div(numerator: int, denominator: int) -> int:
    # Always rounds up
    return math.ceil(numerator / denominator)


class ModValue:
    def __init__(self, base: int):
        self.base: int = base
        self._adds: List[Union[int, Callable[[], int]]] = []
        self._mults: List[Union[float, Callable[[], float]]] = []
        self._resistances: List[Union[bool, Callable[[], bool]]] = []
        self._caps: List[Union[int, Callable[[int], int]]] = []
        self.is_irreducible: bool = False

    def add(self, val: Union[int, Callable[[], int]]) -> None:
        self._adds.append(val)

    def mult(self, val: Union[float, Callable[[], float]]) -> None:
        self._mults.append(val)

    def add_resistance(self, val: Union[bool, Callable[[], bool]] = True) -> None:
        self._resistances.append(val)

    def cap(self, val: Union[int, Callable[[int], int]]) -> None:
        self._caps.append(val)

    @property
    def value(self) -> int:
        adds = [a() if callable(a) else a for a in self._adds]
        mults = [m() if callable(m) else m for m in self._mults]
        has_resistance = any(r() if callable(r) else r for r in self._resistances)

        if self.is_irreducible:
            adds = [a for a in adds if a > 0]
            has_resistance = False

        pos_mults = [m for m in mults if m > 1.0]

        if pos_mults and has_resistance:
            final_mult = 1.0
        elif pos_mults:
            final_mult = 1.0 + sum(m - 1.0 for m in pos_mults)
        elif has_resistance:
            final_mult = 0.5
        else:
            final_mult = 1.0

        value = float(self.base) * final_mult
        value += sum(adds)
        value = math.ceil(value)

        for cap in self._caps:
            value = cap(int(value)) if callable(cap) else min(value, float(cap))

        return int(value)
