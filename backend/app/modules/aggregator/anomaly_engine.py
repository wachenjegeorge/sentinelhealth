"""Autonomous Anomaly Detection Engine."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

async def scan_for_anomalies(session: AsyncSession, facility_id: str, county: str) -> int:
    """Scans recent logs and creates autonomous alerts if spikes are detected."""
    
    # 1. Look for fatigue/heat spikes in the last 4 hours
    # We aggregate by department and shift
    spikes = (await session.execute(text("""
        SELECT department, shift,
               count(*) as n,
               avg(fatigue) as avg_fatigue,
               avg(heat_exposure) as avg_heat,
               count(*) FILTER (WHERE fatigue >= 8) as high_fatigue_count,
               count(*) FILTER (WHERE heat_exposure >= 8) as high_heat_count
        FROM logs
        WHERE created_at >= now() - interval '4 hours'
        GROUP BY department, shift
        HAVING count(*) >= 3 -- need at least 3 reports to trigger
    """))).mappings().all()

    alerts_created = 0

    for row in spikes:
        # Determine if it's an anomaly
        is_fatigue_spike = row["high_fatigue_count"] >= 3
        is_heat_spike = row["high_heat_count"] >= 3

        if not is_fatigue_spike and not is_heat_spike:
            continue

        alert_type = "fatigue_spike" if is_fatigue_spike else "heat_strain"
        
        # Check if an active alert already exists for this group to avoid duplicates
        existing = (await session.execute(text("""
            SELECT 1 FROM autonomous_alerts
            WHERE facility_id = :f AND department = :d AND shift = :s
              AND alert_type = :t AND status = 'active'
        """), {"f": facility_id, "d": row["department"], "s": row["shift"], "t": alert_type})).scalar()

        if existing:
            continue

        # Generate deterministic AI protocol based on the alert type
        if alert_type == "heat_strain":
            protocol = "Deploy immediate hydration station. Enforce 15-min shaded rest breaks every hour. Check ventilation."
        else:
            protocol = "Mandate fatigue recovery breaks. Review shift roster for consecutive night shifts. Offer counselling."

        # Insert the alert
        await session.execute(text("""
            INSERT INTO autonomous_alerts
                (facility_id, county, department, shift, alert_type, severity, details, ai_protocol)
            VALUES
                (:f, :c, :d, :s, :t, 'critical', :details, :protocol)
        """), {
            "f": facility_id, "c": county, "d": row["department"], "s": row["shift"],
            "t": alert_type,
            "details": f'{{"reports": {row["n"]}, "avg_fatigue": {row["avg_fatigue"]}, "avg_heat": {row["avg_heat"]}}}',
            "protocol": protocol
        })
        alerts_created += 1

    return alerts_created
