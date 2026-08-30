import { DownloadOutlined, ReloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Drawer, Input, Select, Space, Table, Tag, Timeline, Typography } from "antd";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { downloadDocument, getDocumentEvents, getDocuments } from "../api/documents";
import { getWarehouses } from "../api/masterData";

const types = ["BOL", "POD", "DELIVERY_RECEIPT", "WAREHOUSE", "EXCEPTION_ATTACHMENT", "GENERAL"];
const statuses = ["DRAFT", "AVAILABLE", "RECEIVED", "PENDING", "SUPERSEDED", "ARCHIVED"];

export function DocumentsPage() {
  const [sp] = useSearchParams();
  const [params, setParams] = useState<any>({ page: 1, per_page: 20, document_type: sp.get("document_type") || undefined, status: sp.get("status") || undefined });
  const [selected, setSelected] = useState<number | null>(Number(sp.get("selected") || 0) || null);
  const list = useQuery({ queryKey: ["documents", params], queryFn: () => getDocuments(params) });
  const events = useQuery({ queryKey: ["document-events", selected], queryFn: () => getDocumentEvents(selected!), enabled: !!selected });
  const wh = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const current = list.data?.data.find((row) => row.id === selected);
  return <div className="page">
    <div className="page-heading">
      <div><Typography.Title level={4}>Documents</Typography.Title><Typography.Text type="secondary">Operational Document Center</Typography.Text></div>
      <Button icon={<ReloadOutlined />} onClick={() => list.refetch()}>Refresh</Button>
    </div>
    <div className="dispatch-filters">
      <Input placeholder="Search document or file" onPressEnter={(e) => setParams((p: any) => ({ ...p, q: e.currentTarget.value, page: 1 }))} />
      <Select allowClear placeholder="Type" options={types.map((x) => ({ value: x, label: x }))} onChange={(v) => setParams((p: any) => ({ ...p, document_type: v, page: 1 }))} />
      <Select allowClear placeholder="Status" options={statuses.map((x) => ({ value: x, label: x }))} onChange={(v) => setParams((p: any) => ({ ...p, status: v, page: 1 }))} />
      <Select allowClear placeholder="Warehouse" options={(wh.data || []).map((x: any) => ({ value: x.id, label: x.warehouse_code }))} onChange={(v) => setParams((p: any) => ({ ...p, warehouse_id: v, page: 1 }))} />
    </div>
    <Table rowKey="id" loading={list.isLoading} dataSource={list.data?.data || []} onRow={(r) => ({ onClick: () => setSelected(r.id) })}
      pagination={{ current: list.data?.meta.page, pageSize: list.data?.meta.per_page, total: list.data?.meta.total, onChange: (page) => setParams((p: any) => ({ ...p, page })) }}
      columns={[
        { title: "Document", dataIndex: "document_no" },
        { title: "Type", dataIndex: "document_type", render: (v: string) => <Tag>{v}</Tag> },
        { title: "Status", dataIndex: "status" },
        { title: "Reference", render: (_: unknown, r) => r.references.map((x) => x.label).join(", ") || "—" },
        { title: "Warehouse", dataIndex: "warehouse_code" },
        { title: "File", dataIndex: "original_file_name" },
        { title: "Ver", dataIndex: "version" },
        { title: "Uploaded By", dataIndex: "uploader_name" },
        { title: "Uploaded At", dataIndex: "uploaded_at", render: (v: string) => new Date(v).toLocaleString() },
      ]} />
    <Drawer width={480} title={current?.document_no || "Document"} open={!!selected} onClose={() => setSelected(null)}>
      {current && <>
        <Typography.Paragraph>{current.document_type} · {current.status} · v{current.version}</Typography.Paragraph>
        <Typography.Paragraph>{current.original_file_name}</Typography.Paragraph>
        <Space wrap>{current.references.map((r) => <Tag key={`${r.kind}-${r.id}`}>{r.kind} {r.label}</Tag>)}</Space>
        <div style={{ margin: "12px 0" }}><Button icon={<DownloadOutlined />} onClick={() => downloadDocument(current.id, current.original_file_name)}>Download</Button></div>
        <Typography.Title level={5}>History</Typography.Title>
        <Timeline items={(events.data?.data || []).map((e: any) => ({ children: <><b>{e.event_type}</b><br /><small>{new Date(e.created_at).toLocaleString()} · {e.actor_name}</small></> }))} />
      </>}
    </Drawer>
  </div>;
}
