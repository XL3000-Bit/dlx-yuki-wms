"""Synthetic master data only. Refuses any database other than UNI's isolated cluster."""
import json
import os
import sys
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
url = make_url(os.environ['DATABASE_URL'])
assert url.host == '127.0.0.1' and url.port == 55437 and url.database == 'uni_phase1', 'Isolated database required'
from app.db.session import SessionLocal
from app.models import User, Warehouse, WarehouseArea, WarehouseLocation, Customer, Carrier
from app.core.security import hash_password
config = json.loads((root / '.uni-local/credentials.json').read_text(encoding='utf-8-sig'))
with SessionLocal() as db:
    admin = db.scalar(select(User).where(User.username == config['username']))
    if not admin:
        db.add(User(username=config['username'], display_name='Local Test Admin', email='uni-local@example.com', password_hash=hash_password(config['password']), role='ADMIN', is_active=True))
    elif admin.email == 'uni-local@example.invalid':
        admin.email = 'uni-local@example.com'
    warehouse = db.scalar(select(Warehouse).where(Warehouse.warehouse_code == 'UNI-TEST'))
    if not warehouse:
        warehouse = Warehouse(warehouse_code='UNI-TEST', warehouse_name='LOCAL TEST WHS', address='100 Example Road', city='Test City', state='CA', zip_code='00000')
        db.add(warehouse); db.flush()
        area = WarehouseArea(warehouse_id=warehouse.id, area_code='TEST', area_name='Test Receiving')
        db.add(area); db.flush()
        db.add(WarehouseLocation(warehouse_id=warehouse.id, area_id=area.id, location_code='TEST-A01', location_name='Test A01'))
    if not db.scalar(select(Customer).where(Customer.customer_code == 'UNI-TEST')):
        db.add(Customer(customer_code='UNI-TEST', customer_name='SYNTHETIC CUSTOMER'))
    if not db.scalar(select(Carrier).where(Carrier.carrier_code == 'UNI-TEST')):
        db.add(Carrier(carrier_code='UNI-TEST', carrier_name='SYNTHETIC CARRIER', scac='TEST'))
    db.commit()
print('Synthetic user, warehouse, location, customer and carrier ready.')
