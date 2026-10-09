from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession, require_outbound_write
from app.models import User
from app.schemas.outbound import OBCreate
from app.services.access_policy import assert_customer_access, assert_warehouse_access
from app.services.outbound import create_ob
from app.services.cargo_bol import assign_remaining, cargo_detail, export_cargo_bols, list_cargo_bols

router = APIRouter(prefix="/cargo-bols", tags=["Cargo BOL"])
Writer = Annotated[User, Depends(require_outbound_write)]


class AssignRequest(BaseModel):
    outbound_id: int = Field(gt=0)
    bol_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=100)


class CargoOutbound(OBCreate):
    warehouse_id: int = Field(gt=0)
    customer_id: int = Field(gt=0)


class CreateOutboundRequest(BaseModel):
    outbound: CargoOutbound
    bol_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=100)


def cargo_filters(q: str = Query("", max_length=200), remaining_only: bool = False,
                  warehouse_id: int | None = Query(None, gt=0),
                  customer_id: int | None = Query(None, gt=0),
                  source_type: Literal["INBOUND", "FBA", "HISTORY_OUTBOUND"] | None = None,
                  del_code: str | None = Query(None, max_length=100)):
    return dict(q=q, remaining_only=remaining_only, warehouse_id=warehouse_id,
                customer_id=customer_id, source_type=source_type, del_code=del_code)


Filters = Annotated[dict, Depends(cargo_filters)]


@router.get("")
def listing(db: DbSession, user: CurrentUser, filters: Filters, page: int = Query(1, ge=1),
            page_size: int = Query(20, ge=1, le=100)):
    return list_cargo_bols(db, user, page=page, page_size=page_size, **filters)


@router.get("/export.xlsx")
def export(db: DbSession, user: CurrentUser, filters: Filters):
    return Response(export_cargo_bols(db, user, **filters),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="Cargo_BOL_Export.xlsx"'})


@router.post("/assign")
def assign(body: AssignRequest, db: DbSession, user: Writer):
    return assign_remaining(db, user, body.outbound_id, body.bol_ids)


@router.post("/create-outbound", status_code=201)
def create_from_cargo(body: CreateOutboundRequest, db: DbSession, user: Writer):
    assert_warehouse_access(user, body.outbound.warehouse_id)
    assert_customer_access(user, body.outbound.customer_id)
    try:
        order = create_ob(db, body.outbound, user.id, commit=False)
        # Assignment commits the order and all allocations together, or rolls all of them back.
        return assign_remaining(db, user, order.id, body.bol_ids)
    except Exception:
        db.rollback()
        raise


@router.get("/{identity_id}")
def detail(identity_id: int, db: DbSession, user: CurrentUser):
    return cargo_detail(db, user, identity_id)
