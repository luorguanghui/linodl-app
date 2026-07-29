import { create, type StateCreator } from "zustand";
import { createStore, type StoreApi } from "zustand/vanilla";

import { desktopApi, type DesktopApi } from "../api/desktop";
import type {
  BootstrapResponse,
  BridgeErrorDto,
  PollDto,
  PollResponse,
  TaskDto,
  OperationMapDto,
  DesktopSettingsDto,
  ProfileHealthDto,
} from "../api/types";

export type ProfileState = ProfileHealthDto;
export type WorkbenchOperationKind = "search" | "catalog" | "download";
type WriteGuard = () => boolean;

const allowWrites: WriteGuard = () => true;

export interface DesktopState {
  tasks: TaskDto[];
  taskVersion: number;
  operations: OperationMapDto;
  operationVersion: number;
  activeOperationId: string | null;
  activeOperationKind: WorkbenchOperationKind | null;
  selectedVolumes: string[];
  pendingCancellationIds: string[];
  pendingRestartIds: string[];
  profile: ProfileState;
  settings: DesktopSettingsDto;
  notice: BridgeErrorDto | null;
  /** Lifecycle callers pass a guard; direct callers omit it and own the request. */
  bootstrap(writeGuard?: WriteGuard): Promise<void>;
  /** Lifecycle callers pass a guard; direct callers omit it and own the request. */
  pollOnce(writeGuard?: WriteGuard): Promise<void>;
  search(query: string): Promise<void>;
  loadCatalog(url: string): Promise<void>;
  startDownload(catalogOperationId: string, selectedVolumes: string[]): Promise<void>;
  toggleVolume(volumeName: string): void;
  cancelTask(taskId: string): Promise<void>;
  restartTask(taskId: string): Promise<void>;
  focusTaskVerification(taskId: string): Promise<void>;
  checkProfile(): Promise<void>;
  startManualVerification(targetUrl: string): Promise<void>;
  viewTaskResult(taskId: string): boolean;
}

const unavailableNotice: BridgeErrorDto = {
  code: "DESKTOP_API_UNAVAILABLE",
  message: "桌面服务暂不可用。",
  action: "请稍后重试。",
};

function isBridgeError(
  response: PollResponse | BootstrapResponse | { ok: boolean },
): response is { ok: false; error: BridgeErrorDto } {
  return "ok" in response && response.ok === false;
}

function mergeSnapshot(snapshot: PollDto) {
  return (state: DesktopState) => ({
    taskVersion: snapshot.task_version,
    tasks: snapshot.tasks ?? state.tasks,
    operationVersion: snapshot.operation_version,
    operations: snapshot.operations ?? state.operations,
    profile: snapshot.profile ?? state.profile,
  });
}

function noticeFor(_error: unknown): BridgeErrorDto {
  return unavailableNotice;
}

function createDesktopState(api: DesktopApi): StateCreator<DesktopState> {
  let commandSequence = 0;

  return (set, get) => ({
    tasks: [],
    taskVersion: -1,
    operations: {},
    operationVersion: -1,
    activeOperationId: null,
    activeOperationKind: null,
    selectedVolumes: [],
    pendingCancellationIds: [],
    pendingRestartIds: [],
    profile: { status: "unknown", detail: "" },
    settings: {},
    notice: null,
    async bootstrap(writeGuard = allowWrites) {
      try {
        const response = await api.bootstrap();
        if (isBridgeError(response)) {
          if (writeGuard()) {
            set({ notice: response.error });
          }
          return;
        }
        if (writeGuard()) {
          set((state) => ({
            ...mergeSnapshot(response)(state),
            settings: response.config,
            notice: null,
          }));
        }
      } catch (error) {
        if (writeGuard()) {
          set({ notice: noticeFor(error) });
        }
      }
    },
    async pollOnce(writeGuard = allowWrites) {
      try {
        const response = await api.poll(get().taskVersion, get().operationVersion);
        if (isBridgeError(response)) {
          if (writeGuard()) {
            set({ notice: response.error });
          }
          return;
        }
        if (writeGuard()) {
          set((state) => ({ ...mergeSnapshot(response)(state), notice: null }));
        }
      } catch (error) {
        if (writeGuard()) {
          set({ notice: noticeFor(error) });
        }
      }
    },
    async search(query) {
      const sequence = ++commandSequence;
      set({
        activeOperationId: null,
        activeOperationKind: "search",
        selectedVolumes: [],
        notice: null,
      });
      await startOperation(
        api.startSearch(query),
        set,
        () => sequence === commandSequence,
      );
    },
    async loadCatalog(url) {
      const sequence = ++commandSequence;
      set({
        activeOperationId: null,
        activeOperationKind: "catalog",
        selectedVolumes: [],
        notice: null,
      });
      await startOperation(
        api.loadCatalog(url),
        set,
        () => sequence === commandSequence,
      );
    },
    async startDownload(catalogOperationId, selectedVolumes) {
      const sequence = ++commandSequence;
      set({
        activeOperationId: null,
        activeOperationKind: "download",
        notice: null,
      });
      await startOperation(
        api.startDownload(catalogOperationId, selectedVolumes),
        set,
        () => sequence === commandSequence,
      );
    },
    toggleVolume(volumeName) {
      set((state) => ({
        selectedVolumes: state.selectedVolumes.includes(volumeName)
          ? state.selectedVolumes.filter((name) => name !== volumeName)
          : [...state.selectedVolumes, volumeName],
      }));
    },
    async cancelTask(taskId) {
      if (get().pendingCancellationIds.includes(taskId)) {
        return;
      }
      set((state) => ({
        pendingCancellationIds: [...state.pendingCancellationIds, taskId],
      }));
      try {
        const response = await api.cancel(taskId);
        if (isBridgeError(response)) {
          set({ notice: response.error });
          return;
        }
        set({ notice: null });
      } catch (error) {
        set({ notice: noticeFor(error) });
      } finally {
        set((state) => ({
          pendingCancellationIds: state.pendingCancellationIds.filter(
            (id) => id !== taskId,
          ),
        }));
      }
    },
    async restartTask(taskId) {
      if (get().pendingRestartIds.includes(taskId)) {
        return;
      }
      set((state) => ({
        pendingRestartIds: [...state.pendingRestartIds, taskId],
      }));
      try {
        const task = get().tasks.find((candidate) => candidate.id === taskId);
        const sequence = ++commandSequence;
        set({
          activeOperationKind: toWorkbenchKind(task?.input_snapshot?.kind),
          notice: null,
        });
        await startOperation(
          api.restartTask(taskId),
          set,
          () => sequence === commandSequence,
        );
      } finally {
        set((state) => ({
          pendingRestartIds: state.pendingRestartIds.filter(
            (id) => id !== taskId,
          ),
        }));
      }
    },
    async focusTaskVerification(taskId) {
      await runCommand(api.focusTaskVerification(taskId), set);
    },
    async checkProfile() {
      await runCommand(api.checkProfile(), set);
    },
    async startManualVerification(targetUrl) {
      await runCommand(api.startManualVerification(targetUrl), set);
    },
    viewTaskResult(taskId) {
      const operation = Object.values(get().operations).find(
        (candidate) =>
          candidate.task_id === taskId && candidate.status === "completed",
      );
      if (operation) {
        set({
          activeOperationId: operation.id,
          activeOperationKind: toWorkbenchKind(operation.kind),
          notice: null,
        });
        return true;
      }
      return false;
    },
  });
}

