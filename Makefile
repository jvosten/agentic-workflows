UV ?= uv

.PHONY: install check doctor

# make install V=1: one line per link
install:
	@$(UV) tool install --quiet --editable .
	@"$$($(UV) tool dir --bin)/aw" install $(if $(V),--verbose)
	@echo "next: make doctor"

check:
	$(UV) run pytest

# make doctor V=1: every check, not only problems
doctor:
	@"$$($(UV) tool dir --bin)/aw" doctor $(if $(V),--verbose)
