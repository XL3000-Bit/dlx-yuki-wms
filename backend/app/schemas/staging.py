from decimal import Decimal

from pydantic import BaseModel, Field


class StageRequest(BaseModel):
    outbound_id: int
    picking_item_id: int
    staging_location_id: int | None = None
    location_id: int | None = None
    quantity: Decimal = Field(gt=0)
    quantity_unit: str = "PALLET"
    action: str = "STAGE"
    client_operation_id: str | None = Field(None, max_length=64)


class VerificationStartRequest(BaseModel):
    client_operation_id: str | None = Field(None, max_length=64)


class VerificationScanRequest(BaseModel):
    verification_run_id: str | None = None
    verification_id: str | None = None
    outbound_id: int
    picking_item_id: int
    quantity: Decimal = Field(gt=0)
    quantity_unit: str = "PALLET"
    client_operation_id: str | None = Field(None, max_length=64)


class VerificationCompleteRequest(BaseModel):
    verification_run_id: str | None = None
    verification_id: str | None = None
    client_operation_id: str | None = Field(None, max_length=64)
