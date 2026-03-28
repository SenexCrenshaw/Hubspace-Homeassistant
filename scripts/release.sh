#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_PATH="$ROOT_DIR/custom_components/hubspace/manifest.json"
REMOTE="origin"
PUSH=0
GITHUB_RELEASE=0
DRY_RUN=0
CURRENT_ONLY=0
COMMIT_MESSAGE=""

usage() {
  cat <<'EOF'
Usage:
  scripts/release.sh <patch|minor|major|X.Y.Z> [--push] [--github-release] [--remote <name>] [--message <text>] [--dry-run]
  scripts/release.sh --current [--push] [--github-release] [--remote <name>] [--dry-run]

Behavior:
  - Bump mode expects your release changes to already be staged.
  - Bump mode updates custom_components/hubspace/manifest.json, commits the staged changes,
    creates an annotated tag matching the manifest version, then optionally pushes and
    creates a GitHub release.
  - Current mode skips the version bump and commit, and just tags/releases the current HEAD.

Examples:
  ./scripts/release.sh patch --push --github-release
  ./scripts/release.sh 6.1.1 --push
  ./scripts/release.sh --current --push --github-release
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf 'DRY RUN:'
    printf ' %q' "$@"
    printf '\n'
    return
  fi

  "$@"
}

read_manifest_version() {
  python3 - "$MANIFEST_PATH" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text())
print(manifest["version"])
PY
}

write_manifest_version() {
  python3 - "$MANIFEST_PATH" "$1" <<'PY'
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
next_version = sys.argv[2]
manifest = json.loads(manifest_path.read_text())
manifest["version"] = next_version
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
PY
}

resolve_version() {
  python3 - "$1" "$2" <<'PY'
import re
import sys

current = sys.argv[1]
requested = sys.argv[2].removeprefix("v")
pattern = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

if pattern.fullmatch(requested) is not None:
    print(requested)
    raise SystemExit

if requested in {"patch", "minor", "major"}:
    current_match = pattern.fullmatch(current)
    if current_match is None:
        raise SystemExit(
            f"Current manifest version '{current}' is not strict semver. "
            "Pass an explicit X.Y.Z version."
        )
    major, minor, patch = map(int, current_match.groups())
    if requested == "patch":
        patch += 1
    elif requested == "minor":
        minor += 1
        patch = 0
    else:
        major += 1
        minor = 0
        patch = 0
    print(f"{major}.{minor}.{patch}")
    raise SystemExit

if pattern.fullmatch(requested) is None:
    raise SystemExit(
        "Version must be patch, minor, major, or an explicit X.Y.Z value."
    )

print(requested)
PY
}

current_branch() {
  git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD
}

ensure_branch() {
  local branch

  branch="$(current_branch)"
  if [[ "$branch" == "HEAD" ]]; then
    die "detached HEAD is not supported for release automation"
  fi
}

ensure_no_unstaged_tracked_changes() {
  if ! git -C "$ROOT_DIR" diff --quiet --ignore-submodules --; then
    die "unstaged tracked changes detected; stage or stash them first"
  fi
}

ensure_staged_changes() {
  if git -C "$ROOT_DIR" diff --cached --quiet --ignore-submodules --; then
    die "no staged changes found; stage the files you want in the release commit first"
  fi
}

ensure_no_staged_changes() {
  if ! git -C "$ROOT_DIR" diff --cached --quiet --ignore-submodules --; then
    die "--current requires no staged changes"
  fi
}

ensure_tag_missing() {
  if git -C "$ROOT_DIR" rev-parse --verify --quiet "refs/tags/$1" >/dev/null; then
    die "tag '$1' already exists locally"
  fi
}

create_github_release() {
  if ! command -v gh >/dev/null 2>&1; then
    die "gh CLI is required for --github-release"
  fi

  run gh release create \
    "$1" \
    --verify-tag \
    --title "$1" \
    --generate-notes
}

VERSION_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --push)
      PUSH=1
      shift
      ;;
    --github-release)
      GITHUB_RELEASE=1
      PUSH=1
      shift
      ;;
    --remote)
      [[ $# -ge 2 ]] || die "--remote requires a value"
      REMOTE="$2"
      shift 2
      ;;
    --message)
      [[ $# -ge 2 ]] || die "--message requires a value"
      COMMIT_MESSAGE="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --current)
      CURRENT_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      die "unknown option: $1"
      ;;
    *)
      if [[ -n "$VERSION_ARG" ]]; then
        die "only one version argument is supported"
      fi
      VERSION_ARG="$1"
      shift
      ;;
  esac
done

if [[ "$CURRENT_ONLY" -eq 1 ]]; then
  [[ -z "$VERSION_ARG" ]] || die "--current does not accept a version argument"
else
  [[ -n "$VERSION_ARG" ]] || die "missing required version argument"
fi

if ! git -C "$ROOT_DIR" remote get-url "$REMOTE" >/dev/null 2>&1; then
  die "git remote '$REMOTE' does not exist"
fi

ensure_branch

CURRENT_VERSION="$(read_manifest_version)"
NEXT_VERSION="$CURRENT_VERSION"

if [[ "$CURRENT_ONLY" -eq 1 ]]; then
  ensure_no_unstaged_tracked_changes
  ensure_no_staged_changes
else
  ensure_no_unstaged_tracked_changes
  ensure_staged_changes
  NEXT_VERSION="$(resolve_version "$CURRENT_VERSION" "$VERSION_ARG")"
  if [[ "$NEXT_VERSION" == "$CURRENT_VERSION" ]]; then
    die "next version matches current manifest version '$CURRENT_VERSION'"
  fi
fi

ensure_tag_missing "$NEXT_VERSION"

if [[ "$CURRENT_ONLY" -eq 0 ]]; then
  run write_manifest_version "$NEXT_VERSION"
  run git -C "$ROOT_DIR" add "$MANIFEST_PATH"
  if [[ -z "$COMMIT_MESSAGE" ]]; then
    COMMIT_MESSAGE="Release $NEXT_VERSION"
  fi
  run git -C "$ROOT_DIR" commit -m "$COMMIT_MESSAGE"
fi

run git -C "$ROOT_DIR" tag -a "$NEXT_VERSION" -m "Release $NEXT_VERSION"

if [[ "$PUSH" -eq 1 ]]; then
  BRANCH="$(current_branch)"
  run git -C "$ROOT_DIR" push "$REMOTE" "$BRANCH"
  run git -C "$ROOT_DIR" push "$REMOTE" "$NEXT_VERSION"
fi

if [[ "$GITHUB_RELEASE" -eq 1 ]]; then
  create_github_release "$NEXT_VERSION"
fi

echo "Prepared release $NEXT_VERSION"
