import queue
import re
import threading
import time

from ..config.manager import ConfigManager
from ..core.browser import BASE_URL, BrowserSession, is_cloudflare_challenge
from ..core.search import SearchEngine
from ..core.catalog import fetch_catalog, parse_catalog
from ..core.auth import login, check_logged_in
from ..core.downloader import DownloadCancelled, Downloader, sanitize
from ..core.epub import EpubExporter
from .tasks import TaskInputSnapshot, TaskStatus, TaskStore, task_store
from .verification import VerificationService


verification_service = VerificationService()


class BackgroundWorker(threading.Thread):
    def __init__(
        self,
        message_queue: queue.Queue,
        owner=None,
        *,
        task_title: str = "后台任务",
        input_snapshot: TaskInputSnapshot | None = None,
        task_store_instance: TaskStore | None = None,
    ):
        super().__init__(daemon=True)
        self._queue = message_queue
        self._cancel_flag = threading.Event()
        self._owner = owner
        self._task_store = task_store_instance or task_store
        self._task_id = self._task_store.create(
            task_title,
            input_snapshot,
        ).id
        self._outcome = None
        self._error_detail = ""

    @property
    def task(self):
        return self._task_store.get(self._task_id)

    def start(self):
        if self.task.status is TaskStatus.QUEUED:
            self._task_store.transition(
                self._task_id,
                TaskStatus.RUNNING,
                "正在运行",
            )
        super().start()

    def cancel(self):
        self._cancel_flag.set()
        if self.task.status not in {
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.COMPLETED,
        }:
            self._task_store.transition(
                self._task_id,
                TaskStatus.CANCELLING,
                "正在取消",
            )

    def is_cancelled(self):
        return self._cancel_flag.is_set()

    def report_progress(self, msg: str):
        if self.task.status in {
            TaskStatus.RUNNING,
            TaskStatus.WAITING_FOR_PROFILE,
        }:
            self._task_store.transition(
                self._task_id,
                TaskStatus.RUNNING,
                msg,
            )
        self._queue.put(("progress", msg, self._owner))

    def report_profile_wait(self, msg: str):
        self._task_store.transition(
            self._task_id,
            TaskStatus.WAITING_FOR_PROFILE,
            msg,
        )
        self._queue.put(("progress", msg, self._owner))

    def verify_challenge(self, target_url: str, reason: str = "") -> bool:
        message = "等待用户完成浏览器验证"
        self._task_store.transition(
            self._task_id,
            TaskStatus.WAITING_FOR_VERIFICATION,
            message,
        )
        self._queue.put(("progress", message, self._owner))
        result = verification_service.verify(
            target_url,
            self.config,
            self._cancel_flag,
            self.report_progress,
        )
        if result.cancelled:
            self.cancel()
            return False
        if not result.passed:
            raise RuntimeError(result.message)
        self._task_store.transition(
            self._task_id,
            TaskStatus.RUNNING,
            result.message,
        )
        self._queue.put(("progress", result.message, self._owner))
        return True

    def report_result(self, data):
        self._outcome = TaskStatus.COMPLETED
        self._queue.put(("result", data, self._owner))

    def report_error(self, msg: str):
        self._outcome = TaskStatus.FAILED
        self._error_detail = msg
        self._queue.put(("error", msg, self._owner))

    def report_done(self):
        self._queue.put(("done", None, self._owner))
        if self.is_cancelled():
            status = TaskStatus.CANCELLED
            detail = "已取消"
        elif self._outcome is TaskStatus.FAILED:
            status = TaskStatus.FAILED
            detail = "执行失败"
        else:
            status = TaskStatus.COMPLETED
            detail = "已完成"
        self._task_store.transition(
            self._task_id,
            status,
            detail,
            progress=1.0 if status is TaskStatus.COMPLETED else None,
            error_detail=self._error_detail,
        )


