from typing import Annotated, Any, TypeVar
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.api.deps import CurrentUser, DbSession, require_admin
from app.db.base import Base
from app.models import AmazonFCAddress, Carrier, Customer, User, Warehouse, WarehouseArea, WarehouseLocation
from app.repositories.base import Repository
from app.schemas.masters import AreaCreate, AreaRead, CarrierCreate, CarrierRead, CustomerCreate, CustomerRead, FCAddressCreate, FCAddressRead, LocationCreate, LocationRead, WarehouseCreate, WarehouseRead
from app.services.access import apply_customer_scope, apply_warehouse_scope, get_access_scope

router = APIRouter(prefix="/master-data", tags=["Master Data"])
Admin = Annotated[User, Depends(require_admin)]
T = TypeVar("T", bound=Base)


def create(db: DbSession, model: type[T], payload: Any) -> T:
    try:
        return Repository(model).create(db, payload.model_dump())
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate or invalid reference") from exc


@router.get("/customers", response_model=list[CustomerRead])
def customers(db: DbSession, user: CurrentUser):
    scope = get_access_scope(db, user)
    return list(db.scalars(apply_customer_scope(select(Customer), Customer.id, scope).order_by(Customer.id)).all())

@router.post("/customers", response_model=CustomerRead, status_code=201)
def add_customer(payload: CustomerCreate, db: DbSession, _: Admin): return create(db, Customer, payload)

@router.get("/warehouses", response_model=list[WarehouseRead])
def warehouses(db: DbSession, user: CurrentUser):
    scope = get_access_scope(db, user)
    return list(db.scalars(apply_warehouse_scope(select(Warehouse), Warehouse.id, scope).order_by(Warehouse.id)).all())

@router.post("/warehouses", response_model=WarehouseRead, status_code=201)
def add_warehouse(payload: WarehouseCreate, db: DbSession, _: Admin): return create(db, Warehouse, payload)

@router.get("/warehouse-areas", response_model=list[AreaRead])
def areas(db: DbSession, user: CurrentUser):
    scope = get_access_scope(db, user)
    return list(db.scalars(apply_warehouse_scope(select(WarehouseArea), WarehouseArea.warehouse_id, scope)).all())

@router.post("/warehouse-areas", response_model=AreaRead, status_code=201)
def add_area(payload: AreaCreate, db: DbSession, _: Admin): return create(db, WarehouseArea, payload)

@router.get("/warehouse-locations", response_model=list[LocationRead])
def locations(db: DbSession, user: CurrentUser, location_code: str | None = Query(None)):
    scope = get_access_scope(db, user)
    query = apply_warehouse_scope(select(WarehouseLocation), WarehouseLocation.warehouse_id, scope)
    if location_code: query = query.where(WarehouseLocation.location_code.ilike(f"%{location_code}%"))
    return list(db.scalars(query).all())

@router.post("/warehouse-locations", response_model=LocationRead, status_code=201)
def add_location(payload: LocationCreate, db: DbSession, _: Admin): return create(db, WarehouseLocation, payload)

@router.get("/carriers", response_model=list[CarrierRead])
def carriers(db: DbSession, _: CurrentUser): return Repository(Carrier).list(db)

@router.post("/carriers", response_model=CarrierRead, status_code=201)
def add_carrier(payload: CarrierCreate, db: DbSession, _: Admin): return create(db, Carrier, payload)

@router.get("/amazon-fc-addresses", response_model=list[FCAddressRead])
def fc_addresses(db: DbSession, _: CurrentUser): return Repository(AmazonFCAddress).list(db)

@router.get("/amazon-fc-addresses/{fc_code}", response_model=FCAddressRead)
def fc_address(fc_code: str, db: DbSession, _: CurrentUser):
    item = db.scalar(select(AmazonFCAddress).where(AmazonFCAddress.fc_code == fc_code.upper()))
    if item is None: raise HTTPException(status.HTTP_404_NOT_FOUND, "Amazon FC not found")
    return item

@router.post("/amazon-fc-addresses", response_model=FCAddressRead, status_code=201)
def add_fc(payload: FCAddressCreate, db: DbSession, _: Admin):
    payload.fc_code = payload.fc_code.upper()
    return create(db, AmazonFCAddress, payload)
