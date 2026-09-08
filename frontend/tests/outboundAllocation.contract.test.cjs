const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const ts = require('../node_modules/typescript');

// Execute the actual (currently unrouted) drawer without publishing a test route.
// React/Ant/HTTP boundaries are synthetic: these are component contract tests,
// not browser or database evidence. No quantity or request formula is copied here.
const frontend = path.resolve(__dirname, '..');
const ref = id => ({ id, code: `REF-${id}`, name: `Ref ${id}` });
const fbaRow = (patch = {}) => ({
  id: 701, inventory_lot_id: 903, lot_no: 'LOT-903', container_number: 'SYNTHETIC',
  fc_code: 'ONT8', location: ref(1), inbound_date: '2026-09-01', aging_days: 4,
  priority_level: 'GREEN', priority_label: 'New', allocated_pallet_qty: '10.000',
  allocated_carton_qty: '20', allocated_weight_lbs: '1000', allocated_cbm: '5',
  inventory_available_pallet_qty: '77', inventory_available_carton_qty: '88',
  inventory_available_weight_lbs: '99', inventory_available_cbm: '66',
  fc_mismatch: false, created_by: { id: 1, username: 'synthetic' },
  created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', ...patch,
});
const inventoryRow = (patch = {}) => ({
  id: 701, lot_no: 'COLLIDING-LOT-701', container_number: 'OTHER-INVENTORY',
  warehouse: ref(1), location: ref(1), fc_code: 'ONT8', marking: null, customer: ref(1),
  source_inbound_id: 1, inbound_date: '2026-09-01', aging_days: 4,
  priority_level: 'GREEN', priority_label: 'New', original_pallet_qty: '20',
  available_pallet_qty: '20', allocated_pallet_qty: '0', hold_pallet_qty: '0',
  original_carton_qty: '40', available_carton_qty: '40', allocated_carton_qty: '0',
  hold_carton_qty: '0', original_weight_lbs: '2000', available_weight_lbs: '2000',
  allocated_weight_lbs: '0', original_cbm: '10', available_cbm: '10', allocated_cbm: '0',
  status: 0, status_name: 'Available', remark: null,
  created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', ...patch,
});
const remainingRow = (patch = {}) => ({
  id: 701, inventory_lot_id: 903, fba_allocation_id: 701, source_type: 'FBA',
  lot_no: 'LOT-903', container_number: 'SYNTHETIC', fc_code: 'ONT8', location: 'A01',
  inbound_date: '2026-09-01', remaining_pallet_qty: '4.000', remaining_carton_qty: '8',
  remaining_weight_lbs: '400', remaining_cbm: '2', ...patch,
});
function harness() {
  const state = {
    ob: { id: 81, ob_no: 'TEST-OB', ob_type: 'FBA', warehouse: ref(1), fba_shipment: ref(51) },
    fba: [fbaRow()], inventory: [inventoryRow()],
    detail: { basic: { id: 81, ob_type: 'FBA', fba_id: 51 }, remaining_sources: [remainingRow()], allowed_actions: { allocate: true } },
    queryOverrides: {}, requests: [], errors: [], refetches: [], resets: 0, completeMutation: false,
  };
  const slots = []; let cursor = 0; let dirty = false; let effects = [];
  const form = { resetFields: () => { state.resets++; } };
  const react = {
    useState: initial => {
      const i = cursor++;
      if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial;
      return [slots[i], next => { const value = typeof next === 'function' ? next(slots[i]) : next; if (!Object.is(slots[i], value)) { slots[i] = value; dirty = true; } }];
    },
    useRef: initial => { const i = cursor++; return slots[i] ??= { current: initial }; },
    useEffect: (fn, deps) => {
      const i = cursor++;
      if (!slots[i] || deps.some((d, n) => !Object.is(d, slots[i][n]))) { effects.push(fn); slots[i] = deps; }
    },
  };
  const jsx = (type, props) => ({ type, props: props ?? {} });
  const Form = Object.assign(() => {}, { Item: 'Form.Item', useForm: () => [form] });
  const antd = Object.fromEntries(['Button', 'Drawer', 'Dropdown', 'InputNumber', 'Modal', 'Select', 'Space', 'Table', 'Tag'].map(n => [n, n]));
  Object.assign(antd, { Form, Input: { Search: 'Input.Search', TextArea: 'Input.TextArea' }, Typography: {}, message: { error: value => state.errors.push(value), success: () => {} } });
  const mocks = {
    react, 'react/jsx-runtime': { jsx, jsxs: jsx }, antd, '@ant-design/icons': {},
    '@tanstack/react-query': {
      useQuery: config => {
        const key = config.queryKey[0];
        const data = key === 'ob-inventory' ? { data: state.inventory } : key === 'ob-fba-source' ? state.fba : state.detail;
        return { data: config.enabled === false ? undefined : data, isLoading: false, isFetching: false, isError: false,
          refetch: async () => { state.refetches.push(key); }, ...state.queryOverrides[key] };
      },
      useMutation: config => ({ isPending: false, mutate: value => {
        const result = config.mutationFn(value);
        return state.completeMutation ? result.then(config.onSuccess) : result;
      } }),
    },
    '../api/outbound': { allocateOutbound: (id, payload) => { state.requests.push({ id, payload }); return Promise.resolve({}); } },
    '../api/fba': {}, '../api/inventory': {}, '../api/masterData': {}, '../components/ImportWizard': {},
  };
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file);
    const mod = { exports: {} }; cache.set(file, mod.exports);
    const input = fs.readFileSync(file, 'utf8') + (file.endsWith('OutboundDispatchPage.tsx') ? '\nexport { AllocationDrawer };\n' : '');
    const output = ts.transpileModule(input, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX } }).outputText;
    const requireMock = name => {
      if (name in mocks) return mocks[name];
      if (name.startsWith('.')) return load(path.resolve(path.dirname(file), `${name}.ts`));
      throw new Error(`Unexpected dependency: ${name}`);
    };
    vm.runInThisContext(`(function(require,module,exports){${output}\n})`, { filename: file })(requireMock, mod, mod.exports);
    return mod.exports;
  }
  const { AllocationDrawer } = load(path.join(frontend, 'src/pages/OutboundDispatchPage.tsx'));
  function render() {
    let tree;
    for (let i = 0; i < 8; i++) {
      cursor = 0; dirty = false; effects = [];
      tree = AllocationDrawer({ ob: state.ob, onClose: () => {}, onChanged: () => {} });
      effects.forEach(fn => fn());
      if (!dirty) return tree;
    }
    throw new Error('Unstable render');
  }
  function find(tree, predicate) {
    if (!tree || typeof tree !== 'object') return undefined;
    if (Array.isArray(tree)) { for (const item of tree) { const result = find(item, predicate); if (result) return result; } return undefined; }
    return predicate(tree) ? tree : find(tree.props?.children, predicate);
  }
  const table = tree => find(tree, n => n.type === 'Table');
  const allocationForm = tree => find(tree, n => n.type === Form);
  function select(index = 0) { const t = table(render()); t.props.rowSelection.onSelect(t.props.dataSource[index]); return render(); }
  function submit(tree = select(), values = { pallet_qty: '1', carton_qty: '0', weight_lbs: '0', cbm: '0' }) {
    const f = allocationForm(tree); if (f) f.props.onFinish(values);
  }
  function quantity(title, index = 0) {
    const t = table(render()); const col = t.props.columns.find(c => c.title === title); const row = t.props.dataSource[index];
    return String(col.render ? col.render(undefined, row) : row[col.dataIndex]);
  }
  return { state, render, table, allocationForm, select, submit, quantity, find, load };
}

