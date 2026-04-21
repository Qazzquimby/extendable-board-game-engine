from targeting import Burst, Square, get_line
from grid import Grid


def test_burst_area():
    grid = Grid(width=100, height=100)
    bursts = list(Burst(radius=1).get_selections(grid, (1, 1)))
    assert len(bursts) == 1
    burst = bursts[0]
    # first space of range can be diagnoal, making 3x3 square
    assert len(burst) == 9
    assert (1, 1) in burst
    assert (2, 2) in burst
    assert (0, 0) in burst
    assert (1, 3) not in burst

    bursts_radius_2 = list(Burst(radius=2).get_selections(grid, (50, 50)))
    assert len(bursts_radius_2) == 1
    assert (
        len(bursts_radius_2[0]) == 9 + 3 * 4
    )  # inner square of 9 +3 more on each side

    burst_radius_0 = list(Burst(radius=0).get_selections(grid, (10, 10)))[0]
    assert len(burst_radius_0) == 1


def test_burst_with_range():
    grid = Grid(width=10, height=10)
    # Burst 1 in range 2
    selections = list(Burst(radius=1, range_limit=2).get_selections(grid, (5, 5)))
    # Range 2 from (5,5) includes 13 points (1 center + 9 dist1 + 3*4 dist2)
    assert len(selections) == 21

    # Check that one of the selections is centered on (5, 7)
    expected_center = (5, 7)
    found = False
    for sel in selections:
        if expected_center in sel and (5, 8) in sel and (5, 6) in sel:
            found = True
            break
    assert found


def test_square_area():
    grid = Grid(width=10, height=10)
    # 2x2 square containing start (range_limit=0)
    selections = list(Square(side_length=2).get_selections(grid, (5, 5)))
    assert len(selections) == 4
    for sq in selections:
        assert len(sq) == 4
        assert (5, 5) in sq


def test_square_with_range():
    grid = Grid(width=100, height=100)
    # 2x2 square in range 3
    selections = list(Square(side_length=2, in_range=1).get_selections(grid, (50, 50)))
    # Range 1 is 3x3 square
    # Total of 2x2 squares that can be drawn overlapping any of them is (3+1*3+1)=16
    assert len(selections) == 16


def test_get_line_orthogonal():
    line = get_line(
        grid=Grid(width=100, height=100), start=(0, 0), target=(1, 0), length=3
    )
    assert line == [(1, 0), (2, 0), (3, 0)]


def test_get_line_diagonal():
    line = get_line(
        grid=Grid(width=100, height=100), start=(0, 0), target=(1, 1), length=3
    )
    assert line == [(1, 1), (2, 2), (3, 3)]


def test_get_line_arbitrary_angle():
    # Target is at knight's move distance
    line = get_line(
        grid=Grid(width=100, height=100), start=(0, 0), target=(2, 1), length=4
    )
    # step_x = 2/2 = 1, step_y = 1/2 = 0.5
    # i=1: (1, 0.5)->(1, 0) or (1, 1) depending on round. round(0.5) is 0 in python 3 for even, but let's check exact math:
    # i=1: x=1, y=0
    # i=2: x=2, y=1
    # i=3: x=3, y=2
    # i=4: x=4, y=2
    assert len(line) == 4
    assert line[1] == (2, 1)  # The target itself should be the second point
