# Contributing to SentinelHealth Kenya

## Getting started

1. Fork the repository
2. Clone your fork
3. Create a branch: git checkout -b feat/your-feature
4. Make changes
5. Run tests: docker compose exec monolith pytest -v
6. Commit: git commit -m "feat: your feature"
7. Push: git push origin feat/your-feature
8. Open a Pull Request

## Commit messages

Follow Conventional Commits: feat, fix, docs, test, refactor, chore.

## What to test

Every PR must include a test for the behavior it adds:

- New tenant tables: include an RLS test proving cross-tenant isolation
- New write endpoints: include an idempotency test
- New roles or grants: update tests/test_permissions.py expected matrix
- New aggregates: include a k-anonymity test
- New LLM tools: prove the tool dispatch respects role allowlists

## Privacy invariants, non-negotiable

1. Raw worker IDs must never be written to any database column
2. Admin endpoints must never return worker_id_hash or log_id
3. Any aggregate with fewer than 5 reporters must be suppressed
4. Audit log entries are append-only, no UPDATE, no DELETE, ever
5. The assistant's SQL tool may only SELECT from agg_logs

PRs that violate these are rejected without discussion.

## Code style

- Python: standard formatting, no linter enforced yet (added Day 5)
- SQL: UPPER CASE keywords, one clause per line for long queries
- JS: 2-space indent, const/let over var

## Reviewing

All PRs require one approval. The reviewer must confirm:

- CI passes (build + compile check)
- New behavior is covered by a test
- No privacy invariant is violated
- README or CHANGELOG updated if behavior changes
