from typing import NamedTuple


class Point(NamedTuple):
    x: int
    y: int

    def get_distance(self, other: "Point") -> int:
        delta = self - other
        return abs(delta.x) + abs(delta.y)

    def __str__(self):
        return f"({self.x},{self.y})"

    def __add__(self, other: "Point") -> "Point":
        return Point(x=self.x + other.x, y=self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        return Point(x=self.x - other.x, y=self.y - other.y)
