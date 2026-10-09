import { InboxOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Progress,
  Select,
  Space,
  Statistic,
  Steps,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { importContainerTracking } from "../api/containerTracking";
import {
  confirmImport,
  getImportProgress,
  getValidationResult,
  inspectWorkbook,
  previewProfile,
  validateImportAsync,
  type ImportModule,
} from "../api/imports";
import { getWarehouses } from "../api/masterData";
import { useCurrentUser } from "../hooks/usePermissions";
import type { ImportSummary, ImportValidationResult, WorkbookInspection } from "../types/imports";
import type { Warehouse } from "../types/masterData";

type SlotId = "tracking" | "ol" | "ds" | "outbound";

interface SlotConfig {
  id: SlotId;
  step: number;
  title: string;
  fileHint: string;
  module?: ImportModule;
  profile?: string;
  sheetHint: string;
}

const SLOTS: SlotConfig[] = [
  { id: "tracking", step: 0, title: "1. Container Tracking", fileHint: "01_container_tracking.csv", sheetHint: "CSV" },
  { id: "ol", step: 1, title: "2. OL inbound", fileHint: "02_ol_inbound.csv", module: "inbound", profile: "WEST_COAST_4_0_OL", sheetHint: "OL / CSV" },
  { id: "ds", step: 2, title: "3. DS / FBA", fileHint: "03b_ds_lines.csv", module: "fba", profile: "WEST_COAST_4_0_DS", sheetHint: "DS / CSV" },
  { id: "outbound", step: 3, title: "4. Outbound headers", fileHint: "03a_outbound_header.csv", module: "outbound", profile: "WEST_COAST_4_0_OUTBOUND", sheetHint: "Outbound / CSV" },
];

interface SlotState {
  file?: File;
  inspection?: WorkbookInspection;
  jobId?: number;
  mapping?: Record<string, string>;
  validation?: ImportValidationResult;
  result?: ImportSummary | Record<string, unknown>;
  progress?: number;
  status: "idle" | "ready" | "validating" | "validated" | "done" | "error";
  message?: string;
}

const emptySlot = (): SlotState => ({ status: "idle" });

async function waitForValidation(jobId: number, onProgress: (pct: number) => void) {
  for (let attempt = 0; attempt < 2400; attempt += 1) {
    const current = await getImportProgress(jobId);
    onProgress(current.progress_percent);
    if (current.status === "READY" || current.status === "VALIDATED") return getValidationResult(jobId);
    if (current.status === "FAILED") throw new Error("Validation failed");
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error("Validation timed out");
}

export function AdminDataUploadPage() {
  const me = useCurrentUser();
  const [warehouses, setWarehouses] = useState<Warehouse[]>([]);
  const [warehouseId, setWarehouseId] = useState<number>();
  const [autoReceive, setAutoReceive] = useState(true);
  const [inventoryOk, setInventoryOk] = useState(false);
  const [slots, setSlots] = useState<Record<SlotId, SlotState>>({
    tracking: emptySlot(), ol: emptySlot(), ds: emptySlot(), outbound: emptySlot(),
  });

  useEffect(() => {
    getWarehouses()
      .then((rows) => {
        setWarehouses(rows);
        setWarehouseId((current) => current ?? rows[0]?.id);
      })
      .catch(() => message.error("Unable to load warehouses"));
  }, []);

  if (me.isSuccess && me.data?.role !== "ADMIN") return <Navigate to="/inbound" replace />;

  const patch = (id: SlotId, next: Partial<SlotState>) => {
    setSlots((current) => ({ ...current, [id]: { ...current[id], ...next } }));
  };
  const done = (id: SlotId) => slots[id].status === "done";

  async function stage(slot: SlotConfig, file: File) {
    patch(slot.id, { file, status: "ready", message: file.name, result: undefined, validation: undefined });
    if (slot.id === "tracking") return false;
    if (!warehouseId) {
      message.warning("Select a warehouse first");
      return false;
    }
    patch(slot.id, { status: "validating", progress: 0 });
    try {
      const inspection = await inspectWorkbook(file);
      const sheet =
        Object.entries(inspection.suggested_profiles).find(([, code]) => code === slot.profile)?.[0] ||
        inspection.sheet_names[0];
      const preview = await previewProfile(inspection.upload_token, sheet, slot.profile || "WEST_COAST_4_0_OL", warehouseId);
      await validateImportAsync(preview.job_id);
      const validation = await waitForValidation(preview.job_id, (pct) => patch(slot.id, { progress: pct }));
      patch(slot.id, {
        inspection, jobId: preview.job_id, mapping: preview.suggested_mapping, validation,
        status: "validated", progress: 100,
        message: `${validation.valid_rows} valid · ${validation.warning_rows} warn · ${validation.error_rows} error`,
      });
    } catch {
      patch(slot.id, { status: "error", message: "Preview / validate failed" });
      message.error(`${slot.title} validation failed`);
    }
    return false;
  }

  async function confirm(slot: SlotConfig) {
    const state = slots[slot.id];
    if (slot.id === "tracking") {
      if (!state.file) return;
      patch(slot.id, { status: "validating" });
      try {
        const result = await importContainerTracking(state.file);
        patch(slot.id, { status: "done", result, message: `created ${result.created ?? 0} · updated ${result.updated ?? 0}` });
        message.success("Container tracking imported");
      } catch {
        patch(slot.id, { status: "error", message: "Tracking import failed" });
        message.error("Tracking import failed. Check headers and admin permission.");
      }
      return;
    }
    if (!state.jobId || !state.mapping || !state.validation || state.validation.valid_rows === 0) {
      message.warning("Validate a file with at least one valid row first");
      return;
    }
    if (slot.id === "ds" && !done("ol")) {
      message.warning("Import OL and reconcile inventory before DS");
      return;
    }
    if (slot.id === "outbound" && (!done("ol") || !done("ds") || !inventoryOk)) {
      message.warning("Outbound stays locked until OL + DS are imported and inventory is checked");
      return;
    }
    patch(slot.id, { status: "validating" });
    try {
      const result = await confirmImport(slot.module as ImportModule, state.jobId, state.mapping, "SKIP", {
        include_warning_rows: true,
        auto_create_location: true,
        auto_receive_to_inventory: slot.id === "ol" && autoReceive,
      });
      patch(slot.id, { status: "done", result, message: `imported ${result.imported_rows} · skipped ${result.skipped_rows}` });
      message.success(`${slot.title} confirmed`);
    } catch {
      patch(slot.id, { status: "error", message: "Confirm failed" });
      message.error("Confirm failed. Duplicate file may need a different strategy, or rows have errors.");
    }
  }

  const currentStep = done("outbound") ? 4 : done("ds") ? 3 : done("ol") ? 2 : done("tracking") ? 1 : 0;

  return (
    <div className="page admin-upload">
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>Admin Data Upload</Typography.Title>
          <Typography.Text type="secondary">
            Administrator only. West Coast 4.0 pilot CSVs. Preview does not write business rows until Confirm.
          </Typography.Text>
        </div>
        <Space>
          <Select
            style={{ width: 280 }}
            value={warehouseId}
            placeholder="Warehouse"
            onChange={setWarehouseId}
            options={warehouses.map((row) => ({ value: row.id, label: `${row.warehouse_code} — ${row.warehouse_name}` }))}
          />
        </Space>
      </div>
      <div className="admin-upload-body">
        <Alert
          type="info"
          showIcon
          message="Required order: Tracking (optional) → OL → check pallet/carton → DS → check FBA → Outbound"
          description="Use files from import_out. Duplicate strategy is SKIP. Do not upload the 297 MB source workbook here."
        />
        <Steps style={{ margin: "16px 0 20px" }} current={currentStep} items={[{ title: "Tracking" }, { title: "OL" }, { title: "Inventory check" }, { title: "DS" }, { title: "Outbound" }]} />
        <Checkbox checked={autoReceive} onChange={(e) => setAutoReceive(e.target.checked)}>
          OL confirm also receives dated valid rows into inventory
        </Checkbox>
        <Checkbox style={{ marginLeft: 16 }} checked={inventoryOk} onChange={(e) => setInventoryOk(e.target.checked)}>
          I reconciled pallet / carton for the pilot containers
        </Checkbox>
        <div className="admin-upload-grid">
          {SLOTS.map((slot) => {
            const state = slots[slot.id];
            const locked =
              (slot.id === "ds" && !done("ol")) ||
              (slot.id === "outbound" && (!done("ol") || !done("ds") || !inventoryOk));
            return (
              <Card key={slot.id} size="small" title={slot.title} extra={<Tag color={state.status === "done" ? "green" : locked ? "default" : "orange"}>{state.status}</Tag>}>
                <p className="admin-upload-hint">Expected file: {slot.fileHint}</p>
                <Upload.Dragger accept=".xlsx,.csv" showUploadList={false} disabled={locked || state.status === "validating"} beforeUpload={(file) => stage(slot, file)}>
                  <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                  <p>{state.file?.name || "Drop CSV / XLSX"}</p>
                </Upload.Dragger>
                {state.status === "validating" && <Progress percent={Math.round(state.progress || 0)} style={{ marginTop: 10 }} />}
                {state.message && <p className="admin-upload-msg">{state.message}</p>}
                {state.validation && (
                  <div className="summary-row compact">
                    <Statistic title="Total" value={state.validation.total_rows} />
                    <Statistic title="Valid" value={state.validation.valid_rows} />
                    <Statistic title="Warn" value={state.validation.warning_rows} />
                    <Statistic title="Error" value={state.validation.error_rows} />
                  </div>
                )}
                {state.result && slot.id === "tracking" && (
                  <Descriptions size="small" column={2} items={Object.entries(state.result).slice(0, 6).map(([key, value]) => ({ key, label: key, children: String(value) }))} />
                )}
                {state.result && slot.id !== "tracking" && "imported_rows" in (state.result as ImportSummary) && (
                  <div className="summary-row compact">
                    <Statistic title="Imported" value={(state.result as ImportSummary).imported_rows} />
                    <Statistic title="Skipped" value={(state.result as ImportSummary).skipped_rows} />
                    <Statistic title="Errors" value={(state.result as ImportSummary).error_rows} />
                  </div>
                )}
                <div className="wizard-actions">
                  <Button type="primary" disabled={locked || state.status === "done" || (slot.id !== "tracking" && state.status !== "validated")} onClick={() => confirm(slot)}>
                    Confirm import
                  </Button>
                </div>
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}
