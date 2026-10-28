---
name: review-pr
description: Review a CIVET pull request - fetches the PR, checks it out in an isolated worktree, runs the CI checks (pyflakes, ruff, tests, zero-missing-lines coverage) and reviews the diff against this repo's conventions. Use when asked to review a PR by number or URL.
argument-hint: "<PR number or URL>"
---

Review one pull request and report findings. **Read-only toward GitHub**: never post a review, comment,
approval or label unless the user explicitly asks for that after seeing your findings. Paths are relative
to the repo root; `$ARGUMENTS` is the PR number or URL.

## 1. Gather context

```bash
gh pr view $ARGUMENTS --json number,title,author,baseRefName,headRefOid,state,isDraft,additions,deletions,changedFiles,reviewDecision
gh pr diff $ARGUMENTS --name-only
gh pr checks $ARGUMENTS
gh pr diff $ARGUMENTS
```

Note what the PR says it does (title, body, linked issue) before reading code; the review is whether the
diff does that, and nothing it shouldn't. If the state is not `OPEN`, say so up front.

## 2. Check it out in a throwaway worktree

Never switch the user's working tree.

```bash
W=/tmp/civet-review-$PR && git worktree add --detach $W HEAD
cd $W && gh pr checkout $PR --detach
export PATH=<repo root>/.venv/bin:$PATH      # reuse the main checkout's venv (see /run-civet to create it)
python manage.py makemigrations              # migrations are gitignored; without this every test fails with "no such table"
```

## 3. Run the CI checks on the PR

```bash
ruff format --check --diff .
pyflakes $(git ls-files '*.py')
make test <labels for the changed modules>
make coverage <labels for the changed modules>
```

- Pick test labels from the changed files (`ci/ajax/views.py` -> `ci.ajax.tests.test_views`; see the `ci/*/tests`
  dirs). CI runs the whole suite, so also run `make test` unscoped if the PR touches `ci/models.py`,
  `ci/views.py`, `Permissions.py` or shared helpers.
- Coverage must be **zero missing lines** for the changed files. With a scoped run, ignore files the PR
  did not touch and lines only reachable from other test modules (check before reporting them: rerun with the
  module that covers them). Excluded paths are listed in `.coveragerc`.
- Tests run under `-Werror`, so a new warning is a real failure.
- Selenium tests only run with `SELENIUM_TEST=1` and need Chrome; run them for template/JS changes if
  Chrome is available, otherwise say they weren't run.

## 4. Review the diff

Read the changed code in the worktree, not just the patch. Look for, in order:

1. **Correctness**: wrong conditions, unhandled `DoesNotExist`, race conditions around job claiming
   (`select_for_update`), status transitions, off-by-one in offsets/pagination.
2. **Security**: if the diff touches `ci/webhook.py`, `ci/github/`, `ci/gitlab/`, `ci/oauth_api.py`,
   `ci/Permissions.py`, `ci/ajax/`, `ci/client/` or result serving, delegate to the `security-reviewer`
   agent and fold its findings in.
3. **Tests**: new behavior and error paths covered; if lines are missing, say which and suggest the
   `coverage-gatekeeper` agent rather than writing tests yourself.
4. **Conventions** (`project-conventions` skill): no committed migrations, nothing edited under
   `ci/static/third_party/`, new git-server behavior added to `GitAPI` *and* both the GitHub and GitLab
   implementations, status/comment/label updates enqueued through `ci/tasks.py` rather than called inline,
   authorization via `ci/Permissions.py`.
5. **Scope**: unrelated changes, drive-by reformatting, dependency bumps outside `pyproject.toml` pins.

## 5. Report

Lead with a verdict (approve / approve with nits / changes requested) and the CI-check results from step 3
(what you ran, and what you did not). Then findings ordered by severity, each with `file:line`, the
concrete failure scenario, and a suggested fix. Distinguish what you verified by running code from what
you inferred from reading. If the PR is clean, say so briefly rather than inventing nits.

## 6. Clean up

```bash
cd <repo root> && git worktree remove /tmp/civet-review-$PR
```

The gitignored migrations and `.coverage` files don't block the removal. If it refuses, run
`git -C /tmp/civet-review-$PR status --short` and look before adding `--force`. A full test run leaves an
untracked `out.json` (written by `test_commands.py` via `dump_latest`), which is safe to discard; anything else
is a change you made, so check it first.

The tests also need `distutils`, which Python 3.13 removed, for `client/JobRunner.py`. If the client test modules
fail with `No module named 'distutils'`, run `uv pip install --python <repo root>/.venv/bin/python setuptools`.
