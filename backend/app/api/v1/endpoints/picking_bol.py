from io import BytesIO
from openpyxl import Workbook
from fastapi import APIRouter,Depends
from fastapi.responses import Response,StreamingResponse
from app.api.deps import CurrentUser,DbSession,require_outbound_write
from app.models import User,PickingList,BOL
from app.schemas.picking_bol import BOLRead,PickComplete,PickingRead
from app.services.picking_bol import bol_pdf,bol_read,bol_xlsx,complete_picking,generate_bol,generate_picking,picking_read
router=APIRouter(tags=['Picking and BOL']);Writer=Depends(require_outbound_write)
@router.post('/outbounds/{ob_id}/picking-lists',response_model=PickingRead)
def create_picking(ob_id:int,db:DbSession,user:User=Writer):return picking_read(generate_picking(db,ob_id,user.id))
@router.get('/picking-lists',response_model=list[PickingRead])
def picking_list(db:DbSession,_:CurrentUser):return[picking_read(x) for x in db.query(PickingList).order_by(PickingList.id.desc()).limit(200)]
@router.get('/picking-lists/{pid}',response_model=PickingRead)
def picking_detail(pid:int,db:DbSession,_:CurrentUser):return picking_read(db.get(PickingList,pid))
@router.post('/picking-lists/{pid}/complete',response_model=PickingRead)
def picking_complete(pid:int,payload:PickComplete|None,db:DbSession,user:User=Writer):return picking_read(complete_picking(db,pid,user.id,payload))
@router.get('/picking-lists/{pid}/xlsx')
def picking_excel(pid:int,db:DbSession,_:CurrentUser):
 p=db.get(PickingList,pid);wb=Workbook();ws=wb.active;ws.append(['Picking No','OB ID','Sequence','Location','Container','FC','Marking','Pallet','Carton','Weight LBS','CBM'])
 for i in p.items:ws.append([p.picking_no,p.outbound_order_id,i.sequence_no,i.location.location_code if i.location else '',i.container_number,i.fc_code,i.marking,i.planned_pallet_qty,i.planned_carton_qty,i.planned_weight_lbs,i.planned_cbm])
 s=BytesIO();wb.save(s);s.seek(0);return StreamingResponse(s,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename={p.picking_no}.xlsx'})
@router.post('/outbounds/{ob_id}/bol',response_model=BOLRead)
def create_bol(ob_id:int,db:DbSession,user:User=Writer):return bol_read(generate_bol(db,ob_id,user.id))
@router.get('/bols',response_model=list[BOLRead])
def bols(db:DbSession,_:CurrentUser):return[bol_read(x) for x in db.query(BOL).order_by(BOL.id.desc()).limit(200)]
@router.get('/bols/{bid}',response_model=BOLRead)
def bol_detail(bid:int,db:DbSession,_:CurrentUser):return bol_read(db.get(BOL,bid))
@router.get('/bols/{bid}/xlsx')
def bol_excel(bid:int,db:DbSession,_:CurrentUser):b=db.get(BOL,bid);return StreamingResponse(BytesIO(bol_xlsx(b)),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename={b.bol_no}.xlsx'})
@router.get('/bols/{bid}/pdf')
def bol_pdf_file(bid:int,db:DbSession,_:CurrentUser):b=db.get(BOL,bid);return Response(bol_pdf(b),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename={b.bol_no}.pdf'})
