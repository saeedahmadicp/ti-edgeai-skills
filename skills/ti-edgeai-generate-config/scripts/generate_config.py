#!/usr/bin/env python3
"""Generate an edgeai-gst-apps YAML config (inputs / models / outputs / flows) for a TI Edge AI board.

Examples
  # USB webcam -> detector -> HDMI display with FPS graph
  generate_config.py --input usb --source /dev/video<N> --width 640 --height 360 --format auto \
      --model /opt/model_zoo/ONR-OD-9001-x --viz-threshold 0.3 --output display --perf-overlay graph

  # video file -> two models side by side -> saved video
  generate_config.py --input video --source /opt/edgeai-test-data/videos/video0_1280_768.h264 --width 1280 --height 768 \
      --model /opt/model_zoo/A --model /opt/model_zoo/B --output file --sink /opt/edgeai-test-data/output/out.mkv \
      --out-width 1280 --out-height 720

The result is plain YAML; run validate_config.py on it before copying to /opt/edgeai-gst-apps/configs/.
"""
import argparse
import math
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

INPUT_DEFAULTS = {  # kind -> (source, format, framerate)
    "usb": ("/dev/video-usb-cam0", "auto", 30),
    "csi": ("/dev/video-imx219-cam0", "rggb", 30),
    "video": ("/opt/edgeai-test-data/videos/video0_1280_768.h264", "h264", 30),
    "image": ("/opt/edgeai-test-data/images/%04d.jpg", None, 1),
    "rtsp": ("rtsp://127.0.0.1:8554/stream", None, 30),
    "test": ("videotestsrc", "I420", 30),
}


class _Dumper(yaml.SafeDumper):
    """mappings in block style (one key per line), lists inline: `flow0: [input0, model0, output0, [0, 0, 320, 360]]`"""


_Dumper.add_representer(list, lambda d, data: d.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True))


def clean(pairs):
    """ordered mapping without the unset (None) entries"""
    return {k: v for k, v in pairs if v is not None}


def positive(p, name, value, allow_none=False):
    if value is None and allow_none:
        return
    if value is None or value <= 0:
        p.error(f"{name} must be a positive number (got {value})")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--title", default="Edge AI app")
    p.add_argument("--input", choices=sorted(INPUT_DEFAULTS), required=True)
    p.add_argument("--source", help="device / file / URL (default depends on --input)")
    p.add_argument("--width", type=int, required=True, help="actual input width (must match the camera mode / file)")
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--framerate", type=int)
    p.add_argument("--format", help="jpeg|yuv|raw|auto (camera), h264|h265|auto (video), rggb (CSI), I420 (test)")
    p.add_argument("--subdev-id", help="CSI sensor sub-device, e.g. /dev/v4l-imx219-subdev0")
    p.add_argument("--loop", action="store_true", help="loop file inputs")
    p.add_argument("--model", action="append", required=True, help="model folder; repeat for several models")
    p.add_argument("--viz-threshold", type=float, help="detection score threshold for drawing")
    p.add_argument("--top-n", type=int, help="classification: results to show")
    p.add_argument("--alpha", type=float, help="segmentation: mask blend")
    p.add_argument("--output", choices=["display", "file", "image", "stream", "fakesink"], required=True)
    p.add_argument("--sink", help="path for file/image outputs, e.g. /opt/edgeai-test-data/output/out.mkv or out_%%04d.jpg")
    p.add_argument("--out-width", type=int, help="output width (default: input width; must not exceed the input)")
    p.add_argument("--out-height", type=int)
    p.add_argument("--perf-overlay", choices=["graph", "text"], help="display only")
    p.add_argument("--connector", type=int, help="kmssink display id (from modetest)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8081)
    p.add_argument("--encoding", default="jpeg", choices=["jpeg", "h264", "mp4"])
    p.add_argument("-o", "--out-file", help="write here instead of stdout")
    a = p.parse_args()

    for name, v in (("--width", a.width), ("--height", a.height)):
        positive(p, name, v)
    for name, v in (("--framerate", a.framerate), ("--out-width", a.out_width), ("--out-height", a.out_height),
                    ("--top-n", a.top_n)):
        positive(p, name, v, allow_none=True)
    if not 1 <= a.port <= 65535:
        p.error(f"--port must be 1..65535 (got {a.port})")
    if a.viz_threshold is not None and not 0 <= a.viz_threshold <= 1:
        p.error("--viz-threshold must be between 0 and 1")
    if a.alpha is not None and not 0 <= a.alpha <= 1:
        p.error("--alpha must be between 0 and 1")
    if a.connector is not None and a.connector < 0:
        p.error("--connector must be >= 0")

    src, fmt, fps = INPUT_DEFAULTS[a.input]
    src = a.source or src
    fmt = a.format or fmt
    fps = a.framerate or fps
    ow, oh = a.out_width or a.width, a.out_height or a.height

    inp = [("source", src), ("format", fmt), ("width", a.width), ("height", a.height), ("framerate", fps),
           ("subdev-id", a.subdev_id)]
    if a.input in ("video", "image", "rtsp"):
        inp.append(("loop", a.loop))
    if a.input == "image":
        inp.append(("index", 0))
    if a.input == "test":
        inp.append(("pattern", "ball"))

    out = {"display": [("sink", "kmssink"), ("width", ow), ("height", oh), ("overlay-perf-type", a.perf_overlay),
                       ("connector", a.connector)],
           "file": [("sink", a.sink or "/opt/edgeai-test-data/output/output_video.mkv"), ("width", ow), ("height", oh)],
           "image": [("sink", a.sink or "/opt/edgeai-test-data/output/output_image_%04d.jpg"), ("width", ow),
                     ("height", oh)],
           "stream": [("sink", "remote"), ("width", ow), ("height", oh), ("port", a.port), ("host", a.host),
                      ("encoding", a.encoding)],
           "fakesink": [("sink", "fakesink"), ("width", ow), ("height", oh)]}[a.output]

    n = len(a.model)
    flows = {}
    if n == 1:
        flows["flow0"] = ["input0", "model0", "output0"]
    else:  # several models share the output: tile them in a grid (mosaic)
        cols = math.ceil(math.sqrt(n)); rows = math.ceil(n / cols)
        cw, ch = (ow // cols) & ~1, (oh // rows) & ~1
        if cw <= 0 or ch <= 0:
            p.error(f"output {ow}x{oh} is too small to tile {n} models")
        for i in range(n):
            flows[f"flow{i}"] = ["input0", f"model{i}", "output0", [(i % cols) * cw, (i // cols) * ch, cw, ch]]

    cfg = {"title": a.title,
           "inputs": {"input0": clean(inp)},
           "models": {f"model{i}": clean([("model_path", m), ("viz_threshold", a.viz_threshold), ("topN", a.top_n),
                                          ("alpha", a.alpha)]) for i, m in enumerate(a.model)},
           "outputs": {"output0": clean(out)},
           "flows": flows}
    # built as a mapping and serialized by PyYAML, so titles/paths with quotes, colons or '#' stay valid YAML
    text = "---\n" + yaml.dump(cfg, Dumper=_Dumper, sort_keys=False, default_flow_style=False, width=1000, allow_unicode=True)
    if a.out_file:
        with open(a.out_file, "w") as f:
            f.write(text)
        print(f"wrote {a.out_file}", file=sys.stderr)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
