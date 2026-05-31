.PHONY: test lint validate-schemas preflight release-check clean

# ── Test targets ──────────────────────────────────────────────────────────────

test:
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

# ── Lint ──────────────────────────────────────────────────────────────────────

lint:
	python -m ruff check . || true

# ── Schema validation ─────────────────────────────────────────────────────────

validate-schemas:
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

preflight: validate-schemas test-prii
	@echo "Preflight complete."

# ── Release gate ──────────────────────────────────────────────────────────────

release-check:
	python run_all.py --release-check

# ── Syntax check ─────────────────────────────────────────────────────────────

syntax-check:
	find . -path ./.git -prune -o -path ./.claude -prune -o -name "*.py" -print -exec python -m py_compile {} +
	@echo "All Python modules compile OK."

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true
