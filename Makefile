SHELL := /bin/bash

REMOTE ?= origin
PUSH ?= 0
GH_RELEASE ?= 0
DRY_RUN ?= 0
RELEASE_ARGS = $(if $(filter 1,$(PUSH)),--push,) $(if $(filter 1,$(GH_RELEASE)),--github-release,) $(if $(filter 1,$(DRY_RUN)),--dry-run,) --remote $(REMOTE)

.PHONY: help release release-patch release-minor release-major publish-current

help:
	@printf '%s\n' \
		'make release VERSION=6.1.1 [PUSH=1] [GH_RELEASE=1] [REMOTE=origin]' \
		'make release-patch [PUSH=1] [GH_RELEASE=1] [REMOTE=origin]' \
		'make release-minor [PUSH=1] [GH_RELEASE=1] [REMOTE=origin]' \
		'make release-major [PUSH=1] [GH_RELEASE=1] [REMOTE=origin]' \
		'make publish-current [PUSH=1] [GH_RELEASE=1] [REMOTE=origin]'

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
