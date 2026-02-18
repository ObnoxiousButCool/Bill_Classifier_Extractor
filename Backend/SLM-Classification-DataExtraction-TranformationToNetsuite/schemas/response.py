"""
Response schemas for API endpoints.
"""
from pydantic import BaseModel
from typing import Any, List, Optional
from datetime import datetime


class BillResponse(BaseModel):
    """Response schema for a single bill record."""
    bill_id: str
    bill_type: str
    bill_subtype: Optional[str] = None
    extracted_json: dict
    netsuite_json: dict
    tally_xml: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True  # Allows ORM mode for SQLAlchemy models


class BillListResponse(BaseModel):
    """Response schema for list of bills."""
    bills: List[BillResponse]
    count: int
