from fastapi import APIRouter

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("/latest")
async def get_latest_report():
    return {"report": {}}
