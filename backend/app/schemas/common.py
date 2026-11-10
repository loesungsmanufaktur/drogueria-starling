from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# SAL-1: money is Decimal with 2 decimal places, never float.
Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
