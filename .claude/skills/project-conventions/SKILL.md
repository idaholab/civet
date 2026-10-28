---
name: project-conventions
description: CIVET project conventions - coverage policy, test layout, generated migrations, vendored assets, and style rules. Use when writing or modifying code or tests in this repo.
user-invocable: false
---

# CIVET conventions

## Layout
- `ci/` - Django server app (models, views, webhooks, recipes, GitHub/GitLab APIs). Tests in `ci/tests/`
  plus per-package `tests/` dirs (`ci/github/tests`, `ci/gitlab/tests`, `ci/recipe/tests`, `ci/client/tests`).
- `client/` - the job-running client (separate from the server; tests in `client/tests`).
- `civet/` - Django project settings/urls/wsgi.

## Style and CI gates
- Formatting is `ruff format` (CI runs `ruff format --check`); lint is `pyflakes`. Nothing else is enforced.
- Python 3.13 only; dependencies are pinned exactly in `pyproject.toml` (Dependabot manages them).
  Django is capped below 7.0.
- Tests run under `python -Werror`: new warnings (including deprecations) fail the suite.

## Coverage policy
- CI fails on **any** uncovered line (`MAX_MISSING_LINES := 0`). New branches need tests.
- Omitted from coverage (don't expect tests there): `*/__init__.py`, `ci/templatetags/*`,
  `ci/migrations/*`, `ci/management/commands/*`, `ci/recipe/recipe_to_bash.py`, `client/daemon.py`,
  `client/scripts/*`, `civet/*`, `manage.py`, and test files themselves.
- Prefer testing through existing helpers in `ci/tests/utils.py` and `ci/tests/DBTester.py`
  rather than building fixtures by hand.

## Tests
- Run a subset with `make test <dotted.path>` (e.g. `make test ci.tests.test_models`).
- Selenium tests (`*_selenium.py`) only run with `SELENIUM_TEST=1`.

## Migrations
- `ci/migrations/*` is **gitignored** (only `__init__.py` is tracked). CI runs `makemigrations`
  then `migrate`. Don't commit migration files; model changes just need the model edit.

## Do not edit
- `ci/static/third_party/` (bootstrap, font-awesome, jquery, shields.io) is vendored. A hook blocks edits.

## Naming
- Modules are mixed case where they hold one main class/concept (`Permissions.py`, `PushEvent.py`,
  `test_PushEvent.py`); match the neighbouring files rather than renaming.
