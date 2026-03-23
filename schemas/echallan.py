from pydantic import BaseModel
from typing import Optional


class EChallan(BaseModel):
    challan_number: Optional[str]
    vehicle_number: Optional[str]
    violation_date: Optional[str]
    amount: Optional[str]
    offence_description: Optional[str]
    payment_status: Optional[str]