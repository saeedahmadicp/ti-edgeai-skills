# Board access, services and peripherals (Edge AI Linux SDK images)

The Edge AI SDK Linux image has the same layout on every supported SoC. Concrete numbers (disk size, clocks, connector names)
below are examples from a TDA4VM on SDK 11.0; read them from your own board.

## Access
- SSH as root (default image has no password): `ssh root@<board-ip>`; `scp -r <model-folder> root@<board-ip>:/opt/model_zoo/`.
- The root filesystem is small (13 GB, a few GB free in the example). A compiled detector folder is tens of MB. Check `df -h /`.
- `/tmp` is tmpfs. Annotated-frame outputs at 30 fps fill the disk quickly: clean `/opt/edgeai-test-data/output/*` after tests.

## Services and processes that matter
| Item | Notes |
|---|---|
| `edgeai-init.service` | "EdgeAI OOB demos": starts the stock GUI (`edgeai-gui-app -platform linuxfb`) on the display at boot. `systemctl stop edgeai-init` frees the display; `systemctl start edgeai-init` restores it. Stopping it needs the owner's authorization; record `systemctl is-active/is-enabled edgeai-init` first and restore it afterwards. |
| Background runs | On the tested image, processes started with `nohup ... &` inside an ssh command were killed when the command ended (session cleanup; behaviour depends on the image's systemd settings). Use `systemd-run --unit=<name> --setenv=SOC=<gst key> --setenv=TERM=xterm --setenv=PYTHONPATH=/usr/lib/python3.12/site-packages --working-directory=/opt/edgeai-gst-apps/apps_python script -qfc "./app_edgeai.py ../configs/<cfg>.yaml" /dev/null`; stop with `systemctl stop <name>`. `script` supplies the tty the app's status screen needs. |
| Python env | `export PYTHONPATH=/usr/lib/python3.12/site-packages` for scripts using onnxruntime-tidl / cv2 / numpy (path depends on the image's Python). |
| Accelerator clocks | `k3conf` reads/sets clocks; the C7x remote log prints `CPU Frequency` (1 GHz on the example TDA4VM). |

## Display
- `cat /sys/class/drm/card*-*/status` shows connectors; `modetest -M tidss -c` lists connector/CRTC ids.
- App output size cannot exceed the input size, so a 640x360 camera mode gives a 640x360 picture.
- `kmssink` options (`connector:`) pick the display. Display output needs the stock GUI stopped (see above). End-to-end display output
  has not been confirmed on screen in this repository's tests.

## Cameras
- USB webcams appear as `/dev/videoN` (N>=2); `/dev/video0` and `/dev/video1` are the hardware decoder and encoder.
  Use `v4l2-ctl --list-devices` and `v4l2-ctl -d /dev/videoN --list-formats-ext`.
- Some UVC webcams offer only uncompressed YUYV (no MJPEG) and trade resolution for frame rate (an example unit: 640x360@30,
  960x544@15, 1280x720@10). Use `format: auto` and pick the mode from `--list-formats-ext`.
- Stock configs use `/dev/video-usb-cam0` / `/dev/video-imx219-cam0` udev symlinks made by
  `/opt/edgeai-gst-apps/scripts/setup_cameras.sh`; use the raw `/dev/videoN` when the links do not exist.
- CSI sensors (IMX219, IMX390, OV5640...) are set up by `setup_cameras.sh` (media-ctl routes/formats). Not tested here.
- If no camera appears after boot and `dmesg` shows `usbN-portM: Cannot enable`, the USB hub did not enumerate: power-cycle with the
  camera attached. Do not unbind/rebind host-controller drivers remotely without the owner's OK.

## Logs
- Application: stdout/stderr of `app_edgeai.py`; GStreamer tracer files via `GST_DEBUG_FILE`.
- C7x/MCU: `source /opt/vision_apps/vision_apps_init.sh` then `/opt/vx_app_arm_remote_log.out &` (accelerator messages do not print
  without it). For a failed model load the app-side `TIVX_CMD_NODE_CREATE failed` line was the useful one.
- Boot-time hardware: `dmesg`, `/sys/kernel/debug/remoteproc/remoteproc*/trace0` (Sciserver/PSDK version banner).
