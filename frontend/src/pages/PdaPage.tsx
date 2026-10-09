import {
  ArrowLeftOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  LogoutOutlined,
  ScanOutlined,
  SoundOutlined,
  WifiOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Form, Input, Select, Switch } from "antd";
import type { InputRef } from "antd";
import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  completeScanSession,
  confirmPick,
  createScanSession,
  getScanEvents,
  getScanSession,
  resetPickStep,
  ScanEvent,
  PickStep,
  ScanResultResponse,
  submitScan,
} from "../api/scanExecution";
import { CameraScanner } from "../components/pda/CameraScanner";
import { PdaOfflineQueue } from "../components/pda/PdaOfflineQueue";
import {
  cameraScanKey,
  isScannableStep,
  scanResultClass,
  shouldSubmitCameraScan,
  type ScanInputSource,
} from "../components/pda/cameraScanPolicy";
import { enqueueUnique, pdaQueueRepository } from "../components/pda/offlineQueueDb";
import {
  isActiveQueueRecord,
  makePdaQueueRecord,
  type PdaQueueFailure,
  type PdaQueueRecord,
} from "../components/pda/offlineQueuePolicy";
import { PdaQueueSynchronizer } from "../components/pda/offlineQueueSync";
import { getWarehouses } from "../api/masterData";
import { usePermission } from "../hooks/usePermissions";
import { useAuthStore } from "../stores/auth";
import { PdaOperations, type PdaMode } from "./PdaOperations";
import "./pda.css";

function apiError(error: unknown) {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg ?? "Invalid request").join("; ");
  }
  return "操作未完成，请检查网络后重试。";
}

function queueFailure(error: unknown): PdaQueueFailure {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    return {
      httpStatus: error.response?.status,
      errorCode: error.code,
      message: typeof detail === "string" ? detail : error.message || "同步失败",
    };
  }
  return { message: error instanceof Error ? error.message : "同步失败" };
}

async function sendQueuedOperation(record: PdaQueueRecord) {
  const queuedSessionId = record.payload.session_id;
  if (record.operation_type === "SCAN_VALUE") {
    return submitScan(queuedSessionId, String(record.payload.value ?? ""))
      .catch((requestError) => Promise.reject(queueFailure(requestError)));
  }
  return confirmPick(queuedSessionId, {
    quantity: Number(record.payload.quantity),
    client_operation_id: record.client_operation_id,
  }).catch((requestError) => Promise.reject(queueFailure(requestError)));
}

