import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Alert, Button, Card, Input, Popconfirm, Select, Space, Table, Tabs, Tag, Typography } from 'antd';
import { api } from '../api/client';
import { getCustomers, getWarehouses } from '../api/masterData';
import { useCurrentUser } from '../hooks/usePermissions';
import { createReviewDraft, restoreReviewDraft } from './wpsReviewDraft';

interface Row {
  sourceIdentity: Record<string, string>;
  key: string; customerId: number | null; customerMatchStatus: string;
  locationStatus: string; unknownLocations: string[];
  values: Record<string, unknown>; rawFields: Record<string, unknown>;
  issues: { field: string; code: string }[];
  linkReview?: { status: string; suggestedInboundId: number | null; written: boolean; confirmationToken?: string };
  duplicateCheck?: { status: string; candidateCount: number; candidates: {
    id: number; inboundNo: string; container: string; customerId: number | null; warehouseId: number;
    destination: string | null; cartons: string; pallets: string; location: string | null; status: number;
    comparison?: { field: string; wps: string | null; yuki: string | null; status: string }[];
    linkedToOtherSource?: boolean;
  }[] };
}
interface Sheet { sheet: string; complete: boolean; snapshotTime: string; rows: Row[]; missingFields: string[] }
interface Reconciliation { container: string; olRows: number; inboundRows: number; olCartons: string | null; inboundCartons: string | null; difference: string | null; status: string }
interface Review { sheets: Sheet[]; reconciliation: Reconciliation[]; duplicateSummary?: { recordsChecked: number; counts: Record<string, number> }; linkSummary?: { counts: Record<string, number> } }
const linkLabels: Record<string, string> = {
  ready_for_review: '字段一致 · 待人工确认', shared_candidate: '多条 WPS 明细匹配同一入库单',
  multiple_matches: '多张入库单字段一致', needs_comparison: '字段缺失、不一致或已被关联',
  customer_required: '先确认客户', warehouse_required: '先选择目标仓库',
  snapshot_incomplete: '样本不完整或缺列', source_blocked: '来源标识或柜号异常',
  already_linked: '已有来源关联 · 核对变更', no_candidate: '无历史候选 · 待核实',
  too_many_candidates: '候选超过 10 条 · 待单独核查',
};
const comparisonLabels: Record<string, string> = { container: '柜号', customer: '客户', warehouse: '仓库',
  destination: '仓点', cartons: '件数', pallets: '板数', unloadDate: '拆柜日期', location: '人工库位', weight: '重量 lb（2 位小数）', cbm: '体积 CBM（4 位小数）', fba: 'FBA', po: 'PO', receivedDate: '收货日期' };
const duplicateLabels: Record<string, string> = {
  source_linked: '已有来源关联（待核对变更）', source_conflict: '来源关联冲突',
  history_candidate: '同柜历史记录 · 疑似重复', no_candidate: '未找到同柜记录',
  invalid_source: '缺少来源标识', duplicate_source: '样本来源标识重复', missing_container: '缺少柜号', not_applicable: '计划表不参与库存防重',
};
const labels: Record<string, string> = {
  matched: '匹配', manual: '手动指定', unmatched: '未匹配', ambiguous: '多个客户匹配',
  not_applicable: '—', warehouse_required: '待选仓库', missing: '缺少库位', needs_review: '库位待核对',
  missing_counterpart: '缺少同柜数据', ambiguous_inbound: '提柜记录重复', missing_quantity: '件数缺失',
  partial_snapshot: '样本不完整，暂不判定', difference: '件数不一致',
  missing_or_ambiguous: '缺失或存在多个值', destination_needs_mapping: '仓点待映射',
  zero_weight_needs_review: '重量为零，待核对', pallet_suffix_needs_review: '库位带板数后缀，待确认',
  incomplete_identity: '来源标识缺失', invalid_number: '数字格式错误', invalid_date: '日期格式错误',
};
const display = (value: unknown): string => value === null || value === undefined || value === '' ? '—' :
  Array.isArray(value) ? value.map(display).join(' / ') : typeof value === 'object' ? JSON.stringify(value) : String(value);

