export type PdaQueueOperation = "SCAN_VALUE" | "CONFIRM_PICK";
export type PdaQueueStatus =
  | "PENDING"
  | "SENDING"
  | "FAILED_RETRYABLE"
  | "BLOCKED_AUTH"
  | "FAILED_PERMANENT"
  | "COMPLETED";

export interface PdaQueuePayload {
  session_id: number;
  value?: string;
  quantity?: number;
  step?: string;
  source?: "manual" | "camera";
}

export interface PdaQueueRecord {
  local_queue_id: string;
  client_operation_id: string;
  operation_type: PdaQueueOperation;
  payload: PdaQueuePayload;
  created_at: string;
  retry_count: number;
  last_attempt_at: string | null;
  last_error: string | null;
  status: PdaQueueStatus;
  next_attempt_at: string | null;
  lease_expires_at: string | null;
  completed_at: string | null;
}

export interface NewPdaQueueRecord {
  sessionId: number;
  clientOperationId: string;
  operationType: PdaQueueOperation;
  value?: string;
  quantity?: number;
  step?: string;
  source?: "manual" | "camera";
}

export interface PdaQueueFailure {
  httpStatus?: number;
  errorCode?: string;
  message: string;
}

export const MAX_AUTOMATIC_RETRIES = 3;
export const BASE_RETRY_DELAY_MS = 1_000;
export const SENDING_LEASE_MS = 120_000;
export const COMPLETION_RETENTION_MS = 86_400_000;

function cleanText(value: unknown, fallback: string) {
  if (typeof value !== "string") return fallback;
  return value.replace(/[\r\n\t]+/g, " ").slice(0, 240) || fallback;
}

export function makePdaQueueRecord(input: NewPdaQueueRecord, now = new Date()): PdaQueueRecord {
  const createdAt = now.toISOString();
  return {
    local_queue_id: input.clientOperationId,
    client_operation_id: input.clientOperationId,
    operation_type: input.operationType,
    payload: {
      session_id: input.sessionId,
      ...(input.operationType === "SCAN_VALUE"
        ? { value: cleanText(input.value, "").trim(), step: input.step, source: input.source }
        : { quantity: Number(input.quantity) }),
    },
    created_at: createdAt,
    retry_count: 0,
    last_attempt_at: null,
    last_error: null,
    status: "PENDING",
    next_attempt_at: null,
    lease_expires_at: null,
    completed_at: null,
  };
}

export function retryDelayMs(retryCount: number) {
  return BASE_RETRY_DELAY_MS * (2 ** Math.max(0, retryCount - 1));
}

export function isServerIdempotent(record: PdaQueueRecord) {
  return record.operation_type === "CONFIRM_PICK";
}

export function isActiveQueueRecord(record: PdaQueueRecord) {
  return record.status !== "COMPLETED";
}

export function applyQueueFailure(record: PdaQueueRecord, failure: PdaQueueFailure, now = new Date()): PdaQueueRecord {
  const lastError = cleanText(failure.message, failure.errorCode ?? "同步失败");
  const base = { ...record, lease_expires_at: null, last_error: lastError };

  if (failure.httpStatus === 401 || failure.httpStatus === 403) {
    return { ...base, status: "BLOCKED_AUTH", next_attempt_at: null };
  }
  if (failure.httpStatus !== undefined && failure.httpStatus >= 400 && failure.httpStatus < 500) {
    return { ...base, status: "FAILED_PERMANENT", next_attempt_at: null };
  }

  const retryCount = record.retry_count + 1;
  return {
    ...base,
    retry_count: retryCount,
    status: "FAILED_RETRYABLE",
    next_attempt_at: retryCount < MAX_AUTOMATIC_RETRIES
      ? new Date(now.getTime() + retryDelayMs(retryCount)).toISOString()
      : null,
  };
}
