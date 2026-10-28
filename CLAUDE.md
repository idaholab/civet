# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CIVET is a Django CI server (GitHub/GitLab webhooks in, commit statuses out) plus a separate polling client that runs the jobs. See the README for the project background; setup docs live in the external GitHub wiki.

## Commands

Python 3.13 only (`.python-version`). Dependencies are pinned in `pyproject.toml`; the `test` extra provides ruff, pyflakes, coverage, selenium. CI installs them with `pip-compile --extra=test` into a venv.

```bash
make test                          # all tests: python -Werror ./manage.py test --parallel=4
make test ci.tests.test_models     # extra args are test labels (make ignores them as targets)
make test ci.tests.test_models.Tests.test_job_status   # single test
make coverage [labels]             # tests under coverage, then `coverage report -m`
make check                         # fails if ANY line is uncovered (MAX_MISSING_LINES := 0)

pyflakes $(git ls-files '*.py')    # lint (CI)
ruff format --check --diff .       # format check (CI); drop flags to apply
SELENIUM_TEST=1 make test ci.tests.test_job_view_selenium   # Selenium tests are skipped without this (needs Chrome)
```

- Tests run with `-Werror`: any new warning, including deprecations, fails the suite.
- `/run-checks` runs the CI sequence locally. A hook formats edited `.py` files with ruff, and another blocks edits to `ci/static/third_party/`.
- Running the server locally: `./manage.py migrate`, then `./manage.py db_worker` (single worker) alongside the web process.

## Architecture

Three cooperating pieces: the Django server (`ci/`, project settings in `civet/`), the job runner (`client/`, a standalone process), and the git servers (GitHub/GitLab) on either side.

**Event flow** (needs several files to see):
1. A git server POSTs to `ci/github/views.py` or `ci/gitlab/views.py`. Both delegate to `ci/webhook.py:handle_webhook`, which is parameterized by an `is_authentic` callback (HMAC signature for GitHub) and a `process_event` callback.
2. The event processors (`PullRequestEvent`, `PushEvent`, `ReleaseEvent`, `ManualEvent` in `ci/`) create an `Event` plus one `Job` per matching `Recipe`/`BuildConfig` (`ci/models.py`). `ci/event.py` has event-level operations such as cancel.
3. Clients poll `ci/client/views.py:get_job`. Ready jobs come from `ci/client/ReadyJobs.py` (ordered by priority, then creation), are cached, and claimed atomically. Client endpoints are authenticated by a `build_key` carried in the URL, not by session.
4. The client (`client/JobGetter`, `JobRunner`, `ServerUpdater`, wired together in `client/BaseClient.py`) runs the recipe's steps and posts step output back (`start_step_result`, `update_step_result`, `complete_step_result`, `job_finished`).
5. `ci/client/UpdateRemoteStatus.py` turns job/event state changes into commit statuses, PR comments and labels. It does not call the git server inline: it enqueues `ci/tasks.py` tasks (Django `django.tasks` with the `django_tasks_db` backend), so webhooks and clients never wait on the git server.

**Things that are easy to get wrong**
- Background tasks must be processed by a **single** worker so a job's statuses (pending, running, complete) arrive in order. Task arguments are primary keys/plain values and must be JSON serializable; tasks that post one status/comment/label take values captured at enqueue time, while the job/event-complete tasks rebuild from the DB when they run.
- In tests (`manage.py test`), `civet/settings.py` swaps in the immediate task backend, so `.enqueue()` runs synchronously.
- `ci/git_api.py:GitAPI` is the abstract interface; `ci/github/api.py` and `ci/gitlab/api.py` implement it. Callers get the right implementation from the model (e.g. `build_user.api()` on `GitUser`), so new git-server behavior goes in the interface plus both implementations. OAuth is in `ci/oauth_api.py` and the per-server `oauth.py` modules.
- Authorization is centralized in `ci/Permissions.py` (collaborator/team checks are cached for `PERMISSION_CACHE_TIMEOUT`). Views and ajax endpoints should go through it rather than checking users ad hoc.
- Recipes are `.cfg` files under `recipes/` in a separate recipe repo (default `RECIPE_BASE_DIR` is `../civet_recipes`, outside this repo). `ci/recipe/RecipeRepoReader`/`RecipeReader` parse them, `RecipeCreator` syncs them into DB `Recipe`/`Step` rows (`./manage.py load_recipes [--force] [--dryrun]`), and `recipe_to_bash.py` converts a recipe to a script.
- `civet/settings.py` is the checked-in default (sqlite DB, `INSTALLED_GITSERVERS = [github_config]`, placeholder secrets). Deployments override it; do not put real credentials there.
- `ci/migrations/*` is gitignored (only `__init__.py` is tracked); CI and deployments run `makemigrations` then `migrate`. Model changes need no migration file in the PR.

## Tests

- Server tests live in `ci/tests/` and in per-package `tests/` dirs (`ci/github`, `ci/gitlab`, `ci/recipe`, `ci/client`, `ci/ajax`); client tests in `client/tests`.
- Use `ci/tests/utils.py` (factories for servers, users, repos, events, jobs) and `ci/tests/DBTester.py` rather than hand-building fixtures.
- CI requires zero uncovered lines. Excluded from coverage (`.coveragerc`): migrations, `ci/management/commands`, `ci/templatetags`, `ci/recipe/recipe_to_bash.py`, `client/daemon.py`, `client/scripts`, `civet/`, `manage.py`, tests. The `coverage-gatekeeper` (fills gaps) and `security-reviewer` (webhooks, `Permissions.py`, OAuth, client API) agents are slow: use them when asked, or when a coverage report or the nature of the change calls for it, not on every change. Likewise run the narrowest `make test <labels>` that covers a change, and the full suite or `make coverage` only when asked or when shared code (`ci/models.py`, `ci/views.py`, `Permissions.py`, settings) changed; CI runs the full suite on every PR anyway.
- CI runs the full suite with `SELENIUM_TEST=1` (the `test` job, via `make coverage`), so Selenium failures will only show up in CI unless you run them locally for UI changes.
