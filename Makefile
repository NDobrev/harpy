REPO ?=
PR ?=
ID ?=
WEB := web

UV_SYNC_FLAGS := --all-extras
FORMAT_ARGS :=
RUFF_FIX := --fix
WEB_FMT := npm --prefix $(WEB) run fmt
ifeq ($(CI),true)
UV_SYNC_FLAGS += --frozen
FORMAT_ARGS := --check
RUFF_FIX :=
WEB_FMT := npm --prefix $(WEB) run fmt:check
endif

.PHONY: setup lock fmt lint types test package check goldens review tasks build-task web-openapi

setup:
	uv sync $(UV_SYNC_FLAGS)
	npm --prefix $(WEB) ci
	@echo "harpy is installed in .venv. Invoke it with: uv run harpy --help"
	@echo "fish: source .venv/bin/activate.fish"
	@echo "web gallery: npm --prefix web run dev"

lock:
	uv lock --check

fmt:
	uv run ruff format $(FORMAT_ARGS) src tests scripts
	$(WEB_FMT)

lint:
	uv run ruff check $(RUFF_FIX) src tests scripts
	npm --prefix $(WEB) run lint

types:
	uv run mypy src tests
	npm --prefix $(WEB) run types

test:
	uv run pytest -m "not cursor"
	npm --prefix $(WEB) run test

web-openapi:
	uv run harpy schema --web | python -c "import json,sys; print(json.dumps(json.load(sys.stdin), indent=2, sort_keys=True))" > docs/web/openapi.json
	@echo "wrote docs/web/openapi.json"

package:
	uv build --no-sources --no-build-isolation

check: lock fmt lint types test package

goldens:
	uv run pytest --snapshot-update

review:
	uv run harpy review --repo $(REPO) $(PR)

tasks:
	uv run python scripts/tasks.py --ready

build-task:
	scripts/build-task.sh $(ID)
