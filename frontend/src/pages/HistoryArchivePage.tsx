import { useState } from 'react';
import { Alert, Button, Descriptions, Drawer, Input, Select, Space, Table, Typography, message } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';

type Sheet = { id: number; sheet: string; file_name: string; total_rows: number; columns: string[]; warehouse: string };
type Row = { id: number; row_number: number; conversion?: {business_no?: string}; data: Record<string, unknown> };
const display = (v: unknown) => v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v);

export function HistoryArchivePage() {
  const [sheetId, setSheetId] = useState<number>();
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Row>();
  const [downloading, setDownloading] = useState(false);
  const sheets = useQuery({ queryKey: ['history-archive'], queryFn: async () => (await api.get<Sheet[]>('/history-archive')).data });
  const sheet = sheets.data?.find(s => s.id === sheetId) ?? sheets.data?.[0];
  const records = useQuery({ queryKey: ['history-archive-records', sheet?.id, query, page], enabled: !!sheet,
    queryFn: async () => (await api.get<{ total: number; rows: Row[] }>(`/history-archive/${sheet!.id}/records`, { params: { q: query, page, page_size: 50 } })).data });
  async function download() {
    if (!sheet) return;
    setDownloading(true);
    try {
      const result = await api.get(`/history-archive/${sheet.id}/source`, { responseType: 'blob' });
      const url = URL.createObjectURL(result.data); const link = document.createElement('a');
      link.href = url; link.download = sheet.file_name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { message.error('原始文件下载失败，请重试'); }
    finally { setDownloading(false); }
  }
  return <div className="page">
    <Typography.Title level={4}>美西仓历史档案</Typography.Title>
    <Alert type="info" showIcon message="历史业务记录已转换，可按转换后单号查询。原表数据保留；可用库存需另行核对。" description="保留原表字段、出入库时间与原始行号。点击记录查看全部字段；照片和附件请下载原始 Excel 查看。" style={{ marginBottom: 16 }} />
    {(sheets.isError || records.isError) && <Alert type="error" message="读取档案失败，请刷新重试" />}
    <Space wrap style={{ marginBottom: 16 }}>
      <Select style={{ minWidth: 250 }} loading={sheets.isLoading} value={sheet?.id} options={sheets.data?.map(s => ({ value: s.id, label: `${s.sheet} · ${s.total_rows.toLocaleString()} 条` }))} onChange={v => { setSheetId(v); setPage(1); setSelected(undefined); }} />
      <Input.Search allowClear placeholder="搜索柜号、FBA、PO 或任意字段" style={{ width: 340 }} onSearch={v => { setQuery(v); setPage(1); }} enterButton="搜索" />
      <Button disabled={!sheet} loading={downloading} onClick={download}>下载原始 Excel</Button>
    </Space>
    <Typography.Paragraph type="secondary">{sheet?.warehouse} · {sheet?.file_name} · 全部 {sheets.data?.reduce((n, s) => n + s.total_rows, 0).toLocaleString() ?? '—'} 条</Typography.Paragraph>
    <Table<Row> rowKey="id" size="small" loading={records.isLoading || sheets.isLoading} dataSource={records.data?.rows ?? []}
      onRow={row => ({ onClick: () => setSelected(row), style: { cursor: 'pointer' } })}
      columns={[{ title: '原表行号', dataIndex: 'row_number', width: 100, fixed: 'left' }, { title: '转换后单号', width: 200, render: (_: unknown, row: Row) => row.conversion?.business_no ?? '参考档案' }, ...(sheet?.columns ?? []).map(c => ({ title: c, key: c, width: 180, ellipsis: true, render: (_: unknown, row: Row) => display(row.data[c]) }))]}
      scroll={{ x: Math.max(1000, (sheet?.columns.length ?? 0) * 180), y: 520 }}
      pagination={{ current: page, pageSize: 50, total: records.data?.total ?? 0, showSizeChanger: false, onChange: setPage, showTotal: n => `共 ${n.toLocaleString()} 条` }} />
    <Drawer open={!!selected} onClose={() => setSelected(undefined)} width={800} title={`${sheet?.sheet} · 原表第 ${selected?.row_number} 行`}>
      <Descriptions bordered column={1} items={Object.entries(selected?.data ?? {}).map(([key, value]) => ({ key, label: key, children: <span style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{display(value) || '—'}</span> }))} />
    </Drawer>
  </div>;
}
