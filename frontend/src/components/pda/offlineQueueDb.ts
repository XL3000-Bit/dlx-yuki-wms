import { COMPLETION_RETENTION_MS, MAX_AUTOMATIC_RETRIES, SENDING_LEASE_MS, type PdaQueueRecord } from "./offlineQueuePolicy.ts";

export interface PdaQueueRepository {
  list(): Promise<PdaQueueRecord[]>;
  add(record: PdaQueueRecord): Promise<void>;
  put(record: PdaQueueRecord): Promise<void>;
  get(clientOperationId: string): Promise<PdaQueueRecord | undefined>;
  claimNext(now?: Date): Promise<PdaQueueRecord | undefined>;
  requeueRetryable(clientOperationId: string): Promise<void>;
  requeueBlockedAuth(): Promise<void>;
  recoverInterrupted(now?: Date): Promise<void>;
  pruneCompleted(now?: Date): Promise<void>;
}

const DB_NAME = "dlx-wms-pda";
const DB_VERSION = 2;
const STORE_NAME = "offline-operations";

function requestResult<T>(request: IDBRequest<T>) {
  return new Promise<T>((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

function transactionDone(transaction: IDBTransaction) {
  return new Promise<void>((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB transaction failed"));
    transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB transaction aborted"));
  });
}

function openDatabase() {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      const store = database.objectStoreNames.contains(STORE_NAME)
        ? request.transaction!.objectStore(STORE_NAME)
        : database.createObjectStore(STORE_NAME, { keyPath: "local_queue_id" });
      for (const name of Array.from(store.indexNames)) store.deleteIndex(name);
      store.createIndex("client_operation_id", "client_operation_id", { unique: true });
      store.createIndex("created_at", "created_at");
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Unable to open IndexedDB"));
  });
}

async function withTransaction<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => Promise<T>) {
  const database = await openDatabase();
  try {
    const transaction = database.transaction(STORE_NAME, mode);
    const result = await run(transaction.objectStore(STORE_NAME));
    await transactionDone(transaction);
    return result;
  } finally {
    database.close();
  }
}

