PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: help venv install test lint build demo drift serve web web-dev operator-build operator-run go-test clean

help:
	@echo "TwinOps targets:"
	@echo "  make venv            - create virtualenv"
	@echo "  make install         - install package + dev deps"
	@echo "  make test            - run Python unit tests"
	@echo "  make lint            - run ruff"
	@echo "  make demo            - full self-healing drift demo"
	@echo "  make drift           - build + drift against sample telemetry"
	@echo "  make serve           - live MQTT-style simulator + drift API"
	@echo "  make web             - build web control plane into web/dist"
	@echo "  make web-dev         - run Vite UI (proxies API on :8080)"
	@echo "  make operator-build  - build Go operator manager binary"
	@echo "  make operator-run    - run operator against current kubeconfig"
	@echo "  make go-test         - run Go tests"
	@echo "  make build           - build sdist/wheel"
	@echo "  make clean           - remove build artifacts"

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

serve:
	$(BIN)/twinopsctl serve --example examples/assembly-line --host 127.0.0.1 --port 8080

web:
	cd web && npm install && npm run build

web-dev:
	cd web && npm run dev -- --host 127.0.0.1 --port 5173

operator-build:
	go build -o bin/manager ./cmd/manager

operator-run: operator-build
	./bin/manager --twinopsctl=$(BIN)/twinopsctl

go-test:
	go test ./...

clean:
	rm -rf dist build bin *.egg-info python/*.egg-info .pytest_cache .ruff_cache .coverage
	rm -rf examples/assembly-line/generated examples/assembly-line/demo-run usd/generated web/dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
