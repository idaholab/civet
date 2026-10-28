#!/usr/bin/env bash
# PostToolUse hook: format edited Python files with ruff (CI runs `ruff format --check`).
# Silently does nothing if ruff is not installed so it never blocks a session.
file=$(jq -r '.tool_input.file_path // empty')
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0
if command -v ruff >/dev/null 2>&1; then
  ruff format --quiet "$file" || true
fi
exit 0
