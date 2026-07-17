"""Tests for the Grid module — pathfinding, range, LOS, and movement."""

from dataclasses import dataclass

from src.grid import Grid, Direction
from src.point import Point


@dataclass
class MockEntity:
    """Minimal entity stub for push/pull tests."""
    pos: Point


# ── Grid initialization ──

def test_grid_init_dimensions():
    """Grid(5, 5) creates a 5x5 grid."""
    g = Grid(5, 5)
    assert g.width == 5
    assert g.height == 5


def test_grid_default_size():
    """Grid() defaults to 10x10."""
    g = Grid()
    assert g.width == 10
    assert g.height == 10


# ── Wall blocking ──

def test_is_movement_blocked_by_wall():
    """A wall blocks movement through its cell."""
    g = Grid()
    g.add_wall(Point(1, 0))
    assert g.is_movement_blocked(Point(0, 0), Point(1, 0))


def test_is_movement_blocked_by_edge_wall():
    """An edge wall blocks movement between two adjacent cells."""
    g = Grid()
    g.add_edge_wall(Point(0, 0), Point(1, 0))
    assert g.is_movement_blocked(Point(0, 0), Point(1, 0))


def test_open_space_not_blocked():
    """Empty cells have no movement blocking."""
    g = Grid()
    assert not g.is_movement_blocked(Point(0, 0), Point(0, 1))


# ── Range ──

def test_get_range_same_point():
    """Range from a point to itself is 0."""
    g = Grid()
    assert g.get_range(Point(0, 0), Point(0, 0)) == 0


def test_get_range_orthogonal():
    """Range along a straight line equals the distance."""
    g = Grid()
    assert g.get_range(Point(0, 0), Point(3, 0)) == 3
    assert g.get_range(Point(0, 0), Point(0, 3)) == 3


def test_get_range_diagonal_first():
    """First diagonal step counts as 1, subsequent are orthogonal."""
    g = Grid()
    assert g.get_range(Point(0, 0), Point(1, 1)) == 1  # single diagonal
    assert g.get_range(Point(0, 0), Point(2, 2)) == 3  # diag + ortho + ortho
    assert g.get_range(Point(0, 0), Point(3, 1)) == 3  # diag + ortho + ortho


def test_get_range_different_start():
    """Range calculation works from any start point."""
    g = Grid()
    assert g.get_range(Point(2, 2), Point(4, 4)) == 3


# ── Line of Sight ──

def test_los_clear_horizontal():
    """Clear horizontal line has LOS and no cover."""
    g = Grid()
    visible, cover = g.get_line_of_sight(Point(0, 0), Point(3, 0))
    assert visible is True
    assert cover is False


def test_los_clear_vertical():
    """Clear vertical line has LOS and no cover."""
    g = Grid()
    visible, cover = g.get_line_of_sight(Point(0, 0), Point(0, 3))
    assert visible is True
    assert cover is False


def test_los_blocked_by_wall():
    """A wall between start and target blocks LOS."""
    g = Grid()
    g.add_wall(Point(1, 0))
    visible, _ = g.get_line_of_sight(Point(0, 0), Point(2, 0))
    assert visible is False


def test_los_covered():
    """A wall adjacent to the target provides cover."""
    g = Grid()
    g.add_wall(Point(2, 1))
    visible, cover = g.get_line_of_sight(Point(0, 0), Point(2, 2))
    assert visible is True
    assert cover is True


def test_los_same_point():
    """LOS from a point to itself is visible with no cover."""
    g = Grid()
    visible, cover = g.get_line_of_sight(Point(1, 1), Point(1, 1))
    assert visible is True
    assert cover is False


# ── Push movement ──

def test_push_path_east():
    """Push EAST moves the subject in the +x direction."""
    g = Grid()
    entity = MockEntity(pos=Point(5, 5))
    path = g.get_push_path(entity, Direction.EAST, 3)
    assert path == [Point(6, 5), Point(7, 5), Point(8, 5)]


def test_push_path_north():
    """Push NORTH moves the subject in the -y direction."""
    g = Grid()
    entity = MockEntity(pos=Point(5, 5))
    path = g.get_push_path(entity, Direction.NORTH, 2)
    assert path == [Point(5, 4), Point(5, 3)]


def test_push_path_stops_at_wall():
    """Push stops when it hits a wall."""
    g = Grid()
    entity = MockEntity(pos=Point(5, 5))
    g.add_wall(Point(7, 5))
    path = g.get_push_path(entity, Direction.EAST, 5)
    assert path == [Point(6, 5)]


def test_push_path_stops_at_boundary():
    """Push stops at the grid boundary."""
    g = Grid(width=5, height=5)
    entity = MockEntity(pos=Point(3, 3))
    path = g.get_push_path(entity, Direction.EAST, 5)
    assert path == [Point(4, 3)]


# ── Pull movement ──

def test_pull_path_toward_point():
    """Pull moves the subject toward a target point."""
    g = Grid()
    entity = MockEntity(pos=Point(5, 5))
    path = g.get_pull_path(entity, Point(5, 2), 3)
    assert len(path) == 3
    assert path[-1] == Point(5, 2)


def test_pull_path_stops_at_wall():
    """Pull stops one step before a wall blocking the path."""
    g = Grid()
    entity = MockEntity(pos=Point(5, 5))
    g.add_wall(Point(5, 3))
    path = g.get_pull_path(entity, Point(5, 0), 5)
    assert path == [Point(5, 4)]


def test_pull_path_already_at_target():
    """Pull with subject already at target returns empty path."""
    g = Grid()
    entity = MockEntity(pos=Point(5, 2))
    path = g.get_pull_path(entity, Point(5, 2), 3)
    assert path == []


# ── get_points_in_range ──

def test_points_in_range_includes_self():
    """get_points_in_range includes the start point."""
    g = Grid()
    points = g.get_points_in_range(Point(1, 1), max_range=2)
    assert Point(1, 1) in points


def test_points_in_range_respects_max_range():
    """get_points_in_range excludes points beyond max_range."""
    g = Grid()
    points = g.get_points_in_range(Point(0, 0), max_range=2)
    assert Point(0, 3) not in points
    assert Point(3, 0) not in points


def test_points_in_range_blocked_by_los():
    """get_points_in_range blocks points that lack line of sight."""
    g = Grid()
    points = g.get_points_in_range(
        start=Point(0, 0),
        max_range=3,
        blocking_los_points={Point(0, 1)},
    )
    assert Point(0, 2) not in points


def test_points_in_range_empty_for_negative():
    """Negative max_range returns empty."""
    g = Grid()
    points = g.get_points_in_range(Point(0, 0), max_range=-1)
    assert len(points) == 0
