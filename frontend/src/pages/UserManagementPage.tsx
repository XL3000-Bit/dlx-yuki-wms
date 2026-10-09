import { Button, Drawer, Form, Input, Select, Space, Switch, Table, Tag, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createUser, listUsers, updateUser, type ManagedUser, type UserRole } from "../api/users";
import { useCurrentUser } from "../hooks/usePermissions";

const ROLES: UserRole[] = ["ADMIN", "MANAGER", "INBOUND", "OUTBOUND", "WAREHOUSE", "VIEWER"];
const colors: Record<string, string> = { ADMIN: "red", MANAGER: "purple", INBOUND: "blue", OUTBOUND: "cyan", WAREHOUSE: "gold", VIEWER: "default" };

export function UserManagementPage() {
  const qc = useQueryClient();
  const me = useCurrentUser();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const users = useQuery({ queryKey: ["users"], queryFn: listUsers });
  const create = useMutation({
    mutationFn: createUser,
    onSuccess: () => { message.success("User created"); setOpen(false); form.resetFields(); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: () => message.error("Unable to create user. Username/email may already exist, and password must be 10+ characters."),
  });
  const patch = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) => updateUser(id, payload),
    onSuccess: () => { message.success("User updated"); qc.invalidateQueries({ queryKey: ["users"] }); },
    onError: () => message.error("Update rejected"),
  });

  if (me.data && me.data.role !== "ADMIN") {
    return <Typography.Text type="danger">Only ADMIN can manage users.</Typography.Text>;
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>User Management</Typography.Title>
          <Typography.Text type="secondary">My Company</Typography.Text>
        </div>
        <Button type="primary" onClick={() => setOpen(true)}>New User</Button>
      </div>
      <Table
        className="dense-table"
        rowKey="id"
        loading={users.isLoading}
        dataSource={users.data || []}
        pagination={false}
        columns={[
          { title: "Username", dataIndex: "username" },
          { title: "Display Name", dataIndex: "display_name" },
          { title: "Email", dataIndex: "email" },
          {
            title: "Role",
            dataIndex: "role",
            render: (role: UserRole, row: ManagedUser) => (
              <Select
                value={role}
                style={{ width: 140 }}
                options={ROLES.map((value) => ({ value, label: value }))}
                onChange={(value) => patch.mutate({ id: row.id, payload: { role: value } })}
              />
            ),
          },
          {
            title: "Active",
            dataIndex: "is_active",
            render: (value: boolean, row: ManagedUser) => (
              <Switch checked={value} onChange={(checked) => patch.mutate({ id: row.id, payload: { is_active: checked } })} />
            ),
          },
          {
            title: "Status",
            render: (_: unknown, row: ManagedUser) => <Tag color={row.is_active ? colors[row.role] : "default"}>{row.is_active ? row.role : "INACTIVE"}</Tag>,
          },
        ]}
      />
      <Drawer title="New User" open={open} onClose={() => setOpen(false)} extra={<Button type="primary" loading={create.isPending} onClick={() => form.submit()}>Create</Button>}>
        <Form form={form} layout="vertical" onFinish={(values) => create.mutate(values)}>
          <Form.Item name="username" label="Username" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="display_name" label="Display Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}><Input /></Form.Item>
          <Form.Item name="password" label="Password" extra="At least 10 characters" rules={[{ required: true, min: 10 }]}><Input.Password /></Form.Item>
          <Form.Item name="role" label="Role" initialValue="VIEWER"><Select options={ROLES.map((value) => ({ value, label: value }))} /></Form.Item>
        </Form>
        <Space direction="vertical" style={{ marginTop: 12 }}>
          <Typography.Text type="secondary">ADMIN can manage users and data upload. Other roles follow warehouse operations permissions.</Typography.Text>
        </Space>
      </Drawer>
    </>
  );
}
