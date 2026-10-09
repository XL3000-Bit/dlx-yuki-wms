import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  ScanOutlined,
  StopOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Progress,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import type { InputRef } from "antd";
import axios from "axios";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  cancelScanSession,
  completeScanSession,
  confirmPick,
  createScanSession,
  getScanEvents,
  getScanSession,
  PickingExecutionSummary,
  resetPickStep,
  ScanEvent,
  ScanOperationType,
  ScanResult,
  ScanResultResponse,
  ScanSessionCreate,
  submitScan,
} from "../api/scanExecution";
import { getWarehouses } from "../api/masterData";
import { usePermission } from "../hooks/usePermissions";
import "./scanExecution.css";

const operations: { value: ScanOperationType; label: string }[] = [
  { value: "PICK", label: "Pick" },
  { value: "STAGE", label: "Stage" },
  { value: "LOAD_VERIFY", label: "Load Verify" },
];

const resultColors: Record<ScanResult, string> = {
  ACCEPTED: "success",
  DUPLICATE: "warning",
  REJECTED: "error",
  NOT_FOUND: "error",
  WRONG_WAREHOUSE: "error",
  WRONG_OUTBOUND: "error",
  WRONG_LOCATION: "error",
  PICK_SOURCE_MISMATCH: "error",
  INVALID_STATE: "default",
};

const stepLabels = {
  EXPECT_LOCATION: "SCAN LOCATION",
  EXPECT_LOT: "SCAN INVENTORY LOT",
  EXPECT_QUANTITY_CONFIRMATION: "CONFIRM QUANTITY",
  COMPLETED: "PICKING COMPLETED",
} as const;

function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg ?? "Invalid request").join("; ");
    }
  }
  return "The scan request could not be completed.";
}

function playFeedback(accepted: boolean) {
  const AudioContextClass = window.AudioContext;
  if (!AudioContextClass) return;
  const context = new AudioContextClass();
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.frequency.value = accepted ? 880 : 220;
  gain.gain.setValueAtTime(0.05, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.1);
  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + 0.1);
  oscillator.addEventListener("ended", () => void context.close());
}

function formatBusinessTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Los_Angeles",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function newClientOperationId() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `pick-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function ScanExecutionPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const permission = usePermission("manage_outbound");
  const inputRef = useRef<InputRef>(null);
  const quantityRef = useRef<InputRef>(null);
  const sessionId = Number(searchParams.get("session")) || null;
  const initialOperation = (searchParams.get("operation") as ScanOperationType) || "PICK";
  const [setupOperation, setSetupOperation] = useState<ScanOperationType>(initialOperation);
  const [scanValue, setScanValue] = useState("");
  const [quantityValue, setQuantityValue] = useState("1");
  const [pickOperationId, setPickOperationId] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<ScanResultResponse | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [recent, setRecent] = useState<ScanEvent[]>([]);
  const [sound, setSound] = useState(() => localStorage.getItem("scan-sound") !== "off");

  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const detail = useQuery({
    queryKey: ["scan-session", sessionId],
    queryFn: () => getScanSession(sessionId!),
    enabled: sessionId !== null,
  });
  const events = useQuery({
    queryKey: ["scan-session-events", sessionId],
    queryFn: () => getScanEvents(sessionId!, 20),
    enabled: sessionId !== null,
  });

  useEffect(() => {
    if (events.data) setRecent(events.data.data);
  }, [events.data]);

  const session = lastResponse?.session ?? detail.data?.session;
  const counters = lastResponse?.counters ?? detail.data?.counters;
  const pickingSummary = lastResponse?.picking_summary ?? detail.data?.picking_summary;
  const isOpen = session?.status === "OPEN";
  const isPick = session?.operation_type === "PICK";
  const expectsQuantity = isPick && pickingSummary?.current_step === "EXPECT_QUANTITY_CONFIRMATION";

  const focusCapture = useCallback((summary?: PickingExecutionSummary | null) => {
    window.requestAnimationFrame(() => {
      if (summary?.current_step === "EXPECT_QUANTITY_CONFIRMATION") {
        quantityRef.current?.focus({ cursor: "all" });
      } else {
        inputRef.current?.focus({ cursor: "all" });
      }
    });
  }, []);

  useEffect(() => {
    if (isOpen) focusCapture(pickingSummary);
  }, [focusCapture, isOpen, pickingSummary]);

  const refreshSession = (response: ScanResultResponse) => {
    setLastResponse(response);
    setRecent(response.recent_events);
    setRequestError(null);
    void queryClient.invalidateQueries({ queryKey: ["scan-session", sessionId] });
    void queryClient.invalidateQueries({ queryKey: ["scan-session-events", sessionId] });
  };

  const create = useMutation({
    mutationFn: createScanSession,
    onSuccess: (response) => {
      const next = new URLSearchParams(searchParams);
      next.set("session", String(response.session.id));
      next.set("warehouse", String(response.session.warehouse_id));
      next.set("operation", response.session.operation_type);
      setSearchParams(next, { replace: true });
      setLastResponse(null);
      setRecent([]);
      setRequestError(null);
    },
    onError: (error) => setRequestError(errorMessage(error)),
  });

  const scan = useMutation({
    mutationFn: (value: string) => submitScan(sessionId!, value),
    onSuccess: (response) => {
      refreshSession(response);
      setScanValue("");
      if (response.picking_summary?.current_step === "EXPECT_QUANTITY_CONFIRMATION") {
        setQuantityValue("1");
        setPickOperationId(newClientOperationId());
      }
      if (sound) playFeedback(response.event.result === "ACCEPTED");
      focusCapture(response.picking_summary);
    },
    onError: (error) => {
      setRequestError(errorMessage(error));
      focusCapture(pickingSummary);
    },
  });

  const pickConfirm = useMutation({
    mutationFn: ({ quantity, operationId }: { quantity: number; operationId: string }) =>
      confirmPick(sessionId!, { quantity, client_operation_id: operationId }),
    onSuccess: (response) => {
      refreshSession(response);
      setQuantityValue("1");
      setPickOperationId(null);
      if (sound) playFeedback(response.event.result === "ACCEPTED");
      focusCapture(response.picking_summary);
    },
    onError: (error) => {
      setRequestError(errorMessage(error));
      focusCapture(pickingSummary);
    },
  });

  const resetStep = useMutation({
    mutationFn: () => resetPickStep(sessionId!),
    onSuccess: (response) => {
      setLastResponse(null);
      setScanValue("");
      setQuantityValue("1");
      setPickOperationId(null);
      setRequestError(null);
      queryClient.setQueryData(["scan-session", sessionId], response);
      focusCapture(response.picking_summary);
    },
    onError: (error) => setRequestError(errorMessage(error)),
  });

  const transition = useMutation({
    mutationFn: (action: "complete" | "cancel") =>
      action === "complete" ? completeScanSession(sessionId!) : cancelScanSession(sessionId!),
    onSuccess: (response) => {
      setLastResponse(null);
      setRequestError(null);
      queryClient.setQueryData(["scan-session", sessionId], response);
    },
    onError: (error) => setRequestError(errorMessage(error)),
  });

  const submitScanValue = () => {
    const value = scanValue.trim();
    if (!value || !sessionId || !isOpen || expectsQuantity || scan.isPending || !permission.allowed) return;
    scan.mutate(value);
  };

  const submitQuantity = () => {
    const quantity = Number(quantityValue);
    if (
      !sessionId ||
      !isOpen ||
      !expectsQuantity ||
      !Number.isFinite(quantity) ||
      quantity <= 0 ||
      pickConfirm.isPending ||
      !permission.allowed
    ) {
      if (!Number.isFinite(quantity) || quantity <= 0) setRequestError("Pick quantity must be greater than zero.");
      return;
    }
    const operationId = pickOperationId ?? newClientOperationId();
    if (!pickOperationId) setPickOperationId(operationId);
    pickConfirm.mutate({ quantity, operationId });
  };

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !isOpen) return;
      event.preventDefault();
      setRequestError(null);
      if (
        isPick &&
        pickingSummary &&
        pickingSummary.current_step !== "EXPECT_LOCATION" &&
        pickingSummary.current_step !== "COMPLETED" &&
        !resetStep.isPending
      ) {
        resetStep.mutate();
        return;
      }
      setScanValue("");
      focusCapture(pickingSummary);
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [focusCapture, isOpen, isPick, pickingSummary, resetStep]);

  const initialValues = useMemo<Partial<ScanSessionCreate>>(
    () => ({
      warehouse_id: Number(searchParams.get("warehouse")) || undefined,
      operation_type: initialOperation,
      outbound_id: Number(searchParams.get("outbound_id")) || undefined,
      picking_id: Number(searchParams.get("picking_id")) || undefined,
      picking_ref: searchParams.get("picking_ref") || undefined,
      load_id: Number(searchParams.get("load_id")) || undefined,
    }),
    [initialOperation, searchParams],
  );

  const columns = [
    {
      title: "Time",
      dataIndex: "scanned_at",
      width: 105,
      render: (value: string) => formatBusinessTime(value),
    },
    { title: "Value", dataIndex: "raw_value", ellipsis: true, width: 170 },
    {
      title: "Result",
      dataIndex: "result",
      width: 170,
      render: (value: ScanResult) => <Tag color={resultColors[value]}>{value}</Tag>,
    },
    {
      title: "Quantity",
      width: 110,
      render: (_: unknown, row: ScanEvent) =>
        row.quantity === null ? "--" : `${row.quantity} ${row.quantity_unit ?? ""}`,
    },
    {
      title: "Reference",
      width: 180,
      render: (_: unknown, row: ScanEvent) =>
        row.reference_value ?? row.matched_entity_type ?? "--",
    },
    { title: "Message", dataIndex: "message", ellipsis: true },
  ];

  const startNew = () => {
    const next = new URLSearchParams(searchParams);
    next.delete("session");
    setSearchParams(next, { replace: true });
    setLastResponse(null);
    setRecent([]);
    setRequestError(null);
    setScanValue("");
    setQuantityValue("1");
    setPickOperationId(null);
  };

  const pickPercent = pickingSummary?.required_qty
    ? Math.min(100, Math.round((pickingSummary.picked_qty / pickingSummary.required_qty) * 100))
    : 0;

  return (
    <div className="page scan-page">
      <div className="page-heading scan-heading">
        <div>
          <Typography.Title level={4}>Scan Execution</Typography.Title>
          <Typography.Text type="secondary">
            Keyboard-wedge capture for pick, stage, and load verification
          </Typography.Text>
        </div>
        <Space>
          <Typography.Text type="secondary">Sound</Typography.Text>
          <Switch
            checked={sound}
            onChange={(checked) => {
              setSound(checked);
              localStorage.setItem("scan-sound", checked ? "on" : "off");
            }}
          />
          {sessionId && <Button onClick={startNew}>New Session</Button>}
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              void detail.refetch();
              void events.refetch();
            }}
            disabled={!sessionId}
          >
            Refresh
          </Button>
        </Space>
      </div>

      {permission.isError && <Alert type="error" showIcon message="Unable to verify your scan permission." />}
      {!permission.isLoading && !permission.allowed && (
        <Alert
          type="warning"
          showIcon
          message="Read only"
          description="Manage Outbound permission is required to create a session or submit scans."
        />
      )}
      {requestError && (
        <Alert closable type="error" showIcon message={requestError} onClose={() => setRequestError(null)} />
      )}

      {!sessionId ? (
        <div className="scan-setup-wrap">
          <Card title="Start scan session" className="scan-setup-card">
            <Form<ScanSessionCreate>
              layout="vertical"
              initialValues={initialValues}
              onFinish={(values) => {
                if (values.operation_type === "PICK") {
                  create.mutate({
                    warehouse_id: values.warehouse_id,
                    operation_type: "PICK",
                    picking_ref: values.picking_ref?.trim(),
                  });
                } else {
                  create.mutate(values);
                }
              }}
            >
              <div className="scan-setup-grid">
                <Form.Item name="operation_type" label="Operation" rules={[{ required: true }]}>
                  <Select options={operations} onChange={setSetupOperation} />
                </Form.Item>
                <Form.Item name="warehouse_id" label="Warehouse" rules={[{ required: true }]}>
                  <Select
                    loading={warehouses.isLoading}
                    placeholder="Select warehouse"
                    options={(warehouses.data ?? []).map((warehouse) => ({
                      value: warehouse.id,
                      label: `${warehouse.warehouse_code} — ${warehouse.warehouse_name}`,
                    }))}
                  />
                </Form.Item>
                {setupOperation === "PICK" ? (
                  <Form.Item
                    name="picking_ref"
                    label="Picking No."
                    rules={[{ required: true, message: "Scan or enter a Picking No." }]}
                  >
                    <Input autoFocus placeholder="Scan or enter Picking No." maxLength={24} />
                  </Form.Item>
                ) : (
                  <>
                    <Form.Item name="outbound_id" label="Related Outbound ID">
                      <InputNumber min={1} precision={0} placeholder="Optional" />
                    </Form.Item>
                    <Form.Item name="picking_id" label="Related Picking ID">
                      <InputNumber min={1} precision={0} placeholder="Optional" />
                    </Form.Item>
                    <Form.Item name="load_id" label="Related Load ID">
                      <InputNumber min={1} precision={0} placeholder="Optional" />
                    </Form.Item>
                  </>
                )}
              </div>
              {setupOperation === "PICK" && (
                <Alert
                  className="scan-setup-note"
                  type="info"
                  showIcon
                  message="The Picking No. binds the outbound automatically. Numeric database IDs are not accepted for Pick mode."
                />
              )}
              {warehouses.isError && <Alert type="error" showIcon message="Warehouse list could not be loaded." />}
              <Button
                type="primary"
                htmlType="submit"
                icon={<ScanOutlined />}
                loading={create.isPending}
                disabled={!permission.allowed || warehouses.isError}
              >
                Start Session
              </Button>
            </Form>
          </Card>
        </div>
      ) : detail.isLoading ? (
        <div className="scan-state">Loading scan session…</div>
      ) : detail.isError || !session ? (
        <div className="scan-state">
          <Alert
            type="error"
            showIcon
            message="Scan session is unavailable"
            description={errorMessage(detail.error)}
          />
        </div>
      ) : (
        <div className="scan-workbench">
          <div className="scan-session-bar">
            <Space size="middle" wrap>
              <Typography.Text strong>{session.session_no}</Typography.Text>
              <Tag color={session.status === "OPEN" ? "processing" : "default"}>{session.status}</Tag>
              <span>{session.operation_type}</span>
              <span>Warehouse #{session.warehouse_id}</span>
              {pickingSummary ? (
                <>
                  <Typography.Text strong>{pickingSummary.picking_no}</Typography.Text>
                  <span>{pickingSummary.outbound_no}</span>
                  <Tag>{pickingSummary.picking_status}</Tag>
                </>
              ) : (
                <>
                  {session.outbound_id && <span>OB #{session.outbound_id}</span>}
                  {session.picking_id && <span>Picking #{session.picking_id}</span>}
                  {session.load_id && <span>Load #{session.load_id}</span>}
                </>
              )}
            </Space>
            <Space>
              <Button
                icon={<StopOutlined />}
                danger
                disabled={!isOpen || !permission.allowed}
                loading={transition.isPending}
                onClick={() => transition.mutate("cancel")}
              >
                Cancel Session
              </Button>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                disabled={!isOpen || !permission.allowed}
                loading={transition.isPending}
                onClick={() => transition.mutate("complete")}
              >
                {pickingSummary && pickingSummary.remaining_qty > 0 ? "End Partial Session" : "Complete Session"}
              </Button>
            </Space>
          </div>

          {isPick && pickingSummary ? (
            <div className="pick-execution-panel">
              <div className="pick-progress-card">
                <div className="pick-progress-head">
                  <div>
                    <Typography.Text type="secondary">Current step</Typography.Text>
                    <Typography.Title level={3}>{stepLabels[pickingSummary.current_step]}</Typography.Title>
                  </div>
                  <Tag color={pickingSummary.current_step === "COMPLETED" ? "success" : "processing"}>
                    {pickingSummary.quantity_unit}
                  </Tag>
                </div>
                <Progress percent={pickPercent} status={pickPercent === 100 ? "success" : "active"} />
                <div className="pick-metrics">
                  <Statistic title="Required" value={pickingSummary.required_qty} />
                  <Statistic title="Picked" value={pickingSummary.picked_qty} valueStyle={{ color: "#389e0d" }} />
                  <Statistic title="Remaining" value={pickingSummary.remaining_qty} valueStyle={{ color: "#d46b08" }} />
                  <Statistic title="Locations" value={pickingSummary.locations_visited} />
                  <Statistic title="Lots Picked" value={pickingSummary.lots_picked} />
                </div>
              </div>

              <div className="pick-source-card">
                <div><span>Location</span><strong>{pickingSummary.current_location_code ?? "Waiting for scan"}</strong></div>
                <div><span>Inventory Lot</span><strong>{pickingSummary.current_lot_no ?? "Waiting for scan"}</strong></div>
                <div><span>Item Remaining</span><strong>{pickingSummary.current_item_remaining_qty ?? "--"}</strong></div>
                <div><span>Available to Pick</span><strong>{pickingSummary.current_item_available_qty ?? "--"}</strong></div>
              </div>
            </div>
          ) : (
            <div className="scan-counters">
              <Statistic title="Accepted" value={counters?.accepted ?? 0} valueStyle={{ color: "#389e0d" }} />
              <Statistic title="Rejected" value={counters?.rejected ?? 0} valueStyle={{ color: "#cf1322" }} />
              <Statistic title="Duplicate" value={counters?.duplicate ?? 0} valueStyle={{ color: "#d46b08" }} />
              <Statistic title="Total" value={counters?.total ?? 0} />
            </div>
          )}

          <div className="scan-capture">
            {expectsQuantity ? (
              <div className="pick-quantity-row">
                <Input
                  className="scan-input pick-quantity-input"
                  ref={quantityRef}
                  value={quantityValue}
                  inputMode="decimal"
                  onChange={(event) => setQuantityValue(event.target.value)}
                  onPressEnter={submitQuantity}
                  disabled={!isOpen || !permission.allowed || pickConfirm.isPending}
                  addonAfter={pickingSummary?.quantity_unit}
                  aria-label="Confirmed pick quantity"
                />
                <Button
                  className="pick-confirm-button"
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  loading={pickConfirm.isPending}
                  disabled={!isOpen || !permission.allowed}
                  onClick={submitQuantity}
                >
                  Confirm Pick
                </Button>
                <Button icon={<UndoOutlined />} loading={resetStep.isPending} onClick={() => resetStep.mutate()}>
                  Rescan
                </Button>
              </div>
            ) : (
              <Input
                className="scan-input"
                ref={inputRef}
                autoFocus
                prefix={<ScanOutlined />}
                value={scanValue}
                onChange={(event) => setScanValue(event.target.value)}
                onPressEnter={submitScanValue}
                disabled={!isOpen || !permission.allowed || pickingSummary?.current_step === "COMPLETED"}
                placeholder={
                  pickingSummary?.current_step === "EXPECT_LOCATION"
                    ? "Scan location code…"
                    : pickingSummary?.current_step === "EXPECT_LOT"
                      ? "Scan inventory lot number…"
                      : isOpen
                        ? "Scan barcode or reference…"
                        : `Session ${session.status.toLowerCase()}`
                }
                aria-label="Scan barcode or reference"
              />
            )}
            <Typography.Text type="secondary">
              Enter to submit · Esc to {isPick && pickingSummary?.current_step !== "EXPECT_LOCATION" ? "restart current pick" : "clear"}
            </Typography.Text>
          </div>

          {lastResponse && (
            <Alert
              className="scan-result-alert"
              showIcon
              icon={lastResponse.event.result === "ACCEPTED" ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
              type={lastResponse.event.result === "ACCEPTED" ? "success" : "warning"}
              message={
                <Space>
                  <Tag color={resultColors[lastResponse.event.result]}>{lastResponse.event.result}</Tag>
                  <span>{lastResponse.event.message}</span>
                </Space>
              }
            />
          )}

          <div className="scan-history">
            <Typography.Title level={5}>Recent execution events</Typography.Title>
            <Table<ScanEvent>
              className="dense-table"
              rowKey="id"
              columns={columns}
              dataSource={recent}
              loading={events.isLoading}
              pagination={false}
              size="small"
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No events in this session" /> }}
              scroll={{ x: 950, y: "calc(100dvh - 620px)" }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
