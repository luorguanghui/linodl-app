import type {
  BootstrapDto,
  BootstrapResponse,
  BridgeCancelResult,
  BridgeArchiveListResult,
  BridgeCommandResult,
  BridgeDirectoryResult,
  BridgeOperationResult,
  BridgeSettingsResult,
  PollResponse,
  SaveSettingsDto,
} from "./types";

type PywebviewMethods = Record<
  string,
  (...values: unknown[]) => Promise<unknown>
>;

declare global {
  interface Window {
    pywebview?: { api: PywebviewMethods };
  }
}

const developmentBootstrap: BootstrapDto = {
  task_version: 0,
  tasks: [],
  operation_version: 0,
  operations: {},
  profile: { status: "unknown", detail: "" },
  config: {},
};

export async function waitForPywebview(): Promise<void> {
  if (window.pywebview?.api || import.meta.env.DEV) {
    return;
  }

  await new Promise<void>((resolve) => {
    window.addEventListener("pywebviewready", () => resolve(), { once: true });
  });
}

export async function invoke<T>(method: string, ...args: unknown[]): Promise<T> {
  await waitForPywebview();
  const api = window.pywebview?.api as
    | Record<string, (...values: unknown[]) => Promise<T>>
    | undefined;
  if (!api?.[method]) {
    throw new Error(`Desktop API method is unavailable: ${method}`);
  }
  return api[method](...args);
}

export interface DesktopApi {
  bootstrap(): Promise<BootstrapResponse>;
  poll(taskVersion: number, operationVersion: number): Promise<PollResponse>;
  startSearch(query: string): Promise<BridgeOperationResult>;
  loadCatalog(url: string): Promise<BridgeOperationResult>;
  startDownload(
    catalogOperationId: string,
    selectedVolumes: string[],
  ): Promise<BridgeOperationResult>;
  cancel(taskId: string): Promise<BridgeCancelResult>;
  restartTask(taskId: string): Promise<BridgeOperationResult>;
  focusTaskVerification(taskId: string): Promise<BridgeCommandResult>;
  checkProfile(): Promise<BridgeCommandResult>;
  startManualVerification(targetUrl: string): Promise<BridgeCommandResult>;
  listArchives(): Promise<BridgeArchiveListResult>;
  startVerify(archiveId: string): Promise<BridgeOperationResult>;
  startExport(
    archiveId: string,
    perVolume: boolean,
  ): Promise<BridgeOperationResult>;
  getSettings(): Promise<BridgeSettingsResult>;
  saveSettings(settings: SaveSettingsDto): Promise<BridgeCommandResult>;
  chooseDirectory(): Promise<BridgeDirectoryResult>;
  openDirectory(path: string): Promise<BridgeCommandResult>;
}

export const desktopApi: DesktopApi = {
  async bootstrap() {
    if (import.meta.env.DEV && !window.pywebview?.api) {
      return developmentBootstrap;
    }
    return invoke<BootstrapResponse>("bootstrap");
  },
  poll(taskVersion, operationVersion) {
    return invoke<PollResponse>("poll", taskVersion, operationVersion);
  },
  startSearch(query) {
    return invoke<BridgeOperationResult>("start_search", query);
  },
  loadCatalog(url) {
    return invoke<BridgeOperationResult>("load_catalog", url);
  },
  startDownload(catalogOperationId, selectedVolumes) {
    return invoke<BridgeOperationResult>(
      "start_download",
      catalogOperationId,
      selectedVolumes,
    );
  },
  cancel(taskId) {
    return invoke<BridgeCancelResult>("cancel", taskId);
  },
  restartTask(taskId) {
    return invoke<BridgeOperationResult>("restart_task", taskId);
  },
  focusTaskVerification(taskId) {
    return invoke<BridgeCommandResult>("focus_task_verification", taskId);
  },
  checkProfile() {
    return invoke<BridgeCommandResult>("check_profile");
  },
  startManualVerification(targetUrl) {
    return invoke<BridgeCommandResult>(
      "start_manual_verification",
      targetUrl,
    );
  },
  listArchives() {
    return invoke<BridgeArchiveListResult>("list_archives");
  },
  startVerify(archiveId) {
    return invoke<BridgeOperationResult>("start_verify", archiveId);
  },
  startExport(archiveId, perVolume) {
    return invoke<BridgeOperationResult>(
      "start_export",
      archiveId,
      perVolume,
    );
  },
  getSettings() {
    return invoke<BridgeSettingsResult>("get_settings");
  },
  saveSettings(settings) {
    return invoke<BridgeCommandResult>("save_settings", settings);
  },
  chooseDirectory() {
    return invoke<BridgeDirectoryResult>("choose_directory");
  },
  openDirectory(path) {
    return invoke<BridgeCommandResult>("open_directory", path);
  },
};