class SearchWorker(BackgroundWorker):
    def __init__(self, keyword: str, config: ConfigManager, message_queue: queue.Queue, owner=None):
        super().__init__(
            message_queue,
            owner=owner,
            task_title=f"搜索 {keyword}",
            input_snapshot=TaskInputSnapshot(kind="search", query=keyword),
        )
        self.keyword = keyword
        self.config = config

    def run(self):
        session = None
        try:
            self.report_progress("正在启动浏览器...")
            session = BrowserSession(
                headless=self.config.headless,
                anti_bot_mode=self.config.anti_bot_mode,
                proxy=self.config.proxy,
                geoip=self.config.geoip,
                profile_dir=self.config.profile_dir,
                progress_callback=self.report_progress,
                cancel_event=self._cancel_flag,
                profile_wait_callback=self.report_profile_wait,
                verification_callback=self.verify_challenge,
            )
            session.start()
            self.report_progress(f"正在搜索: {self.keyword}")
            engine = SearchEngine(browser_session=session)
            results = engine.search(self.keyword)
            self.report_result(results)
        except Exception as e:
            self.report_error(str(e))
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            self.report_done()


class CatalogWorker(BackgroundWorker):
    def __init__(self, url: str, config: ConfigManager, message_queue: queue.Queue, owner=None):
        super().__init__(
            message_queue,
            owner=owner,
            task_title="读取作品目录",
            input_snapshot=TaskInputSnapshot(kind="catalog", url=url),
        )
        self.url = url
        self.config = config

    def run(self):
        session = None
        try:
            self.report_progress("正在获取目录...")
            session = BrowserSession(
                headless=self.config.headless,
                anti_bot_mode=self.config.anti_bot_mode,
                proxy=self.config.proxy,
                geoip=self.config.geoip,
                profile_dir=self.config.profile_dir,
                progress_callback=self.report_progress,
                cancel_event=self._cancel_flag,
                profile_wait_callback=self.report_profile_wait,
                verification_callback=self.verify_challenge,
            )
            session.start()
            html = fetch_catalog(self.url, browser_session=session)
            volumes, novel_info = parse_catalog(html)
            self.report_result((volumes, novel_info))
        except Exception as e:
            self.report_error(str(e))
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            self.report_done()


class DownloadWorker(BackgroundWorker):
    def __init__(
        self, volumes, selected_volume_names, novel_info,
        config: ConfigManager, message_queue: queue.Queue, owner=None
    ):
        super().__init__(
            message_queue,
            owner=owner,
            task_title=f"下载 {getattr(novel_info, 'title', '') or '作品'}",
            input_snapshot=TaskInputSnapshot(
                kind="download",
                selected_volumes=tuple(sorted(selected_volume_names)),
                output_dir=config.output_dir,
            ),
        )
        self.volumes = volumes
        self.selected_volume_names = selected_volume_names
        self.novel_info = novel_info
        self.config = config

    def run(self):
        session = None
        try:
            self.report_progress("正在启动浏览器...")
            session = BrowserSession(
                headless=self.config.headless,
                anti_bot_mode=self.config.anti_bot_mode,
                proxy=self.config.proxy,
                geoip=self.config.geoip,
                profile_dir=self.config.profile_dir,
                progress_callback=self.report_progress,
                cancel_event=self._cancel_flag,
                profile_wait_callback=self.report_profile_wait,
                verification_callback=self.verify_challenge,
            )
            session.start()

            if self.is_cancelled():
                return

            if self.config.has_credentials():
                self.report_progress("正在登录...")
                ok, msg = login(session, self.config.username, self.config.password)
                if not ok:
                    self.report_error(f"登录失败: {msg}")
                    return

            if self.is_cancelled():
                return

            downloader = Downloader(
                output_dir=self.config.output_dir,
                delay_range=self.config.delay_range,
                progress_callback=self.report_progress,
                cancel_callback=self.is_cancelled,
            )

            self.report_progress("正在下载...")
            result = downloader.download(
                self.volumes,
                self.selected_volume_names,
                self.novel_info,
                browser_session=session,
            )

            if self.is_cancelled():
                return

            self.report_progress("正在校验...")
            verification = downloader.verify_all(self.volumes, self.selected_volume_names)

            self.report_result((result, verification, downloader))
        except DownloadCancelled:
            pass
        except Exception as e:
            self.report_error(str(e))
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            self.report_done()


