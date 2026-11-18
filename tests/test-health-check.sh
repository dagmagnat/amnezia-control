#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CASE_DIR=$(mktemp -d /tmp/ac-health-test.XXXXXX)
cleanup(){ rm -f -- "$CASE_DIR/curl" "$CASE_DIR/pass" "$CASE_DIR/fail"; rmdir -- "$CASE_DIR"; }
trap cleanup EXIT
cat >"$CASE_DIR/curl" <<'MOCK'
#!/usr/bin/env bash
printf 'curl: (7) simulated connection refused during startup\n' >&2
exit "${AC_TEST_CURL_EXIT:-0}"
MOCK
chmod +x "$CASE_DIR/curl"
export PATH="$CASE_DIR:$PATH"
AC_TEST_CURL_EXIT=0 bash "$ROOT/scripts/wait-panel.sh" >"$CASE_DIR/pass" 2>&1
[[ $(<"$CASE_DIR/pass") != *'curl:'* ]]
[[ $(<"$CASE_DIR/pass") == *'Panel is ready.'* ]]
if AC_TEST_CURL_EXIT=7 bash "$ROOT/scripts/wait-panel.sh" >"$CASE_DIR/fail" 2>&1; then
    echo 'FAIL: failed readiness check returned success'; exit 1
fi
[[ $(<"$CASE_DIR/fail") == *'Panel failed to start.'* ]]
[[ $(<"$CASE_DIR/fail") == *'curl: (7)'* ]]
[[ $(<"$CASE_DIR/fail") != *'Panel is ready.'* ]]
printf 'PASS: startup retries stay quiet; final failure stays visible and returns nonzero.\n'
