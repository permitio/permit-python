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
# permit/api/models.py (the TYPE_CHECKING / PYDANTIC_VERSION branches).
generate-models:
	datamodel-codegen --url https://api.permit.io/v2/openapi.json \
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