test('actual drawer maps FBA 701 to lot 903, even when inventory lot 701 exists', () => {
  const h = harness();
  assert.equal(h.state.inventory[0].id, 701);
  h.submit();
  assert.equal(h.state.requests.length, 1);
  assert.equal(h.state.requests[0].payload.fba_allocation_id, 701);
  assert.equal(h.state.requests[0].payload.inventory_lot_id, 903);
});

test('actual drawer displays authoritative remaining without invented completed fields', () => {
  const h = harness();
  assert.equal('completed_pallet_qty' in h.state.fba[0], false);
  assert.equal(h.quantity('Remaining PLT'), '4.000');
});

const fields = ['pallet_qty', 'carton_qty', 'weight_lbs', 'cbm'];
function useInventory(h) { h.state.ob = { ...h.state.ob, ob_type: 'STANDARD', fba_shipment: null }; }
function submitButton(h, tree) { return h.find(tree, n => n.type === 'Button' && n.props.htmlType === 'submit'); }
function assertBlocked(h, tree, pattern) {
  assert.equal(submitButton(h, tree).props.disabled, true);
  h.submit(tree);
  assert.equal(h.state.requests.length, 0);
  assert.match(String(h.state.errors.at(-1)), pattern);
}

test('normal inventory submits its own lot ID with no FBA association', () => {
  const h = harness(); useInventory(h); h.submit();
  assert.equal(h.state.requests.length, 1);
  assert.equal(h.state.requests[0].payload.inventory_lot_id, 701);
  assert.equal(Object.hasOwn(h.state.requests[0].payload, 'fba_allocation_id'), false);
});

