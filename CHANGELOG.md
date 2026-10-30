# Changelog

All notable changes to this project are documented here.

## [Unreleased]

### Planned

- Day 2: 47-county seed, worker form, admin dashboard on live data
- Day 3: Local LLM assistant with tool calling
- Day 4: KEPH guide, facility registry, compliance page
- Day 5: Test suite expansion, Fly.io deployment, demo video

## [0.1.0] - 2026-10-30

### Added - Day 1 foundation

Infrastructure:

- Docker Compose stack: PostgreSQL 16, FastAPI BFF, FastAPI monolith
- Alembic migration system with prepend_sys_path fix for container paths
- Environment-based configuration via pydantic-settings

Database:

- logs table with HMAC-hashed worker IDs and composite indexes
- idempotency_ledger for exactly-once writes across retries
- upload_sessions for offline-first client state
- audit append-only hash-chained table
- agg_logs view with HAVING count(*) >= 5 (k-anonymity at SQL layer)
- Row-Level Security forced on all four tenant tables
- Three roles: sentinel (migrations), app_user (RLS), sentinel_admin
  (BYPASSRLS reads)

Application:

- BFF at port 8000 with TenantMiddleware (JWT, idempotency-key enforcement)
- Monolith at port 8001 (private, modular: ingestion, risk_engine, aggregator)
- HMAC-SHA256 worker ID hashing
- Deterministic risk engine with five weighted components
- Atomic idempotency via INSERT ON CONFLICT DO NOTHING RETURNING
- Audit log with hash chain (prev_hash to self_hash)

Tests:

- test_rls_blocks_cross_tenant_reads - cross-tenant isolation
- test_rls_requires_tenant_set - enforcement when tenant not set
- test_same_key_returns_same_response - idempotency
- test_failed_work_leaves_no_trace - ACID rollback

### Fixed

- after_begin listener originally attached to async_sessionmaker (a factory)
  rather than sqlalchemy.orm.Session (the class)
- SET TRANSACTION ISOLATION LEVEL rejected after set_config, removed
  (unnecessary with atomic ON CONFLICT)
- permission denied for sequence audit_id_seq, added GRANT USAGE ON ALL
  SEQUENCES
- permission denied for table logs from sentinel_admin, added GRANT SELECT
  on underlying tables (views check caller privileges)
- Login endpoint was unreachable because it required a token, added to BFF
  public path allowlist

### Security

- All tenant tables have RLS ENABLED and FORCED
- Audit append-only for app_user
- Permission matrix verified by test
