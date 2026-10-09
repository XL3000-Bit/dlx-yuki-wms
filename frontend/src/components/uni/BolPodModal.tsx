import { useState } from 'react';
import { Alert, Button, Input, Modal, Radio, Upload } from 'antd';
import { uploadBolPod } from '../../api/uniBol';
import type { UniBol } from '../../api/uniBol';

const dateOnly = (value?: string | number | null) => {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return '';
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};

export function BolPodModal({ row, onSave, onClose }: {
  row: UniBol; onSave: (fn: () => Promise<UniBol>) => Promise<boolean>; onClose: () => void;
}) {
  const latestPod = row.workflow.pod_uploads?.slice(-1)[0];
  const [deliveryDate, setDeliveryDate] = useState(() => latestPod?.delivery_date ?? dateOnly(row.details.delivery_appointment_time));
  const [appointment, setAppointment] = useState(latestPod?.delivery_appointment ?? String(row.details.pod_delivery_appointment || ''));
  const [file, setFile] = useState<File>();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const save = async () => {
    if (saving) return;
    if (!deliveryDate || !file) { setError(!deliveryDate ? 'Delivery Time is required.' : 'Select a POD document.'); return; }
    setSaving(true); setError('');
    try {
      if (await onSave(() => uploadBolPod(row.id, row.version, file, { delivery_date: deliveryDate, delivery_appointment: appointment }))) onClose();
    } finally { setSaving(false); }
  };
  return <Modal open title="POD" width={800} className="uni-bol-pod-modal" maskClosable={false} closable={!saving}
    onCancel={() => { if (!saving) onClose(); }} footer={<Button type="primary" loading={saving} onClick={save}>Save</Button>}>
    <h5>Delivery Time</h5>
    <Input aria-label="Delivery Time" type="date" value={deliveryDate} disabled={saving} onChange={event => setDeliveryDate(event.target.value)} />
    <h5>Delivery Apt#</h5>
    <Input aria-label="Delivery Apt#" maxLength={100} value={appointment} disabled={saving} onChange={event => setAppointment(event.target.value)} />
    <h5>POD Documents</h5>
    <Radio checked>Fast Upload</Radio>
    <Upload.Dragger accept=".pdf,.png,.jpg,.jpeg" multiple={false} showUploadList={false} disabled={saving} beforeUpload={next => {
      if (next.size > 3 * 1024 * 1024) { setError('Maximum upload document size: 3 MB.'); return Upload.LIST_IGNORE; }
      if (!/\.(pdf|png|jpe?g)$/i.test(next.name)) { setError('Select a PDF, PNG or JPEG document.'); return Upload.LIST_IGNORE; }
      setFile(next); setError(''); return false;
    }}>
      <p>Click here or drop a document to upload!</p>
      <span>Maximum upload document size: 3 MB.</span>
    </Upload.Dragger>
    <p className="uni-pod-document-name">{file?.name || 'No Documents.'}</p>
    {error && <Alert type="error" showIcon message={error} />}
  </Modal>;
}
