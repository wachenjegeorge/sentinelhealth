from fastapi import FastAPI
from app.bff.middleware import TenantMiddleware
from app.bff.routes_admin import router as admin_router
from app.bff.routes_sync import router as sync_router
from app.bff.routes_worker import router as worker_router

app = FastAPI(title="SentinelHealth BFF", version="0.1.0")
app.add_middleware(TenantMiddleware)
app.include_router(worker_router)
app.include_router(sync_router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status":"ok","service":"bff"}
