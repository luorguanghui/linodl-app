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


def test_window_state_round_trips_maximized_state(tmp_path):
    store = WindowStateStore(tmp_path / "window.json")
    store.save(WindowState(width=1280, height=820, x=50, y=50, maximized=True))

    assert store.load().maximized is True
