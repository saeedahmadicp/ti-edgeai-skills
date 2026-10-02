---
name: ti-edgeai-generate-config
description: >
  Build, validate and run edgeai-gst-apps YAML configs (inputs, models, outputs, flows) on TI Edge AI boards with a C7x/MMA
  accelerator (TDA4VM, AM68A, AM69A, AM67A, AM62A): video file, image sequence, USB webcam, CSI camera, RTSP or test-pattern
  input; one or several models; display with FPS overlay, saved video/images, network stream or fakesink; mosaic layouts.
  Use this skill whenever the user wants to "run my model on the TI board", show live results on a display, use a webcam or
  camera with the TI demo app, record annotated video, stream detections, write an app_config / edgeai-gst-apps yaml, or asks
  how the TI GStreamer pipeline (tiovxmultiscaler, tiovxdlpreproc, kmssink) is assembled - even if they never say "config".
license: MIT
metadata:
  version: 0.1.0
  tested_on: "TDA4VM, Edge AI SDK 11.0: image, video, classification, two-model mosaic and USB-webcam-to-file runs. Display output not confirmed"
---

# Configs and Runs for edgeai-gst-apps

When this skill is active, **read `references/config-schema.md` before writing a config by hand** and run `scripts/validate_config.py`
before touching the board. Prerequisites and shared rules (SoC key, `[H, W]` order, display ownership): `ti-edgeai-dev`. The model
folder must already exist on the board (`ti-edgeai-import-model`).

## Principles
1. **Minimal first.** Build the smallest working config (one input, one model, one output) and add mosaics, overlays or extra flows
   only when asked.
2. **Finite input for the first run** (image sequence or video file, file output): it ends by itself and can be checked.
3. **Look at the output.** "exit 0" is not a result; open a frame and check boxes, aspect and labels.
4. **Say what ran.** Report the input kind, config, log evidence, and what was not confirmed.

## Workflow

1. **Collect requirements** (infer from the request, ask only for the unknowns): input kind and its *real* mode, model folder(s),
   output kind, display size, how long to run.
   - Camera: discover it, do not assume a node number: `BOARD=root@<board-ip> scripts/discover_cameras.sh` (capture nodes, card names,
     formats and sizes; codec nodes skipped) and choose a mode the camera really offers. Prefer the mode whose aspect matches the model input (16:9 -> 640x360 for a 640x352 model).
     Codec nodes (hardware decoder/encoder) are not cameras; the discovery script skips them. YUYV-only webcams need `format: auto`
     (not `jpeg`).
   - Output size must be <= input size (the app exits otherwise).
2. **Generate**: `python3 scripts/generate_config.py --input usb --source /dev/video<N> --width 640 --height 360 --format auto
   --model /opt/model_zoo/<model> --viz-threshold 0.3 --output display --perf-overlay graph -o my.yaml`
   (several `--model` flags tile them with mosaic rectangles). Edit by hand for anything the generator does not expose;
   `references/config-schema.md` lists every key.
3. **Validate**: `python3 scripts/validate_config.py my.yaml --board root@<board-ip>` (schema, name references, size/mosaic rules, and
   a read-only SSH check that each model folder has param.yaml, dataset.yaml and a compiled net.bin). Fix every ERROR.
4. **Install and run**, look at the output, report what you saw.

## Running

Finite input, saved output (the safe first test; `GST_SOC` is the SoC key from `ti-edgeai-dev/references/platforms.md`):
```bash
scp my.yaml root@<board-ip>:/opt/edgeai-gst-apps/configs/
ssh root@<board-ip> 'cd /opt/edgeai-gst-apps/apps_python && export SOC=<GST_SOC> TERM=xterm &&
   timeout 120 ./app_edgeai.py ../configs/my.yaml > /tmp/run.log 2>&1; echo exit=$?;
   grep -aE "VX_ZONE_ERROR\]|rror|Fail" /tmp/run.log | grep -v -e curses -e setupterm'
```
Success: `exit=0`, `Offloaded Nodes - N, Total Nodes - N`, output files present (`ls /opt/edgeai-test-data/output`). Then `scp` a frame
back and look at it. Delete test outputs afterwards (small disk).

Camera to saved frames: the same with `timeout -s INT 25` (cameras never finish; exit 124 is normal).

Live on a display. This changes the board's system state (the stock GUI is stopped and a transient unit is started), so:
1. **Get explicit authorization first.** Say exactly what you will do and what the user will lose on screen, and wait for a yes.
   Do not stop `edgeai-init` on inference from an earlier request such as "show it on the display". The user must also be present
   to watch.
2. **Record the original state** and keep it in your report: `systemctl is-active edgeai-init; systemctl is-enabled edgeai-init`
   (and whether `edgeai-demo` already exists).
3. Run (only after the yes):
```bash
ssh root@<board-ip> 'systemctl stop edgeai-init'     # the stock GUI owns the screen
ssh root@<board-ip> 'systemd-run --unit=edgeai-demo --setenv=SOC=<GST_SOC> --setenv=TERM=xterm \
   --setenv=PYTHONPATH=/usr/lib/python3.12/site-packages --working-directory=/opt/edgeai-gst-apps/apps_python \
   script -qfc "./app_edgeai.py ../configs/my_display.yaml" /dev/null'
ssh root@<board-ip> 'systemctl is-active edgeai-demo'      # confirm it is alive
```
4. **Restore on every exit path** (done, failed, or the user asks to stop): `systemctl stop edgeai-demo; systemctl start edgeai-init`
   (only if it was active before), then check `systemctl is-active edgeai-init` and report the state you left the board in.
Why a unit: the status screen needs a tty (`script` provides one) and `nohup &` children of an ssh command are killed when it ends.
The same consent rule covers firmware updates, reboots and USB/driver resets (`ti-edgeai-dev`, critical rule 11).

**Display status: not confirmed.** With the stock GUI running, a display-sink run showed nothing on screen; after stopping it the
app ran as a unit without errors, but a picture was never confirmed. Report display runs as unconfirmed until the user says they
see video; if the screen stays blank check `/sys/class/drm/card*-*/status` and the `connector:` option
(`references/camera-and-display.md`).

## Pipeline sanity
With the right `SOC` the app builds `tiovxdlcolorconvert ! tiovxmultiscaler -> {full-res branch, tiovxdlpreproc branch}`. Print it:
`grep -a "multifilesrc\|v4l2src\|tiovx" /tmp/run.log | cut -c1-300`. `videoscale ! videoconvert` means the ARM-only path (missing `SOC`).
Details: `references/pipeline-anatomy.md`.

## Reference Documents
| File | Use when |
|---|---|
| [references/config-schema.md](references/config-schema.md) | every config key and rule |
| [references/pipeline-anatomy.md](references/pipeline-anatomy.md) | elements, tracers, OpTIFlow, C++ app |
| [references/camera-and-display.md](references/camera-and-display.md) | device discovery, formats, display ownership, USB failure modes |

## Files
- `scripts/generate_config.py`, `scripts/validate_config.py`: PyYAML-serialized output; validator checks types and ranges (unit-tested).
- `scripts/discover_cameras.sh`: read-only V4L2 capture-device discovery (unit-tested with a simulated v4l2-ctl; not run on a board).
- `assets/example_{image,video,classification,mosaic,webcam,webcam_display}.yaml`: starting points using TI zoo models (adapt model paths).
