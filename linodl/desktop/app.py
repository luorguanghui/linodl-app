from __future__ import annotations

import os
from pathlib import Path

import webview

from ..config.manager import ConfigManager
from .assets import DesktopAssets
from .window_state import WindowState, WindowStateStore


def run_desktop(config: ConfigManager, debug: bool = False) -> None:
    from .bridge import DesktopBridge

    development_url = os.environ.get("LINODL_FRONTEND_URL", "").strip() if debug else ""
    url = development_url or DesktopAssets.resolve().url
    bridge = DesktopBridge(config=config, debug=debug)
    state_store = WindowStateStore(Path.home() / ".linodl-window.json")
    saved_state = state_store.load()
    normal_state = saved_state
    create_options = {
        "width": saved_state.width,
        "height": saved_state.height,
        "min_size": (900, 640),
    }
    if saved_state.x is not None and saved_state.y is not None:
        create_options.update({"x": saved_state.x, "y": saved_state.y})
    window = webview.create_window(
        "linodl 路 杞诲皬璇磋祫鏂欏簱",
        url=url,
        js_api=bridge,
        **create_options,
    )
    bridge.attach_window(window)

    def record_normal_bounds(*_args) -> None:
        nonlocal normal_state
        if _is_maximized(window):
            return
        normal_state = WindowState(
            width=_window_int(window, "width", normal_state.width),
            height=_window_int(window, "height", normal_state.height),
            x=_window_position(window, "x"),
            y=_window_position(window, "y"),
            maximized=False,
        )

    def save_window_state(*_args) -> None:
        record_normal_bounds()
        state_store.save(
            WindowState(
                width=normal_state.width,
                height=normal_state.height,
                x=normal_state.x,
                y=normal_state.y,
                maximized=_is_maximized(window, saved_state.maximized),
            )
        )

    def close_window(*_args):
        save_window_state()
        if bridge.consume_force_close():
            return None
        if bridge.has_active_tasks():
            window.evaluate_js("window.linodlConfirmClose()")
            return False
        return None

    _subscribe(window, "closing", close_window)
    _subscribe(window, "moved", record_normal_bounds)
    _subscribe(window, "resized", record_normal_bounds)
    if saved_state.maximized:
        _subscribe(window, "shown", lambda *_args: window.maximize())
    webview.start(debug=debug)


def _subscribe(window, event_name: str, callback) -> None:
    event = getattr(getattr(window, "events", None), event_name, None)
    if event is not None:
        event += callback


def _is_maximized(window, fallback: bool = False) -> bool:
    return getattr(window, "maximized", fallback) is True


def _window_int(window, name: str, fallback: int) -> int:
    value = getattr(window, name, fallback)
    return value if type(value) is int else fallback


def _window_position(window, name: str) -> int | None:
    value = getattr(window, name, None)
    return value if type(value) is int else None
