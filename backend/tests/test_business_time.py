from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.outbound import OBCreate
from app.services.dispatch_priority import DispatchPriority, calculate_days_remaining, calculate_dispatch_priority
from app.services.outbound import create_ob
from app.services.outbound_import import parsed_datetime
from app.utils.business_time import business_day_range, get_business_now, get_business_today, to_business_date, to_business_datetime


def test_business_morning_matches_utc_calendar_date():
    now=datetime(2026,8,29,16,0,tzinfo=UTC)
    assert get_business_now(now).hour==9
    assert get_business_today(now)==date(2026,8,29)==now.date()


def test_utc_next_day_does_not_make_los_angeles_outbound_critical():
    now=datetime(2026,8,30,0,30,tzinfo=UTC)
    today=get_business_today(now)
    assert today==date(2026,8,29)
    assert calculate_days_remaining(date(2026,8,30),today)==1
    assert calculate_dispatch_priority(date(2026,8,30),today)==DispatchPriority.HIGH


def test_aware_utc_crosses_to_previous_business_date():
    value=datetime(2026,8,30,0,30,tzinfo=UTC)
    converted=to_business_datetime(value)
    assert converted.isoformat()=='2026-08-29T17:30:00-07:00'
    assert to_business_date(value)==date(2026,8,29)


def test_naive_datetime_is_interpreted_as_business_local_time():
    converted=to_business_datetime(datetime(2026,8,30,8,0))
    assert converted.isoformat()=='2026-08-30T08:00:00-07:00'


def test_outbound_create_and_excel_parser_normalize_naive_schedule(db:Session,seed):
    value=datetime(2026,8,30,8,0)
    order=create_ob(db,OBCreate(warehouse_id=seed['warehouse'].id,schedule_pickup_at=value),seed['admin'].id,commit=False)
    assert order.schedule_pickup_at.isoformat()=='2026-08-30T08:00:00-07:00'
    assert parsed_datetime('2026-08-30 08:00').isoformat()=='2026-08-30T08:00:00-07:00'
    db.rollback()


def test_business_day_range_uses_aware_half_open_local_midnights():
    start,end=business_day_range(date(2026,8,29))
    assert start.isoformat()=='2026-08-29T00:00:00-07:00'
    assert end.isoformat()=='2026-08-30T00:00:00-07:00'
    assert start.tzinfo is not None and end.tzinfo is not None


def test_business_day_range_handles_dst_without_fixed_24_hours():
    start,end=business_day_range(date(2026,3,8))
    assert start.isoformat()=='2026-03-08T00:00:00-08:00'
    assert end.isoformat()=='2026-03-09T00:00:00-07:00'
    assert (end.astimezone(UTC)-start.astimezone(UTC)).total_seconds()==23*60*60

    start,end=business_day_range(date(2026,11,1))
    assert start.utcoffset()==timedelta(hours=-7)
    assert end.utcoffset()==timedelta(hours=-8)
    assert (end.astimezone(UTC)-start.astimezone(UTC)).total_seconds()==25*60*60


def test_inventory_aging_uses_business_today(client:TestClient,seed,monkeypatch):
    monkeypatch.setattr('app.services.inventory.get_business_today',lambda:date(2026,8,29))
    payload={'container_number':'TZ-AGING','customer_id':seed['customer'].id,'warehouse_id':seed['warehouse'].id,'received_date':'2026-08-20','fc_code':'ONT8','pallet_qty':1,'carton_qty':1,'weight_lbs':1,'cbm':1,'location_id':seed['location'].id,'status':3}
    inbound=client.post('/api/v1/inbound',json=payload).json();lot=client.post(f"/api/v1/inbound/{inbound['id']}/receive-to-inventory")
    assert lot.status_code==200,lot.text
    assert lot.json()['aging_days']==9
