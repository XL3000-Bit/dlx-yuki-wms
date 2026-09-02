import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { IDBKeyRange, indexedDB } from "fake-indexeddb";
import {
  MAX_AUTOMATIC_RETRIES,
  applyQueueFailure,
  makePdaQueueRecord,
} from "./offlineQueuePolicy.ts";
import { enqueueUnique, pdaQueueRepository } from "./offlineQueueDb.ts";
import { PdaQueueSynchronizer } from "./offlineQueueSync.ts";

globalThis.indexedDB = indexedDB;
globalThis.IDBKeyRange = IDBKeyRange;

const synchronizers = [];

function record(id, createdAt, operationType = "CONFIRM_PICK") {
  return makePdaQueueRecord({
    sessionId: 7,
    clientOperationId: id,
    operationType,
    ...(operationType === "SCAN_VALUE"
      ? { value: `CODE-${id}`, step: "EXPECT_LOCATION", source: "manual" }
      : { quantity: 2 }),
  }, new Date(createdAt));
}

function synchronizer(sender, options = {}) {
  const value = new PdaQueueSynchronizer(pdaQueueRepository, sender, options);
  synchronizers.push(value);
  return value;
}

async function resetDatabase() {
  await new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase("dlx-wms-pda");
    request.onsuccess = () => resolve();
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("test database is blocked"));
  });
}

beforeEach(resetDatabase);
afterEach(() => {
  for (const value of synchronizers.splice(0)) value.dispose();
});

test("offline enqueue persists the full audit record across repository reopen", async () => {
  const queued = record("offline-1", "2026-01-01T00:00:00.000Z", "SCAN_VALUE");
  await enqueueUnique(pdaQueueRepository, queued);
  const firstRead = await pdaQueueRepository.list();
  const reloadRead = await pdaQueueRepository.list();
  assert.deepEqual(reloadRead, firstRead);
  assert.equal(reloadRead[0].client_operation_id, "offline-1");
  assert.equal(reloadRead[0].operation_type, "SCAN_VALUE");
  assert.equal(reloadRead[0].retry_count, 0);
  assert.equal(reloadRead[0].last_attempt_at, null);
  assert.equal(reloadRead[0].last_error, null);
  assert.equal(reloadRead[0].status, "PENDING");
});

test("replay is FIFO and completed records leave the active count", async () => {
  await pdaQueueRepository.add(record("second", "2026-01-01T00:00:02.000Z"));
  await pdaQueueRepository.add(record("first", "2026-01-01T00:00:01.000Z"));
  const sent = [];
  const completed = await synchronizer(async (queued) => sent.push(queued.client_operation_id)).syncNow();
  assert.equal(completed, 2);
  assert.deepEqual(sent, ["first", "second"]);
  const records = await pdaQueueRepository.list();
  assert.equal(records.filter((queued) => queued.status !== "COMPLETED").length, 0);
  assert.ok(records.every((queued) => queued.completed_at));
});

test("a local success callback cannot requeue a server-confirmed operation", async () => {
  await pdaQueueRepository.add(record("server-confirmed", "2026-01-01T00:00:00.000Z"));
  const worker = synchronizer(async () => ({ ok: true }), {
    onSuccess: async () => { throw new Error("UI refresh failed"); },
  });

  assert.equal(await worker.syncNow(), 1);
  const [saved] = await pdaQueueRepository.list();
  assert.equal(saved.status, "COMPLETED");
});

test("manual and repeated online sync triggers share one worker", async () => {
  await pdaQueueRepository.add(record("single-flight", "2026-01-01T00:00:00.000Z"));
  let release;
  let sends = 0;
  let concurrent = 0;
  let maximumConcurrent = 0;
  const gate = new Promise((resolve) => { release = resolve; });
  const worker = synchronizer(async () => {
    sends += 1;
    concurrent += 1;
    maximumConcurrent = Math.max(maximumConcurrent, concurrent);
    await gate;
    concurrent -= 1;
  });
  const manual = worker.syncNow();
  const onlineOne = worker.syncNow();
  const onlineTwo = worker.syncNow();
  assert.equal(manual, onlineOne);
  assert.equal(onlineOne, onlineTwo);
  release();
  await manual;
  assert.equal(sends, 1);
  assert.equal(maximumConcurrent, 1);
});

