---
name: run-checks
description: Run the same checks CI runs (pyflakes, ruff format, tests, and the zero-missing-lines coverage gate) before pushing
disable-model-invocation: true
argument-hint: "[test paths, e.g. ci.tests.test_models]"
---

Run CI's checks locally, in this order, and stop to report on the first failing stage.
Use the project's Python environment (Python 3.13, deps from `pyproject.toml`, test extras
required: `uv pip install -r pyproject.toml --extra test` or `pip install -e ".[test]"`-equivalent).

1. **Precheck** (mirrors the `precheck` CI job):
   - `pyflakes $(git ls-files '*.py')`
   - `ruff format --check --diff .`
   - If ruff reports a diff, run `ruff format .` and show what changed.

2. **Tests** (mirrors `make test`): `make test $ARGUMENTS`
   - Tests run with `python -Werror`, so any warning is a failure.
   - Selenium tests are skipped unless `SELENIUM_TEST=1` is set; set it only when the change
     touches views, templates, or static JS, and Chrome is available.

3. **Coverage gate** (mirrors the `test` CI job): `make coverage $ARGUMENTS` then `make check`
   - CI requires **zero** missing lines (`MAX_MISSING_LINES := 0` in the Makefile).
   - If lines are missing, list `file:line` ranges from `coverage report -m` and offer to add tests.
   - With a narrowed test path, coverage for unrelated files will look low; only judge the files
     that were changed.

Finish with a short pass/fail summary per stage.
