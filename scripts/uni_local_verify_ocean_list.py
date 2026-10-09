"""Ocean list acceptance against the isolated local API, using synthetic data only."""
import json
import urllib.error
import urllib.parse
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
masters = {name: request('GET', '/master-data/' + name)[0]['id'] for name in ('warehouses', 'customers')}
prefix = 'LOCAL-OCEAN-' + datetime.now().strftime('%m%d%H%M%S')


def create(suffix, cartons=100):
    return request('POST', '/inbound', {'warehouse_id': masters['warehouses'], 'customer_id': masters['customers'],
        'container_number': prefix + suffix, 'unload_date': '2026-09-17', 'fc_code': 'TEST9',
        'marking': 'SYNTHETIC-LIST', 'pallet_qty': 4, 'carton_qty': cartons, 'weight_lbs': 1000, 'cbm': 8, 'status': 0}, 201)


def listed(**params):
    return request('GET', '/ocean-inbound?' + urllib.parse.urlencode({'q': prefix, **params}))


def receiving_state(shipment):
    return [{**line, 'inbound': {key: value for key, value in line['inbound'].items()
        if key not in ('source_metadata', 'updated_at')}} for line in shipment['data']]


a = create('-A')
second = create('-A', 25)
b = create('-B')
c = create('-C')
path = f"/ocean-inbound/{a['id']}"
before = request('GET', path)
fields = {'version': 0, 'transport_status': '待提待拆', 'list_status': 'Upcoming Inbound',
    'scheduled_delivery_date': '2026-09-18T23:45:00', 'pod_eta': '2026-09-19', 'appointment': '2026-09-20 23:59',
    'size': '40HQ', 'trucker': 'SYNTHETIC TRUCKER', 'team': 'SYNTHETIC TEAM', 'released': True,
    'outbound_fully_pod': True, 'unloading_amount': '120.50', 'unloading_remark': 'Synthetic original remark'}
request('PUT', path + '/shipment', fields)
request('PUT', path + '/shipment', {'version': 1, 'printed': True})
after = request('GET', path)
check('Inline partial save preserves unrelated shipment fields', all(after['shipment'][key] == value for key, value in fields.items() if key != 'version'))
check('Fresh GET persists edited field and increments shipment version', after['shipment']['printed'] is True and after['shipment']['version'] == 2)
other = request('GET', f"/ocean-inbound/{second['id']}")
check('Grouped cargo lines share the same shipment metadata', other['shipment'] == after['shipment'] and len(other['data']) == 2)
check('Shipment edits leave receipt, business state and inventory unchanged', receiving_state(after) == receiving_state(before))
request('PUT', path + '/shipment', {'version': 1, 'printed': False}, 409)
check('Repeated stale save is rejected without overwrite', request('GET', path)['shipment'] == after['shipment'])
request('PUT', path + '/shipment', {'version': 2, 'unloading_remark': 'x' * 1025}, 422)
check('Oversize remark is rejected without changing version', request('GET', path)['shipment']['version'] == 2)
request('PUT', path + '/shipment', {'version': 2, 'unloading_remark': 'x' * 1024})
request('PUT', path + '/shipment', {'version': 3, 'unloading_remark': 'Synthetic inline remark', 'empty_reported': True})
check('1024 character remark accepted and subsequent partial save persists', request('GET', path)['shipment']['empty_reported'] is True)
request('PUT', f"/ocean-inbound/{b['id']}/shipment", {'version': 0, 'list_status': 'Completed Inbound', 'transport_status': '已提已拆', 'size': '20GP'})

result = listed()
check('List groups cargo lines into one container visit', result['total'] == 3 and next(row for row in result['data'] if row['id'] == a['id'])['pieces'] == 125)
check('Counts retain unclassified shipments without inferring a stock state', result['counts'] == {'Upcoming Inbound': 1, 'Completed Inbound': 1, 'Total': 3, 'Unclassified': 1})
check('Options come from local shipment fields', result['options'] == {'size': ['20GP', '40HQ'], 'trucker': ['SYNTHETIC TRUCKER'], 'team': ['SYNTHETIC TEAM']})
for field in ('printed', 'empty_reported', 'released', 'outbound_fully_pod'):
    yes = listed(**{field: 'true'})
    no = listed(**{field: 'false'})
    check(field + ' Yes/No filter includes absent metadata as No', [row['id'] for row in yes['data']] == [a['id']] and {row['id'] for row in no['data']} == {b['id'], c['id']})
for lo, hi, day in [('scheduled_from', 'scheduled_to', '2026-09-18'), ('pod_eta_from', 'pod_eta_to', '2026-09-19'), ('appointment_from', 'appointment_to', '2026-09-20')]:
    check(lo + ' inclusive date range retains late time on end date', [row['id'] for row in listed(**{lo: day, hi: day})['data']] == [a['id']])
check('Date range outside delivery day returns no match', listed(scheduled_from='2026-09-19')['total'] == 0)
check('Multi status filter selects both requested statuses', listed(list_status='Upcoming Inbound|Completed Inbound')['total'] == 2)
check('Status tab counts remain available when one status is selected', listed(list_status='Upcoming Inbound')['counts'] == result['counts'])
check('Multiple transport selections and default TBD work', listed(transport_status='待提待拆|已提已拆')['total'] == 2 and listed(transport_status='TBD')['data'][0]['id'] == c['id'])
check('Combined filters narrow the same shipment', listed(size='20GP|40HQ', trucker='SYNTHETIC TRUCKER', team='SYNTHETIC TEAM', printed='true')['total'] == 1)
check('Unloading date range applies to grouped visits', listed(date_from='2026-09-17', date_to='2026-09-17')['total'] == 3 and listed(date_from='2026-09-18')['total'] == 0)
for i in range(19):
    create(f'-PAGE{i:02}')
page1 = listed(page=1, per_page=20)
page2 = listed(page=2, per_page=20)
check('Show More pagination has 20 then 2 rows without duplicates', len(page1['data']) == 20 and len(page2['data']) == 2 and len({row['id'] for row in page1['data'] + page2['data']}) == 22 and page1['total'] == 22)
check('Read after all list operations still has unchanged receipt and inventory', receiving_state(request('GET', path)) == receiving_state(before))
report = {'checked_at': datetime.now().isoformat(), 'base': BASE, 'prefix': prefix,
    'anchor_id': a['id'], 'other_ids': [second['id'], b['id'], c['id']], 'checks': checks, 'synthetic_only': True}
(ROOT / '.uni-local/ocean-list-verification.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'prefix': prefix, 'anchor_id': a['id'], 'passed': len(checks)}, ensure_ascii=False))
