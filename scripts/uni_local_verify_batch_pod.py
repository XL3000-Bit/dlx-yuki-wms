"""Batch POD acceptance against only the isolated UNI database and API.

Dispatch membership is an explicit synthetic fixture, not a claimed UNI UI flow.
"""
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8017/api/v1'
config = json.loads((ROOT / '.uni-local/credentials.json').read_text(encoding='utf-8-sig'))
os.environ['DATABASE_URL'] = 'postgresql+psycopg://uni_local:' + urllib.parse.quote(config['db_password'], safe='') + '@127.0.0.1:55437/uni_phase1'
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy.engine import make_url
from app.db.session import SessionLocal
from app.models.uni_bol import UniBol

url = make_url(os.environ['DATABASE_URL'])
assert (url.host, url.port, url.database) == ('127.0.0.1', 55437, 'uni_phase1')
token = ''
checks = []


def request(method, path, data=None, expected=200, multipart=None, raw=False, fields=None):
    headers = {'Authorization': 'Bearer ' + token}
    if multipart:
        selection, content = multipart
        boundary = 'UNI' + secrets.token_hex(16)
        form_fields = fields if fields is not None else {'selection': json.dumps(selection)}
        form_body = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n' for key, value in form_fields.items())
        data = (form_body +
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="synthetic.pdf"\r\nContent-Type: application/pdf\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        headers['Content-Type'] = 'multipart/form-data; boundary=' + boundary
    else:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode() if data is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=headers, method=method), timeout=30) as response:
            code, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        code, body = error.code, error.read()
    assert code == expected, f'{method} {path}: expected {expected}, got {code}: {body[:500]!r}'
    return body if raw else json.loads(body) if body else None


def check(name, result=True):
    assert result, name
    checks.append(name)
    print('PASS:', name, flush=True)


token = request('POST', '/auth/login', {k: config[k] for k in ('username', 'password')})['access_token']
masters = {name: request('GET', '/master-data/' + name)[0]['id'] for name in ('warehouses', 'customers', 'carriers', 'warehouse-locations')}
stamp = datetime.now().strftime('%m%d%H%M%S')
ob_number = 'OB-LOCAL-POD-' + stamp
records, lots = [], []
for suffix in ('A', 'B', 'C'):
    inbound = request('POST', '/inbound', {'warehouse_id': masters['warehouses'], 'customer_id': masters['customers'],
        'container_number': 'LOCAL-POD-' + stamp + suffix, 'unload_date': '2026-09-17', 'fc_code': 'TEST9',
        'marking': 'SYNTHETIC-' + suffix, 'pallet_qty': 4, 'carton_qty': 100, 'weight_lbs': 1000, 'cbm': 8, 'status': 0}, 201)
    path = f"/ocean-inbound/{inbound['id']}"
    line = {'id': inbound['id'], 'version': 0, 'received_qty': 100, 'inbound_pallets': 4,
        'location_id': masters['warehouse-locations'], 'memo': '', 'load_type': 'FBA'}
    request('PUT', path + '/draft', {'lines': [line]})
    request('POST', path + '/confirm', {'lines': [{**line, 'version': 1}]})
    lot = request('POST', path + '/putaway', {'lines': [{'id': inbound['id'], 'version': 2}]})['data'][0]['inbound']['inventory_lot_id']
    lots.append(lot)
    b = request('POST', '/uni-bols', {'warehouse_id': masters['warehouses'], 'customer_id': masters['customers'],
        'delivery_code': 'TEST9', 'details': {'carrier_id': masters['carriers'], 'shipping_mode': 'LTL', 'customer_reference': 'LOCAL-POD-' + stamp}}, 201)
    path = f"/uni-bols/{b['id']}"
    b = request('POST', path + '/loads', {'version': b['version'], 'inventory_lot_ids': [lot]})
    b = request('POST', path + '/actions', {'version': b['version'], 'action': 'confirm'})
    b = request('POST', path + '/actions', {'version': b['version'], 'action': 'shipout', 'confirm_all_picked': True})
    records.append(b)

# Group only freshly-created synthetic records; no customer or historical data touched.
with SessionLocal() as db:
    for b in records:
        record = db.get(UniBol, b['id'])
        assert record.details['customer_reference'] == 'LOCAL-POD-' + stamp
        record.dispatch_ob_no = ob_number
    db.commit()


def candidates(number=ob_number):
    return request('GET', '/uni-bols/pod-candidates?ob_no=' + urllib.parse.quote(number))


def selection(rows):
    return {'ob_no': ob_number, 'bols': [{'id': row['id'], 'version': row['version']} for row in rows],
        'delivery_date': '2026-09-17', 'delivery_appointment': 'SYNTHETIC-APT-' + stamp}