for (const [source, idField] of [['FBA', 'inventory_lot_id'], ['FBA', 'id'], ['INVENTORY', 'id']]) {
  for (const invalid of [undefined, null, 0, -1, 1.5, '903', NaN, Infinity]) {
    test(`${source} invalid ${idField}=${String(invalid)} blocks without guessing an ID`, () => {
      const h = harness();
      if (source === 'INVENTORY') { useInventory(h); h.state.inventory[0][idField] = invalid; }
      else h.state.fba[0][idField] = invalid;
      const tree = h.select();
      assert.match(h.find(tree, n => n.props.role === 'alert').props.children, /valid inventory lot or FBA allocation ID/);
      assertBlocked(h, tree, /valid inventory lot or FBA allocation ID/);
    });
  }
}

for (const [label, change] of [
  ['Outbound', h => { h.state.ob = { ...h.state.ob, id: 82 }; }],
  ['Shipment', h => { h.state.ob = { ...h.state.ob, fba_shipment: ref(52) }; }],
  ['warehouse', h => { h.state.ob = { ...h.state.ob, warehouse: ref(2) }; }],
  ['source type', useInventory],
  ['close', h => { h.state.ob = null; }],
]) {
  test(`${label} switch clears selection/form and blocks old callbacks`, () => {
    const h = harness(); const old = h.select(); const resets = h.state.resets;
    change(h); const current = h.render();
    assert.deepEqual(h.table(current).props.rowSelection.selectedRowKeys, []);
    assert.equal(h.allocationForm(current), undefined);
    assert.ok(h.state.resets > resets);
    h.submit(old);
    assert.equal(h.state.requests.length, 0);
    assert.match(h.state.errors.at(-1), /selection has changed/i);
  });
}

test('switching to another row cannot submit the first row callback', () => {
  const h = harness(); useInventory(h); h.state.inventory.push(inventoryRow({ id: 702 }));
  const old = h.select(0); h.select(1); h.submit(old);
  assert.equal(h.state.requests.length, 0);
  assert.match(h.state.errors.at(-1), /selection has changed/i);
});

for (const source of ['FBA', 'INVENTORY']) {
  test(`${source} true zero remains visible and prohibits positive pallet allocation`, () => {
    const h = harness();
    if (source === 'FBA') h.state.detail.remaining_sources[0].remaining_pallet_qty = '0';
    else { useInventory(h); h.state.inventory[0].available_pallet_qty = '0'; }
    assert.equal(h.quantity(source === 'FBA' ? 'Remaining PLT' : 'Available PLT'), '0');
    const tree = h.select(); h.submit(tree);
    assert.equal(h.state.requests.length, 0);
    assert.match(h.state.errors.at(-1), /exceeds/);
    // A genuine zero in one unit does not hide another unit's positive balance.
    h.submit(tree, { pallet_qty: '0', carton_qty: '1' });
    assert.equal(h.state.requests.length, 1);
    assert.equal(h.state.requests[0].payload.pallet_qty, '0');
  });
  for (const field of fields) {
    for (const invalid of [undefined, null, '', '   ', 'not-a-number', 'NaN', NaN, Infinity, 'Infinity', -1]) {
      test(`${source} ${field}=${String(invalid)} is unavailable, never a fabricated zero`, () => {
        const h = harness();
        if (source === 'FBA') h.state.detail.remaining_sources[0][`remaining_${field}`] = invalid;
        else { useInventory(h); h.state.inventory[0][`available_${field}`] = invalid; }
        const tree = h.select();
        const adapted = h.table(tree).props.dataSource[0];
        assert.equal(adapted.quantities[field], null);
        if (field === 'pallet_qty') assert.equal(h.quantity(source === 'FBA' ? 'Remaining PLT' : 'Available PLT'), 'N/A');
        assertBlocked(h, tree, /balance is unavailable/);
      });
    }
  }
  test(`${source} preserves decimal text and detects a one-unit fractional excess exactly`, () => {
    const h = harness(); const exact = '4.000000000000000001';
    if (source === 'FBA') h.state.detail.remaining_sources[0].remaining_pallet_qty = exact;
    else { useInventory(h); h.state.inventory[0].available_pallet_qty = exact; }
    assert.equal(h.quantity(source === 'FBA' ? 'Remaining PLT' : 'Available PLT'), exact);
    const tree = h.select();
    assert.equal(h.find(tree, n => n.type === 'InputNumber').props.stringMode, true);
    h.submit(tree, { pallet_qty: '4.000000000000000002' });
    assert.equal(h.state.requests.length, 0);
    h.submit(tree, { pallet_qty: exact });
    assert.equal(h.state.requests.length, 1);
    assert.deepEqual(h.state.requests[0].payload, {
      inventory_lot_id: source === 'FBA' ? 903 : 701,
      ...(source === 'FBA' ? { fba_allocation_id: 701 } : {}),
      pallet_qty: exact, carton_qty: '0', weight_lbs: '0', cbm: '0',
    });
  });
  test(`${source} refreshed balance controls display and even previously captured submission`, () => {
    const h = harness(); if (source === 'INVENTORY') useInventory(h);
    const old = h.select();
    if (source === 'FBA') h.state.detail.remaining_sources = [remainingRow({ remaining_pallet_qty: '0.2500' })];
    else h.state.inventory = [inventoryRow({ available_pallet_qty: '0.2500' })];
    assert.equal(h.quantity(source === 'FBA' ? 'Remaining PLT' : 'Available PLT'), '0.2500');
    h.submit(old, { pallet_qty: '1' }); assert.equal(h.state.requests.length, 0);
    h.submit(old, { pallet_qty: '0.2500' });
    assert.equal(h.state.requests.length, 1);
    assert.equal(h.state.requests[0].payload.pallet_qty, '0.2500');
  });
}

