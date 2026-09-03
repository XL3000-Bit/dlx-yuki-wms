// @ts-nocheck
import {
  CheckOutlined,
  CloseCircleOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import {
  Button,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTableScrollHeight } from "../hooks/useTableScrollHeight";
import {
  allocateOutbound,
  cancelOutbound,
  completeOutbound,
  confirmOutbound,
  createOutbound,
  dispatchOutbound,
  exceptionOutbound,
  exportOutbounds,
  exportOutboundSelected,
  getOutboundDispatchReadiness,
  getOutboundWorkbench,
  getOutboundWorkbenchDetail,
  releaseOutbound,
  resolveOutbound,
  runOutboundWorkbenchBatch,
  updateOutboundSchedule,
} from "../api/outbound";
import { generateBol, generatePicking } from "../api/pickingBol";
import { getCarriers, getCustomers, getWarehouses } from "../api/masterData";
import { EntityDocuments } from "../components/EntityDocuments";
import { createLoad } from "../api/loads";
import { ImportWizard } from "../components/ImportWizard";
import {
  OutboundSplitLayout,
  OutboundVerticalSplitLayout,
  type OutboundSplitLayoutHandle,
  type OutboundVerticalSplitLayoutHandle,
} from "../components/outbound-workbench/OutboundSplitLayout";
import { DispatchCommandBar } from "../components/outbound-workbench/DispatchCommandBar";
import {
  DispatchPriorityTag,
  DispatchReadinessTag,
  OutboundDateCell,
} from "../components/DispatchIndicators";

const statuses = [
  "New",
  "On Hold",
  "In Progress",
  "Confirmed",
  "Dispatched",
  "Completed",
  "Canceled",
  "Exception",
];
const colors = {
  New: "blue",
  "On Hold": "gold",
  "In Progress": "processing",
  Confirmed: "cyan",
  Dispatched: "purple",
  Completed: "green",
  Canceled: "default",
  Exception: "red",
};

const n = (value: any) =>
  value == null
    ? "N/A"
    : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });

