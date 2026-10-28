---
name: run-civet
description: Run, start, build, smoke-test, or drive the CIVET Django server locally. Seeds a throwaway sqlite DB, starts the server, and plays the job client protocol with curl to confirm a change works in the real app (not just unit tests).
---

CIVET is a Django server plus a separate polling client. The server is driven over HTTP, so the driver is
`curl` wrapped in `smoke.sh`: it builds a fresh DB, seeds a job, starts the server, then acts as the client
(claim job, run a step, finish) and checks the pages that render the result. All paths are relative to the
repo root.

## Prerequisites

Python 3.13 and `uv`. `pyproject.toml` has no `project.version`, so `uv pip install -r pyproject.toml`
fails; extract the pinned list instead:

```bash
uv venv --python 3.13 .venv
.venv/bin/python -c "
import tomllib
p=tomllib.load(open('pyproject.toml','rb'))['project']
print('\n'.join(p['dependencies']+p['optional-dependencies']['test']))" > /tmp/civet-requirements.txt
uv pip install --python .venv/bin/python -r /tmp/civet-requirements.txt
```

## Run (agent path)

```bash
.claude/skills/run-civet/smoke.sh
```

It deletes `db.sqlite3`, runs `makemigrations` + `migrate`, seeds with `seed.py`, serves on
`127.0.0.1:8765`, and prints one `ok`/`FAIL` line per check, ending in `SMOKE PASSED` or `SMOKE FAILED`.
The server log is `/tmp/civet-server.log`. `KEEP=1` leaves the server running afterwards so you can curl
other pages (`pkill -f "runserver 127.0.0.1:8765"` to stop it); `PORT=` changes the port.

To drive a different flow, copy the `post`/`check` lines in `smoke.sh`. Client endpoints are plain JSON POSTs
authenticated by the `build_key` in the URL (see `ci/client/urls.py` for shapes), for example:

```bash
curl -s -X POST http://127.0.0.1:8765/client/get_job/ -d '{"client_name":"smoke","build_keys":[<key>],"build_configs":["testBuildConfig"]}'
```

## Direct invocation (no server)

Most changes can be checked without the server. Seeding uses the test factories, so you can do the same
in a shell: `PYTHONPATH=.:.claude/skills/run-civet DJANGO_SETTINGS_MODULE=dev_settings .venv/bin/python`
then `import django; django.setup()` and `from ci.tests import utils`.

## Tests

```bash
make test ci.tests.test_models        # needs .venv on PATH: export PATH=$PWD/.venv/bin:$PATH
```

## Gotchas

- **`civet.settings` can't serve as-is.** `DEBUG=False` with empty `ALLOWED_HOSTS` makes `runserver` exit with
  `You must set settings.ALLOWED_HOSTS if DEBUG is False`, and `SESSION_COOKIE_SECURE=True` breaks sessions
  over http. `dev_settings.py` in this skill overlays the real settings; select it with
  `DJANGO_SETTINGS_MODULE=dev_settings` and `PYTHONPATH=.:.claude/skills/run-civet`.
- **Seeded git server must be named `github.com`.** The factory default is `dummy_git_server`, which is not in
  `INSTALLED_GITSERVERS`, so every page that checks permissions 500s with
  `OAuthException: Git server dummy_git_server (GitHub) is not configured`.
- **Anonymous viewers see 404 for everything** unless the repo is `active=True` *and* public. `dev_settings.py`
  sets `public_default=True`; `seed.py` creates the repo active. A 404 on `/job/1/` here means visibility, not a
  missing job.
- **`/pr/<id>/` 404s for a PR with no events.** The `create_event` factory doesn't link the PR, so `seed.py`
  sets `ev.pull_request` itself.
- **`/job_results/<id>/` returns 403 anonymously.** That's expected and the smoke test asserts it.
- **Migrations are gitignored**, so a fresh checkout or worktree has no tables until `makemigrations` runs
  (symptom: `no such table: ci_client`).
- **macOS `sed -i` needs a suffix argument** (`sed -i ''`); use the Edit tool for in-place edits.
- `GET /static/ci/js/` (a directory URL) returns 500 under `runserver --insecure`. I didn't dig into why; request
  real files instead.
- Background tasks use the immediate backend only under `manage.py test`. The real server enqueues them to the DB,
  and they only run under `./manage.py db_worker`. The smoke test never starts a worker, so it doesn't exercise
  the git-server status updates.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pyproject.toml is using the [project] table, but ... project.version` | Use the `tomllib` extraction above |
| `CommandError: You must set settings.ALLOWED_HOSTS` | Use `dev_settings` (smoke.sh does) |
| `Git server ... is not configured` (500) | Server name must equal `github.com` |
| `no such table: ci_...` | `.venv/bin/python manage.py makemigrations && .venv/bin/python manage.py migrate` |
| `ruff: command not found` / `pyflakes: command not found` | Use `.venv/bin/ruff`; each shell call starts without the venv on `PATH` |
