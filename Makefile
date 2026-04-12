# Common dev + test tasks.
# Usage: `make smoke` etc.

.PHONY: smoke smoke-local smoke-full test

# Smoke tests against production (no signup — safe to run anytime)
smoke:
	SMOKE_SKIP_SIGNUP=1 python3 -m pytest tests/smoke/ -v --tb=short

# Smoke tests against local dev server (http://localhost:8000)
smoke-local:
	SMOKE_BASE_URL=http://localhost:8000 SMOKE_SKIP_SIGNUP=1 python3 -m pytest tests/smoke/ -v --tb=short

# Full smoke including signup (creates real test users — staging only!)
smoke-full:
	@echo "⚠️  This creates real test users in the target DB. Make sure SMOKE_BASE_URL points to staging."
	@sleep 2
	python3 -m pytest tests/smoke/ -v --tb=short

# Unit tests (scanner, tier, etc.)
test:
	python3 -m pytest tests/test_ai_day_scanner.py tests/test_tier_enforcement.py tests/test_copilot_education.py -v
