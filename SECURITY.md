# Security Policy

SentinelHealth handles healthcare workforce health data. Security and privacy
are design constraints, not add-ons.

## Reporting a vulnerability

Do not open a public GitHub issue for security vulnerabilities. Email
security@sentinelhealth.example with:

- Description of the issue
- Steps to reproduce
- Potential impact
- Suggested mitigation

You will receive a response within 72 hours.

## Security model

### Identity

- Worker IDs are HMAC-SHA256 hashed with a server-side pepper
  (WORKER_ID_PEPPER) before any database write.
- Raw worker IDs never leave the BFF process.
- JWT tokens are HS256, 12-hour expiry, issued only by
  /api/bff/worker/login.

### Authorization

Three database roles enforce separation:

| Role | Access | Used by |
|------|--------|---------|
| sentinel | Superuser (DDL only) | Alembic migrations |
| app_user | RLS-enforced reads and writes | BFF application engine |
| sentinel_admin | Read-only, BYPASSRLS | Aggregator, audit exports |

No code path uses sentinel outside of migrations. Verified by
tests/test_permissions.py.

### Privacy

- Row-Level Security is ENABLED and FORCED on every tenant table. Even the
  table owner is subject to policies.
- K-anonymity >= 5 is enforced at the SQL layer via HAVING count(*) >= 5 on
  the agg_logs view. Cells with fewer than 5 reporters do not exist as
  queryable data.
- Audit log is append-only and hash-chained. app_user has INSERT only, no
  SELECT, no UPDATE, no DELETE.

### Data in transit

- TLS everywhere in production (Fly.io automatic on *.fly.dev).
- The Docker internal network is not exposed for the monolith.

## Compliance references

- Kenya Digital Health Act 2023 (audit, encryption, access control)
- Kenya Digital Health (Health Information Management Procedures)
  Regulations, 2025
- ISO 27799 (health informatics security management)

## Known limitations

- Development mode only: PgBouncer trust auth when reintroduced on Day 4.
  Production must use scram-sha-256.
- No rate limiting yet. Added on Day 5 via the BFF middleware.
- No LLM safety layer yet. When the assistant is added on Day 3, it is gated
  by role-based tool allowlists.
