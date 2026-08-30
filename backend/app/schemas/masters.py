from pydantic import EmailStr, Field
from app.schemas.common import Timestamped, ORMModel


class CustomerCreate(ORMModel):
    customer_code: str = Field(min_length=1, max_length=50)
    customer_name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = None; phone: str | None = None; email: EmailStr | None = None; remark: str | None = None
class CustomerRead(CustomerCreate, Timestamped): is_active: bool

class WarehouseCreate(ORMModel):
    warehouse_code: str; warehouse_name: str; address: str; city: str; state: str; zip_code: str; country: str = "US"
class WarehouseRead(WarehouseCreate, Timestamped): is_active: bool

class AreaCreate(ORMModel): warehouse_id: int; area_code: str; area_name: str
class AreaRead(AreaCreate, Timestamped): is_active: bool

class LocationCreate(ORMModel): warehouse_id: int; area_id: int; location_code: str; location_name: str
class LocationRead(LocationCreate, Timestamped): is_active: bool

class CarrierCreate(ORMModel):
    carrier_code: str; carrier_name: str; scac: str | None = None; contact_name: str | None = None; phone: str | None = None; email: EmailStr | None = None; remark: str | None = None
class CarrierRead(CarrierCreate, Timestamped): is_active: bool

class FCAddressCreate(ORMModel):
    fc_code: str; fc_name: str | None = None; address_line1: str; address_line2: str | None = None; city: str; state: str; zip_code: str; country: str = "US"
class FCAddressRead(FCAddressCreate, Timestamped): is_active: bool
