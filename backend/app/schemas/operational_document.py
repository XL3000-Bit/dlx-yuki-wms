from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    dispatch_business_type: str | None = None
    model_config = ConfigDict(from_attributes=True)
    id: int; document_no: str; document_type: str; status: str; version: int
    original_filename: str; content_type: str; file_size: int | None; checksum_sha256: str | None
    is_generated: bool; title: str | None; notes: str | None; warehouse_id: int; customer_id: int | None
    inbound_id: int | None
    load_id: int | None; outbound_id: int | None; bol_id: int | None; work_order_id: int | None
    operational_exception_id: int | None; container_tracking_id: int | None
    created_by: int; archived_at: datetime | None; archived_by: int | None; created_at: datetime; updated_at: datetime


class DocumentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; document_id: int; event_type: str; actor_user_id: int | None; message: str | None; created_at: datetime
