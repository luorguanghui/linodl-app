import importlib
import sys
from types import ModuleType

import pytest


@pytest.fixture
def desktop_app(monkeypatch):
    calls = []
    window = object()
    webview = ModuleType("webview")

    def create_window(title, *, url, js_api, width, height, min_size):
        calls.append({"url": url, "debug": js_api.debug})
        return window

    webview.create_window = create_window
    webview.start = lambda *, debug: None

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


def test_run_desktop_uses_local_assets_outside_debug_mode(desktop_app, monkeypatch, tmp_path):
    app, calls = desktop_app
    index_file = tmp_path / "index.html"
    index_file.write_text("<main>linodl</main>", encoding="utf-8")
    monkeypatch.setenv("LINODL_FRONTEND_URL", "http://127.0.0.1:5173")
    monkeypatch.setattr(
        app.DesktopAssets,
        "resolve",
        lambda: app.DesktopAssets(index_file=index_file),
    )

    app.run_desktop(config=object(), debug=False)

    assert calls == [{"url": index_file.as_uri(), "debug": False}]


def test_run_desktop_uses_development_url_in_debug_mode(desktop_app, monkeypatch):
    app, calls = desktop_app
    monkeypatch.setenv("LINODL_FRONTEND_URL", "http://127.0.0.1:5173")

    app.run_desktop(config=object(), debug=True)

    assert calls == [{"url": "http://127.0.0.1:5173", "debug": True}]
