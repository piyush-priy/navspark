from pydantic import BaseModel
from typing import Optional


class NAOrder(BaseModel):
    survey_number: Optional[str]
    village: Optional[str]
    na_area: Optional[str]
    order_date: Optional[str]
    na_order_no: Optional[str]
