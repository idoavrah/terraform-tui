# Development tasks. Everything runs through uv, so `make setup` is the only
# prerequisite beyond uv itself (https://docs.astral.sh/uv/).

EXAMPLE := examples/terraform

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Install dependencies and git hooks
	uv sync
	uv run pre-commit install

.PHONY: lint
lint: ## Lint and check formatting
	uv run ruff check .
	uv run ruff format --check .

.PHONY: format
format: ## Auto-fix lint and format
	uv run ruff check --fix .
	uv run ruff format .

.PHONY: types
types: ## Type-check with mypy
	uv run mypy

.PHONY: test
test: ## Run unit and end-to-end tests
	uv run pytest -m "not integration"

.PHONY: test-integration
test-integration: example-init ## Run tests against a real terraform binary
	uv run pytest -m integration -v

.PHONY: coverage
coverage: ## Run tests with a coverage report
	uv run pytest -m "not integration" --cov --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"

.PHONY: check
check: lint types test ## Everything CI runs on a pull request

.PHONY: run
run: example-init ## Run tftui against the example project
	cd $(EXAMPLE) && uv run --project $(CURDIR) tftui --offline --no-init

.PHONY: example-init
example-init: ## Initialise the example terraform project
	cd $(EXAMPLE) && terraform init -input=false

.PHONY: example-apply
example-apply: example-init ## Create real state in the example project
	cd $(EXAMPLE) && terraform apply -auto-approve

.PHONY: example-clean
example-clean: ## Destroy the example project's state
	cd $(EXAMPLE) && terraform destroy -auto-approve || true
	rm -rf $(EXAMPLE)/generated $(EXAMPLE)/terraform.tfstate*

.PHONY: fixtures
fixtures: example-apply ## Regenerate the captured terraform output in tests/fixtures
	./scripts/capture-fixtures.sh

.PHONY: screenshots
screenshots: example-apply ## Regenerate the SVG screenshots in docs/
	uv run python scripts/capture-screenshots.py

.PHONY: release-check
release-check: ## Would a push to main publish this version?
	uv run --no-project --with packaging python scripts/should_release.py

.PHONY: build
build: ## Build the wheel and sdist
	uv build

.PHONY: clean
clean: ## Remove build and test artefacts
	rm -rf dist build htmlcov .coverage .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