export function WpsReviewPage() {
  const me = useCurrentUser();
  const enabled = me.data?.role === 'ADMIN';
  const [warehouseId, setWarehouseId] = useState<number>();
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [sheetName, setSheetName] = useState('OL');
  const [search, setSearch] = useState('');
  const [issueFilter, setIssueFilter] = useState('all');
  const [duplicateFilter, setDuplicateFilter] = useState('all');
  const [linkFilter, setLinkFilter] = useState('all');
  const [reconciliationFilter, setReconciliationFilter] = useState('all');
  const [draftNotice, setDraftNotice] = useState<{ type: 'success' | 'warning' | 'error'; text: string }>();
  const customers = useQuery({ queryKey: ['wps-customers'], queryFn: getCustomers, enabled });
  const warehouses = useQuery({ queryKey: ['wps-warehouses'], queryFn: getWarehouses, enabled });
  const preview = useQuery({ queryKey: ['wps-review', warehouseId, overrides], enabled,
    queryFn: async () => (await api.post<Review>('/wps/review', { warehouse_id: warehouseId ?? null, customer_overrides: overrides })).data,
    retry: false,
  });
  const [linkNotice, setLinkNotice] = useState<{ type: 'success' | 'error'; text: string }>();
  const confirmLink = useMutation({
    mutationFn: async (row: Row) => api.post('/wps/links/confirm', {
      warehouse_id: warehouseId ?? null, customer_overrides: overrides,
      source_identity: row.sourceIdentity, inbound_id: row.linkReview?.suggestedInboundId,
      confirmation_token: row.linkReview?.confirmationToken,
    }),
    onSuccess: async () => {
      setLinkNotice({ type: 'success', text: '来源关联已保存并记录操作人；库存数量和人工库位保持原值。' });
      await preview.refetch();
    },
    onError: (error: unknown) => {
      const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
      setLinkNotice({ type: 'error', text: detail || '关联未能确认，请重新载入样本核对后重试。' });
      void preview.refetch();
    },
  });
  if (me.isLoading) return <div className="page">正在加载…</div>;
  if (!enabled) return <div className="page"><Alert type="info" message="全客户 WPS 核对页需要管理员账号。" /></div>;
  const sheet = preview.data?.sheets.find(s => s.sheet === sheetName);
  const rows = (sheet?.rows ?? []).filter(row => {
    const matchesSearch = [row.values.customer, row.values.container_number, row.values.raw_location_text]
      .some(value => display(value).toLowerCase().includes(search.trim().toLowerCase()));
    const matchesIssue = issueFilter === 'all' ||
      (issueFilter === 'customer' && !row.customerId) ||
      (issueFilter === 'location' && ['missing', 'needs_review'].includes(row.locationStatus)) ||
      (issueFilter === 'source' && row.issues.length > 0);
    return matchesSearch && matchesIssue && (duplicateFilter === 'all' || row.duplicateCheck?.status === duplicateFilter)
      && (linkFilter === 'all' || row.linkReview?.status === linkFilter);
  });
  const reconciliation = preview.data?.reconciliation ?? [];
  const reconciliationRows = reconciliation.filter(row =>
    (reconciliationFilter === 'all' || row.status === reconciliationFilter) &&
    row.container.toLowerCase().includes(search.trim().toLowerCase()));
  const options = (customers.data ?? []).filter(c => c.is_active).map(c => ({ value: c.id, label: `${c.customer_code} · ${c.customer_name}` }));
  const allRows = preview.data?.sheets.flatMap(s => s.rows) ?? [];
  const draftKey = `yuki:wps-review-draft:v1:${me.data!.id}`;
  const draftReady = !!preview.data && !preview.isFetching && !preview.isError && !!customers.data && !customers.isError && !!warehouses.data && !warehouses.isError;
  const handleDraft = (action: 'save' | 'restore' | 'delete') => {
    try {
      if (action === 'delete') {
        localStorage.removeItem(draftKey);
        setDraftNotice({ type: 'success', text: '已删除本浏览器草稿；页面当前选择保留。' });
      } else if (action === 'save') {
        const draft = createReviewDraft(allRows, overrides, warehouseId);
        localStorage.setItem(draftKey, JSON.stringify(draft));
        setDraftNotice({ type: 'success', text: `已保存 ${draft.entries.length} 条手动客户映射及仓库选择（${new Date(draft.savedAt).toLocaleString()}）。后续修改需要再次保存。` });
      } else {
        const raw = localStorage.getItem(draftKey);
        if (!raw) { setDraftNotice({ type: 'warning', text: '当前账号在此浏览器尚未保存草稿。' }); return; }
        const result = restoreReviewDraft(raw, allRows, options.map(c => c.value), (warehouses.data ?? []).filter(w => w.is_active).map(w => w.id));
        setOverrides(result.overrides);
        setWarehouseId(result.warehouseId);
        setDraftNotice({ type: result.skipped || result.warehouseRemoved ? 'warning' : 'success', text:
          `已恢复 ${new Date(result.savedAt).toLocaleString()} 的草稿，应用 ${Object.keys(result.overrides).length} 条映射。跳过 ${result.skipped} 条来源变化、来源重复或客户失效的映射。${result.warehouseRemoved ? '原仓库已失效，请重新选择。' : ''}` });
      }
    } catch (error) {
      setDraftNotice({ type: 'error', text: `草稿操作失败：${error instanceof Error ? error.message : '请检查浏览器存储权限。'}` });
    }
  };
  const valueColumn = (title: string, key: string, width = 110) => ({ title, key, width, render: (_: unknown, row: Row) => <span style={{ whiteSpace: 'pre-wrap' }}>{display(row.values[key])}</span> });
  return <div className="page">
    <div className="page-heading"><h1>WPS 数据核对</h1><p>所有客户 · 人工库位 · 导入前检查</p></div>
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert showIcon type="info" message="当前使用本地拉取样本核对，可逐条确认来源关联；尚未导入库存。"
        description="客户映射和仓库选择可手动保存为当前账号的浏览器草稿，仅在当前浏览器可恢复。重新载入样本不会访问 WPS；需要先运行拉取脚本更新样本。" />
      <Space wrap>
        <span>目标仓库</span><Select aria-label="目标仓库" placeholder="选择人工库位所属仓库" allowClear style={{ width: 260 }} value={warehouseId} onChange={setWarehouseId}
          loading={warehouses.isLoading} options={(warehouses.data ?? []).filter(w => w.is_active).map(w => ({ value: w.id, label: `${w.warehouse_code} · ${w.warehouse_name}` }))} />
        <Input aria-label="搜索客户柜号库位" placeholder="搜索客户 / 柜号 / 库位" allowClear value={search} onChange={e => setSearch(e.target.value)} style={{ width: 260 }} />
        <Select aria-label="筛选待核对项" value={issueFilter} onChange={setIssueFilter} style={{ width: 180 }} options={[
          { value: 'all', label: '全部明细' }, { value: 'customer', label: '客户待匹配' },
          { value: 'location', label: '库位待处理（先选仓库）' }, { value: 'source', label: '源字段待核对' },
        ]} />
        <Button loading={preview.isFetching} onClick={() => void preview.refetch()}>重新载入样本</Button>
        <Button disabled={!Object.keys(overrides).length} onClick={() => setOverrides({})}>清除手动客户映射</Button>
      </Space>
      <Card size="small" title="核对草稿">
        <Space wrap>
          <Button type="primary" disabled={!draftReady} onClick={() => handleDraft('save')}>保存草稿</Button>
          <Button disabled={!draftReady} onClick={() => handleDraft('restore')}>恢复草稿（替换当前选择）</Button>
          <Button onClick={() => handleDraft('delete')}>删除已存草稿</Button>
          <Typography.Text type="secondary">当前手动映射 {Object.keys(overrides).length} 条 · 覆盖 OL 和提柜两张表 · 不会写入 WPS 或库存</Typography.Text>
        </Space>
        {draftNotice && <Alert style={{ marginTop: 12 }} showIcon type={draftNotice.type} message={draftNotice.text} />}
      </Card>
      {preview.data && <Card size="small" title="导入前检查 · 全部客户与两张表">
        <Space wrap>
          <Tag color={warehouseId ? 'green' : 'orange'}>{warehouseId ? '已选目标仓库' : '待选目标仓库'}</Tag>
          <Tag>客户待匹配 {allRows.filter(r => !r.customerId).length} 条</Tag>
          <Tag>库位待处理 {allRows.filter(r => ['missing', 'needs_review', 'warehouse_required'].includes(r.locationStatus)).length} 条</Tag>
          <Tag>源字段待核对 {allRows.filter(r => r.issues.length > 0).length} 条</Tag>
          <Tag>快照不完整或缺列 {preview.data.sheets.filter(s => !s.complete || s.missingFields.length > 0).length} 张表</Tag>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>以上按原始行计数，同一行可能存在多个问题，不受下方筛选影响。防重候选见下方，库存余额与来源关联仍待核对，当前不能直接导入。</Typography.Paragraph>
      </Card>}
      {preview.data?.duplicateSummary && <Card size="small" title="已有入库记录防重 · OL 明细">
        <Space wrap>{Object.entries(preview.data.duplicateSummary.counts).map(([status, count]) =>
          <Tag key={status} color={status === 'no_candidate' ? 'default' : 'orange'}>{duplicateLabels[status] ?? status} {count} 条</Tag>)}</Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          已检查全部仓库和客户的 {preview.data.duplicateSummary.recordsChecked} 条入库记录。同柜不等于同一批货；未找到同柜记录也不代表可以导入。展开明细可查看候选（最多显示 10 条）。此检查不核对库存余额、不建立关联、不写入库存。
        </Typography.Paragraph>
      </Card>}
      {(customers.isError || warehouses.isError) && <Alert type="error" message="客户或仓库资料加载失败，请刷新页面后重试。" />}
      {preview.data?.linkSummary && <Card size="small" title="来源关联预检 · OL 明细">
        <Space wrap>{Object.entries(preview.data.linkSummary.counts).map(([status, count]) =>
          <Tag key={status} color={status === 'ready_for_review' ? 'blue' : 'orange'}>{linkLabels[status] ?? status} {count} 条</Tag>)}</Space>
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          先确认客户并选择目标仓库，再比对柜号、客户、仓库、仓点、件数、板数、拆柜日期、收货日期、人工库位、重量、体积、FBA 和 PO。
          缺少字段不视为一致；库位带板数后缀会保留。展开候选入库单可查看具体差异。
          字段一致且候选唯一时，展开候选可确认来源关联。确认只保存对应关系与审计记录；已关联记录的差异仅供核对，不会自动修改库存。
        </Typography.Paragraph>
      </Card>}
      {preview.isError && <Alert type="error" showIcon message="样本加载失败" description={((preview.error as { response?: { data?: { detail?: string } } }).response?.data?.detail) || '请检查后端连接后重试。'} />}
      {linkNotice && <Alert showIcon type={linkNotice.type} message={linkNotice.text} />}
      <Tabs activeKey={sheetName} onChange={name => { setSheetName(name); setDuplicateFilter('all'); setLinkFilter('all'); }} items={['OL', '提柜'].map(name => ({ key: name, label: name === 'OL' ? 'OL 库存明细' : '提柜计划' }))} />
      {sheetName === 'OL' && <Select aria-label="筛选来源关联预检" value={linkFilter} onChange={setLinkFilter} style={{ width: 330 }}
        options={[{ value: 'all', label: '全部来源关联预检状态' }, ...Object.entries(linkLabels).map(([value, label]) => ({ value, label }))]} />}
      {sheetName === 'OL' && <Select aria-label="筛选防重状态" value={duplicateFilter} onChange={setDuplicateFilter} style={{ width: 300 }}
        options={[{ value: 'all', label: '全部防重状态' }, ...Object.entries(duplicateLabels).filter(([key]) => key !== 'not_applicable').map(([value, label]) => ({ value, label }))]} />}
      {sheet && <>
        <Alert showIcon type={sheet.complete ? 'info' : 'warning'} message={`${sheet.complete ? '完整快照' : '部分样本'} · ${sheet.rows.length} 条 · ${sheet.rows.filter(r => !r.customerId).length} 条客户待匹配`}
          description={`样本生成时间：${new Date(sheet.snapshotTime).toLocaleString()}。${sheet.complete ? '' : '尚未拉取全部分页，数量结果仅供初步检查。'}${sheet.missingFields.length ? ` 缺少列：${sheet.missingFields.join('、')}` : ''}`} />
        <Typography.Text type="secondary">筛选结果 {rows.length} / {sheet.rows.length} 条</Typography.Text>
        <Table<Row> rowKey="key" dataSource={rows} loading={preview.isFetching} size="small" scroll={{ x: 1800 }} pagination={{ defaultPageSize: 20, showSizeChanger: true }}
          expandable={{ expandedRowRender: row => <>
            {!!row.duplicateCheck?.candidateCount && <>
              <Typography.Paragraph strong>已有入库候选：{row.duplicateCheck.candidateCount} 条（仅展示前 10 条，请核对客户、仓库及业务明细）</Typography.Paragraph>
              <Table rowKey="id" size="small" pagination={false} dataSource={row.duplicateCheck.candidates}
                expandable={{ expandedRowRender: candidate => <>
                  {row.linkReview?.status === 'already_linked' && <Alert type="info" message={`已关联：当前有 ${(candidate.comparison ?? []).filter(c => c.status !== 'equal').length} 个字段缺失或不一致。仅展示差异，不会自动更新库存。`} />}
                  {candidate.linkedToOtherSource && <Alert type="warning" message="此入库单已关联其他 WPS 来源，不能重复关联。" />}
                  <Table rowKey="field" size="small" pagination={false} dataSource={candidate.comparison ?? []} columns={[
                    { title: '比对字段', dataIndex: 'field', render: field => comparisonLabels[field] ?? field },
                    { title: 'WPS 当前值', dataIndex: 'wps', render: (value, item) => item.field === 'customer'
                      ? options.find(c => c.value === Number(value))?.label ?? display(value)
                      : item.field === 'warehouse' ? warehouses.data?.find(w => w.id === Number(value))?.warehouse_code ?? display(value) : display(value) },
                    { title: '系统历史值', dataIndex: 'yuki', render: (value, item) => item.field === 'customer'
                      ? options.find(c => c.value === Number(value))?.label ?? display(value)
                      : item.field === 'warehouse' ? warehouses.data?.find(w => w.id === Number(value))?.warehouse_code ?? display(value) : display(value) },
                    { title: '结果', dataIndex: 'status', render: status => <Tag color={status === 'equal' ? 'green' : 'orange'}>
                      {status === 'equal' ? '一致' : status === 'missing' ? '缺少有效值' : '不一致'}</Tag> },
                  ]} />
                  {row.linkReview?.status === 'ready_for_review' && row.linkReview.suggestedInboundId === candidate.id &&
                    <Popconfirm title={`确认关联到 ${candidate.inboundNo}？`}
                      description="已核对以上字段。保存此 WPS 明细与入库单的对应关系，保留库存数量和人工库位。"
                      okText="确认来源关联" cancelText="返回核对"
                      disabled={preview.isFetching || preview.isError || confirmLink.isPending}
                      onConfirm={() => confirmLink.mutateAsync(row).catch(() => undefined)}>
                      <Button type="primary" style={{ marginTop: 12 }} loading={confirmLink.isPending}
                        disabled={preview.isFetching || preview.isError}>确认此来源关联</Button>
                    </Popconfirm>}
                </> }} columns={[
                { title: '入库单号', dataIndex: 'inboundNo' }, { title: '柜号', dataIndex: 'container' },
                { title: '客户', dataIndex: 'customerId', render: id => options.find(c => c.value === id)?.label ?? `客户 ID ${id ?? '未填写'}` },
                { title: '仓库', dataIndex: 'warehouseId', render: id => warehouses.data?.find(w => w.id === id)?.warehouse_code ?? `仓库 ID ${id}` },
                { title: '仓点', dataIndex: 'destination', render: display }, { title: '件数', dataIndex: 'cartons' },
                { title: '板数', dataIndex: 'pallets' }, { title: '人工库位', dataIndex: 'location', render: display },
              ]} />
            </>}
            <Typography.Text strong>WPS 原始字段</Typography.Text><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(row.rawFields, null, 2)}</pre>
          </> }}
          columns={[
            valueColumn('原客户', 'customer', 120),
            { title: '系统客户', key: 'customer', width: 250, render: (_, row) => <Space direction="vertical" size={2}>
              <Select aria-label={`客户映射 ${row.key}`} showSearch optionFilterProp="label" allowClear placeholder="选择对应客户" value={row.customerId ?? undefined} options={options} style={{ width: 220 }}
                onChange={(id: number | undefined) => setOverrides(current => { const next = { ...current }; if (id === undefined) delete next[row.key]; else next[row.key] = id; return next; })} />
              <Tag color={row.customerId ? 'green' : 'orange'}>{labels[row.customerMatchStatus]}</Tag>
            </Space> },
            valueColumn('柜号', 'container_number', 160), valueColumn('仓点', 'destination'),
            { title: '来源关联预检', key: 'linkReview', width: 210, render: (_, row) => row.linkReview
              ? linkLabels[row.linkReview.status] ?? row.linkReview.status : '—' },
            { title: '已有入库防重', key: 'duplicates', width: 210, render: (_, row) => row.duplicateCheck ? <>
              {duplicateLabels[row.duplicateCheck.status] ?? row.duplicateCheck.status}
              {!!row.duplicateCheck.candidateCount && <div>{row.duplicateCheck.candidateCount} 条候选 · 展开查看</div>}
            </> : '尚未检查' },
            valueColumn('原始库位', 'raw_location_text', 150),
            { title: '库位核对', key: 'location', width: 170, render: (_, row) => <>{labels[row.locationStatus]}{row.unknownLocations.length > 0 && <div>未找到：{row.unknownLocations.join('、')}</div>}</> },
            valueColumn('板数', 'pallet_qty', 80), valueColumn('件数', 'carton_qty', 80),
            valueColumn('重量 lb', 'weight_lbs', 90), valueColumn('体积 CBM', 'cbm', 95),
            valueColumn('FBA', 'fba_references', 160), valueColumn('PO', 'po_numbers', 160),
            { title: '源数据待核对项', key: 'issues', width: 250, render: (_, row) => row.issues.length ? row.issues.map((i, index) => <div key={index}>{i.field}：{labels[i.code] ?? i.code}</div>) : '未发现字段格式问题' },
          ]} />
      </>}
      {preview.data && <Card title="同柜件数核对 · OL 汇总 / 提柜计划">
        <Typography.Paragraph type="secondary">只有两张表均已完整拉取且存在唯一提柜记录、件数齐全，才判定是否一致。这里比较 WPS 两张表，不代表与系统现有库存一致。</Typography.Paragraph>
        <Space wrap style={{ marginBottom: 12 }}>
          <Select aria-label="筛选同柜核对状态" value={reconciliationFilter} onChange={setReconciliationFilter} style={{ width: 260 }} options={[
            { value: 'all', label: `全部柜号（${reconciliation.length}）` },
            ...['matched', 'difference', 'missing_counterpart', 'ambiguous_inbound', 'missing_quantity', 'partial_snapshot'].map(status => ({
              value: status, label: `${labels[status]}（${reconciliation.filter(row => row.status === status).length}）`,
            })),
          ]} />
          <Typography.Text type="secondary">共 {reconciliationRows.length} 柜；上方搜索在此表仅匹配柜号。</Typography.Text>
        </Space>
        <Table<Reconciliation> rowKey="container" dataSource={reconciliationRows} size="small" pagination={{ defaultPageSize: 10, showSizeChanger: true }} scroll={{ x: 850 }} columns={[
          { title: '柜号', dataIndex: 'container' }, { title: 'OL 行数', dataIndex: 'olRows' }, { title: '提柜行数', dataIndex: 'inboundRows' },
          { title: 'OL 件数', dataIndex: 'olCartons', render: display }, { title: '提柜件数', dataIndex: 'inboundCartons', render: display },
          { title: '样本差值', dataIndex: 'difference', render: display }, { title: '状态', dataIndex: 'status', render: (status: string) => <Tag color={status === 'matched' ? 'green' : 'orange'}>{labels[status]}</Tag> },
        ]} />
      </Card>}
    </Space>
  </div>;
}
