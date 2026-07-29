"""Background browser-profile health and manual verification commands."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from typing import Callable, Literal

from ..config.manager import ConfigManager
from ..core.browser import (
    BASE_URL,
    BrowserSession,
    ChallengeState,
    assess_challenge,
)
from ..core.sanitization import redact_sensitive_text
from ..gui.verification import VerificationService


ProfileStatus = Literal[
    "unknown",
    "checking",
    "healthy",
    "needs_verification",
    "busy",
    "error",
]


@dataclass(frozen=True)
class ProfileHealth:
    status: ProfileStatus = "unknown"
    detail: str = ""


class DesktopProfileService:
    """Run explicit profile operations without blocking the pywebview bridge."""

    def __init__(
        self,
        config: ConfigManager,
        *,
        session_factory=BrowserSession,
        verification_service: VerificationService | None = None,
        challenge_assessor: Callable[[str | None], ChallengeState] = assess_challenge,
        check_url: str = BASE_URL,
    ):
        self._config = config
        self._session_factory = session_factory
        self._verification_service = verification_service or VerificationService()
        self._challenge_assessor = challenge_assessor
        self._check_url = check_url
        self._lock = threading.RLock()
        self._health = ProfileHealth()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return asdict(self._health)

    def check_profile(self) -> bool:
        return self._start_background(
            ProfileHealth("checking", "正在检查浏览档案"),
            self._check_profile,
        )

    def start_manual_verification(self, target_url: str) -> bool:
        return self._start_background(
            ProfileHealth("checking", "正在打开可见浏览器"),
            lambda: self._verify_manually(target_url),
        )

    def _start_background(
        self,
        initial: ProfileHealth,
        operation: Callable[[], None],
    ) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._health = initial
            thread = threading.Thread(target=operation, daemon=True)
            self._thread = thread
            thread.start()
            return True

    def _set_health(self, status: ProfileStatus, detail: str) -> None:
        with self._lock:
            self._health = ProfileHealth(status, redact_sensitive_text(detail))

    def _report_profile_wait(self, detail: str) -> None:
        self._set_health("busy", detail or "浏览档案正被其他任务使用")

    def _check_profile(self) -> None:
        session = None
        try:
            session = self._session_factory(
                headless=True,
                anti_bot_mode="cloak",
                proxy=self._config.proxy,
                geoip=bool(self._config.proxy and self._config.geoip),
                profile_dir=self._config.profile_dir,
                progress_callback=lambda _message: None,
                humanize=False,
                profile_wait_callback=self._report_profile_wait,
            )
            session.start(prefer_cloak=True)
            session.goto(
                self._check_url,
                timeout=45000,
                wait_until="domcontentloaded",
            )
            state = self._challenge_assessor(session.content())
            if state is ChallengeState.NORMAL:
                self._set_health("healthy", "浏览档案可正常访问目标页面")
            else:
                self._set_health(
                    "needs_verification",
                    "目标页面需要人工验证或暂时无法确认",
                )
        except Exception as exc:
            self._set_health(
                "error",
                f"浏览档案检查失败：{redact_sensitive_text(exc)}",
            )
        finally:
            if session is not None:
                try:
                    session.close()
                except Exception:
                    pass

    def _verify_manually(self, target_url: str) -> None:
        cancel_event = threading.Event()

        def progress(detail: str) -> None:
            self._set_health("checking", detail)

        try:
            result = self._verification_service.verify(
                target_url,
                self._config,
                cancel_event,
                progress,
            )
        except Exception as exc:
            self._set_health(
                "error",
                f"人工验证失败：{redact_sensitive_text(exc)}",
            )
            return
        if result.passed:
            self._set_health("healthy", result.message or "人工验证已通过")
        elif result.cancelled:
            self._set_health("unknown", result.message or "人工验证已取消")
        else:
            self._set_health(
                "needs_verification",
                result.message or "仍需完成人工验证",
            )
