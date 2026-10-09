import { useEffect, useRef, useState } from 'react';
import { Alert, App, Button, Input, Modal, Table } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import { getPodCandidates, uploadBatchBolPod } from '../../api/uniBol';
import type { UniBol } from '../../api/uniBol';

const today = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
const errorText = (error: unknown) => {
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined;
  return typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(x => x.msg).join('; ') : error instanceof Error ? error.message : 'Upload failed';
};

// This is the list-level OB upload, distinct from the single-BOL detail upload.
export function PodUploadModal({ onClose }: { onClose: () => void }) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [obNumber, setObNumber] = useState('');
  const [rows, setRows] = useState<UniBol[]>([]);
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [deliveryDate, setDeliveryDate] = useState(today);
  const [appointment, setAppointment] = useState('');
  const [file, setFile] = useState<File>();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const lookup = useRef(0);
  useEffect(() => {
    const sequence = ++lookup.current;
    setRows([]); setSelected([]); setError('');
    if (!obNumber.trim()) { setLoading(false); return; }
    setLoading(true);
    const timer = window.setTimeout(() => {
      getPodCandidates(obNumber.trim()).then(result => {
        if (sequence !== lookup.current) return;
        setRows(result); setSelected(result.map(row => row.id));
      }).catch(e => { if (sequence === lookup.current) setError(errorText(e)); })
        .finally(() => { if (sequence === lookup.current) setLoading(false); });
    }, 350);
    return () => { window.clearTimeout(timer); ++lookup.current; };
  }, [obNumber]);
  const save = async () => {
    if (saving || !file || !selected.length || !deliveryDate || loading) return;
    setSaving(true); setError('');
    try {
      await uploadBatchBolPod({ ob_no: obNumber.trim(), delivery_date: deliveryDate, delivery_appointment: appointment,
        bols: rows.filter(row => selected.includes(row.id)).map(({ id, version }) => ({ id, version })) }, file);
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['uni-bols'] }), queryClient.invalidateQueries({ queryKey: ['uni-bol'] })]);
      message.success('POD uploaded successfully'); onClose();
    } catch (e) { setError(errorText(e)); }
    finally { setSaving(false); }
  };
  return <Modal open title="Upload POD" width={800} className="uni-ob-pod-modal" onCancel={() => { if (!saving) onClose(); }}
    maskClosable={false} closable={!saving} footer={<><Button disabled={saving} onClick={onClose}>Cancel</Button><Button type="primary" loading={saving} disabled={loading || !selected.length || !file || !deliveryDate} onClick={save}>Save</Button></>}>
    <label className="uni-pod-field">OB Number<Input autoFocus aria-label="OB Number" placeholder="OB12345" disabled={saving} value={obNumber} onChange={event => setObNumber(event.target.value)} /></label>
    <p className="uni-pod-selected">Selected BOLs: {selected.length} / {rows.length}</p>
    <div className="uni-pod-delivery-fields">
      <label className="uni-pod-field">Delivery Date<Input aria-label="Delivery Date" type="date" required disabled={saving} value={deliveryDate} onChange={event => setDeliveryDate(event.target.value)} /></label>
      <label className="uni-pod-field">Delivery Apt#<Input aria-label="Delivery Apt#" placeholder="APT-1001" disabled={saving} value={appointment} maxLength={100} onChange={event => setAppointment(event.target.value)} /></label>
    </div>
    <label className="uni-pod-file"><input aria-label="POD file" type="file" accept=".pdf,.png,.jpg,.jpeg" disabled={saving} onChange={event => {
      const next = event.target.files?.[0];
      if (next && next.size > 3 * 1024 * 1024) { setFile(undefined); setError('Maximum upload document size: 3 MB.'); event.target.value = ''; return; }
      setFile(next); setError('');
    }} /></label>
    {error && <Alert type="error" showIcon message={error} />}
    <Table<UniBol> rowKey="id" size="small" dataSource={rows} loading={loading} pagination={false} locale={{ emptyText: 'No BOLs found' }}
      rowSelection={{ selectedRowKeys: selected, onChange: setSelected, getCheckboxProps: () => ({ disabled: saving }) }}
      columns={[{ title: 'BOL ID', dataIndex: 'bol_no' }, { title: 'Status', dataIndex: 'status' }, { title: 'POD Status', dataIndex: 'pod_status' }, { title: 'Delivery Ref#', render: (_, row) => row.details.delivery_reference || '' }]} />
  </Modal>;
}
