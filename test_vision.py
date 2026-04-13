from vision import Grid

def test_grid_pathfinding_open():
    grid = Grid()
    path = grid.get_path((0, 0), (2, 2))
    assert path is not None
    assert len(path) == 5  # (0,0) -> (1,0) -> (2,0) -> (2,1) -> (2,2) or similar

def test_grid_pathfinding_with_walls():
    grid = Grid()
    grid.add_wall((1, 0))
    grid.add_wall((1, 1))
    
    path = grid.get_path((0, 0), (2, 0))
    assert path is not None
    # Must go around the wall: (0,0)->(0,1)->(0,2)->(1,2)->(2,2)->(2,1)->(2,0)
    assert len(path) == 7

def test_grid_pathfinding_with_edge_walls():
    grid = Grid()
    # Block direct path between (0,0) and (1,0)
    grid.add_edge_wall((0, 0), (1, 0))
    
    path = grid.get_path((0, 0), (1, 0))
    assert path is not None
    # Must go around the edge wall: (0,0)->(0,1)->(1,1)->(1,0)
    assert len(path) == 4

def test_grid_pathfinding_blocked():
    grid = Grid()
    grid.add_wall((1, 0))
    grid.add_wall((0, 1))
    grid.add_wall((-1, 0))
    grid.add_wall((0, -1))
    
    path = grid.get_path((0, 0), (2, 0))
    assert path is None

def test_line_of_sight_clear():
    grid = Grid()
    visible, covered = grid.get_line_of_sight((0, 0), (3, 0))
    assert visible is True
    assert covered is False

def test_line_of_sight_blocked():
    grid = Grid()
    grid.add_wall((1, 0))
    visible, covered = grid.get_line_of_sight((0, 0), (2, 0))
    assert visible is False

def test_grid_visualize():
    grid = Grid(width=3, height=3)
    grid.add_wall((1, 1))
    path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
    
    vis = grid.visualize(start=(0, 0), target=(2, 2), path=path, visible=True, covered=True)
    assert "<table" in vis
    assert "background-color: green" in vis
    assert "background-color: red" in vis
    assert "background-color: black" in vis
    assert "background-color: blue" in vis

def test_line_of_sight_covered():
    grid = Grid()
    grid.add_wall((1, 1))
    # Looking past a wall that is adjacent to the target
    visible, covered = grid.get_line_of_sight((0, 0), (2, 0))
    assert visible is True
    # Depending on exact geometry, this might be grazing if the wall is adjacent to target
    # In this specific setup, (1,1) is not adjacent to (2,0). Let's use a wall at (2,1)
    grid = Grid()
    grid.add_wall((2, 1))
    visible, covered = grid.get_line_of_sight((0, 0), (2, 2))
    assert visible is True
    assert covered is True

def test_visualize_visibility():
    grid = Grid(width=5, height=5)
    grid.add_wall((2, 2))
    
    vis = grid.visualize_visibility(start=(0, 0))
    assert "<table" in vis
    assert "background-color: green" in vis
    assert "background-color: black" in vis
    assert "background-color: lightblue" in vis
    assert "background-color: darkgray" in vis
    assert "Visibility Legend:" in vis
