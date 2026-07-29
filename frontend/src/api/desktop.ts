import type {
  BootstrapDto,
  BootstrapResponse,
  BridgeCancelResult,
  BridgeCommandResult,
  BridgeOperationResult,
  PollResponse,
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
  checkProfile(): Promise<BridgeCommandResult>;
  startManualVerification(targetUrl: string): Promise<BridgeCommandResult>;
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
  checkProfile() {
    return invoke<BridgeCommandResult>("check_profile");
  },
  startManualVerification(targetUrl) {
    return invoke<BridgeCommandResult>(
      "start_manual_verification",
      targetUrl,
    );
  },
};
