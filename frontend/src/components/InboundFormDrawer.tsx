import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Card, Drawer, Form, Input, InputNumber, Select, Space, Typography } from 'antd'
import { useEffect } from 'react'
import type { InboundInput, InboundLineInput, InboundRecord } from '../types/inbound'
import type { Customer, Location, Warehouse } from '../types/masterData'

const emptyLine = (): InboundLineInput => ({
  line_no: 0,
  fc_code: '',
  pallet_qty: 0,
  carton_qty: 0,
})

function valuesForRecord(record: InboundRecord | null): Partial<InboundInput> {
  if (!record) {
    return {
      status: 0,
      lines: [emptyLine(), emptyLine()],
    }
  }

  const lines: InboundLineInput[] = record.lines.length
    ? record.lines.map((line) => ({
        line_no: line.line_no,
        fc_code: line.fc_code,
        pallet_qty: Number(line.pallet_qty),
        carton_qty: Number(line.carton_qty),
        weight_lbs: line.weight_lbs == null ? undefined : Number(line.weight_lbs),
        cbm: line.cbm == null ? undefined : Number(line.cbm),
        location_id: line.location_id ?? undefined,
        note: line.note ?? undefined,
      }))
    : [
        {
          line_no: 1,
          fc_code: record.fc_code ?? '',
          pallet_qty: Number(record.pallet_qty),
          carton_qty: Number(record.carton_qty),
          weight_lbs: record.weight_lbs == null ? undefined : Number(record.weight_lbs),
          cbm: record.cbm == null ? undefined : Number(record.cbm),
          location_id: record.location?.id,
        },
      ]

  return {
    container_number: record.container_number,
    customer_id: record.customer?.id,
    warehouse_id: record.warehouse.id,
    unload_date: record.unload_date ?? undefined,
    received_date: record.received_date ?? undefined,
    marking: record.marking ?? undefined,
    status: record.status,
    remark: record.remark ?? undefined,
    lines,
  }
}

export function InboundFormDrawer({
  open,
  record,
  customers,
  warehouses,
  locations,
  onClose,
  onSave,
  loading,
}: {
  open: boolean
  record: InboundRecord | null
  customers: Customer[]
  warehouses: Warehouse[]
  locations: Location[]
  onClose: () => void
  onSave: (value: InboundInput) => void
  loading: boolean
}) {
  const [form] = Form.useForm<InboundInput>()
  const warehouseId = Form.useWatch('warehouse_id', form)

  useEffect(() => {
    if (open) {
      form.resetFields()
      form.setFieldsValue(valuesForRecord(record))
    }
  }, [open, record, form])

  function submit(values: InboundInput) {
    const lines = values.lines.map((line, index) => ({ ...line, line_no: index + 1 }))
    const first = lines[0]
    onSave({
      ...values,
      lines,
      fc_code: first?.fc_code,
      location_id: first?.location_id,
      pallet_qty: lines.reduce((total, line) => total + line.pallet_qty, 0),
      carton_qty: lines.reduce((total, line) => total + line.carton_qty, 0),
      weight_lbs: lines.reduce((total, line) => total + (line.weight_lbs ?? 0), 0),
      cbm: lines.reduce((total, line) => total + (line.cbm ?? 0), 0),
    })
  }

  const availableLocations = locations.filter((location) => location.warehouse_id === warehouseId)

  return (
    <Drawer
      title={record ? `Edit ${record.inbound_no}` : 'Create Inbound'}
      width={980}
      open={open}
      onClose={onClose}
      extra={
        <Space>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="primary" loading={loading} onClick={() => form.submit()}>
            Save
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" onFinish={submit}>
        <div className="two-col-form">
          <Form.Item name="container_number" label="Container Number" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="customer_id" label="Customer">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={customers.map((customer) => ({
                value: customer.id,
                label: `${customer.customer_code} — ${customer.customer_name}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="warehouse_id" label="Warehouse" rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={warehouses.map((warehouse) => ({
                value: warehouse.id,
                label: `${warehouse.warehouse_code} — ${warehouse.warehouse_name}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="unload_date" label="Unload Date">
            <Input type="date" />
          </Form.Item>
          <Form.Item name="marking" label="Marking">
            <Input />
          </Form.Item>
          <Form.Item name="remark" label="Remark">
            <Input />
          </Form.Item>
        </div>

        <Typography.Title level={5}>Inbound Lines</Typography.Title>
        <Form.List name="lines">
          {(fields, { add, remove }) => (
            <Space direction="vertical" size="middle" style={{ display: 'flex' }}>
              {fields.map((field, index) => (
                <Card
                  key={field.key}
                  size="small"
                  title={`Line ${index + 1}`}
                  extra={
                    <Button
                      type="text"
                      danger
                      aria-label={`Remove line ${index + 1}`}
                      icon={<DeleteOutlined />}
                      disabled={fields.length === 1}
                      onClick={() => remove(field.name)}
                    />
                  }
                >
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                      gap: '0 12px',
                    }}
                  >
                    <Form.Item
                      name={[field.name, 'fc_code']}
                      label="FC Code"
                      rules={[{ required: true, whitespace: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'pallet_qty']}
                      label="Pallet Qty"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item
                      name={[field.name, 'carton_qty']}
                      label="Carton Qty"
                      rules={[{ required: true }]}
                    >
                      <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'weight_lbs']} label="Weight LBS">
                      <InputNumber min={0} precision={2} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'cbm']} label="CBM">
                      <InputNumber min={0} precision={4} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item name={[field.name, 'location_id']} label="Location">
                      <Select
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        options={availableLocations.map((location) => ({
                          value: location.id,
                          label: location.location_code,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name={[field.name, 'note']} label="Line Note">
                      <Input />
                    </Form.Item>
                  </div>
                </Card>
              ))}
              <Button block icon={<PlusOutlined />} onClick={() => add(emptyLine())}>
                Add Line
              </Button>
            </Space>
          )}
        </Form.List>
      </Form>
    </Drawer>
  )
}
