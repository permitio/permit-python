.PHONY: help

.DEFAULT_GOAL := help

generate-models:
	datamodel-codegen --url https://api.permit.io/v2/openapi.json \
		--input-file-type openapi \
		--output permit/api/models.py \
		--output-model-type pydantic.BaseModel \
		--allow-extra-fields \
		--enum-field-as-literal one \
		--use-one-literal-as-default \
		--use-subclass-enum

# python packages (pypi)
clean:
	rm -rf *.egg-info build/ dist/

publish:
	$(MAKE) clean
	python setup.py sdist bdist_wheel
	python -m twine upload dist/*
