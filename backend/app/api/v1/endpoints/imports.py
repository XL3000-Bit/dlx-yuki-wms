import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from fastapi import APIRouter,BackgroundTasks,Depends,File,HTTPException,UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from app.api.deps import CurrentUser,DbSession,require_warehouse_write
from app.db.session import SessionLocal
from app.imports.mapping import suggest_fba_mapping,suggest_mapping
from app.imports.profiles import PROFILES,detect_workbook,suggest_profile
from app.imports.readers import read_tabular,workbook_metadata
from app.models import ImportError,ImportJob,ImportRow,User
from app.models.import_job import ImportModule,ImportStatus
from app.schemas.imports import ConfirmRequest,ImportErrorRead,ImportJobRead,ImportProgress,ImportRowRead,ImportSummary,MappingRequest,PreviewResponse,ProfileRead,ValidationSummary,WorkbookInspectResponse
from app.services.import_service import confirm_job,validate_job
from app.services.fba_import import confirm_fba_job,validate_fba_job
from app.services.outbound_import import confirm_outbound_job,validate_outbound_job
from app.services.phase8_import import confirm_profile_job,stage_profile_job,validate_profile_job

router=APIRouter(prefix="/imports",tags=["Imports"])
Writer=Annotated[User,Depends(require_warehouse_write)]
UPLOAD_DIR=Path(__file__).resolve().parents[4]/"data"/"imports"
TOKEN_RE=re.compile(r"^[a-f0-9]{32}$")
def get_job(db:DbSession,job_id:int)->ImportJob:
    job=db.get(ImportJob,job_id)
    if job is None:raise HTTPException(404,"Import job not found")
    return job
def require_module(job:ImportJob,module:ImportModule)->ImportJob:
    if job.module!=module:raise HTTPException(409,f"Import job is not a {module.value} job")
    return job

def _upload_paths(token:str)->tuple[Path,Path]:
    if not TOKEN_RE.fullmatch(token):raise HTTPException(404,"Upload not found")
    metadata=UPLOAD_DIR/f"{token}.json"
    if not metadata.exists():raise HTTPException(404,"Upload not found")
    info=json.loads(metadata.read_text(encoding="utf-8"));path=UPLOAD_DIR/f"{token}{info['extension']}"
    if not path.exists():raise HTTPException(404,"Upload not found")
    return path,metadata

@router.get("/profiles",response_model=list[ProfileRead])
def profiles(_:CurrentUser):
    return [ProfileRead(code=p.code,name=p.name,module=p.module.value,sheet_name=p.sheet_name) for p in PROFILES.values()]

@router.post("/workbook/inspect",response_model=WorkbookInspectResponse,status_code=201)
async def inspect_workbook(_:Writer,file:UploadFile=File(...)):
    name=file.filename or "upload.xlsx";extension=Path(name).suffix.lower()
    if extension not in (".xlsx",".csv"):raise HTTPException(415,"Only .xlsx and .csv files are supported")
    UPLOAD_DIR.mkdir(parents=True,exist_ok=True);token=uuid4().hex;path=UPLOAD_DIR/f"{token}{extension}";digest=hashlib.sha256();size=0
    with path.open("wb") as output:
        while chunk:=await file.read(1024*1024):output.write(chunk);digest.update(chunk);size+=len(chunk)
    try:
        metadata=workbook_metadata(path) if extension==".xlsx" else {"sheet_names":["CSV"],"sheet_row_estimates":{"CSV":0}}
    except Exception as exc:
        path.unlink(missing_ok=True);raise HTTPException(422,f"Workbook metadata could not be read: {exc}")from exc
    detected=detect_workbook(metadata["sheet_names"]);suggestions={sheet:code for sheet in metadata["sheet_names"] if(code:=suggest_profile(sheet,metadata["sheet_names"]))}
    info={"file_name":name,"extension":extension,"file_size":size,"file_hash":digest.hexdigest(),**metadata}
    (UPLOAD_DIR/f"{token}.json").write_text(json.dumps(info,ensure_ascii=False),encoding="utf-8")
    return WorkbookInspectResponse(upload_token=token,file_name=name,file_size=size,file_hash=info["file_hash"],sheet_names=metadata["sheet_names"],sheet_row_estimates=metadata["sheet_row_estimates"],west_coast_4_0_detected=detected,suggested_profiles=suggestions)

