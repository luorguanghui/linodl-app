import { useEffect, useState } from "react";

import { AppErrorBoundary } from "../components/AppErrorBoundary";
import { BookRail } from "../components/BookRail";
import { ChapterRibbon } from "../components/ChapterRibbon";
import { CommandDeck } from "../components/CommandDeck";
import { TaskInspector } from "../components/TaskInspector";
import { desktopApi } from "../api/desktop";
import { startPolling, stopPolling } from "../store/desktop";
import { AppRouter, type PageKey } from "./AppRouter";

export function DesktopShell() {
  const [currentPage, setCurrentPage] = useState<PageKey>("workbench");
  const [confirmClose, setConfirmClose] = useState(false);

  useEffect(() => {
    startPolling();
    return stopPolling;
  }, []);

  useEffect(() => {
    window.linodlConfirmClose = () => setConfirmClose(true);
    return () => {
      delete window.linodlConfirmClose;
    };
  }, []);

  return (
    <div className="desktop-shell">
      <BookRail currentPage={currentPage} onNavigate={setCurrentPage} />

      <div className="desktop-main">
        <CommandDeck currentPage={currentPage} />

        <main className="workspace-grid" aria-label="轻小说资料工作区">
          <section className="workspace-stage" aria-label="当前页面">
            <ChapterRibbon currentPage={currentPage} />
            <AppErrorBoundary resetKey={currentPage}>
              <AppRouter page={currentPage} />
            </AppErrorBoundary>
          </section>

          <TaskInspector
            onViewResult={(kind) =>
              setCurrentPage(
                kind === "verify"
                  ? "validation"
                  : kind === "export"
                    ? "catalog"
                    : "workbench",
              )
            }
          />
        </main>
      </div>

      {confirmClose ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="确认退出"
          className="close-confirmation"
        >
          <h2>仍有任务正在运行</h2>
          <p>现在退出会中断这些任务。</p>
          <button type="button" onClick={() => setConfirmClose(false)}>
            继续等待
          </button>
          <button type="button" onClick={() => void desktopApi.forceClose()}>
            确认退出
          </button>
        </div>
      ) : null}
    </div>
  );
}
