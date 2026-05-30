
import sys
import os
import datetime

# Add the backend directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db.session import SessionLocal
from app.db.models import TechnicalSignal, PaperPosition, Stock

def check_db():
    db = SessionLocal()
    try:
        # Check Nifty signal
        nifty_signal = db.query(TechnicalSignal).filter_by(symbol="^NSEI").order_by(TechnicalSignal.date.desc()).first()
        if nifty_signal:
            print(f"Nifty Signal found for {nifty_signal.date}: is_bullish={nifty_signal.is_bullish}")
        else:
            print("Nifty Signal NOT found in TechnicalSignal table")

        # Check any paper positions
        pending = db.query(PaperPosition).filter_by(status="pending").count()
        open_pos = db.query(PaperPosition).filter_by(status="open").count()
        closed = db.query(PaperPosition).filter_by(status="closed").count()
        print(f"Paper Positions: Pending={pending}, Open={open_pos}, Closed={closed}")

        # Check latest signals in DB
        latest_date = db.query(TechnicalSignal.date).order_by(TechnicalSignal.date.desc()).first()
        if latest_date:
            print(f"Latest Signal Date in DB: {latest_date[0]}")
            count = db.query(TechnicalSignal).filter_by(date=latest_date[0]).count()
            print(f"Signals for {latest_date[0]}: {count}")

    finally:
        db.close()

if __name__ == "__main__":
    check_db()
