// @ts-nocheck
import {
  CheckOutlined,
  CloseCircleOutlined,
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
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
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
  getOutboundWorkbench,
  getOutboundWorkbenchDetail,
  releaseOutbound,
  resolveOutbound,
  updateOutboundSchedule,
} from "../api/outbound";
import { generateBol, generatePicking } from "../api/pickingBol";
import { getCarriers, getCustomers, getWarehouses } from "../api/masterData";
import { EntityDocuments } from "../components/EntityDocuments";
import { createLoad } from "../api/loads";
import { ImportWizard } from "../components/ImportWizard";
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
  const [detailPanelsVisible, setDetailPanelsVisible] = useState(true);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

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
      if (chosen.length !== selectedIds.length)
        throw new Error("Selected outbound orders are no longer available on this page");
      const warehouseIdsForRows = chosen.map(
        (row: any) =>
          (warehouses.data || []).find(
            (warehouse: any) =>
              warehouse.warehouse_code.trim().toLowerCase() ===
              String(row.warehouse).trim().toLowerCase(),
          )?.id,
      );
      if (warehouseIdsForRows.some((id: any) => id == null))
        throw new Error("Unable to resolve the warehouse for every selected outbound order");
      const warehouseIds = [...new Set(warehouseIdsForRows)];
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
    { title: "Carrier", dataIndex: "carrier", width: 116 },
    { title: "Loading Team", dataIndex: "loading_team", width: 104 },
    { title: "Truck Type", dataIndex: "truck_type", width: 94 },
    { title: "Delivery Type", dataIndex: "delivery_type", width: 106 },
    { title: "Pickup", dataIndex: "pickup_location", width: 132 },
    {
      title: "Scheduled Pickup",
      dataIndex: "schedule_pickup_at",
      width: 150,
    },
    {
      title: "Appointment",
      dataIndex: "delivery_appointment_time",
      width: 150,
    },
    { title: "OB Type", dataIndex: "ob_type", width: 88 },
    { title: "Destination / FC", dataIndex: "fc_code", width: 112, className: "ops-key-cell" },
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
      render: (value: any) =>
        value ? <DispatchReadinessTag value={value} /> : "--",
    },
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
    { title: "Reference", dataIndex: "reference_no", width: 132 },
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
  const selectedRows = rows.filter((row: any) => selectedIds.includes(row.id));
  const selectedPallets = selectedRows.reduce(
    (total: number, row: any) => total + Number(row.allocated_pallet_qty || 0),
    0,
  );

  const upperPanel = (
    <section className="dispatch-panel dispatch-section-card dispatch-panel-upper">
      <div className="panel-title">
        <div>
          <h3>Outbound BOL / Allocated Shipment List</h3>
          <span className="panel-subtitle">
            {selected ? `${selected.ob_no} · ${selected.status_name}` : "Select an outbound order"}
          </span>
        </div>
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
      <div className="dispatch-table-host dispatch-panel-table-host">
        <Table
          className="dispatch-dense-table"
          size="small"
          sticky
          pagination={false}
          rowKey="id"
          dataSource={detail.data?.allocations || []}
          columns={allocCols}
          scroll={{ x: 760, y: 210 }}
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
    <section className="dispatch-panel dispatch-section-card dispatch-panel-lower">
      <div className="panel-title">
        <div>
          <h3>Remaining Shipment / Inventory List</h3>
          <span className="panel-subtitle">Available source inventory that can be allocated to the selected OB</span>
        </div>
        <Space size={6}>
          <Button icon={<ReloadOutlined />} onClick={() => detail.refetch()}>Refresh</Button>
        </Space>
      </div>
      {selected && <EntityDocuments relation={{ outbound_id: selected.id }} />}
      <div className="dispatch-table-host dispatch-panel-table-host">
        <Table
          className="dispatch-dense-table remaining-source-table"
          size="small"
          sticky
          pagination={false}
          rowKey="id"
          dataSource={detail.data?.remaining_sources || []}
          columns={sourceCols}
          scroll={{ x: 960, y: 230 }}
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
      <div className="dispatch-page-scroll">
        <div className="dispatch-breadcrumb">Home <span>/</span> Outbound <span>/</span> Dispatch</div>
        <div className="workbench-heading dispatch-sticky-heading">
          <div className="workbench-title">
            <Typography.Title level={4}>Outbound Dispatch</Typography.Title>
            <Typography.Text type="secondary">Dispatch, BOL allocation, picking and shipment execution</Typography.Text>
          </div>
          <div className="workbench-toolbar">
            <div className="toolbar-group dispatch-batch-actions">
              <Button danger icon={<CloseCircleOutlined />} disabled={!selected?.allowed_actions?.cancel} onClick={() => action.mutate({ name: "cancel", id: selected.id })}>Cancel</Button>
              <Button icon={<CheckOutlined />} disabled={!selected?.allowed_actions?.dispatch} onClick={() => action.mutate({ name: "dispatch", id: selected.id })}>Dispatch Current OB</Button>
              <Button icon={<ExclamationCircleOutlined />} disabled={!selected?.allowed_actions?.exception} onClick={() => setExceptionOpen(true)}>Exception</Button>
              <Button loading={createLoadMutation.isPending} disabled={!selectedIds.length} onClick={() => createLoadMutation.mutate()}>Create Load</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>Create OB</Button>
            </div>
          </div>
        </div>

        <section className="dispatch-filter-card">
          <div className="dispatch-filter-grid">
            <label><span>Search</span><Input allowClear value={sp.get("q") || ""} placeholder="OB / BOL / Container / FBA / ST / PO / FC" onChange={(event) => patch({ q: event.target.value, page: 1 })} /></label>
            <label><span>Status</span><Select allowClear value={params.status} placeholder="All statuses" onChange={(value) => patch({ status: value, page: 1 })} options={statuses.map((status, index) => ({ value: index, label: status }))} /></label>
            <label><span>OB Type</span><Select allowClear value={params.ob_type} placeholder="All types" onChange={(value) => patch({ ob_type: value, page: 1 })} options={["STANDARD", "FBA", "TRANSFER", "PICKUP", "OTHER"].map((value) => ({ value, label: value }))} /></label>
            <label><span>Warehouse</span><Select allowClear value={params.warehouse_id} placeholder="All warehouses" onChange={(value) => patch({ warehouse: value, page: 1 })} options={(warehouses.data || []).map((warehouse: any) => ({ value: warehouse.id, label: warehouse.warehouse_code }))} /></label>
            <label><span>Carrier</span><Select showSearch optionFilterProp="label" allowClear value={params.carrier_id} placeholder="All carriers" onChange={(value) => patch({ carrier_id: value, page: 1 })} options={(carriers.data || []).map((carrier: any) => ({ value: carrier.id, label: carrier.carrier_name }))} /></label>
            <div className="dispatch-filter-actions">
              <Button icon={<ReloadOutlined />} onClick={() => refresh()}>Refresh</Button>
              <Button onClick={() => setSp(new URLSearchParams())}>Reset</Button>
              <Button icon={detailPanelsVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />} onClick={() => setDetailPanelsVisible((value) => !value)}>{detailPanelsVisible ? "Hide BOL Lists" : "Show BOL Lists"}</Button>
            </div>
          </div>
        </section>

        <section className="dispatch-orders dispatch-section-card">
          <div className="panel-title">
            <div><h3>Outbound Dispatch List</h3><span className="panel-subtitle">Select an OB number to load its allocated and remaining shipment pools</span></div>
            <Space size={6} wrap>
              <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>Refresh</Button>
              <Button onClick={() => exportOutbounds(params)}>Export Filter</Button>
              <Button icon={<DownloadOutlined />} disabled={!selectedIds.length} onClick={() => exportOutboundSelected(selectedIds)}>Export Selected</Button>
              <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>Import Excel</Button>
            </Space>
          </div>
          <div className="dispatch-table-host dispatch-orders-table-host">
            <Table className="dispatch-dense-table" size="small" sticky scroll={{ x: 2280, y: 310 }} rowKey="id" loading={list.isLoading} dataSource={rows} columns={cols}
              locale={{ emptyText: list.isError ? "Unable to load outbound orders" : "No outbound orders match the current filters" }}
              rowClassName={(row: any) => row.id === selectedId ? "dispatch-row-selected" : ""}
              onRow={(row: any) => ({ onClick: () => patch({ selected_ob: row.id }) })}
              rowSelection={{ selectedRowKeys: selectedIds, onChange: (ids: any) => setSelectedIds(ids) }}
              pagination={{ current: params.page, pageSize: params.per_page, total: list.data?.meta?.total, showSizeChanger: true, pageSizeOptions: [20, 50, 100], showTotal: (total) => `${total} OB` }}
              onChange={(pagination: any, _: any, sorter: any) => patch({ page: pagination.current, per_page: pagination.pageSize, ...(sorter?.field ? { sort_by: sorter.field, sort_order: sorter.order === "ascend" ? "asc" : "desc" } : {}) })}
            />
          </div>
          <div className="dispatch-summary">Total {summary.ob_count || 0} OB <span>/</span> {n(summary.total_pallet_qty)} PLT <span>/</span> {n(summary.allocated_carton_qty)} CTN <span>/</span> {n(summary.allocated_weight_lbs)} LB <span>/</span> {n(summary.allocated_cbm)} CBM{selectedIds.length > 0 && <> <span>/</span> Selected {selectedIds.length} OB / {n(selectedPallets)} PLT</>}</div>
          <div className="dispatch-actions">
            <div className="dispatch-lifecycle-buttons">
              <Button disabled={!selected?.allowed_actions?.confirm} onClick={() => action.mutate({ name: "confirm", id: selected.id })}>Confirm</Button>
              <Button disabled={!selected?.allowed_actions?.dispatch} onClick={() => action.mutate({ name: "dispatch", id: selected.id })}>Dispatch</Button>
              <Button disabled={!selected?.allowed_actions?.complete} onClick={() => action.mutate({ name: "complete", id: selected.id })}>Complete</Button>
              <Button danger disabled={!selected?.allowed_actions?.cancel} onClick={() => action.mutate({ name: "cancel", id: selected.id })}>Cancel</Button>
              <Button disabled={!selected?.allowed_actions?.exception} onClick={() => setExceptionOpen(true)}>Exception</Button>
              {selected?.status_name === "Exception" && <Button onClick={() => action.mutate({ name: "resolve", id: selected.id })}>Resolve Exception</Button>}
            </div>
            <span className="dispatch-stage">{selected ? `Selected ${selected.ob_no} · ${selected.status_name} · ${n(selected.allocated_pallet_qty)} PLT` : "Select an OB to enable lifecycle actions"}</span>
          </div>
        </section>

        {detailPanelsVisible && (selected ? <div className="dispatch-detail-stack">{upperPanel}{lowerPanel}</div> : <div className="dispatch-empty"><div><div className="empty-icon">&#9678;</div><h3>Select an outbound order</h3><p>Its allocated BOL/shipment list and remaining inventory will appear here.</p></div></div>)}
      </div>
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
        onCreate={(values: any) => create.mutate(values)}
      />
      <ExceptionDrawer open={exceptionOpen} selected={selected} onClose={() => setExceptionOpen(false)} onDone={() => { setExceptionOpen(false); refresh(); }} />
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

function ExceptionDrawer({ open, selected, onClose, onDone }: any) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const submit = async (values: any) => {
    if (!selected?.id) return;
    setSaving(true);
    try {
      await exceptionOutbound(selected.id, values.reason, values.remark);
      message.success("Outbound moved to exception");
      form.resetFields();
      onDone();
    } catch {
      message.error("Unable to mark outbound as exception");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer title={`Outbound Exception${selected?.ob_no ? ` · ${selected.ob_no}` : ""}`} open={open} onClose={onClose}
      extra={<Button type="primary" danger loading={saving} onClick={() => form.submit()}>Confirm Exception</Button>}>
      <Form form={form} layout="vertical" onFinish={submit}>
        <Form.Item name="reason" label="Exception Reason" rules={[{ required: true, message: "Enter an exception reason" }]}>
          <Input placeholder="Short operational reason" />
        </Form.Item>
        <Form.Item name="remark" label="Remark">
          <Input.TextArea rows={4} placeholder="Optional investigation context" />
        </Form.Item>
      </Form>
    </Drawer>
  );
}

function CreateDrawer({ open, onClose, onCreate }: any) {
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
      <Form form={form} layout="vertical" onFinish={onCreate}>
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
