from grid import Grid
from point import Point


def test_grid_pathfinding_open():
    grid = Grid()
    path = grid.get_path(Point(0, 0), Point(2, 2))
    assert path is not None
    assert len(path) == 5


def test_grid_pathfinding_with_walls():
    grid = Grid()
    grid.add_wall(Point(1, 0))
    grid.add_wall(Point(1, 1))

    path = grid.get_path(Point(0, 0), Point(2, 0))
    assert path is not None
    assert len(path) == 7


def test_grid_pathfinding_with_edge_walls():
    grid = Grid()
    grid.add_edge_wall(Point(0, 0), Point(1, 0))

    path = grid.get_path(Point(0, 0), Point(1, 0))
    assert path is not None
    assert len(path) == 4


def test_get_range():
    grid = Grid()
    assert grid.get_range(Point(0, 0), Point(0, 0)) == 0
    assert grid.get_range(Point(0, 0), Point(3, 0)) == 3
    assert grid.get_range(Point(0, 0), Point(0, 3)) == 3
    assert grid.get_range(Point(0, 0), Point(1, 1)) == 1
    assert grid.get_range(Point(0, 0), Point(2, 2)) == 3
    assert grid.get_range(Point(0, 0), Point(3, 1)) == 3


def test_push_pull_movement():
    grid = Grid()
    path = grid.get_pull_path(Point(3, 0), Point(1, 0), pull_to=Point(0, 0))
    assert path is not None
    assert len(path) == 3

    path = grid.get_push_path(Point(1, 0), Point(3, 0), push_from=Point(0, 0))
    assert path is not None
    assert len(path) == 3


def test_grid_pathfinding_blocked():
    grid = Grid()
    grid.add_wall(Point(1, 0))
    grid.add_wall(Point(0, 1))
    grid.add_wall(Point(-1, 0))
    grid.add_wall(Point(0, -1))

    path = grid.get_path(Point(0, 0), Point(2, 0))
    assert path is None


def test_line_of_sight_clear():
    grid = Grid()
    visible, covered = grid.get_line_of_sight(Point(0, 0), Point(3, 0))
    assert visible is True
    assert covered is False


def test_line_of_sight_blocked():
    grid = Grid()
    grid.add_wall(Point(1, 0))
    visible, covered = grid.get_line_of_sight(Point(0, 0), Point(2, 0))
    assert visible is False


def test_grid_visualize():
    grid = Grid(width=3, height=3)
    grid.add_wall(Point(1, 1))
    path = [Point(0, 0), Point(1, 0), Point(2, 0), Point(2, 1), Point(2, 2)]

    vis = grid.visualize(
        start=Point(0, 0), target=Point(2, 2), path=path, visible=True, covered=True
    )
    assert "<table" in vis
    assert "background-color: green" in vis
    assert "background-color: red" in vis
    assert "background-color: black" in vis
    assert "background-color: blue" in vis


def test_line_of_sight_covered():
    grid = Grid()
    grid.add_wall(Point(1, 1))
    visible, covered = grid.get_line_of_sight(Point(0, 0), Point(2, 0))
    assert visible is True
    grid = Grid()
    grid.add_wall(Point(2, 1))
    visible, covered = grid.get_line_of_sight(Point(0, 0), Point(2, 2))
    assert visible is True
    assert covered is True


def test_split_los_and_movement():
    grid = Grid()
    # Space 1,0 blocks movement but not LOS
    # Space 0,1 blocks LOS but not movement
    blocking_movement = {Point(1, 0)}
    blocking_los = {Point(0, 1)}
    
    points_in_range = grid.get_points_in_range(
        Point(0, 0), 2, blocking_los_points=blocking_los, blocking_movement_points=blocking_movement
    )
    
    # We can't step on (1,0), so to reach (2,0) takes 4 movement steps, which is out of max_range 2.
    assert Point(2, 0) not in points_in_range
    # We can step on (0,1) because it doesn't block movement, but LOS to (0,2) is blocked.
    assert Point(0, 2) not in points_in_range


def test_visualize_visibility():
    grid = Grid(width=5, height=5)
    grid.add_wall(Point(2, 2))

    vis = grid.visualize_visibility(start=Point(0, 0))
    assert "<table" in vis
    assert "background-color: green" in vis
    assert "background-color: black" in vis
    assert "background-color: lightblue" in vis
    assert "background-color: darkgray" in vis
    assert "Visibility Legend:" in vis
