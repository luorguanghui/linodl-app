"""Entry point: python -m linodl [options]."""

from __future__ import annotations

import sys

from .cli.app import App
from .config.manager import ConfigManager
from .core.browser import BrowserSession


def main():
    config = ConfigManager()
    debug = "--debug" in sys.argv
    if debug:
        sys.argv.remove("--debug")

    if len(sys.argv) > 1:
        _batch_mode(config, debug)
    else:
        App(config, debug=debug).run()


def _batch_mode(config: ConfigManager, debug: bool = False):
    """Handle command-line arguments for scripting."""
    from rich.console import Console

    from .core.auth import check_logged_in, login
    from .core.browser import BrowserSession
    from .core.catalog import fetch_catalog, parse_catalog
    from .core.downloader import Downloader
    from .core.search import SearchEngine

    console = Console()
    args = sys.argv[1:]
    search_term = None
    catalog_url = None
    volumes_arg = None
    no_login = False

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--search" and i + 1 < len(args):
            search_term = args[i + 1]
            i += 2
        elif arg == "--url" and i + 1 < len(args):
            catalog_url = args[i + 1]
            i += 2
        elif arg == "--volumes" and i + 1 < len(args):
            volumes_arg = args[i + 1]
            i += 2
        elif arg == "--no-login":
            no_login = True
            i += 1
        elif arg == "--output-dir" and i + 1 < len(args):
            config.output_dir = args[i + 1]
            i += 2
        elif arg == "--headed":
            config.headless = False
            i += 1
        elif arg == "--anti-bot" and i + 1 < len(args):
            config.anti_bot_mode = args[i + 1]
            i += 2
        elif arg == "--proxy" and i + 1 < len(args):
            config.proxy = args[i + 1]
            i += 2
        elif arg == "--warmup-cloudflare":
            _warmup_cloudflare(config, console)
            return
        else:
            i += 1

    if search_term:
        console.print(f"[cyan]搜索: {search_term}[/cyan]")
        try:
            with _new_session(config) as session:
                engine = SearchEngine(debug=debug, browser_session=session)
                novels = engine.search(search_term)
        except Exception as exc:
            console.print(f"[red]搜索失败: {exc}[/red]")
            return
        for idx, novel in enumerate(novels[:20], 1):
            console.print(
                f"  [{idx}] {novel.title} (ID: {novel.novel_id}) 作者: {novel.author or '-'}"
            )
        if not novels:
            console.print("[yellow]无结果[/yellow]")
        return

    if catalog_url:
        console.print(f"[cyan]获取目录: {catalog_url}[/cyan]")
        with _new_session(config) as session:
            html = fetch_catalog(catalog_url, browser_session=session)
            volumes, novel_info = parse_catalog(html)
            console.print(f"小说: {novel_info.title}, 作者: {novel_info.author or '-'}")
            console.print(f"共 {len(volumes)} 卷")

            if volumes_arg:
                indices = [int(x.strip()) for x in volumes_arg.split(",")]
                selected = {volumes[i - 1].name for i in indices if 1 <= i <= len(volumes)}
            else:
                selected = {v.name for v in volumes}
            console.print(f"选中: {', '.join(selected)}")

            if not no_login:
                if check_logged_in(session):
                    console.print("  [green]已处于登录状态（复用浏览器 profile）[/]")
                elif config.has_credentials():
                    ok, msg = login(session, config.username, config.password)
                    console.print(f"  {'[green]' if ok else '[yellow]'}{msg}[/]")
                else:
                    console.print("  [dim]未设置账号，跳过登录[/]")

            def report(msg):
                console.print(f"  {msg}")

            session.progress_callback = report
            downloader = Downloader(
                output_dir=config.output_dir,
                delay_range=config.delay_range,
                progress_callback=report,
            )
            result = downloader.download(volumes, selected, novel_info, browser_session=session)

        console.print(
            f"\n[green]完成! 成功: {result.success}, 跳过: {result.skipped}, 失败: {result.failed}[/green]"
        )
        console.print(f"输出: {result.output_dir}")
        if downloader.failed_chapters:
            console.print("[yellow]失败章节 URL：[/yellow]")
            for failed_url in downloader.failed_chapters[:20]:
                console.print(f"  {failed_url}")
        return

    console.print("[bold]linodl v2.1[/bold] - linovelib.com 小说下载器")
    console.print()
    console.print("用法: python -m linodl [选项]")
    console.print()
    console.print("选项:")
    console.print("  --search <关键词>          搜索小说")
    console.print("  --url <目录URL>            直接指定目录 URL 下载")
    console.print("  --volumes <1,3,5>          选择要下载的卷（逗号分隔）")
    console.print("  --output-dir <目录>        指定输出目录")
    console.print("  --no-login                 跳过登录")
    console.print("  --headed                   显示浏览器窗口")
    console.print("  --anti-bot auto|playwright|cloak   (默认: cloak)")
    console.print("  --proxy <URL>              设置 HTTP/SOCKS 代理")
    console.print("  --warmup-cloudflare        预热 CloakBrowser 绕过 Cloudflare 验证")
    console.print()
    console.print("无参数运行进入交互模式: python -m linodl")


def _warmup_cloudflare(config: ConfigManager, console):
    """Open a visible CloakBrowser so the user can complete Cloudflare verification
    once. The profile is then saved and reused by subsequent runs."""
    console.print("[cyan]正在打开 CloakBrowser 预热 Cloudflare 验证...[/cyan]")
    console.print()
    console.print("[bold]请按以下步骤操作：[/bold]")
    console.print("  1. 在弹出的 CloakBrowser 窗口中完成「验证您是真人」")
    console.print("  2. 验证通过后会继续导航到搜索页")
    console.print("  3. 完成后不要关闭浏览器窗口，程序会自动保存 profile")
    console.print("  4. [dim]最长等待 5 分钟[/dim]")
    console.print()

    session = BrowserSession(
        headless=False,
        anti_bot_mode="cloak",
        proxy=config.proxy,
        geoip=config.geoip,
        profile_dir=config.profile_dir,
    )
    try:
        session.start()
        session.navigate_with_challenge_retry(
            "https://www.linovelib.com", "warmup-home", timeout_ms=300000
        )
        console.print("[green]✓ 首页验证通过[/green]")

        session.page.goto(
            "https://www.linovelib.com/S6/", timeout=45000, wait_until="domcontentloaded"
        )
        try:
            session.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        if session.page_has_challenge():
            console.print("[yellow]搜索页仍需要验证，请在浏览器中完成...[/yellow]")
            if session.wait_for_challenge_clear("warmup-search"):
                console.print("[green]✓ 搜索页验证通过[/green]")
            else:
                console.print("[yellow]⚠ 搜索页验证超时，已保存当前 profile[/yellow]")
        else:
            console.print("[green]✓ 搜索页访问成功[/green]")

        console.print()
        console.print(f"[green]Profile 已保存到: {config.profile_dir}\\cloak[/green]")
        console.print("[dim]后续搜索可复用此 profile，减少验证频率[/dim]")
    finally:
        session.close()


def _new_session(config: ConfigManager) -> BrowserSession:
    return BrowserSession(
        headless=config.headless,
        anti_bot_mode=config.anti_bot_mode,
        proxy=config.proxy,
        geoip=config.geoip,
        profile_dir=config.profile_dir,
    )


if __name__ == "__main__":
    main()
