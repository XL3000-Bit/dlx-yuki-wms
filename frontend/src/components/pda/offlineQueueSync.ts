import {
  applyQueueFailure,
  type PdaQueueFailure,
  type PdaQueueRecord,
} from "./offlineQueuePolicy.ts";
import type { PdaQueueRepository } from "./offlineQueueDb.ts";

export type PdaQueueSender = (record: PdaQueueRecord) => Promise<unknown>;
export type PdaQueueSuccess = (record: PdaQueueRecord, response: unknown) => void | Promise<void>;

interface PdaQueueSynchronizerOptions {
  onSuccess?: PdaQueueSuccess;
  onChange?: () => void | Promise<void>;
  now?: () => Date;
  canSend?: () => boolean;
}

export class PdaQueueSynchronizer {
  private active: Promise<number> | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private disposed = false;
  private readonly repository: PdaQueueRepository;
  private readonly sender: PdaQueueSender;
  private readonly onSuccess?: PdaQueueSuccess;
  private readonly onChange?: () => void | Promise<void>;
  private readonly now: () => Date;
  private readonly canSend: () => boolean;

  constructor(repository: PdaQueueRepository, sender: PdaQueueSender, options: PdaQueueSynchronizerOptions = {}) {
    this.repository = repository;
    this.sender = sender;
    this.onSuccess = options.onSuccess;
    this.onChange = options.onChange;
    this.now = options.now ?? (() => new Date());
    this.canSend = options.canSend ?? (() => true);
  }

  resume() {
    this.disposed = false;
  }

  dispose() {
    this.disposed = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  syncNow() {
    if (this.disposed || !this.canSend()) return Promise.resolve(0);
    if (this.active) return this.active;
    this.active = this.run().finally(async () => {
      this.active = null;
      await this.scheduleNextRetry();
    });
    return this.active;
  }

  async retry(clientOperationId: string) {
    await this.repository.requeueRetryable(clientOperationId);
    await this.onChange?.();
    return this.syncNow();
  }

  private async run() {
    let completed = 0;
    while (!this.disposed) {
      const sending = await this.repository.claimNext(this.now());
      if (!sending) break;
      await this.onChange?.();

      try {
        const response = await this.sender(sending);
        const completedAt = this.now().toISOString();
        await this.repository.put({
          ...sending,
          status: "COMPLETED",
          completed_at: completedAt,
          lease_expires_at: null,
          next_attempt_at: null,
          last_error: null,
        });
        completed += 1;
        try {
          await this.onSuccess?.(sending, response);
        } catch {
          // The server response is authoritative. A presentation refresh failure
          // must never turn a completed write back into a retryable operation.
        }
      } catch (error) {
        const failure = error as PdaQueueFailure;
        const failed = applyQueueFailure(sending, {
          httpStatus: failure.httpStatus,
          errorCode: failure.errorCode,
          message: failure.message || "同步失败",
        }, this.now());
        await this.repository.put(failed);
        await this.onChange?.();
        break;
      }

      await this.onChange?.();
    }
    return completed;
  }

  private async scheduleNextRetry() {
    if (this.disposed || this.retryTimer) return;
    const due = (await this.repository.list())
      .filter((record) => record.status !== "COMPLETED")[0];
    // Retry scheduling must obey the same FIFO head as claimNext. A blocked head
    // cannot be bypassed and must not spin a timer for later work.
    if (due?.status !== "FAILED_RETRYABLE") return;
    if (!due?.next_attempt_at) return;
    const delay = Math.max(0, Date.parse(due.next_attempt_at) - this.now().getTime());
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      if (this.canSend()) void this.syncNow();
    }, delay);
  }
}
