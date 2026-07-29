import { Archive, ExternalLink, FileArchive } from "lucide-react";
import { useEffect, useState } from "react";

import type { ArchiveDto, OperationDto } from "../../api/types";
import { useDesktopStore } from "../../store/desktop";
import "../utility.css";

export interface ArchiveModel {
  archives: ArchiveDto[];
  loading?: boolean;
  exportOperation?: OperationDto;
  loadArchives(): void | Promise<void>;
  startExport(archiveId: string, perVolume: boolean): void | Promise<void>;
  openDirectory(path: string): void | Promise<void>;
}

interface ArchivePageProps {
  model?: ArchiveModel;
}

function ConnectedArchivePage() {
  const archives = useDesktopStore((state) => state.archives);
  const loading = useDesktopStore((state) => state.archivesLoading);
  const operationId = useDesktopStore(
    (state) => state.activeExportOperationId,
  );
  const exportOperation = useDesktopStore((state) =>
    operationId ? state.operations[operationId] : undefined,
  );
  const loadArchives = useDesktopStore((state) => state.loadArchives);
  const startExport = useDesktopStore((state) => state.startExport);
  const openDirectory = useDesktopStore((state) => state.openDirectory);

  return (
    <ArchiveView
      model={{
        archives,
        loading,
        exportOperation,
        loadArchives,
        startExport,
        openDirectory,
      }}
    />
  );
}

function exportPaths(operation?: OperationDto): string[] {
  if (!operation || operation.status !== "completed") return [];
  if (typeof operation.result === "string") return [operation.result];
  return Array.isArray(operation.result)
    ? operation.result.filter(
        (path): path is string => typeof path === "string",
      )
    : [];
}

function ArchiveView({ model }: { model: ArchiveModel }) {
  const [perVolume, setPerVolume] = useState(true);
  const paths = exportPaths(model.exportOperation);

  useEffect(() => {
    void model.loadArchives();
  }, [model.loadArchives]);

  return (
    <section className="utility-page" aria-label="归档与导出">
      <div className="utility-card">
        <header className="utility-card-heading">
          <div>
            <h2>
              <Archive size={18} aria-hidden="true" />
              本地归档
            </h2>
            <p>只列出设置中输出目录的直接子目录。</p>
          </div>
          <button
            className="utility-button"
            type="button"
            onClick={() => void model.loadArchives()}
          >
            刷新归档
          </button>
        </header>

        {model.archives.length === 0 ? (
          <p className="utility-empty">
            {model.loading ? "正在扫描归档…" : "输出目录中还没有可用归档。"}
          </p>
        ) : (
          <ul className="archive-list">
            {model.archives.map((archive) => (
              <li className="archive-row" key={archive.id}>
                <div className="archive-copy">
                  <h3 className="archive-title">{archive.title}</h3>
                  <p className="archive-path">{archive.path}</p>
                </div>
                <div className="archive-counts" aria-label={`${archive.title}统计`}>
                  <span>{archive.volume_count} 卷</span>
                  <span>{archive.chapter_count} 章</span>
                </div>
                <div className="archive-actions">
                  <button
                    className="utility-button"
                    type="button"
                    aria-label={`打开${archive.title}目录`}
                    onClick={() => void model.openDirectory(archive.path)}
                  >
                    <ExternalLink size={15} aria-hidden="true" />
                    打开
                  </button>
                  <button
                    className="utility-button is-primary"
                    type="button"
                    aria-label={`导出${archive.title}`}
                    onClick={() =>
                      void model.startExport(archive.id, perVolume)
                    }
                  >
                    <FileArchive size={15} aria-hidden="true" />
                    导出 EPUB
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <footer className="utility-options">
          <label className="utility-checkbox">
            <input
              type="checkbox"
              checked={perVolume}
              onChange={(event) => setPerVolume(event.target.checked)}
            />
            分卷导出
          </label>
          <p className="utility-note">
            取消勾选会把所选归档合并为单个 EPUB。
          </p>
        </footer>
      </div>

      {model.exportOperation ? (
        <div className="utility-card" aria-live="polite">
          <header className="utility-card-heading">
            <h2>导出结果</h2>
            <p>{model.exportOperation.detail}</p>
          </header>
          {paths.length ? (
            <ul className="verification-issue-list">
              {paths.map((path) => (
                <li className="verification-issue" key={path}>
                  <p className="archive-path">{path}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="utility-note">
              {model.exportOperation.status === "failed"
                ? model.exportOperation.error || "导出失败。"
                : "导出进度会持续显示在任务检查器中。"}
            </p>
          )}
        </div>
      ) : null}
    </section>
  );
}

export function ArchivePage({ model }: ArchivePageProps) {
  return model ? <ArchiveView model={model} /> : <ConnectedArchivePage />;
}
