import importlib
import sys
from types import ModuleType

import pytest


@pytest.fixture
def desktop_app(monkeypatch):
    calls = []

    class Event:
        def __init__(self):
            self.callbacks = []

        def __iadd__(self, callback):
            self.callbacks.append(callback)
            return self

    class Window:
        def __init__(self):
            self.events = type(
                "Events",
                (),
                {
                    "closing": Event(),
                    "moved": Event(),
                    "resized": Event(),
                    "maximized": Event(),
                    "restored": Event(),
                    "shown": Event(),
                },
            )()

    window = Window()
    webview = ModuleType("webview")
    webview.created_titles = []
    webview.started = []

    def create_window(title, *, url, js_api, width, height, min_size, **kwargs):
        webview.created_titles.append(title)
        calls.append({"url": url, "debug": js_api.debug})
        return window

    webview.create_window = create_window
    def start(*, debug, icon=None):
        webview.started.append({"debug": debug, "icon": icon})

    webview.start = start

    bridge = ModuleType("linodl.desktop.bridge")

    class DesktopBridge:
        def __init__(self, config, debug):
            self.debug = debug

        def attach_window(self, attached_window):
            assert attached_window is window

    bridge.DesktopBridge = DesktopBridge
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setitem(sys.modules, "linodl.desktop.bridge", bridge)
    monkeypatch.delitem(sys.modules, "linodl.desktop.app", raising=False)

    return importlib.import_module("linodl.desktop.app"), calls


def test_run_desktop_uses_unicode_window_title(desktop_app):
    app, _ = desktop_app

    app.run_desktop(config=object())

    assert app.webview.created_titles == ["linodl · 轻小说资料库"]


def test_run_desktop_uses_local_assets_outside_debug_mode(desktop_app, monkeypatch, tmp_path):
    app, calls = desktop_app
    index_file = tmp_path / "index.html"
    index_file.write_text("<main>linodl</main>", encoding="utf-8")
    icon_file = tmp_path / "linodl.ico"
    icon_file.write_bytes(b"icon")
    monkeypatch.setenv("LINODL_FRONTEND_URL", "http://127.0.0.1:5173")
    monkeypatch.setattr(
        app.DesktopAssets,
        "resolve",
        lambda: app.DesktopAssets(index_file=index_file, icon_file=icon_file),
    )

    app.run_desktop(config=object(), debug=False)

    assert calls == [{"url": index_file.as_uri(), "debug": False}]
    assert app.webview.started == [{"debug": False, "icon": str(icon_file)}]


def test_run_desktop_uses_development_url_in_debug_mode(desktop_app, monkeypatch):
    app, calls = desktop_app
    monkeypatch.setenv("LINODL_FRONTEND_URL", "http://127.0.0.1:5173")

    app.run_desktop(config=object(), debug=True)

    assert calls == [{"url": "http://127.0.0.1:5173", "debug": True}]


def test_run_desktop_defers_close_when_a_task_is_active(desktop_app, monkeypatch):
    app, _ = desktop_app
    callbacks = []

    class Store:
        def load(self):
            return app.WindowState()

        def save(self, state):
            self.state = state

    class Event:
        def __iadd__(self, callback):
            callbacks.append(callback)
            return self

    class Window:
        events = type("Events", (), {"closing": Event()})()

        def evaluate_js(self, script):
            self.script = script

    window = Window()
    monkeypatch.setattr(app, "WindowStateStore", lambda path: Store())
    monkeypatch.setattr(app.webview, "create_window", lambda *args, **kwargs: window)

    class Bridge:
        debug = False

        def __init__(self, config, debug):
            self.debug = debug

        def attach_window(self, attached_window):
            assert attached_window is window

        def consume_force_close(self):
            return False

        def has_active_tasks(self):
            return True

    bridge_module = sys.modules["linodl.desktop.bridge"]
    bridge_module.DesktopBridge = Bridge

    app.run_desktop(config=object())

    assert callbacks[0]() is False
    assert window.script == "window.linodlConfirmClose()"


def test_run_desktop_saves_normal_bounds_when_closed(desktop_app, monkeypatch):
    app, _ = desktop_app
    saved = []

    class Store:
        def load(self):
            return app.WindowState()

        def save(self, state):
            saved.append(state)

    class Bridge:
        debug = False

        def __init__(self, config, debug):
            self.debug = debug

        def attach_window(self, window):
            self.window = window

        def consume_force_close(self):
            return False

        def has_active_tasks(self):
            return False

    class Window:
        width = 1440
        height = 900
        x = 40
        y = 30
        maximized = False

        class Closing:
            def __init__(self):
                self.callbacks = []

            def __iadd__(self, callback):
                self.callbacks.append(callback)
                return self

        events = type("Events", (), {"closing": Closing()})()

    window = Window()
    monkeypatch.setattr(app, "WindowStateStore", lambda path: Store(), raising=False)
    monkeypatch.setattr(app.webview, "create_window", lambda *args, **kwargs: window)
    sys.modules["linodl.desktop.bridge"].DesktopBridge = Bridge

    app.run_desktop(config=object())

    assert window.events.closing.callbacks[0]() is None
    assert saved == [app.WindowState(1440, 900, 40, 30, False)]
