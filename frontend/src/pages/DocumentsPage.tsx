import { DownloadOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Alert,
  Drawer,
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
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  archiveDocument,
  downloadDocument,
  getDocument,
  getDocumentEvents,
  getDocuments,
  OperationalDocument,
  uploadDocument,
} from "../api/documents";
import { usePermission } from "../hooks/usePermissions";

const TYPES = [
  "BOL",
  "POD",
  "DELIVERY_RECEIPT",
  "WAREHOUSE",
  "EXCEPTION_ATTACHMENT",
  "GENERAL",
];
export function DocumentsPage() {
  const [searchParams] = useSearchParams();
  const qc = useQueryClient();
  const { allowed: canOutbound } = usePermission("manage_outbound");
  const { allowed: canWarehouse } = usePermission("manage_warehouse");
  const canWrite = canOutbound || canWarehouse;
  const [params, setParams] = useState<Record<string, unknown>>({
    page: 1,
    per_page: 50,
  });
  const [selected, setSelected] = useState<OperationalDocument | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const errorText = (e: any, fallback: string) => {
    const detail = e.response?.data?.detail;
    return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : fallback;
  };
  const [form] = Form.useForm();
  const resetUpload = () => {
    setFile(null);
    setUploadError(null);
    form.resetFields();
  };
  const selectedId = Number(searchParams.get("selected"));
  const linkedDocument = useQuery({
    queryKey: ["document", selectedId],
    queryFn: () => getDocument(selectedId),
    enabled: Number.isInteger(selectedId) && selectedId > 0,
  });
  useEffect(() => {
    if (linkedDocument.data) setSelected(linkedDocument.data);
  }, [linkedDocument.data]);
  const list = useQuery({
    queryKey: ["documents", params],
    queryFn: () => getDocuments(params),
  });
  const events = useQuery({
    queryKey: ["document-events", selected?.id],
    queryFn: () => getDocumentEvents(selected!.id),
    enabled: !!selected,
  });
  const create = useMutation({
    mutationFn: (v: Record<string, unknown>) => uploadDocument(v, file!),
    onSuccess: () => {
      message.success("Document uploaded");
      setUploadOpen(false);
      setFile(null);
      setUploadError(null);
      form.resetFields();
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e: any) => setUploadError(errorText(e, "Upload failed; check the connection and retry")),
  });
  const archive = useMutation({
    mutationFn: archiveDocument,
    onSuccess: () => {
      message.success("Document archived");
      setSelected(null);
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (e: any) => message.error(errorText(e, "Archive failed")),
  });
  return (
    <div className="page">
      <Space style={{ width: "100%", justifyContent: "space-between" }}>
        <div>
          <Typography.Title level={2}>Document & POD Center</Typography.Title>
          <Typography.Text type="secondary">
            Controlled operational files, generated BOLs, POD receipts and
            append-only history.
          </Typography.Text>
        </div>
        {canWrite && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => { resetUpload(); setUploadOpen(true); }}
          >
            Upload
          </Button>
        )}
      </Space>
      <Space wrap style={{ margin: "20px 0" }}>
        <Input.Search
          allowClear
          placeholder="Document no, filename or BOL"
          onSearch={(q) => setParams((p) => ({ ...p, q: q || undefined }))}
        />
        <Select
          allowClear
          placeholder="Type"
          style={{ width: 210 }}
          options={TYPES.map((x) => ({ value: x }))}
          onChange={(document_type) =>
            setParams((p) => ({ ...p, document_type }))
          }
        />
        <Select
          allowClear
          placeholder="Status"
          style={{ width: 160 }}
          options={["AVAILABLE", "SUPERSEDED", "ARCHIVED"].map((x) => ({
            value: x,
          }))}
          onChange={(status) => setParams((p) => ({ ...p, status }))}
        />
      </Space>
      <Table
        rowKey="id"
        loading={list.isLoading}
        dataSource={list.data?.data || []}
        pagination={{ pageSize: 50, total: list.data?.meta.total }}
        onRow={(r) => ({ onClick: () => setSelected(r) })}
        columns={[
          { title: "Document", dataIndex: "document_no" },
          {
            title: "Type",
            dataIndex: "document_type",
            render: (v: string) => (
              <Tag
                color={v === "POD" ? "green" : v === "BOL" ? "blue" : undefined}
              >
                {v}
              </Tag>
            ),
          },
          { title: "File", dataIndex: "original_filename" },
          { title: "Version", dataIndex: "version", render: (v) => `v${v}` },
          {
            title: "Status",
            dataIndex: "status",
            render: (v) => <Tag>{v}</Tag>,
          },
          {
            title: "Created",
            dataIndex: "created_at",
            render: (v) => new Date(v).toLocaleString(),
          },
          {
            title: "",
            render: (_, r) => (
              <Button
                icon={<DownloadOutlined />}
                onClick={(e) => {
                  e.stopPropagation();
                  downloadDocument(r);
                }}
              />
            ),
          },
        ]}
      />
      <Drawer
        width={520}
        open={!!selected}
        onClose={() => setSelected(null)}
        title={selected?.document_no}
        extra={
          selected && canWrite && selected.status !== "ARCHIVED" ? (
            <Button danger onClick={() => archive.mutate(selected.id)}>
              Archive
            </Button>
          ) : null
        }
      >
        {selected && (
          <>
            <Typography.Title level={5}>
              {selected.original_filename}
            </Typography.Title>
            <p>
              <Tag color={selected.document_type === "POD" ? "green" : "blue"}>
                {selected.document_type}
              </Tag>{" "}
              Version {selected.version} · {selected.status}
            </p>
            <p>{selected.title || "No title"}</p>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => downloadDocument(selected)}
            >
              Download
            </Button>
            <Typography.Title level={5} style={{ marginTop: 24 }}>
              Event history
            </Typography.Title>
            {events.data?.map((e) => (
              <div
                key={e.id}
                style={{
                  borderLeft: "2px solid #d9d9d9",
                  padding: "0 0 16px 12px",
                }}
              >
                <b>{e.event_type}</b>
                <div>{e.message}</div>
                <Typography.Text type="secondary">
                  {new Date(e.created_at).toLocaleString()}
                </Typography.Text>
              </div>
            ))}
          </>
        )}
      </Drawer>
      <Modal
        open={uploadOpen}
        onCancel={() => { if (!create.isPending) { setUploadOpen(false); resetUpload(); } }}
        closable={!create.isPending}
        maskClosable={!create.isPending}
        cancelButtonProps={{ disabled: create.isPending }}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
        okButtonProps={{ disabled: !file || create.isPending }}
        title="Upload operational document"
      >
        {uploadError && <Alert type="error" showIcon message={uploadError} style={{ marginBottom: 16 }} />}
        <Form form={form} layout="vertical" onFinish={(v) => { if (file && !create.isPending) { setUploadError(null); create.mutate(v); } }}>
          <Form.Item
            name="document_type"
            label="Document type"
            rules={[{ required: true }]}
          >
            <Select
              options={TYPES.filter((x) => x !== "BOL").map((x) => ({
                value: x,
              }))}
            />
          </Form.Item>
          <Form.Item label="File" required>
            <Upload
              disabled={create.isPending}
              fileList={file ? [{ uid: 'selected-file', name: file.name, status: 'done' }] : []}
              onRemove={() => { setFile(null); setUploadError(null); return true; }}
              beforeUpload={(f) => {
                setFile(f);
                setUploadError(null);
                return false;
              }}
              maxCount={1}
              accept=".pdf,.xlsx,.xls,.csv,.jpg,.jpeg,.png"
            >
              <Button>Select file</Button>
            </Upload>
          </Form.Item>
          <Typography.Text type="secondary">
            Link at least one operational record.
          </Typography.Text>
          <Form.Item name="load_id" label="Load ID">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="outbound_id" label="Outbound ID">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="work_order_id" label="Work order ID">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="operational_exception_id" label="Exception ID">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="container_tracking_id" label="Container ID">
            <Input type="number" />
          </Form.Item>
          <Form.Item name="title" label="Title">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
