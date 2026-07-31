PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: help venv install test lint build demo drift clean

help:
	@echo "TwinOps targets:"
	@echo "  make venv     - create virtualenv"
	@echo "  make install  - install package + dev deps"
	@echo "  make test     - run unit tests"
	@echo "  make lint     - run ruff"
	@echo "  make demo     - full self-healing drift demo"
	@echo "  make drift    - build + drift against sample telemetry"
	@echo "  make build    - build sdist/wheel"
	@echo "  make clean    - remove build artifacts"

venv:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -U pip

install: venv
	$(BIN)/pip install -e ".[dev]"

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check python tests

build:
	$(BIN)/python -m build

demo:
	bash scripts/demo_self_healing.sh

drift:
	$(BIN)/twinopsctl build examples/assembly-line/twin.yaml --out examples/assembly-line/generated
	-$(BIN)/twinopsctl drift \
		--desired examples/assembly-line/desired.yaml \
		--stage examples/assembly-line/generated/root.usda \
		--observed examples/assembly-line/telemetry.json \
		--manifest examples/assembly-line/twin.yaml \
		--out examples/assembly-line/generated/drift \
		--propose examples/assembly-line/generated/proposal

clean:
	rm -rf dist build *.egg-info python/*.egg-info .pytest_cache .ruff_cache .coverage
	rm -rf examples/assembly-line/generated examples/assembly-line/demo-run usd/generated
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