function operationId() {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `pda-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function beep(ok: boolean) {
  const AudioContextClass = window.AudioContext;
  if (!AudioContextClass) return;
  const context = new AudioContextClass();
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.frequency.value = ok ? 920 : 180;
  gain.gain.setValueAtTime(0.06, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + (ok ? 0.09 : 0.22));
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + (ok ? 0.09 : 0.22));
  oscillator.addEventListener("ended", () => void context.close());
}

const stepCopy = {
  EXPECT_LOCATION: { eyebrow: "第 1 步", title: "扫描库位", hint: "请扫描货物所在库位码" },
  EXPECT_LOT: { eyebrow: "第 2 步", title: "扫描库存批次", hint: "请扫描该库位中的 Lot No." },
  EXPECT_QUANTITY_CONFIRMATION: { eyebrow: "第 3 步", title: "确认拣货数量", hint: "输入本次实际拣货数量" },
  COMPLETED: { eyebrow: "任务完成", title: "拣货已完成", hint: "所有要求数量均已确认" },
} as const;

function PickingPdaPage({ onHome }: { onHome: () => void }) {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const permission = usePermission("manage_outbound");
  const logout = useAuthStore((state) => state.logout);
  const scanRef = useRef<InputRef>(null);
  const qtyRef = useRef<InputRef>(null);
  const scanInFlightRef = useRef(false);
  const lastAcceptedCameraScanRef = useRef<string | null>(null);
  const sessionId = Number(params.get("session")) || null;
  const [scanValue, setScanValue] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [clientOperationId, setClientOperationId] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<ScanResultResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queueNotice, setQueueNotice] = useState<string | null>(null);
  const [queueRecords, setQueueRecords] = useState<PdaQueueRecord[]>([]);
  const [queueSyncing, setQueueSyncing] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [sound, setSound] = useState(() => localStorage.getItem("pda-sound") !== "off");

  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const detail = useQuery({
    queryKey: ["scan-session", sessionId],
    queryFn: () => getScanSession(sessionId!),
    enabled: sessionId !== null,
  });
  const events = useQuery({
    queryKey: ["scan-session-events", sessionId, "pda"],
    queryFn: () => getScanEvents(sessionId!, 6),
    enabled: sessionId !== null,
  });

  const session = lastResponse?.session ?? detail.data?.session;
  const summary = lastResponse?.picking_summary ?? detail.data?.picking_summary;
  const recent = lastResponse?.recent_events ?? events.data?.data ?? [];
  const isOpen = session?.status === "OPEN";
  const expectsQuantity = summary?.current_step === "EXPECT_QUANTITY_CONFIRMATION";
  const currentStep = summary ? stepCopy[summary.current_step] : null;
  const progress = summary?.required_qty
    ? Math.min(100, Math.round((summary.picked_qty / summary.required_qty) * 100))
    : 0;

  const focusCurrent = useCallback((quantityStep = expectsQuantity) => {
    window.requestAnimationFrame(() => {
      if (quantityStep) qtyRef.current?.focus({ cursor: "all" });
      else scanRef.current?.focus({ cursor: "all" });
    });
  }, [expectsQuantity]);

  const loadQueue = useCallback(async () => {
    try {
      setQueueRecords(await pdaQueueRepository.list());
    } catch {
      setError("无法读取本机离线队列；本设备可能禁用了 IndexedDB。离线操作未保存。");
    }
  }, []);

  useEffect(() => {
    if (isOpen) focusCurrent();
  }, [focusCurrent, isOpen]);

  const refresh = (response: ScanResultResponse) => {
    setLastResponse(response);
    setError(null);
    void queryClient.invalidateQueries({ queryKey: ["scan-session", sessionId] });
    void queryClient.invalidateQueries({ queryKey: ["scan-session-events", sessionId] });
  };

  const currentSessionIdRef = useRef(sessionId);
  currentSessionIdRef.current = sessionId;
  const loadQueueRef = useRef(loadQueue);
  loadQueueRef.current = loadQueue;
  const queueSuccessRef = useRef<(record: PdaQueueRecord, response: unknown) => void>(() => undefined);
  queueSuccessRef.current = (record, response) => {
    const result = response as ScanResultResponse;
    if (record.payload.session_id === currentSessionIdRef.current) {
      refresh(result);
      if (record.operation_type === "SCAN_VALUE") {
        setScanValue("");
        if (record.payload.source === "camera" && result.event.result === "ACCEPTED") {
          lastAcceptedCameraScanRef.current = cameraScanKey(record.payload.step as PickStep, record.payload.value ?? "");
        }
        const quantityStep = result.picking_summary?.current_step === "EXPECT_QUANTITY_CONFIRMATION";
        if (quantityStep) {
          setQuantity("1");
          setClientOperationId(operationId());
        }
        if (sound) beep(result.event.result === "ACCEPTED");
        focusCurrent(quantityStep);
      } else {
        setQuantity("1");
        setClientOperationId(null);
        focusCurrent(false);
      }
    }
    setQueueNotice("同步成功：服务器已确认本机队列操作。");
  };
  const queueSynchronizerRef = useRef<PdaQueueSynchronizer | null>(null);
  if (!queueSynchronizerRef.current) {
    queueSynchronizerRef.current = new PdaQueueSynchronizer(pdaQueueRepository, sendQueuedOperation, {
      onSuccess: (record, response) => queueSuccessRef.current(record, response),
      onChange: () => loadQueueRef.current(),
      canSend: () => navigator.onLine,
    });
  }

  const runQueueSync = useCallback(async () => {
    if (!navigator.onLine) {
      setError("当前离线，队列仍保存在本机。联网后再同步。");
      return;
    }
    setQueueSyncing(true);
    setQueueNotice(null);
    try {
      const completed = await queueSynchronizerRef.current!.syncNow();
      if (completed === 0) setQueueNotice("未完成同步；记录已保留，请查看队列状态和失败原因。");
    } finally {
      setQueueSyncing(false);
      await loadQueue();
    }
  }, [loadQueue]);

  const retryQueueRecord = async (clientOperationId: string) => {
    if (!navigator.onLine) return;
    setQueueSyncing(true);
    try {
      await queueSynchronizerRef.current!.retry(clientOperationId);
    } finally {
      setQueueSyncing(false);
      await loadQueue();
    }
  };

  useEffect(() => {
    const handleOnline = () => {
      setOnline(true);
      void runQueueSync();
    };
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [runQueueSync]);

  useEffect(() => {
    queueSynchronizerRef.current?.resume();
    void (async () => {
      await pdaQueueRepository.recoverInterrupted();
      await pdaQueueRepository.requeueBlockedAuth();
      await pdaQueueRepository.pruneCompleted();
      await loadQueue();
      if (navigator.onLine) await runQueueSync();
    })().catch(() => setError("无法恢复本机离线队列，请保持在线并联系管理员。"));
    return () => queueSynchronizerRef.current?.dispose();
  }, [loadQueue, runQueueSync]);

  const create = useMutation({
    mutationFn: createScanSession,
    onSuccess: (response) => {
      setParams({ session: String(response.session.id) }, { replace: true });
      setLastResponse(null);
      setError(null);
    },
    onError: (requestError) => setError(apiError(requestError)),
  });

  const reset = useMutation({
    mutationFn: () => resetPickStep(sessionId!),
    onSuccess: () => {
      setLastResponse(null);
      setQuantity("1");
      setClientOperationId(null);
      lastAcceptedCameraScanRef.current = null;
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["scan-session", sessionId] });
      focusCurrent(false);
    },
    onError: (requestError) => setError(apiError(requestError)),
  });

  const finish = useMutation({
    mutationFn: () => completeScanSession(sessionId!),
    onSuccess: () => {
      setLastResponse(null);
      void queryClient.invalidateQueries({ queryKey: ["scan-session", sessionId] });
    },
    onError: (requestError) => setError(apiError(requestError)),
  });

  const lastEvent = recent[0];
  const resultClass = scanResultClass(lastEvent?.result);
  const warehouseName = useMemo(() => {
    const warehouse = warehouses.data?.find((item) => item.id === session?.warehouse_id);
    return warehouse ? warehouse.warehouse_code : session ? `#${session.warehouse_id}` : "";
  }, [session, warehouses.data]);

  const sessionQueueBlocked = queueRecords.some((record) =>
    isActiveQueueRecord(record) && record.payload.session_id === sessionId,
  );

  const submitScanCode = async (rawValue: string, source: ScanInputSource) => {
    const value = rawValue.trim();
    const step = summary?.current_step;
    if (!value || !step || !isOpen || !isScannableStep(step) || scanInFlightRef.current || sessionQueueBlocked) return;
    if (source === "camera" && !shouldSubmitCameraScan({
      value,
      step,
      online,
      isOpen,
      requestInFlight: scanInFlightRef.current,
      lastAcceptedKey: lastAcceptedCameraScanRef.current,
    })) return;

    scanInFlightRef.current = true;
    const id = operationId();
    const record = makePdaQueueRecord({
      sessionId: sessionId!,
      clientOperationId: id,
      operationType: "SCAN_VALUE",
      value,
      step,
      source,
    });
    try {
      await enqueueUnique(pdaQueueRepository, record);
      setScanValue("");
      await loadQueue();
      if (navigator.onLine) await runQueueSync();
      else setQueueNotice("扫描已保存到本机，尚未写入服务器；恢复网络后将自动同步。");
    } catch {
      setError("扫描未能保存到本机；未向服务器报告成功，请勿继续作业。");
      if (sound) beep(false);
    } finally {
      scanInFlightRef.current = false;
    }
  };

  const submitScanValue = () => void submitScanCode(scanValue, "manual");

  const submitCameraValue = (value: string) => {
    setScanValue(value);
    void submitScanCode(value, "camera");
  };

  const submitQuantity = async () => {
    if (sessionQueueBlocked) return;
    const value = Number(quantity);
    if (!Number.isFinite(value) || value <= 0) {
      setError("请输入大于 0 的有效数量。");
      return;
    }
    const id = clientOperationId ?? operationId();
    setClientOperationId(id);
    const record = makePdaQueueRecord({
      sessionId: sessionId!,
      clientOperationId: id,
      operationType: "CONFIRM_PICK",
      quantity: value,
    });
    try {
      await enqueueUnique(pdaQueueRepository, record);
      await loadQueue();
      if (navigator.onLine) await runQueueSync();
      else setQueueNotice("数量确认已保存到本机，尚未写入服务器；恢复网络后将自动同步。");
    } catch {
      setError("数量确认未能保存到本机；未向服务器报告成功。");
    }
  };

  const startNew = () => {
    if (sessionQueueBlocked) {
      setError("当前作业仍有未同步记录；请先完成同步或处理失败记录，再开始新作业。");
      return;
    }
    setParams({ mode: "pick" }, { replace: true });
    setLastResponse(null);
    setScanValue("");
    setQuantity("1");
    lastAcceptedCameraScanRef.current = null;
    setError(null);
  };

  return (
    <main className="pda-shell">
      <header className="pda-header">
        <div className="pda-brand"><span>Warehouse</span><small>WMS · PDA</small></div>
        <div className={`pda-network ${online ? "is-online" : "is-offline"}`}>
          <WifiOutlined /> {online ? "在线" : "离线"}
        </div>
        <Button type="text" aria-label="退出登录" icon={<LogoutOutlined />} onClick={logout} />
      </header>

      {!online && <Alert banner type="warning" message="网络已断开：扫描操作可保存到本机，但尚未写入服务器。" />}
      {error && <Alert banner closable type="error" message={error} onClose={() => setError(null)} />}
      {queueNotice && <Alert banner closable type="info" message={queueNotice} onClose={() => setQueueNotice(null)} />}
      <PdaOfflineQueue
        records={queueRecords}
        online={online}
        syncing={queueSyncing}
        onSync={() => void runQueueSync()}
        onRetry={(clientOperationId) => void retryQueueRecord(clientOperationId)}
      />

      {!sessionId ? (
        <section className="pda-setup">
          <div className="pda-kicker">PICKING</div>
          <h1>开始拣货</h1>
          <p>选择仓库并扫描拣货单号，系统将自动绑定出库单。</p>
          <Form
            layout="vertical"
            onFinish={(values: { warehouse_id: number; picking_ref: string }) =>
              create.mutate({
                warehouse_id: values.warehouse_id,
                operation_type: "PICK",
                picking_ref: values.picking_ref.trim(),
              })
            }
          >
            <Form.Item name="warehouse_id" label="作业仓库" rules={[{ required: true, message: "请选择仓库" }]}>
              <Select
                size="large"
                loading={warehouses.isLoading}
                placeholder="选择仓库"
                options={(warehouses.data ?? []).map((item) => ({
                  value: item.id,
                  label: `${item.warehouse_code} · ${item.warehouse_name}`,
                }))}
              />
            </Form.Item>
            <Form.Item name="picking_ref" label="拣货单号" rules={[{ required: true, message: "请扫描或输入拣货单号" }]}>
              <Input size="large" autoFocus prefix={<ScanOutlined />} placeholder="扫描 Picking No." autoComplete="off" />
            </Form.Item>
            {permission.isError && <Alert type="error" message="无法验证当前账号权限。" />}
            {!permission.isLoading && !permission.allowed && <Alert type="warning" message="当前账号缺少出库作业权限。" />}
            <Button
              block
              size="large"
              type="primary"
              htmlType="submit"
              loading={create.isPending}
              disabled={!online || !permission.allowed || warehouses.isError}
            >
              进入作业
            </Button>
            <Button block size="large" onClick={onHome}>返回功能菜单</Button>
          </Form>
        </section>
      ) : detail.isLoading ? (
        <div className="pda-centered">正在载入作业…</div>
      ) : detail.isError || !session || !summary ? (
        <section className="pda-centered">
          <CloseCircleFilled className="pda-state-icon" />
          <h2>无法打开此作业</h2>
          <p>{apiError(detail.error)}</p>
          <Button onClick={startNew}>返回</Button>
        </section>
      ) : (
        <>
          <section className="pda-taskbar">
            <Button type="text" icon={<ArrowLeftOutlined />} onClick={startNew}>新作业</Button>
            <div><strong>{summary.picking_no}</strong><span>{summary.outbound_no} · {warehouseName}</span></div>
            <label><SoundOutlined /><Switch size="small" checked={sound} onChange={(checked) => {
              setSound(checked);
              localStorage.setItem("pda-sound", checked ? "on" : "off");
            }} /></label>
          </section>

          <section className="pda-progress">
            <div className="pda-progress-copy"><span>拣货进度</span><strong>{progress}%</strong></div>
            <div className="pda-progress-track"><i style={{ width: `${progress}%` }} /></div>
            <div className="pda-progress-values">
              <span>已拣 <b>{summary.picked_qty}</b></span>
              <span>剩余 <b>{summary.remaining_qty}</b> {summary.quantity_unit}</span>
            </div>
          </section>

          <section className={`pda-action-card ${resultClass}`}>
            <div className="pda-step"><span>{currentStep?.eyebrow}</span><h1>{currentStep?.title}</h1><p>{currentStep?.hint}</p></div>
            {summary.current_step === "COMPLETED" ? (
              <div className="pda-complete"><CheckCircleFilled /><span>单据数量已全部完成</span></div>
            ) : expectsQuantity ? (
              <div className="pda-capture">
                <Input
                  ref={qtyRef}
                  size="large"
                  className="pda-primary-input"
                  inputMode="decimal"
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  onPressEnter={submitQuantity}
                  addonAfter={summary.quantity_unit}
                  disabled={queueSyncing || sessionQueueBlocked}
                />
                <Button block size="large" type="primary" loading={queueSyncing} disabled={sessionQueueBlocked} onClick={() => void submitQuantity()}>
                  {online ? "确认数量" : "保存到本机"}
                </Button>
                <Button block size="large" disabled={!online || sessionQueueBlocked} onClick={() => reset.mutate()} loading={reset.isPending}>重新扫描库位</Button>
              </div>
            ) : (
              <div className="pda-capture">
                <Input
                  ref={scanRef}
                  size="large"
                  className="pda-primary-input"
                  prefix={<ScanOutlined />}
                  value={scanValue}
                  onChange={(event) => setScanValue(event.target.value)}
                  onPressEnter={submitScanValue}
                  placeholder={summary.current_step === "EXPECT_LOCATION" ? "扫描库位码" : "扫描 Lot No."}
                  autoComplete="off"
                  disabled={queueSyncing || sessionQueueBlocked}
                />
                <Button block size="large" type="primary" loading={queueSyncing} disabled={!scanValue.trim() || sessionQueueBlocked} onClick={submitScanValue}>
                  {online ? "提交扫描" : "保存到本机"}
                </Button>
                <CameraScanner onDetected={submitCameraValue} />
              </div>
            )}
            {(summary.current_location_code || summary.current_lot_no) && (
              <div className="pda-context">
                <span>库位<strong>{summary.current_location_code ?? "—"}</strong></span>
                <span>批次<strong>{summary.current_lot_no ?? "—"}</strong></span>
                <span>本项可拣<strong>{summary.current_item_available_qty ?? "—"}</strong></span>
              </div>
            )}
          </section>

          {lastEvent && (
            <section className={`pda-feedback ${scanResultClass(lastEvent.result)}`}>
              {lastEvent.result === "ACCEPTED" ? <CheckCircleFilled /> : <CloseCircleFilled />}
              <div><strong>{lastEvent.result}</strong><span>{lastEvent.message}</span></div>
            </section>
          )}

          <section className="pda-history">
            <h2>最近记录 <span>{recent.length}</span></h2>
            {recent.length === 0 ? <p className="pda-empty">等待首次扫描</p> : recent.map((event: ScanEvent) => (
              <div className="pda-event" key={event.id}>
                <i className={event.result === "ACCEPTED" ? "is-ok" : "is-error"} />
                <div><strong>{event.reference_value || event.normalized_value || event.event_type}</strong><span>{event.message}</span></div>
                <time>{new Date(event.scanned_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>
              </div>
            ))}
          </section>

          <footer className="pda-footer">
            <Button
              block
              size="large"
              type={summary.remaining_qty === 0 ? "primary" : "default"}
              loading={finish.isPending}
              disabled={!isOpen || !online || sessionQueueBlocked}
              onClick={() => finish.mutate()}
            >
              {summary.remaining_qty === 0 ? "完成并结束会话" : "结束本次作业（部分完成）"}
            </Button>
            {!isOpen && <Button block size="large" onClick={startNew}>开始新作业</Button>}
          </footer>
        </>
      )}
    </main>
  );
}

const pdaModes: PdaMode[] = ["inbound", "outbound", "pick", "count", "move"];

export function PdaPage() {
  const [params, setParams] = useSearchParams();
  const requestedMode = params.get("mode");
  const sessionId = Number(params.get("session")) || null;
  const mode = pdaModes.includes(requestedMode as PdaMode) ? requestedMode as PdaMode : null;
  const navigate = (nextMode: PdaMode | null) => {
    const next = new URLSearchParams();
    if (nextMode) next.set("mode", nextMode);
    setParams(next, { replace: true });
  };

  if (mode === "pick" || sessionId) {
    return <PickingPdaPage onHome={() => navigate(null)} />;
  }

  return <PdaOperations mode={mode === "inbound" || mode === "outbound" || mode === "count" || mode === "move" ? mode : null} onNavigate={navigate} />;
}
