const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('../node_modules/typescript');

const frontend = path.resolve(__dirname, '..');
const jsx = (type, props) => ({ type, props: props || {} });
const mocks = {
  antd: Object.fromEntries(['Alert', 'Button', 'Table'].map((name) => [name, name])),
  'react/jsx-runtime': { Fragment: 'Fragment', jsx, jsxs: jsx },
  '../DispatchIndicators': {
    DispatchPriorityTag: 'DispatchPriorityTag',
    OutboundDateCell: 'OutboundDateCell',
  },
};
const cache = new Map();
function resolveLocal(from, request) {
  const base = path.resolve(path.dirname(from), request);
  return ['.ts', '.tsx', '.js'].map((ext) => `${base}${ext}`).find(fs.existsSync);
}
function load(file) {
  if (cache.has(file)) return cache.get(file);
  const mod = { exports: {} };
  cache.set(file, mod.exports);
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const requireMock = (request) => {
    if (request in mocks) return mocks[request];
    if (request.startsWith('.')) return load(resolveLocal(file, request));
    throw new Error(`Unexpected dependency: ${request}`);
  };
  vm.runInThisContext(`(function(require,module,exports){${output}\n})`, { filename: file })(requireMock, mod, mod.exports);
  cache.set(file, mod.exports);
  return mod.exports;
}

const componentFile = path.join(frontend, 'src/components/outbound-workbench/RemainingSourceTable.tsx');
const utilsFile = path.join(frontend, 'src/utils/outboundAllocation.ts');
const { RemainingSourceTable } = load(componentFile);
const {
  classifyFbaAllocationSources,
  FBA_MAPPING_INVALID_MESSAGE,
  FBA_MAPPING_MISSING_MESSAGE,
  workbenchSourceAllocationData,
} = load(utilsFile);

const standardRow = (patch = {}) => ({
  id: 904,
  inventory_lot_id: 904,
  fba_allocation_id: null,
  source_type: 'INVENTORY',
  available_pallet_qty: '10.000',
  available_carton_qty: 20,
  available_weight_lbs: '1000.25',
  available_cbm: 5,
  ...patch,
});
const fbaRemaining = (patch = {}) => ({
  id: 701,
  inventory_lot_id: 903,
  fba_allocation_id: 701,
  source_type: 'FBA',
  remaining_pallet_qty: '4.000',
  remaining_carton_qty: 8,
  remaining_weight_lbs: '400.50',
  remaining_cbm: 2,
  ...patch,
});
const fbaAllocation = (patch = {}) => ({ id: 701, inventory_lot_id: 903, ...patch });

function find(tree, predicate) {
  if (!tree || typeof tree !== 'object') return undefined;
  if (Array.isArray(tree)) {
    for (const child of tree) {
      const match = find(child, predicate);
      if (match) return match;
    }
    return undefined;
  }
  return predicate(tree) ? tree : find(tree.props?.children, predicate);
}
function render(row, patch = {}) {
  const state = { selected: null, refreshed: 0, allocated: null };
  const tree = RemainingSourceTable({
    rows: row ? [row] : [],
    selectedIds: [],
    ready: true,
    loading: false,
    canAllocate: true,
    errorMessage: null,
    scrollY: 300,
    onSelectionChange: (ids) => { state.selected = ids; },
    onAllocate: (value) => { state.allocated = value; },
    onRefresh: () => { state.refreshed += 1; },
    ...patch,
  });
  return { tree, table: find(tree, (node) => node.type === 'Table'), state };
}
function values(table, row) {
  const titles = ['Available PLT', 'Available CTN', 'Available LB', 'Available CBM'];
  return titles.map((title) => table.props.columns.find((col) => col.title === title).render(undefined, row));
}

for (const [kind, row, expected] of [
  ['STANDARD', standardRow(), ['10.000', '20', '1000.25', '5']],
  ['FBA', fbaRemaining(), ['4.000', '8', '400.50', '2']],
]) {
  test(`${kind} Remaining Source renders authoritative PLT, CTN, LB, and CBM`, () => {
    const { table } = render(row);
    assert.deepEqual(values(table, row), expected);
  });
}

test('true numeric and text zeros remain visible in every dimension', () => {
  const row = fbaRemaining({
    remaining_pallet_qty: 0,
    remaining_carton_qty: '0',
    remaining_weight_lbs: '0.000',
    remaining_cbm: 0,
  });
  assert.deepEqual(values(render(row).table, row), ['0', '0', '0.000', '0']);
});

for (const invalid of [undefined, null, '', 'NaN', NaN, Infinity, 'Infinity', -1]) {
  test(`unavailable/invalid quantity ${String(invalid)} is N/A and cannot be selected`, () => {
    const row = standardRow({ available_carton_qty: invalid });
    const { table, state } = render(row);
    assert.equal(values(table, row)[1], 'N/A');
    assert.equal(table.props.rowSelection.getCheckboxProps(row).disabled, true);
    table.props.rowSelection.onChange([row.id]);
    assert.deepEqual(state.selected, []);
    assert.doesNotMatch(JSON.stringify(values(table, row)), /NaN|Infinity/);
  });
}

test('mapping error is actionable and disables stale selection', () => {
  const row = fbaRemaining();
  const { tree, table, state } = render(row, {
    selectedIds: [row.id],
    ready: false,
    errorMessage: FBA_MAPPING_MISSING_MESSAGE,
  });
  const alert = find(tree, (node) => node.type === 'Alert');
  assert.match(alert.props.message, /mapping is missing.*open.*correct.*refresh/i);
  assert.equal(table.props.rowSelection.getCheckboxProps(row).disabled, true);
  alert.props.action.props.onClick();
  assert.equal(state.refreshed, 1);
});

test('empty FBA allocation list is missing mapping, while a fully exhausted mapped allocation is valid empty', () => {
  assert.equal(classifyFbaAllocationSources([], []).mappingError, FBA_MAPPING_MISSING_MESSAGE);
  assert.equal(classifyFbaAllocationSources([fbaAllocation()], []).mappingError, null);
});

test('invalid and duplicate FBA mappings are rejected', () => {
  const row = fbaRemaining({ inventory_lot_id: 904 });
  assert.equal(classifyFbaAllocationSources([fbaAllocation()], [row]).mappingError, FBA_MAPPING_INVALID_MESSAGE);
  const exact = fbaRemaining();
  assert.equal(classifyFbaAllocationSources([fbaAllocation()], [exact, { ...exact }]).mappingError, FBA_MAPPING_INVALID_MESSAGE);
});

test('FBA request preserves allocation ID and inventory lot ID despite an ID collision', () => {
  assert.deepEqual(workbenchSourceAllocationData(fbaRemaining()), {
    inventory_lot_id: 903,
    fba_allocation_id: 701,
    pallet_qty: '4.000',
    carton_qty: '8',
    weight_lbs: '400.50',
    cbm: '2',
  });
});

test('the routed workbench uses the tested Remaining Source component and strict request builder', () => {
  const page = fs.readFileSync(path.join(frontend, 'src/pages/OutboundDispatchWorkbenchPage.tsx'), 'utf8');
  const routes = fs.readFileSync(path.join(frontend, 'src/App.tsx'), 'utf8');
  assert.match(page, /<RemainingSourceTable/);
  assert.match(page, /workbenchSourceAllocationData\(row\)/);
  assert.match(page, /classifyFbaAllocationSources/);
  assert.match(routes, /OutboundDispatchWorkbenchPage/);
});
