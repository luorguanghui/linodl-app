import { BookMarked } from "lucide-react";

import {
  PAGE_DEFINITIONS,
  type PageKey,
} from "../app/AppRouter";

interface BookRailProps {
  currentPage: PageKey;
  onNavigate: (page: PageKey) => void;
}

export function BookRail({ currentPage, onNavigate }: BookRailProps) {
  return (
    <aside className="book-rail">
      <div className="rail-brand">
        <span className="rail-brand-mark" aria-hidden="true">
          <BookMarked size={20} strokeWidth={1.8} />
        </span>
        <div className="rail-brand-copy">
          <p className="rail-brand-title">轻小说资料工作室</p>
          <p className="rail-brand-subtitle">linodl studio</p>
        </div>
      </div>

      <nav className="rail-navigation" aria-label="书脊导航">
        {PAGE_DEFINITIONS.map((definition, index) => {
          const Icon = definition.icon;
          const isCurrent = definition.key === currentPage;

          return (
            <button
              className="rail-nav-button"
              type="button"
              key={definition.key}
              aria-label={definition.label}
              aria-current={isCurrent ? "page" : undefined}
              title={definition.label}
              onClick={() => onNavigate(definition.key)}
            >
              <span className="rail-nav-icon" aria-hidden="true">
                <Icon size={19} strokeWidth={1.8} />
              </span>
              <span className="rail-nav-copy">
                <span className="rail-nav-label">{definition.label}</span>
                <span className="rail-nav-chapter">
                  CH.{String(index + 1).padStart(2, "0")}
                </span>
              </span>
            </button>
          );
        })}
      </nav>

      <p className="rail-footnote">资料留在本机 · 任务持续可见</p>
    </aside>
  );
}
