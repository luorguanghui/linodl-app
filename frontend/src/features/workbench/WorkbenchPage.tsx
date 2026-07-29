import { BookOpenCheck, LoaderCircle, Search, TriangleAlert } from "lucide-react";
import { useState } from "react";

import type { BridgeErrorDto, OperationDto } from "../../api/types";
import {
  useDesktopStore,
  type DesktopState,
  type WorkbenchOperationKind,
} from "../../store/desktop";
import { NovelResults, type NovelResult } from "./NovelResults";
import { NovelSummary, type CatalogNovel } from "./NovelSummary";
import { VolumeList, type CatalogVolume } from "./VolumeList";
import "./workbench.css";

export type WorkbenchViewState =
  | "empty"
  | "searching"
  | "results"
  | "catalog"
  | "downloading"
  | "completed"
  | "failed";

interface WorkbenchFailure {
  message: string;
  action: string;
  detail?: string;
}

interface DownloadSummary {
  novel_title?: string;
  success?: number;
  skipped?: number;
  failed?: number;
  output_dir?: string;
}

export interface WorkbenchModel {
  state: WorkbenchViewState;
  operationKind?: WorkbenchOperationKind | null;
  results?: NovelResult[];
  catalogOperationId?: string;
  novel?: CatalogNovel;
  volumes?: CatalogVolume[];
  selectedVolumes?: string[];
  download?: DownloadSummary;
  error?: WorkbenchFailure;
  search(query: string): void | Promise<void>;
  loadCatalog(url: string): void | Promise<void>;
  startDownload(
    catalogOperationId: string,
    selectedVolumes: string[],
  ): void | Promise<void>;
  toggleVolume(volumeName: string): void;
}

interface WorkbenchPageProps {
  model?: WorkbenchModel;
}

type WorkbenchSnapshot = Pick<
  DesktopState,
  | "operations"
  | "activeOperationId"
  | "activeOperationKind"
  | "selectedVolumes"
  | "notice"
>;

const invalidSourceMessage =
  "目前仅支持 linovelib.com 的作品或目录链接。";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function toNovel(value: unknown): CatalogNovel | null {
  if (!isRecord(value)) return null;
  return {
    novel_id: text(value.novel_id),
    title: text(value.title),
    author: text(value.author),
    description: text(value.description),
    catalog_url: text(value.catalog_url),
    chapter_count: count(value.chapter_count),
    word_count: text(value.word_count),
    tags: stringList(value.tags),
  };
}

function toNovelResults(value: unknown): NovelResult[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const novel = toNovel(item);
    if (!novel) return [];
    const catalogUrl =
      novel.catalog_url ||
      (novel.novel_id
        ? `https://www.linovelib.com/novel/${novel.novel_id}/catalog`
        : "");
    if (!catalogUrl) return [];
    return [{ ...novel, catalog_url: catalogUrl }];
  });
}

function toVolumes(value: unknown): CatalogVolume[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!isRecord(item) || !text(item.name)) return [];
    return [
      {
        name: text(item.name),
        text_count: count(item.text_count),
        illus_count: count(item.illus_count),
      },
    ];
  });
}

function toDownloadSummary(value: unknown): DownloadSummary | undefined {
  const candidate = Array.isArray(value) ? value[0] : value;
  if (!isRecord(candidate)) return undefined;
  return {
    novel_title: text(candidate.novel_title),
    success: count(candidate.success),
    skipped: count(candidate.skipped),
    failed: count(candidate.failed),
    output_dir: text(candidate.output_dir),
  };
}

function operationFailure(operation: OperationDto): WorkbenchFailure {
  const labels: Record<WorkbenchOperationKind, string> = {
    search: "作品检索失败。",
    catalog: "目录读取失败。",
    download: "下载未能完成。",
  };
  const kind = isWorkbenchOperationKind(operation.kind)
    ? operation.kind
    : "search";
  return {
    message: labels[kind],
    action: "查看任务状态，调整输入后重试。",
    detail: operation.error || operation.detail || undefined,
  };
}

function noticeFailure(notice: BridgeErrorDto): WorkbenchFailure {
  return {
    message: notice.message,
    action: notice.action,
  };
}

function isWorkbenchOperationKind(
  value: string | null | undefined,
): value is WorkbenchOperationKind {
  return value === "search" || value === "catalog" || value === "download";
}

