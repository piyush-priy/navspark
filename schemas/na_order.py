from pydantic import BaseModel
from typing import Optional


class NAOrder(BaseModel):
    survey_number: Optional[str]
    village: Optional[str]
    area_in_na_order: Optional[str]
    dated: Optional[str]
    na_order_no: Optional[str]

    # Legacy compatibility fields (kept so older flows do not break).
    land_area: Optional[str]
    owner_name: Optional[str]
    order_date: Optional[str]
    company_name: Optional[str]