const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const target = { exports: {} }
const output = ts.transpileModule(fs.readFileSync(path.join(__dirname, 'src/components/outboundAllocationSource.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
new Function('module', 'exports', output)(target, target.exports)

test('FBA allocation uses its inventory lot identity separately from reservation identity', () => {
  assert.deepEqual(target.exports.allocationSourceIds({ kind: 'fba', row: { id: 101, inventory_lot_id: 202 } }),
    { inventory_lot_id: 202, fba_allocation_id: 101 })
})
test('private inventory allocation does not inherit an FBA reservation identity', () => {
  assert.deepEqual(target.exports.allocationSourceIds({ kind: 'inventory', row: { id: 303 } }),
    { inventory_lot_id: 303 })
})
