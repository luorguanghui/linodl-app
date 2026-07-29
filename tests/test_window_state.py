import pytest

from linodl.desktop.window_state import WindowState, WindowStateStore


def test_window_state_clamps_invalid_saved_bounds(tmp_path):
    store = WindowStateStore(tmp_path / "window.json")
    store.save(
        WindowState(
            width=300,
            height=200,
            x=-99999,
            y=-99999,
            maximized=False,
        )
    )

    state = store.load()

    assert state.width >= 900
    assert state.height >= 640
    assert state.x is None
    assert state.y is None


@pytest.mark.parametrize("x", [10000, -10000])
def test_window_state_discards_far_offscreen_positions(tmp_path, x):
    store = WindowStateStore(tmp_path / "window.json")
    store.save(WindowState(width=1280, height=820, x=x, y=0, maximized=False))

    state = store.load()

    assert state.x is None
    assert state.y is None


def test_window_state_round_trips_normal_bounds_and_maximized_state(tmp_path):
    store = WindowStateStore(tmp_path / "window.json")
    store.save(WindowState(width=1280, height=820, x=50, y=50, maximized=True))

    assert store.load() == WindowState(
        width=1280,
        height=820,
        x=50,
        y=50,
        maximized=True,
    )
