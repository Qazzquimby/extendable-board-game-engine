class UniqueTuple(tuple):
    def __new__(cls, iterable=None):
        if not iterable:
            iterable = []
        return super().__new__(cls, dict.fromkeys(iterable))
