from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field

Quantity = Decimal

class BusinessClassification(BaseModel):
    business_type: Literal["FBA", "PRIVATE"]

class AllocationWrite(BaseModel):
    inventory_allocation_id: int
    carton_qty: Decimal = Field(ge=0, le=Decimal("9999999999.99"), decimal_places=2)
    pallet_qty: Decimal = Field(ge=0, le=Decimal("9999999999.99"), decimal_places=2)
    operation_id: str = Field(min_length=1, max_length=64)

class PlanLineWrite(BaseModel):
    allocation_id: int
    carton_qty: Decimal = Field(ge=0, le=Decimal("9999999999.99"), decimal_places=2)
    pallet_qty: Decimal = Field(ge=0, le=Decimal("9999999999.99"), decimal_places=2)

class PlanWrite(BaseModel):
    expected_revision: int = Field(ge=0)
    lines: list[PlanLineWrite] = Field(min_length=1, max_length=1000)

class PlanFinalize(BaseModel):
    expected_revision: int = Field(ge=0)
