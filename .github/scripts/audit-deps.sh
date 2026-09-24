#!/usr/bin/env bash
#
# Scan this package's dependencies for known vulnerabilities.
#
# Usage: audit-deps.sh <output-dir>
#
# Writes four dependency trees to <output-dir>, each as a directory holding a
# file literally named requirements.txt, plus one Trivy report per tree:
#
#   runtime-ceiling/  + trivy-runtime-ceiling.json
#       requirements.txt alone, current resolution. What a fresh
#       `pip install permit` gets today.
#   runtime-floor/    + trivy-runtime-floor.json
#   runtime-floor-pydantic-v2/  + trivy-runtime-floor-pydantic-v2.json
#       requirements.txt alone, lowest-direct. Together, the lowest versions
#       the PUBLISHED specs permit -- i.e. real consumer exposure. These are
#       the trees that matter most for a library with open `>=` ranges.
#       requirements.txt accepts either pydantic major, and lowest-direct
#       picks the lowest release it allows, which is a pydantic 1 release, so
#       runtime-floor alone never scans a pydantic 2 floor.
#       runtime-floor-pydantic-v2 holds pydantic to 2 and scans the lowest
#       pydantic 2 (and the pydantic-core it pins) the specs permit.
#   dev-ceiling/      + trivy-dev-ceiling.json
#       requirements.txt + requirements-dev.txt, current resolution. Test
#       tooling only; never ships to a user.
#
# Plus pip-audit-<tree>.json (advisory only) for each of the four trees.
#
# WHY RUNTIME IS COMPILED ALONE. Compiling the runtime and dev files together
# lets a dev tool drag a runtime dependency's floor upward and hide the real
# exposure: when a dev tool needs a newer release of a runtime dependency than
# the floor in requirements.txt, the combined floor resolves that newer release,
# but a consumer installing only `permit` can still land on the older one.
# Scanning the combined floor would silently under-report exactly the versions
# users can actually get.
#
# WHY COMPILE AT ALL. Trivy's pip analyzer only understands `==`. Pointed at
# this repo's raw requirements.txt it reports zero findings and exits 0 -- a
# silently green gate. It also keys on the FILENAME, which is why each tree is
# written to its own directory as `requirements.txt` rather than scanned as a
# loose file (a loose file reports "Not scanned" and, again, exits 0).
set -euo pipefail

OUT="${1:?usage: audit-deps.sh <output-dir>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# The declared minimum. Resolving at the floor of supported Python is the
# worst case a consumer can legitimately be in.
PYTHON_VERSION="${AUDIT_PYTHON_VERSION:-3.10}"

# A resolved tree with almost nothing in it means the compile silently produced
# garbage. The real runtime tree is ~20 packages; 5 is a floor low enough never
# to false-positive and high enough to catch an empty or truncated compile.
MIN_PACKAGES=5

compile_tree() {
  local name="$1" resolution="$2"
  shift 2
  mkdir -p "${OUT}/${name}"
  local args=(--python-version "${PYTHON_VERSION}" --quiet -o "${OUT}/${name}/requirements.txt")
  if [ -n "${resolution}" ]; then
    args+=(--resolution "${resolution}")
  fi
  uv pip compile "$@" "${args[@]}"

  # Hard post-condition. Without this, an empty tree flows straight into Trivy,
  # which writes {"Results": null}, exits 0, and reads as a clean scan.
  local count
  count=$(grep -c '^[^#[:space:]].*==' "${OUT}/${name}/requirements.txt" || true)
  if [ "${count:-0}" -lt "${MIN_PACKAGES}" ]; then
    echo "::error title=Dependency resolution failed::Tree '${name}' resolved only ${count:-0} packages (expected at least ${MIN_PACKAGES}). Refusing to scan an empty tree and report it as clean."
    exit 1
  fi
  echo "${name}: ${count} packages"
}