def snapshot():
    return {'rows': candidates(), 'stock': [request('GET', f'/inventory/{lot}') for lot in lots]}


rows = candidates()
check('OB lookup returns all three associated BOLs', len(rows) == 3 and {r['id'] for r in rows} == {r['id'] for r in records})
check('OB lookup is exact and case-insensitive', len(candidates(ob_number.lower())) == 3 and candidates(ob_number[:-1]) == [])
pdf = request('GET', f"/bols/{records[0]['documents'][0]['id']}/pdf", raw=True)
before = snapshot()
for name, payload, content, code in [
    ('Reject mismatched OB atomically', {**selection(rows), 'ob_no': ob_number + '-OTHER'}, pdf, 409),
    ('Reject stale BOL atomically', {**selection(rows), 'bols': [{'id': r['id'], 'version': r['version'] - (i == 1)} for i, r in enumerate(rows)]}, pdf, 409),
    ('Reject duplicate BOL selection atomically', selection([rows[0], rows[0]]), pdf, 422),
    ('Reject invalid file atomically', selection(rows), b'not a pdf', 415),
    ('Reject document above 3 MB atomically', selection(rows), b'%PDF-' + b'0' * (3 * 1024 * 1024), 413),
    ('Reject missing delivery date', {**selection(rows), 'delivery_date': ''}, pdf, 422),
]:
    request('POST', '/uni-bols/pod-batch', expected=code, multipart=(payload, content))
    check(name, snapshot() == before)

payload = selection(rows[:1])
saved = request('POST', '/uni-bols/pod-batch', multipart=(payload, pdf))
after = snapshot()
check('Subset upload updates only selected BOL', len(saved) == 1 and after['rows'][1:] == before['rows'][1:] and after['rows'][0]['pod_status'] == 'Awaiting Verify')
check('POD never changes shipment status or inventory', after['stock'] == before['stock'] and all(r['status'] == 'In Transit' for r in after['rows']))
metadata = after['rows'][0]['workflow']['pod_uploads'][-1]
check('Delivery metadata persists after reload', metadata['delivery_date'] == payload['delivery_date'] and metadata['delivery_appointment'] == payload['delivery_appointment'])
request('POST', '/uni-bols/pod-batch', expected=409, multipart=(payload, pdf))
check('Repeated stale submit has no side effects', snapshot() == after)
request('POST', '/uni-bols/pod-batch', expected=409, multipart=(selection(after['rows']), pdf))
check('Duplicate file in one BOL rejects entire batch', snapshot() == after)
request('POST', '/uni-bols/pod-batch', multipart=(selection(after['rows'][1:]), pdf))
final = snapshot()
check('Remaining BOLs accept same file in separate subset', all(r['pod_status'] == 'Awaiting Verify' for r in final['rows']) and final['stock'] == before['stock'])

detail_before = final
detail_row = detail_before['rows'][0]
detail_fields = {'version': detail_row['version'], 'delivery_date': '2026-09-16', 'delivery_appointment': 'DETAIL-' + stamp}
request('POST', f"/uni-bols/{detail_row['id']}/pod", multipart=({}, pdf + b'\n% detail POD\n'), fields=detail_fields)
detail_after = snapshot()
detail_metadata = detail_after['rows'][0]['workflow']['pod_uploads'][-1]
check('Detail POD saves delivery date and appointment after reload', detail_metadata['delivery_date'] == detail_fields['delivery_date'] and detail_metadata['delivery_appointment'] == detail_fields['delivery_appointment'])
check('Detail POD keeps shipment status and inventory unchanged', detail_after['stock'] == before['stock'] and detail_after['rows'][0]['status'] == detail_row['status'])
request('POST', f"/uni-bols/{detail_row['id']}/pod", expected=409, multipart=({}, pdf + b'\n% detail POD\n'), fields=detail_fields)
check('Detail POD repeat submit has no side effects', snapshot() == detail_after)

browser_file = ROOT / '.uni-local' / 'synthetic-batch-pod.pdf'
browser_file.write_bytes(pdf + b'\n% browser acceptance ' + stamp.encode() + b'\n')
report = {'checked_at': datetime.now().isoformat(), 'base': BASE, 'ob_number': ob_number, 'bol_ids': [r['id'] for r in rows],
    'lot_ids': lots, 'checks': checks, 'browser_file': str(browser_file), 'synthetic_only': True,
    'membership_fixture': 'direct isolated DB fixture; join/remove OB UI not verified'}
(ROOT / '.uni-local/batch-pod-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({'passed': len(checks), 'ob_number': ob_number, 'bol_ids': report['bol_ids']}))