export function deriveWorkbenchModel(
  snapshot: WorkbenchSnapshot,
  actions: Pick<
    WorkbenchModel,
    "search" | "loadCatalog" | "startDownload" | "toggleVolume"
  >,
): WorkbenchModel {
  const operation = snapshot.activeOperationId
    ? snapshot.operations[snapshot.activeOperationId]
    : undefined;
  const operationKind = isWorkbenchOperationKind(operation?.kind)
    ? operation.kind
    : snapshot.activeOperationKind;

  if (snapshot.notice) {
    return {
      ...actions,
      state: "failed",
      operationKind,
      error: noticeFailure(snapshot.notice),
    };
  }

  if (!operation) {
    if (operationKind === "download") {
      return { ...actions, state: "downloading", operationKind };
    }
    if (operationKind === "search" || operationKind === "catalog") {
      return { ...actions, state: "searching", operationKind };
    }
    return { ...actions, state: "empty", operationKind: null };
  }

  if (operation.status === "failed" || operation.status === "cancelled") {
    return {
      ...actions,
      state: "failed",
      operationKind,
      error: operationFailure(operation),
    };
  }

  if (operation.status === "running") {
    return {
      ...actions,
      state: operationKind === "download" ? "downloading" : "searching",
      operationKind,
    };
  }

  if (operationKind === "search") {
    return {
      ...actions,
      state: "results",
      operationKind,
      results: toNovelResults(operation.result),
    };
  }

  if (operationKind === "catalog") {
    const catalog = Array.isArray(operation.result) ? operation.result : [];
    return {
      ...actions,
      state: "catalog",
      operationKind,
      catalogOperationId: operation.id,
      volumes: toVolumes(catalog[0]),
      novel: toNovel(catalog[1]) ?? { title: "未命名作品" },
      selectedVolumes: snapshot.selectedVolumes,
    };
  }

  return {
    ...actions,
    state: "completed",
    operationKind,
    download: toDownloadSummary(operation.result),
  };
}

function ConnectedWorkbenchPage() {
  const operations = useDesktopStore((state) => state.operations);
  const activeOperationId = useDesktopStore(
    (state) => state.activeOperationId,
  );
  const activeOperationKind = useDesktopStore(
    (state) => state.activeOperationKind,
  );
  const selectedVolumes = useDesktopStore((state) => state.selectedVolumes);
  const notice = useDesktopStore((state) => state.notice);
  const search = useDesktopStore((state) => state.search);
  const loadCatalog = useDesktopStore((state) => state.loadCatalog);
  const startDownload = useDesktopStore((state) => state.startDownload);
  const toggleVolume = useDesktopStore((state) => state.toggleVolume);

  const model = deriveWorkbenchModel(
    {
      operations,
      activeOperationId,
      activeOperationKind,
      selectedVolumes,
      notice,
    },
    { search, loadCatalog, startDownload, toggleVolume },
  );

  return <WorkbenchView model={model} />;
}

function classifyInput(value: string): "empty" | "query" | "url" | "invalid_url" {
  const trimmed = value.trim();
  if (!trimmed) return "empty";
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      const host = parsed.hostname.toLowerCase();
      return host === "linovelib.com" || host.endsWith(".linovelib.com")
        ? "url"
        : "invalid_url";
    }
  } catch {
    return "query";
  }
  return "query";
}

