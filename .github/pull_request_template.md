## What

Brief description of the change.

## Why

Fixes #

## How tested

- [ ] docker compose exec monolith pytest -v passes locally
- [ ] New behavior covered by a test
- [ ] Manual verification via curl (paste response)

## Privacy checklist

- [ ] No raw worker IDs written to any column
- [ ] No individual records returned from admin endpoints
- [ ] Aggregates still enforce k-anonymity >= 5
- [ ] Audit log remains append-only

## Checklist

- [ ] CHANGELOG.md updated under Unreleased
- [ ] README updated if public API changed
- [ ] No secrets committed
