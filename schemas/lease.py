from pydantic import BaseModel
from typing import Optional


class LeaseRecord(BaseModel):
    survey_number: Optional[str]
    village: Optional[str]
    lease_area: Optional[str]
    lease_start_date: Optional[str]
    lease_deed_doc_no: Optional[str]
