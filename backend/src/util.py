class UniqueTuple(tuple):
    def __new__(cls, iterable=None):
        if isinstance(iterable, UniqueTuple):
            return iterable
        if not iterable:
            iterable = []
        return super().__new__(cls, dict.fromkeys(iterable))


DO_NOTHING = "Do Nothing"
EntityId = int
