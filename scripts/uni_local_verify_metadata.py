"""In Transit / Delivered detail saves; only the local UNI API, synthetic data."""
import json
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8017/api/v1'
config = json.loads((ROOT / '.uni-local/credentials.json').read_text(encoding='utf-8-sig'))
token = ''
checks = []


def request(method, path, data=None, expected=200):
    headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
    body = json.dumps(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + path, data=body, headers=headers, method=method), timeout=30) as response:
            code, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        code, body = error.code, error.read()
    assert code == expected, f'{method} {path}: expected {expected}, got {code}: {body[:500]!r}'
    return json.loads(body) if body else None


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS:', name, flush=True)


token = request('POST', '/auth/login', {k: config[k] for k in ('username', 'password')})['access_token']
masters = {name: request('GET', '/master-data/' + name)[0]['id'] for name in ('warehouses', 'customers', 'carriers', 'warehouse-locations')}
prefix = 'LOCAL-META-' + datetime.now().strftime('%m%d%H%M%S')
inbound = request('POST', '/inbound', {'warehouse_id': masters['warehouses'], 'customer_id': masters['customers'],
    'container_number': prefix, 'unload_date': '2026-09-17', 'fc_code': 'TEST9', 'marking': 'SYNTHETIC-METADATA',
    'pallet_qty': 4, 'carton_qty': 100, 'weight_lbs': 1000, 'cbm': 8, 'status': 0}, 201)
ipath = f"/ocean-inbound/{inbound['id']}"
line = {'id': inbound['id'], 'version': 0, 'received_qty': 100, 'inbound_pallets': 4,
    'location_id': masters['warehouse-locations'], 'memo': '', 'load_type': 'FBA'}
request('PUT', ipath + '/draft', {'lines': [line]})
request('POST', ipath + '/confirm', {'lines': [{**line, 'version': 1}]})
lot = request('POST', ipath + '/putaway', {'lines': [{'id': inbound['id'], 'version': 2}]})['data'][0]['inbound']['inventory_lot_id']
b = request('POST', '/uni-bols', {'warehouse_id': masters['warehouses'], 'customer_id': masters['customers'],
    'delivery_code': 'TEST9', 'details': {'carrier_id': masters['carriers'], 'shipping_mode': 'LTL', 'customer_reference': prefix}}, 201)
path = f"/uni-bols/{b['id']}"
b = request('PUT', path, {'version': b['version'], 'details': {**b['details'], 'seal_number': 'PRE-SEAL'}})
check('Pre metadata save persists', request('GET', path)['details']['seal_number'] == 'PRE-SEAL')
b = request('POST', path + '/loads', {'version': b['version'], 'inventory_lot_ids': [lot]})
b = request('POST', path + '/actions', {'version': b['version'], 'action': 'confirm'})
b = request('POST', path + '/actions', {'version': b['version'], 'action': 'shipout', 'confirm_all_picked': True})
stock = request('GET', f'/inventory/{lot}')
before = request('GET', path)
changes = {'seal_number': 'LOCAL-SEAL', 'pro_number': 'LOCAL-PRO', 'payment': 'COLLECT',
    'title_header': 'SYNTHETIC HEADER', 'title_body': 'Synthetic title', 'billing_to': 'Synthetic billing',
    'remark': 'Metadata acceptance', 'customer_remark': 'Synthetic customer remark',
    'internal_remark': 'Synthetic internal remark', 'urgent_level': 'Yes'}
payload = {'version': b['version'], 'details': {**b['details'], **changes}}
request('PUT', path, payload)
after = request('GET', path)
check('In Transit editable fields persist on fresh GET', all(after['details'][k] == v for k, v in changes.items()))
check('Metadata save preserves shipment status, loads and workflow', all(after[k] == before[k] for k in ('status', 'loads', 'workflow')))
check('Metadata save preserves inventory and reservation', request('GET', f'/inventory/{lot}') == stock)
request('PUT', path, payload, 409)
check('Repeated stale save has no side effects', request('GET', path) == after and request('GET', f'/inventory/{lot}') == stock)
for key, value in [('shipping_mode', "53' FTL"), ('delivery_reference', 'FORBIDDEN'), ('carrier_id', None)]:
    request('PUT', path, {'version': after['version'], 'details': {**after['details'], key: value}}, 409)
    check('Reject read-only ' + key + ' atomically', request('GET', path) == after and request('GET', f'/inventory/{lot}') == stock)
request('PUT', path, {'version': after['version'], 'details': {**after['details'], 'payment': 'UNKNOWN'}}, 422)
check('Invalid payment rejected without changes', request('GET', path) == after)
after = request('PUT', path, {'version': after['version'], 'details': {**after['details'], 'payment': ''}})
check('Blank payment persists after reload', request('GET', path)['details']['payment'] == '')
check('Clearing payment preserves shipment, loads and inventory',
      all(after[k] == before[k] for k in ('status', 'loads', 'workflow')) and request('GET', f'/inventory/{lot}') == stock)
delivered = request('POST', path + '/actions', {'version': after['version'], 'action': 'deliver'})
check('Synthetic BOL reaches Delivered before metadata validation', delivered['status'] == 'Delivered')
check('Delivery timestamp is returned separately from editable details', bool(delivered['delivery_time']) and 'delivery_time' not in delivered['details'])
delivered_stock = request('GET', f'/inventory/{lot}')
delivered_changes = {**changes, 'seal_number': 'DELIVERED-SEAL', 'payment': '', 'remark': 'Delivered metadata acceptance'}
delivered_payload = {'version': delivered['version'], 'details': {**delivered['details'], **delivered_changes}}
saved = request('PUT', path, delivered_payload)
check('Delivered editable fields persist on fresh GET', all(request('GET', path)['details'][k] == v for k, v in delivered_changes.items()))
check('Delivered metadata advances version exactly once', saved['version'] == delivered['version'] + 1)
check('Delivered save preserves the server delivery timestamp', saved['delivery_time'] == delivered['delivery_time'])
check('Delivered metadata preserves shipment, loads, workflow and inventory',
      all(saved[k] == delivered[k] for k in ('status', 'loads', 'workflow')) and request('GET', f'/inventory/{lot}') == delivered_stock)
request('PUT', path, delivered_payload, 409)
check('Delivered repeated stale save has no side effects', request('GET', path) == saved and request('GET', f'/inventory/{lot}') == delivered_stock)
for key, value in [('shipping_mode', "53' FTL"), ('delivery_reference', 'FORBIDDEN'), ('carrier_id', None)]:
    request('PUT', path, {'version': saved['version'], 'details': {**saved['details'], key: value}}, 409)
    check('Delivered rejects read-only ' + key + ' atomically', request('GET', path) == saved and request('GET', f'/inventory/{lot}') == delivered_stock)
request('PUT', path, {'version': saved['version'], 'details': {**saved['details'], 'payment': 'UNKNOWN'}}, 422)
check('Delivered invalid payment rejected without changes', request('GET', path) == saved)
request('PUT', path, {'version': saved['version'], 'details': {**saved['details'], 'delivery_time': '2000-01-01T00:00:00Z'}}, 422)
check('Delivery timestamp cannot be overwritten by detail save', request('GET', path) == saved and request('GET', f'/inventory/{lot}') == delivered_stock)
report = {'checked_at': datetime.now().isoformat(), 'base': BASE, 'prefix': prefix, 'bol_id': b['id'],
    'lot_id': lot, 'checks': checks, 'synthetic_only': True}
(ROOT / '.uni-local/metadata-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'passed': len(checks), 'bol_id': b['id'], 'prefix': prefix}))
