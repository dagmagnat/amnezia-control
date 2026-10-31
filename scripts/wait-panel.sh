#!/usr/bin/env bash
set -Eeuo pipefail
# curl reports every failed retry with --show-error. Keep those messages private
# while the service starts, then show a diagnostic only if all retries fail.
HEALTH_LOG=$(mktemp /tmp/ac-panel-health.XXXXXX)
trap 'rm -f -- "$HEALTH_LOG"' EXIT
printf 'Ожидание запуска панели / Waiting for panel startup…\n'
if curl --fail --silent --show-error --retry 15 --retry-connrefused \
    --retry-delay 1 --retry-max-time 45 --connect-timeout 2 --max-time 5 \
    http://127.0.0.1:8090/api/me >/dev/null 2>"$HEALTH_LOG"; then
    printf 'Панель готова / Panel is ready.\n'
else
    printf 'Панель не запустилась / Panel failed to start.\n' >&2
    tail -n 1 "$HEALTH_LOG" >&2
    printf 'Диагностика / Diagnostics: journalctl -u amnezia-control -n 50 --no-pager\n' >&2
    exit 1
fi
