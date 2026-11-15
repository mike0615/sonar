#!/usr/bin/env bash
# Build Sonar RPMs for Rocky Linux 9 and 10 using podman (or docker).
# Usage: bash packaging/build-rpm.sh [9] [10]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENGINE="$(command -v podman || command -v docker || true)"
[ -n "${ENGINE}" ] || { echo "podman or docker is required." >&2; exit 1; }
VERSIONS=("$@"); [ ${#VERSIONS[@]} -gt 0 ] || VERSIONS=(9 10)
for v in "${VERSIONS[@]}"; do
    echo "== Building in rockylinux/rockylinux:${v}"
    "${ENGINE}" run --rm -v "${REPO_ROOT}:/work:Z" "docker.io/rockylinux/rockylinux:${v}" \
        bash -c "bash /work/packaging/build-in-container.sh"
done
ls -lh "${REPO_ROOT}"/out/sonar-*.rpm
