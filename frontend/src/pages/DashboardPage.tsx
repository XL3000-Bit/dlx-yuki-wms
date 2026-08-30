import { ReloadOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, DatePicker, Empty, Select, Space, Statistic, Table, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getOperationsDashboard } from "../api/dashboard";
import { getWarehouses } from "../api/masterData";
import { usePermissions } from "../hooks/usePermissions";

const presets = [
  { value: "today", label: "Today" },
  { value: "yesterday", label: "Yesterday" },
  { value: "last_7_days", label: "Last 7 Days" },
  { value: "this_month", label: "This Month" },
  { value: "custom", label: "Custom" },
];

const agingLabel: Record<string, string> = { lt_4h: "< 4h", h4_12: "4–12h", h12_24: "12–24h", d1_3: "1–3d", gt_3d: "> 3d", gt_24h: "> 24h" };

export function DashboardPage() {
  const { warehouseIds, warehouseScopeMode } = usePermissions();
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const [preset, setPreset] = useState("today");
  const [custom, setCustom] = useState<[string, string] | null>(null);
  const warehouses = useQuery({ queryKey: ["warehouses"], queryFn: getWarehouses });
  const params = useMemo(() => ({
    warehouse_id: warehouseId,
    preset: preset === "custom" ? undefined : preset,
    date_from: preset === "custom" ? custom?.[0] : undefined,
    date_to: preset === "custom" ? custom?.[1] : undefined,
  }), [warehouseId, preset, custom]);
  const dash = useQuery({ queryKey: ["operations-dashboard", params], queryFn: () => getOperationsDashboard(params) });
  const data = dash.data;
  const cards = data ? [
    ["Active Loads", data.summary.active_loads],
    ["Outbound Ready", data.summary.outbound_ready_active],
    ["Open Work Orders", data.summary.open_work_orders],
    ["Open Exceptions", data.summary.open_exceptions],
    ["Critical Exceptions", data.summary.critical_exceptions],
    ["Completed Today", data.summary.completed_today],
  ] as const : [];
  const showBreakdown = (data?.warehouse_breakdown.length || 0) > 1;

  return (
    <div className="page dashboard-page">
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>Operations Command</Typography.Title>
          <Typography.Text type="secondary">Snapshot vs period facts · scoped to your warehouses</Typography.Text>
        </div>
        <Space wrap>
          <Select allowClear placeholder="Warehouse" style={{ width: 160 }} value={warehouseId} onChange={setWarehouseId} options={(warehouses.data || []).map((w: any) => ({ value: w.id, label: w.warehouse_code }))} />
          <Select style={{ width: 140 }} value={preset} options={presets} onChange={setPreset} />
          {preset === "custom" && <DatePicker.RangePicker onChange={(v) => setCustom(v ? [v[0]!.format("YYYY-MM-DD"), v[1]!.format("YYYY-MM-DD")] : null)} />}
          <Button icon={<ReloadOutlined />} onClick={() => dash.refetch()}>Refresh</Button>
        </Space>
      </div>
      {dash.isError && <div className="error-state">Unable to load operations dashboard.</div>}
      <div className="dashboard-cards">
        {cards.map(([title, card]) => (
          <Link key={title} to={card.href} className="dashboard-card">
            <Card size="small" loading={dash.isLoading}>
              <Statistic title={title} value={card.value} />
              <Typography.Text type="secondary">{card.kind}</Typography.Text>
            </Card>
          </Link>
        ))}
      </div>
      <div className="dashboard-grid">
        <Card size="small" title="Work Order Funnel" loading={dash.isLoading}>
          {(data?.work_orders.funnel || []).map((row) => (
            <div key={row.key} className="funnel-row"><span>{row.key}</span><b>{row.value}</b></div>
          ))}
          <Typography.Paragraph type="secondary">Overdue (has scheduled_at): {data?.work_orders.overdue ?? 0}</Typography.Paragraph>
        </Card>
        <Card size="small" title="Exception Aging" loading={dash.isLoading}>
          {Object.entries(data?.exceptions.aging || {}).map(([key, value]) => (
            <div key={key} className="funnel-row"><span>{agingLabel[key] || key}</span><b>{value}</b></div>
          ))}
          <Typography.Paragraph type="secondary">Avg resolution: {data?.exceptions.average_resolution_seconds == null ? "n/a" : `${Math.round((data.exceptions.average_resolution_seconds || 0) / 3600)}h`}</Typography.Paragraph>
        </Card>
        <Card size="small" title="Open Exception Types" loading={dash.isLoading}>
          {(data?.exceptions.types_open || []).length ? (data!.exceptions.types_open.map((row) => (
            <div key={row.type} className="funnel-row"><span>{row.type}</span><b>{row.count}</b></div>
          ))) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No open exceptions" />}
        </Card>
      </div>
      {showBreakdown && (
        <Card size="small" title="Warehouse Breakdown" style={{ margin: 12 }}>
          <Table size="small" rowKey="warehouse_id" pagination={false} dataSource={data?.warehouse_breakdown || []} columns={[
            { title: "Warehouse", dataIndex: "warehouse_code" },
            { title: "Active Loads", dataIndex: "active_loads" },
            { title: "Open WOs", dataIndex: "open_work_orders" },
            { title: "Open Exceptions", dataIndex: "open_exceptions" },
            { title: "Critical", dataIndex: "critical_exceptions" },
          ]} />
        </Card>
      )}
      <div className="dashboard-grid">
        <Card size="small" title="Needs Attention" loading={dash.isLoading}>
          {(data?.attention || []).length ? <Table size="small" rowKey={(r) => `${r.kind}-${r.id}`} pagination={false} dataSource={data?.attention} columns={[
            { title: "Ref", dataIndex: "reference", render: (v: string, r) => <Link to={r.target_route}>{v}</Link> },
            { title: "Kind", dataIndex: "kind" },
            { title: "State", render: (_: unknown, r) => <Tag>{r.severity_or_priority}</Tag> },
            { title: "Age h", dataIndex: "age_hours" },
          ]} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Nothing aging or critical" />}
        </Card>
        <Card size="small" title="Recent Activity" loading={dash.isLoading}>
          {(data?.recent_activity || []).length ? <Table size="small" rowKey={(r, i) => `${r.kind}-${i}`} pagination={false} dataSource={data?.recent_activity} columns={[
            { title: "When", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleString() },
            { title: "Ref", dataIndex: "reference", render: (v: string, r) => <Link to={r.target_route}>{v}</Link> },
            { title: "Event", dataIndex: "event_type" },
          ]} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No recent events" />}
        </Card>
      </div>
      {warehouseScopeMode === "SELECTED" && warehouseIds.length === 1 && <Typography.Paragraph type="secondary" style={{ padding: 12 }}>Single-warehouse scope · breakdown hidden.</Typography.Paragraph>}
    </div>
  );
}
