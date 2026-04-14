from targeting import get_burst, get_line


def test_get_burst():
    burst = get_burst((0, 0), 1)
    assert len(burst) == 9
    assert (0, 0) in burst
    assert (1, 1) in burst
    assert (-1, -1) in burst
    assert (0, 2) not in burst

    burst_radius_2 = get_burst((5, 5), 2)
    assert len(burst_radius_2) == 25


def test_get_line_orthogonal():
    line = get_line((0, 0), (1, 0), 3)
    assert line == [(1, 0), (2, 0), (3, 0)]


def test_get_line_diagonal():
    line = get_line((0, 0), (1, 1), 3)
    assert line == [(1, 1), (2, 2), (3, 3)]


def test_get_line_arbitrary_angle():
    # Target is at knight's move distance
    line = get_line((0, 0), (2, 1), 4)
    # step_x = 2/2 = 1, step_y = 1/2 = 0.5
    # i=1: (1, 0.5)->(1, 0) or (1, 1) depending on round. round(0.5) is 0 in python 3 for even, but let's check exact math:
    # i=1: x=1, y=0
    # i=2: x=2, y=1
    # i=3: x=3, y=2
    # i=4: x=4, y=2
    assert len(line) == 4
    assert line[1] == (2, 1)  # The target itself should be the second point


def test_get_line_same_point():
    assert get_line((0, 0), (0, 0), 5) == []
