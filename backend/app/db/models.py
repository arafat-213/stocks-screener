from sqlalchemy import Column, String, Float, DateTime, PrimaryKeyConstraint, Text, Integer
from sqlalchemy.orm import declarative_base
import datetime
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
    date = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String)
    entry_score = Column(Float)
    rsi = Column(Float)
    macd = Column(Float)
    ema_signal = Column(String)
    volume_signal = Column(String)
    __table_args__ = (PrimaryKeyConstraint('date', 'symbol'),)

class FundamentalData(Base):
    __tablename__ = "fundamental_data"
    date = Column(DateTime, default=datetime.datetime.utcnow)
    symbol = Column(String)
    pe = Column(Float, nullable=True)
    pb = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    debt_equity = Column(Float, nullable=True)
    eps_growth = Column(Float, nullable=True)
    promoter_holding = Column(Float, nullable=True)
    __table_args__ = (PrimaryKeyConstraint('date', 'symbol'),)

class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    run_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String)
    stocks_fetched = Column(Integer)
    stocks_scored = Column(Integer)
    errors = Column(Text)
