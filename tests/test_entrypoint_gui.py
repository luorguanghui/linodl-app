import sys
from types import ModuleType

from linodl import __main__ as entrypoint


def test_gui_flag_starts_react_desktop(monkeypatch):
    calls = []
    desktop_app = ModuleType("linodl.desktop.app")
    desktop_app.run_desktop = lambda config, debug: calls.append((config, debug))
    config = object()
    monkeypatch.setattr(entrypoint, "ConfigManager", lambda: config)
    monkeypatch.setitem(sys.modules, "linodl.desktop.app", desktop_app)
    monkeypatch.setattr(sys, "argv", ["linodl", "--gui"])

    entrypoint.main()

    assert calls == [(config, False)]


def test_legacy_gui_flag_starts_customtkinter_fallback(monkeypatch):
    calls = []
    gui_app = ModuleType("linodl.gui.app")
    config = object()

    class MainWindow:
        def __init__(self, received_config, debug):
            calls.append((received_config, debug))

        def run(self):
            calls.append("run")

    gui_app.MainWindow = MainWindow
    monkeypatch.setattr(entrypoint, "ConfigManager", lambda: config)
    monkeypatch.setitem(sys.modules, "linodl.gui.app", gui_app)
    monkeypatch.setattr(sys, "argv", ["linodl", "--legacy-gui", "--debug"])

    entrypoint.main()

    assert calls == [(config, True), "run"]
