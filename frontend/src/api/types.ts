export type TaskStatus =
  | "queued"
  | "waiting_for_profile"
  | "running"
  | "waiting_for_verification"
  | "cancelling"
  | "cancelled"
  | "failed"
  | "completed";

export interface TaskDto {
  id: string;
  title: string;
  status: TaskStatus;
  detail: string;
  progress: number;
  input_snapshot: TaskInputDto | null;
  error_detail: string;
}

export interface VersionedTasksDto {
  version: number;
  tasks: TaskDto[] | null;
}

export interface TaskInputDto {
  kind: string;
  query: string;
  url: string;
  selected_volumes: string[];
  output_dir: string;
}

export type OperationStatus = "running" | "completed" | "failed" | "cancelled";

export interface OperationDto {
  id: string;
  kind: string;
  task_id: string;
  status: OperationStatus;
  detail: string;
  result: unknown;
  error: string;
}

export type OperationMapDto = Record<string, OperationDto>;

export interface PollDto {
  task_version: number;
  tasks: TaskDto[] | null;
  operation_version: number;
  operations: OperationMapDto | null;
  profile?: ProfileHealthDto;
}

export interface DesktopSettingsDto {
  username?: string;
  has_password?: boolean;
  output_dir?: string;
  headless?: boolean;
  anti_bot_mode?: string;
  profile_dir?: string;
  proxy?: string;
  geoip?: boolean;
  theme?: string;
}

export interface SaveSettingsDto extends DesktopSettingsDto {
  password: string;
  clear_password: boolean;
}

export interface ArchiveDto {
  id: string;
  title: string;
  path: string;
  volume_count: number;
  chapter_count: number;
}

export type ProfileStatus =
  | "unknown"
  | "checking"
  | "healthy"
  | "needs_verification"
  | "busy"
  | "error";

export interface ProfileHealthDto {
  status: ProfileStatus;
  detail: string;
}

export interface BootstrapDto extends PollDto {
  config: DesktopSettingsDto;
}

export interface BridgeErrorDto {
  code: string;
  message: string;
  action: string;
}

export interface BridgeErrorResponse {
  ok: false;
  error: BridgeErrorDto;
}

export interface BridgeOperationResponse {
  ok: true;
  operation_id: string;
}

export interface BridgeCancelResponse {
  ok: true;
}

export interface BridgeCommandResponse {
  ok: true;
}

export interface BridgeArchiveListResponse {
  ok: true;
  archives: ArchiveDto[];
}

export interface BridgeSettingsResponse {
  ok: true;
  settings: DesktopSettingsDto;
}

export interface BridgeDirectoryResponse {
  ok: true;
  path: string;
}

export type PollResponse = PollDto | BridgeErrorResponse;
export type BootstrapResponse = BootstrapDto | BridgeErrorResponse;
export type BridgeOperationResult = BridgeOperationResponse | BridgeErrorResponse;
export type BridgeCancelResult = BridgeCancelResponse | BridgeErrorResponse;
export type BridgeCommandResult = BridgeCommandResponse | BridgeErrorResponse;
export type BridgeArchiveListResult =
  | BridgeArchiveListResponse
  | BridgeErrorResponse;
export type BridgeSettingsResult =
  | BridgeSettingsResponse
  | BridgeErrorResponse;
export type BridgeDirectoryResult =
  | BridgeDirectoryResponse
  | BridgeErrorResponse;
