# SentinelHealth Kenya

Population and Workforce Health Early Warning System for Kenyan healthcare providers.

Status: Day 1 complete. Verified end-to-end on Docker Compose.

## The problem

Kenya's healthcare workforce operates under structural strain. Core personnel
density is 15.6 per 10,000 against the WHO threshold of 23. Only 6 of 47
counties meet the norm. Heat exposure in kitchens and laundries, night-shift
fatigue in ICU and ED, and respiratory clusters in TB wards become avoidable
medical emergencies because the signals are never aggregated early enough.

SentinelHealth ingests worker wellness check-ins, correlates them with
environmental and workforce-pressure signals, and surfaces aggregated risk to
facility and county health officers before incidents escalate.

## What works today

- Worker check-in API with HMAC-hashed worker IDs (raw IDs never stored)
- Deterministic risk engine producing a 0-100 score per check-in
- Idempotent writes for unreliable networks (same key, same response, one row)
- ACID rollback guarantees verified by test
- Row-Level Security enforced and forced on all tenant tables
- Append-only hash-chained audit log
- K-anonymity >= 5 enforced at the SQL aggregation layer
- Aggregated overview endpoint for health officers
- Full permission matrix across three roles

## Architecture

    Client (offline-first PWA, days 3-4)
        |
        v  HTTPS + JWT
    BFF (public port 8000)          auth, rate-limit, idempotency
        |
        v  private network
    Monolith (port 8001)            ingestion, risk_engine, aggregator
        |
        v
    PostgreSQL 16                   RLS FORCED on every tenant table
        app_user       -> writes, RLS enforced
        sentinel_admin -> reads, BYPASSRLS
        sentinel       -> migrations

## Quick start

Requires Docker Desktop and Git Bash (or any POSIX shell).

    git clone https://github.com/YOUR_USERNAME/sentinelhealth-ke.git
    cd sentinelhealth-ke
    cp .env.example .env
    docker compose up --build -d
    sleep 20
    curl -s http://localhost:8000/health
    # {"status":"ok","service":"bff"}

Full round-trip (submit a check-in):

    TOKEN=$(curl -s -X POST http://localhost:8000/api/bff/worker/login \\
      -H "Content-Type: application/json" \\
      -d '{"worker_id":"W-DEMO-1","facility_id":"mombasa-cgtrh","role":"worker"}' \\
      | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

    curl -s -X POST http://localhost:8000/api/bff/sync/checkins \\
      -H "Authorization: Bearer $TOKEN" \\
      -H "Idempotency-Key: $(python -c 'import uuid;print(uuid.uuid4().hex)')" \\
      -H "Content-Type: application/json" \\
      -d '{"worker_id":"W-DEMO-1","department":"ICU","shift":"night","fatigue":9,"heat_exposure":7,"hours_worked":12,"symptoms":["headache","dizziness"]}'

## API

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | /health | none | Liveness |
| POST | /api/bff/worker/login | none | Issue JWT |
| POST | /api/bff/sync/checkins | bearer + Idempotency-Key | Submit wellness log |
| POST | /api/bff/sync/heartbeat | bearer | Keep upload session alive |
| GET | /api/bff/admin/overview | bearer (health_officer) | Aggregated WVI, k >= 5 |

## Testing

    docker compose exec monolith pytest -v

Expected: 4 passed. RLS isolation, RLS enforcement, idempotency, ACID rollback.

## Design decisions

Row-Level Security, forced. Every tenant table has FORCE ROW LEVEL SECURITY.
The application role app_user cannot see cross-tenant rows even if application
code forgets to filter. A missing SET LOCAL app.facility_id raises immediately.

Idempotency by atomic claim. INSERT ON CONFLICT DO NOTHING RETURNING id gives
exactly-one-execution semantics without SERIALIZABLE isolation. This is the
same pattern Stripe uses for payment idempotency.

K-anonymity in SQL, not Python. The agg_logs view has HAVING count(*) >= 5.
Cells with fewer than 5 reporters never exist in the view. No application bug
can leak them.

BFF shield. The BFF owns auth, idempotency-key enforcement, and response
shaping. The monolith is reachable only on the private Docker network.

Modular monolith. Modules (ingestion, risk_engine, aggregator) have service
interfaces. Extraction to a microservice is a folder move plus an HTTP client.

## Privacy and compliance

- Worker IDs are HMAC-SHA256 hashed with a server-side pepper before any
  database write.
- Admin endpoints never return individual records, only department/shift
  aggregates.
- Groups below 5 reporters are suppressed at the SQL layer.
- Audit log is append-only and hash-chained (prev_hash / self_hash).
- All traffic is TLS in production (Fly.io automatic).

Aligned with the Kenya Digital Health Act 2023 audit, encryption, and
access-control requirements.

## Kenya data model (Days 2-3)

- All 47 counties
- KEPH Levels 1-6 (Community Health Unit to National Tertiary)
- County referral hospitals, sub-county hospitals, health centres
- Healthcare departments: ED, ICU, maternity, paediatrics, OPD, lab,
  radiology, pharmacy, wards, community health, kitchen/laundry,
  waste/mortuary

## Roadmap

| Day | Focus | Deliverable |
|-----|-------|-------------|
| 1 | Foundation | RLS, idempotency, ACID, permissions (verified by 4 tests) |
| 2 | Data and UI | 47 counties, worker form, admin dashboard on live data |
| 3 | Assistant | Local LLM with tool calling, KB search, web search |
| 4 | Kenya-specific | KEPH guide, facility registry, compliance page |
| 5 | Polish | Test suite, README, demo video, Fly.io deployment |

## License

MIT. See LICENSE.