echo "::group::Resolving dependency trees (python ${PYTHON_VERSION})"
# lowest-direct, not lowest: pin the declared bounds to their floor but let
# transitives resolve normally. Plain `lowest` would drag every transitive back
# to its first ever release and drown the report in irrelevant history.
compile_tree runtime-ceiling "" "${REPO_ROOT}/requirements.txt"
compile_tree runtime-floor "lowest-direct" "${REPO_ROOT}/requirements.txt"
echo "pydantic>=2" >"${OUT}/pydantic-v2-constraint.txt"
compile_tree runtime-floor-pydantic-v2 "lowest-direct" "${REPO_ROOT}/requirements.txt" \
  --constraints "${OUT}/pydantic-v2-constraint.txt"
compile_tree dev-ceiling "" "${REPO_ROOT}/requirements.txt" "${REPO_ROOT}/requirements-dev.txt"
echo "::endgroup::"

# Trivy exits non-zero on findings when --exit-code is set. We do not set it:
# the report must be produced and rendered whatever the outcome, and the
# pass/fail decision is made once, later, by format_audit.py --gate. One
# decision point means the PR comment and the check can never disagree.
#
# --ignorefile /dev/null is deliberate. Trivy picks up a .trivyignore from the
# working directory automatically and drops matching advisories from the JSON
# entirely -- they vanish from the gate, the PR comment and the Slack message
# with no trace that anything was suppressed. Unfixable advisories already fail
# open (see Finding.blocking), so there is no need for a silent mute button.
for tree in runtime-ceiling runtime-floor runtime-floor-pydantic-v2 dev-ceiling; do
  echo "::group::Trivy scan (${tree})"
  trivy fs \
    --scanners vuln \
    --format json \
    --ignorefile /dev/null \
    --output "${OUT}/trivy-${tree}.json" \
    --quiet \
    "${OUT}/${tree}"
  echo "::endgroup::"
done

# pip-audit is advisory-only. It reports no severity at all, so it can never
# gate; it is here because it reads PYSEC, which sometimes carries a
# Python-specific advisory before it reaches the GHSA feed Trivy uses.
# A pip-audit failure must never fail the job.
#
# Each tree is already a fully pinned `uv pip compile` output, so pip-audit
# reads the pins as written (--no-deps --disable-pip) instead of resolving them
# again in a throwaway venv. That venv is where it used to fail: ensurepip
# exits non-zero on the uv-managed Python, so pip-audit never produced a report.
#
# The exit code cannot tell a failure from a finding: pip-audit exits 1 for
# both. A finished run always writes its report and a failed one writes
# nothing, so each report is deleted before its run and a missing one is the
# failure signal. format_audit.py names every tree without a report in the PR
# comment, the job summary and the Slack message.
#
# PIP_AUDIT_LOGLEVEL=ERROR drops the warning pip-audit logs for --no-deps,
# which recommends hashing the requirements. With --disable-pip, pip-audit only
# checks that hashes are present and never verifies them, so hashing would add
# nothing. Errors, and the summary line, still print.
#
# The private cache keeps pip-audit away from the runner's pip HTTP cache,
# whose entries another pip version may have written in a format it cannot
# read.
PIP_AUDIT_VERSION="2.10.1"
pip_audit_cache="$(mktemp -d)"
for tree in runtime-ceiling runtime-floor runtime-floor-pydantic-v2 dev-ceiling; do
  report="${OUT}/pip-audit-${tree}.json"
  echo "::group::pip-audit (${tree}, advisory)"
  rm -f "${report}"
  status=0
  PIP_AUDIT_LOGLEVEL=ERROR uv tool run --from "pip-audit==${PIP_AUDIT_VERSION}" pip-audit \
    --requirement "${OUT}/${tree}/requirements.txt" \
    --no-deps \
    --disable-pip \
    --cache-dir "${pip_audit_cache}" \
    --format json \
    --output "${report}" \
    --progress-spinner off || status=$?
  if [ ! -s "${report}" ]; then
    echo "::warning title=pip-audit did not run::pip-audit exited ${status} without a report for ${tree}, so only Trivy checked that tree. The audit report names it too."
  fi
  echo "::endgroup::"
done
rm -r "${pip_audit_cache}"
