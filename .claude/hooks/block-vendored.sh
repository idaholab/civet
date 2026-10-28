#!/usr/bin/env bash
# PreToolUse hook: refuse edits to vendored third-party static assets.
file=$(jq -r '.tool_input.file_path // empty')
case "$file" in
  */ci/static/third_party/*)
    echo "Blocked: $file is a vendored third-party asset (ci/static/third_party). Do not edit it directly." >&2
    exit 2
    ;;
esac
exit 0
