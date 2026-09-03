REPO ?=
PR ?=
ID ?=

.PHONY: setup fmt lint types test check goldens review tasks build-task

setup:
	uv sync --all-extras
	@echo "harpy is installed in .venv. Invoke it with: uv run harpy --help"
	@echo "fish: source .venv/bin/activate.fish"

fmt:
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

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
