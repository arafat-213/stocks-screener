from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class Stock(Base):
    __tablename__ = "stocks"
    symbol = Column(String, primary_key=True)
    name = Column(String)
    sector = Column(String)
    industry = Column(String)
    market_cap = Column(Float)

class DailyScore(Base):
    __tablename__ = "daily_scores"
    date = Column(DateTime, primary_key=True)
    symbol = Column(String, primary_key=True)
    entry_score = Column(Float)
    rsi = Column(Float)
    macd = Column(Float)
    ema_signal = Column(String)
    volume_signal = Column(String)

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=func.now())
    status = Column(String)  # idle / running / complete / failed / warning
    stocks_fetched = Column(Integer)
    stocks_scored = Column(Integer)
    errors = Column(Text)
