import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
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
import { useSearchParams } from "react-router-dom";
import { getWarehouses } from "../api/masterData";
import {
  assignWorkOrder,
  changeWorkOrderStatus,
  createWorkOrder,
  getWorkOrder,
  getWorkOrders,
  WorkOrder,
} from "../api/workOrders";
import { WorkOrderHistory } from "../components/WorkOrderHistory";
import { EntityDocuments } from "../components/EntityDocuments";
import { usePermission } from "../hooks/usePermissions";

const types = ["PICK", "STAGE", "LOAD", "CHECK", "GENERAL"];
const statuses = ["OPEN", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELED"];
const priorities = ["LOW", "NORMAL", "HIGH", "URGENT"];
const allowed: Record<string, string[]> = {
  OPEN: ["ASSIGNED", "IN_PROGRESS", "CANCELED"],
  ASSIGNED: ["IN_PROGRESS", "CANCELED"],
  IN_PROGRESS: ["COMPLETED"],
};

export function WorkOrdersPage() {
  const { allowed: canManage } = usePermission("manage_warehouse");
  const qc = useQueryClient();
  const [sp] = useSearchParams();
  const [params, setParams] = useState<any>({
    page: 1,
    per_page: 20,
    status: sp.get("status") || undefined,
    priority: sp.get("priority") || undefined,
    warehouse_id: Number(sp.get("warehouse_id")) || undefined,
  });
  const [selected, setSelected] = useState<number | null>(
    Number(sp.get("selected") || 0) || null,
  );
  const [open, setOpen] = useState(false);
  const [assignOpen, setAssignOpen] = useState(false);
  const [form] = Form.useForm();
  const [assignForm] = Form.useForm();
  const list = useQuery({
    queryKey: ["work-orders", params],
    queryFn: () => getWorkOrders(params),
  });
  const detail = useQuery({
    queryKey: ["work-order", selected],
    queryFn: () => getWorkOrder(selected!),
    enabled: !!selected,
  });
  const wh = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const create = useMutation({
    mutationFn: createWorkOrder,
    onSuccess: (r) => {
      message.success(`Created ${r.work_order_no}`);
      setOpen(false);
      form.resetFields();
      qc.invalidateQueries({ queryKey: ["work-orders"] });
    },
    onError: () => message.error("Unable to create work order"),
  });
  const transition = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      changeWorkOrderStatus(id, status),
    onSuccess: (r) => {
      setSelected(r.id);
      qc.invalidateQueries({ queryKey: ["work-orders"] });
      qc.invalidateQueries({ queryKey: ["work-order", r.id] });
      qc.invalidateQueries({ queryKey: ["work-order-events", r.id] });
    },
    onError: () => message.error("Status transition rejected"),
  });
  const assign = useMutation({
    mutationFn: (v: {
      assigned_to?: number | null;
      assigned_team?: string | null;
    }) => assignWorkOrder(selected!, v),
    onSuccess: (r) => {
      message.success("Assignment updated");
      setAssignOpen(false);
      assignForm.resetFields();
      qc.invalidateQueries({ queryKey: ["work-orders"] });
      qc.invalidateQueries({ queryKey: ["work-order", r.id] });
      qc.invalidateQueries({ queryKey: ["work-order-events", r.id] });
    },
    onError: () => message.error("Unable to update assignment"),
  });
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>Work Orders</Typography.Title>
          <Typography.Text type="secondary">
            Warehouse execution tasks
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
              Create Work Order
            </Button>
          )}
        </Space>
      </div>
      <div className="dispatch-filters">
        <Input
          placeholder="Search Work Order No"
          onPressEnter={(e) =>
            setParams((p: any) => ({ ...p, q: e.currentTarget.value, page: 1 }))
          }
        />
        <Select
          allowClear
          placeholder="Type"
          options={types.map((x) => ({ value: x, label: x }))}
          onChange={(v) =>
            setParams((p: any) => ({ ...p, work_order_type: v, page: 1 }))
          }
        />
        <Select
          allowClear
          placeholder="Status"
          value={params.status}
          options={statuses.map((x) => ({ value: x, label: x }))}
          onChange={(v) =>
            setParams((p: any) => ({ ...p, status: v, page: 1 }))
          }
        />
        <Select
          allowClear
          placeholder="Priority"
          value={params.priority}
          options={priorities.map((x) => ({ value: x, label: x }))}
          onChange={(v) =>
            setParams((p: any) => ({ ...p, priority: v, page: 1 }))
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
        <InputNumber
          placeholder="Assignee ID"
          min={1}
          onPressEnter={(e) =>
            setParams((p: any) => ({
              ...p,
              assigned_to: Number(e.currentTarget.value) || undefined,
              page: 1,
            }))
          }
        />
      </div>
      <Table
        rowKey="id"
        loading={list.isLoading}
        dataSource={list.data?.data ?? []}
        onRow={(r: WorkOrder) => ({ onClick: () => setSelected(r.id) })}
        pagination={{
          current: list.data?.meta.page,
          pageSize: list.data?.meta.per_page,
          total: list.data?.meta.total,
        }}
        columns={[
          { title: "Work Order No", dataIndex: "work_order_no" },
          { title: "Type", dataIndex: "work_order_type" },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string) => <Tag>{v}</Tag>,
          },
          { title: "Priority", dataIndex: "priority" },
          { title: "Warehouse", dataIndex: "warehouse_id" },
          { title: "Load", dataIndex: "load_id" },
          { title: "Outbound", dataIndex: "outbound_id" },
          {
            title: "Assigned",
            render: (_: any, r: WorkOrder) =>
              r.assignee_name || r.assigned_team || "—",
          },
          { title: "Created At", dataIndex: "created_at" },
        ]}
      />
      <Drawer
        width={520}
        title={detail.data?.work_order_no ?? "Work Order Detail"}
        open={!!selected}
        onClose={() => setSelected(null)}
      >
        {detail.data && (
          <>
            <Typography.Title level={5}>Overview</Typography.Title>
            <Typography.Paragraph>
              Type: {detail.data.work_order_type} · Priority:{" "}
              <Tag>{detail.data.priority}</Tag> · Status:{" "}
              <Tag>{detail.data.status}</Tag>
            </Typography.Paragraph>
            <Typography.Title level={5}>Related Objects</Typography.Title>
            <Typography.Paragraph>
              Load: {detail.data.load_id ?? "—"} · Outbound:{" "}
              {detail.data.outbound_id ?? "—"} · Picking:{" "}
              {detail.data.picking_list_id ?? "—"}
            </Typography.Paragraph>
            <Typography.Title level={5}>Execution</Typography.Title>
            {canManage && (
              <Space wrap>
                <Button
                  onClick={() => {
                    assignForm.setFieldsValue({
                      assigned_to: detail.data!.assigned_to,
                      assigned_team: detail.data!.assigned_team,
                    });
                    setAssignOpen(true);
                  }}
                >
                  Assign
                </Button>
                {(allowed[detail.data.status] ?? []).map((s) => (
                  <Button
                    key={s}
                    onClick={() =>
                      transition.mutate({ id: detail.data!.id, status: s })
                    }
                  >
                    {s}
                  </Button>
                ))}
              </Space>
            )}
            <Typography.Paragraph style={{ marginTop: 12 }}>
              Assigned:{" "}
              {detail.data.assignee_name || detail.data.assigned_team || "—"}
            </Typography.Paragraph>
            <Typography.Title level={5}>Notes</Typography.Title>
            <Typography.Paragraph>
              {detail.data.notes || "—"}
            </Typography.Paragraph>
            <EntityDocuments relation={{ work_order_id: detail.data.id }} />
            <Typography.Title level={5}>History</Typography.Title>
            <WorkOrderHistory workOrderId={selected} />
          </>
        )}
      </Drawer>
      <Modal
        title="Create Work Order"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)}>
          <Form.Item
            name="work_order_type"
            label="Type"
            rules={[{ required: true }]}
          >
            <Select options={types.map((x) => ({ value: x, label: x }))} />
          </Form.Item>
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
          <Form.Item name="priority" label="Priority" initialValue="NORMAL">
            <Select options={priorities.map((x) => ({ value: x, label: x }))} />
          </Form.Item>
          <Form.Item name="load_id" label="Load ID">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="outbound_id" label="Outbound ID">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="picking_list_id" label="Picking List ID">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="container_tracking_id" label="Container Tracking ID">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="assigned_team" label="Assigned Team">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="Assign Work Order"
        open={assignOpen}
        onCancel={() => setAssignOpen(false)}
        onOk={() => assignForm.submit()}
        confirmLoading={assign.isPending}
      >
        <Form
          form={assignForm}
          layout="vertical"
          onFinish={(v) => assign.mutate(v)}
        >
          <Form.Item name="assigned_to" label="Assignee User ID">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="assigned_team" label="Assigned Team">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
