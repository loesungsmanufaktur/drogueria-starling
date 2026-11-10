from app.db import ddl
from app.db.base import Base

ddl.install(Base.metadata)

__all__ = ["Base"]
