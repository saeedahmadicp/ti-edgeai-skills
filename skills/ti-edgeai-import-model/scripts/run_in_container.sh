#!/bin/bash
# Run a command inside the TIDL tools container (built from Dockerfile.tidl-tools) with the TIDL environment set up.
#   TIDL_TAG   edgeai-tidl-tools tag the image was built with (a release TI lists as compatible with the board SDK)   default 11_00_06_00
#   TOOLS_SOC  tools SoC the image was built for: am68pa (TDA4VM/J721E), am68a, am69a, am62a, am67a   default am68pa
#   IMAGE      image name; default ti-tidl-tools:$TIDL_TAG-$TOOLS_SOC
#   WORKDIR=/path/to/project ./run_in_container.sh "python3 compile_tidl.py --model ... "
# WORKDIR is mounted at the SAME absolute path inside the container (so absolute paths and dataset symlinks
# keep working) and is the working directory. Set OUT_DIR to chown generated files back to you.
# --shm-size=4g is required: with Docker's 64 MB default the TIDL import tool dies with "Bus error".
set -e
TIDL_TAG=${TIDL_TAG:-11_00_06_00}
TOOLS_SOC=${TOOLS_SOC:-am68pa}
IMAGE=${IMAGE:-ti-tidl-tools:$TIDL_TAG-$TOOLS_SOC}
SOC_UP=$(echo "$TOOLS_SOC" | tr a-z A-Z)
WORKDIR=${WORKDIR:-$PWD}
MOUNTS=${EXTRA_MOUNTS:-}          # e.g. EXTRA_MOUNTS="-v /data:/data" if data lives outside WORKDIR
SCRIPTS=$(cd "$(dirname "$0")" && pwd)   # mounted read-only at the same path so $SCRIPTS/compile_tidl.py works inside
T=/opt/edgeai-tidl-tools/tools
docker run --rm --shm-size=4g -v "$WORKDIR:$WORKDIR" -v "$SCRIPTS:$SCRIPTS:ro" $MOUNTS -w "$WORKDIR" \
  -e SCRIPTS="$SCRIPTS" -e TIDL_TOOLS_PATH=$T/$SOC_UP/tidl_tools -e SOC=$TOOLS_SOC \
  -e LD_LIBRARY_PATH=$T/$SOC_UP/tidl_tools:$T/osrt_deps:$T/osrt_deps/opencv_4.2.0_x86_u22/opencv/ \
  "$IMAGE" bash -c "test -d \"\$TIDL_TOOLS_PATH\" || { echo \"ERROR: \$TIDL_TOOLS_PATH missing in image $IMAGE (built for another TOOLS_SOC/TIDL_TAG?)\" >&2; exit 97; }; $*; rc=\$?; chown -R $(id -u):$(id -g) '${OUT_DIR:-$WORKDIR}' 2>/dev/null; exit \$rc"
