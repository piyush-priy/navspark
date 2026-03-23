from pydantic import BaseModel
from typing import Optional


class LeaseRecord(BaseModel):
    survey_number: Optional[str]
    land_area: Optional[str]
    owner_name: Optional[str]
    lease_start_date: Optional[str]
    lease_duration: Optional[str]
    company_name: Optional[str]