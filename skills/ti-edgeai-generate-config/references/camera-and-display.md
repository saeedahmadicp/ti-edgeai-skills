# Cameras and display (device facts; see ti-edgeai-dev/references/board-and-services.md for the board basics)

## Discover
```bash
ssh root@<ip> 'lsusb; v4l2-ctl --list-devices; ls /dev/video*; for c in /sys/class/drm/card*-*; do echo $c $(cat $c/status) $(head -1 $c/modes); done'
ssh root@<ip> 'v4l2-ctl -d /dev/video<N> --list-formats-ext | head -40'   # or scripts/discover_cameras.sh
```
- A camera that is plugged in but absent from `lsusb` is a hardware/enumeration problem, not a config problem
  (`dmesg | grep -i usb`). Observed once: `usb usb1-port1: Cannot enable. Maybe the USB cable is bad?` after a reboot; replugging while
  the board ran did nothing. Remedy that does not change software: power-cycle the board with the camera attached.
- UVC webcam example (example unit): YUYV only; 640x480@30, 640x360@30, 424x240@30, 800x448@20, 960x544@15, 1280x720@10. Frame rate falls as resolution rises on such cameras.

## Camera config
```yaml
inputs: {input0: {source: /dev/video<N>, format: auto, width: 640, height: 360, framerate: 30}}
```
`format: jpeg` requires an MJPEG camera. For CSI sensors use the template (`rggb`, `subdev-id`) and run `setup_cameras.sh`/`init_script.sh`
first; unverified here.

## Display
- `kmssink` + `overlay-perf-type: graph|text` shows FPS/load on the picture. `connector:` picks the display id (`modetest -M tidss -c`).
- The stock GUI (`edgeai-gui-app -platform linuxfb`, started by `edgeai-init.service`) draws on the same screen. With it running,
  a display run showed nothing for the user. Stop it for tests (`systemctl stop edgeai-init`), run the app as a systemd unit
  (`generate-config SKILL.md`), and restore with `systemctl start edgeai-init`. A successful on-screen picture was NOT confirmed yet.
- Output size must be <= input size: a 640x360 camera mode shows a 640x360 picture on a 1280x800 screen. For a bigger picture use a
  larger camera mode (UVC YUYV drops to 10 fps at 1280x720), or a camera/file input that is larger.
