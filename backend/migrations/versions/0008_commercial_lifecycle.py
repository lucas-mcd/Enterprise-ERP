"""Cancel draft orders and record lost opportunities."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def states(table: str, name: str, column: str, values: str) -> None:
    op.drop_constraint(op.f(f"ck_{table}_{name}"), table, type_="check")
    op.create_check_constraint(
        op.f(f"ck_{table}_{name}"), table, f"{column} IN ({values})"
    )


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("normalized_name", sa.String(360), nullable=False),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "normalized_name"),
    )
    op.create_index("ix_suppliers_tenant_id", "suppliers", ["tenant_id"])
    op.add_column("business_orders", sa.Column("supplier_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_business_orders_tenant_id_suppliers",
        "business_orders",
        "suppliers",
        ["tenant_id", "supplier_id"],
        ["tenant_id", "id"],
    )
    op.add_column("crm_opportunities", sa.Column("loss_reason", sa.String(180)))
    states(
        "business_orders",
        "order_status",
        "status",
        "'draft','completed','aguardando_aprovacao','cancelled'",
    )
    states(
        "crm_opportunities",
        "valid_stage",
        "stage",
        "'prospeccao','proposta','negociacao','fechado','perdido'",
    )


def downgrade() -> None:
    # Reinstating the constraints fails atomically if newer states are in use.
    states(
        "business_orders",
        "order_status",
        "status",
        "'draft','completed','aguardando_aprovacao'",
    )
    states(
        "crm_opportunities",
        "valid_stage",
        "stage",
        "'prospeccao','proposta','negociacao','fechado'",
    )
    op.drop_column("crm_opportunities", "loss_reason")
    op.drop_constraint(
        "fk_business_orders_tenant_id_suppliers", "business_orders", type_="foreignkey"
    )
    op.drop_column("business_orders", "supplier_id")
    op.drop_table("suppliers")
