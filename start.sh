#!/bin/sh

echo "========================================"
echo " Starting SentinelHealth on Render"
echo "========================================"

echo ""
echo "--- DIAGNOSTIC: files present in container? ---"
ls -la /app/scripts/ 2>&1 || echo "  /app/scripts MISSING"
ls -la /app/migrations/versions/ 2>&1 || echo "  /app/migrations/versions MISSING"
echo ""

echo "--- Running database migrations ---"
if alembic upgrade head; then
    echo "✓ Migrations applied successfully"
else
    echo "⚠ Migration failed — app will still start"
fi

echo ""
echo "--- Seeding facility data (Level 1-6) ---"
if python /app/scripts/seed_all_facilities.py; then
    echo "✓ Facilities seeded"
else
    echo "⚠ Facility seed skipped"
fi

echo ""
echo "--- Seeding verified test accounts ---"
if python /app/scripts/seed_test_accounts.py; then
    echo "✓ Test accounts ready"
else
    echo "⚠ Test account seed skipped"
fi

echo ""
echo "--- Starting Uvicorn ---"
exec uvicorn app.combined:app --host 0.0.0.0 --port ${PORT:-8000}
