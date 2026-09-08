REPO ?=
PR ?=
ID ?=

UV_SYNC_FLAGS := --all-extras
FORMAT_ARGS :=
RUFF_FIX := --fix
ifeq ($(CI),true)
UV_SYNC_FLAGS += --frozen
FORMAT_ARGS := --check
RUFF_FIX :=
endif

.PHONY: setup fmt lint types test check goldens review tasks build-task

setup:
	uv sync $(UV_SYNC_FLAGS)
	@echo "harpy is installed in .venv. Invoke it with: uv run harpy --help"
	@echo "fish: source .venv/bin/activate.fish"

fmt:
	uv run ruff format $(FORMAT_ARGS) src tests scripts
	uv run ruff check $(RUFF_FIX) src tests scripts

lint:
	uv run ruff check src tests scripts

types:
	uv run mypy src tests

test:
	uv run pytest -m "not cursor"

check: fmt lint types test

goldens:
	uv run pytest --snapshot-update

review:
	uv run harpy review --repo $(REPO) $(PR)

tasks:
	uv run python scripts/tasks.py --ready

build-task:
	scripts/build-task.sh $(ID)
