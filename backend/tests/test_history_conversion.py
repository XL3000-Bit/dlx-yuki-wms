import pytest
from fastapi import HTTPException
from sqlalchemy import select, func
from app.models import ImportJob, ImportRow, InboundRecord, FBAShipment, OutboundOrder, InventoryLot
from app.models.import_job import ImportModule
from app.models.container_tracking import ContainerTracking
from app.services.convert_west_history import convert, PROFILE
from app.services.history_policy import require_live_record


def test_history_conversion_preserves_source_without_stock_and_is_repeatable(db, seed):
    rows = []
    for sheet in ('提柜', 'OL', 'DS', '出库'):
        job = ImportJob(module=ImportModule.INBOUND, file_name='history.xlsx', original_file_name='history.xlsx',
                        profile_code=PROFILE, source_sheet=sheet, created_by=seed['admin'].id)
        db.add(job); db.flush()
        row = ImportRow(import_job_id=job.id, row_number=2,
                        raw_data={'柜号': 'TEST123', '板数': '2', '件数': '30', '预计送仓时间': '待定'})
        db.add(row); rows.append(row)
    db.flush()
    result = convert(db, seed['admin'].id, seed['warehouse'].id)
    assert result['created'] == {'提柜': 1, 'OL': 1, 'DS': 1, '出库': 1}
    assert len(result['issues']) == 1
    assert db.scalar(select(func.count()).select_from(InventoryLot)) == 0
    for model in (InboundRecord, FBAShipment, OutboundOrder):
        record = db.scalar(select(model))
        with pytest.raises(HTTPException) as error:
            require_live_record(db, record)
        assert error.value.status_code == 409
    assert db.scalar(select(InboundRecord)).carton_qty == 30
    assert db.scalar(select(ContainerTracking)).container_number == 'TEST123'
    assert all(r.created_entity_id and r.mapped_data['business_no'] for r in rows)
    assert rows[-1].raw_data['预计送仓时间'] == '待定'
    second = convert(db, seed['admin'].id, seed['warehouse'].id)
    assert second['created'] == {}
    assert second['already_converted'] == result['created']
