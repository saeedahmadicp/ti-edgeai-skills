#!/bin/bash
# List the V4L2 capture devices (cameras) with their card name and offered formats / sizes, so configs use what the camera really
# provides instead of an assumed /dev/videoN. Memory-to-memory nodes (hardware decoder / encoder) are skipped.
#
#   BOARD=root@<board-ip> ./discover_cameras.sh        # query the board over ssh
#   ./discover_cameras.sh                              # run on the board itself
# Read-only: it only calls v4l2-ctl.
run() { if [ -n "${BOARD:-}" ]; then ssh "$BOARD" "$1"; else bash -c "$1"; fi; }
run '
found=0
for d in /dev/video*; do
  [ -e "$d" ] || continue
  info=$(v4l2-ctl -d "$d" --all 2>/dev/null) || continue
  echo "$info" | grep -q "Memory-to-Memory" && continue
  echo "$info" | grep -q "Video Capture" || continue
  found=1
  card=$(echo "$info" | sed -n "s/^[[:space:]]*Card type[[:space:]]*:[[:space:]]*//p" | head -1)
  echo "== $d  card: ${card:-unknown}"
  v4l2-ctl -d "$d" --list-formats-ext 2>/dev/null | grep -E "\[[0-9]+\]|Size:|Interval" | head -40
done
[ "$found" = 1 ] || echo "no V4L2 capture device found (check: lsusb, dmesg | grep -i usb, ls /dev/video*)"
'
