"""Interactive CLI application using rich."""

import msvcrt
import os
import re
import sys

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from ..config.manager import ConfigManager
from ..core.auth import check_logged_in, login
from ..core.browser import BrowserSession
from ..core.catalog import fetch_catalog, parse_catalog
from ..core.downloader import Downloader
from ..core.epub import EpubExporter
from ..core.search import SearchEngine
from ..models.novel import Chapter, ChapterIssue, NovelInfo, VerificationResult, Volume


class App:
    def __init__(self, config: ConfigManager = None, debug: bool = False):
        self.config = config or ConfigManager()
        self.console = Console()
        self.debug = debug

    def run(self):
        self._banner()
        self._ensure_credentials()

        while True:
            choice = self._main_menu()
            if choice == "1":
                self._flow_search()
            elif choice == "2":
                self._flow_download_url()
            elif choice == "3":
                self._flow_export_epub()
            elif choice == "4":
                self._flow_verify()
            elif choice == "5":
                self._flow_settings()
            elif choice == "6":
                self.console.print("[dim]再见![/dim]")
                break

    def _banner(self):
        self.console.print()
        self.console.print(Panel.fit(
            "[bold cyan]linodl v2.1[/bold cyan] - linovelib.com 小说下载器\n"
            "[dim]支持搜索、登录、按卷下载、EPUB 导出、Cloudflare 自动兜底[/dim]",
            border_style="cyan",
        ))

    def _prompt_password(self, prompt_text: str = "  密码") -> str:
        """Prompt for password with real-time * feedback for each character."""
        self.console.print(f"{prompt_text}: ", end="")
        pwd = []
        while True:
            ch = msvcrt.getch()
            if ch in (b"\r", b"\n"):
                break
            if ch == b"\x08":
                if pwd:
                    pwd.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch == b"\x03":
                raise KeyboardInterrupt
            else:
                try:
                    char = ch.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if char.isprintable():
                    pwd.append(char)
                    sys.stdout.write("*")
                    sys.stdout.flush()
        self.console.print()
        return "".join(pwd)

    def _ensure_credentials(self):
        if not self.config.has_credentials():
            self.console.print("[yellow]未检测到账号配置，请输入登录信息[/yellow]")
            username = Prompt.ask("  邮箱/用户名")
            password = self._prompt_password()
            self.config.set_credentials(username, password)
            self.console.print("[green]✓ 账号已保存到 ~/.linovelib.ini[/green]")

    def _main_menu(self) -> str:
        self.console.print()
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="cyan", justify="right")
        table.add_column()
        table.add_row("[1]", "搜索并下载小说")
        table.add_row("[2]", "直接 URL 下载")
        table.add_row("[3]", "导出 EPUB（已有下载目录）")
        table.add_row("[4]", "校验已下载的小说")
        table.add_row("[5]", "设置")
        table.add_row("[6]", "退出")
        self.console.print(table)
        return Prompt.ask("请选择", choices=["1", "2", "3", "4", "5", "6"], default="1")

    def _new_browser_session(self, progress_callback=None) -> BrowserSession:
        return BrowserSession(
            headless=self.config.headless,
            anti_bot_mode=self.config.anti_bot_mode,
            proxy=self.config.proxy,
            geoip=self.config.geoip,
            profile_dir=self.config.profile_dir,
            progress_callback=progress_callback,
        )

    def _flow_search(self):
        keyword = Prompt.ask("输入搜索关键词").strip()
        if not keyword:
            self.console.print("[red]关键词不能为空[/red]")
            return

        self.console.print("[cyan]正在搜索...[/cyan]")
        try:
            with self._new_browser_session() as session:
                engine = SearchEngine(debug=self.debug, browser_session=session)
                novels = engine.search(keyword)
                if not novels:
                    self.console.print("[yellow]未找到结果[/yellow]")
                    return

                novel = self._display_search_results(novels)
                if novel is None:
                    return
                self._download_novel(novel, browser_session=session)
        except Exception as e:
            self.console.print(f"[red]搜索失败: {e}[/red]")
            self.console.print("[dim]提示：可尝试直接用 URL 下载（主菜单选 2）[/dim]")

    def _display_search_results(self, novels: list[NovelInfo]) -> NovelInfo | None:
        self.console.print()
        table = Table(title="搜索结果", show_lines=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("标题", style="cyan")
        table.add_column("作者", style="green")
        table.add_column("ID", style="dim", width=8)

        for i, novel in enumerate(novels[:20], 1):
            table.add_row(
                str(i),
                novel.title or "(未知标题)",
                novel.author or "-",
                novel.novel_id,
            )

        self.console.print(table)
        self.console.print(f"[dim]共 {len(novels)} 条结果[/dim]")
        choice = Prompt.ask("选择序号（或输入 0 返回）", default="1")

        try:
            idx = int(choice)
            if idx == 0:
                return None
            if 1 <= idx <= min(len(novels), 20):
                return novels[idx - 1]
        except ValueError:
            pass

        self.console.print("[red]无效选择[/red]")
        return None

    def _download_novel(self, novel: NovelInfo, browser_session: BrowserSession = None):
        if not novel.catalog_url:
            novel.catalog_url = f"https://www.linovelib.com/novel/{novel.novel_id}/catalog"

        with self.console.status("[cyan]正在获取目录...[/cyan]"):
            try:
                html = fetch_catalog(novel.catalog_url, browser_session=browser_session)
                volumes, novel_info = parse_catalog(html)
            except Exception as e:
                self.console.print(f"[red]获取目录失败: {e}[/red]")
                return

        if novel.title and not novel_info.title:
            novel_info.title = novel.title
        if novel.author and not novel_info.author:
            novel_info.author = novel.author

        self.console.print(f"\n[bold]{novel_info.title or novel.title}[/bold]")
        self.console.print(f"作者: {novel_info.author or novel.author or '-'}")
        self.console.print(f"共 {len(volumes)} 卷\n")

        vol_table = Table(show_header=True)
        vol_table.add_column("#", width=4)
        vol_table.add_column("卷名", style="cyan")
        vol_table.add_column("文本章节", justify="right")
        vol_table.add_column("插图", justify="right")
        for i, vol in enumerate(volumes, 1):
            vol_table.add_row(str(i), vol.name, str(vol.text_count), str(vol.illus_count))
        self.console.print(vol_table)

        selected = self._prompt_volume_selection(volumes)
        if not selected:
            return

        self._run_download(volumes, selected, novel_info, browser_session=browser_session)

    def _prompt_volume_selection(self, volumes: list[Volume]) -> set[str]:
        choice = Prompt.ask(
            "选择卷号 ([green]A[/green]全部 / 1,3,5 逗号分隔 / 0 返回)",
            default="A",
        )
        if choice.strip().upper() == "A":
            return {v.name for v in volumes}
        if choice.strip() == "0":
            return set()
        try:
            indices = [int(x.strip()) for x in choice.split(",")]
            selected = {volumes[i - 1].name for i in indices if 1 <= i <= len(volumes)}
        except ValueError:
            self.console.print("[red]无效选择[/red]")
            return set()
        if not selected:
            self.console.print("[red]未选择任何卷[/red]")
        return selected

    def _flow_download_url(self):
        url = Prompt.ask("输入目录 URL", default="https://www.linovelib.com/novel/")
        if not url or "linovelib.com" not in url:
            self.console.print("[red]无效 URL[/red]")
            return

        with self._new_browser_session() as session:
            with self.console.status("[cyan]正在获取目录...[/cyan]"):
                try:
                    html = fetch_catalog(url, browser_session=session)
                    volumes, novel_info = parse_catalog(html)
                except Exception as e:
                    self.console.print(f"[red]获取目录失败: {e}[/red]")
                    return

            self.console.print(f"\n[bold]{novel_info.title}[/bold]")
            self.console.print(f"作者: {novel_info.author or '-'}")
            self.console.print(f"共 {len(volumes)} 卷\n")

            selected = self._prompt_volume_selection(volumes)
            if selected:
                self._run_download(volumes, selected, novel_info, browser_session=session)

    def _show_result_panel(self, result):
        self.console.print(Panel.fit(
            f"[bold]下载完成[/bold]\n"
            f"小说: {result.novel_title}\n"
            f"成功: {result.success}  跳过: {result.skipped}  失败: {result.failed}\n"
            f"输出: {result.output_dir}",
            border_style="green",
        ))

    def _show_verification_report(self, verification: VerificationResult):
        """Display a structured verification report."""
        if verification is None:
            return

        self.console.print()

        if verification.is_clean:
            self.console.print(Panel.fit(
                f"[bold green]✓ 校验通过[/bold green]\n"
                f"共检查 {verification.total_expected} 项，全部完整",
                border_style="green",
            ))
            return

        # Build issue summary table
        summary_parts = [f"检查 {verification.total_expected} 项"]
        if verification.complete:
            summary_parts.append(f"[green]完整 {verification.complete}[/green]")
        if verification.missing:
            summary_parts.append(f"[red]缺失 {verification.missing}[/red]")
        if verification.empty:
            summary_parts.append(f"[red]空内容 {verification.empty}[/red]")
        if verification.truncated:
            summary_parts.append(f"[yellow]可能截断 {verification.truncated}[/yellow]")
        if verification.image_issues:
            summary_parts.append(f"[yellow]图片问题 {verification.image_issues}[/yellow]")
        catalog_gaps = [i for i in verification.issues if i.issue == "catalog_gap"]
        if catalog_gaps:
            summary_parts.append(f"[red]目录缺章 {len(catalog_gaps)}[/red]")

        border_style = "red" if (verification.missing or verification.empty) else "yellow"
        self.console.print(Panel.fit(
            f"[bold]校验结果[/bold]\n" + "，".join(summary_parts),
            border_style=border_style,
        ))

        if not verification.issues:
            return

        # Show detailed issue table (limit to 30 rows)
        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("卷", style="dim", max_width=12)
        table.add_column("章节", style="cyan", max_width=22)
        table.add_column("问题", style="red", max_width=14)
        table.add_column("详情", style="dim", max_width=40)

        for issue in verification.issues[:30]:
            issue_label = {
                "missing": "[red]缺失[/red]",
                "empty": "[red]空内容[/red]",
                "truncated": "[yellow]可能截断[/yellow]",
                "image_missing": "[yellow]图片缺失[/yellow]",
                "image_corrupt": "[yellow]图片损坏[/yellow]",
                "catalog_gap": "[red]目录缺章[/red]",
            }.get(issue.issue, issue.issue)

            table.add_row(
                issue.volume_name,
                f"{issue.chapter_index:03d}_{issue.chapter_title}" if issue.chapter_index else issue.chapter_title,
                issue_label,
                issue.detail,
            )

        self.console.print(table)

        if len(verification.issues) > 30:
            self.console.print(
                f"  [dim]... 还有 {len(verification.issues) - 30} 个问题未显示[/dim]"
            )

    @staticmethod
    def _rebuild_failed_from_verification(downloader, verification: VerificationResult):
        """Populate downloader.failed_chapters from verification issues for retry."""
        downloader.failed_chapters.clear()
        seen = set()
        for issue in verification.issues:
            if issue.chapter_url and issue.chapter_url not in seen:
                seen.add(issue.chapter_url)
                downloader.failed_chapters.append(
                    f"https://www.linovelib.com{issue.chapter_url}"
                )

    def _run_download(self, volumes: list[Volume], selected: set, novel_info,
                      browser_session: BrowserSession = None):
        self.console.print("\n[cyan]正在启动浏览器并登录...[/cyan]")

        owns_session = browser_session is None
        session = browser_session or self._new_browser_session()
        downloader = None
        try:
            session.start()

            if check_logged_in(session):
                self.console.print("[green]✓ 已处于登录状态（复用浏览器 profile）[/green]")
            elif self.config.has_credentials():
                self.console.print(f"[dim]正在登录 {self.config.username} ...[/dim]")
                login_ok, login_msg = login(session, self.config.username, self.config.password)
                if login_ok:
                    self.console.print(f"[green]✓ {login_msg}[/green]")
                else:
                    self.console.print(f"[yellow]⚠ {login_msg}[/yellow]")
                    if not Confirm.ask("是否继续尝试下载？（未登录可能无法获取内容）", default=False):
                        return
            else:
                self.console.print("[dim]未设置账号，跳过登录[/dim]")

            report_lines = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=self.console,
            ) as progress:
                def progress_cb(msg: str):
                    report_lines.append(msg)
                    progress.update(task_id, description=msg[:80], advance=1)

                session.progress_callback = progress_cb
                downloader = Downloader(
                    output_dir=self.config.output_dir,
                    delay_range=self.config.delay_range,
                    progress_callback=progress_cb,
                )
                total_chapters = sum(
                    1 for v in volumes if v.name in selected
                    for c in v.chapters
                )
                task_id = progress.add_task(
                    f"[cyan]下载 {novel_info.title}...",
                    total=total_chapters,
                )
                result = downloader.download(
                    volumes, selected, novel_info, browser_session=session
                )

            self.console.print()
            self._show_result_panel(result)

            # ── Post-download verification ──────────────────────────────
            verification = None
            if downloader:
                with self.console.status("[cyan]正在校验下载完整性...[/cyan]"):
                    verification = downloader.verify_all(volumes, selected)
                self._show_verification_report(verification)

            # ── Retry loop driven by verification ───────────────────────
            retry_round = 0
            max_retries = 3
            while downloader and not (verification and verification.is_clean):
                retry_round += 1
                if retry_round > max_retries:
                    self.console.print(
                        f"[yellow]已达最大重试次数 ({max_retries})，停止重试[/yellow]"
                    )
                    break

                issue_count = verification.issue_count if verification else 0
                if not Confirm.ask(
                    f"\n[bold]发现 {issue_count} 个问题，是否重试修复？[/bold]",
                    default=True,
                ):
                    break

                # Rebuild failed_chapters from verification issues
                self._rebuild_failed_from_verification(downloader, verification)

                # Clean up problematic files so retry actually re-downloads them
                downloader.prepare_retry(verification)

                self.console.print(
                    f"\n[cyan]第 {retry_round} 轮重试中 "
                    f"({len(downloader.failed_chapters)} 章)...[/cyan]"
                )

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=self.console,
                ) as progress:
                    def progress_cb(msg: str):
                        progress.update(task_id, description=msg[:80], advance=1)

                    downloader.progress_callback = progress_cb
                    task_id = progress.add_task(
                        f"[cyan]重试 {novel_info.title}...",
                        total=max(len(downloader.failed_chapters), 1),
                    )
                    retry_result = downloader.download(
                        volumes, selected, novel_info, browser_session=session
                    )

                self.console.print()
                self.console.print(
                    f"[bold]第 {retry_round} 轮重试结果：[/bold]"
                    f"[green]成功 {retry_result.success}[/green]，"
                    f"[red]失败 {retry_result.failed}[/red]"
                )

                # Re-verify after retry
                with self.console.status("[cyan]重新校验...[/cyan]"):
                    verification = downloader.verify_all(volumes, selected)
                self._show_verification_report(verification)

            if Confirm.ask("是否导出为 EPUB?", default=False):
                with self.console.status("[cyan]正在生成 EPUB...[/cyan]"):
                    exporter = EpubExporter()
                    paths = exporter.export(novel_info, volumes, self.config.output_dir)
                if isinstance(paths, list):
                    for p in paths:
                        self.console.print(f"[green]✓ EPUB 已保存到: {p}[/green]")
                else:
                    self.console.print(f"[green]✓ EPUB 已保存到: {paths}[/green]")
        except Exception as e:
            self.console.print(f"[red]下载出错: {e}[/red]")
        finally:
            if owns_session:
                session.close()

    def _flow_verify(self):
        """Verify already-downloaded novel chapters without re-downloading."""
        output_dir = self.config.output_dir
        if not os.path.isdir(output_dir):
            self.console.print(f"[red]输出目录不存在: {output_dir}[/red]")
            return

        subdirs = [
            d for d in os.listdir(output_dir)
            if os.path.isdir(os.path.join(output_dir, d))
        ]
        if not subdirs:
            self.console.print("[yellow]输出目录为空[/yellow]")
            return

        self.console.print()
        for i, d in enumerate(subdirs, 1):
            txt_count = len([
                f for f in os.listdir(os.path.join(output_dir, d))
                if f.endswith(".txt")
            ])
            illus_dir = os.path.join(output_dir, d, "插图")
            img_count = len(os.listdir(illus_dir)) if os.path.isdir(illus_dir) else 0
            self.console.print(f"  [{i}] {d} ({txt_count} 章, {img_count} 图)")

        choice = Prompt.ask(
            "选择要校验的目录序号 ([green]A[/green]全部 / 1,3 / 2-5 / 0 返回)",
            default="A",
        )
        try:
            selected_dirs = self._parse_export_directory_selection(choice, subdirs)
        except ValueError:
            self.console.print("[red]无效选择[/red]")
            return

        if not selected_dirs:
            return

        # Build Volume/Chapter objects from directory structure
        volumes = []
        for directory in selected_dirs:
            vol = self._build_volume_from_directory(output_dir, directory)
            # Also add illustration chapter if illustration dir exists
            illus_dir = os.path.join(output_dir, directory, "插图")
            if os.path.isdir(illus_dir) and os.listdir(illus_dir):
                vol.chapters.append(Chapter(
                    index=0,
                    url="",
                    title="插图",
                    is_illustration=True,
                    volume_name=directory,
                ))
            volumes.append(vol)

        selected_names = set(selected_dirs)

        with self.console.status("[cyan]正在校验...[/cyan]"):
            downloader = Downloader(output_dir=output_dir)
            verification = downloader.verify_all(volumes, selected_names)

        self._show_verification_report(verification)

        if not verification.is_clean:
            self.console.print()
            self.console.print(
                "[dim]提示: 使用主菜单 [2] 直接 URL 下载同一小说，[/dim]"
            )
            self.console.print(
                "[dim]下载器会自动跳过完整章节，仅修复有问题的部分[/dim]"
            )

    def _flow_export_epub(self):
        output_dir = self.config.output_dir
        if not os.path.isdir(output_dir):
            self.console.print(f"[red]输出目录不存在: {output_dir}[/red]")
            return

        subdirs = [
            d for d in os.listdir(output_dir)
            if os.path.isdir(os.path.join(output_dir, d))
        ]
        if not subdirs:
            self.console.print("[yellow]输出目录为空[/yellow]")
            return

        for i, d in enumerate(subdirs, 1):
            txt_count = len([
                f for f in os.listdir(os.path.join(output_dir, d))
                if f.endswith(".txt")
            ])
            self.console.print(f"  [{i}] {d} ({txt_count} 章节)")

        choice = Prompt.ask(
            "选择要导出的目录序号 ([green]A[/green]全部 / 1,3 / 2-5 / 0 返回)",
            default="1",
        )
        try:
            selected_dirs = self._parse_export_directory_selection(choice, subdirs)
        except ValueError:
            self.console.print("[red]无效选择[/red]")
            return

        if not selected_dirs:
            return

        novel_info, volumes = self._build_epub_export_from_directories(
            output_dir,
            selected_dirs,
        )

        with self.console.status("[cyan]正在生成 EPUB...[/cyan]"):
            exporter = EpubExporter()
            paths = exporter.export(novel_info, volumes, output_dir)
        if isinstance(paths, list):
            for p in paths:
                self.console.print(f"[green]✓ EPUB 已保存到: {p}[/green]")
        else:
            self.console.print(f"[green]✓ EPUB 已保存到: {paths}[/green]")

    def _parse_export_directory_selection(self, choice: str, subdirs: list[str]) -> list[str]:
        choice = choice.strip()
        if choice.upper() == "A":
            return list(subdirs)
        if choice == "0":
            return []

        selected = []
        seen = set()
        for token in choice.split(","):
            token = token.strip()
            if not token:
                continue

            if "-" in token:
                start_text, end_text = token.split("-", 1)
                start = int(start_text.strip())
                end = int(end_text.strip())
                if start > end:
                    raise ValueError("range start is greater than range end")
                indices = range(start, end + 1)
            else:
                indices = [int(token)]

            for index in indices:
                if index < 1 or index > len(subdirs):
                    raise ValueError("selection index out of range")
                name = subdirs[index - 1]
                if name not in seen:
                    selected.append(name)
                    seen.add(name)

        if not selected:
            raise ValueError("empty selection")
        return selected

    def _build_epub_export_from_directories(
        self,
        output_dir: str,
        selected_dirs: list[str],
    ) -> tuple[NovelInfo, list[Volume]]:
        title = (
            selected_dirs[0]
            if len(selected_dirs) == 1
            else self._derive_batch_epub_title(selected_dirs)
        )
        volumes = [
            self._build_volume_from_directory(output_dir, directory)
            for directory in selected_dirs
        ]
        return NovelInfo(title=title), volumes

    def _build_volume_from_directory(self, output_dir: str, directory: str) -> Volume:
        vol_path = os.path.join(output_dir, directory)
        vol = Volume(name=directory)
        for fname in sorted(os.listdir(vol_path)):
            if not fname.endswith(".txt"):
                continue
            name_no_ext, _ = os.path.splitext(fname)
            match = re.match(r"^(\d+)_(.+)$", name_no_ext)
            if match:
                idx = int(match.group(1))
                title = match.group(2)
            else:
                idx = len(vol.chapters) + 1
                title = name_no_ext
            vol.chapters.append(Chapter(
                index=idx,
                url="",
                title=title,
                is_illustration=False,
                volume_name=directory,
            ))
        return vol

    @staticmethod
    def _derive_batch_epub_title(selected_dirs: list[str]) -> str:
        common = os.path.commonprefix(selected_dirs).strip(" -_.")
        return common or "batch"

    def _flow_warmup_cloudflare(self):
        self.console.print("[cyan]正在打开 CloakBrowser 预热 Cloudflare 验证...[/cyan]")
        self.console.print()
        self.console.print("[bold]请按以下步骤操作：[/bold]")
        self.console.print("  1. 在弹出的 CloakBrowser 窗口中完成「验证您是真人」")
        self.console.print("  2. 验证通过后会继续导航到搜索页")
        self.console.print("  3. 完成后不要关闭浏览器窗口，程序会自动保存 profile")
        self.console.print("  4. [dim]最长等待 5 分钟[/dim]")
        self.console.print()

        session = BrowserSession(
            headless=False,
            anti_bot_mode="cloak",
            proxy=self.config.proxy,
            geoip=self.config.geoip,
            profile_dir=self.config.profile_dir,
        )
        try:
            session.start()
            session.navigate_with_challenge_retry(
                "https://www.linovelib.com", "warmup-home", timeout_ms=300000
            )
            self.console.print("[green]✓ 首页验证通过[/green]")

            session.page.goto(
                "https://www.linovelib.com/S6/", timeout=45000, wait_until="domcontentloaded"
            )
            try:
                session.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            if session.page_has_challenge():
                self.console.print("[yellow]搜索页仍需要验证，请在浏览器中完成...[/yellow]")
                if session.wait_for_challenge_clear("warmup-search"):
                    self.console.print("[green]✓ 搜索页验证通过[/green]")
                else:
                    self.console.print("[yellow]⚠ 搜索页验证超时，已保存当前 profile[/yellow]")
            else:
                self.console.print("[green]✓ 搜索页访问成功[/green]")

            self.console.print()
            self.console.print(f"[green]Profile 已保存到: {self.config.profile_dir}\\cloak[/green]")
            self.console.print("[dim]后续搜索可复用此 profile，减少验证频率[/dim]")
        finally:
            session.close()

    def _flow_settings(self):
        self.console.print()
        self.console.print("[bold]当前设置[/bold]")
        username = self.config.username or "(未设置)"
        password_hidden = "****" if self.config.password else "(未设置)"
        self.console.print(f"  [1] 账号: {username}")
        self.console.print(f"  [2] 密码: {password_hidden}")
        self.console.print(f"  [3] 输出目录: {self.config.output_dir}")
        self.console.print(f"  [4] 无头模式: {self.config.headless}")
        self.console.print(f"  [5] 反爬模式: {self.config.anti_bot_mode}")
        self.console.print(f"  [6] 浏览器档案目录: {self.config.profile_dir}")
        self.console.print(f"  [7] 代理: {self.config.proxy or '(未设置)'}")
        self.console.print(f"  [8] GeoIP: {self.config.geoip}")
        if self.config.has_credentials():
            self.console.print("  [9] [red]退出账号[/red]")
        self.console.print("  [W] [cyan]预热 Cloudflare 验证[/cyan]")
        self.console.print("  [0] 返回")
        self.console.print()

        choices = [str(i) for i in range(0, 9)]
        if self.config.has_credentials():
            choices.append("9")
        choices.append("W")
        sub = Prompt.ask("修改哪一项?", choices=choices, default="0")

        if sub == "1":
            self.config.username = Prompt.ask("新用户名/邮箱", default=self.config.username)
            self.console.print("[green]✓ 已更新[/green]")
        elif sub == "2":
            self.config.password = self._prompt_password("新密码")
            self.console.print("[green]✓ 已更新[/green]")
        elif sub == "3":
            self.config.output_dir = Prompt.ask("新输出目录", default=self.config.output_dir)
            self.console.print("[green]✓ 已更新[/green]")
        elif sub == "4":
            self.config.headless = not self.config.headless
            self.console.print(f"[green]✓ 无头模式已{'开启' if self.config.headless else '关闭'}[/green]")
        elif sub == "5":
            self.config.anti_bot_mode = Prompt.ask(
                "反爬模式",
                choices=["auto", "playwright", "cloak"],
                default=self.config.anti_bot_mode,
            )
            self.console.print("[green]✓ 已更新[/green]")
        elif sub == "6":
            self.config.profile_dir = Prompt.ask("浏览器档案目录", default=self.config.profile_dir)
            self.console.print("[green]✓ 已更新[/green]")
        elif sub == "7":
            self.config.proxy = Prompt.ask("代理 URL（留空关闭）", default=self.config.proxy)
            self.console.print("[green]✓ 已更新[/green]")
        elif sub == "8":
            self.config.geoip = not self.config.geoip
            self.console.print(f"[green]✓ GeoIP 已{'开启' if self.config.geoip else '关闭'}[/green]")
        elif sub == "9":
            if Confirm.ask("确认清除账号密码？", default=False):
                self.config.set_credentials("", "")
                self.console.print("[green]✓ 账号已清除[/green]")
        elif sub == "W":
            self._flow_warmup_cloudflare()
