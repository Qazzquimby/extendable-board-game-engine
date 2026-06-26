class UniqueTuple(tuple):
    def __new__(cls, iterable=None):
        if not iterable:
            iterable = []
        return super().__new__(cls, dict.fromkeys(iterable))


class HashByValue:
    _hash_exclude = {"engine"}

    def _hashable(self, obj):
        if isinstance(obj, dict):
            return tuple(
                sorted(
                    (k, self._hashable(v))
                    for k, v in obj.items()
                    if k not in self._hash_exclude
                )
            )
        elif isinstance(obj, list):
            return tuple(self._hashable(x) for x in obj)
        elif isinstance(obj, set):
            return frozenset(self._hashable(x) for x in obj)
        elif isinstance(obj, tuple):
            return tuple(self._hashable(x) for x in obj)
        elif hasattr(obj, "__dict__"):
            return (
                type(obj),
                self._hashable(obj.__dict__),
            )
        else:
            return obj

    def __hash__(self):
        return hash(self._hashable(self.__dict__))

    def __eq__(self, other):
        return type(self) is type(other) and self._hashable(
            self.__dict__
        ) == self._hashable(other.__dict__)
