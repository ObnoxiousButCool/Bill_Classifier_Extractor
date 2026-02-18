"""
SQLAlchemy model for bill processing records.
"""
from sqlalchemy import Column, String, JSON, DateTime, Text
from sqlalchemy.sql import func
from core.database import Base


class Bill(Base):
    """
    Bill processing record model.
    Stores document classification results and extracted data in both formats.
    """
    __tablename__ = "bills"
    
    bill_id = Column(String(255), primary_key=True, index=True)
    bill_type = Column(String(50), nullable=False)  # "Invoice Bill" or "Expense Bill"
    bill_subtype = Column(String(50), nullable=True)  # Future extensibility
    extracted_json = Column(JSON, nullable=False)  # Generic format
    netsuite_json = Column(JSON, nullable=False)  # NetSuite API format
    tally_xml = Column(Text,nullable=False) # tally XML
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<Bill(bill_id='{self.bill_id}', bill_type='{self.bill_type}')>"
