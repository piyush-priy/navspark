from pydantic import BaseModel
from typing import Optional


class NAOrder(BaseModel):
    survey_number: Optional[str]
    land_area: Optional[str]
    owner_name: Optional[str]
    order_date: Optional[str]
    company_name: Optional[str]