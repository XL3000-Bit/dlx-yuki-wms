import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import {
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  downloadDocument,
  getDocuments,
  uploadDocument,
  type DocumentType,
  type OperationalDocument,
} from "../api/documents";
import { usePermission } from "../hooks/usePermissions";

type Relation = Partial<
  Record<
    "load_id" | "outbound_id" | "work_order_id" | "operational_exception_id",
    number
  >
>;
const types: DocumentType[] = [
  "POD",
  "DELIVERY_RECEIPT",
  "WAREHOUSE",
  "EXCEPTION_ATTACHMENT",
  "GENERAL",
];

export function EntityDocuments({ relation }: { relation: Relation }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const [file, setFile] = useState<File | null>(null);
  const outbound = usePermission("manage_outbound");
  const warehouse = usePermission("manage_warehouse");
  const canUpload = outbound.allowed || warehouse.allowed;
  const key = JSON.stringify(relation);
  const list = useQuery({
    queryKey: ["entity-documents", key],
    queryFn: () => getDocuments({ ...relation, per_page: 20 }),
  });
  const upload = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      uploadDocument({ ...values, ...relation }, file!),
    onSuccess: () => {
      message.success("Document uploaded");
      setOpen(false);
      form.resetFields();
      setFile(null);
      qc.invalidateQueries({ queryKey: ["entity-documents", key] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: () => message.error("Document upload rejected"),
  });
  return (
    <>
      <Space
        style={{
          width: "100%",
          justifyContent: "space-between",
          marginTop: 12,
        }}
      >
        <Typography.Title level={5}>Documents</Typography.Title>
        {canUpload && (
          <Button
            size="small"
            icon={<UploadOutlined />}
            onClick={() => setOpen(true)}
          >
            Upload
          </Button>
        )}
      </Space>
      <Table
        size="small"
        rowKey="id"
        loading={list.isLoading}
        dataSource={list.data?.data ?? []}
        pagination={false}
        locale={{ emptyText: "No documents" }}
        columns={[
          {
            title: "Document",
            render: (_: unknown, r: OperationalDocument) => (
              <>
                <b>{r.document_no}</b>
                <br />
                <small>{r.original_filename}</small>
              </>
            ),
          },
          {
            title: "Type",
            dataIndex: "document_type",
            render: (v: string) => (
              <Tag color={v === "POD" ? "green" : undefined}>{v}</Tag>
            ),
          },
          { title: "Ver.", dataIndex: "version", width: 55 },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string) => <Tag>{v}</Tag>,
          },
          {
            title: "",
            width: 45,
            render: (_: unknown, r: OperationalDocument) => (
              <Button
                type="text"
                icon={<DownloadOutlined />}
                onClick={() => downloadDocument(r)}
              />
            ),
          },
        ]}
      />
      <Modal
        title="Upload document"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => (file ? form.submit() : message.error("Select a file"))}
        confirmLoading={upload.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => upload.mutate(v)}>
          <Form.Item
            name="document_type"
            label="Document type"
            rules={[{ required: true }]}
          >
            <Select options={types.map((x) => ({ value: x, label: x }))} />
          </Form.Item>
          <Form.Item name="title" label="Title">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea />
          </Form.Item>
          <Form.Item label="File" required>
            <Upload
              beforeUpload={(f) => {
                setFile(f);
                return false;
              }}
              maxCount={1}
            >
              <Button>Select file</Button>
            </Upload>
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
