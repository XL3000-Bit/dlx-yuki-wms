import enum
from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")

class ImportModule(str, enum.Enum): INBOUND="INBOUND"; FBA="FBA"; OUTBOUND="OUTBOUND"; INVENTORY_ADJUSTMENT="INVENTORY_ADJUSTMENT"; CONTAINER_TRACKING="CONTAINER_TRACKING"
class ImportStatus(str, enum.Enum): UPLOADED="UPLOADED"; READING="READING"; MAPPING="MAPPING"; PREVIEWED="PREVIEWED"; VALIDATING="VALIDATING"; VALIDATED="VALIDATED"; READY="READY"; IMPORTING="IMPORTING"; COMPLETED="COMPLETED"; FAILED="FAILED"; CANCELED="CANCELED"
class ImportSeverity(str, enum.Enum): WARNING="WARNING"; ERROR="ERROR"
class RowValidationStatus(str, enum.Enum): PENDING="PENDING"; VALID="VALID"; WARNING="WARNING"; ERROR="ERROR"; IMPORTED="IMPORTED"; SKIPPED="SKIPPED"

class ImportJob(Base):
    __tablename__="import_jobs"
    id:Mapped[int]=mapped_column(primary_key=True);module:Mapped[ImportModule]=mapped_column(Enum(ImportModule,name="import_module"),index=True);file_name:Mapped[str]=mapped_column(String(255));original_file_name:Mapped[str]=mapped_column(String(255));status:Mapped[ImportStatus]=mapped_column(Enum(ImportStatus,name="import_status"),index=True,default=ImportStatus.UPLOADED)
    profile_code:Mapped[str|None]=mapped_column(String(64),index=True);source_sheet:Mapped[str|None]=mapped_column(String(100));file_size:Mapped[int|None]=mapped_column(Integer);file_hash:Mapped[str|None]=mapped_column(String(64),index=True);stored_file_path:Mapped[str|None]=mapped_column(String(500));batch_size:Mapped[int]=mapped_column(Integer,default=1000,server_default="1000")
    total_rows:Mapped[int]=mapped_column(Integer,default=0);processed_rows:Mapped[int]=mapped_column(Integer,default=0,server_default="0");progress_percent:Mapped[Decimal]=mapped_column(Numeric(6,2),default=0,server_default="0");current_stage:Mapped[str]=mapped_column(String(32),default="UPLOADED",server_default="UPLOADED");valid_rows:Mapped[int]=mapped_column(Integer,default=0);warning_rows:Mapped[int]=mapped_column(Integer,default=0);error_rows:Mapped[int]=mapped_column(Integer,default=0);imported_rows:Mapped[int]=mapped_column(Integer,default=0)
    mapping:Mapped[dict[str,str]|None]=mapped_column(JsonType);detected_columns:Mapped[list[str]|None]=mapped_column(JsonType);sheet_names:Mapped[list[str]|None]=mapped_column(JsonType);sheet_row_estimates:Mapped[dict[str,int]|None]=mapped_column(JsonType);options:Mapped[dict[str,Any]|None]=mapped_column(JsonType);performance:Mapped[dict[str,Any]|None]=mapped_column(JsonType);reconciliation:Mapped[dict[str,Any]|None]=mapped_column(JsonType);duplicate_of_job_id:Mapped[int|None]=mapped_column(ForeignKey("import_jobs.id",ondelete="SET NULL"),index=True);created_by:Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="RESTRICT"),index=True);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now());completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));rows:Mapped[list["ImportRow"]]=relationship(cascade="all, delete-orphan",foreign_keys="ImportRow.import_job_id");errors:Mapped[list["ImportError"]]=relationship(cascade="all, delete-orphan")

class ImportRow(Base):
    __tablename__="import_rows"
    id:Mapped[int]=mapped_column(primary_key=True);import_job_id:Mapped[int]=mapped_column(ForeignKey("import_jobs.id",ondelete="CASCADE"),index=True);row_number:Mapped[int]=mapped_column(Integer);source_sheet:Mapped[str|None]=mapped_column(String(100));row_fingerprint:Mapped[str|None]=mapped_column(String(64),index=True);raw_data:Mapped[dict[str,Any]]=mapped_column(JsonType);mapped_data:Mapped[dict[str,Any]|None]=mapped_column(JsonType);validation_status:Mapped[RowValidationStatus]=mapped_column(Enum(RowValidationStatus,name="row_validation_status"),default=RowValidationStatus.PENDING);created_entity_type:Mapped[str|None]=mapped_column(String(50));created_entity_id:Mapped[int|None]=mapped_column(Integer);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class ImportError(Base):
    __tablename__="import_errors"
    id:Mapped[int]=mapped_column(primary_key=True);import_job_id:Mapped[int]=mapped_column(ForeignKey("import_jobs.id",ondelete="CASCADE"),index=True);row_number:Mapped[int]=mapped_column(Integer);column_name:Mapped[str|None]=mapped_column(String(100));raw_value:Mapped[str|None]=mapped_column(Text);severity:Mapped[ImportSeverity]=mapped_column(Enum(ImportSeverity,name="import_severity"));error_code:Mapped[str]=mapped_column(String(50));error_message:Mapped[str]=mapped_column(Text);suggested_fix:Mapped[str|None]=mapped_column(Text);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
