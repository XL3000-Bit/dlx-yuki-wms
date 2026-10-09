"""Prevent legacy writers from bypassing the OB BOL lifecycle."""
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.orm import Session


@event.listens_for(Session, 'before_flush')
def protect_uni_aggregate(db, flush_context, instances):
    if db.info.get('uni_workflow'):
        return
    from app.models import (UniBol, OutboundOrder, FBAShipment, OutboundInventoryAllocation,
                            FBAInventoryAllocation, PickingList, PickingListItem, BOL, BOLItem,
                            OperationalDocument)
    from app.models.operational_document import DocumentType
    ob_ids, fba_ids = set(), set()
    for obj in set(db.dirty) | set(db.deleted) | set(db.new):
        if obj in db.dirty and not db.is_modified(obj, include_collections=False):
            continue
        if isinstance(obj, OutboundOrder):
            ob_ids.add(obj.id)
        elif isinstance(obj, FBAShipment):
            fba_ids.add(obj.id)
        elif isinstance(obj, (OutboundInventoryAllocation, PickingList, BOL)):
            ob_ids.add(obj.outbound_order_id)
        elif isinstance(obj, FBAInventoryAllocation):
            fba_ids.add(obj.fba_shipment_id)
        elif isinstance(obj, PickingListItem):
            parent = db.get(PickingList, obj.picking_list_id) if obj.picking_list_id else None
            if parent:
                ob_ids.add(parent.outbound_order_id)
        elif isinstance(obj, BOLItem):
            parent = db.get(BOL, obj.bol_id) if obj.bol_id else None
            if parent:
                ob_ids.add(parent.outbound_order_id)
        elif isinstance(obj, OperationalDocument) and obj.document_type == DocumentType.POD:
            # Replacing or archiving a reviewed POD must not leave the aggregate
            # pointing to a missing/superseded document with a Verified status.
            ob_ids.add(obj.outbound_id)
            parent = db.get(BOL, obj.bol_id) if obj.bol_id else None
            if parent:
                ob_ids.add(parent.outbound_order_id)
    ob_ids.discard(None)
    fba_ids.discard(None)
    if (ob_ids and db.scalar(select(UniBol.id).where(UniBol.outbound_order_id.in_(ob_ids)).limit(1))) or (
            fba_ids and db.scalar(select(UniBol.id).where(UniBol.fba_shipment_id.in_(fba_ids)).limit(1))):
        raise HTTPException(409, 'This shipment is managed by OB BOL. Use the OB BOL workflow.')
