from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from app.db import with_tenant

router = APIRouter(prefix="/api/bff/telemetry", tags=["telemetry"])

class TelemetryPayload(BaseModel):
    temp_c: float = Field(ge=-10, le=50)
    humidity: float = Field(ge=0, le=100)
    sensor_id: str

@router.post("/ingest")
async def ingest_telemetry(payload: TelemetryPayload, request: Request):
    """Endpoint for external IoT sensors to push data."""
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role="health_officer", user_id=claims["sub"]) as session:
        # In a real app, we would save this to a time-series DB like TimescaleDB or InfluxDB.
        # For this prototype, we just log it to the audit trail so it shows up.
        await session.execute(text("""
            INSERT INTO audit (facility_id, actor, role, action, resource, detail, prev_hash, self_hash)
            VALUES (:f, :a, 'iot_sensor', 'telemetry.ingest', :r, :d, '0', '0')
        """), {
            "f": claims["facility_id"], "a": payload.sensor_id, "r": f"sensor/{payload.sensor_id}",
            "d": f'{{"temp": {payload.temp_c}, "humidity": {payload.humidity}}}'
        })
    return {"ok": True, "message": "Telemetry ingested"}
