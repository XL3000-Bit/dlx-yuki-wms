import { Alert, Button, Table } from "antd";
import type { OutboundRemainingSource } from "../../types/outboundAllocation";
import {
  retainValidSourceSelection,
  workbenchSourceError,
  workbenchSourceQuantity,
} from "../../utils/outboundAllocation";
import {
  DispatchPriorityTag,
  OutboundDateCell,
} from "../DispatchIndicators";

type Props = {
  rows: OutboundRemainingSource[];
  selectedIds: number[];
  ready: boolean;
  loading: boolean;
  canAllocate: boolean;
  errorMessage: string | null;
  scrollY: number;
  onSelectionChange: (ids: number[]) => void;
  onAllocate: (row: OutboundRemainingSource) => void;
  onRefresh: () => void;
};

const balance = (
  row: OutboundRemainingSource,
  field: "pallet" | "carton" | "weight_lbs" | "cbm",
) => workbenchSourceQuantity(row, field) ?? "N/A";

export function RemainingSourceTable({
  rows,
  selectedIds,
  ready,
  loading,
  canAllocate,
  errorMessage,
  scrollY,
  onSelectionChange,
  onAllocate,
  onRefresh,
}: Props) {
  const selectable = ready && canAllocate && !errorMessage;
  const columns = [
    {
      title: "Container",
      dataIndex: "container_number",
      width: 132,
      className: "ops-key-cell",
    },
    { title: "FC", dataIndex: "fc_code", width: 68, className: "ops-key-cell" },
    { title: "Location", dataIndex: "location", width: 92 },
    {
      title: "Available PLT",
      width: 94,
      align: "right" as const,
      render: (_: unknown, row: OutboundRemainingSource) => balance(row, "pallet"),
    },
    {
      title: "Available CTN",
      width: 94,
      align: "right" as const,
      render: (_: unknown, row: OutboundRemainingSource) => balance(row, "carton"),
    },
    {
      title: "Available LB",
      width: 104,
      align: "right" as const,
      render: (_: unknown, row: OutboundRemainingSource) => balance(row, "weight_lbs"),
    },
    {
      title: "Available CBM",
      width: 104,
      align: "right" as const,
      render: (_: unknown, row: OutboundRemainingSource) => balance(row, "cbm"),
    },
    { title: "Inbound", dataIndex: "inbound_date", width: 92 },
    {
      title: "Warehouse Days",
      dataIndex: "warehouse_days",
      width: 100,
      align: "right" as const,
      render: (value: number | null | undefined) => value ?? "--",
    },
    {
      title: "Earliest Outbound",
      dataIndex: "earliest_outbound_date",
      width: 112,
      render: (value: string | null | undefined, row: OutboundRemainingSource) => (
        <OutboundDateCell value={value} days={row.outbound_days_remaining} />
      ),
    },
    {
      title: "Priority",
      dataIndex: "dispatch_priority",
      width: 96,
      render: (value: string | null | undefined) => (
        <DispatchPriorityTag value={value} />
      ),
    },
    {
      title: "",
      width: 96,
      fixed: "right" as const,
      render: (_: unknown, row: OutboundRemainingSource) => (
        <Button
          className="source-allocate-button"
          size="small"
          disabled={!selectable || !!workbenchSourceError(row)}
          onClick={() => onAllocate(row)}
        >
          Drag BOL
        </Button>
      ),
    },
  ];

  return (
    <>
      {errorMessage && (
        <Alert
          type="error"
          showIcon
          message={errorMessage}
          action={<Button onClick={onRefresh}>Refresh sources</Button>}
        />
      )}
      <Table<OutboundRemainingSource>
        className="dispatch-dense-table remaining-source-table"
        size="small"
        sticky
        pagination={false}
        rowKey="id"
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) =>
            onSelectionChange(
              retainValidSourceSelection(
                keys.map((key) => Number(key)),
                rows,
                selectable,
              ),
            ),
          getCheckboxProps: (row) => ({
            disabled: !selectable || !!workbenchSourceError(row),
          }),
        }}
        dataSource={rows}
        columns={columns}
        scroll={{ x: 1250, y: scrollY }}
        locale={{
          emptyText: loading
            ? "Loading source inventory..."
            : errorMessage || "No remaining source inventory",
        }}
      />
    </>
  );
}
