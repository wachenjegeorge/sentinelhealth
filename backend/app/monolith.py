from fastapi import FastAPI
from app.modules.aggregator import service as aggregator_service
from app.modules.ingestion import service as ingestion_service
from app.modules.risk_engine import service as risk_service

app = FastAPI(title="SentinelHealth Monolith", version="0.1.0")


@app.get("/health")
async def health():
    return {"status":"ok","service":"monolith",
            "modules":["ingestion","risk_engine","aggregator"]}
