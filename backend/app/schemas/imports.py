from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, computed_field

class MappingRequest(BaseModel): mapping:dict[str,str]
class ConfirmRequest(MappingRequest): duplicate_strategy:Literal["SKIP","UPDATE"]="SKIP";include_warning_rows:bool=True;auto_receive_to_inventory:bool=False;auto_create_location:bool=False
class PreviewResponse(BaseModel):job_id:int;file_name:str;detected_columns:list[str];suggested_mapping:dict[str,str];preview_rows:list[dict[str,Any]];total_rows:int
class WorkbookInspectResponse(BaseModel):upload_token:str;file_name:str;file_size:int;file_hash:str;sheet_names:list[str];sheet_row_estimates:dict[str,int];west_coast_4_0_detected:bool;suggested_profiles:dict[str,str]
class ProfileRead(BaseModel):code:str;name:str;module:str;sheet_name:str
class ValidationSummary(BaseModel):job_id:int;total_rows:int;valid_rows:int;warning_rows:int;error_rows:int;rows:list[dict[str,Any]];duration_seconds:float|None=None;rows_per_second:float|None=None
class ImportSummary(BaseModel):job_id:int;total_rows:int;imported_rows:int;skipped_rows:int;warning_rows:int;error_rows:int;reconciliation:dict[str,Any]|None=None
class ImportProgress(BaseModel):job_id:int;status:str;current_stage:str;processed_rows:int;total_rows:int;progress_percent:float;warning_rows:int;error_rows:int
class ImportJobRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;module:str;file_name:str;original_file_name:str;status:str;total_rows:int;processed_rows:int=0;progress_percent:float=0;current_stage:str="UPLOADED";valid_rows:int;warning_rows:int;error_rows:int;imported_rows:int;created_by:int;created_at:datetime;completed_at:datetime|None;mapping:dict[str,str]|None=None;profile_code:str|None=None;source_sheet:str|None=None;file_hash:str|None=None;performance:dict[str,Any]|None=None;reconciliation:dict[str,Any]|None=None
    @computed_field
    @property
    def status_name(self)->str:return self.status.replace("_"," ").title()
class ImportErrorRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;row_number:int;column_name:str|None;raw_value:str|None;severity:str;error_code:str;error_message:str;suggested_fix:str|None=None;created_at:datetime
class ImportRowRead(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:int;row_number:int;raw_data:dict[str,Any];mapped_data:dict[str,Any]|None;validation_status:str;created_entity_type:str|None;created_entity_id:int|None;created_at:datetime