test("IndexedDB claim is atomic across two synchronizer instances", async () => {
  await pdaQueueRepository.add(record("atomic", "2026-01-01T00:00:00.000Z"));
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const sent = [];
  const sender = async (queued) => {
    sent.push(queued.client_operation_id);
    await gate;
  };
  const first = synchronizer(sender);
  const second = synchronizer(sender);
  const firstRun = first.syncNow();
  const secondRun = second.syncNow();
  await new Promise((resolve) => setTimeout(resolve, 0));
  release();
  await Promise.all([firstRun, secondRun]);
  assert.deepEqual(sent, ["atomic"]);
});

test("network and 5xx failures use finite exponential retry state", () => {
  let failed = record("retry", "2026-01-01T00:00:00.000Z");
  for (let attempt = 1; attempt <= MAX_AUTOMATIC_RETRIES; attempt += 1) {
    const now = new Date(`2026-01-01T00:00:0${attempt}.000Z`);
    failed = applyQueueFailure(failed, { message: "Network Error" }, now);
    assert.equal(failed.status, "FAILED_RETRYABLE");
    assert.equal(failed.retry_count, attempt);
    assert.equal(failed.next_attempt_at === null, attempt === MAX_AUTOMATIC_RETRIES);
  }
});

test("401 and 403 block authentication without automatic retry", async (context) => {
  for (const status of [401, 403]) {
    await context.test(String(status), () => {
      const failed = applyQueueFailure(record(`auth-${status}`, "2026-01-01T00:00:00.000Z"), {
        httpStatus: status,
        message: "Authentication required",
      });
      assert.equal(failed.status, "BLOCKED_AUTH");
      assert.equal(failed.retry_count, 0);
      assert.equal(failed.next_attempt_at, null);
    });
  }
});

test("non-retryable 4xx is retained with its visible error", async () => {
  await pdaQueueRepository.add(record("business", "2026-01-01T00:00:00.000Z"));
  await synchronizer(async () => {
    throw { httpStatus: 422, message: "Quantity exceeds remaining" };
  }).syncNow();
  const [failed] = await pdaQueueRepository.list();
  assert.equal(failed.status, "FAILED_PERMANENT");
  assert.equal(failed.last_error, "Quantity exceeds remaining");
  assert.equal(failed.next_attempt_at, null);
});

test("a network failure is persisted as retryable", async () => {
  await pdaQueueRepository.add(record("network", "2026-01-01T00:00:00.000Z"));
  await synchronizer(async () => {
    throw { message: "Network unavailable" };
  }).syncNow();
  const [failed] = await pdaQueueRepository.list();
  assert.equal(failed.status, "FAILED_RETRYABLE");
  assert.equal(failed.retry_count, 1);
  assert.match(failed.last_error, /Network unavailable/);
  assert.ok(failed.next_attempt_at);
});

test("an expired sending lease recovers after browser interruption", async () => {
  await pdaQueueRepository.add({
    ...record("interrupted", "2026-01-01T00:00:00.000Z"),
    status: "SENDING",
    lease_expires_at: "2026-01-01T00:01:00.000Z",
  });
  await pdaQueueRepository.recoverInterrupted(new Date("2026-01-01T00:02:00.000Z"));
  const [recovered] = await pdaQueueRepository.list();
  assert.equal(recovered.status, "PENDING");
  assert.equal(recovered.client_operation_id, "interrupted");
  assert.match(recovered.last_error, /中断/);
});

test("an offline worker leaves persisted work pending", async () => {
  await pdaQueueRepository.add(record("still-offline", "2026-01-01T00:00:00.000Z"));
  let sends = 0;
  const completed = await synchronizer(async () => { sends += 1; }, { canSend: () => false }).syncNow();
  const [queued] = await pdaQueueRepository.list();
  assert.equal(completed, 0);
  assert.equal(sends, 0);
  assert.equal(queued.status, "PENDING");
});
