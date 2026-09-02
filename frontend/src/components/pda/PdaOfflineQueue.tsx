import { SyncOutlined } from "@ant-design/icons";
import { Button } from "antd";
import { isActiveQueueRecord, isServerIdempotent, type PdaQueueRecord, type PdaQueueStatus } from "./offlineQueuePolicy.ts";

interface PdaOfflineQueueProps {
  records: PdaQueueRecord[];
  online: boolean;
  syncing: boolean;
  onSync: () => void;
  onRetry: (clientOperationId: string) => void;
}

const statusCopy: Record<PdaQueueStatus, string> = {
  PENDING: "待同步",
  SENDING: "正在同步",
  FAILED_RETRYABLE: "同步失败（可重试）",
  BLOCKED_AUTH: "需要重新登录",
  FAILED_PERMANENT: "业务校验失败",
  COMPLETED: "已同步",
};

export function PdaOfflineQueue({ records, online, syncing, onSync, onRetry }: PdaOfflineQueueProps) {
  const active = records.filter(isActiveQueueRecord);
  const pending = active.filter((record) => ["PENDING", "FAILED_RETRYABLE"].includes(record.status)).length;
  const sending = active.filter((record) => record.status === "SENDING").length;
  const failed = active.filter((record) => ["FAILED_RETRYABLE", "FAILED_PERMANENT"].includes(record.status)).length;
  const blockedAuth = active.filter((record) => record.status === "BLOCKED_AUTH").length;

  if (active.length === 0) return null;

  return (
    <section className="pda-offline-queue" aria-label="离线队列">
      <div className="pda-queue-heading">
        <div><strong>本机离线队列</strong><span>刷新或重启后仍保留</span></div>
        <Button icon={<SyncOutlined />} loading={syncing} disabled={!online || syncing || pending === 0} onClick={onSync}>
          重新同步
        </Button>
      </div>
      <div className="pda-queue-counts">
        <span>待同步<b>{pending}</b></span>
        <span>正在同步<b>{sending}</b></span>
        <span>同步失败<b>{failed}</b></span>
        <span>需重新登录<b>{blockedAuth}</b></span>
      </div>
      {active.some((record) => !isServerIdempotent(record)) && (
        <p className="pda-queue-risk">仓位/批次扫描接口没有服务端幂等键，将按 At-Least-Once 重试；网络中断恰好发生在服务端处理后时，存在重复提交风险。</p>
      )}
      <div className="pda-queue-records">
        {active.map((record) => (
          <article key={record.local_queue_id}>
            <div>
              <strong>{record.operation_type === "SCAN_VALUE" ? "仓位/批次扫描" : "数量确认"}</strong>
              <span>{statusCopy[record.status]} · {new Date(record.created_at).toLocaleString()}</span>
              {record.last_error && <p>{record.last_error}</p>}
            </div>
            {["FAILED_RETRYABLE", "FAILED_PERMANENT"].includes(record.status) && (
              <Button size="small" disabled={!online || syncing} onClick={() => onRetry(record.client_operation_id)}>
                重新同步
              </Button>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
