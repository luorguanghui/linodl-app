import threading
import sys
import types

import pytest


def test_same_profile_waits_until_first_lease_releases(tmp_path):
    from linodl.core.profile_coordinator import BrowserProfileCoordinator

    coordinator = BrowserProfileCoordinator(poll_interval=0.01)
    entered = threading.Event()

    def acquire_in_thread():
        with coordinator.acquire(str(tmp_path)):
            entered.set()

    with coordinator.acquire(str(tmp_path)):
        thread = threading.Thread(target=acquire_in_thread)
        thread.start()
        assert not entered.wait(0.05)

    assert entered.wait(0.2)
    thread.join(0.5)
    assert not thread.is_alive()


def test_waiting_profile_lease_can_be_cancelled(tmp_path):
    from linodl.core.profile_coordinator import (
        BrowserProfileCoordinator,
        ProfileLeaseCancelled,
    )

    coordinator = BrowserProfileCoordinator(poll_interval=0.01)
    cancel = threading.Event()
    outcome = []

    def acquire_in_thread():
        try:
            with coordinator.acquire(str(tmp_path), cancel_event=cancel):
                outcome.append("entered")
        except ProfileLeaseCancelled:
            outcome.append("cancelled")

    with coordinator.acquire(str(tmp_path)):
        thread = threading.Thread(target=acquire_in_thread)
        thread.start()
        cancel.set()
        thread.join(0.5)

    assert outcome == ["cancelled"]
    assert not thread.is_alive()


def test_wait_callback_is_reported_once(tmp_path):
    from linodl.core.profile_coordinator import BrowserProfileCoordinator

    coordinator = BrowserProfileCoordinator(poll_interval=0.01)
    messages = []
    entered = threading.Event()

    def acquire_in_thread():
        with coordinator.acquire(
            str(tmp_path),
            wait_callback=messages.append,
        ):
            entered.set()

    with coordinator.acquire(str(tmp_path)):
        thread = threading.Thread(target=acquire_in_thread)
        thread.start()
        assert not entered.wait(0.05)

    thread.join(0.5)
    assert messages == ["等待浏览档案…"]


def test_releases_profile_after_body_raises(tmp_path):
    from linodl.core.profile_coordinator import BrowserProfileCoordinator

    coordinator = BrowserProfileCoordinator(poll_interval=0.01)

    with pytest.raises(RuntimeError, match="boom"):
        with coordinator.acquire(str(tmp_path)):
            raise RuntimeError("boom")

    with coordinator.acquire(str(tmp_path)):
        pass


def test_browser_session_holds_profile_until_close(monkeypatch, tmp_path):
    from linodl.core import browser as browser_module
    from linodl.core.browser import BrowserSession
    from linodl.core.profile_coordinator import BrowserProfileCoordinator

    class FakeContext:
        pages = []

        def new_page(self):
            return types.SimpleNamespace(content=lambda: "")

        def close(self):
            pass

    monkeypatch.setattr(
        browser_module,
        "profile_coordinator",
        BrowserProfileCoordinator(poll_interval=0.01),
        raising=False,
    )
    monkeypatch.setitem(
        sys.modules,
        "cloakbrowser",
        types.SimpleNamespace(
            launch_persistent_context=lambda path, **kwargs: FakeContext()
        ),
    )

    first = BrowserSession(profile_dir=str(tmp_path), anti_bot_mode="cloak")
    second = BrowserSession(profile_dir=str(tmp_path), anti_bot_mode="cloak")
    second_started = threading.Event()

    first.start()

    def start_second():
        second.start()
        second_started.set()

    thread = threading.Thread(target=start_second)
    thread.start()
    assert not second_started.wait(0.05)

    first.close()
    assert second_started.wait(0.2)
    second.close()
    thread.join(0.5)
    assert not thread.is_alive()
