import { DownloadOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography, Upload, message } from "antd";
import { useState } from "react";
import { archiveDocument, downloadDocument, getDocuments, uploadDocument } from "../api/documents";
import { usePermissions } from "../hooks/usePermissions";

const types = ["BOL", "POD", "DELIVERY_RECEIPT", "WAREHOUSE", "EXCEPTION_ATTACHMENT", "GENERAL"];

export function DocumentsPanel(props: { loadId?: number; outboundId?: number; workOrderId?: number; exceptionId?: number; allowedTypes?: string[] }) {
  const qc = useQueryClient();
  const { canWriteWarehouse, canWriteOutbound } = usePermissions();
  const canUpload = canWriteWarehouse || canWriteOutbound;
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const params = {
    load_id: props.loadId,
    outbound_id: props.outboundId,
    work_order_id: props.workOrderId,
    exception_id: props.exceptionId,
    per_page: 50,
  };
  const list = useQuery({ queryKey: ["documents", params], queryFn: () => getDocuments(params), enabled: !!(props.loadId || props.outboundId || props.workOrderId || props.exceptionId) });
  const upload = useMutation({
    mutationFn: uploadDocument,
    onSuccess: () => { message.success("Document uploaded"); setOpen(false); form.resetFields(); qc.invalidateQueries({ queryKey: ["documents"] }); },
    onError: (e: any) => message.error(e.response?.data?.detail || "Upload rejected"),
  });
  const archive = useMutation({
    mutationFn: archiveDocument,
    onSuccess: () => { message.success("Archived"); qc.invalidateQueries({ queryKey: ["documents"] }); },
    onError: () => message.error("Unable to archive"),
  });
  const options = (props.allowedTypes || types).map((x) => ({ value: x, label: x }));
  const pod = (list.data?.data || []).find((d) => d.document_type === "POD" && ["AVAILABLE", "RECEIVED"].includes(d.status));
  return <>
    <div className="page-heading" style={{ height: 48 }}>
      <Typography.Title level={5}>Documents {props.loadId ? <Tag color={pod ? "green" : "orange"}>{pod ? "POD Received" : "Pending POD"}</Tag> : null}</Typography.Title>
      {canUpload && <Button size="small" icon={<PlusOutlined />} onClick={() => setOpen(true)}>Upload</Button>}
    </div>
    <Table size="small" rowKey="id" pagination={false} loading={list.isLoading} dataSource={list.data?.data || []} columns={[
      { title: "Type", dataIndex: "document_type", render: (v: string) => <Tag>{v}</Tag> },
      { title: "File", dataIndex: "original_file_name" },
      { title: "Status", dataIndex: "status" },
      { title: "Ver", dataIndex: "version", width: 50 },
      { title: "By", dataIndex: "uploader_name" },
      { title: "Date", dataIndex: "uploaded_at", render: (v: string) => new Date(v).toLocaleString() },
      { title: "", render: (_: unknown, row) => <Space>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadDocument(row.id, row.original_file_name)} />
        {canUpload && row.status !== "ARCHIVED" && <Button size="small" onClick={() => archive.mutate(row.id)}>Archive</Button>}
      </Space> },
    ]} />
    <Modal title="Upload Document" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={upload.isPending}>
      <Form form={form} layout="vertical" onFinish={(v) => upload.mutate({
        file: v.file.file.originFileObj || v.file.file,
        document_type: v.document_type,
        description: v.description,
        load_id: props.loadId,
        outbound_id: props.outboundId,
        work_order_id: props.workOrderId,
        exception_id: props.exceptionId,
      })}>
        <Form.Item name="document_type" label="Type" rules={[{ required: true }]}><Select options={options} /></Form.Item>
        <Form.Item name="file" label="File" rules={[{ required: true }]} valuePropName="file"><Upload beforeUpload={() => false} maxCount={1}><Button>Select file</Button></Upload></Form.Item>
        <Form.Item name="description" label="Description"><Input /></Form.Item>
      </Form>
    </Modal>
  </>;
}
