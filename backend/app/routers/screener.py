from fastapi import APIRouter

router = APIRouter(prefix="/api/screener", tags=["screener"])


@router.get("/top")
async def get_top_stocks():
    return {"top_stocks": []}


@router.post("/run")
async def run_screener():
    return {"message": "Screener run initiated", "job_id": "placeholder-id"}
