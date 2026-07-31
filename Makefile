PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: help venv install test lint build demo clean

help:
	@echo "TwinOps targets:"
	@echo "  make venv     - create virtualenv"
	@echo "  make install  - install package + dev deps"
	@echo "  make test     - run unit tests"
	@echo "  make lint     - run ruff"
	@echo "  make demo     - compile assembly-line example"
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
	$(BIN)/twinopsctl build examples/assembly-line/twin.yaml --out examples/assembly-line/generated

clean:
	rm -rf dist build *.egg-info python/*.egg-info .pytest_cache .ruff_cache .coverage
	rm -rf examples/assembly-line/generated usd/generated
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
