import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Alert,
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
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { createLoad, getLoad, getLoads, Load, BusinessType } from "../api/loads";
import { getCarriers, getWarehouses } from "../api/masterData";
import { createWorkOrder, getWorkOrder } from "../api/workOrders";
import { WorkOrderHistory } from "../components/WorkOrderHistory";
import { LoadDispatchReadiness } from "../components/LoadDispatchReadiness";
import { EntityDocuments } from "../components/EntityDocuments";
import { usePermission } from "../hooks/usePermissions";

import { LoadDispatchWorkbench } from '../components/LoadDispatchWorkbench';

export function LoadsPage({businessType = 'PRIVATE'}:{businessType?:BusinessType}) {
  const { allowed: canManage } = usePermission("manage_outbound");
  const { allowed: canManageWorkOrders } = usePermission("manage_warehouse");
  const qc = useQueryClient();
  const [sp] = useSearchParams();
  const [params, setParams] = useState<any>({
    page: 1,
    per_page: 20,
    status: sp.get("status") || undefined,
    warehouse_id: Number(sp.get("warehouse_id")) || undefined,
  });
  const [selected, setSelected] = useState<number | null>(
    Number(sp.get("selected") || 0) || null,
  );
  const [selectedWorkOrder, setSelectedWorkOrder] = useState<number | null>(
    null,
  );
  const [open, setOpen] = useState(false);
  const [readinessRevision, setReadinessRevision] = useState(0);
  const [form] = Form.useForm();
  const list = useQuery({
    queryKey: ["loads", businessType, params],
    queryFn: () => getLoads({...params,business_type:businessType}),
  });
  const detail = useQuery({
    queryKey: ["load", selected],
    queryFn: () => getLoad(selected!),
    enabled: !!selected,
  });
  const workOrderDetail = useQuery({
    queryKey: ["work-order", selectedWorkOrder],
    queryFn: () => getWorkOrder(selectedWorkOrder!),
    enabled: !!selectedWorkOrder,
  });
  const wh = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const carriers = useQuery({ queryKey: ["carriers"], queryFn: getCarriers });
  const create = useMutation({
    mutationFn: createLoad,
    onSuccess: (r) => {
      message.success(`Created ${r.load_no}`);
      setOpen(false);
      form.resetFields();
      qc.invalidateQueries({ queryKey: ["loads"] });
    },
  });
  const createLoadWorkOrder = useMutation({
    mutationFn: () =>
      createWorkOrder({
        work_order_type: "LOAD",
        warehouse_id: detail.data!.warehouse_id,
        load_id: detail.data!.id,
        priority: "NORMAL",
      }),
    onSuccess: (r) => {
      message.success(`Created ${r.work_order_no}`);
      qc.invalidateQueries({ queryKey: ["load", selected] });
      qc.invalidateQueries({ queryKey: ["work-orders"] });
    },
    onError: () => message.error("Unable to create work order"),
  });

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>{businessType === 'FBA' ? 'FBA 派发' : '私仓派发'}</Typography.Title>
          <Typography.Text type="secondary">
            Outbound transportation aggregates
          </Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>
            Refresh
          </Button>
          {canManage && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setOpen(true)}
            >
              Create Load
            </Button>
          )}
        </Space>
      </div>
      <div className="dispatch-filters">
        <Input
          placeholder="Search Load No"
          onPressEnter={(e) =>
            setParams((p: any) => ({ ...p, q: e.currentTarget.value, page: 1 }))
          }
        />
        <Select
          allowClear
          placeholder="Status"
          value={params.status}
          options={[
            "PLANNED",
            "READY",
            "DISPATCHED",
            "COMPLETED",
            "CANCELED",
          ].map((x) => ({ value: x, label: x }))}
          onChange={(v) =>
            setParams((p: any) => ({ ...p, status: v, page: 1 }))
          }
        />
        <Select
          allowClear
          placeholder="Warehouse"
          value={params.warehouse_id}
          options={(wh.data ?? []).map((x: any) => ({
            value: x.id,
            label: x.warehouse_code,
          }))}
          onChange={(v) =>
            setParams((p: any) => ({ ...p, warehouse_id: v, page: 1 }))
          }
        />
      </div>
      <Table
        rowKey="id"
        loading={list.isLoading}
        dataSource={list.data?.data ?? []}
        pagination={{
          current: list.data?.meta.page,
          pageSize: list.data?.meta.per_page,
          total: list.data?.meta.total,
        }}
        columns={[
          {
            title: "Load No",
            dataIndex: "load_no",
            render: (v: string, r: Load) => (
              <Button type="link" onClick={() => setSelected(r.id)}>
                {v}
              </Button>
            ),
          },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: "Warehouse",
            render: (_: any, r: Load) => r.warehouse?.code,
          },
          {
            title: "Carrier",
            render: (_: any, r: Load) => r.carrier?.code ?? "—",
          },
          { title: "Appointment", dataIndex: "appointment_time" },
          { title: "Outbound Count", dataIndex: "outbound_count" },
          { title: "Destination", dataIndex: "destination_name" },
        ]}
      />
      <Drawer
        width={900}
        title={detail.data?.load_no ?? "Load Detail"}
        open={!!selected}
        onClose={() => {
          setSelected(null);
          setSelectedWorkOrder(null);
        }}
      >
        {detail.data && detail.data.dispatch_business_type !== businessType && <Alert type="error" message="此派车单业务类型不属于当前入口，操作已阻断"/>}
        {detail.data && detail.data.dispatch_business_type === businessType && (
          <>
            <Typography.Title level={5}>Overview</Typography.Title>
            <Typography.Paragraph>
              Status: <Tag>{detail.data.status}</Tag> · Warehouse:{" "}
              {detail.data.warehouse?.code}
            </Typography.Paragraph>
            <Typography.Title level={5}>
              Active Exceptions{" "}
              <Tag
                color={detail.data.active_exception_count ? "red" : "default"}
              >
                {detail.data.active_exception_count ?? 0}
              </Tag>
            </Typography.Title>
            {detail.data.active_exception_count ? (
              <Table
                size="small"
                pagination={false}
                rowKey="id"
                dataSource={detail.data.active_exceptions ?? []}
                columns={[
                  {
                    title: "No",
                    dataIndex: "exception_no",
                    render: (value: string, row: any) => (
                      <Link to={`/trouble-shoot?selected=${row.id}`}>
                        {value}
                      </Link>
                    ),
                  },
                  {
                    title: "Severity",
                    dataIndex: "severity",
                    render: (value: string) => (
                      <Tag
                        color={
                          value === "CRITICAL"
                            ? "red"
                            : value === "HIGH"
                              ? "orange"
                              : "blue"
                        }
                      >
                        {value}
                      </Tag>
                    ),
                  },
                  { title: "Status", dataIndex: "status" },
                  { title: "Title", dataIndex: "title" },
                ]}
              />
            ) : (
              <Typography.Paragraph type="secondary">
                No active exceptions.
              </Typography.Paragraph>
            )}
            <div className="page-heading">
              <Typography.Title level={5}>Work Orders</Typography.Title>
              {canManageWorkOrders && (
                <Button
                  icon={<PlusOutlined />}
                  loading={createLoadWorkOrder.isPending}
                  onClick={() => createLoadWorkOrder.mutate()}
                >
                  Create Work Order
                </Button>
              )}
            </div>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              dataSource={detail.data.work_orders ?? []}
              columns={[
                {
                  title: "No",
                  dataIndex: "work_order_no",
                  render: (value: string, row: any) => (
                    <Button
                      type="link"
                      onClick={() => setSelectedWorkOrder(row.id)}
                    >
                      {value}
                    </Button>
                  ),
                },
                { title: "Type", dataIndex: "work_order_type" },
                { title: "Status", dataIndex: "status" },
                { title: "Priority", dataIndex: "priority" },
                {
                  title: "Assigned",
                  render: (_: any, r: any) =>
                    r.assignee_name || r.assigned_team || "—",
                },
                { title: "Created", dataIndex: "created_at" },
                { title: "Started", dataIndex: "started_at" },
                { title: "Completed", dataIndex: "completed_at" },
              ]}
            />
            <Typography.Title level={5}>Outbound Orders</Typography.Title>
            <Typography.Paragraph>
              {detail.data.outbound_count} OB · {detail.data.total_pallet_qty}{" "}
              PLT · {detail.data.total_carton_qty} CTN ·{" "}
              {detail.data.total_weight_lbs} LBS · {detail.data.total_cbm} CBM
            </Typography.Paragraph>
            {selected !== null && detail.data.id === selected && (
              <LoadDispatchReadiness key={selected} loadId={selected} refreshToken={readinessRevision} />
            )}
            <LoadDispatchWorkbench key={detail.data.id} load={detail.data} businessType={businessType} canManage={canManage} onChanged={() => setReadinessRevision(v => v + 1)} />
            <EntityDocuments relation={{ load_id: detail.data.id }} onChanged={() => setReadinessRevision(v => v + 1)} />
          </>
        )}
      </Drawer>
      <Drawer
        width={560}
        title={workOrderDetail.data?.work_order_no ?? "Work Order Detail"}
        open={!!selectedWorkOrder}
        onClose={() => setSelectedWorkOrder(null)}
      >
        {workOrderDetail.data && (
          <>
            <Typography.Title level={5}>Overview</Typography.Title>
            <Typography.Paragraph>
              Type: {workOrderDetail.data.work_order_type} · Priority:{" "}
              <Tag>{workOrderDetail.data.priority}</Tag> · Status:{" "}
              <Tag>{workOrderDetail.data.status}</Tag>
            </Typography.Paragraph>
            <Typography.Title level={5}>Related Objects</Typography.Title>
            <Typography.Paragraph>
              Load: {workOrderDetail.data.load_id ?? "—"} · Outbound:{" "}
              {workOrderDetail.data.outbound_id ?? "—"} · Picking:{" "}
              {workOrderDetail.data.picking_list_id ?? "—"}
            </Typography.Paragraph>
            <Typography.Title level={5}>Execution</Typography.Title>
            <Typography.Paragraph>
              Assigned:{" "}
              {workOrderDetail.data.assignee_name ||
                workOrderDetail.data.assigned_team ||
                "—"}{" "}
              · Scheduled:{" "}
              {workOrderDetail.data.scheduled_at
                ? new Date(workOrderDetail.data.scheduled_at).toLocaleString()
                : "—"}
            </Typography.Paragraph>
            <Typography.Title level={5}>Notes</Typography.Title>
            <Typography.Paragraph>
              {workOrderDetail.data.notes || "—"}
            </Typography.Paragraph>
            <Typography.Title level={5}>History</Typography.Title>
            <WorkOrderHistory workOrderId={selectedWorkOrder} />
          </>
        )}
      </Drawer>
      <Modal
        title="Create Load"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => create.mutate({ ...v, dispatch_business_type:businessType, outbound_ids: [] })}
        >
          <Form.Item
            name="warehouse_id"
            label="Warehouse"
            rules={[{ required: true }]}
          >
            <Select
              options={(wh.data ?? []).map((x: any) => ({
                value: x.id,
                label: x.warehouse_code,
              }))}
            />
          </Form.Item>
          <Form.Item name="carrier_id" label="Carrier">
            <Select
              allowClear
              options={(carriers.data ?? []).map((x: any) => ({
                value: x.id,
                label: x.carrier_code,
              }))}
            />
          </Form.Item>
          <Form.Item name="destination_name" label="Destination">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
