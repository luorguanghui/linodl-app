import { BookOpen, BookOpenText } from "lucide-react";

import { AppButton } from "../../components/AppButton";

export interface NovelResult {
  novel_id?: string;
  title: string;
  author?: string;
  description?: string;
  catalog_url: string;
}

interface NovelResultsProps {
  results: NovelResult[];
  onOpenCatalog: (url: string) => void;
}

export function NovelResults({
  results,
  onOpenCatalog,
}: NovelResultsProps) {
  return (
    <section className="novel-results" aria-labelledby="result-heading">
      <header className="workbench-section-heading">
        <div>
          <p className="workbench-eyebrow">检索书架</p>
          <h2 id="result-heading">找到 {results.length} 部作品</h2>
        </div>
        <span className="workbench-count">{results.length}</span>
      </header>

      {results.length === 0 ? (
        <p className="workbench-empty-copy">
          没有找到匹配作品。换一个书名或作者名再试一次。
        </p>
      ) : (
        <ol className="novel-result-list">
          {results.map((novel, index) => (
            <li
              className="novel-result-row"
              key={novel.novel_id || novel.catalog_url || `${novel.title}-${index}`}
            >
              <span className="novel-result-mark" aria-hidden="true">
                <BookOpen size={18} strokeWidth={1.7} />
              </span>
              <div className="novel-result-copy">
                <h3>{novel.title || "未命名作品"}</h3>
                <p className="novel-result-author">
                  {novel.author ? `作者 · ${novel.author}` : "作者信息暂缺"}
                </p>
                <p className="novel-result-description">
                  {novel.description || "该作品暂无简介。"}
                </p>
              </div>
              <AppButton
                className="workbench-secondary-action"
                variant="secondary"
                icon={BookOpenText}
                onClick={() => onOpenCatalog(novel.catalog_url)}
                aria-label={`读取《${novel.title}》目录`}
              >
                读取目录
              </AppButton>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
