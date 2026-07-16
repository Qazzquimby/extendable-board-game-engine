import math
from typing import Callable, List, Union

# todo integrate with dynamicint in the event system


def div(numerator: int, denominator: int) -> int:
    # Always rounds up
    return math.ceil(numerator / denominator)


class ModInt:
    def __init__(self, base: Union[int, "ModInt"], is_irreducible=False):
        self.base: int = base
        self._adds: List[Union[int, Callable[[], int]]] = []
        self._mults: List[Union[float, Callable[[], float]]] = []
        self._resistances: List[Union[bool, Callable[[], bool]]] = []
        self._caps: List[Union[int, Callable[[int], int]]] = []
        self.is_irreducible: bool = is_irreducible

        if isinstance(base, ModInt):
            self.base = base.base
            self._adds = base._adds
            self._mults = base._mults
            self._resistances = base._resistances
            self._caps = base._caps
            self.is_irreducible = base.is_irreducible

    def __int__(self):
        return self.value

    def __add__(self, other):
        return self.add(int(other))

    def __mul__(self, other):
        return self.mult(int(other))

    def add(self, val: Union[int, Callable[[], int]]) -> "ModInt":
        self._adds.append(val)
        return self

    def mult(self, val: Union[float, Callable[[], float]]) -> "ModInt":
        self._mults.append(val)
        return self

    def add_resistance(self, val: Union[bool, Callable[[], bool]] = True) -> "ModInt":
        self._resistances.append(val)
        return self

    def cap(self, val: Union[int, Callable[[int], int]]) -> "ModInt":
        self._caps.append(val)
        return self

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

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ModInt):
            return self.value == other.value
        elif isinstance(other, int):
            return self.value == other
        else:
            return NotImplemented

    def __gt__(self, other):
        if isinstance(other, ModInt):
            return self.value > other.value
        elif isinstance(other, int):
            return self.value > other
        else:
            return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, ModInt):
            return self.value < other.value
        elif isinstance(other, int):
            return self.value < other
        else:
            return NotImplemented
