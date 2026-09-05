from io import BytesIO
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
 try:
  get_ob(db,ob_id,user=user)
  result=ensure_outbound_documents(db,ob_id,user.id)
  db.commit()
 except Exception:
  db.rollback()
  raise
 return {'outbound_order_id':ob_id,'picking_list_id':result.picking.id,'picking_list_number':result.picking.picking_no,'bol_id':result.bol.id,'bol_number':result.bol.bol_no,'picking_list_created':result.picking_list_created,'bol_created':result.bol_created,'documents_reused':result.documents_reused,'picking':picking_read(result.picking),'bol':bol_read(result.bol)}
@router.get('/bols',response_model=list[BOLRead])
def bols(db:DbSession,user:CurrentUser):return[bol_read(x) for x in db.scalars(_scoped_query(select(BOL).join(OutboundOrder,OutboundOrder.id==BOL.outbound_order_id),user).order_by(BOL.id.desc()).limit(200)).all()]
@router.get('/bols/{bid}',response_model=BOLRead)
def bol_detail(bid:int,db:DbSession,user:CurrentUser):return bol_read(_bol(db,user,bid))
@router.get('/bols/{bid}/xlsx')
def bol_excel(bid:int,db:DbSession,user:CurrentUser):b=_bol(db,user,bid);return StreamingResponse(BytesIO(bol_xlsx(b)),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename={b.bol_no}.xlsx'})
@router.get('/bols/{bid}/pdf')
def bol_pdf_file(bid:int,db:DbSession,user:CurrentUser):b=_bol(db,user,bid);return Response(bol_pdf(b),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename={b.bol_no}.pdf'})
