"""Rollback-only PostgreSQL performance fixture for the Phase 9 workbench."""
import sys,time
from app.db.session import SessionLocal
from app.models import FBAShipment,User,Warehouse
from app.services.fba_workbench import list_workbench,workbench_detail

db=SessionLocal()
try:
    user=db.query(User).first();warehouse=db.query(Warehouse).first();base=db.query(FBAShipment).count()
    fixture_size=int(sys.argv[1])if len(sys.argv)>1 else 5000
    rows=[FBAShipment(fba_no=f"PH9PERF{i:06d}",warehouse_id=warehouse.id,amazon_fc_code="ONT8",status=0,created_by=user.id)for i in range(fixture_size)]
    db.add_all(rows);db.flush();started=time.perf_counter();result=list_workbench(db,user,page=1,per_page=20,stage="all",sort_by="priority_rank",sort_order="desc");list_ms=(time.perf_counter()-started)*1000
    started=time.perf_counter();workbench_detail(db,rows[0].id,user);detail_ms=(time.perf_counter()-started)*1000
    print(f"BASE={base} FIXTURE={fixture_size} TOTAL={result['meta']['total']} LIST_MS={list_ms:.1f} DETAIL_MS={detail_ms:.1f}")
finally:
    db.rollback();db.close();print("ROLLED_BACK=YES")
