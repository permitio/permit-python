#!/usr/bin/env bash
#
# Scan this package's dependencies for known vulnerabilities.
#
# Usage: audit-deps.sh <output-dir>
#
# Writes three dependency trees to <output-dir>, each as a directory holding a
# file literally named requirements.txt, plus one Trivy report per tree:
#
#   runtime-ceiling/  + trivy-runtime-ceiling.json
#       pyproject.toml [project].dependencies alone, current resolution. What
#       a fresh `pip install permit` gets today.
#   runtime-floor/    + trivy-runtime-floor.json
#       pyproject.toml [project].dependencies alone, lowest-direct. The lowest
#       versions the PUBLISHED specs permit -- i.e. real consumer exposure.
#       This is the tree that matters most for a library with open `>=`
#       ranges.
#   dev-ceiling/      + trivy-dev-ceiling.json
#       [project].dependencies + the `dev` dependency group, current
#       resolution. Test tooling only; never ships to a user.
#
# These are compiled from pyproject.toml, NOT exported from uv.lock: the lock
# pins one resolution for this repo's own CI, while the audit has to see what a
# consumer can resolve from the published ranges -- today's ceiling and the
# floor.
#
# Plus pip-audit.json (advisory only) for the runtime ceiling.
#
# WHY RUNTIME IS COMPILED ALONE. Compiling the runtime and dev deps together
# lets a dev tool drag a runtime dependency's floor upward and hide the real
# exposure: with mypy in the mix the floor resolves typing-extensions==4.12.0,
# because mypy requires >=4.6 -- but a consumer installing only `permit` can
# still land on 4.5.0. Scanning the combined floor would silently under-report
# exactly the versions users can actually get.
#
# WHY COMPILE AT ALL. Trivy's pip analyzer only understands `==`. Pointed at
# a list of open ranges it reports zero findings and exits 0 -- a
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
  # --no-sources: the published build ignores [tool.uv.sources] (uv build
  # --no-sources), so the audit must too. --exclude-newer false: the publish-age
  # cooldown in pyproject.toml applies to this repo's `uv lock` only; consumers
  # resolve against the index as it is today.
  local args=(
    --no-sources
    --exclude-newer false
    --python-version "${PYTHON_VERSION}"
    --quiet
    -o "${OUT}/${name}/requirements.txt"
  )
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
# Passing pyproject.toml compiles [project].dependencies only; dependency
# groups are added solely by an explicit --group.
compile_tree runtime-ceiling "" "${REPO_ROOT}/pyproject.toml"
compile_tree runtime-floor "lowest-direct" "${REPO_ROOT}/pyproject.toml"
compile_tree dev-ceiling "" "${REPO_ROOT}/pyproject.toml" \
  --group "${REPO_ROOT}/pyproject.toml:dev"

# The package-count check above cannot tell a dev tree from a runtime one, so a
# --group that silently matched nothing would scan the runtime tree twice and
# report the dev tooling as clean.
if ! grep -q '^pytest==' "${OUT}/dev-ceiling/requirements.txt"; then
  message="Tree 'dev-ceiling' does not contain pytest, so the 'dev' dependency group"
  message+=" was not resolved. Refusing to scan a runtime-only tree and report the dev"
  message+=" tooling as clean."
  echo "::error title=Dependency resolution failed::${message}"
  exit 1
fi
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
for tree in runtime-ceiling runtime-floor dev-ceiling; do
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
echo "::group::pip-audit (advisory)"
if ! uv tool run --from pip-audit pip-audit \
  --requirement "${OUT}/runtime-ceiling/requirements.txt" \
  --format json \
  --output "${OUT}/pip-audit.json" \
  --progress-spinner off; then
  echo "::warning::pip-audit did not complete cleanly; continuing with Trivy results only."
  # An absent file is handled by format_audit.py as a note; a truncated one
  # would be reported as a parse error. Remove it so a partial write cannot be
  # mistaken for a failed scan.
  rm -f "${OUT}/pip-audit.json"
fi
echo "::endgroup::"
