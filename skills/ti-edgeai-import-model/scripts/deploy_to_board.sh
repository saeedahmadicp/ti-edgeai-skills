#!/bin/bash
# Copy a packaged model folder (and optionally a config) to a TI Edge AI board and smoke-test it.
#
#   BOARD=root@<board-ip> [GST_SOC=j721e] ./deploy_to_board.sh <model_folder> [config.yaml]
#
# Safety:
#   * Never deletes anything. An existing /opt/model_zoo/<name> or config of the same name is refused unless REPLACE=1;
#     with REPLACE=1 the old one is MOVED to a timestamped ".backup-..." sibling that you can restore or delete yourself.
#   * Uploads go to a staging directory and are moved into place only after the copy and a sanity check succeed.
#   * Both destinations (model folder and config) are checked BEFORE anything is uploaded; a collision changes nothing.
#   * Success needs evidence, not just an exit status: the app log must be non-empty, show `Offloaded Nodes - N, Total Nodes - N`
#     with 0 < N and N == M (zero nodes or zero total is a failure; the model loaded on the accelerator; ALLOW_PARTIAL_OFFLOAD=1 accepts N < M, NO_OFFLOAD_CHECK=1 skips this), and have
#     no known error line. A live run that timed out with an empty log is a failure.
#   * Frames: the log cannot prove frames were processed. Set EXPECT_OUTPUT='/opt/edgeai-test-data/output/out*.jpg' (a remote glob the
#     config writes to) to require at least one file newer than the start of the run.
# Smoke-test semantics (config given):
#   finite input (image sequence / video file): must exit 0 within RUN_SECONDS; exit 124 (timeout) is a FAILURE.
#   live input (camera / RTSP): set LIVE=1; the app is stopped after RUN_SECONDS and exit 124 counts as success if the log
#   shows no error line.
# Variables: BOARD (required), EXPECT_OUTPUT, ALLOW_PARTIAL_OFFLOAD, NO_OFFLOAD_CHECK, GST_SOC (default j721e; see ti-edgeai-dev/references/platforms.md), RUN_SECONDS (90), LIVE (0),
#   REPLACE (0), MODEL_ZOO (/opt/model_zoo), GST_APPS (/opt/edgeai-gst-apps).
# Exit codes: 0 ok; 2 usage/model folder problem; 3 destination exists (use REPLACE=1); 4 copy failed;
#   5 smoke test failed (application exit status or error line in the log).
set -uo pipefail
BOARD=${BOARD:?set BOARD=user@host}
MODEL=${1:?model folder}
CONFIG=${2:-}
RUN_SECONDS=${RUN_SECONDS:-90}
GST_SOC=${GST_SOC:-j721e}
LIVE=${LIVE:-0}
EXPECT_OUTPUT=${EXPECT_OUTPUT:-}
ALLOW_PARTIAL_OFFLOAD=${ALLOW_PARTIAL_OFFLOAD:-0}
NO_OFFLOAD_CHECK=${NO_OFFLOAD_CHECK:-0}
REPLACE=${REPLACE:-0}
MODEL_ZOO=${MODEL_ZOO:-/opt/model_zoo}
GST_APPS=${GST_APPS:-/opt/edgeai-gst-apps}
APP_DIR=$GST_APPS/apps_python
REMOTE_LOG=${REMOTE_LOG:-/tmp/deploy_test.log}
CFG_DIR=${CFG_DIR:-$GST_APPS/configs}
ERR_RE='VX_ZONE_ERROR\]|Create state function failed|Got invalid dimensions|Traceback|Segmentation fault|Bus error|Fail'

[ -f "$MODEL/param.yaml" ] && [ -d "$MODEL/artifacts" ] && [ -d "$MODEL/model" ] || {
  echo "ERROR: $MODEL is not a packaged model folder (needs model/, artifacts/, param.yaml)" >&2; exit 2; }
[ -n "$CONFIG" ] && [ ! -f "$CONFIG" ] && { echo "ERROR: config $CONFIG not found" >&2; exit 2; }
name=$(basename "$MODEL")
stamp=$(date +%Y%m%d-%H%M%S)
stage="$MODEL_ZOO/.incoming-$name-$stamp"

if [ "$REPLACE" != 1 ]; then
  if ssh "$BOARD" "test -e '$MODEL_ZOO/$name'"; then
    echo "ERROR: $BOARD:$MODEL_ZOO/$name already exists. Nothing was changed. Set REPLACE=1 to move it to a .backup- folder and install the new one." >&2
    exit 3
  fi
  if [ -n "$CONFIG" ] && ssh "$BOARD" "test -e '$CFG_DIR/$(basename "$CONFIG")'"; then
    echo "ERROR: config $CFG_DIR/$(basename "$CONFIG") already exists on the board. Nothing was changed. Rename your config or set REPLACE=1 (the old one is kept as a .backup- file)." >&2
    exit 3
  fi
fi

