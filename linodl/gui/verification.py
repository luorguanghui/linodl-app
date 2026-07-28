"""Visible browser verification for recoverable GUI tasks."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from ..config.manager import ConfigManager
from ..core.browser import BrowserSession, ChallengeState, assess_challenge


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    cancelled: bool = False
    message: str = ""


class VerificationService:
    """Open a headed CloakBrowser and recheck the original target page."""

    def __init__(
        self,
        session_factory=BrowserSession,
        poll_interval: float = 1.0,
    ):
        self._session_factory = session_factory
        self._poll_interval = poll_interval

    def verify(
        self,
        target_url: str,
        config: ConfigManager,
        cancel_event: threading.Event,
        progress: Callable[[str], None],
        *,
        timeout_ms: int = 300000,
    ) -> VerificationResult:
        if cancel_event.is_set():
            return VerificationResult(False, cancelled=True, message="验证已取消")

        session = self._session_factory(
            headless=False,
            anti_bot_mode="cloak",
            proxy=config.proxy,
            geoip=bool(config.proxy and config.geoip),
            profile_dir=config.profile_dir,
            progress_callback=progress,
            humanize=False,
            cancel_event=cancel_event,
            profile_wait_callback=progress,
        )
        try:
            progress("已打开可见 CloakBrowser，请完成页面验证。")
            session.start(prefer_cloak=True)
            session.goto(target_url, timeout=45000, wait_until="domcontentloaded")
            deadline = time.monotonic() + timeout_ms / 1000

            while time.monotonic() < deadline:
                if cancel_event.is_set():
                    return VerificationResult(
                        False,
                        cancelled=True,
                        message="验证已取消",
                    )

                state = assess_challenge(session.content())
                if state is ChallengeState.NORMAL:
                    progress("正在复检原目标页面…")
                    session.goto(
                        target_url,
                        timeout=45000,
                        wait_until="domcontentloaded",
                    )
                    if assess_challenge(session.content()) is ChallengeState.NORMAL:
                        return VerificationResult(
                            True,
                            message="验证已通过，正在恢复原任务。",
                        )

                time.sleep(self._poll_interval)

            return VerificationResult(
                False,
                message="验证等待超时，输入和浏览档案已保留。",
            )
        except Exception as exc:
            if cancel_event.is_set():
                return VerificationResult(
                    False,
                    cancelled=True,
                    message="验证已取消",
                )
            return VerificationResult(
                False,
                message=f"可见浏览器验证失败: {exc}",
            )
        finally:
            session.close()
