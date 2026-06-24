import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class Watchlist(Base):
    __tablename__ = "watchlist"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, index=True, nullable=False)
    ticker = Column(String, index=True, nullable=False)
    
    # Scheduling parameters (APScheduler will read these)
    cron_hour = Column(Integer, nullable=True)
    cron_minute = Column(Integer, nullable=True)
    
    # Concurrency Lock Flag
    is_processing = Column(Boolean, default=False)
    last_error = Column(Text, nullable=True)

class FinancialReport(Base):
    __tablename__ = "financial_reports"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    ticker = Column(String(12), index=True, nullable=False)
    owner_id = Column(String, index=True, nullable=False)
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    
    # Optimized Storage: No raw HTML allowed, strictly Markdown and JSON numbers
    quantitative_metrics = Column(JSON, nullable=False) 
    markdown_content = Column(Text, nullable=False)     

class JobRun(Base):
    __tablename__ = "job_runs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, nullable=False)
    triggered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    status = Column(String, nullable=False) # e.g., "SUCCESS" or "FAILED"
    execution_time_ms = Column(Integer, nullable=True)
    error_log = Column(Text, nullable=True)