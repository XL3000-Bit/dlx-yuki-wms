from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session,sessionmaker
from sqlalchemy.pool import StaticPool
from app.api.deps import get_db
from app.core.security import create_access_token,hash_password
from app.db.base import Base
from app.main import app
from app.models import AmazonFCAddress,Carrier,Customer,InventoryPriorityRule,User,Warehouse,WarehouseArea,WarehouseLocation
from app.models.user import UserRole

engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
TestingSession=sessionmaker(bind=engine,expire_on_commit=False)

@pytest.fixture(autouse=True)
def database()->Generator[None,None,None]:
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with TestingSession() as session:
        session.add_all([InventoryPriorityRule(min_days=0,max_days=7,priority_level="GREEN",priority_label="New",sort_order=1),InventoryPriorityRule(min_days=8,max_days=14,priority_level="YELLOW",priority_label="Attention",sort_order=2),InventoryPriorityRule(min_days=15,max_days=21,priority_level="ORANGE",priority_label="High Priority",sort_order=3),InventoryPriorityRule(min_days=22,max_days=None,priority_level="RED",priority_label="Process First",sort_order=4)]);session.commit()
    yield
    app.dependency_overrides.clear()

@pytest.fixture
def db()->Generator[Session,None,None]:
    session=TestingSession();yield session;session.close()

@pytest.fixture
def seed(db:Session)->dict[str,object]:
    admin=User(username="admin",display_name="Admin",email="admin@test.local",password_hash=hash_password("WarehousePassword!"),role=UserRole.ADMIN);viewer=User(username="viewer",display_name="Viewer",email="viewer@test.local",password_hash=hash_password("WarehousePassword!"),role=UserRole.VIEWER);customer=Customer(customer_code="ACME",customer_name="ACME Logistics");warehouse=Warehouse(warehouse_code="DLX-LAX",warehouse_name="DLX Los Angeles",address="1 Warehouse Way",city="Los Angeles",state="CA",zip_code="90001");carrier=Carrier(carrier_code="AMZF",carrier_name="Amazon Freight",scac="AFNG");fc=AmazonFCAddress(fc_code="ONT8",fc_name="Amazon ONT8",address_line1="24300 Nandina Ave",city="Moreno Valley",state="CA",zip_code="92551");db.add_all([admin,viewer,customer,warehouse,carrier,fc]);db.flush();area=WarehouseArea(warehouse_id=warehouse.id,area_code="RECEIVING",area_name="Receiving");db.add(area);db.flush();location=WarehouseLocation(warehouse_id=warehouse.id,area_id=area.id,location_code="A01",location_name="A01");db.add(location);db.commit();return{"admin":admin,"viewer":viewer,"customer":customer,"warehouse":warehouse,"location":location,"carrier":carrier,"fc":fc}

@pytest.fixture
def client(db:Session,seed:dict[str,object])->TestClient:
    def override():yield db
    app.dependency_overrides[get_db]=override;admin=seed["admin"];client=TestClient(app);client.headers["Authorization"]=f"Bearer {create_access_token(str(admin.id))}";return client
