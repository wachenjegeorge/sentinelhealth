# SentinelHealth Kenya

**Workforce health early-warning for Kenya's healthcare system.**

**Live demo:** https://sentinelhealth.onrender.com
**Demo video:** LINK_TO_BE_ADDED
**Test accounts:** `test-worker` · `test-dept-head` · `test-head` · `test-officer` · `sentinel`
**Password for all:** `TestPass2026!`

---

## The problem, in 30 seconds

Kenya's healthcare workforce operates under structural strain. Core personnel density is **15.6 per 10,000** against the WHO threshold of **23**. Only **6 of 47 counties** meet the threshold. Heat exposure in kitchens and laundries, night-shift fatigue in ICU and ED, and respiratory clusters in TB wards become avoidable medical emergencies because **the signals are never aggregated early enough**.

Kenya's Digital Health Act (2023) mandates audit trails, encryption, and access control. But no operational tool today connects a night-shift ICU nurse's fatigue report to a department head's decision to reallocate staff to a county officer's escalation to the National MOH — with privacy enforced at the database layer.

**SentinelHealth does.**

---

## What it does

A worker's wellness check-in triggers a chain across five roles. Each role sees its own dashboard with its own AI lens on the same underlying data:

1. **Worker check-in** — fatigue 9, heat 9, ICU night shift
2. **Risk engine** scores it Critical (74/100) deterministically
3. **Department Head** sees the check-in in an AI-triaged confirmation queue
4. **Hospital Head** sees the department spike and clicks for a 4-section AI strategy
5. **County Officer** sees the aggregate across 47 facilities with 7-day forecast
6. **National Admin** sees systemic patterns and drafts policy-grade escalation

---

## What's actually working today

Every feature below is deployed and functional. Every button does something real.

### Worker dashboard (`/worker`)
- Daily wellness check-in: fatigue, heat, hours, symptoms (8 flags)
- Deterministic risk score → Critical / Moderate / Low, with component breakdown
- Personal AI Health Coach reads last 7 check-ins, offers one action
- Predictive early-warning banner (fatigue >=8 AND sleep <6h, OR heat >=8 AND fatigue >=7)
- Wearable sync (steps, sleep, kcal), upcoming roster, shift change requests
- Medical history (RLS-scoped so only that worker sees their own rows)

### Department Head (`/dept-head`)
- **Confirmation queue** — every high-risk check-in routed for human review
- **AI Triage** — one click analyzes pending reports, returns verdict per report: `likely_real`, `outlier`, or `uncertain`, with reasoning
- **AI Deep Report** — 5-section strategic analysis (Executive Summary / Team Health / Verification Insights / Risk Drivers / Prescriptive Actions)
- **Anomaly Triage** — active spikes: acknowledge, dismiss as false positive, or escalate to hospital head
- **Predictive Roster** — schedule shifts for workers in your department
- 30-day trend chart with hover tooltips

### Hospital Head (`/admin`)
- **Clickable department cards** showing WVI, report count, shift coverage
- **Click any department** → 4-section AI analysis (Situation / Top 3 Actions / Escalation / Watchouts)
- **AI is role-aware:** hospital head lens = staff reallocation, cross-department impact, escalation decisions
- **AI Strategic Brief** with 4 KPI cards, scoped to their facility only
- **Generate Action Plan** — 5-section comprehensive plan via LLM
- **Schedule shifts** with department-to-worker filtering

### County Officer (`/admin`)
- County-scoped aggregate (RLS guarantees they only see their county)
- **AI Strategic Brief** — top 5 facilities by WVI, priority ranking, 3 actions this week, escalation decision
- **7-day WVI forecast** — linear projection from last 14 days + peer comparison vs national median
- **County Intelligence Center** (`/admin/intel/{county}`) — 4-tab deep dive: risk distribution, facility table, 30-day trends + anomalies, AI-generated 5-section report
- **Facility deep-dive** — click any facility → department breakdown → send recommendation to that hospital head
- **Export CSV** — 5000-row data export

### National Admin (`/admin`)
- All 47 counties aggregated
- Same dashboards at national scope
- Approval queue for pending county officers

### All roles
- Glassmorphism UI (animated mesh gradient, frosted cards, cursor glow)
- Floating AI chat widget on every authenticated page
- Role-aware prompts — same LLM, different system prompt per role
- Session-based auth with JWT (12h expiry)

---

## Technical depth

For engineers evaluating whether this is real:

### Row-Level Security (FORCE)

Every tenant table has `ALTER TABLE ... FORCE ROW LEVEL SECURITY`. Three DB roles:

- `app_user` — `NOBYPASSRLS`, RLS-enforced reads and writes. **This is the runtime role.**
- `sentinel_admin` — `BYPASSRLS`, read-only, for exports and audit
- `neondb_owner` — migrations only

A bug in any single route cannot leak cross-tenant data because the DB refuses the query. Verified by `test_rls_blocks_cross_tenant_reads`.

### K-anonymity >= 5 at the SQL layer

The `agg_logs` view has `HAVING count(*) >= 5`. Any group with fewer than 5 verified reporters does not exist as queryable data. No application bug can leak it. Verified by `test_k_anonymity_threshold`.

### HMAC-SHA256 worker ID hashing

Raw worker IDs are hashed with a server-side pepper before any database write. `worker_id_hash` is 64 hex characters. The pepper lives only in the app environment. Individual check-ins cannot be re-linked to a person without it.

### Hash-chained audit log

Every state change writes to `audit` with `prev_hash -> self_hash`. `app_user` has INSERT only — no UPDATE, no DELETE. Tamper-evident, aligned with Kenya Digital Health Act 2023 audit requirements.

### Idempotency

