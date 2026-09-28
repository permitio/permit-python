# Tests for the permit-python-3-migration skill

These tests check `MIGRATION.md`, the skill in `../permit-python-3-migration/` and its
scanner against each other and against the SDK. They are not part of the SDK's test suite:
CI runs them in their own job, `Migration Skill Tests`.

Run them from the repository root:

```bash
pip install . -r requirements-dev.txt
python -m pytest -c skills/tests/pytest.ini skills/tests
```

## Do not use the sample apps

`fixtures/v2_app` is a sample project written against permit 2.x. It pins **old versions
with known vulnerabilities on purpose**:

- permit 2.8.3;
- aiohttp 3.12.14 (CVE-2026-69244 and other advisories);
- pydantic 1 from 1.10.0 (CVE-2024-3772 before 1.10.13);
- Python 3.8/3.9;
- older typing-extensions and loguru.

`fixtures/v3_app` is the same app after the migration.

These versions must not be used anymore:

- Don't install or run either sample app, and don't copy their pins or code into a project.
- They exist only as input for the scanner, which reads them and never imports them. The
  tests copy them to a temporary directory and scan the copy.

The dependency files are stored as `*.fixture` (`pyproject.toml.fixture`,
`requirements.txt.fixture`), so dependency scanners don't read the sample apps' pins as this
repository's dependencies:

- GitHub's dependency graph, Dependency Review, Dependabot and Snyk find manifests by file
  name, so they skip these files.
- The Trivy step in `.github/workflows/security.yml` and `python-sdk-publish.yml` also skips
  `skills/tests/fixtures`.
- `test_no_fixture_file_has_a_name_github_reads_as_a_dependency_manifest` fails if a
  fixture is stored under a manifest name again.
