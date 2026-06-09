.PHONY: help bootstrap test lint lint-strict format mypy check \
	validate-schemas preflight release-check clean

.DEFAULT_GOAL := help

# Curated lint/type allowlist (T6-49/50) — must match LINT_PATHS in ci.yml.
# Grows as more modules are cleaned in later themes.
LINT_PATHS := provenance_utils.py run_modes.py integration/mbil.py \
	pipeline/db_utils.py pipeline/terrain_hook.py federation/envelope.py \
	federation/readiness.py pipeline/logging_config.py pipeline/config_loader.py \
	pipeline/seeding.py pipeline/verbosity.py

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── Bootstrap ─────────────────────────────────────────────────────────────────

bootstrap:  ## Create a venv, install dev extras, install pre-commit hooks
	python -m venv .venv
	. .venv/bin/activate && pip install -e ".[airspace,earthgpt,server,dev]" "httpx>=0.27" && pre-commit install
	@echo "Bootstrap complete. Activate with: . .venv/bin/activate"

# ── Test targets ──────────────────────────────────────────────────────────────

test:  ## Run the core test suite (excludes gebco-only suites)
	python -m pytest tests/ -q --ignore=tests/test_io.py --ignore=tests/test_terrain.py

test-schemas:
	python -m pytest tests/test_schema_validation.py tests/test_new_schemas.py \
	  tests/test_satellite_source_manifest_schema.py -v

test-prii:
	python -m pytest tests/test_prii_readiness_engine.py tests/test_cli_readiness.py \
	  tests/test_schema_validation.py -v

test-phase1:
	python -m pytest tests/test_hardening_layer.py tests/test_operational_intelligence.py \
	  tests/test_calibrate_scoring.py tests/test_manual_review_queue.py -v

# ── Lint + type check ─────────────────────────────────────────────────────────

lint:  ## Advisory repo-wide ruff (non-gating)
	python -m ruff check . || true

lint-strict:  ## Gating ruff + black --check on the curated allowlist
	python -m ruff check $(LINT_PATHS)
	python -m black --check $(LINT_PATHS)

format:  ## Auto-fix imports + format the curated allowlist in place
	python -m ruff check --fix $(LINT_PATHS)
	python -m black $(LINT_PATHS)

mypy:  ## Type-check the curated allowlist
	python -m mypy $(LINT_PATHS)

check: lint-strict mypy test  ## Local CI parity: lint + type + test

# ── Schema validation ─────────────────────────────────────────────────────────

validate-schemas:  ## Load all schemas and assert the expected count
	python -c "\
	from integration.schema_validation import SchemaValidator; \
	v = SchemaValidator(); \
	schemas = v.available_schemas(); \
	print(f'Loaded {len(schemas)} schemas: {schemas}'); \
	assert len(schemas) >= 11, f'Expected >=11, got {len(schemas)}'"

docs-check:
	@echo "Checking schema/contract doc alignment..."
	@for s in schemas/*.schema.json; do \
	  name=$$(basename "$$s" .schema.json); \
	  doc="docs/contracts/$$(echo $$name | tr '[:lower:]' '[:upper:]' | tr '_' '_').md"; \
	  if [ -f "docs/contracts/$${name}.md" ] || [ -f "docs/contracts/$$(echo $$name | awk '{print toupper($$0)}').md" ]; then \
	    echo "  OK: $$name"; \
	  else \
	    echo "  MISSING doc for: $$name"; \
	  fi; \
	done

# ── Full preflight ────────────────────────────────────────────────────────────

preflight: validate-schemas test-prii  ## Schema validation + PRII tests
	@echo "Preflight complete."

# ── Release gate ──────────────────────────────────────────────────────────────

release-check:  ## Run the umbrella release gate
	python run_all.py --release-check

# ── Syntax check ─────────────────────────────────────────────────────────────

syntax-check:  ## Compile every Python module (no import)
	find . -path ./.git -prune -o -path ./.claude -prune -o -name "*.py" -print -exec python -m py_compile {} +
	@echo "All Python modules compile OK."

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:  ## Remove caches and compiled artifacts
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
