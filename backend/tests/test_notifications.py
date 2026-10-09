from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import OperationalNotification


def test_urgent_work_order_notification_is_deduplicated_and_readable(client, db, seed):
    payload={"work_order_type":"GENERAL","warehouse_id":seed["warehouse"].id,"priority":"URGENT","assigned_to":seed["admin"].id}
    created=client.post("/api/v1/work-orders",json=payload)
    assert created.status_code==201
    notices=client.get("/api/v1/notifications",params={"unread_only":True})
    assert notices.status_code==200 and notices.json()["meta"]["total"]==1
    notice=notices.json()["data"][0]
    assert notice["type"]=="WORK_ORDER_URGENT"
    assert notice["target_route"]==f"/work-orders?selected={created.json()['id']}"
    row=db.query(OperationalNotification).one()
    assert row.dedupe_key==f"WORK_ORDER_URGENT:work_order:{created.json()['id']}"
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(OperationalNotification(notification_type=row.notification_type,severity=row.severity,
                title=row.title,message=row.message,user_id=row.user_id,warehouse_id=row.warehouse_id,
                source_type=row.source_type,source_id=row.source_id,reference=row.reference,
                target_route=row.target_route,dedupe_key=row.dedupe_key))
            db.flush()
    assert db.query(OperationalNotification).count()==1
    client.patch(f"/api/v1/work-orders/{created.json()['id']}",json={"notes":"same condition"})
    assert db.query(OperationalNotification).count()==1
    assert client.post(f"/api/v1/notifications/{notice['id']}/read").status_code==200
    assert client.get("/api/v1/notifications/unread-count").json()=={"count":0}


def test_terminal_work_order_deactivates_urgent_and_overdue(client, seed):
    scheduled=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()
    created=client.post("/api/v1/work-orders",json={"work_order_type":"GENERAL","warehouse_id":seed["warehouse"].id,
        "priority":"URGENT","assigned_to":seed["admin"].id,"scheduled_at":scheduled}).json()
    types={row["type"] for row in client.get("/api/v1/notifications").json()["data"]}
    assert types=={"WORK_ORDER_URGENT","WORK_ORDER_OVERDUE"}
    client.post(f"/api/v1/work-orders/{created['id']}/status",json={"status":"IN_PROGRESS"})
    client.post(f"/api/v1/work-orders/{created['id']}/status",json={"status":"COMPLETED"})
    assert client.get("/api/v1/notifications/unread-count").json()=={"count":0}


def test_mark_all_read_only_updates_visible_user(client, db, seed):
    client.post("/api/v1/work-orders",json={"work_order_type":"GENERAL","warehouse_id":seed["warehouse"].id,
        "priority":"URGENT","assigned_to":seed["admin"].id})
    response=client.post("/api/v1/notifications/mark-all-read")
    assert response.status_code==200 and response.json()=={"updated":1}
    assert client.get("/api/v1/notifications",params={"unread_only":True}).json()["data"]==[]


def test_upcoming_load_notification_is_removed_when_load_is_canceled(client, seed):
    appointment=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    created=client.post("/api/v1/loads",json={"dispatch_business_type":"PRIVATE", "warehouse_id":seed["warehouse"].id,
        "appointment_time":appointment,"outbound_ids":[]})
    assert created.status_code==201
    notices=client.get("/api/v1/notifications").json()["data"]
    assert len(notices)==1 and notices[0]["type"]=="LOAD_APPOINTMENT_UPCOMING"
    assert notices[0]["target_route"]==f"/loads?selected={created.json()['id']}"
    canceled=client.post(f"/api/v1/loads/{created.json()['id']}/status",json={"status":"CANCELED"})
    assert canceled.status_code==200
    assert client.get("/api/v1/notifications/unread-count").json()=={"count":0}
