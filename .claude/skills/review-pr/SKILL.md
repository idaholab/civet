---
name: review-pr
description: Review a CIVET pull request - fetches the PR, checks it out in an isolated worktree, runs fast lint checks, runs tests or the security-reviewer agent only when asked or justified by the diff, and reviews the diff against this repo's conventions. Use when asked to review a PR by number or URL.
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
```

Only if you are going to run tests (step 3), also run `python manage.py makemigrations` in the worktree:
migrations are gitignored, so without it every test fails with "no such table".

## 3. Run only the checks the PR justifies

Tests and security review are slow and CI already runs the whole suite on every PR (`gh pr checks` above), so
do not run them by default. Start from CI's results and what the diff changes, then escalate only as far as
needed. Say in the report what you skipped and why.

**Always (seconds):**

```bash
ruff format --check --diff .
pyflakes $(git ls-files '*.py')
```

**Tests: run only if the user asked for them, or CI's tests are failing/missing, or the diff changes behavior CI
may not cover.** Then pick the narrowest scope:

- Docs, comments, config under `.claude/`, formatting-only or test-only changes: no test run.
- Otherwise `make test <labels for the changed modules>` (`ci/ajax/views.py` -> `ci.ajax.tests.test_views`; see
  the `ci/*/tests` dirs). If CI is green for the same head commit, a scoped run is only worth it to
  reproduce a suspicion, not to re-confirm CI.
- The unscoped `make test`, or `make coverage`, only if the user asked, or the PR changes shared code
  (`ci/models.py`, `ci/views.py`, `Permissions.py`, settings, `ci/tests/utils.py`) *and* CI is not already green.
- Coverage must be **zero missing lines** for the changed files, but CI's coverage gate and the `codecov/patch`
  check already report this; prefer them over a local `make coverage`. If you do run it scoped, ignore files the
  PR did not touch and lines only reachable from other test modules (rerun with the module that covers them
  before reporting). Excluded paths are in `.coveragerc`.
- Tests run under `-Werror`, so a new warning is a real failure.
- Selenium tests only run with `SELENIUM_TEST=1` and need Chrome; only for template/JS changes the user cares
  about, and say they weren't run if Chrome is unavailable.

## 4. Review the diff

Read the changed code in the worktree, not just the patch. Look for, in order:

1. **Correctness**: wrong conditions, unhandled `DoesNotExist`, race conditions around job claiming
   (`select_for_update`), status transitions, off-by-one in offsets/pagination.
2. **Security**: read the diff for security problems yourself first. Delegate to the slow `security-reviewer`
   agent only if the user asked for a security review, or the diff changes how requests are authenticated,
   authorized, signed, parsed or served (`ci/webhook.py`, `ci/github/`, `ci/gitlab/`, `ci/oauth_api.py`,
   `ci/Permissions.py`, `ci/ajax/`, `ci/client/`, result serving) in a non-trivial way. Touching one of those
   paths for a rename, log message, comment or test is not enough. When you skip it, say so in the report.
3. **Tests**: new behavior and error paths covered, judged from the tests in the diff and from CI's coverage
   results. If lines are missing, say which and suggest the `coverage-gatekeeper` agent rather than writing tests
   yourself.
4. **Conventions** (`project-conventions` skill): no committed migrations, nothing edited under
   `ci/static/third_party/`, new git-server behavior added to `GitAPI` *and* both the GitHub and GitLab
   implementations, status/comment/label updates enqueued through `ci/tasks.py` rather than called inline,
   authorization via `ci/Permissions.py`.
5. **Scope**: unrelated changes, drive-by reformatting, dependency bumps outside `pyproject.toml` pins.

## 5. Report

Lead with a verdict (approve / approve with nits / changes requested) and the check results: CI's status for
the head commit, what you ran locally, and what you skipped (tests, coverage, security-reviewer) with the
reason. Offer to run a skipped one if the user wants it. Then findings ordered by severity, each with `file:line`, the
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
