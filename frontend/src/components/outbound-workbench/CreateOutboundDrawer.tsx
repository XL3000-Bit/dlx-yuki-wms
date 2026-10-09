import { Splitter, Button, Drawer, Form, Input, InputNumber, Select, Table, message } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { createOutboundFromCargo, type CargoBol } from '../../api/cargoBols'
import { getCarriers } from '../../api/masterData'
import './create-outbound.css'
import CreateOutboundBolPicker from './CreateOutboundBolPicker'

type Row = Record<string, any>
const options = (values: string[]) => values.map(value => ({ value, label: value }))
export default function CreateOutboundDrawer({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void; initialRows?: Row[] }) {
  const [form] = Form.useForm()
  const [related, setRelated] = useState<CargoBol[]>([])
  const dragged = useRef<CargoBol | null>(null)
  const warehouse = related[0]?.warehouse_id
  const customer = related[0]?.customer_id
  const carriers = useQuery({ queryKey: ['carriers'], queryFn: getCarriers, enabled: open })
  useEffect(() => {
    if (open) {
      form.resetFields()
      setRelated([]); dragged.current = null
    }
  }, [open])
  const fba = related.find(row => row.source_type === 'FBA')
  const save = useMutation({
    mutationFn: (values: Row) => createOutboundFromCargo({
      ...values, warehouse_id: warehouse, customer_id: customer, ob_type: fba ? 'FBA' : values.ob_type, fba_shipment_id: fba?.fba_shipment_id,
      schedule_pickup_at: values.schedule_pickup_at || null, delivery_appointment_time: values.delivery_appointment_time || null,
    }, related.map(row => row.id)),
    onSuccess: result => { message.success(`已创建 ${result.ob_no} 并配入 ${result.bol_count} 条 BOL 的余量`); onDone() },
    onError: (error: any) => message.error(typeof error.response?.data?.detail === 'string' ? error.response.data.detail : '创建失败，请核对字段及库存后重试'),
  })
  const compatible = (row: CargoBol) => row.can_allocate && !!row.customer_id
    && (!related.length || (row.warehouse_id === warehouse && row.customer_id === customer && related[0].source_type === row.source_type && (row.source_type !== 'FBA' || related[0].fba_shipment_id === row.fba_shipment_id)))
  const add = (row: CargoBol) => {
    if (!compatible(row)) { message.warning('请选择同一仓库、客户的入库货物，或同一个 FBA 货件。'); return }
    if (related.length >= 100) { message.warning('每次最多选择 100 条 BOL'); return }
    setRelated(current => current.some(item => item.id === row.id) ? current : [...current, row])
    if (row.source_type === 'FBA') form.setFieldValue('ob_type', 'FBA')
  }
  const remove = (row: CargoBol) => {
    setRelated(current => current.filter(item => item.id !== row.id))
    if (related.length === 1 && row.source_type === 'FBA') form.setFieldValue('ob_type', 'TBD')
  }
  const columns = [
    ['OB BOL#', 'bol_no'], ['PO#', 'po_number'], ['Source#', 'source_no'], ['Type', 'source_type'],
    ['Pickup Location', 'warehouse_name'], ['Del Code', 'del_code'], ['CNTR#', 'container_number'],
    ['Remaining PLT', 'available_pallet_qty'], ['Remaining CTN', 'available_carton_qty'],
    ['Weight LB', 'available_weight_lbs'], ['CBM', 'available_cbm'],
  ].map(([title, dataIndex]) => ({ title, dataIndex, width: 130, ellipsis: true, render: (value: unknown) => value == null || value === '' ? '—' : String(value) }))
  return <Drawer width="96vw" title="Home > Outbound > Dispatch" open={open} onClose={save.isPending ? undefined : onClose} className="create-outbound-drawer" styles={{ body: { background: '#f3f4f8', padding: 0, overflow: 'hidden' } }}>
    <Form className="create-ob-layout" form={form} layout="vertical" initialValues={{ ob_type: 'TBD', delivery_type: 'TBD', truck_type: 'TBD' }} onFinish={values => {
      if (!related.length) { message.warning('请至少选择一条可配货 BOL。'); return }
      save.mutate(values)
    }} disabled={save.isPending}>
      <Splitter><Splitter.Panel defaultSize="50%" min="15%">
      <section className="create-ob-editor" aria-label="Create Outbound">
      <div className="create-ob-editor-content">
      <h3 className="create-ob-title">Create Outbound</h3>
      <div className="create-ob-top">
        <Form.Item label="OB#"><Input disabled placeholder="Generate automatically" /></Form.Item>
        <Form.Item name="ob_type" label="OB Type"><Select disabled={!!fba || save.isPending} options={options(fba ? ['FBA'] : ['TBD', 'Direct', 'Consol', 'Redirect'])} /></Form.Item>
        <Form.Item name="delivery_type" label="Delivery Type"><Select options={options(['TBD', 'FBA', 'FBM', 'UPS', 'FedEx', 'Order Fulfillment', 'Self Pickup', 'USPS', 'MIX', 'DHL', 'Walmart'])} /></Form.Item>
        <Form.Item name="truck_type" label="Truck Type"><Select options={options(['TBD', "53' FTL", 'LTL', "26' FTL", 'Floor loaded', "30' FTL"])} /></Form.Item>
      </div>
      <div className="create-ob-body">
        <div>
          <Form.Item name="carrier_id" label="Carrier"><Select placeholder="TBD" allowClear showSearch optionFilterProp="label" options={carriers.data?.map(c => ({ value: c.id, label: c.carrier_name }))} /></Form.Item>
          <Form.Item name="pickup_location" label="Pickup Location"><Input placeholder="TBD" /></Form.Item>
          <Form.Item name="booked_pallet_qty" label="Booked PLT"><InputNumber placeholder="TBD" min={0} precision={2} /></Form.Item>
        </div>
        <div>
          <Form.Item name="schedule_pickup_at" label="Schedule Pickup Time"><Input type="datetime-local" /></Form.Item>
          <Form.Item name="delivery_appointment_time" label="Delivery Apt Time"><Input type="datetime-local" /></Form.Item>
          <Form.Item name="appointment_reference" label="ISA/DEL APT#" rules={[{ max: 100 }]}><Input placeholder="TBD" maxLength={100} /></Form.Item>
          <Form.Item name="reference_no" label="DEL REF#"><Input placeholder="TBD" /></Form.Item>
        </div>
      </div>
      <div className="create-ob-related-title">Related OB BOL List* <span>已选 {related.length} 条</span></div>
      <div className="create-ob-drop" onDragOver={event => event.preventDefault()} onDrop={event => {
        event.preventDefault(); if (save.isPending) return
        const id = Number(event.dataTransfer.getData('application/yuki-cargo-bol-id'))
        const row = dragged.current; if (row?.id === id) add(row); dragged.current = null
      }}>从右侧拖入 BOL，或勾选添加</div>
      <Table<CargoBol> size="small" rowKey="id" dataSource={related} locale={{ emptyText: '从右侧列表选择 BOL。' }} pagination={false} scroll={{ x: 1600 }} columns={[...columns, { title: 'Action', width: 90, fixed: 'right', render: (_, row) => <Button type="link" disabled={save.isPending} onClick={() => remove(row)}>Remove</Button> }]} />
      </div>
      <div className="create-ob-footer"><Button disabled={save.isPending} onClick={onClose}>Cancel</Button><Button htmlType="submit" type="primary" disabled={!warehouse || !customer || !related.length} loading={save.isPending}>Create</Button></div>
      </section>
      </Splitter.Panel><Splitter.Panel min="15%">
        {open && <CreateOutboundBolPicker related={related} compatible={compatible} add={add} remove={remove} onDrag={row => { dragged.current = row }} disabled={save.isPending} />}
      </Splitter.Panel></Splitter>
    </Form>
  </Drawer>
}