@router.post("/workbook/{upload_token}/preview",response_model=PreviewResponse,status_code=201)
def preview_profile(upload_token:str,sheet_name:str,profile_code:str,warehouse_id:int,db:DbSession,user:Writer,batch_size:int=1000,preview_limit:int=30):
    path,metadata_path=_upload_paths(upload_token);info=json.loads(metadata_path.read_text(encoding="utf-8"))
    return stage_profile_job(db,path=path,original_name=info["file_name"],file_hash=info["file_hash"],file_size=info["file_size"],sheet_name=sheet_name,profile_code=profile_code,warehouse_id=warehouse_id,user_id=user.id,sheet_names=info["sheet_names"],sheet_row_estimates=info["sheet_row_estimates"],batch_size=batch_size,preview_limit=preview_limit)

def _validate_background(job_id:int)->None:
    with SessionLocal() as session:
        job=session.get(ImportJob,job_id)
        if job is None:return
        try:validate_profile_job(session,job,False)
        except Exception:
            session.rollback();job=session.get(ImportJob,job_id)
            if job:job.status=ImportStatus.FAILED;job.current_stage="FAILED";session.commit()

@router.post("/{job_id}/validate-async",status_code=202)
def validate_async(job_id:int,tasks:BackgroundTasks,db:DbSession,_:Writer):
    job=get_job(db,job_id)
    if not job.profile_code:raise HTTPException(409,"Async validation requires an Import Profile")
    if job.status not in(ImportStatus.PREVIEWED,ImportStatus.VALIDATED,ImportStatus.READY):raise HTTPException(409,"Import job cannot be validated")
    job.status=ImportStatus.VALIDATING;job.current_stage="VALIDATING";job.processed_rows=0;job.progress_percent=0;db.commit();tasks.add_task(_validate_background,job.id)
    return {"job_id":job.id,"status":"VALIDATING"}

@router.get("/{job_id}/progress",response_model=ImportProgress)
def progress(job_id:int,db:DbSession,_:CurrentUser):
    job=get_job(db,job_id);return ImportProgress(job_id=job.id,status=job.status.value,current_stage=job.current_stage,processed_rows=job.processed_rows,total_rows=job.total_rows,progress_percent=float(job.progress_percent),warning_rows=job.warning_rows,error_rows=job.error_rows)

@router.get("/{job_id}/validation-result",response_model=ValidationSummary)
def validation_result(job_id:int,db:DbSession,_:CurrentUser):
    job=get_job(db,job_id)
    if job.status not in(ImportStatus.READY,ImportStatus.VALIDATED,ImportStatus.COMPLETED):raise HTTPException(409,"Validation is not complete")
    rows=list(db.scalars(select(ImportRow).where(ImportRow.import_job_id==job.id).order_by(ImportRow.row_number).limit(50)).all());errors=list(db.scalars(select(ImportError).where(ImportError.import_job_id==job.id,ImportError.row_number.in_([r.row_number for r in rows])).order_by(ImportError.id)).all());by_row={}
    for error in errors:by_row.setdefault(error.row_number,[]).append({"severity":error.severity.value,"column":error.column_name or "","code":error.error_code,"message":error.error_message})
    output=[{"row_number":row.row_number,"data":row.mapped_data or{},"status":row.validation_status.value,"issues":by_row.get(row.row_number,[])} for row in rows]
    perf=job.performance or{};return ValidationSummary(job_id=job.id,total_rows=job.total_rows,valid_rows=job.valid_rows,warning_rows=job.warning_rows,error_rows=job.error_rows,rows=output,duration_seconds=perf.get("validation_seconds"),rows_per_second=perf.get("validation_rows_per_second"))