class RetryWorker(BackgroundWorker):
    def __init__(
        self, downloader: Downloader, volumes, selected_volume_names,
        novel_info, config: ConfigManager, message_queue: queue.Queue, owner=None
    ):
        super().__init__(
            message_queue,
            owner=owner,
            task_title=f"重试 {getattr(novel_info, 'title', '') or '作品'}",
            input_snapshot=TaskInputSnapshot(
                kind="retry",
                selected_volumes=tuple(sorted(selected_volume_names)),
                output_dir=config.output_dir,
            ),
        )
        self.downloader = downloader
        self.volumes = volumes
        self.selected_volume_names = selected_volume_names
        self.novel_info = novel_info
        self.config = config

    def run(self):
        session = None
        try:
            self.downloader.cancel_callback = self.is_cancelled
            self.report_progress("正在启动浏览器用于重试...")
            session = BrowserSession(
                headless=self.config.headless,
                anti_bot_mode=self.config.anti_bot_mode,
                proxy=self.config.proxy,
                geoip=self.config.geoip,
                profile_dir=self.config.profile_dir,
                progress_callback=self.report_progress,
                cancel_event=self._cancel_flag,
                profile_wait_callback=self.report_profile_wait,
                verification_callback=self.verify_challenge,
            )
            session.start()

            if self.config.has_credentials():
                ok, msg = login(session, self.config.username, self.config.password)
                if not ok:
                    self.report_error(f"登录失败: {msg}")
                    return

            self.report_progress("正在重试失败章节...")
            result = self.downloader.download(
                self.volumes,
                self.selected_volume_names,
                self.novel_info,
                browser_session=session,
            )

            self.report_progress("重试后校验中...")
            verification = self.downloader.verify_all(self.volumes, self.selected_volume_names)

            self.report_result((result, verification, self.downloader))
        except DownloadCancelled:
            pass
        except Exception as e:
            self.report_error(str(e))
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            self.report_done()


class ExportWorker(BackgroundWorker):
    def __init__(self, novel_info, volumes, base_dir: str, per_volume: bool, message_queue: queue.Queue, owner=None):
        super().__init__(
            message_queue,
            owner=owner,
            task_title=f"导出 {getattr(novel_info, 'title', '') or '作品'}",
            input_snapshot=TaskInputSnapshot(kind="export", output_dir=base_dir),
        )
        self.novel_info = novel_info
        self.volumes = volumes
        self.base_dir = base_dir
        self.per_volume = per_volume

    def run(self):
        try:
            self.report_progress("正在导出 EPUB...")
            exporter = EpubExporter()
            result = exporter.export(
                self.novel_info, self.volumes, self.base_dir, per_volume=self.per_volume
            )
            self.report_result(result)
        except Exception as e:
            self.report_error(str(e))
        finally:
            self.report_done()


class VerifyWorker(BackgroundWorker):
    def __init__(self, volumes, selected_volume_names, output_dir: str, message_queue: queue.Queue, owner=None):
        super().__init__(
            message_queue,
            owner=owner,
            task_title="校验下载内容",
            input_snapshot=TaskInputSnapshot(
                kind="verify",
                selected_volumes=tuple(sorted(selected_volume_names)),
                output_dir=output_dir,
            ),
        )
        self.volumes = volumes
        self.selected_volume_names = selected_volume_names
        self.output_dir = output_dir

    def run(self):
        try:
            self.report_progress("正在校验下载内容...")
            downloader = Downloader(output_dir=self.output_dir)
            result = downloader.verify_all(self.volumes, self.selected_volume_names)
            self.report_result(result)
        except Exception as e:
            self.report_error(str(e))
        finally:
            self.report_done()


