
import "../components/outbound-workbench/dispatch-reference.css";
import CreateDrawer from "../components/outbound-workbench/CreateOutboundDrawer";
import DispatchBolPanels from "../components/outbound-workbench/DispatchBolPanels";
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
  Checkbox,
  Popover,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
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
  exportOutboundBols,
  updateOutboundTransferCodes,
  exportOutboundSelected,
  getOutboundDispatchReadiness,
  getOutboundWorkbench,
  getOutboundWorkbenchDetail,
  releaseOutbound,
  resolveOutbound,
  runOutboundInventoryBatch,
  runOutboundWorkbenchBatch,
  updateOutboundSchedule,
} from "../api/outbound";
import { generateBol, generatePicking, downloadFile, downloadOutboundPackage } from "../api/pickingBol";
import { getCarriers, getCustomers, getWarehouses } from "../api/masterData";
import { EntityDocuments } from "../components/EntityDocuments";
import { createLoad, getLoads, attachLoadOutbounds } from "../api/loads";
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
  const [modal, modalContextHolder] = Modal.useModal();
  const [bolView, setBolView] = useState(true);
  const [showBolFilters, setShowBolFilters] = useState(true);
  const [dragBolsOpen, setDragBolsOpen] = useState(false);
  const [dragBolsRows, setDragBolsRows] = useState<any[]>([]);
  const [targetLoad, setTargetLoad] = useState<number | "new">("new");
  const [loadSearch, setLoadSearch] = useState("");
  const [loadPage, setLoadPage] = useState(1);
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferCode, setTransferCode] = useState("");
  const [transferIds, setTransferIds] = useState<number[]>([]);
  const bolColumnDefinitions: Array<[string, string, number]> = [
    ["OB#", "ob_no", 145], ["BOL#", "bol_no", 140], ["Type", "bol_type", 125],
    ["Group Status", "group_status", 130], ["Pickup Location", "pickup_location", 145],
    ["Del Code", "del_code", 125], ["Redirect Code", "redirect_code", 125],
    ["Transfer Code", "transfer_code", 140], ["Weight LB", "weight_lbs", 120],
    ["Status", "status_name", 180],
  ];
  const [bolFields, setBolFields] = useState(bolColumnDefinitions.map(([, key]) => key));
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [exceptionOpen, setExceptionOpen] = useState(false);
  const [rightHidden, setRightHidden] = useState(false);
  const [executionOpen, setExecutionOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectedAllocationIds, setSelectedAllocationIds] = useState<number[]>(
    [],
  );
  const [selectedSourceIds, setSelectedSourceIds] = useState<number[]>([]);
  const horizontalSplitRef = useRef<OutboundSplitLayoutHandle>(null);
  const verticalSplitRef = useRef<OutboundVerticalSplitLayoutHandle>(null);
  const [ordersTableRef, ordersScrollY] = useTableScrollHeight(98, 128);
  const [allocationTableRef, allocationScrollY] = useTableScrollHeight(48, 44);
  const [sourceTableRef, sourceScrollY] = useTableScrollHeight(48, 64);

  const params = useMemo(
    () => ({
      page: Number(sp.get("page") || 1),
      per_page: Number(sp.get("per_page") || 20),
      q: sp.get("q") || undefined,
      ...Object.fromEntries(["id", "bol_no", "container_number", "delivery_location", "pickup_location", "redirect_location", "reference_search", "del_ref", "agent_code", "delivery_type", "skd_pu_date"].map(key => [key, sp.get(key) || undefined])),
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
  const lifecycleRows = executionOpen
    ? selected ? [selected] : []
    : selectedIds.length
    ? selectedRows
    : selected
      ? [selected]
      : [];
  const lifecycleIds = lifecycleRows.map((row: any) => row.id);
  const canRunLifecycle = (name: string) =>
    lifecycleRows.some((row: any) => row.allowed_actions?.[name]);

  useEffect(() => {
    setSelectedAllocationIds([]);
    setSelectedSourceIds([]);
  }, [selectedId]);

  const patch = (values: any) => {
    const selectionScopeKeys = new Set([
      "page",
      "per_page",
      "q",
      "id",
      "status",
      "ob_type",
      "warehouse",
      "carrier_id",
      "bol_no",
      "container_number",
      "delivery_location",
      "reference_search",
      "del_ref",
      "agent_code",
      "pickup_location",
      "redirect_location",
      "sort_by",
      "sort_order",
    ]);
    const selectionScopeChanged = Object.keys(values).some((key) =>
      selectionScopeKeys.has(key),
    );
    if (selectionScopeChanged) {
      setSelectedIds([]);
    }
    const query = new URLSearchParams(sp);
    if (selectionScopeChanged) query.delete("selected_ob");
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
    ["cargo-bols", "inventory", "fba", "picking"].forEach(key => qc.invalidateQueries({ queryKey: [key] }));
  };
  const transferMutation = useMutation({
    mutationFn: () => updateOutboundTransferCodes(transferIds, transferCode),
    onSuccess: (result) => { message.success(`已更新 ${result.updated} 条转运代码`); setTransferOpen(false); refresh(); },
    onError: () => message.error("更新失败，请检查权限后重试"),
  });
  const downloadBols = async (ids?: number[]) => {
    try { await exportOutboundBols(params, ids); } catch { message.error("导出失败，请重试"); }
  };
  const documentPackage = useMutation({
    mutationFn: ({ id, obNo }: any) => downloadOutboundPackage(id, obNo),
    onSuccess: () => { message.success('已下载 ZIP：内含 BOL 和抓货单 PDF，解压后即可打印'); refresh(); },
    onError: (error: Error) => message.error(error.message),
  });
  const downloadDocument = async (url: string, name: string) => {
    try { await downloadFile(url, name); } catch { message.error('单据下载失败，请重试'); }
  };
  const action = useMutation({
    mutationFn: ({ name, id }: { name: "confirm" | "dispatch" | "complete" | "cancel" | "resolve" | "picking" | "bol"; id: number }) =>
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
    onSuccess: (result: any, variables: any) => {
      if (variables.name === "delete") {
        const deletedIds = result.results
          .filter((item: any) => item.status === "success")
          .map((item: any) => item.id);
        if (deletedIds.length) {
          setSelectedIds((current) =>
            current.filter((id) => !deletedIds.includes(id)),
          );
          const currentSelectedId = Number(sp.get("selected_ob") || 0);
          if (deletedIds.includes(currentSelectedId)) {
            const query = new URLSearchParams(sp);
            query.delete("selected_ob");
            setSp(query, { replace: true });
          }
        }
      }
      const failedResults = result.results.filter(
        (item: any) => item.status === "failed",
      );
      if (result.failed > 0) {
        modal.warning({
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
        modal.warning({
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
  const inventoryMove = useMutation({
    mutationFn: async ({
      direction,
      rows: moveRows,
    }: {
      direction: "allocate" | "release";
      rows: any[];
    }) => {
      const items = moveRows.map((row) => ({
        id: row.id,
        data:
          direction === "allocate"
            ? {
              inventory_lot_id: row.inventory_lot_id || row.id,
              fba_allocation_id: row.fba_allocation_id,
              pallet_qty:
                row.available_pallet_qty ?? row.remaining_pallet_qty ?? 0,
              carton_qty:
                row.available_carton_qty ?? row.remaining_carton_qty ?? 0,
              weight_lbs:
                row.available_weight_lbs ?? row.remaining_weight_lbs ?? 0,
              cbm: row.available_cbm ?? row.remaining_cbm ?? 0,
            }
            : { allocation_id: row.id },
      }));
      const result = await runOutboundInventoryBatch(
        selectedId,
        direction,
        items,
      );
      return { ...result, direction };
    },
    onSuccess: (result) => {
      const successfulIds = result.results
        .filter((item) => item.status === "success")
        .map((item) => item.id);
      if (result.direction === "allocate") {
        setSelectedSourceIds((current) =>
          current.filter((id) => !successfulIds.includes(id)),
        );
      } else {
        setSelectedAllocationIds((current) =>
          current.filter((id) => !successfulIds.includes(id)),
        );
      }
      if (result.failed) {
        modal.warning({
          title: result.successful
            ? "Batch move completed with blocked rows"
            : "Batch move blocked",
          content: (
            <div>
              <p>
                Successful: {result.successful}; Failed: {result.failed}
              </p>
              <ul>
                {result.results
                  .filter((item) => item.status === "failed")
                  .map((item) => (
                    <li key={item.id}>
                      Row {item.id}: {item.reason}
                    </li>
                  ))}
              </ul>
            </div>
          ),
        });
      } else {
        message.success(
          `${result.successful} row${result.successful === 1 ? "" : "s"} ${
            result.direction === "allocate" ? "moved" : "removed"
          }`,
        );
      }
      refresh();
    },
    onError: (error: any) =>
      message.error(error?.response?.data?.detail || "Batch move rejected"),
  });

  const runInventoryMove = (direction: "allocate" | "release") => {
    if (!selectedId || inventoryMove.isPending) return;
    const ids =
      direction === "allocate" ? selectedSourceIds : selectedAllocationIds;
    const data =
      direction === "allocate"
        ? detail.data?.remaining_sources || []
        : activeAllocations;
    const moveRows = data.filter((row: any) => ids.includes(row.id));
    if (moveRows.length) inventoryMove.mutate({ direction, rows: moveRows });
  };

  const hasReleasableQuantity = (row: any) =>
    ["pallet_qty", "carton_qty", "weight_lbs", "cbm"].some(
      (metric) =>
        Number(row[`allocated_${metric}`] || 0) -
          Number(row[`completed_${metric}`] || 0) >
        0,
    );
  const activeAllocations = (detail.data?.allocations || []).filter((row: any) =>
    ["pallet_qty", "carton_qty", "weight_lbs", "cbm"].some(
      (metric) =>
        Number(row[`allocated_${metric}`] || 0) > 0 ||
        Number(row[`completed_${metric}`] || 0) > 0,
    ),
  );
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
  const loadTargets = useQuery({
    queryKey: ["drag-bol-loads", dragBolsRows[0]?.warehouse_id, loadSearch, loadPage],
    queryFn: () => getLoads({ business_type: 'PRIVATE', warehouse_id: dragBolsRows[0]?.warehouse_id, q: loadSearch || undefined, page: loadPage, per_page: 100 }),
    enabled: dragBolsOpen && !!dragBolsRows[0]?.warehouse_id,
  });
  const openDragBols = () => {
    const chosen = rows.filter((row: any) => selectedIds.includes(row.id));
    if (!chosen.length || chosen.length !== selectedIds.length) {
      message.warning("请在当前页重新勾选要加入装车单的记录"); return;
    }
    if (new Set(chosen.map((row: any) => row.warehouse_id)).size !== 1) {
      message.warning("请选择同一个仓库的记录"); return;
    }
    if (chosen.some((row:any)=>row.dispatch_business_type!=='PRIVATE')) { message.warning('请先在私仓派发工作台明确订单业务类型；FBA 订单使用独立入口'); return; }
    setDragBolsRows(chosen); setTargetLoad("new"); setLoadSearch(""); setLoadPage(1); setDragBolsOpen(true);
  };
  const assignBols = useMutation({
    mutationFn: () => targetLoad === "new"
      ? createLoad({ dispatch_business_type:'PRIVATE', warehouse_id: dragBolsRows[0].warehouse_id, outbound_ids: dragBolsRows.map((row: any) => row.id) })
      : attachLoadOutbounds(targetLoad, dragBolsRows.map((row: any) => row.id)),
    onSuccess: (load) => {
      setDragBolsOpen(false); setSelectedIds([]); refresh();
      qc.invalidateQueries({ queryKey: ["loads"] });
      qc.invalidateQueries({ queryKey: ["drag-bol-loads"] });
      modal.success({ title: "已加入装车单", content: load.load_no, okText: "查看装车单",
        onOk: () => navigate(`/loads/private?selected=${load.id}`) });
    },
    onError: (error: any) => {
      const detail = error?.response?.data?.detail;
      message.error(typeof detail === "string" ? detail : "加入失败，请检查记录是否已属于其他装车单或已完成");
    },
  });
  const createLoadMutation = useMutation({
    mutationFn: () => {
      const chosen = rows.filter((row: any) => selectedIds.includes(row.id));
      const warehouseIds = [
        ...new Set(chosen.map((row: any) => row.warehouse_id)),
      ];
      if (warehouseIds.length !== 1)
        throw new Error("Select outbound orders from one warehouse");
      if (chosen.some((row:any)=>row.dispatch_business_type!=='PRIVATE')) throw new Error('请先明确私仓订单业务类型，FBA 使用独立入口');
      return createLoad({
        dispatch_business_type:'PRIVATE',
        warehouse_id: warehouseIds[0],
        outbound_ids: selectedIds,
      });
    },
    onSuccess: (load: any) =>
      Modal.success({
        title: "Load created",
        content: `Load ${load.load_no} is ready.`,
        okText: "Open Load",
        onOk: () => navigate(`/loads/private?selected=${load.id}`),
      }),
    onError: (error: any) =>
      message.error(error?.message || "Unable to create load"),
  });

  const resetWindow = () => {
    horizontalSplitRef.current?.reset();
    verticalSplitRef.current?.reset();
  };

  const bolColumns = bolColumnDefinitions.filter(([, key]) => bolFields.includes(key)).map(([title, key, width]) => ({
    title, dataIndex: key, key, width,
    render: (value: string | number | null, row: { id: number; weight_source?: string | null }) => key === "ob_no"
      ? <a onClick={() => patch({ selected_ob: row.id })}>{value}</a>
      : key === "weight_lbs"
        ? <Tooltip title={row.weight_source || "无重量来源"}>{value == null ? "—" : Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</Tooltip>
        : <span style={{ whiteSpace: "normal", overflowWrap: "anywhere" }}>{value || "—"}</span>,
  }));
  const openRecord = (row: any) => { setSelectedIds([row.id]); patch({ selected_ob: row.id }); };
  const textColumn = (title: string, key: string, width = 108) => ({ title, dataIndex: key, width, render: (v: any) => {
    const text = v == null || v === "" ? "—" : String(v);
    const display = ["schedule_pickup_at", "delivery_appointment_time"].includes(key) ? text.replace("T", " ").slice(0, 16) : text;
    return <span style={{ whiteSpace: "normal", overflowWrap: "anywhere" }} title={text}>{display}</span>;
  } });
  const cols = [
    { title: "OB#", dataIndex: "ob_no", width: 140, sorter: true, render: (v: string, row: any) => <a onClick={() => { openRecord(row); setExecutionOpen(true); }}>{v}</a> },
    textColumn("Status", "status_name", 138), textColumn("Carrier Code", "carrier"), textColumn("Loading Team", "loading_team"), textColumn("Truck Type", "truck_type"),
    { title: "Notify Carrier", width: 100, render: () => <Tooltip title="承运商通知尚未接入"><span className="reference-unavailable">Notify</span></Tooltip> },
    textColumn("Delivery Type", "delivery_type"), textColumn("Pickup Location", "pickup_location", 125), textColumn("Schedule PU", "schedule_pickup_at", 132), textColumn("DEL APT TIME", "delivery_appointment_time", 132),
    textColumn("OB Type", "ob_type"), textColumn("DEL", "del_code"), textColumn("Redirect", "redirect_code"), textColumn("Booked Qty", "booked_pallet_qty"), textColumn("ISA/DEL APT#", "appointment_reference", 140), textColumn("DEL REF#", "reference_no", 145),
    { title: "WHS Remark", width: 90, render: (_: any, row: any) => <Tooltip title={row.remark || "暂无备注"}><span aria-label="Warehouse remark">▤</span></Tooltip> },
    { title: "OB BOL", key: "expand", width: 80, fixed: "right" as const, render: (_: any, row: any) => <Button type="link" size="small" onClick={() => {
      openRecord(row); setExecutionOpen(true);
    }}>Show</Button> },
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
      align: "right" as const,
      render: n,
    },
    {
      title: "Picked",
      dataIndex: "picked_pallet_qty",
      width: 72,
      align: "right" as const,
      render: n,
    },
    {
      title: "Done",
      dataIndex: "completed_pallet_qty",
      width: 68,
      align: "right" as const,
      render: n,
    },
    {
      title: "Remain",
      width: 74,
      align: "right" as const,
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
          disabled={
            !selected?.allowed_actions?.release || !hasReleasableQuantity(row)
          }
          onClick={() => releaseOutbound(selectedId, row.id, {}).then(refresh)}
        >
          Remove
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
      align: "right" as const,
      render: (_: any, row: any) =>
        n(row.available_pallet_qty ?? row.remaining_pallet_qty),
    },
    { title: "Inbound", dataIndex: "inbound_date", width: 92 },
    {
      title: "Warehouse Days",
      dataIndex: "warehouse_days",
      width: 100,
      align: "right" as const,
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
      width: 96,
      fixed: "right" as const,
      render: (_: any, row: any) => (
        <Button
          className="source-allocate-button"
          size="small"
          disabled={!selected?.allowed_actions?.allocate}
          onClick={() =>
            allocateOutbound(selectedId, {
              inventory_lot_id: row.inventory_lot_id || row.id,
              fba_allocation_id: row.fba_allocation_id,
              pallet_qty:
                row.available_pallet_qty ?? row.remaining_pallet_qty ?? 0,
              carton_qty:
                row.available_carton_qty ?? row.remaining_carton_qty ?? 0,
              weight_lbs:
                row.available_weight_lbs ?? row.remaining_weight_lbs ?? 0,
              cbm: row.available_cbm ?? row.remaining_cbm ?? 0,
            }).then(refresh)
          }
        >
          Drag BOL
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
          Allocation / Picking / BOL
        </h3>
        <Space size={6} wrap>
          <Button type="primary" loading={documentPackage.isPending}
            disabled={!selected?.allowed_actions?.picking || !selected?.allowed_actions?.bol || selected?.status === 4}
            title="先分配库存；下载 ZIP 内含 BOL 与抓货单 PDF"
            onClick={() => documentPackage.mutate({ id: selected.id, obNo: selected.ob_no })}>
            一键 BOL + 抓货单
          </Button>
          {(detail.data?.picking || []).filter((p: any) => p.status !== 4).map((p: any) =>
            <Button key={`pdf-p-${p.id}`} onClick={() => downloadDocument(`/picking-lists/${p.id}/pdf`, `${p.picking_no}.pdf`)}>抓货单 {p.picking_no}</Button>)}
          {(detail.data?.bols || []).filter((b: any) => b.status !== 4).map((b: any) =>
            <Button key={`pdf-b-${b.id}`} onClick={() => downloadDocument(`/bols/${b.id}/pdf`, `${b.bol_no}.pdf`)}>BOL {b.bol_no}</Button>)}
          <Button
            disabled={
              !selected?.allowed_actions?.release ||
              selectedAllocationIds.length === 0 ||
              inventoryMove.isPending
            }
            loading={
              inventoryMove.isPending &&
              inventoryMove.variables?.direction === "release"
            }
            onClick={() => runInventoryMove("release")}
          >
            Remove Selected ({selectedAllocationIds.length})
          </Button>
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
          rowSelection={{
            selectedRowKeys: selectedAllocationIds,
            onChange: (keys) =>
              setSelectedAllocationIds(keys.map((key) => Number(key))),
            getCheckboxProps: (row: any) => ({
              disabled:
                !selected?.allowed_actions?.release ||
                !hasReleasableQuantity(row),
            }),
          }}
          dataSource={activeAllocations}
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
        {selectedAllocationIds.length > 0 && (
          <span className="inventory-drag-hint">
            {selectedAllocationIds.length} selected — choose Remove Selected
          </span>
        )}
      </div>
    </section>
  );

  const lowerPanel = (
    <section
      className="dispatch-panel dispatch-panel-lower"
      aria-labelledby="outbound-region-source"
    >
      <div className="panel-title">
        <h3 id="outbound-region-source">Remaining Source</h3>
        <Space size={6} wrap>
          <span className="inventory-drag-help">
            Select rows, then choose Drag BOL
          </span>
          <Button
            type="primary"
            disabled={
              !selected?.allowed_actions?.allocate ||
              selectedSourceIds.length === 0 ||
              inventoryMove.isPending
            }
            loading={
              inventoryMove.isPending &&
              inventoryMove.variables?.direction === "allocate"
            }
            onClick={() => runInventoryMove("allocate")}
          >
            Drag BOL ({selectedSourceIds.length})
          </Button>
        </Space>
      </div>
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
          rowSelection={{
            selectedRowKeys: selectedSourceIds,
            onChange: (keys) =>
              setSelectedSourceIds(keys.map((key) => Number(key))),
            getCheckboxProps: () => ({
              disabled: !selected?.allowed_actions?.allocate,
            }),
          }}
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
      {modalContextHolder}
      <Modal title="Drag BOLs / 加入装车单" open={dragBolsOpen}
        onCancel={() => { if (!assignBols.isPending) setDragBolsOpen(false); }}
        onOk={() => assignBols.mutate()} confirmLoading={assignBols.isPending}
        okButtonProps={{ disabled: targetLoad !== "new" && !loadTargets.data?.data.some((load) => load.id === targetLoad && ["PLANNED", "READY"].includes(load.status)) }}
        okText={targetLoad === "new" ? "新建并加入" : "加入装车单"}>
        <p>已选 {dragBolsRows.length} 条记录：{dragBolsRows.map((row) => row.bol_no || row.ob_no).join("、")}</p>
        <p>请选择目标装车单。此操作只关联记录，库存和出库状态不会改变。</p>
        <Input.Search placeholder="搜索装车单号" allowClear onSearch={(value) => {
          setLoadSearch(value); setLoadPage(1); setTargetLoad("new");
        }} style={{ marginBottom: 12 }} />
        <Select aria-label="目标装车单" style={{ width: "100%" }} value={targetLoad}
          onChange={setTargetLoad} loading={loadTargets.isFetching}
          options={[{ value: "new", label: "新建装车单" },
            ...(loadTargets.data?.data || []).filter((load) => ["PLANNED", "READY"].includes(load.status))
              .map((load) => ({ value: load.id, label: `${load.load_no} · ${load.status} · ${load.outbound_count} 条` }))]} />
        {loadTargets.isError && <p role="alert">装车单加载失败，<a onClick={() => loadTargets.refetch()}>点击重试</a></p>}
        {(loadTargets.data?.meta?.total_pages || 0) > 1 && <Space style={{ marginTop: 12 }}>
          <Button disabled={loadPage <= 1} onClick={() => { setLoadPage(loadPage - 1); setTargetLoad("new"); }}>上一页</Button>
          <span>{loadPage} / {loadTargets.data?.meta?.total_pages}</span>
          <Button disabled={loadPage >= (loadTargets.data?.meta.total_pages ?? 1)} onClick={() => { setLoadPage(loadPage + 1); setTargetLoad("new"); }}>下一页</Button>
        </Space>}
      </Modal>
      <Modal title="Batch Update Transfer Code / 批量更新转运代码" open={transferOpen}
        onCancel={() => setTransferOpen(false)} onOk={() => transferMutation.mutate()}
        confirmLoading={transferMutation.isPending} okText="保存">
        <p>更新选中的 {transferIds.length} 条记录；留空会清除转运代码。</p>
        <Input maxLength={100} value={transferCode} onChange={(e) => setTransferCode(e.target.value)} />
      </Modal>
            <OutboundSplitLayout ref={horizontalSplitRef} showControls={false} defaultExpanded onCollapsedChange={setRightHidden}
              right={<DispatchBolPanels selectedOutbound={selected?.id === selectedId ? selected : undefined} onSelect={id => patch({ selected_ob: id })} />}
              left={<div className="dispatch-left-workspace">
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
                delivery_type: sp.get("delivery_type") || "",
                skd_pu_date: sp.get("skd_pu_date") || "",
              }}
              warehouses={warehouses.data || []}
              carriers={carriers.data || []}
              selectedCount={selectedIds.length || (selected ? 1 : 0)}
              canConfirm={canRunLifecycle("confirm")}
              canCancel={canRunLifecycle("cancel")}
              canException={!!selected?.allowed_actions?.exception}
              canDispatch={canRunLifecycle("dispatch")}
              rightHidden={rightHidden}
              onChange={patch}
              onRefresh={refresh}
              onResetFilters={() => {
                setSelectedIds([]);
                setSp(new URLSearchParams());
              }}
              onResetWindow={resetWindow}
              onToggleRight={() => horizontalSplitRef.current?.toggleRight()}
              onCreate={() => setCreateOpen(true)}
              onConfirm={() => runLifecycle("confirm")}
              onCancel={() => runLifecycle("cancel")}
              onDispatch={() => runLifecycle("dispatch")}
              onException={() => setExceptionOpen(true)}
              onDelete={() => {
                const ids = selectedIds.length
                  ? selectedIds
                  : selected
                    ? [selected.id]
                    : [];
                if (!ids.length) return;
                const labels = rows
                  .filter((row: any) => ids.includes(row.id))
                  .map((row: any) => row.ob_no);
                modal.confirm({
                  title: `Delete ${ids.length} outbound order${ids.length === 1 ? "" : "s"}?`,
                  content: (
                    <div>
                      <p>
                        This permanently deletes only pristine New drafts. Any
                        outbound with allocations or execution records will be
                        rejected and kept.
                      </p>
                      {labels.length > 0 && <p>{labels.join(", ")}</p>}
                    </div>
                  ),
                  okText: "Delete",
                  okButtonProps: { danger: true },
                  onOk: () => batchAction.mutateAsync({ name: "delete", ids }),
                });
              }}
            />
            <section
              className="dispatch-orders"
              aria-labelledby="outbound-region-orders"
            >
              <h3 id="outbound-region-orders" className="reference-sr-only">Outbound Orders</h3>
              <div
                ref={ordersTableRef}
                className="dispatch-table-host dispatch-orders-table-host"
              >
                <Table
                  className="dispatch-dense-table"
                  size="small"
                  sticky
                  scroll={{ x: 2120, y: ordersScrollY }}
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
          </div>} />
      <Drawer title={selected ? `${selected.ob_no} — OB Details` : 'OB Details'}
        rootClassName="dispatch-execution-drawer" open={executionOpen}
        onClose={() => setExecutionOpen(false)} width="92vw">
        <Tabs key={`${selectedId}-${executionOpen}`} defaultActiveKey="detail" items={[
          { key: 'detail', label: 'Detail', children: (
            <div className="dispatch-detail-columns">
              <div className="dispatch-detail-workflow">
                <section className="dispatch-detail-actions" aria-label="Outbound workflow">
                  <div className="dispatch-detail-heading"><strong>Outbound Workflow</strong><Tag>{selected?.status_name || 'Loading…'}</Tag></div>
                  <Space wrap>
                    {['confirm', 'dispatch', 'complete', 'cancel'].map(name => (
                      <Button key={name} danger={name === 'cancel'} disabled={!canRunLifecycle(name) || batchAction.isPending}
                        onClick={() => runLifecycle(name)}>{name[0].toUpperCase() + name.slice(1)}</Button>
                    ))}
                    <Button disabled={!selected?.allowed_actions?.exception || action.isPending} onClick={() => setExceptionOpen(true)}>Exception</Button>
                  </Space>
                  {selected?.blocking_reasons?.length > 0 && <p>{selected.blocking_reasons.join(' · ')}</p>}
                </section>
                <div className="dispatch-detail-tables">
                  <OutboundVerticalSplitLayout ref={verticalSplitRef} top={upperPanel} bottom={lowerPanel} />
                </div>
              </div>
              <section className="dispatch-general-information" aria-label="General Information">
                <h3>General Information</h3>
                <dl>{[
                  ['OB#', selected?.ob_no], ['BOL#', selected?.bol_no], ['Status', selected?.status_name],
                  ['Customer', selected?.customer], ['Warehouse', selected?.warehouse],
                  ['Carrier', selected?.carrier], ['Loading Team', selected?.loading_team],
                  ['Truck Type', selected?.truck_type], ['Delivery Type', selected?.delivery_type],
                  ['Pickup Location', selected?.pickup_location], ['Delivery Code', selected?.fc_code],
                  ['OB Type', selected?.ob_type], ['Schedule Pickup', selected?.schedule_pickup_at],
                  ['Delivery Appointment', selected?.delivery_appointment_time],
                  ['FBA#', selected?.fba_no || selected?.fba_id], ['Reference#', selected?.reference_no],
                  ['Allocated PLT', selected?.allocated_pallet_qty], ['Allocated CTN', selected?.allocated_carton_qty],
                  ['Weight LB', selected?.allocated_weight_lbs], ['CBM', selected?.allocated_cbm],
                ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value === null || value === undefined || value === '' ? '—' : String(value)}</dd></div>)}</dl>
              </section>
            </div>
          )},
          { key: 'documents', label: 'Documents', children: selected ? <EntityDocuments relation={{ outbound_id: selected.id }} /> : null },
          { key: 'activities', label: 'Log Activities', children: <div className="dispatch-detail-empty">当前接口暂无可展示的操作日志。</div> },
        ]} />
      </Drawer>
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
        initialRows={selectedRows}
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
