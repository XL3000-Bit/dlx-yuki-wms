import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from app.api.deps import DbSession, require_admin
from app.models.user import User
from app.models.customer import Customer
from app.models.inbound import InboundRecord, AuditLog
from app.services.wps_duplicates import identity_key
from app.services.wps_duplicates import annotate_duplicates
from app.services.wps_link_review import annotate_link_review
from app.models.warehouse import Warehouse, WarehouseLocation
from app.services.wps_review import review

router = APIRouter(prefix="/wps", tags=["WPS review"])
# Deployments may point this at their own private snapshot directory.
SNAPSHOT_DIR = Path(os.environ.get("WPS_PREVIEW_DIR", str(Path(__file__).resolve().parents[5] / "tmp" / "wps")))


class ReviewRequest(BaseModel):
    warehouse_id: int | None = None
    customer_overrides: dict[str, int] = Field(default_factory=dict, max_length=10000)


@router.post("/review")
def preview(payload: ReviewRequest, db: DbSession, _user: Annotated[User, Depends(require_admin)]):
    if payload.warehouse_id is not None:
        warehouse = db.get(Warehouse, payload.warehouse_id)
        if warehouse is None or not warehouse.is_active:
            raise HTTPException(422, "请选择有效仓库")
    sheets = []
    for name, filename in (("OL", "ol-normalized.json"), ("提柜", "inbound-normalized.json")):
        path = SNAPSHOT_DIR / filename
        try:
            sheet = json.loads(path.read_text(encoding="utf-8-sig"))
            if sheet.get("mode") != "normalized_preview_only" or sheet.get("sheet") != name or sheet.get("customerScope") != "all":
                raise ValueError("Unexpected snapshot format")
            if not isinstance(sheet.get("rows"), list):
                raise ValueError("Missing rows")
            sheet["snapshotTime"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            sheets.append(sheet)
        except FileNotFoundError:
            raise HTTPException(409, "尚未生成 WPS 样本，请先运行拉取与标准化脚本")
        except (OSError, ValueError):
            raise HTTPException(409, "WPS 样本无法读取，请重新生成")
    try:
        result = review(sheets, db.scalars(select(Customer)).all(),
                      db.scalars(select(WarehouseLocation)).all(), payload.warehouse_id, payload.customer_overrides)
        records = db.scalars(select(InboundRecord).execution_options(populate_existing=True)).all()
        result["duplicateSummary"] = annotate_duplicates(result["sheets"], records)
        result["linkSummary"] = annotate_link_review(result["sheets"], records, payload.warehouse_id)
        return result
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class ConfirmLinkRequest(ReviewRequest):
    source_identity: dict[str, str]
    inbound_id: int
    confirmation_token: str = Field(min_length=64, max_length=64)


@router.post('/links/confirm')
def confirm_link(payload: ConfirmLinkRequest, db: DbSession, user: Annotated[User, Depends(require_admin)]):
    try:
        # Serialize link claims and inbound edits, including claims for the same source
        # on different records. Kept within this short confirmation transaction.
        if db.bind.dialect.name == 'postgresql':
            db.execute(text('LOCK TABLE inbound_records IN SHARE ROW EXCLUSIVE MODE'))
        result = preview(payload, db, user)
        source = identity_key(payload.source_identity)
        rows = [row for sheet in result['sheets'] if sheet['sheet'] == 'OL'
                for row in sheet['rows'] if source and identity_key(row['sourceIdentity']) == source]
        if len(rows) != 1:
            raise HTTPException(409, '来源缺失或重复，请重新载入样本')
        row = rows[0]
        check = row['linkReview']
        if (check['status'] != 'ready_for_review' or check['suggestedInboundId'] != payload.inbound_id
                or check.get('confirmationToken') != payload.confirmation_token):
            raise HTTPException(409, '数据或关联状态已变化，请重新载入并核对后确认')
        record = db.get(InboundRecord, payload.inbound_id)
        before = record.source_metadata
        if before is not None and not isinstance(before, dict):
            raise HTTPException(409, '历史来源资料格式异常，请先核查')
        record.source_metadata = {**(before or {}), 'sourceIdentity': row['sourceIdentity'],
            'wpsLink': {'confirmedBy': user.id, 'confirmedAt': datetime.now(timezone.utc).isoformat(),
                        'snapshotValues': row['values'], 'confirmationToken': payload.confirmation_token}}
        db.add(AuditLog(user_id=user.id, action='WPS_LINK_CONFIRMED', entity_type='InboundRecord',
                       entity_id=record.id, before_data={'source_metadata': before},
                       after_data={'source_metadata': record.source_metadata}))
        db.commit()
        return {'inboundId': record.id, 'linked': True, 'inventoryWritten': False}
    except Exception:
        db.rollback()
        raise
