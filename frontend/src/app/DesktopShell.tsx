import { useEffect, useState } from "react";

import { AppErrorBoundary } from "../components/AppErrorBoundary";
import { BookRail } from "../components/BookRail";
import { ChapterRibbon } from "../components/ChapterRibbon";
import { CommandDeck } from "../components/CommandDeck";
import { TaskInspector } from "../components/TaskInspector";
import { startPolling, stopPolling } from "../store/desktop";
import { AppRouter, type PageKey } from "./AppRouter";

export function DesktopShell() {
  const [currentPage, setCurrentPage] = useState<PageKey>("workbench");

  useEffect(() => {
    startPolling();
    return stopPolling;
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

          <TaskInspector />
        </main>
      </div>
    </div>
  );
}
