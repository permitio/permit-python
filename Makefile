.PHONY: help generate-models generate-sync-stubs clean

.DEFAULT_GOAL := help

help:
	@echo "generate-models      regenerate permit/api/models.py from the Permit OpenAPI spec"
	@echo "generate-sync-stubs  regenerate permit/_sync_types.pyi after changing an async API class"
	@echo "clean                remove build artifacts"
	@echo ""
	@echo "Releasing is done by publishing a GitHub release, which runs"
	@echo ".github/workflows/python-sdk-publish.yml (build -> security scan -> PyPI)."

# --use-default-kwarg writes Field(default=None, ...): type checkers only treat a
# keyword default as optional, so a positional one makes every optional field
# required to them. The generator emits plain `from pydantic import ...`, so after
# regenerating, re-apply the hand-written pydantic import header at the top of
# permit/api/models.py (the TYPE_CHECKING / _PYDANTIC_VERSION branches). Keep
# PYDANTIC_VERSION imported under the private _PYDANTIC_VERSION alias there, or
# permit/__init__.py's `from permit.api.models import *` exports it.
# The generator is pinned to 0.33.0, the release that produced the current file.
# --exclude-newer freezes its dependencies and formatters at that date, so an
# unchanged spec regenerates an unchanged file; those dependencies do not install
# on Python 3.14, hence --python 3.11. It runs through uvx, so it needs uv.
#
# Schema drift check: .github/scripts/check_schema_drift.py runs this generator
# with these flags (a unit test keeps the two equal) and compares the result with
# permit/api/models.py by structure: classes, fields, types, required or optional,
# defaults, aliases, Config.extra and enum members. A difference that makes the SDK
# send what the API rejects, or reject what it returns, fails the check; a class or
# optional field the SDK lacks is only reported. Known differences are listed in
# .github/scripts/schema_drift_allowlist.json with a one-line reason each, and an
# entry that no longer matches fails the check until it is removed. The entries
# whose reason says "by hand" are hand fixes to re-apply after regenerating. Run it
# after regenerating; it exits 0 (no new drift), 1 (new failing drift or a stale
# entry) or 2 (the comparison did not run):
#   python .github/scripts/check_schema_drift.py --models permit/api/models.py \
#     --allowlist .github/scripts/schema_drift_allowlist.json
# .github/workflows/schema-drift.yml runs it weekly, on manual dispatch and on pull
# requests that change these files.
generate-models:
	uvx --python 3.11 --exclude-newer 2025-09-18 \
		--from 'datamodel-code-generator[http]==0.33.0' datamodel-codegen \
		--url https://api.permit.io/v2/openapi.json \
		--input-file-type openapi \
		--output permit/api/models.py \
		--output-model-type pydantic.BaseModel \
		--allow-extra-fields \
		--enum-field-as-literal one \
		--use-one-literal-as-default \
		--use-subclass-enum \
		--use-default-kwarg

# PYTHONPATH makes the script import this checkout's permit, not an installed copy.
generate-sync-stubs:
	PYTHONPATH=. python scripts/generate_sync_stubs.py

clean:
	rm -rf *.egg-info build/ dist/