echo "== uploading $name to $BOARD:$stage"
ssh "$BOARD" "mkdir '$stage'" && scp -rq "$MODEL/." "$BOARD:$stage/" || { echo "ERROR: copy failed (the existing model was not touched)" >&2; exit 4; }
ssh "$BOARD" "test -f '$stage/param.yaml' && test -d '$stage/artifacts'" || { echo "ERROR: staged copy incomplete; staging kept at $stage" >&2; exit 4; }
backup=""
if ssh "$BOARD" "test -e '$MODEL_ZOO/$name'"; then
  backup="$MODEL_ZOO/.backup-$name-$stamp"
  ssh "$BOARD" "mv '$MODEL_ZOO/$name' '$backup'" || { echo "ERROR: could not move the old model aside; staging kept at $stage" >&2; exit 4; }
fi
ssh "$BOARD" "mv '$stage' '$MODEL_ZOO/$name'" || { echo "ERROR: could not move the staged copy into place; staging at $stage${backup:+, old model at $backup}" >&2; exit 4; }
echo "== installed $MODEL_ZOO/$name${backup:+ (previous version kept at $backup)}"

if [ -n "$CONFIG" ]; then
  cfg=$(basename "$CONFIG")
  if ssh "$BOARD" "test -e '$CFG_DIR/$cfg'"; then ssh "$BOARD" "mv '$CFG_DIR/$cfg' '$CFG_DIR/.backup-$cfg-$stamp'" || exit 4; fi
  scp -q "$CONFIG" "$BOARD:$CFG_DIR/$cfg" || { echo "ERROR: config copy failed" >&2; exit 4; }
  echo "== running $cfg for up to ${RUN_SECONDS}s (SOC=$GST_SOC is required, otherwise the app silently uses an ARM-only pipeline)"
  [ -n "$EXPECT_OUTPUT" ] && ssh "$BOARD" "touch '$REMOTE_LOG.start'"
  ssh "$BOARD" "cd '$APP_DIR' && export SOC=$GST_SOC TERM=xterm && timeout -s INT $RUN_SECONDS ./app_edgeai.py ../configs/$cfg > $REMOTE_LOG 2>&1"
  rc=$?
  errs=$(ssh "$BOARD" "grep -aE '$ERR_RE' $REMOTE_LOG | grep -v -e curses -e setupterm | head -8 | cut -c1-200")
  logbytes=$(ssh "$BOARD" "wc -c < $REMOTE_LOG" | tr -d ' ')
  offload=$(ssh "$BOARD" "grep -a 'Offloaded Nodes' $REMOTE_LOG | head -1")
  echo "application exit status: $rc; log size: ${logbytes:-0} bytes"
  [ -n "$offload" ] && echo "$offload"
  [ -n "$errs" ] && { echo "error lines in the log:"; echo "$errs"; }
  fail() { echo "RESULT: FAILED ($1)"; exit 5; }
  [ -n "$errs" ] && fail "error lines in the log"
  case $rc in
    0) ;;
    124|130) if [ "$LIVE" != 1 ]; then fail "finite input did not finish within ${RUN_SECONDS}s; raise RUN_SECONDS or use LIVE=1 for camera input"; fi;;
    *) fail "application exit status $rc";;
  esac
  [ "${logbytes:-0}" -gt 0 ] 2>/dev/null || fail "the application log is empty: no evidence the app started"
  if [ "$NO_OFFLOAD_CHECK" != 1 ]; then
    [ -n "$offload" ] || fail "no 'Offloaded Nodes' line in the log: no evidence the model loaded on the accelerator (NO_OFFLOAD_CHECK=1 to skip)"
    n=$(echo "$offload" | sed -n 's/.*Offloaded Nodes *- *\([0-9]*\).*/\1/p'); t=$(echo "$offload" | sed -n 's/.*Total Nodes *- *\([0-9]*\).*/\1/p')
    if [ -z "$n" ] || [ -z "$t" ]; then fail "could not parse the offload line: $offload"; fi
    if [ "$t" -le 0 ] || [ "$n" -le 0 ] || [ "$n" -gt "$t" ]; then fail "implausible offload counts (offloaded $n, total $t): nothing ran on the accelerator"; fi
    if [ "$n" != "$t" ] && [ "$ALLOW_PARTIAL_OFFLOAD" != 1 ]; then fail "only $n of $t nodes were offloaded to the accelerator (ALLOW_PARTIAL_OFFLOAD=1 to accept)"; fi
  fi
  if [ -n "$EXPECT_OUTPUT" ]; then
    out_dir=$(dirname "$EXPECT_OUTPUT"); out_pat=$(basename "$EXPECT_OUTPUT")
    new_files=$(ssh "$BOARD" "find '$out_dir' -maxdepth 1 -name '$out_pat' -newer '$REMOTE_LOG.start' | wc -l" | tr -d ' ')
    [ "${new_files:-0}" -gt 0 ] 2>/dev/null || fail "no output file matching $EXPECT_OUTPUT was written during the run: no evidence frames were processed"
    echo "output files written during the run: $new_files"
  fi
  if [ "$rc" = 0 ]; then echo "RESULT: OK (application finished cleanly)"
  else echo "RESULT: OK (live input ran until the ${RUN_SECONDS}s timeout; model loaded, no error lines)"; fi
  [ -n "$EXPECT_OUTPUT" ] || echo "NOTE: frame processing was not verified (the log only shows the model loaded); set EXPECT_OUTPUT to check an output file"
fi
exit 0
