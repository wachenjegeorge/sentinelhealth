import random
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from sqlalchemy import text
from app.db import with_tenant

router = APIRouter(prefix="/api/bff/worker/wearable", tags=["wearable"])

@router.post("/sync")
async def sync_wearable(request: Request):
    """Simulates syncing data from Apple Health / Google Fit."""
    claims = request.state.claims
    today = datetime.now(timezone.utc).date()
    
    # Generate realistic healthcare worker data
    steps = random.randint(8000, 16000)
    calories = int(steps * 0.045)
    sleep = round(random.uniform(4.5, 8.5), 1)
    active = random.randint(30, 90)

    async with with_tenant(claims["facility_id"], role="worker", user_id=claims["sub"]) as session:
        await session.execute(text("""
            INSERT INTO wearable_metrics (user_id, facility_id, metric_date, steps, calories_burned, sleep_hours, active_minutes)
            VALUES (:u, :f, :d, :s, :c, :sl, :a)
            ON CONFLICT (user_id, metric_date) DO UPDATE
            SET steps = EXCLUDED.steps, calories_burned = EXCLUDED.calories_burned,
                sleep_hours = EXCLUDED.sleep_hours, active_minutes = EXCLUDED.active_minutes,
                synced_at = now()
        """), {"u": claims["sub"], "f": claims["facility_id"], "d": today, "s": steps, "c": calories, "sl": sleep, "a": active})
        
    return {"ok": True, "steps": steps, "calories": calories, "sleep": sleep}

@router.post("/schedule/upload")
async def upload_schedule(request: Request):
    """Simulates parsing an uploaded HR roster and populating the schedule."""
    claims = request.state.claims
    async with with_tenant(claims["facility_id"], role="worker", user_id=claims["sub"]) as session:
        # Wipe existing upcoming and insert a fresh mock roster
        await session.execute(text("DELETE FROM worker_schedules WHERE user_id = :u AND start_time > now()"), {"u": claims["sub"]})
        
        # Insert 3 mock shifts
        await session.execute(text("""
            INSERT INTO worker_schedules (user_id, facility_id, department, shift_type, start_time, end_time, status)
            VALUES 
            (:u, :f, 'ICU / Critical Care', 'night', now() + interval '1 day', now() + interval '1 day 12 hours', 'scheduled'),
            (:u, :f, 'Emergency Department', 'day', now() + interval '3 days', now() + interval '3 days 12 hours', 'scheduled'),
            (:u, :f, 'ICU / Critical Care', 'night', now() + interval '5 days', now() + interval '5 days 12 hours', 'scheduled')
        """), {"u": claims["sub"], "f": claims["facility_id"]})
    return {"ok": True}
