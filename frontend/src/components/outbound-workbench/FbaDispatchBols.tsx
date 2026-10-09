import { useEffect, useState } from 'react';
import { Alert, Button, Table, Tabs, message } from 'antd';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { changeDispatchBols, getDispatchBols, UniBol } from '../../api/uniBol';

const mime = 'application/x-uni-fba-bols';
function Pane({ obId, pool }: {obId: number; pool: boolean}) {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const client = useQueryClient();
  const query = useQuery({queryKey: ['dispatch-bols', obId, pool, page], queryFn: () => getDispatchBols(obId, pool, page)});
  useEffect(() => {
    if (!query.data) return;
    const visible = new Set(query.data.data.map(b => b.id));
    setSelected(previous => previous.filter(id => visible.has(Number(id))));
    setPage(current => Math.min(current, Math.max(1, Math.ceil(query.data.total / 10))));
  }, [query.data]);
  const selection = (query.data?.data || []).filter(b => selected.includes(b.id)).map(({id, version}) => ({id, version}));
  async function update(action: 'join' | 'remove', bols: {id: number; version: number}[]) {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await changeDispatchBols(obId, action, bols);
      // Apply only confirmed server results; failed requests leave both lists intact.
      await client.cancelQueries({queryKey: ['dispatch-bols']});
      const changed = new Set<number>(result.data.map((b: UniBol) => b.id));
      for (const cached of client.getQueryCache().findAll({queryKey: ['dispatch-bols']})) {
        const [, targetId, candidate, currentPage] = cached.queryKey;
        if (!candidate && targetId !== obId) continue;
        client.setQueryData<{data: UniBol[]; total: number}>(cached.queryKey, previous => {
          if (!previous) return previous;
          const receiving = candidate ? action === 'remove' : action === 'join';
          const remaining = previous.data.filter(b => !changed.has(b.id));
          return {...previous,
            total: Math.max(0, previous.total + (receiving ? changed.size : -changed.size)),
            data: receiving && currentPage === 1
              ? [...remaining, ...result.data].sort((a, b) => b.id - a.id).slice(0, 10)
              : remaining,
          };
        });
      }
      setSelected([]);
      await client.invalidateQueries({queryKey: ['dispatch-bols']});
      await client.invalidateQueries({queryKey: ['uni-bols']});
      message.success(action === 'join' ? 'BOL 已加入 OB' : 'BOL 已移出 OB');
    } catch (e: any) { setError(String(e.response?.data?.detail || e.message)); }
    finally { setBusy(false); }
  }
  const queryError = query.error as {response?: {data?: {detail?: unknown}}; message?: string} | null;
  const queryDetail = queryError?.response?.data?.detail ?? queryError?.message ?? 'BOL 加载失败，请重试';
  const queryErrorMessage = typeof queryDetail === 'string' ? queryDetail : JSON.stringify(queryDetail);
  const columns = [
    {title: 'BOL #', dataIndex: 'bol_no', width: 120, render: (v: string, b: UniBol) => <Link to={`/outbound/bol/${b.id}`}>{v}</Link>},
    {title: 'Delivery Code', dataIndex: 'delivery_code', width: 100},
    {title: 'Transfer Code', width: 100, render: (_: unknown, b: UniBol) => b.details.transfer_code || ''},
    {title: 'Status', dataIndex: 'status', width: 110},
    {title: 'Pickup Location', dataIndex: 'pickup', width: 110},
    {title: 'Qty', dataIndex: 'cartons', width: 85},
    {title: 'WHS PLT', dataIndex: 'whs_pallets', width: 85},
    ...(!pool ? [{title: 'Action', width: 85, render: (_: unknown, b: UniBol) => <Button danger type="link" size="small" disabled={busy} onClick={() => update('remove', [{id: b.id, version: b.version}])}>Remove</Button>}] : []),
  ];
  return <section aria-label={pool ? 'FBA BOL pool' : 'OB BOL members'} style={{background: '#fff', padding: 12, minWidth: 0, width: '100%', boxSizing: 'border-box', borderLeft: pool ? undefined : '3px solid #1677ff'}}> 
    {pool && <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: 10}}><span>出库提单列表</span><span>{selection.length > 0 && <Button size="small" type="primary" draggable onDragStart={e => {e.dataTransfer.setData(mime, JSON.stringify(selection)); e.dataTransfer.effectAllowed = 'move';}}>Drag BOLs</Button>} <Button size="small" onClick={() => query.refetch()}>刷新</Button></span></div>}
    {!pool && <Tabs items={[{key: 'bol', label: 'OB BOL'}]} />}
    {(error || query.isError) && <Alert type="error" showIcon message={error || queryErrorMessage}
      action={query.isError ? <Button size="small" loading={query.isFetching} onClick={() => query.refetch()}>重试</Button> : undefined} />}
    <div onDragOver={e => {if (!pool && e.dataTransfer.types.includes(mime)) {e.preventDefault(); e.dataTransfer.dropEffect = 'move';}}} onDrop={e => {
      if (pool) return; e.preventDefault();
      try {const values = JSON.parse(e.dataTransfer.getData(mime));
        if (!Array.isArray(values) || !values.length || values.some(b => !Number.isInteger(b.id) || !Number.isInteger(b.version))) throw new Error('无效 BOL 选择');
        void update('join', values);
      } catch {setError('无效 BOL 选择');}
    }} style={{minHeight: 120}}>
      <Table<UniBol> size="small" rowKey="id" loading={query.isFetching || busy} columns={columns} dataSource={query.data?.data || []} scroll={{x: 800}}
        locale={query.isError ? {emptyText: '关联查询失败，请重试'} : undefined}
        rowSelection={pool ? {selectedRowKeys: selected, onChange: setSelected} : undefined}
        pagination={{current: page, pageSize: 10, total: query.data?.total || 0, showSizeChanger: false, onChange: p => {setPage(p); setSelected([]);}}} />
    </div>
  </section>;
}
export const FbaDispatchPool = ({obId}: {obId: number}) => <Pane key={obId} obId={obId} pool />;
export const FbaDispatchMembers = ({obId}: {obId: number}) => <Pane obId={obId} pool={false} />;