Every write endpoint requires an `Idempotency-Key` header. The ledger uses `INSERT ON CONFLICT DO NOTHING RETURNING id` for atomic claim — exactly-once semantics without SERIALIZABLE isolation. Same key -> same response, one row. Verified by `test_same_key_returns_same_response`.

### Three-layer AI

When the LLM is down or hallucinating, the system does not crash. Three layers, in order:

1. **Groq LLM** (openai/gpt-oss-120b via Groq, model fallback chain to qwen/llama) with 6 read-only tool schemas
2. **Deterministic intent router** — 100% uptime, no LLM required, strict clinical rules
3. **Verifier** — every numeric claim and every county name in the LLM output must appear in a tool result, else the response is rejected and the deterministic layer takes over

### Role-aware AI

Same department, three different lenses:

- `hospital_head` -> "reallocate 2 nurses from Maternity to ICU tonight"
- `county_officer` -> "your facility is +12 above peer median"
- `admin` -> "systemic pattern across 4 counties, propose national staffing policy"

One prompt template, three role filters.

### KEPH-aware

All 1,126 facilities are seeded across KEPH Levels 1-6. Department dropdowns filter by KEPH level (a Level 2 clinic cannot select ICU). Department head registration is blocked at KEPH levels that have no department structure.

### Anomaly engine

Scans last 4 hours for fatigue/heat spikes (min 3 reports per dept x shift). Creates autonomous alerts with deterministic AI protocol. Multi-tier triage: dept head -> hospital head -> county officer -> admin, with escalation chain recorded in JSONB.

---

## The privacy invariants, tested

Every PR that touches the privacy layer must pass:

    docker compose exec monolith pytest tests/ -v

Expected output:

    tests/test_acid.py::test_failed_work_leaves_no_trace             PASSED
    tests/test_dept_head_workflow.py::test_high_risk_checkin_lands_in_queue PASSED
    tests/test_dept_head_workflow.py::test_low_risk_checkin_skips_queue PASSED
    tests/test_dept_head_workflow.py::test_confirm_updates_both_tables PASSED
    tests/test_dept_head_workflow.py::test_k_anonymity_threshold     PASSED
    tests/test_dept_head_workflow.py::test_alert_triage_acknowledge  PASSED
    tests/test_idempotency.py::test_same_key_returns_same_response   PASSED
    tests/test_rls.py::test_rls_blocks_cross_tenant_reads            PASSED
    tests/test_rls.py::test_rls_requires_tenant_set                  PASSED
    ================= 9 passed =================

The five privacy invariants (non-negotiable):

1. Raw worker IDs are never written to any column
2. Admin endpoints never return `worker_id_hash` or individual log IDs
3. Any aggregate with fewer than 5 reporters is suppressed at SQL layer
4. Audit log is append-only, no UPDATE, no DELETE
5. The assistant's SQL tool may only SELECT from `agg_logs`

---

## Architecture

Browser (PWA shell, offline-capable via sw.js)
  |
  | HTTPS + JWT
  v
BFF (port 8000)          auth, rate-limit, idempotency-key enforcement
  |
  | private network
  v
Monolith (port 8001)     ingestion, risk_engine, aggregator, assistant
  |
  v
PostgreSQL 16 (Neon)
  app_user          writes, RLS enforced
  sentinel_admin    reads, BYPASSRLS
  neondb_owner      migrations only

Stack:

- **Framework:** FastAPI + SQLAlchemy 2.0 (asyncpg) + Alembic
- **LLM:** Groq (openai/gpt-oss-120b fallback chain)
- **Deployment:** Render (Docker) + Neon Postgres 16
- **Frontend:** Vanilla JS + Tailwind CDN + glassmorphism CSS layer

---

## Kenya data model

- **47 counties** with county referral hospitals seeded
- **KEPH Levels 1-6** (Community Health Unit -> National Tertiary)
- **Department taxonomy per level** — a Level 4 Sub-County Hospital cannot have an ICU
- **MOH HRH Strategy 2024** staffing density data (nurses 10.1/10k, clinical officers 3.2/10k, doctors 0.89/10k)
- **Kenya MoH National Guidelines on Workplace Mental Wellness (Oct 2024)** in the clinical knowledge base

---

## Compliance

- **Kenya Digital Health Act (2023)** — audit, encryption, access control
- **Kenya Digital Health (Health Information Management Procedures) Regulations (2025)**
- **Kenya Data Protection Act (2019)** — lawfulness, minimisation, accuracy
- **ISO 27799** — Health informatics security management

Worker accounts support soft-delete with PII purge (right to erasure). Data retention window is 30 days before hard delete.

---

## Running locally

    git clone https://github.com/wachenjegeorge/sentinelhealth.git
    cd sentinelhealth
    cp .env.example .env
    # fill in DATABASE_URL_* (app_user, sentinel_admin, neondb_owner), JWT_SECRET, WORKER_ID_PEPPER
    docker compose up --build -d
    sleep 20
    curl http://localhost:8000/health

Requires Docker Desktop and a Postgres 16 instance (local or Neon).

---

## Roadmap

| Phase | Status |
|---|---|
| Day 1 — RLS, idempotency, ACID, tests | shipped |
| Day 2 — 47 counties, worker form, dept-head queue | shipped |
| Day 3 — Assistant (3-layer + tools + role-aware) | shipped |
| Day 4 — KEPH, facility registry, compliance page | shipped |
| Day 5 — Test suite expansion, Render deploy | shipped |
| v2 — SMS/USSD worker interface for offline rural workers | planned |
| v2 — Swahili LLM for local-language check-ins | planned |
| v2 — Integration with DHIS2 for national surveillance | planned |

---

## License

MIT. See LICENSE.

Built for Kenya healthcare workers, by developers who believe the system fails them at the data layer, not the clinical one.