function WorkbenchView({ model }: { model: WorkbenchModel }) {
  const [command, setCommand] = useState("");
  const [inputError, setInputError] = useState("");
  const busy = model.state === "searching" || model.state === "downloading";

  function submitCommand() {
    const value = command.trim();
    const kind = classifyInput(value);
    if (kind === "empty") {
      setInputError("请输入作品名称或目录 URL。");
      return;
    }
    if (kind === "invalid_url") {
      setInputError(invalidSourceMessage);
      return;
    }
    setInputError("");
    if (kind === "url") {
      void model.loadCatalog(value);
      return;
    }
    void model.search(value);
  }

  return (
    <div className="workbench">
      <form
        className="workbench-command"
        aria-label="查找作品或目录"
        onSubmit={(event) => {
          event.preventDefault();
          submitCommand();
        }}
      >
        <label htmlFor="workbench-command-input">作品名或目录地址</label>
        <div className="workbench-command-row">
          <span className="workbench-command-icon" aria-hidden="true">
            <Search size={19} strokeWidth={1.8} />
          </span>
          <input
            id="workbench-command-input"
            value={command}
            onChange={(event) => setCommand(event.target.value)}
            placeholder="输入作品名，或粘贴 linovelib.com 目录地址"
            disabled={busy}
          />
          <button type="submit" disabled={busy}>
            查找作品
          </button>
        </div>
        <p
          className={`workbench-input-note${inputError ? " is-error" : ""}`}
          role={inputError ? "alert" : undefined}
        >
          {inputError || "一个入口完成检索与目录读取。"}
        </p>
      </form>

      <div className="workbench-body" data-state={model.state}>
        {model.state === "empty" ? <WorkbenchEmpty /> : null}
        {model.state === "searching" ? (
          <WorkbenchProgress
            title={
              model.operationKind === "catalog"
                ? "正在整理作品目录"
                : "正在检索作品"
            }
            detail={
              model.operationKind === "catalog"
                ? "目录返回后会直接进入卷册选择。"
                : "候选作品返回后会按书目逐行列出。"
            }
          />
        ) : null}
        {model.state === "results" ? (
          <NovelResults
            results={model.results ?? []}
            onOpenCatalog={(url) => void model.loadCatalog(url)}
          />
        ) : null}
        {model.state === "catalog" && model.novel ? (
          <div className="catalog-workspace">
            <NovelSummary novel={model.novel} />
            <div className="catalog-volume-column">
              <VolumeList
                volumes={model.volumes ?? []}
                selectedVolumes={model.selectedVolumes ?? []}
                onToggle={model.toggleVolume}
              />
              <footer className="catalog-actions">
                <p>
                  已选择 <strong>{model.selectedVolumes?.length ?? 0}</strong>{" "}
                  卷
                </p>
                <button
                  type="button"
                  disabled={(model.selectedVolumes?.length ?? 0) === 0}
                  onClick={() =>
                    void model.startDownload(
                      model.catalogOperationId ?? "",
                      model.selectedVolumes ?? [],
                    )
                  }
                >
                  下载所选
                </button>
              </footer>
            </div>
          </div>
        ) : null}
        {model.state === "downloading" ? (
          <WorkbenchProgress
            title="正在下载所选卷册"
            detail="任务进度会同时保留在右侧检查器中，可以继续查看其他章节。"
          />
        ) : null}
        {model.state === "completed" ? (
          <CompletedState summary={model.download} />
        ) : null}
        {model.state === "failed" ? (
          <FailureState error={model.error} />
        ) : null}
      </div>
    </div>
  );
}

function WorkbenchEmpty() {
  return (
    <section className="workbench-empty">
      <span className="workbench-state-icon" aria-hidden="true">
        <BookOpenCheck size={22} strokeWidth={1.8} />
      </span>
      <div>
        <p className="workbench-eyebrow">从一本书开始</p>
        <h2>检索作品，再选择要整理的卷册</h2>
        <p>
          输入书名会打开候选书架；粘贴受支持的目录地址则会直接读取卷册。
        </p>
      </div>
    </section>
  );
}

function WorkbenchProgress({
  title,
  detail,
}: {
  title: string;
  detail: string;
}) {
  return (
    <section className="workbench-progress" aria-live="polite">
      <span className="workbench-state-icon is-spinning" aria-hidden="true">
        <LoaderCircle size={22} strokeWidth={1.8} />
      </span>
      <div>
        <p className="workbench-eyebrow">工作台处理中</p>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
    </section>
  );
}

function CompletedState({ summary }: { summary?: DownloadSummary }) {
  return (
    <section className="workbench-completed" aria-live="polite">
      <span className="workbench-state-icon" aria-hidden="true">
        <BookOpenCheck size={22} strokeWidth={1.8} />
      </span>
      <div>
        <p className="workbench-eyebrow">整理完成</p>
        <h2>{summary?.novel_title || "所选卷册已下载"}</h2>
        <p>
          成功 {summary?.success ?? 0} · 跳过 {summary?.skipped ?? 0} · 失败{" "}
          {summary?.failed ?? 0}
        </p>
        {summary?.output_dir ? (
          <p className="workbench-output">输出位置：{summary.output_dir}</p>
        ) : null}
      </div>
    </section>
  );
}

function FailureState({ error }: { error?: WorkbenchFailure }) {
  return (
    <section className="workbench-failure" role="alert">
      <span className="workbench-state-icon" aria-hidden="true">
        <TriangleAlert size={22} strokeWidth={1.8} />
      </span>
      <div>
        <p className="workbench-eyebrow">需要处理</p>
        <h2>{error?.message || "任务未能完成。"}</h2>
        <p>{error?.action || "检查输入后重试。"}</p>
        {error?.detail ? (
          <details>
            <summary>技术详情</summary>
            <pre>{error.detail}</pre>
          </details>
        ) : null}
      </div>
    </section>
  );
}

export function WorkbenchPage({ model }: WorkbenchPageProps) {
  return model ? <WorkbenchView model={model} /> : <ConnectedWorkbenchPage />;
}
