UV ?= uv

.PHONY: install check test lint format types doctor

# make install V=1: one line per link
install:
	@$(UV) tool install --quiet --editable .
	@"$$($(UV) tool dir --bin)/aw" install $(if $(V),--verbose)
	@echo "next: make doctor"

# what CI runs; verify_cmd for sessions in this repo
check: test lint types

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

# rewrite: fix what ruff can and format
format:
	$(UV) run ruff check --fix src tests
	$(UV) run ruff format src tests

types:
	$(UV) run ty check src tests

# make doctor V=1: every check, not only problems
doctor:
	@"$$($(UV) tool dir --bin)/aw" doctor $(if $(V),--verbose)