export function createDesktopStore(api: DesktopApi = desktopApi): StoreApi<DesktopState> {
  return createStore(createDesktopState(api));
}

async function startOperation(
  command: Promise<{ ok: boolean; operation_id?: string; error?: BridgeErrorDto }>,
  set: StoreApi<DesktopState>["setState"],
  writeGuard: WriteGuard,
): Promise<void> {
  try {
    const response = await command;
    if (isBridgeError(response)) {
      if (writeGuard()) {
        set({ notice: response.error });
      }
      return;
    }
    if (writeGuard()) {
      set({
        activeOperationId: response.operation_id ?? null,
        notice: null,
      });
    }
  } catch (error) {
    if (writeGuard()) {
      set({ notice: noticeFor(error) });
    }
  }
}

async function runCommand(
  command: Promise<{ ok: boolean; error?: BridgeErrorDto }>,
  set: StoreApi<DesktopState>["setState"],
): Promise<void> {
  try {
    const response = await command;
    if (isBridgeError(response)) {
      set({ notice: response.error });
      return;
    }
    set({ notice: null });
  } catch (error) {
    set({ notice: noticeFor(error) });
  }
}

function toWorkbenchKind(kind?: string): WorkbenchOperationKind | null {
  return kind === "search" || kind === "catalog" || kind === "download"
    ? kind
    : null;
}

export const useDesktopStore = create<DesktopState>(createDesktopState(desktopApi));

let pollingTimer: ReturnType<typeof setTimeout> | undefined;
let pollingActive = false;
let pollingBootstrapped = false;
let pollingGeneration = 0;

function schedulePolling(generation: number) {
  if (!pollingActive || generation !== pollingGeneration) {
    return;
  }
  const delay = document.hidden ? 2_000 : 500;
  pollingTimer = setTimeout(async () => {
    if (!pollingActive || generation !== pollingGeneration) {
      return;
    }
    pollingTimer = undefined;
    const writeGuard = () => pollingActive && generation === pollingGeneration;
    await useDesktopStore.getState().pollOnce(writeGuard);
    if (pollingActive && generation === pollingGeneration) {
      schedulePolling(generation);
    }
  }, delay);
}

function restartPollingForVisibility() {
  if (!pollingActive || !pollingBootstrapped) {
    return;
  }
  const generation = ++pollingGeneration;
  if (pollingTimer !== undefined) {
    clearTimeout(pollingTimer);
    pollingTimer = undefined;
  }
  schedulePolling(generation);
}

export function startPolling(): void {
  if (pollingActive) {
    return;
  }
  pollingActive = true;
  pollingBootstrapped = false;
  const generation = ++pollingGeneration;
  document.addEventListener("visibilitychange", restartPollingForVisibility);
  void useDesktopStore
    .getState()
    .bootstrap(() => pollingActive && generation === pollingGeneration)
    .then(() => {
      if (!pollingActive || generation !== pollingGeneration) {
        return;
      }
      pollingBootstrapped = true;
      schedulePolling(generation);
    });
}

export function stopPolling(): void {
  pollingActive = false;
  pollingBootstrapped = false;
  pollingGeneration += 1;
  if (pollingTimer !== undefined) {
    clearTimeout(pollingTimer);
    pollingTimer = undefined;
  }
  document.removeEventListener("visibilitychange", restartPollingForVisibility);
}
