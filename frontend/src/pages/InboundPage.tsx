import {
  DownloadOutlined,
  EditOutlined,
  FileExcelOutlined,
  PlusOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  cancelInbound,
  createInbound,
  downloadInbound,
  getInbound,
  getInbounds,
  receiveInbound,
  updateInbound,
} from '../api/inbound'
import { getCustomers, getLocations, getWarehouses } from '../api/masterData'
import { ImportWizard } from '../components/ImportWizard'
import { InboundFormDrawer } from '../components/InboundFormDrawer'
import type {
  InboundInput,
  InboundListParams,
  InboundRecord,
  InboundStatus,
} from '../types/inbound'

const statusLabels: Record<InboundStatus, string> = {
  0: 'Draft',
  1: 'Receiving',
  2: 'Received',
  3: 'Put Away',
  4: 'Completed',
  5: 'Hold',
  6: 'Canceled',
}

function errorMessage(error: unknown, fallback: string) {
  if (axios.isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
  }
  return fallback
}

function total(record: InboundRecord, field: 'pallet_qty' | 'carton_qty' | 'weight_lbs' | 'cbm') {
  if (record.lines?.length) {
    return record.lines.reduce((sum, line) => sum + Number(line[field] ?? 0), 0)
  }
  return Number(record[field] ?? 0)
}

