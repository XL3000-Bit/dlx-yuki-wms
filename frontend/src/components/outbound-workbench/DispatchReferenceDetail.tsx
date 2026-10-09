import { useState } from 'react';
import { Alert, Button, Dropdown, Table, Tabs } from 'antd';
import { DownOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { getOutboundWorkbenchDetail } from '../../api/outbound';
import { EntityDocuments } from '../EntityDocuments';

const quantities = ['pallet_qty', 'carton_qty', 'weight_lbs', 'cbm'];
// One cargo identity may span several inventory lots, especially for FBA.
function cargoRows(allocations: any[]) {
  const groups = new Map<string, any>();
  for (const allocation of allocations) {
    const key = allocation.cargo_bol_id ? String(allocation.cargo_bol_id) : 'allocation-' + allocation.id;
    const group = groups.get(key) || { id: key, cargo_bol_no: allocation.cargo_bol_no, references: {} };
    for (const field of ['po_number', 'container_number', 'fc_code', 'lot_no', 'location']) {
      group.references[field] ||= new Set<string>();
      if (allocation[field]) group.references[field].add(String(allocation[field]));
    }
    for (const quantity of quantities) {
      for (const prefix of ['allocated_', 'completed_']) {
        const field = prefix + quantity;
        group[field] = (group[field] || 0) + Number(allocation[field] || 0);
      }
    }
    groups.set(key, group);
  }
  return [...groups.values()].map(group => ({
    ...group, ...Object.fromEntries(Object.entries(group.references).map(([key, values]) => [key, [...(values as Set<string>)].join(', ')])),
    remaining_pallet_qty: group.allocated_pallet_qty - group.completed_pallet_qty,
  }));
}

export function DispatchReferenceDetail({ row, onDetails, onSchedule }: { row: any; onDetails: () => void; onSchedule: () => void }) {
  const [tab, setTab] = useState('bol');
  const detail = useQuery({ queryKey: ['outbound-workbench-detail', row.id], queryFn: () => getOutboundWorkbenchDetail(row.id) });
  const bols = cargoRows(detail.data?.allocations || []);
  const numeric = (v: unknown) => v == null ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const col = (title: string, key: string, width = 110, number = false): any => ({ title, dataIndex: key, width, ellipsis: true, render: (v: unknown) => number ? numeric(v) : v == null || v === '' ? '—' : String(v) });
  const numericFields = ['allocated_pallet_qty', 'allocated_carton_qty', 'allocated_weight_lbs', 'allocated_cbm', 'completed_pallet_qty', 'remaining_pallet_qty'];
  const columns: any[] = [
    { title: 'Cargo BOL#', dataIndex: 'cargo_bol_no', width: 180, render: (v: string) => <Button type="link" onClick={onDetails}>{v || '查看货物'}</Button> },
    col('PO#', 'po_number', 140), col('CNTR#', 'container_number', 140), col('Del Code', 'fc_code'),
    col('Lot#', 'lot_no', 180), col('WHS Area', 'location', 120),
    col('已配 PLT', 'allocated_pallet_qty', 105, true), col('已配 CTN', 'allocated_carton_qty', 105, true),
    col('已配 Weight LB', 'allocated_weight_lbs', 130, true), col('已配 CBM', 'allocated_cbm', 105, true),
    col('已出库 PLT', 'completed_pallet_qty', 110, true), col('待出库 PLT', 'remaining_pallet_qty', 110, true),
  ];
  const disabled = (key: string, label: string) => ({ key, label, disabled: true, title: '此功能尚未接入' });
  const items = [disabled('loaded', 'Cargo loaded'), disabled('amazon', 'Export Amazon Apt'), disabled('print', 'Print OB'),
    disabled('merge', 'Merge OB BOL'), disabled('redirect', 'Batch Update Redirect Location'),
    { key: 'schedule', label: 'Update Delivery Appointment Time', disabled: !row.allowed_actions?.exception },
    { key: 'pod', label: 'Upload / View POD' }, { key: 'details', label: 'OB Details / 操作详情' }];
  return <div className="reference-detail">
    <Tabs activeKey={tab} onChange={setTab} tabBarExtraContent={<Dropdown trigger={['click']} menu={{ items, onClick: ({ key }) => {
      if (key === 'details') onDetails();
      if (key === 'schedule') onSchedule();
      if (key === 'pod') setTab('documents');
    } }}><Button type="primary" size="small">Actions <DownOutlined /></Button></Dropdown>} items={[
      { key: 'bol', label: 'OB BOL', children: <>
        {detail.isError ? <Alert type="error" message="货物明细加载失败" action={<Button onClick={() => detail.refetch()}>重试</Button>} /> : null}
        <Table rowKey="id" size="small" tableLayout="fixed" loading={detail.isLoading} dataSource={bols} columns={columns} pagination={false} scroll={{ x: 1535 }}
          locale={{ emptyText: row.bol_no ? `历史 BOL 参考号：${row.bol_no}。尚无实际库存分配；可在 OB Details 查看导入记录。` : '此出库单暂无实际货物分配。' }}
          summary={() => bols.length ? <Table.Summary.Row>{columns.map((c, i) => <Table.Summary.Cell index={i} key={i}>
            {i === 0 ? 'Total' : numericFields.includes(c.dataIndex) ? numeric(bols.reduce((sum, b) => sum + Number(b[c.dataIndex] || 0), 0)) : ''}
          </Table.Summary.Cell>)}</Table.Summary.Row> : null} />
        <div className="reference-detail-note">待出库 = 本单已配 − 已出库；可配库存余量见 Remaining BOL List。 <Button type="link" onClick={onDetails}>OB Details / 查看货物与操作</Button></div>
      </> },
      { key: 'chat', label: 'Chat Room', children: <div className="reference-tab-empty">当前系统尚未接入聊天功能。</div> },
      { key: 'documents', label: 'Document', children: <EntityDocuments relation={{ outbound_id: row.id }} /> },
      { key: 'remark', label: 'Remark to customer', children: <div className="reference-tab-empty">{detail.data?.basic?.remark || row.remark || '暂无备注'}</div> },
    ]} />
  </div>;
}