export function OutboundDispatchWorkbenchPage() {
  const [sp, setSp] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [exceptionOpen, setExceptionOpen] = useState(false);
  const [rightHidden, setRightHidden] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const horizontalSplitRef = useRef<OutboundSplitLayoutHandle>(null);
  const verticalSplitRef = useRef<OutboundVerticalSplitLayoutHandle>(null);
  const [ordersTableRef, ordersScrollY] = useTableScrollHeight(98, 128);
  const [allocationTableRef, allocationScrollY] = useTableScrollHeight(48, 44);
  const [sourceTableRef, sourceScrollY] = useTableScrollHeight(48, 64);

  const params = useMemo(
    () => ({
      page: Number(sp.get("page") || 1),
      per_page: Number(sp.get("per_page") || 20),
      q:
        sp.get("q") ||
        sp.get("id") ||
        sp.get("bol_no") ||
        sp.get("container_number") ||
        sp.get("delivery_location") ||
        sp.get("transfer_address") ||
        sp.get("reference_search") ||
        sp.get("del_ref") ||
        sp.get("agent_code") ||
        undefined,
      status: sp.get("status") ? Number(sp.get("status")) : undefined,
      ob_type: sp.get("ob_type") || undefined,
      warehouse_id: sp.get("warehouse")
        ? Number(sp.get("warehouse"))
        : undefined,
      carrier_id: sp.get("carrier_id")
        ? Number(sp.get("carrier_id"))
        : undefined,
      sort_by: sp.get("sort_by") || "created_at",
      sort_order: sp.get("sort_order") || "desc",
    }),
    [sp],
  );

  const list = useQuery({
    queryKey: ["outbound-workbench", params],
    queryFn: () => getOutboundWorkbench(params),
  });
  const warehouses = useQuery({
    queryKey: ["warehouses"],
    queryFn: getWarehouses,
  });
  const carriers = useQuery({ queryKey: ["carriers"], queryFn: getCarriers });
  const selectedId = Number(sp.get("selected_ob") || 0) || selectedIds[0];
  const detail = useQuery({
    queryKey: ["outbound-workbench-detail", selectedId],
    queryFn: () => getOutboundWorkbenchDetail(selectedId),
    enabled: !!selectedId,
  });
  const rows = list.data?.data || [];
  const selected =
    detail.data?.basic || rows.find((row: any) => row.id === selectedId);
  const selectedRows = rows.filter((row: any) => selectedIds.includes(row.id));
  const lifecycleRows = selectedIds.length
    ? selectedRows
    : selected
      ? [selected]
      : [];
  const lifecycleIds = lifecycleRows.map((row: any) => row.id);
  const canRunLifecycle = (name: string) =>
    lifecycleRows.some((row: any) => row.allowed_actions?.[name]);

  const patch = (values: any) => {
    const query = new URLSearchParams(sp);
    Object.entries(values).forEach(([key, value]) =>
      value === undefined || value === ""
        ? query.delete(key)
        : query.set(key, String(value)),
    );
    setSp(query, { replace: true });
  };
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["outbound-workbench"] });
    qc.invalidateQueries({ queryKey: ["outbound-workbench-detail"] });
  };
  const action = useMutation({
    mutationFn: ({ name, id }: any) =>
      ({
        confirm: confirmOutbound,
        dispatch: dispatchOutbound,
        complete: completeOutbound,
        cancel: cancelOutbound,
        resolve: resolveOutbound,
        picking: generatePicking,
        bol: generateBol,
      })[name](id),
    onSuccess: () => {
      message.success("Operation completed");
      refresh();
    },
    onError: () => message.error("Operation rejected"),
  });
  const batchAction = useMutation({
    mutationFn: async ({ name, ids }: any) => {
      if (name === "dispatch") {
        const readiness = await Promise.all(
          ids.map(async (id: number) => ({
            id,
            readiness: await getOutboundDispatchReadiness(id),
          })),
        );
        const blocked = readiness.filter(
          ({ readiness: result }: any) => result.status !== "READY",
        );
        if (blocked.length) {
          const error: any = new Error("Dispatch blocked by readiness checks");
          error.blocked = blocked;
          throw error;
        }
      }
      return runOutboundWorkbenchBatch(name, ids);
    },
    onSuccess: (result: any) => {
      const failedResults = result.results.filter(
        (item: any) => item.status === "failed",
      );
      if (result.failed > 0) {
        Modal.warning({
          title:
            result.successful > 0
              ? "Batch completed with blocked outbound orders"
              : "Batch operation blocked",
          content: (
            <div>
              <p>
                Successful: {result.successful}; Failed: {result.failed}
              </p>
              <ul>
                {failedResults.map((item: any) => (
                  <li key={item.id}>
                    OB {item.id}: {item.reason || "Operation rejected"}
                  </li>
                ))}
              </ul>
            </div>
          ),
        });
      } else {
        message.success(
          `Batch operation completed for ${result.successful} outbound order${result.successful === 1 ? "" : "s"}`,
        );
      }
      refresh();
    },
    onError: (error: any) => {
      if (error.blocked?.length) {
        Modal.warning({
          title: "Dispatch blocked",
          content: (
            <ul>
              {error.blocked.flatMap(({ id, readiness }: any) =>
                readiness.blocking_reasons.map((reason: string, index: number) => (
                  <li key={`${id}-${index}`}>
                    OB {id}: {reason}
                  </li>
                )),
              )}
            </ul>
          ),
        });
        return;
      }
      message.error(error?.message || "Batch operation rejected");
    },
  });
  const runLifecycle = (name: string) => {
    if (lifecycleIds.length) batchAction.mutate({ name, ids: lifecycleIds });
  };
  const create = useMutation({
    mutationFn: createOutbound,
    onSuccess: () => {
      message.success("Outbound created");
      setCreateOpen(false);
      refresh();
    },
    onError: () => message.error("Unable to create outbound"),
  });
  const createLoadMutation = useMutation({
    mutationFn: () => {
      const chosen = rows.filter((row: any) => selectedIds.includes(row.id));
      const warehouseIds = [
        ...new Set(chosen.map((row: any) => row.warehouse_id)),
      ];
      if (warehouseIds.length !== 1)
        throw new Error("Select outbound orders from one warehouse");
      return createLoad({
        warehouse_id: warehouseIds[0],
        outbound_ids: selectedIds,
      });
    },
    onSuccess: (load: any) =>
      Modal.success({
        title: "Load created",
        content: `Load ${load.load_no} is ready.`,
        okText: "Open Load",
        onOk: () => navigate(`/loads?selected=${load.id}`),
      }),
    onError: (error: any) =>
      message.error(error?.message || "Unable to create load"),
  });

  const resetWindow = () => {
    horizontalSplitRef.current?.reset();
    verticalSplitRef.current?.reset();
  };

  const cols = [
    {
      title: "OB#",
      dataIndex: "ob_no",
      fixed: "left",
      width: 118,
      sorter: true,
      render: (value: any, row: any) => (
        <Button
          className="ops-key-link"
          type="link"
          onClick={() => patch({ selected_ob: row.id })}
        >
          {value}
        </Button>
      ),
    },
    {
      title: "Status",
      dataIndex: "status_name",
      width: 88,
      render: (value: any) => <Tag color={colors[value]}>{value}</Tag>,
    },
    { title: "FC", dataIndex: "fc_code", width: 72, className: "ops-key-cell" },
    {
      title: "Plan PLT",
      dataIndex: "planned_pallet_qty",
      width: 78,
      align: "right",
      render: n,
    },
    {
      title: "Alloc PLT",
      dataIndex: "allocated_pallet_qty",
      width: 78,
      align: "right",
      render: n,
    },
    {
      title: "Picked PLT",
      dataIndex: "picked_pallet_qty",
      width: 82,
      align: "right",
      render: n,
    },
    {
      title: "Done PLT",
      dataIndex: "completed_pallet_qty",
      width: 78,
      align: "right",
      render: n,
    },
    {
      title: "Remain PLT",
      dataIndex: "remaining_pallet_qty",
      width: 84,
      align: "right",
      render: n,
    },
    {
      title: "Earliest Outbound",
      dataIndex: "earliest_outbound_date",
      width: 112,
      render: (value: any, row: any) => (
        <OutboundDateCell value={value} days={row.outbound_days_remaining} />
      ),
    },
    {
      title: "Priority",
      dataIndex: "dispatch_priority",
      width: 96,
      render: (value: any) =>
        value ? <DispatchPriorityTag value={value} /> : "--",
    },
    {
      title: "Readiness",
      dataIndex: "dispatch_readiness",
      width: 108,
      render: (value: any, row: any) =>
        value ? (
          <DispatchReadinessTag
            value={value}
            reasons={row.blocking_reasons}
          />
        ) : (
          "--"
        ),
    },
    { title: "Carrier", dataIndex: "carrier", width: 116 },
    {
      title: "FBA",
      dataIndex: "fba_no",
      width: 112,
      className: "ops-key-cell",
    },
    {
      title: "ST",
      dataIndex: "st_number",
      width: 108,
      className: "ops-key-cell",
    },
    {
      title: "LB",
      dataIndex: "allocated_weight_lbs",
      width: 94,
      align: "right",
      render: n,
    },
    {
      title: "CBM",
      dataIndex: "allocated_cbm",
      width: 78,
      align: "right",
      render: n,
    },
    { title: "APT", dataIndex: "delivery_appointment_time", width: 150 },
  ];

  const allocCols = [
    {
      title: "Lot",
      dataIndex: "lot_no",
      width: 112,
      className: "ops-key-cell",
    },
    {
      title: "Container",
      dataIndex: "container_number",
      width: 132,
      className: "ops-key-cell",
    },
    { title: "Source", dataIndex: "source_type", width: 82 },
    {
      title: "PLT",
      dataIndex: "allocated_pallet_qty",
      width: 64,
      align: "right",
      render: n,
    },
    {
      title: "Picked",
      dataIndex: "picked_pallet_qty",
      width: 72,
      align: "right",
      render: n,
    },
    {
      title: "Done",
      dataIndex: "completed_pallet_qty",
      width: 68,
      align: "right",
      render: n,
    },
    {
      title: "Remain",
      width: 74,
      align: "right",
      render: (_: any, row: any) =>
        n(
          Number(row.allocated_pallet_qty || 0) -
            Number(row.completed_pallet_qty || 0),
        ),
    },
    {
      title: "",
      width: 72,
      render: (_: any, row: any) => (
        <Button
          size="small"
          onClick={() => releaseOutbound(selectedId, row.id, {}).then(refresh)}
        >
          Release
        </Button>
      ),
    },
  ];

  const sourceCols = [
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
      align: "right",
      render: (_: any, row: any) =>
        n(row.available_pallet_qty ?? row.remaining_pallet_qty),
    },
    { title: "Inbound", dataIndex: "inbound_date", width: 92 },
    {
      title: "Warehouse Days",
      dataIndex: "warehouse_days",
      width: 100,
      align: "right",
      render: (value: any) => value ?? "--",
    },
    {
      title: "Earliest Outbound",
      dataIndex: "earliest_outbound_date",
      width: 112,
      render: (value: any, row: any) => (
        <OutboundDateCell value={value} days={row.outbound_days_remaining} />
      ),
    },
    {
      title: "Priority",
      dataIndex: "dispatch_priority",
      width: 96,
      render: (value: any) => <DispatchPriorityTag value={value} />,
    },
    {
      title: "",
      width: 78,
      fixed: "right",
      render: (_: any, row: any) => (
        <Button
          className="source-allocate-button"
          size="small"
          onClick={() =>
            allocateOutbound(selectedId, {
              inventory_lot_id: row.inventory_lot_id || row.id,
              fba_allocation_id: row.fba_allocation_id,
              pallet_qty: row.available_pallet_qty || row.remaining_pallet_qty,
              carton_qty: row.available_carton_qty || row.remaining_carton_qty,
              weight_lbs: row.weight_lbs || 0,
              cbm: row.cbm || 0,
            }).then(refresh)
          }
        >
          Allocate
        </Button>
      ),
    },
  ];

  const summary = list.data?.summary || {};
  const selectedPallets = selectedRows.reduce(
    (total: number, row: any) => total + Number(row.allocated_pallet_qty || 0),
    0,
  );

  const upperPanel = (
    <section
      className="dispatch-panel dispatch-panel-upper"
      aria-labelledby="outbound-region-allocation"
    >
      <div className="panel-title">
        <h3 id="outbound-region-allocation">
          Region 2: Allocation / Picking / BOL
        </h3>
        <Space size={6} wrap>
          <Button
            disabled={!selected?.allowed_actions?.picking}
            onClick={() => action.mutate({ name: "picking", id: selected.id })}
          >
            Generate Picking
          </Button>
          <Button
            disabled={!selected?.allowed_actions?.bol}
            onClick={() => action.mutate({ name: "bol", id: selected.id })}
          >
            Generate BOL
          </Button>
          <Button onClick={() => setScheduleOpen(true)}>Schedule / APT</Button>
        </Space>
      </div>
      <div
        ref={allocationTableRef}
        className="dispatch-table-host dispatch-panel-table-host"
      >
        <Table
          className="dispatch-dense-table"
          size="small"
          sticky
          pagination={false}
          rowKey="id"
          dataSource={detail.data?.allocations || []}
          columns={allocCols}
          scroll={{ x: 690, y: allocationScrollY }}
          locale={{
            emptyText: detail.isLoading
              ? "Loading allocations..."
              : "No active allocations",
          }}
        />
      </div>
      <div className="dispatch-summary">
        Total {n(selected?.allocated_pallet_qty)} PLT <span>/</span>{" "}
        {n(selected?.allocated_carton_qty)} CTN <span>/</span>{" "}
        {n(selected?.allocated_weight_lbs)} LB <span>/</span>{" "}
        {n(selected?.allocated_cbm)} CBM
      </div>
    </section>
  );

  const lowerPanel = (
    <section
      className="dispatch-panel dispatch-panel-lower"
      aria-labelledby="outbound-region-source"
    >
      <div className="panel-title">
        <h3 id="outbound-region-source">Region 3: Remaining Source</h3>
      </div>
      {selected && <EntityDocuments relation={{ outbound_id: selected.id }} />}
      <div
        ref={sourceTableRef}
        className="dispatch-table-host dispatch-panel-table-host"
      >
        <Table
          className="dispatch-dense-table remaining-source-table"
          size="small"
          sticky
          pagination={false}
          rowKey="id"
          dataSource={detail.data?.remaining_sources || []}
          columns={sourceCols}
          scroll={{ x: 870, y: sourceScrollY }}
          locale={{
            emptyText: detail.isLoading
              ? "Loading source inventory..."
              : "No remaining source inventory",
          }}
        />
      </div>
    </section>
  );

  return (
    <div className="dispatch-workbench">
      <OutboundSplitLayout
        left={
          <div className="dispatch-left-workspace">
            <DispatchCommandBar
              values={{
                id: sp.get("id") || "",
                status: sp.get("status") || "",
                ob_type: sp.get("ob_type") || "",
                warehouse: sp.get("warehouse") || "",
                carrier_id: sp.get("carrier_id") || "",
                bol_no: sp.get("bol_no") || "",
                container_number: sp.get("container_number") || "",
                delivery_location: sp.get("delivery_location") || "",
                reference_search: sp.get("reference_search") || "",
                del_ref: sp.get("del_ref") || "",
                agent_code: sp.get("agent_code") || "",
                pickup_location: sp.get("pickup_location") || "",
                redirect_location: sp.get("redirect_location") || "",
              }}
              warehouses={warehouses.data || []}
              carriers={carriers.data || []}
              selectedCount={selectedIds.length}
              canConfirm={canRunLifecycle("confirm")}
              canCancel={canRunLifecycle("cancel")}
              canException={!!selected?.allowed_actions?.exception}
              canDispatch={canRunLifecycle("dispatch")}
              rightHidden={rightHidden}
              onChange={patch}
              onRefresh={() => list.refetch()}
              onResetFilters={() => setSp(new URLSearchParams())}
              onResetWindow={resetWindow}
              onToggleRight={() => horizontalSplitRef.current?.toggleRight()}
              onCreate={() => setCreateOpen(true)}
              onConfirm={() => runLifecycle("confirm")}
              onCancel={() => runLifecycle("cancel")}
              onDispatch={() => runLifecycle("dispatch")}
              onException={() => setExceptionOpen(true)}
              onDelete={() => {
                if (!selected) return;
                Modal.confirm({
                  title: "Delete / cancel this OB?",
                  content: "Yuki has no hard-delete API. This runs Cancel.",
                  onOk: () => action.mutate({ name: "cancel", id: selected.id }),
                });
              }}
            />
            <div className="workbench-heading">
              <div className="workbench-title">
                <Typography.Title level={4}>Outbound Dispatch</Typography.Title>
                <Typography.Text type="secondary">
                  Outbound Execution Workbench
                </Typography.Text>
              </div>
              <div className="workbench-toolbar">
                <div className="toolbar-group toolbar-secondary">
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={() => list.refetch()}
                  >
                    Refresh
                  </Button>
                  <Button onClick={() => exportOutbounds(params)}>
                    Export Current Filter
                  </Button>
                  <Button
                    icon={<DownloadOutlined />}
                    disabled={!selectedIds.length}
                    onClick={() => exportOutboundSelected(selectedIds)}
                  >
                    Export Selected
                  </Button>
                  <Button
                    disabled={!selectedIds.length}
                    loading={createLoadMutation.isPending}
                    onClick={() => createLoadMutation.mutate()}
                  >
                    Create Load
                  </Button>
                  <Button
                    icon={<UploadOutlined />}
                    onClick={() => setImportOpen(true)}
                  >
                    Import Excel
                  </Button>
                </div>
                <div className="toolbar-group toolbar-primary">
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={() => setCreateOpen(true)}
                  >
                    Create OB
                  </Button>
                </div>
              </div>
            </div>
            <div className="dispatch-filters">
              <Input
                allowClear
                value={sp.get("q") || ""}
                placeholder="Search OB / BOL / Container / FBA / ST / PO / FC"
                onChange={(event) => patch({ q: event.target.value, page: 1 })}
              />
              <Select
                allowClear
                value={params.status}
                placeholder="Status"
                onChange={(value) => patch({ status: value, page: 1 })}
                options={statuses.map((status, index) => ({
                  value: index,
                  label: status,
                }))}
              />
              <Select
                allowClear
                value={params.warehouse_id}
                placeholder="Warehouse"
                onChange={(value) => patch({ warehouse: value, page: 1 })}
                options={(warehouses.data || []).map((warehouse: any) => ({
                  value: warehouse.id,
                  label: warehouse.warehouse_code,
                }))}
              />
              <Button onClick={() => setSp(new URLSearchParams())}>
                Reset
              </Button>
            </div>
            <section
              className="dispatch-orders"
              aria-labelledby="outbound-region-orders"
            >
              <h3 id="outbound-region-orders">Region 1: Outbound Orders</h3>
              <div
                ref={ordersTableRef}
                className="dispatch-table-host dispatch-orders-table-host"
              >
                <Table
                  className="dispatch-dense-table"
                  size="small"
                  sticky
                  scroll={{ x: 1730, y: ordersScrollY }}
                  rowKey="id"
                  loading={list.isLoading}
                  dataSource={rows}
                  columns={cols}
                  locale={{
                    emptyText: list.isError
                      ? "Unable to load outbound orders"
                      : "No outbound orders match the current filters",
                  }}
                  rowSelection={{
                    selectedRowKeys: selectedIds,
                    onChange: (ids: any) => setSelectedIds(ids),
                  }}
                  pagination={{
                    current: params.page,
                    pageSize: params.per_page,
                    total: list.data?.meta?.total,
                    showSizeChanger: true,
                    pageSizeOptions: [20, 50, 100],
                    showTotal: (total) => `${total} OB`,
                  }}
                  onChange={(pagination: any, _, sorter: any) =>
                    patch({
                      page: pagination.current,
                      per_page: pagination.pageSize,
                      ...(sorter?.field
                        ? {
                            sort_by: sorter.field,
                            sort_order:
                              sorter.order === "ascend" ? "asc" : "desc",
                          }
                        : {}),
                    })
                  }
                />
              </div>
              <div className="dispatch-summary">
                Total {summary.ob_count || 0} OB <span>/</span>{" "}
                {n(summary.total_pallet_qty)} PLT <span>/</span>{" "}
                {n(summary.allocated_carton_qty)} CTN <span>/</span>{" "}
                {n(summary.allocated_weight_lbs)} LB <span>/</span>{" "}
                {n(summary.allocated_cbm)} CBM
                {selectedIds.length > 0 && (
                  <>
                    {" "}
                    <span>/</span> Selected {selectedIds.length} OB /{" "}
                    {n(selectedPallets)} PLT ({n((selectedPallets / 26) * 100)}
                    %)
                  </>
                )}
              </div>
            </section>
            <div className="dispatch-actions">
              <div className="dispatch-lifecycle-buttons">
                <Button
                  disabled={!canRunLifecycle("confirm")}
                  onClick={() => runLifecycle("confirm")}
                >
                  Confirm
                </Button>
                <Button
                  disabled={!canRunLifecycle("dispatch")}
                  onClick={() => runLifecycle("dispatch")}
                >
                  Dispatch
                </Button>
                <Button
                  disabled={!canRunLifecycle("complete")}
                  onClick={() => runLifecycle("complete")}
                >
                  Complete
                </Button>
                <Button
                  danger
                  disabled={!canRunLifecycle("cancel")}
                  onClick={() => runLifecycle("cancel")}
                >
                  Cancel
                </Button>
                <Button
                  disabled={!selected?.allowed_actions?.exception}
                  onClick={() =>
                    action.mutate({ name: "exception", id: selected.id })
                  }
                >
                  Exception
                </Button>
              </div>
              <span className="dispatch-stage">
                {selected
                  ? `Stage: ${selected.status_name} / Trailer ${n(selected.allocated_pallet_qty)} / 26 PLT`
                  : "Select an OB to enable lifecycle actions"}
              </span>
            </div>
          </div>
        }
        right={
          <div className="dispatch-right">
            {selected ? (
              <OutboundVerticalSplitLayout
                top={upperPanel}
                bottom={lowerPanel}
              />
            ) : (
              <div className="dispatch-empty">
                <div>
                  <div className="empty-icon">&#9678;</div>
                  <h3>Select an outbound order</h3>
                  <p>
                    View allocations, picking, BOL, and remaining inventory for
                    the selected OB.
                  </p>
                  <small>Click an OB# from Outbound Orders to begin.</small>
                </div>
              </div>
            )}
          </div>
        }
      />
      <ScheduleDrawer
        open={scheduleOpen}
        selected={selected}
        onClose={() => setScheduleOpen(false)}
        onDone={() => {
          setScheduleOpen(false);
          refresh();
        }}
      />
      <CreateDrawer
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onDone={() => {
          setCreateOpen(false);
          refresh();
        }}
      />
      <ImportWizard
        module="outbound"
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onComplete={refresh}
      />
    </div>
  );
}

