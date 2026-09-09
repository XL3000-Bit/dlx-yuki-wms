const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const frontend = path.resolve(__dirname, '..')
const read = (relativePath) => fs.readFileSync(path.join(frontend, relativePath), 'utf8')

test('inbound API exposes detail, update, receive, and cancel contracts', () => {
  const source = read('src/api/inbound.ts')

  assert.match(source, /api\.get<InboundRecord>\(`\/inbound\/\$\{id\}`\)/)
  assert.match(source, /api\.patch<InboundRecord>\(`\/inbound\/\$\{id\}`, data\)/)
  assert.match(source, /api\.post<ReceiveInboundResponse>\(`\/inbound\/\$\{id\}\/receive`\)/)
  assert.match(source, /api\.post<InboundRecord>\(`\/inbound\/\$\{id\}\/cancel`\)/)
  assert.match(source, /inventory_lots: InventoryLot\[\]/)
})

test('inbound types preserve all seven numeric states and line fields', () => {
  const source = read('src/types/inbound.ts')

  assert.match(source, /InboundStatus = 0 \| 1 \| 2 \| 3 \| 4 \| 5 \| 6/)
  for (const field of [
    'line_no',
    'fc_code',
    'pallet_qty',
    'carton_qty',
    'weight_lbs',
    'cbm',
    'location_id',
    'note',
  ]) {
    assert.match(source, new RegExp(`\\b${field}[?:]`))
  }
  assert.match(source, /lines: InboundLine\[\]/)
  assert.match(source, /lines: InboundLineInput\[\]/)
  assert.match(source, /po_number: string \| null/)
  assert.match(source, /po_number\?: string/)
})

test('inbound UI provides two initial lines and required workflow actions', () => {
  const drawer = read('src/components/InboundFormDrawer.tsx')
  const page = read('src/pages/InboundPage.tsx')

  assert.match(drawer, /lines: \[emptyLine\(\), emptyLine\(\)\]/)
  assert.match(drawer, /<Form\.List name="lines">/)
  assert.match(drawer, /<Form\.Item name="po_number" label="PO Number">/)
  assert.match(page, /title: 'PO Number', dataIndex: 'po_number'/)
  assert.match(drawer, />\s*Add Line\s*</)
  assert.match(drawer, />\s*Save Draft\s*</)
  for (const action of ['Refresh', 'Receive', 'Cancel', 'View Inventory']) {
    assert.match(page, new RegExp(`>\\s*${action}\\s*<`))
  }
  assert.match(page, /const \[modal, modalContextHolder\] = Modal\.useModal\(\)/)
  assert.match(page, /modal\.confirm\(\{/)
  assert.match(page, /\{modalContextHolder\}/)
  assert.match(page, /navigate\(`\/inventory\?container_number=/)
})

test('inventory handoff consumes and displays the container URL filter', () => {
  const inventory = read('src/pages/InventoryPage.tsx')

  assert.match(inventory, /useSearchParams/)
  assert.match(inventory, /searchParams\.get\('container_number'\)/)
  assert.match(inventory, /container_number:initialContainerNumber/)
  assert.match(inventory, /initialValues=\{\{container_number:initialContainerNumber\}\}/)
})

test('picking list renders the business outbound number', () => {
  const page = read('src/pages/PickingPage.tsx')
  assert.match(page, /title:'OB No',render:\(_:any,r:any\)=>r\.ob_no/)
  assert.doesNotMatch(page, /title:'OB No',render:\(_:any,r:any\)=>r\.outbound_order_id/)
})