for (const query of ['ob-fba-source', 'ob-allocation-sources', 'ob-inventory']) {
  for (const flag of ['isLoading', 'isFetching', 'isError']) {
    test(`${query} ${flag} prevents use of cached balances`, () => {
      const h = harness(); if (query === 'ob-inventory') useInventory(h);
      h.state.queryOverrides[query] = { [flag]: true };
      assert.equal(h.quantity(query === 'ob-inventory' ? 'Available PLT' : 'Remaining PLT'), 'N/A');
      assertBlocked(h, h.select(), /refresh|unavailable/i);
    });
  }
}

for (const [label, change] of [
  ['other Outbound', h => { h.state.detail.basic.id = 82; }],
  ['other shipment', h => { h.state.detail.basic.fba_id = 52; }],
  ['other source type', h => { h.state.detail.basic.ob_type = 'STANDARD'; }],
  ['allocation denied', h => { h.state.detail.allowed_actions.allocate = false; }],
  ['missing source', h => { h.state.detail.remaining_sources = []; }],
  ['duplicate source', h => { h.state.detail.remaining_sources.push(remainingRow()); }],
  ['wrong source lot', h => { h.state.detail.remaining_sources[0].inventory_lot_id = 701; }],
  ['wrong source ID', h => { h.state.detail.remaining_sources[0].id = 702; }],
  ['wrong FBA ID', h => { h.state.detail.remaining_sources[0].fba_allocation_id = 702; }],
  ['wrong source kind', h => { h.state.detail.remaining_sources[0].source_type = 'INVENTORY'; }],
]) {
  test(`FBA ${label} never falls back to allocated or global available`, () => {
    const h = harness(); change(h);
    assert.equal(h.quantity('Remaining PLT'), 'N/A');
    assertBlocked(h, h.select(), /refresh|unavailable/i);
  });
}

for (const values of [{}, { pallet_qty: '0.000' }, { pallet_qty: null }, { pallet_qty: '' },
  { pallet_qty: 'NaN' }, { pallet_qty: Infinity }, { pallet_qty: '-1' }, { carton_qty: '9' }]) {
  test(`actual request builder rejects invalid/all-zero/over-limit input ${JSON.stringify(values)}`, () => {
    const h = harness(); h.submit(h.select(), values);
    assert.equal(h.state.requests.length, 0); assert.equal(h.state.errors.length, 1);
  });
}

test('successful FBA submission invalidates selection and refreshes raw sources plus authoritative balances', async () => {
  const h = harness(); h.state.completeMutation = true; h.submit();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(h.state.requests.length, 1);
  assert.deepEqual(h.state.refetches.sort(), ['ob-allocation-sources', 'ob-fba-source']);
  assert.equal(h.allocationForm(h.render()), undefined);
});
