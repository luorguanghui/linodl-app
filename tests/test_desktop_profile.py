from __future__ import annotations

import threading
import time

from linodl.config.manager import ConfigManager
from linodl.core.browser import ChallengeState
from linodl.desktop.profile import DesktopProfileService
from linodl.gui.verification import VerificationResult


def wait_for_status(service, expected):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        snapshot = service.snapshot()
        if snapshot["status"] == expected:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"profile status did not become {expected!r}")


def test_profile_check_uses_injected_headless_cloak_session(tmp_path):
    captured = {}

    class FakeSession:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def start(self, prefer_cloak=False):
            captured["prefer_cloak"] = prefer_cloak

        def goto(self, url, **kwargs):
            captured["url"] = url

        def content(self):
            return "<html>normal</html>"

        def close(self):
            captured["closed"] = True

    service = DesktopProfileService(
        ConfigManager(str(tmp_path / "settings.ini")),
        session_factory=FakeSession,
        challenge_assessor=lambda _content: ChallengeState.NORMAL,
    )

    assert service.snapshot() == {"status": "unknown", "detail": ""}
    assert service.check_profile() is True
    snapshot = wait_for_status(service, "healthy")

    assert snapshot["detail"]
    assert captured["kwargs"]["headless"] is True
    assert captured["kwargs"]["anti_bot_mode"] == "cloak"
    assert captured["prefer_cloak"] is True
    assert captured["closed"] is True


def test_profile_check_reports_challenge_without_attempting_to_solve_it(tmp_path):
    class FakeSession:
        def __init__(self, **kwargs):
            pass

        def start(self, prefer_cloak=False):
            pass

        def goto(self, url, **kwargs):
            pass

        def content(self):
            return "<html>challenge</html>"

        def close(self):
            pass

    service = DesktopProfileService(
        ConfigManager(str(tmp_path / "settings.ini")),
        session_factory=FakeSession,
        challenge_assessor=lambda _content: ChallengeState.CHALLENGE,
    )

    service.check_profile()

    assert wait_for_status(service, "needs_verification")["detail"]


def test_manual_verification_uses_injected_visible_service(tmp_path):
    called = threading.Event()
    captured = {}

    class FakeVerificationService:
        def verify(self, target_url, config, cancel_event, progress):
            captured["target_url"] = target_url
            captured["config"] = config
            captured["cancel_event"] = cancel_event
            progress("等待人工完成验证")
            called.set()
            return VerificationResult(True, message="验证通过")

    config = ConfigManager(str(tmp_path / "settings.ini"))
    service = DesktopProfileService(
        config,
        verification_service=FakeVerificationService(),
    )

    assert service.start_manual_verification("https://example.test/challenge") is True
    assert called.wait(1)
    snapshot = wait_for_status(service, "healthy")

    assert snapshot["detail"] == "验证通过"
    assert captured["target_url"] == "https://example.test/challenge"
    assert captured["config"] is config


def test_manual_verification_failure_becomes_redacted_error_state(tmp_path):
    class FailingVerificationService:
        def verify(self, target_url, config, cancel_event, progress):
            raise RuntimeError("token=secret-value")

    service = DesktopProfileService(
        ConfigManager(str(tmp_path / "settings.ini")),
        verification_service=FailingVerificationService(),
    )

    service.start_manual_verification("https://example.test/challenge")
    snapshot = wait_for_status(service, "error")

    assert "secret-value" not in snapshot["detail"]