function formatQuantity(value: number) {
  return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function statusColor(status: InboundStatus) {
  if (status === 2 || status === 3 || status === 4) return 'green'
  if (status === 5 || status === 6) return 'red'
  return 'orange'
}

export function InboundPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [params, setParams] = useState<InboundListParams>({
    page: 1,
    per_page: 20,
    sort_by: 'id',
    sort_order: 'desc',
  })
  const [form] = Form.useForm<InboundListParams>()
  const [drawer, setDrawer] = useState(false)
  const [editing, setEditing] = useState<InboundRecord | null>(null)
  const [importOpen, setImportOpen] = useState(false)

  const list = useQuery({ queryKey: ['inbound', params], queryFn: () => getInbounds(params) })
  const customers = useQuery({ queryKey: ['customers'], queryFn: getCustomers })
  const warehouses = useQuery({ queryKey: ['warehouses'], queryFn: getWarehouses })
  const locations = useQuery({ queryKey: ['locations'], queryFn: getLocations })

  const edit = useMutation({
    mutationFn: getInbound,
    onSuccess: (record) => {
      setEditing(record)
      setDrawer(true)
    },
    onError: (error) => message.error(errorMessage(error, 'Unable to load inbound details')),
  })

  const save = useMutation({
    mutationFn: (value: InboundInput) =>
      editing ? updateInbound(editing.id, value) : createInbound(value),
    onSuccess: () => {
      message.success(editing ? 'Inbound updated' : 'Inbound created')
      setDrawer(false)
      setEditing(null)
      queryClient.invalidateQueries({ queryKey: ['inbound'] })
    },
    onError: (error) => message.error(errorMessage(error, 'Unable to save inbound')),
  })

  const receive = useMutation({
    mutationFn: receiveInbound,
    onSuccess: (result) => {
      const count = result.inventory_lots.length
      message.success(`Inbound received; ${count} inventory lot${count === 1 ? '' : 's'} created`)
      queryClient.invalidateQueries({ queryKey: ['inbound'] })
      queryClient.invalidateQueries({ queryKey: ['inventory'] })
    },
    onError: (error) => message.error(errorMessage(error, 'Unable to receive inbound')),
  })

  const cancel = useMutation({
    mutationFn: cancelInbound,
    onSuccess: () => {
      message.success('Inbound canceled')
      queryClient.invalidateQueries({ queryKey: ['inbound'] })
    },
    onError: (error) => message.error(errorMessage(error, 'Unable to cancel inbound')),
  })

  const columns: ColumnsType<InboundRecord> = [
    { title: 'Inbound No', dataIndex: 'inbound_no', fixed: 'left', width: 130, sorter: true },
    { title: 'Container', dataIndex: 'container_number', width: 140 },
    { title: 'Customer', width: 130, render: (_, record) => record.customer?.name ?? '—' },
    { title: 'Warehouse', width: 105, render: (_, record) => record.warehouse.code },
    {
      title: 'Status',
      width: 105,
      render: (_, record) => (
        <Tag color={statusColor(record.status)}>{record.status_name || statusLabels[record.status]}</Tag>
      ),
    },
    { title: 'Received Date', dataIndex: 'received_date', width: 115, render: (value) => value ?? '—' },
    {
      title: 'Lines',
      width: 70,
      align: 'right',
      render: (_, record) => record.lines?.length ?? (record.fc_code ? 1 : 0),
    },
    {
      title: 'Pallets',
      width: 85,
      align: 'right',
      render: (_, record) => formatQuantity(total(record, 'pallet_qty')),
    },
    {
      title: 'Cartons',
      width: 85,
      align: 'right',
      render: (_, record) => formatQuantity(total(record, 'carton_qty')),
    },
    {
      title: 'Weight LBS',
      width: 105,
      align: 'right',
      render: (_, record) => formatQuantity(total(record, 'weight_lbs')),
    },
    {
      title: 'CBM',
      width: 80,
      align: 'right',
      render: (_, record) => formatQuantity(total(record, 'cbm')),
    },
    { title: 'Marking', dataIndex: 'marking', width: 100, render: (value) => value ?? '—' },
    { title: 'Remark', dataIndex: 'remark', width: 140, ellipsis: true },
    {
      title: 'Actions',
      fixed: 'right',
      width: 285,
      render: (_, record) => (
        <Space size={2} wrap>
          {record.status === 0 && (
            <Button
              type="text"
              icon={<EditOutlined />}
              loading={edit.isPending && edit.variables === record.id}
              onClick={() => edit.mutate(record.id)}
            >
              Edit
            </Button>
          )}
          {(record.status === 0 || record.status === 1) && (
            <Button
              type="link"
              loading={receive.isPending && receive.variables === record.id}
              onClick={() => receive.mutate(record.id)}
            >
              Receive
            </Button>
          )}
          {record.status === 0 && (
            <Button
              type="link"
              danger
              loading={cancel.isPending && cancel.variables === record.id}
              onClick={() =>
                Modal.confirm({
                  title: `Cancel ${record.inbound_no}?`,
                  content: 'The inbound will no longer be available for editing or receiving.',
                  okText: 'Cancel Inbound',
                  okButtonProps: { danger: true },
                  onOk: () => cancel.mutateAsync(record.id),
                })
              }
            >
              Cancel
            </Button>
          )}
          {(record.status === 2 || record.inventory_created) && (
            <Button
              type="link"
              onClick={() =>
                navigate(`/inventory?container_number=${encodeURIComponent(record.container_number)}`)
              }
            >
              View Inventory
            </Button>
          )}
        </Space>
      ),
    },
  ]

  function reset() {
    form.resetFields()
    setParams({ page: 1, per_page: 20, sort_by: 'id', sort_order: 'desc' })
  }

  function change(pagination: TablePaginationConfig, _filters: unknown, sorter: unknown) {
    const selection = sorter as { field?: string; order?: string }
    setParams((current) => ({
      ...current,
      page: pagination.current,
      per_page: pagination.pageSize,
      sort_by: selection.field ?? current.sort_by,
      sort_order:
        selection.order === 'ascend'
          ? 'asc'
          : selection.order === 'descend'
            ? 'desc'
            : current.sort_order,
    }))
  }

  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <Typography.Title level={4}>Inbound Management</Typography.Title>
          <Typography.Text type="secondary">
            Create multi-line receipts and receive them into inventory
          </Typography.Text>
        </div>
        <Space wrap>
          <Button icon={<ReloadOutlined />} loading={list.isFetching} onClick={() => list.refetch()}>
            Refresh
          </Button>
          <Button icon={<DownloadOutlined />} onClick={() => downloadInbound('template')}>
            Download Template
          </Button>
          <Button icon={<FileExcelOutlined />} onClick={() => downloadInbound('export', params)}>
            Export Excel
          </Button>
          <Button icon={<UploadOutlined />} onClick={() => setImportOpen(true)}>
            Import Excel
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditing(null)
              setDrawer(true)
            }}
          >
            Create Inbound
          </Button>
        </Space>
      </div>

      <Form
        form={form}
        layout="vertical"
        className="filter-form"
        onFinish={(values) => setParams({ ...params, ...values, page: 1 })}
      >
        <Form.Item name="q" label="Inbound No / Search">
          <Input />
        </Form.Item>
        <Form.Item name="container_number" label="Container Number">
          <Input />
        </Form.Item>
        <Form.Item name="customer_id" label="Customer">
          <Select
            allowClear
            options={(customers.data ?? []).map((customer) => ({
              value: customer.id,
              label: customer.customer_name,
            }))}
          />
        </Form.Item>
        <Form.Item name="warehouse_id" label="Warehouse">
          <Select
            allowClear
            options={(warehouses.data ?? []).map((warehouse) => ({
              value: warehouse.id,
              label: warehouse.warehouse_code,
            }))}
          />
        </Form.Item>
        <Form.Item name="fc_code" label="FC Code">
          <Input />
        </Form.Item>
        <Form.Item name="location_id" label="Location">
          <Select
            allowClear
            options={(locations.data ?? []).map((location) => ({
              value: location.id,
              label: location.location_code,
            }))}
          />
        </Form.Item>
        <Form.Item name="status" label="Status">
          <Select
            allowClear
            options={Object.entries(statusLabels).map(([value, label]) => ({
              value: Number(value),
              label,
            }))}
          />
        </Form.Item>
        <Form.Item name="unload_date_from" label="Unload Date">
          <Input type="date" />
        </Form.Item>
        <Form.Item name="received_date_from" label="Received Date">
          <Input type="date" />
        </Form.Item>
        <div className="filter-actions">
          <Button onClick={reset}>Reset</Button>
          <Button type="primary" htmlType="submit">
            Search
          </Button>
        </div>
      </Form>

      {list.isError && (
        <div className="error-state">
          {errorMessage(list.error, 'Unable to load inbound records.')}
        </div>
      )}
      <Table
        className="dense-table"
        rowKey="id"
        loading={list.isLoading}
        dataSource={list.data?.data ?? []}
        columns={columns}
        scroll={{ x: 1660, y: 'calc(100vh - 345px)' }}
        sticky
        pagination={{
          current: list.data?.meta.page,
          pageSize: list.data?.meta.per_page,
          total: list.data?.meta.total,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          showTotal: (count) => `${count} records`,
        }}
        onChange={change}
      />
      <InboundFormDrawer
        open={drawer}
        record={editing}
        customers={customers.data ?? []}
        warehouses={warehouses.data ?? []}
        locations={locations.data ?? []}
        loading={save.isPending}
        onClose={() => {
          setDrawer(false)
          setEditing(null)
        }}
        onSave={(value) => save.mutate(value)}
      />
      <ImportWizard
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onComplete={() => queryClient.invalidateQueries({ queryKey: ['inbound'] })}
      />
    </div>
  )
}
