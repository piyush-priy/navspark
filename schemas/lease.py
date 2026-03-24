from pydantic import BaseModel
from typing import Optional


class LeaseRecord(BaseModel):
    survey_number: Optional[str]
    lease_deed_doc_no: Optional[str]
    lease_area: Optional[str]
    lease_start: Optional[str]

    # Legacy compatibility fields (kept so older flows do not break).
    land_area: Optional[str]
    owner_name: Optional[str]
    lease_start_date: Optional[str]
    lease_duration: Optional[str]
    company_name: Optional[str]