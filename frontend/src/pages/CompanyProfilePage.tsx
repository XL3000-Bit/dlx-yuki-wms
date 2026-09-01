import { Button, Card, Form, Input, Select, Typography, message } from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "../api/client";
import { getWarehouses } from "../api/masterData";
import { useCurrentUser } from "../hooks/usePermissions";

type Profile = {
  company_name: string;
  brand_name: string;
  legal_name: string;
  email: string;
  phone: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  country: string;
  timezone: string;
  default_warehouse_id: number | null;
};

export function CompanyProfilePage() {
  const [form] = Form.useForm<Profile>();
  const qc = useQueryClient();
  const me = useCurrentUser();
  const isAdmin = me.data?.role === "ADMIN";
  const profile = useQuery({ queryKey: ["company-profile"], queryFn: async () => (await api.get<Profile>("/company-profile")).data });
  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const save = useMutation({
    mutationFn: async (values: Profile) => (await api.put("/company-profile", values)).data,
    onSuccess: () => { message.success("Company profile saved"); qc.invalidateQueries({ queryKey: ["company-profile"] }); },
    onError: () => message.error("Save rejected. ADMIN role required."),
  });
  useEffect(() => { if (profile.data) form.setFieldsValue(profile.data); }, [profile.data, form]);

  return (
    <>
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>Company Profile</Typography.Title>
          <Typography.Text type="secondary">My Company</Typography.Text>
        </div>
        {isAdmin && <Button type="primary" loading={save.isPending} onClick={() => form.submit()}>Save</Button>}
      </div>
      <Card loading={profile.isLoading}>
        <Form form={form} layout="vertical" className="two-col-form" onFinish={(values) => save.mutate(values)} disabled={!isAdmin}>
          <Form.Item name="company_name" label="Company Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="brand_name" label="Brand Name" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="legal_name" label="Legal Name"><Input /></Form.Item>
          <Form.Item name="email" label="Email"><Input /></Form.Item>
          <Form.Item name="phone" label="Phone"><Input /></Form.Item>
          <Form.Item name="address" label="Address" className="full"><Input /></Form.Item>
          <Form.Item name="city" label="City"><Input /></Form.Item>
          <Form.Item name="state" label="State"><Input /></Form.Item>
          <Form.Item name="zip_code" label="ZIP"><Input /></Form.Item>
          <Form.Item name="country" label="Country"><Input maxLength={2} /></Form.Item>
          <Form.Item name="timezone" label="Timezone"><Input /></Form.Item>
          <Form.Item name="default_warehouse_id" label="Default Warehouse">
            <Select allowClear options={(warehouses.data || []).map((row) => ({ value: row.id, label: `${row.warehouse_code} — ${row.warehouse_name}` }))} />
          </Form.Item>
        </Form>
        {!isAdmin && <Typography.Text type="secondary">Only ADMIN can save company profile.</Typography.Text>}
      </Card>
    </>
  );
}
