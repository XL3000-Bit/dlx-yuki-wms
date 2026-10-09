from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from openpyxl import Workbook
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from fastapi.responses import Response,StreamingResponse
from app.api.deps import CurrentUser,DbSession,require_outbound_write
from app.models import User,PickingList,BOL,OutboundOrder
from app.schemas.picking_bol import BOLRead,OutboundDocumentsRead,PickComplete,PickingRead
from app.services.picking_bol import bol_pdf,bol_read,bol_xlsx,complete_picking,ensure_outbound_documents,generate_bol,generate_picking,picking_read
from app.services.access_policy import customer_clause, warehouse_clause
from app.services.outbound import get_ob
from app.services.history_policy import require_live_record
from app.services.picking_bol import picking_pdf
router=APIRouter(tags=['Picking and BOL']);Writer=Depends(require_outbound_write)
@router.post('/outbounds/{ob_id}/picking-lists',response_model=PickingRead)
def create_picking(ob_id:int,db:DbSession,user:User=Writer):get_ob(db,ob_id,user=user);return picking_read(generate_picking(db,ob_id,user.id))
def _scoped_query(stmt,user):
 for scope in (warehouse_clause(user,OutboundOrder.warehouse_id),customer_clause(user,OutboundOrder.customer_id)):
  if scope is not None:stmt=stmt.where(scope)
 return stmt
def _picking(db,user,pid):
 row=db.scalar(_scoped_query(select(PickingList).join(OutboundOrder,OutboundOrder.id==PickingList.outbound_order_id).where(PickingList.id==pid),user))
 if row is None:raise HTTPException(404,'Picking list not found')
 return row
def _bol(db,user,bid):
 row=db.scalar(_scoped_query(select(BOL).join(OutboundOrder,OutboundOrder.id==BOL.outbound_order_id).where(BOL.id==bid),user))
 if row is None:raise HTTPException(404,'BOL not found')
 return row
@router.get('/picking-lists',response_model=list[PickingRead])
def picking_list(db:DbSession,user:CurrentUser):return[picking_read(x) for x in db.scalars(_scoped_query(select(PickingList).join(OutboundOrder,OutboundOrder.id==PickingList.outbound_order_id),user).order_by(PickingList.id.desc()).limit(200)).all()]
@router.get('/picking-lists/{pid}',response_model=PickingRead)
def picking_detail(pid:int,db:DbSession,user:CurrentUser):return picking_read(_picking(db,user,pid))
@router.post('/picking-lists/{pid}/complete',response_model=PickingRead)
def picking_complete(pid:int,payload:PickComplete|None,db:DbSession,user:User=Writer):_picking(db,user,pid);return picking_read(complete_picking(db,pid,user.id,payload))
@router.get('/picking-lists/{pid}/xlsx')
def picking_excel(pid:int,db:DbSession,user:CurrentUser):
 p=_picking(db,user,pid);wb=Workbook();ws=wb.active;ws.append(['Picking No','OB ID','Sequence','Location','Container','FC','Marking','Pallet','Carton','Weight LBS','CBM'])
 for i in p.items:ws.append([p.picking_no,p.outbound_order_id,i.sequence_no,i.location.location_code if i.location else '',i.container_number,i.fc_code,i.marking,i.planned_pallet_qty,i.planned_carton_qty,i.planned_weight_lbs,i.planned_cbm])
 s=BytesIO();wb.save(s);s.seek(0);return StreamingResponse(s,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename={p.picking_no}.xlsx'})
@router.post('/outbounds/{ob_id}/bol',response_model=BOLRead)
def create_bol(ob_id:int,db:DbSession,user:User=Writer):get_ob(db,ob_id,user=user);return bol_read(generate_bol(db,ob_id,user.id))
@router.post('/outbounds/{ob_id}/documents/ensure',response_model=OutboundDocumentsRead)
def ensure_documents(ob_id:int,db:DbSession,user:User=Writer):
 get_ob(db,ob_id,user=user);picking,bol=ensure_outbound_documents(db,ob_id,user.id);return {'outbound_order_id':ob_id,'picking':picking_read(picking),'bol':bol_read(bol)}

@router.get('/picking-lists/{pid}/pdf')
def picking_pdf_file(pid:int,db:DbSession,user:CurrentUser):
 p=_picking(db,user,pid)
 return Response(picking_pdf(p),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename={p.picking_no}.pdf'})

@router.post('/outbounds/{ob_id}/documents/package')
def document_package(ob_id:int,db:DbSession,user:User=Writer):
 ob=get_ob(db,ob_id,user=user)
 require_live_record(db,ob)
 if ob.status in (4,5,6):raise HTTPException(409,'该出库单已发车、完成或取消，请从已有单据中下载。')
 if not ob.allocations:raise HTTPException(409,'请先核对库存并分配货物，再生成 BOL 和抓货单。')
 try:
  _,bol=ensure_outbound_documents(db,ob_id,user.id,commit=False)
  pickings=list(db.scalars(select(PickingList).where(PickingList.outbound_order_id==ob_id,PickingList.status!=4).order_by(PickingList.id)).all())
  # Documents are snapshots: never silently ship an obsolete quantity.
  expected={a.id:(a.allocated_pallet_qty-a.completed_pallet_qty,a.allocated_carton_qty-a.completed_carton_qty,a.allocated_weight_lbs-a.completed_weight_lbs,a.allocated_cbm-a.completed_cbm) for a in ob.allocations}
  actual={i.outbound_allocation_id:(i.pallet_qty,i.carton_qty,i.weight_lbs,i.cbm) for i in bol.items}
  picked={}
  for p in pickings:
   for i in p.items:
    key=i.outbound_allocation_id
    old=picked.get(key,(0,0))
    picked[key]=(old[0]+i.planned_pallet_qty,old[1]+i.planned_carton_qty)
  if actual!=expected or picked!={key:value[:2] for key,value in expected.items()}:
   raise HTTPException(409,'现有单据与当前配货数量不一致，请先核对并更新单据，避免使用旧单。')
  output=BytesIO()
  with ZipFile(output,'w',ZIP_DEFLATED) as archive:
   archive.writestr(f'{bol.bol_no}.pdf',bol_pdf(bol))
   for p in pickings:archive.writestr(f'{p.picking_no}.pdf',picking_pdf(p))
  db.commit()
 except Exception:
  db.rollback()
  raise
 return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename=OB-{ob_id}-documents.zip'})
@router.get('/bols',response_model=list[BOLRead])
def bols(db:DbSession,user:CurrentUser):return[bol_read(x) for x in db.scalars(_scoped_query(select(BOL).join(OutboundOrder,OutboundOrder.id==BOL.outbound_order_id),user).order_by(BOL.id.desc()).limit(200)).all()]
@router.get('/bols/{bid}',response_model=BOLRead)
def bol_detail(bid:int,db:DbSession,user:CurrentUser):return bol_read(_bol(db,user,bid))
@router.get('/bols/{bid}/xlsx')
def bol_excel(bid:int,db:DbSession,user:CurrentUser):b=_bol(db,user,bid);return StreamingResponse(BytesIO(bol_xlsx(b)),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename={b.bol_no}.xlsx'})
@router.get('/bols/{bid}/pdf')
def bol_pdf_file(bid:int,db:DbSession,user:CurrentUser):b=_bol(db,user,bid);return Response(bol_pdf(b),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename={b.bol_no}.pdf'})