def _page_has_content(session) -> bool:
    """Check if the page has loaded meaningful content.

    Returns False for CF challenge pages even if they have text, since
    challenge pages (e.g. "Just a moment...") are not real content."""
    try:
        html = session.content() or ""
    except Exception:
        return False
    if is_cloudflare_challenge(html):
        return False
    text = re.sub(r"<[^>]+>", " ", html).strip()
    if len(text) >= 20:
        return True
    compact_html = html.lower()
    return any(marker in compact_html for marker in (
        "linovelib",
        "/novel/",
        "/s6/",
        "轻小说",
        "小說",
        "小说",
    ))


def _wait_for_page_ready(session, retries: int = 5, delay: float = 1.0) -> bool:
    """Wait for page content to render after navigation.

    After domcontentloaded the JS-rendered content may still be loading.
    We wait for networkidle briefly, then retry."""
    for i in range(retries):
        if _page_has_content(session):
            return True
        if i < retries - 1:
            try:
                session.page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            time.sleep(delay)
    return False


def _wait_for_clearance_cookie(session, timeout_ms: int, progress_callback=None) -> bool:
    """Wait for the cf_clearance cookie to be set.

    If Turnstile auto-resolves without user interaction, the clearance cookie
    may not be set. In that case we prompt the user to manually complete
    verification so the cookie is saved to the profile."""
    if session._has_cloudflare_clearance():
        return True

    def _report(msg):
        if progress_callback:
            progress_callback(msg)

    _report(
        "验证已通过但 cookie 尚未保存，请在 CloakBrowser 窗口中\n"
        "点击「验证您是真人」完成人机验证，程序会自动继续。"
    )
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        time.sleep(1)
        if session._has_cloudflare_clearance():
            return True
    return False


def perform_cloudflare_warmup(session, timeout_ms: int = 600000, progress_callback=None):
    def progress(message: str):
        if progress_callback:
            progress_callback(message)

    session.start(prefer_cloak=True)
    session._clear_cloudflare_cookies()

    progress("正在打开首页 — 请在浏览器窗口中完成人机验证...")
    home_ok = session.navigate_with_challenge_retry(
        BASE_URL, reason="Cloudflare 预热", timeout_ms=timeout_ms
    )
    if not home_ok:
        return False, "Cloudflare 验证超时。"
    if not _wait_for_page_ready(session):
        return False, "页面未加载完成，请重新点击预热并等待页面显示后再结束。"

    search_url = f"{BASE_URL}/S6/"
    progress("首页已通过，正在尝试打开搜索页确认 profile 可复用...")
    try:
        search_ok = session.navigate_with_challenge_retry(
            search_url, reason="搜索页", timeout_ms=60000
        )
        if search_ok and _wait_for_page_ready(session):
            progress("搜索页验证通过，profile 可正常复用。")
        else:
            progress("搜索页验证跳过（不影响预热结果），浏览器档案已保存。")
    except Exception:
        progress("搜索页验证跳过（不影响预热结果），浏览器档案已保存。")

    return True, "Cloudflare 验证成功完成，浏览器档案已保存。"


class WarmupWorker(BackgroundWorker):
    def __init__(self, config: ConfigManager, message_queue: queue.Queue, owner=None):
        super().__init__(
            message_queue,
            owner=owner,
            task_title="验证浏览档案",
            input_snapshot=TaskInputSnapshot(kind="warmup"),
        )
        self.config = config

    def run(self):
        session = None
        try:
            self.report_progress("正在启动 CloakBrowser 进行 Cloudflare 预热...")
            session = BrowserSession(
                headless=False,
                anti_bot_mode="cloak",
                proxy=self.config.proxy,
                geoip=self.config.geoip,
                profile_dir=self.config.profile_dir,
                progress_callback=self.report_progress,
                humanize=False,
                cancel_event=self._cancel_flag,
                profile_wait_callback=self.report_profile_wait,
            )
            ok, message = perform_cloudflare_warmup(
                session,
                timeout_ms=600000,
                progress_callback=self.report_progress,
            )
            if ok:
                self.report_result(message)
            else:
                self.report_error(message)
        except Exception as e:
            self.report_error(str(e))
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass
            self.report_done()
