"""phase 1 core master data

Revision ID: 20260828_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260828_0001"; down_revision = None; branch_labels = None; depends_on = None
user_role = postgresql.ENUM("ADMIN", "MANAGER", "INBOUND", "OUTBOUND", "WAREHOUSE", "VIEWER", name="user_role", create_type=False)

def timestamps(): return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]

def upgrade() -> None:
    user_role.create(op.get_bind(), checkfirst=True)
    op.create_table("users", sa.Column("id",sa.Integer(),primary_key=True),sa.Column("username",sa.String(50),nullable=False),sa.Column("display_name",sa.String(100),nullable=False),sa.Column("email",sa.String(255),nullable=False),sa.Column("password_hash",sa.String(255),nullable=False),sa.Column("role",user_role,nullable=False),sa.Column("is_active",sa.Boolean(),server_default="true",nullable=False),*timestamps());op.create_index("ix_users_username","users",["username"],unique=True);op.create_index("ix_users_email","users",["email"],unique=True)
    op.create_table("customers",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("customer_code",sa.String(50),nullable=False),sa.Column("customer_name",sa.String(200),nullable=False),sa.Column("contact_name",sa.String(100)),sa.Column("phone",sa.String(30)),sa.Column("email",sa.String(255)),sa.Column("remark",sa.Text()),sa.Column("is_active",sa.Boolean(),server_default="true",nullable=False),*timestamps());op.create_index("ix_customers_customer_code","customers",["customer_code"],unique=True);op.create_index("ix_customers_customer_name","customers",["customer_name"])
    op.create_table("warehouses",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("warehouse_code",sa.String(50),nullable=False),sa.Column("warehouse_name",sa.String(200),nullable=False),sa.Column("address",sa.Text(),nullable=False),sa.Column("city",sa.String(100),nullable=False),sa.Column("state",sa.String(50),nullable=False),sa.Column("zip_code",sa.String(20),nullable=False),sa.Column("country",sa.String(2),server_default="US",nullable=False),sa.Column("is_active",sa.Boolean(),server_default="true",nullable=False),*timestamps());op.create_index("ix_warehouses_warehouse_code","warehouses",["warehouse_code"],unique=True)
    op.create_table("warehouse_areas",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("warehouse_id",sa.Integer(),sa.ForeignKey("warehouses.id",ondelete="CASCADE"),nullable=False),sa.Column("area_code",sa.String(50),nullable=False),sa.Column("area_name",sa.String(100),nullable=False),sa.Column("is_active",sa.Boolean(),server_default="true",nullable=False),*timestamps(),sa.UniqueConstraint("warehouse_id","area_code",name="uq_warehouse_area_code"));op.create_index("ix_warehouse_areas_warehouse_id","warehouse_areas",["warehouse_id"])
    op.create_table("warehouse_locations",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("warehouse_id",sa.Integer(),sa.ForeignKey("warehouses.id",ondelete="CASCADE"),nullable=False),sa.Column("area_id",sa.Integer(),sa.ForeignKey("warehouse_areas.id",ondelete="RESTRICT"),nullable=False),sa.Column("location_code",sa.String(50),nullable=False),sa.Column("location_name",sa.String(100),nullable=False),sa.Column("is_active",sa.Boolean(),server_default="true",nullable=False),*timestamps(),sa.UniqueConstraint("warehouse_id","location_code",name="uq_warehouse_location_code"));op.create_index("ix_warehouse_locations_warehouse_id","warehouse_locations",["warehouse_id"]);op.create_index("ix_warehouse_locations_area_id","warehouse_locations",["area_id"]);op.create_index("ix_warehouse_locations_location_code","warehouse_locations",["location_code"])
    op.create_table("carriers",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("carrier_code",sa.String(50),nullable=False),sa.Column("carrier_name",sa.String(200),nullable=False),sa.Column("scac",sa.String(10),unique=True),sa.Column("contact_name",sa.String(100)),sa.Column("phone",sa.String(30)),sa.Column("email",sa.String(255)),sa.Column("remark",sa.Text()),sa.Column("is_active",sa.Boolean(),server_default="true",nullable=False),*timestamps());op.create_index("ix_carriers_carrier_code","carriers",["carrier_code"],unique=True);op.create_index("ix_carriers_carrier_name","carriers",["carrier_name"])
    op.create_table("amazon_fc_addresses",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("fc_code",sa.String(20),nullable=False),sa.Column("fc_name",sa.String(200)),sa.Column("address_line1",sa.String(255),nullable=False),sa.Column("address_line2",sa.String(255)),sa.Column("city",sa.String(100),nullable=False),sa.Column("state",sa.String(50),nullable=False),sa.Column("zip_code",sa.String(20),nullable=False),sa.Column("country",sa.String(2),server_default="US",nullable=False),sa.Column("is_active",sa.Boolean(),server_default="true",nullable=False),*timestamps());op.create_index("ix_amazon_fc_addresses_fc_code","amazon_fc_addresses",["fc_code"],unique=True)

def downgrade() -> None:
    for table in ["amazon_fc_addresses","carriers","warehouse_locations","warehouse_areas","warehouses","customers","users"]: op.drop_table(table)
    user_role.drop(op.get_bind(), checkfirst=True)
