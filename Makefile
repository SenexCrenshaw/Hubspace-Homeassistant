SHELL := /bin/bash

REMOTE ?= origin
PUSH ?=
GH_RELEASE ?=
DRY_RUN ?= 0
PYTHON_BIN := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PRE_COMMIT_BIN := $(if $(wildcard .venv/bin/pre-commit),.venv/bin/pre-commit,pre-commit)
RELEASE_ARGS = $(if $(filter 1,$(PUSH)),--push,) $(if $(filter 0,$(PUSH)),--no-push,) $(if $(filter 1,$(GH_RELEASE)),--github-release,) $(if $(filter 0,$(GH_RELEASE)),--no-github-release,) $(if $(filter 1,$(DRY_RUN)),--dry-run,) --remote $(REMOTE)

.PHONY: help test lint qa release release-patch release-minor release-major publish-current

help:
	@printf '%s\n' \
		'make test' \
		'make lint' \
		'make qa' \
		'make release VERSION=6.1.1 [PUSH=0|1] [GH_RELEASE=0|1] [REMOTE=origin] [DRY_RUN=1]' \
		'make release-patch [PUSH=0|1] [GH_RELEASE=0|1] [REMOTE=origin] [DRY_RUN=1]' \
		'make release-minor [PUSH=0|1] [GH_RELEASE=0|1] [REMOTE=origin] [DRY_RUN=1]' \
		'make release-major [PUSH=0|1] [GH_RELEASE=0|1] [REMOTE=origin] [DRY_RUN=1]' \
		'make publish-current [PUSH=0|1] [GH_RELEASE=0|1] [REMOTE=origin] [DRY_RUN=1]'

test:
	@$(PYTHON_BIN) -m pytest

lint:
	@$(PRE_COMMIT_BIN) run --all-files

qa: test lint

release:
	@test -n "$(VERSION)" || (echo "VERSION is required"; exit 1)
	@./scripts/release.sh "$(VERSION)" $(RELEASE_ARGS)

release-patch:
	@./scripts/release.sh patch $(RELEASE_ARGS)

release-minor:
	@./scripts/release.sh minor $(RELEASE_ARGS)

release-major:
	@./scripts/release.sh major $(RELEASE_ARGS)

publish-current:
	@./scripts/release.sh --current $(RELEASE_ARGS)