function normalizeRecord(value: unknown): PdaQueueRecord | null {
  if (!value || typeof value !== "object") return null;
  const current = value as Partial<PdaQueueRecord>;
  if (typeof current.client_operation_id === "string" && typeof current.operation_type === "string") {
    return current as PdaQueueRecord;
  }
  const legacy = value as Record<string, unknown>;
  if (typeof legacy.operation_id !== "string" || (legacy.action_type !== "SCAN_VALUE" && legacy.action_type !== "CONFIRM_PICK")) return null;
  const match = String(legacy.endpoint ?? "").match(/\/scan-sessions\/(\d+)\//);
  const rawPayload = legacy.sanitized_payload;
  const payload = rawPayload && typeof rawPayload === "object" ? rawPayload as Record<string, unknown> : {};
  const sessionId = typeof payload.session_id === "number" ? payload.session_id : Number(match?.[1]);
  if (!Number.isSafeInteger(sessionId) || sessionId <= 0) return null;
  return {
    local_queue_id: String(legacy.local_queue_id ?? legacy.operation_id),
    client_operation_id: legacy.operation_id,
    operation_type: legacy.action_type,
    payload: {
      session_id: sessionId,
      ...(typeof payload.value === "string" ? { value: payload.value } : {}),
      ...(typeof payload.quantity === "number" ? { quantity: payload.quantity } : {}),
      ...(typeof payload.step === "string" ? { step: payload.step } : {}),
      ...(payload.source === "manual" || payload.source === "camera" ? { source: payload.source } : {}),
    },
    created_at: String(legacy.created_at ?? new Date().toISOString()),
    retry_count: Number(legacy.retry_count ?? 0),
    last_attempt_at: null,
    last_error: typeof legacy.last_error_message === "string" ? legacy.last_error_message : null,
    status: legacy.status === "COMPLETED" ? "COMPLETED" : "PENDING",
    next_attempt_at: typeof legacy.next_retry_at === "string" ? legacy.next_retry_at : null,
    lease_expires_at: null,
    completed_at: legacy.status === "COMPLETED" ? String(legacy.updated_at ?? legacy.created_at) : null,
  };
}

async function allRecords(store: IDBObjectStore) {
  const raw = await requestResult(store.getAll()) as unknown[];
  return raw.map(normalizeRecord).filter((record): record is PdaQueueRecord => record !== null)
    .sort((left, right) => left.created_at.localeCompare(right.created_at));
}

export const pdaQueueRepository: PdaQueueRepository = {
  list: () => withTransaction("readonly", allRecords),
  add: (record) => withTransaction("readwrite", async (store) => { await requestResult(store.add(record)); }),
  put: (record) => withTransaction("readwrite", async (store) => { await requestResult(store.put(record)); }),
  get: (id) => withTransaction("readonly", async (store) => normalizeRecord(await requestResult(store.get(id))) ?? undefined),
  claimNext: (now = new Date()) => withTransaction("readwrite", async (store) => {
    const timestamp = now.getTime();
    const active = (await allRecords(store)).filter((record) => record.status !== "COMPLETED");
    const candidate = active[0];
    if (!candidate) return undefined;
    const sendable = candidate.status === "PENDING" || (
      candidate.status === "FAILED_RETRYABLE"
      && candidate.retry_count < MAX_AUTOMATIC_RETRIES
      && (!candidate.next_attempt_at || Date.parse(candidate.next_attempt_at) <= timestamp)
    );
    if (!sendable) return undefined;
    const claimed: PdaQueueRecord = {
      ...candidate,
      status: "SENDING",
      last_attempt_at: now.toISOString(),
      lease_expires_at: new Date(timestamp + SENDING_LEASE_MS).toISOString(),
    };
    await requestResult(store.put(claimed));
    return claimed;
  }),
  requeueRetryable: (id) => withTransaction("readwrite", async (store) => {
    const record = normalizeRecord(await requestResult(store.get(id)));
    if (!record || !["FAILED_RETRYABLE", "FAILED_PERMANENT"].includes(record.status)) return;
    await requestResult(store.put({ ...record, status: "PENDING", retry_count: 0, next_attempt_at: null, last_error: null, lease_expires_at: null }));
  }),
  requeueBlockedAuth: () => withTransaction("readwrite", async (store) => {
    for (const record of await allRecords(store)) {
      if (record.status === "BLOCKED_AUTH") await requestResult(store.put({ ...record, status: "PENDING", next_attempt_at: null }));
    }
  }),
  recoverInterrupted: (now = new Date()) => withTransaction("readwrite", async (store) => {
    for (const record of await allRecords(store)) {
      if (record.status === "SENDING" && (!record.lease_expires_at || Date.parse(record.lease_expires_at) <= now.getTime())) {
        await requestResult(store.put({ ...record, status: "PENDING", lease_expires_at: null, last_error: "上次同步被中断，已恢复等待重试。" }));
      }
    }
  }),
  pruneCompleted: (now = new Date()) => withTransaction("readwrite", async (store) => {
    const cutoff = now.getTime() - COMPLETION_RETENTION_MS;
    for (const record of await allRecords(store)) {
      if (record.status === "COMPLETED" && record.completed_at && Date.parse(record.completed_at) < cutoff) {
        await requestResult(store.delete(record.local_queue_id));
      }
    }
  }),
};

export async function enqueueUnique(repository: PdaQueueRepository, record: PdaQueueRecord) {
  const existing = await repository.get(record.client_operation_id);
  if (existing) return existing;
  try {
    await repository.add(record);
    return record;
  } catch (error) {
    if (error instanceof DOMException && error.name === "ConstraintError") {
      return (await repository.get(record.client_operation_id)) ?? Promise.reject(error);
    }
    throw error;
  }
}
