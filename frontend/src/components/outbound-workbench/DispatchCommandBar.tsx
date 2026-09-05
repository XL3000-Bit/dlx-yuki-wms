import { Button, DatePicker, Input, Select, Space } from "antd";
import "./dispatch-command.css";

const STATUSES = ["New", "On Hold", "In Progress", "Confirmed", "Dispatched", "Completed", "Canceled", "Exception"];
const TYPES = ["STANDARD", "FBA", "TRANSFER", "PICKUP", "OTHER"];

type Props = {
  values: Record<string, string>;
  warehouses: { id: number; warehouse_code: string }[];
  carriers: { id: number; carrier_name: string; carrier_code?: string }[];
  selectedCount: number;
  canConfirm?: boolean;
  canCancel?: boolean;
  canException?: boolean;
  canDispatch?: boolean;
  rightHidden?: boolean;
  onChange: (patch: Record<string, string | number | undefined>) => void;
  onRefresh: () => void;
  onResetFilters: () => void;
  onResetWindow: () => void;
  onToggleRight: () => void;
  onCreate: () => void;
  onConfirm: () => void;
  onCancel: () => void;
  onException: () => void;
  onDispatch: () => void;
  onDelete: () => void;
};

export function DispatchCommandBar(props: Props) {
  const v = props.values;
  const set = (key: string, value: string | number | undefined) => props.onChange({ [key]: value, page: 1 });
  return (
    <div className="dispatch-command">
      <div className="dispatch-command-top">
        <div className="dispatch-crumb">Home <span>/</span> Outbound <span>/</span> Dispatch</div>
        <Space size={6} wrap className="dispatch-command-actions">
          <Button danger disabled={!props.selectedCount} onClick={props.onDelete}>
            {props.selectedCount > 1 ? `Delete Selected (${props.selectedCount})` : "Delete"}
          </Button>
          <Button disabled={!props.canCancel} onClick={props.onCancel}>Cancel</Button>
          <Button disabled={!props.canConfirm} onClick={props.onConfirm}>Confirm OB</Button>
          <Button disabled={!props.canException} onClick={props.onException}>Exception</Button>
          <Button disabled={!props.canDispatch} onClick={props.onDispatch}>Dispatch</Button>
          <Button type="primary" onClick={props.onCreate}>Create OB</Button>
        </Space>
      </div>
      <div className="dispatch-unicang-filters">
        <label>ID<input value={v.id || ""} onChange={(e) => set("id", e.target.value)} /></label>
        <label>Status
          <Select allowClear value={v.status || undefined} placeholder=" " onChange={(value) => set("status", value)}
            options={STATUSES.map((label, value) => ({ value: String(value), label }))} />
        </label>
        <label>Type
          <Select allowClear value={v.ob_type || undefined} placeholder=" " onChange={(value) => set("ob_type", value)}
            options={TYPES.map((value) => ({ value, label: value }))} />
        </label>
        <label>Warehouse
          <Select allowClear value={v.warehouse || undefined} placeholder=" " onChange={(value) => set("warehouse", value)}
            options={props.warehouses.map((row) => ({ value: String(row.id), label: row.warehouse_code }))} />
        </label>
        <label>Pickup Location<input value={v.pickup_location || ""} onChange={(e) => set("pickup_location", e.target.value)} /></label>
        <label>Delivery Location<input value={v.delivery_location || ""} onChange={(e) => set("delivery_location", e.target.value)} /></label>
        <label>Carrier
          <Select allowClear value={v.carrier_id || undefined} placeholder=" " onChange={(value) => set("carrier_id", value)}
            options={props.carriers.map((row) => ({ value: String(row.id), label: row.carrier_code || row.carrier_name }))} />
        </label>
        <label>BOL#<input value={v.bol_no || ""} onChange={(e) => set("bol_no", e.target.value)} /></label>
        <label>CNTR# / IB#<input value={v.container_number || ""} onChange={(e) => set("container_number", e.target.value)} /></label>
        <label>SKD PU Date<DatePicker allowClear onChange={(_, text) => set("skd_pu_date", Array.isArray(text) ? text[0] : text)} /></label>
        <label>Redirect Location<input value={v.redirect_location || ""} onChange={(e) => set("redirect_location", e.target.value)} /></label>
        <label>ISA / FBA / REF#<input value={v.reference_search || ""} onChange={(e) => set("reference_search", e.target.value)} /></label>
        <label>DEL REF#<input value={v.del_ref || ""} onChange={(e) => set("del_ref", e.target.value)} /></label>
        <label>Agent Code<input value={v.agent_code || ""} onChange={(e) => set("agent_code", e.target.value)} /></label>
        <div className="dispatch-filter-actions">
          <Button type="primary" onClick={props.onRefresh}>Refresh</Button>
          <Button onClick={props.onResetFilters}>Reset</Button>
        </div>
      </div>
      <div className="dispatch-window-controls">
        <Button size="small" onClick={props.onResetWindow}>Reset Window</Button>
        <Button size="small" onClick={props.onToggleRight}>{props.rightHidden ? "Show OB Detail" : "Hide OB Detail"}</Button>
      </div>
    </div>
  );
}
