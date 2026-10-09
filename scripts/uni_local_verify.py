"""Repeatable API acceptance checks against the isolated local UNI instance only."""
import json
import secrets
from datetime import datetime
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8017/api/v1'
config = json.loads((ROOT / '.uni-local/credentials.json').read_text(encoding='utf-8-sig'))
token = ''
checks = []

def call(method, path, data=None, expected=200, auth=None):
    headers = {'Content-Type': 'application/json'}
    if auth or token:
        headers['Authorization'] = 'Bearer ' + (auth or token)
    request = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(request, timeout=30)
        code, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        code, body = error.code, error.read()
    assert code == expected, f'{method} {path}: expected {expected}, got {code}: {body[:800]!r}'
    if '/pdf' in path or '/xlsx' in path:
        return body
    return json.loads(body) if body else None

def check(name, condition=True):
    assert condition, name
    checks.append(name)
    print('PASS:', name, flush=True)


def upload(path, fields, content, expected=200, auth=None):
    boundary = 'UNI' + secrets.token_hex(16)
    chunks = []
    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode(), content, f'\r\n--{boundary}--\r\n'.encode()])
    request = urllib.request.Request(BASE + path, data=b''.join(chunks), headers={
        'Content-Type': 'multipart/form-data; boundary=' + boundary,
        'Authorization': 'Bearer ' + (auth or token)}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            code, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        code, body = error.code, error.read()
    assert code == expected, f'Upload {path}: expected {expected}, got {code}: {body[:800]!r}'
    return json.loads(body)

token = call('POST', '/auth/login', {k: config[k] for k in ['username', 'password']})['access_token']
me = call('GET', '/users/me')
check('Logged-in user profile and permissions load', me['role'] == 'ADMIN')
masters = {name: call('GET', '/master-data/' + name) for name in ['warehouses', 'customers', 'carriers', 'warehouse-locations']}
wh, customer, carrier, location = [masters[name][0]['id'] for name in ['warehouses', 'customers', 'carriers', 'warehouse-locations']]
stamp = datetime.now().strftime('%m%d%H%M%S')
fc = 'TEST9'

def inbound(suffix):
    return call('POST', '/inbound', {'warehouse_id': wh, 'customer_id': customer,
        'container_number': 'LOCAL-' + stamp + suffix, 'unload_date': '2026-09-17', 'fc_code': fc,
        'marking': 'SYNTHETIC-' + suffix, 'pallet_qty': 4, 'carton_qty': 100,
        'weight_lbs': 1000, 'cbm': 8, 'status': 0}, 201)

def receive(record):
    path = f"/ocean-inbound/{record['id']}"
    line = {'id': record['id'], 'version': 0, 'received_qty': 100, 'inbound_pallets': 4,
            'location_id': location, 'memo': '', 'load_type': 'FBA'}
    call('POST', path + '/confirm', {'lines': [{**line, 'received_qty': 99}]}, 422)
    call('PUT', path + '/draft', {'lines': [line]})
    call('PUT', path + '/draft', {'lines': [line]}, 409)
    line['version'] = 1
    received = call('POST', path + '/confirm', {'lines': [line]})['data'][0]
    check('Confirmed receiving creates no inventory: ' + record['container_number'], received['inbound']['status'] == 2 and not received['inbound']['inventory_created'])
    call('POST', path + '/confirm', {'lines': [line]}, 409)
    payload = {'lines': [{'id': record['id'], 'version': 2}]}
    placed = call('POST', path + '/putaway', payload)['data'][0]
    call('POST', path + '/putaway', payload, 409)
    check('Put Away creates inventory exactly once', placed['inbound']['status'] == 3 and placed['inbound']['inventory_created'])
    return placed['inbound']['inventory_lot_id']

def bol():
    return call('POST', '/uni-bols', {'warehouse_id': wh, 'customer_id': customer,
        'delivery_code': fc, 'details': {'carrier_id': carrier, 'shipping_mode': 'LTL',
        'customer_reference': 'LOCAL-' + stamp, 'pickup_address': '100 Example Road',
        'delivery_address': '200 Test Road', 'remark': 'Synthetic acceptance test'}}, 201)

def action(b, action, **extra):
    return call('POST', f"/uni-bols/{b['id']}/actions", {'version': b['version'], 'action': action, **extra})

def stock(lot_id):
    return call('GET', f'/inventory/{lot_id}')

record = inbound('A')
lot_id = receive(record)
b = bol()
path = f"/uni-bols/{b['id']}"
check('Cargo BOL identity distinct from OB', b['bol_no'].startswith('BOL') and b['ob_no'] != b['bol_no'])
call('POST', path + '/actions', {'version': b['version'], 'action': 'confirm'}, 409)
details = b['details']
details['internal_remark'] = 'Persist and reload check'
b = call('PUT', path, {'version': b['version'], 'details': details})
call('PUT', path, {'version': 1, 'details': details}, 409)
check('Save persists and stale saves rejected', call('GET', path)['details']['internal_remark'] == 'Persist and reload check')
b = call('POST', path + '/loads', {'version': b['version'], 'inventory_lot_ids': [lot_id]})
s = stock(lot_id)
check('Select Loads reserves inventory once', float(s['available_carton_qty']) == 0 and float(s['allocated_carton_qty']) == 100)
call('POST', f"/outbounds/{b['outbound_order_id']}/cancel", {}, 409)
check('Legacy outbound cancellation cannot bypass OB BOL', call('GET', path)['status'] == 'Pre' and float(stock(lot_id)['allocated_carton_qty']) == 100)
b = action(b, 'confirm')
check('Confirm BOL creates shipping document', b['status'] == 'Confirmed' and len(b['documents']) == 1)
doc_id = b['documents'][0]['id']
check('PDF is readable', call('GET', f'/bols/{doc_id}/pdf').startswith(b'%PDF'))
check('Excel is readable', call('GET', f'/bols/{doc_id}/xlsx').startswith(b'PK'))
call('POST', path + '/actions', {'version': b['version'], 'action': 'shipout'}, 422)
before_version = b['version']
b = action(b, 'shipout', confirm_all_picked=True)
call('POST', path + '/actions', {'version': before_version, 'action': 'shipout', 'confirm_all_picked': True}, 409)
s = stock(lot_id)
check('Shipout consumes stock exactly once', b['status'] == 'In Transit' and float(s['available_carton_qty']) == 0 and float(s['allocated_carton_qty']) == 0 and float(b['loads'][0]['shipout_pallets']) == 4)
b = action(b, 'deliver')
check('Delivered persists on reload', call('GET', path)['status'] == 'Delivered')
check('List search and status filter', any(x['id'] == b['id'] for x in call('GET', '/uni-bols?status=Delivered&q=' + b['bol_no'])['data']))

cancel_record = inbound('B')
cancel_lot = receive(cancel_record)
c = bol()
c = call('POST', f"/uni-bols/{c['id']}/loads", {'version': c['version'], 'inventory_lot_ids': [cancel_lot]})
c = action(c, 'confirm')
c = action(c, 'cancel')
s = stock(cancel_lot)
check('Cancel releases confirmed reservation', c['status'] == 'Canceled' and float(s['available_carton_qty']) == 100 and float(s['allocated_carton_qty']) == 0)

partial_lot = receive(inbound('C'))
p = bol()
ppath = f"/uni-bols/{p['id']}"
p = call('POST', ppath + '/loads', {'version': p['version'], 'inventory_lot_ids': [partial_lot]})
p = action(p, 'confirm')
pdf = call('GET', f"/bols/{p['documents'][0]['id']}/pdf")
upload(ppath + '/pod', {'version': p['version']}, pdf, 409)
line = {'inventory_lot_id': partial_lot, 'pallet_qty': 1.25, 'carton_qty': 30, 'weight_lbs': 300, 'cbm': 2.4}
payload = {'version': p['version'], 'action': 'shipout', 'confirm_all_picked': True, 'lines': [line], 'request_id': 'partial-' + stamp}
call('POST', ppath + '/actions', {**payload, 'lines': [{**line, 'carton_qty': 101}]}, 409)
p = call('POST', ppath + '/actions', payload)
call('POST', ppath + '/actions', {**payload, 'version': p['version']}, 409)
check('Partial shipout preserves fractional pallets and rejects replay', float(p['remaining_qty']) == 70 and float(stock(partial_lot)['allocated_pallet_qty']) == 2.75)
call('POST', ppath + '/actions', {'version': p['version'], 'action': 'deliver'}, 409)
p = action(p, 'cancel', remark='Synthetic remaining cargo cancellation')
check('Cancel remaining cargo releases only unshipped stock', p['status'] == 'In Transit' and float(p['shipped_qty']) == 30 and float(stock(partial_lot)['available_carton_qty']) == 70 and float(stock(partial_lot)['allocated_carton_qty']) == 0)
p = action(p, 'deliver')
upload(ppath + '/pod', {'version': p['version']}, b'not a PDF', 415)
p = upload(ppath + '/pod', {'version': p['version']}, pdf)
pod_id = p['workflow']['pod_document_id']
upload(ppath + '/pod', {'version': p['version']}, pdf, 409)
review = {'version': p['version'], 'document_id': pod_id, 'result': 'Exception', 'remark': ''}
call('POST', ppath + '/pod/review', review, 422)
p = call('POST', ppath + '/pod/review', {**review, 'result': 'Verified'})
call('POST', ppath + '/pod/review', {**review, 'version': p['version'], 'result': 'Verified'}, 409)
check('POD content, duplicates, review conditions and reload verified', call('GET', ppath)['pod_status'] == 'Verified')
call('POST', f'/documents/{pod_id}/archive', {}, 409)
upload('/documents', {'document_type': 'POD', 'outbound_id': p['outbound_order_id']}, pdf, 409)
upload('/documents', {'document_type': 'POD', 'bol_id': p['documents'][0]['id']}, pdf, 409)
check('Generic document writes cannot bypass POD workflow', call('GET', f'/documents/{pod_id}')['status'] == 'AVAILABLE')

viewer_name, scoped_name = 'viewer_' + stamp, 'scoped_' + stamp
password = secrets.token_urlsafe(24)
for name, role, scope in [(viewer_name, 'VIEWER', 'ALL'), (scoped_name, 'OUTBOUND', 'SELECTED')]:
    call('POST', '/users', {'username': name, 'display_name': 'Synthetic Test User', 'email': name + '@example.com',
         'password': password, 'role': role, 'warehouse_scope_mode': scope, 'customer_scope_mode': scope,
         'warehouse_ids': [], 'customer_ids': []}, 201)
    auth = call('POST', '/auth/login', {'username': name, 'password': password})['access_token']
    if role == 'VIEWER':
        call('POST', '/uni-bols', {'warehouse_id': wh, 'customer_id': customer, 'delivery_code': fc}, 403, auth)
        call('POST', f"/ocean-inbound/{record['id']}/putaway", {'lines': [{'id': record['id'], 'version': 3}]}, 403, auth)
        check('Viewer cannot mutate outbound or inbound')
    else:
        call('GET', path, expected=404, auth=auth)
        call('GET', f"/ocean-inbound/{record['id']}", expected=404, auth=auth)
        check('Warehouse/customer scopes restrict both modules', call('GET', '/uni-bols', auth=auth)['total'] == 0)
        call('GET', f'/documents/{pod_id}', expected=404, auth=auth)
        call('GET', f'/documents/{pod_id}/download', expected=404, auth=auth)
        check('POD metadata and downloads respect customer/warehouse scopes')

report = {'checked_at': datetime.now().isoformat(), 'base_url': BASE, 'checks': checks,
          'inbound_id': record['id'], 'inventory_lot_id': lot_id, 'bol_id': b['id'], 'bol_no': b['bol_no'],
          'canceled_bol_id': c['id'], 'partial_bol_id': p['id'],
          'partial_inventory_lot_id': partial_lot, 'pod_document_id': pod_id, 'synthetic_data_only': True}
(ROOT / '.uni-local/verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'PASS: {len(checks)} acceptance checks; report .uni-local/verification.json')
