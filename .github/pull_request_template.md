## Summary
<!-- 1-3 bullet points describing what changed and why -->

## Test plan
- [ ] New tests added for changed code
- [ ] Existing tests still pass: `python -m pytest tests/ -q --ignore=tests/test_io.py --ignore=tests/test_terrain.py`
- [ ] Schema changes: `python -m pytest tests/test_schema_validation.py tests/test_new_schemas.py -q`
- [ ] PRII preflight: `python -m pytest tests/test_prii_readiness_engine.py tests/test_cli_readiness.py -q`
- [ ] If schemas modified: `python -c "from schema_validation import SchemaValidator; v=SchemaValidator(); print(v.available_schemas())"`
- [ ] No existing files unintentionally modified: `git diff main --name-only`

## Changed files
<!-- List the files changed and why -->

## Checklist
- [ ] No secrets or credentials committed
- [ ] No `*.db` or large binary files added
- [ ] Contract docs updated if schema fields added/removed
