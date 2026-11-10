"""customer tax id, sale customer snapshot, payment details

SAL-13: every customer has a NIT/CUI; missing ones become CF.
SAL-10: sales keep the customer's name and NIT/CUI for the receipt.
SAL-11 / SAL-12: card and transfer payment details.

Revision ID: a22d9c1819c1
Revises: 7f397430a1c6
Create Date: 2026-11-10 17:34:45.539590
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.sales import PAYMENT_DETAIL_CHECKS

revision: str = "a22d9c1819c1"
down_revision: str | None = "7f397430a1c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Customers: normalize NIT/CUI, missing → CF, unique only for real numbers.
    op.execute(
        "UPDATE customers SET document_id = COALESCE("
        "NULLIF(upper(regexp_replace(document_id, '[[:space:]-]', '', 'g')), ''), 'CF')"
    )
    op.drop_constraint(op.f("uq_customers_document_id"), "customers", type_="unique")
    op.alter_column(
        "customers",
        "document_id",
        existing_type=sa.String(length=30),
        nullable=False,
        server_default="CF",
    )
    op.create_index(
        "uq_customers_document_id_not_cf",
        "customers",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("document_id <> 'CF'"),
    )

    # Sales: customer snapshot for the receipt.
    op.add_column(
        "sales",
        sa.Column(
            "customer_name",
            sa.String(length=160),
            server_default="Consumidor Final",
            nullable=False,
        ),
    )
    op.add_column(
        "sales",
        sa.Column("customer_tax_id", sa.String(length=30), server_default="CF", nullable=False),
    )
    # One-time backfill of past sales that had a customer. Sales are immutable
    # (SAL-5), so the guard trigger is paused only for this schema change.
    op.execute("ALTER TABLE sales DISABLE TRIGGER trg_sales_immutable")
    op.execute(
        "UPDATE sales SET customer_name = c.full_name, customer_tax_id = c.document_id "
        "FROM customers c WHERE c.id = sales.customer_id"
    )
    op.execute("ALTER TABLE sales ENABLE TRIGGER trg_sales_immutable")

    # Payments: card / transfer details. NOT VALID keeps payments recorded
    # before these rules untouched while enforcing them for every new row.
    op.add_column("payments", sa.Column("card_type", sa.String(length=30), nullable=True))
    op.add_column("payments", sa.Column("card_last4", sa.String(length=4), nullable=True))
    op.add_column("payments", sa.Column("bank_name", sa.String(length=80), nullable=True))
    op.create_check_constraint(
        op.f("ck_payments_cardtype"), "payments", "card_type IN ('visa', 'mastercard', 'amex')"
    )
    for name, sql in PAYMENT_DETAIL_CHECKS.items():
        op.execute(
            f"ALTER TABLE payments ADD CONSTRAINT ck_payments_{name} CHECK ({sql}) NOT VALID"
        )


def downgrade() -> None:
    for name in PAYMENT_DETAIL_CHECKS:
        op.drop_constraint(op.f(f"ck_payments_{name}"), "payments", type_="check")
    op.drop_constraint(op.f("ck_payments_cardtype"), "payments", type_="check")
    op.drop_column("payments", "bank_name")
    op.drop_column("payments", "card_last4")
    op.drop_column("payments", "card_type")
    op.drop_column("sales", "customer_tax_id")
    op.drop_column("sales", "customer_name")
    op.drop_index("uq_customers_document_id_not_cf", table_name="customers")
    op.alter_column(
        "customers",
        "document_id",
        existing_type=sa.String(length=30),
        nullable=True,
        server_default=None,
    )
    op.create_unique_constraint(op.f("uq_customers_document_id"), "customers", ["document_id"])
