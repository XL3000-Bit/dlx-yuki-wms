"""Explicit historical fixtures for downstream tests; never dispatch authorization."""
def mark_historical_dispatched(db, order_id):
    from app.models import OutboundOrder
    db.get(OutboundOrder, order_id).status = 4
    db.commit()

def mark_historical_exception(db, order_id, reason):
    """Import a legacy exception state; runtime DISPATCHED -> EXCEPTION is forbidden."""
    from app.models import OutboundOrder
    order = db.get(OutboundOrder, order_id)
    order.status = 7
    order.exception_reason = reason
    db.commit()
