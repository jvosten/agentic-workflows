UV ?= uv

.PHONY: install check doctor

install:
	$(UV) tool install --editable .
	"$$($(UV) tool dir --bin)/aw" install
	@echo "installed; run 'make doctor'"

check:
	$(UV) run pytest

doctor:
	"$$($(UV) tool dir --bin)/aw" doctor
