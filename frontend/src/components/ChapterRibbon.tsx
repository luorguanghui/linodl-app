import { PAGE_DEFINITIONS, type PageKey } from "../app/AppRouter";

interface ChapterRibbonProps {
  currentPage: PageKey;
}

export function ChapterRibbon({ currentPage }: ChapterRibbonProps) {
  return (
    <section className="chapter-ribbon" aria-label="章节进度">
      <ol className="chapter-ribbon-list">
        {PAGE_DEFINITIONS.map((definition, index) => (
          <li
            className="chapter-bookmark"
            key={definition.key}
            aria-current={
              definition.key === currentPage ? "step" : undefined
            }
          >
            <span className="chapter-bookmark-index">
              CH.{String(index + 1).padStart(2, "0")}
            </span>
            <span className="chapter-bookmark-label">
              {definition.chapterLabel}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
