import { Layers3 } from "lucide-react";

import { getPageDefinition, type PageKey } from "../app/AppRouter";
import { useDesktopStore } from "../store/desktop";

interface CommandDeckProps {
  currentPage: PageKey;
}

export function CommandDeck({ currentPage }: CommandDeckProps) {
  const taskCount = useDesktopStore((state) => state.tasks.length);
  const definition = getPageDefinition(currentPage);

  return (
    <header className="command-deck">
      <div className="command-context">
        <span className="command-context-icon" aria-hidden="true">
          <Layers3 size={20} strokeWidth={1.8} />
        </span>
        <div>
          <p className="command-kicker">轻小说资料工作室</p>
          <p className="command-page">
            {definition.chapter} / {definition.label}
          </p>
        </div>
      </div>

      <div className="command-status" aria-label="任务概况">
        <span className="command-status-dot" aria-hidden="true" />
        <div className="command-status-copy">
          <p className="command-status-label">桌面任务</p>
          <p className="command-status-value">
            {taskCount > 0 ? `${taskCount} 项已记录` : "工作室已就绪"}
          </p>
        </div>
      </div>
    </header>
  );
}
