import { BadgeCheck, FolderOpen, ScanSearch } from "lucide-react";
import { useEffect, useState } from "react";

import type { ArchiveDto, OperationDto } from "../../api/types";
import { useDesktopStore } from "../../store/desktop";
import "../utility.css";

interface VerificationIssue {
  volume_name?: string;
  chapter_index?: number;
  chapter_title?: string;
  issue?: string;
  detail?: string;
}

interface VerificationSummary {
  total_expected?: number;
  complete?: number;
  issue_count?: number;
  is_clean?: boolean;
  issues?: VerificationIssue[];
}

export interface VerifyModel {
  archives: ArchiveDto[];
  outputDir: string;
  loading?: boolean;
  operation?: OperationDto;
  verification?: VerificationSummary;
  loadArchives(): void | Promise<void>;
  chooseDirectory(): string | null | Promise<string | null>;
  startVerify(archiveId: string): void | Promise<void>;
}

interface VerifyPageProps {
  model?: VerifyModel;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function verificationFrom(operation?: OperationDto): VerificationSummary | undefined {
  if (!operation || operation.status !== "completed" || !isRecord(operation.result)) {
    return undefined;
  }
  return operation.result as VerificationSummary;
}

function ConnectedVerifyPage() {
  const archives = useDesktopStore((state) => state.archives);
  const outputDir = useDesktopStore(
    (state) => state.settings.output_dir ?? "",
  );
  const loading = useDesktopStore((state) => state.archivesLoading);
  const operationId = useDesktopStore(
    (state) => state.activeVerifyOperationId,
  );
  const operation = useDesktopStore((state) =>
    operationId ? state.operations[operationId] : undefined,
  );
  const loadArchives = useDesktopStore((state) => state.loadArchives);
  const chooseDirectory = useDesktopStore((state) => state.chooseDirectory);
  const startVerify = useDesktopStore((state) => state.startVerify);

  return (
    <VerifyView
      model={{
        archives,
        outputDir,
        loading,
        operation,
        verification: verificationFrom(operation),
        loadArchives,
        chooseDirectory,
        startVerify,
      }}
    />
  );
}

function VerifyView({ model }: { model: VerifyModel }) {
  const [selectedArchiveId, setSelectedArchiveId] = useState("");
  const [directory, setDirectory] = useState(model.outputDir);
  const verification = model.verification;
  const issues = verification?.issues ?? [];

  useEffect(() => {
    void model.loadArchives();
  }, [model.loadArchives]);

  useEffect(() => {
    setDirectory(model.outputDir);
  }, [model.outputDir]);

  async function chooseDirectory() {
    const selected = await model.chooseDirectory();
    if (selected) setDirectory(selected);
  }

  return (
    <section className="utility-page" aria-label="内容校验工具">
      <div className="utility-card">
        <header className="utility-card-heading">
          <div>
            <h2>
              <ScanSearch size={18} aria-hidden="true" />
              选择校验范围
            </h2>
            <p>归档扫描仍以设置中保存的输出目录为安全边界。</p>
          </div>
        </header>
        <div className="utility-directory-row">
          <label className="utility-field">
            <span>输出目录</span>
            <input aria-label="校验目录" value={directory} readOnly />
          </label>
          <button
            className="utility-button"
            type="button"
            onClick={() => void chooseDirectory()}
          >
            <FolderOpen size={16} aria-hidden="true" />
            选择目录
          </button>
          <button
            className="utility-button"
            type="button"
            onClick={() => void model.loadArchives()}
          >
            重新扫描
          </button>
        </div>

        {directory !== model.outputDir ? (
          <p className="utility-note" role="status">
            请先在设置页保存这个目录，再重新扫描归档。
          </p>
        ) : null}

        {model.archives.length === 0 ? (
          <p className="utility-empty">
            {model.loading ? "正在扫描归档…" : "没有可校验的归档。"}
          </p>
        ) : (
          <ul className="verification-archive-list">
            {model.archives.map((archive) => (
              <li className="verification-archive-row" key={archive.id}>
                <label>
                  <input
                    type="radio"
                    name="verify-archive"
                    aria-label={`${archive.title}，${archive.volume_count} 卷，${archive.chapter_count} 章`}
                    checked={selectedArchiveId === archive.id}
                    onChange={() => setSelectedArchiveId(archive.id)}
                  />
                  <span className="archive-copy">
                    <strong className="archive-title">{archive.title}</strong>
                    <span className="archive-path">{archive.path}</span>
                  </span>
                  <span className="archive-counts">
                    <span>{archive.chapter_count} 章</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}

        <footer className="utility-options">
          <p className="utility-note">
            校验进度会同步保留在右侧任务检查器中。
          </p>
          <button
            className="utility-button is-primary"
            type="button"
            disabled={!selectedArchiveId}
            onClick={() => void model.startVerify(selectedArchiveId)}
          >
            <BadgeCheck size={16} aria-hidden="true" />
            开始校验
          </button>
        </footer>
      </div>

      {verification ? (
        <div className="utility-card" aria-live="polite">
          <header className="utility-card-heading">
            <h2>校验结果</h2>
            <p>{verification.is_clean ? "全部通过" : `发现 ${verification.issue_count ?? issues.length} 项问题`}</p>
          </header>
          <div className="verification-summary">
            <div className="verification-stat">
              <strong>
                {verification.complete ?? 0} / {verification.total_expected ?? 0}
              </strong>
              <span>完整章节</span>
            </div>
            <div className="verification-stat">
              <strong>{verification.issue_count ?? issues.length}</strong>
              <span>待处理问题</span>
            </div>
            <div className="verification-stat">
              <strong>{verification.is_clean ? "通过" : "需处理"}</strong>
              <span>归档状态</span>
            </div>
          </div>
          {issues.length ? (
            <ul className="verification-issue-list">
              {issues.map((issue, index) => (
                <li
                  className="verification-issue"
                  key={`${issue.volume_name}-${issue.chapter_index}-${index}`}
                >
                  <strong>{issue.chapter_title || "未命名章节"}</strong>
                  <p className="verification-issue-meta">
                    {issue.volume_name || "未分卷"} · 第 {issue.chapter_index ?? "?"} 章 · {issue.issue || "异常"}
                  </p>
                  <p>{issue.detail || "请检查对应章节文件。"}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="utility-note">没有发现缺章、空章或损坏文件。</p>
          )}
        </div>
      ) : model.operation ? (
        <div className="utility-card" aria-live="polite">
          <p className="utility-note">
            {model.operation.status === "failed"
              ? model.operation.error || "校验失败。"
              : "正在校验，详细进度请查看任务检查器。"}
          </p>
        </div>
      ) : null}
    </section>
  );
}

export function VerifyPage({ model }: VerifyPageProps) {
  return model ? <VerifyView model={model} /> : <ConnectedVerifyPage />;
}
