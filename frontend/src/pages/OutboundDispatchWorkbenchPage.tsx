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
import type { TableColumnsType } from "antd";
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
import type {
  OutboundAllocation,
  OutboundParams,
  OutboundRecord,
} from "../types/outbound";
import { generateBol, generatePicking } from "../api/pickingBol";
import { getCarriers, getCustomers, getWarehouses } from "../api/masterData";
import { EntityDocuments } from "../components/EntityDocuments";
import { createLoad } from "../api/loads";
import { getFBAAllocations } from "../api/fba";
import { ImportWizard } from "../components/ImportWizard";
import {
  OutboundSplitLayout,
  OutboundVerticalSplitLayout,
  type OutboundSplitLayoutHandle,
  type OutboundVerticalSplitLayoutHandle,
} from "../components/outbound-workbench/OutboundSplitLayout";
import { DispatchCommandBar } from "../components/outbound-workbench/DispatchCommandBar";
import { RemainingSourceTable } from "../components/outbound-workbench/RemainingSourceTable";
import {
  DispatchPriorityTag,
  DispatchReadinessTag,
  OutboundDateCell,
} from "../components/DispatchIndicators";
import type { OutboundRemainingSource } from "../types/outboundAllocation";
import {
  classifyFbaAllocationSources,
  FBA_MAPPING_INVALID_MESSAGE,
  retainValidSourceSelection,
  workbenchSourceAllocationData,
} from "../utils/outboundAllocation";

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
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [exceptionOpen, setExceptionOpen] = useState(false);
  const [rightHidden, setRightHidden] = useState(false);
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

  const params = useMemo(() => {
    const requestedSortOrder = sp.get("sort_order");
    return {
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
      sort_order: requestedSortOrder === "asc" ? "asc" : "desc",
    } satisfies OutboundParams;
  }, [sp]);

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
  const isFba = selected?.ob_type === "FBA";
  const fbaId = isFba ? Number(selected?.fba_id || 0) : 0;
  const fbaSources = useQuery({
    queryKey: ["outbound-fba-source-map", fbaId],
    queryFn: () => getFBAAllocations(fbaId),
    enabled: !!selectedId && isFba && fbaId > 0,
  });
  const rawSourceRows = (detail.data?.remaining_sources || []) as OutboundRemainingSource[];
  const fbaClassification = useMemo(
    () =>
      isFba && fbaSources.isSuccess
        ? classifyFbaAllocationSources(fbaSources.data || [], rawSourceRows)
        : { sources: [], mappingError: null },
    [isFba, fbaSources.isSuccess, fbaSources.data, rawSourceRows],
  );
  const sourceMappingError = isFba
    ? !fbaId
      ? FBA_MAPPING_INVALID_MESSAGE
      : fbaSources.isError
        ? "Unable to validate the FBA source mapping. Refresh this list and try again."
        : fbaSources.isSuccess
          ? fbaClassification.mappingError
          : null
    : null;
  const sourceErrorMessage = detail.isError
    ? "Unable to load source inventory. Refresh this list and try again."
    : sourceMappingError;
  const sourceReady =
    !!selectedId &&
    detail.isSuccess &&
    (!isFba || fbaSources.isSuccess) &&
    !sourceErrorMessage;
  const sourceRows = sourceReady ? rawSourceRows : [];
  const sourceSelectionSignature = sourceRows.map((row) => row.id).join("|");
  const selectedRows = rows.filter((row: any) => selectedIds.includes(row.id));
  const lifecycleRows = selectedIds.length
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

  useEffect(() => {
    setSelectedSourceIds((current) =>
      retainValidSourceSelection(current, sourceRows, sourceReady),
    );
  }, [sourceReady, sourceSelectionSignature]);

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
    qc.invalidateQueries({ queryKey: ["outbound-fba-source-map"] });
  };
  const actionHandlers = {
    confirm: confirmOutbound,
    dispatch: dispatchOutbound,
    complete: completeOutbound,
    cancel: cancelOutbound,
    resolve: resolveOutbound,
    picking: generatePicking,
    bol: generateBol,
  };
  const isActionName = (name: string): name is keyof typeof actionHandlers =>
    name in actionHandlers;
  const action = useMutation({
    mutationFn: ({ name, id }: { name: string; id: number }) => {
      if (!isActionName(name)) throw new Error("Unknown outbound action");
      return actionHandlers[name](id);
    },
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
  const inventoryRetryRef = useRef<{ signature: string; key: string } | null>(null);
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
            ? workbenchSourceAllocationData(row)
            : { allocation_id: row.id },
      }));
      const signature = JSON.stringify({ selectedId, direction, items });
      if (inventoryRetryRef.current?.signature !== signature) {
        inventoryRetryRef.current = { signature, key: crypto.randomUUID() };
      }
      const result = await runOutboundInventoryBatch(
        selectedId,
        direction,
        items,
        inventoryRetryRef.current.key,
      );
      return { ...result, direction };
    },
    onSuccess: (result) => {
      inventoryRetryRef.current = null;
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
    onError: (error: any) => {
      const status = error?.response?.status;
      if (status && ![408, 429].includes(status) && status < 500) inventoryRetryRef.current = null;
      const detail = error?.response?.data?.detail;
      message.error(detail?.message || detail || "Batch move rejected");
    },
  });

  const runInventoryMove = (direction: "allocate" | "release") => {
    if (!selectedId || inventoryMove.isPending) return;
    const ids =
      direction === "allocate" ? selectedSourceIds : selectedAllocationIds;
    const data =
      direction === "allocate"
        ? sourceRows
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

  const cols: TableColumnsType<OutboundRecord> = [
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
      render: (value: keyof typeof colors) => (
        <Tag color={colors[value]}>{value}</Tag>
      ),
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
      render: (value: any) =>
        value ? <DispatchReadinessTag value={value} /> : "--",
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

  const allocCols: TableColumnsType<OutboundAllocation> = [
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

  const summary = list.data?.summary || {};
  const selectedPallets = selectedRows.reduce(
    (total: number, row: any) => total + Number(row.allocated_pallet_qty || 0),
    0,
  );

  const upperPanel = (
    <div className="dispatch-panel dispatch-panel-upper">
      <div className="panel-title">
        <h3>OB Allocation / Picking / BOL</h3>
        <Space size={6} wrap>
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
    </div>
  );

  const lowerPanel = (
    <div className="dispatch-panel dispatch-panel-lower">
      <div className="panel-title">
        <h3>Remaining Source</h3>
        <Space size={6} wrap>
          <span className="inventory-drag-help">
            Select rows, then choose Drag BOL
          </span>
          <Button
            type="primary"
            disabled={
              !selected?.allowed_actions?.allocate ||
              !sourceReady ||
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
      {selected && <EntityDocuments relation={{ outbound_id: selected.id }} />}
      <div
        ref={sourceTableRef}
        className="dispatch-table-host dispatch-panel-table-host"
      >
        <RemainingSourceTable
          rows={sourceRows}
          selectedIds={selectedSourceIds}
          ready={sourceReady}
          loading={detail.isLoading || (isFba && fbaSources.isLoading)}
          canAllocate={!!selected?.allowed_actions?.allocate}
          errorMessage={sourceErrorMessage}
          scrollY={sourceScrollY}
          onSelectionChange={setSelectedSourceIds}
          onRefresh={() => {
            detail.refetch();
            if (isFba) fbaSources.refetch();
          }}
          onAllocate={(row) =>
            allocateOutbound(
              selectedId,
              workbenchSourceAllocationData(row),
            ).then(refresh)
          }
        />
      </div>
    </div>
  );

  return (
    <div className="dispatch-workbench">
      {modalContextHolder}
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
              selectedCount={selectedIds.length || (selected ? 1 : 0)}
              canConfirm={canRunLifecycle("confirm")}
              canCancel={canRunLifecycle("cancel")}
              canException={!!selected?.allowed_actions?.exception}
              canDispatch={canRunLifecycle("dispatch")}
              rightHidden={rightHidden}
              onChange={patch}
              onRefresh={() => list.refetch()}
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
              <Button
                onClick={() => {
                  setSelectedIds([]);
                  setSp(new URLSearchParams());
                }}
              >
                Reset
              </Button>
            </div>
            <section className="dispatch-orders">
              <h3>Outbound Orders</h3>
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
                  disabled={!selected?.allowed_actions?.confirm}
                  onClick={() =>
                    action.mutate({ name: "confirm", id: selected.id })
                  }
                >
                  Confirm
                </Button>
                <Button
                  disabled={!selected?.allowed_actions?.dispatch}
                  onClick={() =>
                    action.mutate({ name: "dispatch", id: selected.id })
                  }
                >
                  Dispatch
                </Button>
                <Button
                  disabled={!selected?.allowed_actions?.complete}
                  onClick={() =>
                    action.mutate({ name: "complete", id: selected.id })
                  }
                >
                  Complete
                </Button>
                <Button
                  danger
                  disabled={!selected?.allowed_actions?.cancel}
                  onClick={() =>
                    action.mutate({ name: "cancel", id: selected.id })
                  }
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
          <section className="dispatch-right">
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
          </section>
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
