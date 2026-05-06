from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import stocks, screener, reports

app = FastAPI(title="Stock AI API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router)
app.include_router(screener.router)
app.include_router(reports.router)

@app.get("/")
async def root():
    return {"message": "Stock AI API is running", "status": "healthy"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}