@router.get("/{job_id}/errors.xlsx")
def error_export(job_id:int,db:DbSession,_:CurrentUser):
    get_job(db,job_id);rows=list(db.scalars(select(ImportError).where(ImportError.import_job_id==job_id).order_by(ImportError.row_number,ImportError.id)).all());wb=Workbook(write_only=True);ws=wb.create_sheet("Errors");ws.append(["Row Number","Original Data","Error Code","Error Message","Suggested Fix"])
    raw_by_row={row.row_number:row.raw_data for row in db.scalars(select(ImportRow).where(ImportRow.import_job_id==job_id,ImportRow.row_number.in_({e.row_number for e in rows}))).all()}
    for error in rows:ws.append([error.row_number,json.dumps(raw_by_row.get(error.row_number,{}),ensure_ascii=False,default=str),error.error_code,error.error_message,error.suggested_fix])
    stream=BytesIO();wb.save(stream);stream.seek(0);return StreamingResponse(stream,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="import-{job_id}-errors.xlsx"'})
@router.post("/inbound/preview",response_model=PreviewResponse,status_code=201)
async def preview(db:DbSession,user:Writer,file:UploadFile=File(...),preview_limit:int=20):
    name=file.filename or "upload";extension=Path(name).suffix.lower()
    if extension not in (".xlsx",".csv"):raise HTTPException(415,"Only .xlsx and .csv files are supported")
    try:headers,rows=read_tabular(await file.read(),name)
    except (ValueError,UnicodeDecodeError) as exc:raise HTTPException(422,str(exc)) from exc
    job=ImportJob(module=ImportModule.INBOUND,file_name=name,original_file_name=name,status=ImportStatus.PREVIEWED,total_rows=len(rows),created_by=user.id);db.add(job);db.flush()
    for index,row in enumerate(rows,start=2):db.add(ImportRow(import_job_id=job.id,row_number=index,raw_data=row))
    mapping=suggest_mapping(headers);job.mapping=mapping;db.commit();return PreviewResponse(job_id=job.id,file_name=name,detected_columns=headers,suggested_mapping=mapping,preview_rows=rows[:max(1,min(preview_limit,100))],total_rows=len(rows))
@router.post("/inbound/{job_id}/validate",response_model=ValidationSummary)
def validate(job_id:int,payload:MappingRequest,db:DbSession,_:Writer):
    job=get_job(db,job_id);return validate_profile_job(db,job) if job.profile_code else validate_job(db,job,payload.mapping)
@router.post("/inbound/{job_id}/confirm",response_model=ImportSummary)
def confirm(job_id:int,payload:ConfirmRequest,db:DbSession,user:Writer):
    job=get_job(db,job_id)
    return confirm_profile_job(db,job,user.id,duplicate_strategy=payload.duplicate_strategy,include_warning_rows=payload.include_warning_rows,auto_receive_to_inventory=payload.auto_receive_to_inventory,auto_create_location=payload.auto_create_location) if job.profile_code else confirm_job(db,job,payload.mapping,payload.duplicate_strategy,user.id)
@router.post("/fba/preview",response_model=PreviewResponse,status_code=201)
async def preview_fba(db:DbSession,user:Writer,file:UploadFile=File(...),preview_limit:int=20):
    name=file.filename or "upload";extension=Path(name).suffix.lower()
    if extension not in (".xlsx",".csv"):raise HTTPException(415,"Only .xlsx and .csv files are supported")
    try:headers,rows=read_tabular(await file.read(),name)
    except (ValueError,UnicodeDecodeError) as exc:raise HTTPException(422,str(exc)) from exc
    job=ImportJob(module=ImportModule.FBA,file_name=name,original_file_name=name,status=ImportStatus.PREVIEWED,total_rows=len(rows),created_by=user.id);db.add(job);db.flush()
    for index,row in enumerate(rows,start=2):db.add(ImportRow(import_job_id=job.id,row_number=index,raw_data=row))
    mapping=suggest_fba_mapping(headers);job.mapping=mapping;db.commit();return PreviewResponse(job_id=job.id,file_name=name,detected_columns=headers,suggested_mapping=mapping,preview_rows=rows[:max(1,min(preview_limit,100))],total_rows=len(rows))
@router.post("/fba/{job_id}/validate",response_model=ValidationSummary)
def validate_fba(job_id:int,payload:MappingRequest,db:DbSession,_:Writer):
    job=require_module(get_job(db,job_id),ImportModule.FBA);return validate_profile_job(db,job) if job.profile_code else validate_fba_job(db,job,payload.mapping)
@router.post("/fba/{job_id}/confirm",response_model=ImportSummary)
def confirm_fba(job_id:int,payload:ConfirmRequest,db:DbSession,user:Writer):
    job=require_module(get_job(db,job_id),ImportModule.FBA);return confirm_profile_job(db,job,user.id,duplicate_strategy=payload.duplicate_strategy,include_warning_rows=payload.include_warning_rows) if job.profile_code else confirm_fba_job(db,job,payload.mapping,user.id)
@router.post('/outbound/preview',response_model=PreviewResponse,status_code=201)
async def preview_outbound(db:DbSession,user:Writer,file:UploadFile=File(...),preview_limit:int=20):
    name=file.filename or 'upload';extension=Path(name).suffix.lower()
    if extension not in ('.xlsx','.csv'):raise HTTPException(415,'Only .xlsx and .csv files are supported')
    try:headers,rows=read_tabular(await file.read(),name)
    except (ValueError,UnicodeDecodeError) as exc:raise HTTPException(422,str(exc)) from exc
    job=ImportJob(module=ImportModule.OUTBOUND,file_name=name,original_file_name=name,status=ImportStatus.PREVIEWED,total_rows=len(rows),created_by=user.id);db.add(job);db.flush()
    for index,row in enumerate(rows,start=2):db.add(ImportRow(import_job_id=job.id,row_number=index,raw_data=row))
    from app.imports.mapping import suggest_outbound_mapping
    mapping=suggest_outbound_mapping(headers);job.mapping=mapping;db.commit();return PreviewResponse(job_id=job.id,file_name=name,detected_columns=headers,suggested_mapping=mapping,preview_rows=rows[:max(1,min(preview_limit,100))],total_rows=len(rows))
@router.post('/outbound/{job_id}/validate',response_model=ValidationSummary)
def validate_outbound(job_id:int,payload:MappingRequest,db:DbSession,_:Writer):
    job=require_module(get_job(db,job_id),ImportModule.OUTBOUND);return validate_profile_job(db,job) if job.profile_code else validate_outbound_job(db,job,payload.mapping)
@router.post('/outbound/{job_id}/confirm',response_model=ImportSummary)
def confirm_outbound(job_id:int,payload:ConfirmRequest,db:DbSession,user:Writer):
    job=require_module(get_job(db,job_id),ImportModule.OUTBOUND);return confirm_profile_job(db,job,user.id,duplicate_strategy=payload.duplicate_strategy,include_warning_rows=payload.include_warning_rows) if job.profile_code else confirm_outbound_job(db,job,payload.mapping,user.id,payload.duplicate_strategy)
@router.get("",response_model=list[ImportJobRead])
def jobs(db:DbSession,_:CurrentUser):return list(db.scalars(select(ImportJob).order_by(ImportJob.id.desc()).limit(200)).all())
@router.get("/{job_id}",response_model=ImportJobRead)
def job(job_id:int,db:DbSession,_:CurrentUser):return get_job(db,job_id)
@router.get("/{job_id}/errors",response_model=list[ImportErrorRead])
def errors(job_id:int,db:DbSession,_:CurrentUser):get_job(db,job_id);return list(db.scalars(select(ImportError).where(ImportError.import_job_id==job_id).order_by(ImportError.row_number)).all())
@router.get("/{job_id}/rows",response_model=list[ImportRowRead])
def rows(job_id:int,db:DbSession,_:CurrentUser):get_job(db,job_id);return list(db.scalars(select(ImportRow).where(ImportRow.import_job_id==job_id).order_by(ImportRow.row_number).limit(500)).all())
