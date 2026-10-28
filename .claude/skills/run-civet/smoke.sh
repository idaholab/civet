#!/usr/bin/env bash
# Drives a real CIVET server: fresh sqlite DB, seeded job, then plays the client protocol with curl
# (get_job -> start/update/complete step -> job_finished) and checks the pages that render the result.
# Run from the repo root: .claude/skills/run-civet/smoke.sh   (set KEEP=1 to leave the server running)
set -u
cd "$(git rev-parse --show-toplevel)"

PORT=${PORT:-8765}
B=http://127.0.0.1:$PORT
PY=.venv/bin/python
export PYTHONPATH=.:.claude/skills/run-civet DJANGO_SETTINGS_MODULE=dev_settings
LOG=${LOG:-/tmp/civet-server.log}
fail=0

check() { # name expected actual
  if [ "$2" = "$3" ]; then echo "ok   $1 ($3)"; else echo "FAIL $1: expected $2, got $3"; fail=1; fi
}

pkill -f "runserver 127.0.0.1:$PORT" 2>/dev/null; sleep 1
rm -f db.sqlite3
$PY manage.py makemigrations >/dev/null 2>&1 || { echo "makemigrations failed"; exit 1; }
$PY manage.py migrate >/dev/null 2>&1 || { echo "migrate failed"; exit 1; }
SEED=$($PY .claude/skills/run-civet/seed.py 2>&1 | tail -1)
KEY=$(echo "$SEED" | sed -E 's/build_key=([0-9]+).*/\1/')
case "$KEY" in ''|*[!0-9]*) echo "seed failed: $SEED"; exit 1;; esac

$PY manage.py runserver 127.0.0.1:$PORT --noreload --insecure >"$LOG" 2>&1 &
SERVER=$!
[ -z "${KEEP:-}" ] && trap 'kill $SERVER 2>/dev/null' EXIT
for _ in $(seq 20); do curl -s -o /dev/null $B/robots.txt && break; sleep 0.5; done

C=smoke
post() { curl -s -X POST "$B$1" -d "$2"; }
claim=$(post /client/get_job/ "{\"client_name\":\"$C\",\"build_keys\":[$KEY],\"build_configs\":[\"testBuildConfig\"]}")
check "get_job claims job 1" 1 "$(echo "$claim" | $PY -c 'import json,sys;print(json.load(sys.stdin)["job_id"])')"
check "start_step" OK "$(post /client/start_step_result/$KEY/$C/1/ '{"step_num":0,"output":"","time":0,"complete":false,"exit_status":0}' | $PY -c 'import json,sys;print(json.load(sys.stdin)["status"])')"
check "complete_step" OK "$(post /client/complete_step_result/$KEY/$C/1/ '{"step_num":0,"output":"hello from smoke\nall done\n","time":2,"complete":true,"exit_status":0}' | $PY -c 'import json,sys;print(json.load(sys.stdin)["status"])')"
check "job_finished" OK "$(post /client/job_finished/$KEY/$C/1/ '{"seconds":2,"complete":true}' | $PY -c 'import json,sys;print(json.load(sys.stdin)["status"])')"

for p in / /job/1/ /event/1/ /pr/1/ /repo/1/ /clients/ /events/; do
  check "GET $p" 200 "$(curl -s -o /dev/null -w '%{http_code}' $B$p)"
done
check "job page shows Passed" yes "$(curl -s $B/job/1/ | grep -q Passed && echo yes || echo no)"
check "anonymous results download is forbidden" 403 "$(curl -s -o /dev/null -w '%{http_code}' $B/job_results/1/)"
check "server tracebacks" 0 "$(grep -c Traceback "$LOG")"

[ $fail = 0 ] && echo "SMOKE PASSED" || { echo "SMOKE FAILED (log: $LOG)"; exit 1; }
