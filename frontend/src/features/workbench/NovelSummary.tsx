export interface CatalogNovel {
  novel_id?: string;
  title: string;
  author?: string;
  description?: string;
  catalog_url?: string;
  chapter_count?: number;
  word_count?: string;
  tags?: string[];
}

interface NovelSummaryProps {
  novel: CatalogNovel;
}

export function NovelSummary({ novel }: NovelSummaryProps) {
  const metadata = [
    novel.author ? `作者 · ${novel.author}` : null,
    novel.chapter_count ? `${novel.chapter_count} 章` : null,
    novel.word_count || null,
  ].filter(Boolean);

  return (
    <section className="novel-summary" aria-labelledby="catalog-novel-title">
      <p className="workbench-eyebrow">书目摘录</p>
      <h2 id="catalog-novel-title">{novel.title || "未命名作品"}</h2>
      {metadata.length > 0 ? (
        <p className="novel-summary-meta">{metadata.join(" / ")}</p>
      ) : null}
      <p className="novel-summary-description">
        {novel.description || "目录已读取，可以选择要整理的卷册。"}
      </p>
      {novel.tags && novel.tags.length > 0 ? (
        <ul className="novel-tag-list" aria-label="作品标签">
          {novel.tags.map((tag) => (
            <li key={tag}>{tag}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