function ScheduleDrawer({ open, selected, onClose, onDone }: any) {
  const [form] = Form.useForm();
  return (
    <Drawer
      title="Schedule / Appointment"
      open={open}
      onClose={onClose}
      extra={
        <Button type="primary" onClick={() => form.submit()}>
          Save
        </Button>
      }
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={async (values) => {
          await updateOutboundSchedule(selected.id, values);
          message.success("Schedule saved");
          onDone();
        }}
      >
        <Form.Item name="carrier_id" label="Carrier">
          <Input />
        </Form.Item>
        <Form.Item name="schedule_pickup_at" label="Scheduled Pickup">
          <Input />
        </Form.Item>
        <Form.Item name="delivery_appointment_time" label="Appointment Time">
          <Input />
        </Form.Item>
        <Form.Item name="driver_name" label="Driver">
          <Input />
        </Form.Item>
        <Form.Item name="truck_number" label="Truck Number">
          <Input />
        </Form.Item>
        <Form.Item name="trailer_number" label="Trailer Number">
          <Input />
        </Form.Item>
        <Form.Item name="remark" label="Remark">
          <Input.TextArea />
        </Form.Item>
      </Form>
    </Drawer>
  );
}

function CreateDrawer({ open, onClose, onDone }: any) {
  const [form] = Form.useForm();
  const warehouses = useQuery({
    queryKey: ["warehouses"],
    queryFn: getWarehouses,
  });
  const customers = useQuery({
    queryKey: ["customers"],
    queryFn: getCustomers,
  });
  const carriers = useQuery({ queryKey: ["carriers"], queryFn: getCarriers });
  return (
    <Drawer
      title="Create OB"
      open={open}
      onClose={onClose}
      extra={
        <Button type="primary" onClick={() => form.submit()}>
          Create
        </Button>
      }
    >
      <Form form={form} layout="vertical" onFinish={onDone}>
        <Form.Item
          name="warehouse_id"
          label="Warehouse"
          rules={[{ required: true }]}
        >
          <Select
            options={(warehouses.data || []).map((item: any) => ({
              value: item.id,
              label: item.warehouse_code,
            }))}
          />
        </Form.Item>
        <Form.Item name="customer_id" label="Customer">
          <Select
            allowClear
            options={(customers.data || []).map((item: any) => ({
              value: item.id,
              label: item.customer_name,
            }))}
          />
        </Form.Item>
        <Form.Item name="carrier_id" label="Carrier">
          <Select
            allowClear
            options={(carriers.data || []).map((item: any) => ({
              value: item.id,
              label: item.carrier_name,
            }))}
          />
        </Form.Item>
        <Form.Item name="ob_type" initialValue="STANDARD" label="OB Type">
          <Select
            options={["STANDARD", "FBA", "TRANSFER", "PICKUP", "OTHER"].map(
              (value) => ({ value, label: value }),
            )}
          />
        </Form.Item>
        <Form.Item name="reference_no" label="Reference">
          <Input />
        </Form.Item>
      </Form>
    </Drawer>
  );
}
