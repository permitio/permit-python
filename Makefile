.PHONY: help generate-models clean

.DEFAULT_GOAL := help

help:
	@echo "generate-models  regenerate permit/api/models.py from the Permit OpenAPI spec"
	@echo "clean            remove build artifacts"
	@echo ""
	@echo "Releasing is done by publishing a GitHub release, which runs"
	@echo ".github/workflows/python-sdk-publish.yml (build -> security scan -> PyPI)."

generate-models:
	datamodel-codegen --url https://api.permit.io/v2/openapi.json \
		--input-file-type openapi \
		--output permit/api/models.py \
		--output-model-type pydantic.BaseModel \
		--allow-extra-fields \
		--enum-field-as-literal one \
		--use-one-literal-as-default \
		--use-subclass-enum

clean:
	rm -rf *.egg-info build/ dist/
