#!/bin/bash
# Run an Edge AI app config on the board with the GStreamer latency tracer and print per-element latency/FPS.
#
#   BOARD=root@<board-ip> [GST_SOC=j721e] ./trace_pipeline.sh <config.yaml on the board, e.g. ../configs/my_video.yaml> [seconds]
#
# TI's parser redraws a table every second and only stops on SIGINT, so it is run for 8 s and the last table is shown.
# Uses TI's parser (/opt/edgeai-gst-apps/scripts/gst_tracers/parse_gst_tracers.py). Use a config with a finite or
# file/camera input and a non-display sink (file or fakesink) so the measurement is not limited by the display.
set -euo pipefail
BOARD=${BOARD:?set BOARD=user@host}
GST_SOC=${GST_SOC:-j721e}   # edgeai-gst-apps SoC key for your board (see ti-edgeai-dev/references/platforms.md)
CFG=${1:?config path on the board (relative to /opt/edgeai-gst-apps/apps_python)}
SECS=${2:-30}
ssh "$BOARD" "cd /opt/edgeai-gst-apps/apps_python && export SOC=$GST_SOC TERM=xterm && rm -f /run/trace.log && \
  GST_DEBUG_FILE=/run/trace.log GST_DEBUG_NO_COLOR=1 GST_DEBUG='GST_TRACER:7' GST_TRACERS='latency(flags=element)' \
  timeout -s INT $SECS ./app_edgeai.py $CFG > /tmp/trace_run.log 2>&1; \
  ls -la /run/trace.log | cut -c1-80; \
  (TERM=xterm timeout -s INT 8 /opt/edgeai-gst-apps/scripts/gst_tracers/parse_gst_tracers.py /run/trace.log 2>&1 || true) | \
  python3 -c 'import sys; L=sys.stdin.read().splitlines(); i=max((k for k,l in enumerate(L) if l.startswith(\"|element\")), default=None); \
print(chr(10).join(L[i-1:next(k for k in range(i+2,len(L)) if L[k].startswith(\"+--\"))+1]) if i is not None else \"no tracer output; was GST_TRACERS honoured?\")'; rm -f /run/trace.log"
