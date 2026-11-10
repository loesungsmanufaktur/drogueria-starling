from app.db import ddl
from app.db.base import Base
from app.models.alerts import Alert, AlertType
from app.models.audit import AuditLog
from app.models.catalog import ActiveIngredient, Category, Product, ProductIngredient
from app.models.customers import Customer, Prescription, PrescriptionItem
from app.models.inventory import Lot, MovementType, StockMovement
from app.models.purchasing import PurchaseOrder, PurchaseOrderLine, PurchaseStatus, Supplier
from app.models.sales import (
    Payment,
    PaymentMethod,
    Register,
    RegisterShift,
    Sale,
    SaleLine,
    SaleLineLot,
    SaleReturn,
    SaleReturnLine,
    SaleReturnLot,
    SaleVoid,
    ShiftStatus,
)
from app.models.user import Role, User

ddl.install(Base.metadata)

# Registers the audit trail listener for every session (rule 20).
from app.services import audit as _audit  # noqa: E402, F401

__all__ = [
    "ActiveIngredient",
    "Alert",
    "AlertType",
    "AuditLog",
    "Base",
    "Category",
    "Customer",
    "Lot",
    "MovementType",
    "Payment",
    "PaymentMethod",
    "Prescription",
    "PrescriptionItem",
    "Product",
    "ProductIngredient",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "PurchaseStatus",
    "Register",
    "RegisterShift",
    "Role",
    "Sale",
    "SaleLine",
    "SaleLineLot",
    "SaleReturn",
    "SaleReturnLine",
    "SaleReturnLot",
    "SaleVoid",
    "ShiftStatus",
    "StockMovement",
    "Supplier",
    "User",
]
