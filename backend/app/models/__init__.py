from app.db import ddl
from app.db.base import Base
from app.models.audit import AuditLog
from app.models.catalog import ActiveIngredient, Category, Product, ProductIngredient
from app.models.inventory import Lot, MovementType, StockMovement
from app.models.user import Role, User

ddl.install(Base.metadata)

# Registers the audit trail listener for every session (rule 20).
from app.services import audit as _audit  # noqa: E402, F401

__all__ = [
    "ActiveIngredient",
    "AuditLog",
    "Base",
    "Category",
    "Lot",
    "MovementType",
    "Product",
    "ProductIngredient",
    "Role",
    "StockMovement",
    "User",
]
