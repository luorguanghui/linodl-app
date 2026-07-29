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
