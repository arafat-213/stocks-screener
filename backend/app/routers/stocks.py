from fastapi import APIRouter

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

@router.get("/")
async def get_stocks():
    return {"stocks": []}

@router.get("/{symbol}")
async def get_stock_detail(symbol: str):
    return {"symbol": symbol}
