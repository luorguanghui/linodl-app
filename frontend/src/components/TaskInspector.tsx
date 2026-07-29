import { ClipboardList, Inbox } from "lucide-react";

import type { TaskDto, TaskStatus } from "../api/types";
import { useDesktopStore } from "../store/desktop";
import { EmptyState } from "./EmptyState";

const taskStatusLabels: Record<TaskStatus, string> = {
  queued: "已排队",
  waiting_for_profile: "等待档案",
  running: "进行中",
  waiting_for_verification: "等待验证",
  cancelling: "取消中",
  cancelled: "已取消",
  failed: "失败",
  completed: "已完成",
};

function statusTone(
  status: TaskStatus,
): "default" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (
    status === "waiting_for_profile" ||
    status === "waiting_for_verification"
  ) {
    return "warning";
  }
  return "default";
}

function progressPercent(progress: number): number {
  const normalized = progress <= 1 ? progress * 100 : progress;
  return Math.min(100, Math.max(0, Math.round(normalized)));
}

function canCancel(task: TaskDto): boolean {
  return ["queued", "waiting_for_profile", "running"].includes(task.status);
}

function verificationTarget(task: TaskDto): string {
  return task.input_snapshot?.url || "https://www.linovelib.com";
}

interface TaskInspectorProps {
  tasks?: TaskDto[];
}

export function TaskInspector({ tasks: tasksOverride }: TaskInspectorProps = {}) {
  useDesktopStore((state) => state.taskVersion);
  const tasks = tasksOverride ?? useDesktopStore.getState().tasks;
  const pendingCancellationIds = useDesktopStore(
    (state) => state.pendingCancellationIds,
  );
  const notice = useDesktopStore((state) => state.notice);
  const cancelTask = useDesktopStore((state) => state.cancelTask);
  const restartTask = useDesktopStore((state) => state.restartTask);
  const startManualVerification = useDesktopStore(
    (state) => state.startManualVerification,
  );
  const viewTaskResult = useDesktopStore((state) => state.viewTaskResult);

  return (
    <aside className="task-inspector" aria-label="任务检查器">
      <header className="task-inspector-header">
        <div>
          <h2 className="task-inspector-heading">
            <ClipboardList size={18} strokeWidth={1.8} aria-hidden="true" />
            任务检查器
          </h2>
          <p className="task-inspector-caption">跨页面保留的下载与校验进度</p>
        </div>
        <span className="task-count" aria-label={`${tasks.length} 个任务`}>
          {tasks.length}
        </span>
      </header>

      {notice ? (
        <div className="task-notice" role="alert">
          <strong>{notice.message}</strong>
          <span>{notice.action}</span>
        </div>
      ) : null}

      {tasks.length === 0 ? (
        <EmptyState
          compact
          icon={<Inbox size={21} strokeWidth={1.8} />}
          kicker="任务队列为空"
          title="还没有进行中的任务"
          detail="开始检索或采集后，进度会固定显示在这里。"
        />
      ) : (
        <ol className="task-list">
          {tasks.map((task) => {
            const percent = progressPercent(task.progress);
            const cancellationPending =
              pendingCancellationIds.includes(task.id);

            return (
              <li className="task-card" key={task.id}>
                <div className="task-card-head">
                  <div>
                    <p className="task-title">{task.title}</p>
                    {task.detail ? (
                      <p className="task-detail">{task.detail}</p>
                    ) : null}
                  </div>
                  <span
                    className="task-status"
                    data-tone={statusTone(task.status)}
                  >
                    {taskStatusLabels[task.status]}
                  </span>
                </div>

                <div className="task-progress-row">
                  <progress
                    className="task-progress"
                    max={100}
                    value={percent}
                    aria-label={`${task.title}进度`}
                  />
                  <p className="task-progress-label">{percent}%</p>
                </div>

                <div className="task-card-actions">
                  {canCancel(task) ? (
                    <button
                      className="task-action-button task-cancel-button"
                      type="button"
                      aria-label={`取消${task.title}`}
                      disabled={cancellationPending}
                      onClick={() => void cancelTask(task.id)}
                    >
                      {cancellationPending ? "正在取消" : "取消任务"}
                    </button>
                  ) : null}
                  {task.status === "waiting_for_verification" ? (
                    <button
                      className="task-action-button"
                      type="button"
                      onClick={() =>
                        void startManualVerification(verificationTarget(task))
                      }
                    >
                      打开人工验证
                    </button>
                  ) : null}
                  {task.status === "failed" || task.status === "cancelled" ? (
                    <button
                      className="task-action-button"
                      type="button"
                      aria-label={`重新开始${task.title}`}
                      onClick={() => void restartTask(task.id)}
                    >
                      重新开始
                    </button>
                  ) : null}
                  {task.status === "completed" ? (
                    <button
                      className="task-action-button"
                      type="button"
                      aria-label={`查看${task.title}结果`}
                      onClick={() => viewTaskResult(task.id)}
                    >
                      查看结果
                    </button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}
