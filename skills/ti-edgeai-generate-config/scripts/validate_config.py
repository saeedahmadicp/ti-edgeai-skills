#!/usr/bin/env python3
"""Validate an edgeai-gst-apps YAML config before running it on the board.

Checks (errors unless noted):
  * the file parses as YAML and is a mapping; sections inputs/models/outputs/flows exist and are non-empty mappings of mappings
  * required keys and TYPES: source/sink/model_path non-empty strings; width/height positive integers; framerate positive number;
    viz_threshold and alpha in [0, 1]; topN positive integer; port 1..65535; connector >= 0; loop boolean
  * flows are [input, model, output] or [input, model, output, [x,y,w,h]] and reference defined names
  * mosaic = four integers, x/y >= 0, w/h > 0, fully inside the output   (the app exits with "Mosaic is not with in the background buffer")
  * flow output size <= input size            (the app exits with "Flow output resolution can not be greater...")
  * several flows on one output need mosaic rectangles
  * image inputs/outputs contain a %0Nd pattern; video sinks end in .mkv/.mp4/.mov
  * even width/height for tiovx scaling       (warning)
  * with --board user@host: model folder exists on the board with param.yaml, dataset.yaml, artifacts/*_net.bin (SSH, read-only)
Exit code 0 = no errors. Every problem is reported once with the key path, never as a traceback.
"""
import argparse
import re
import shlex
import subprocess
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

errors, warnings = [], []
err = errors.append
warn = warnings.append


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def need_str(where, d, key):
    if key not in d:
        err(f"{where}: missing '{key}'")
        return None
    v = d[key]
    if not isinstance(v, str) or not v.strip():
        err(f"{where}.{key}: must be a non-empty string (got {v!r})")
        return None
    return v


def positive_int(where, d, key, required=True):
    if key not in d:
        if required:
            err(f"{where}: missing '{key}'")
        return None
    v = d[key]
    if not is_int(v) or v <= 0:
        err(f"{where}.{key}: must be a positive integer (got {v!r})")
        return None
    return v


def in_range(where, d, key, lo, hi):
    if key in d and d[key] is not None and (not is_num(d[key]) or not lo <= d[key] <= hi):
        err(f"{where}.{key}: must be a number between {lo} and {hi} (got {d[key]!r})")


def check_input(name, d):
    where = f"inputs.{name}"
    src = need_str(where, d, "source") or ""
    w = positive_int(where, d, "width")
    h = positive_int(where, d, "height")
    if "framerate" in d and (not is_num(d["framerate"]) or d["framerate"] <= 0):
        err(f"{where}.framerate: must be a positive number (got {d['framerate']!r})")
    if "loop" in d and not isinstance(d["loop"], bool):
        err(f"{where}.loop: must be true/false (got {d['loop']!r})")
    if "format" in d and d["format"] is not None and not isinstance(d["format"], str):
        err(f"{where}.format: must be a string (got {d['format']!r})")
    if src.endswith((".jpg", ".png")) and not re.search(r"%0?\d*d", src):
        err(f"{where}: image source needs a %0Nd pattern, e.g. /dir/%04d.jpg")
    if src.startswith("/dev/video") and d.get("format") == "jpeg":
        warn(f"{where}: format jpeg requires an MJPEG camera; use 'auto' for YUYV-only webcams (check v4l2-ctl --list-formats-ext)")
    for k, v in (("width", w), ("height", h)):
        if v and v % 2:
            warn(f"{where}: odd {k}; tiovxmultiscaler does not support odd resolutions")


def check_output(name, d):
    where = f"outputs.{name}"
    sink = need_str(where, d, "sink") or ""
    positive_int(where, d, "width")
    positive_int(where, d, "height")
    if "port" in d and (not is_int(d["port"]) or not 1 <= d["port"] <= 65535):
        err(f"{where}.port: must be an integer 1..65535 (got {d['port']!r})")
    if "host" in d and (not isinstance(d["host"], str) or not d["host"].strip()):
        err(f"{where}.host: must be a non-empty string (got {d['host']!r})")
    if "connector" in d and (not is_int(d["connector"]) or d["connector"] < 0):
        err(f"{where}.connector: must be an integer >= 0 (got {d['connector']!r})")
    if sink.endswith((".jpg", ".png")) and not re.search(r"%0?\d*d", sink):
        err(f"{where}: image sink needs a %0Nd pattern, e.g. /dir/out_%04d.jpg")
    if "." in sink.rsplit("/", 1)[-1] and not sink.endswith((".jpg", ".png", ".mkv", ".mp4", ".mov")):
        err(f"{where}: unsupported sink file type '{sink}'")
    if d.get("overlay-perf-type") not in (None, "graph", "text"):
        err(f"{where}: overlay-perf-type must be graph or text")
    if d.get("encoding") not in (None, "jpeg", "h264", "mp4"):
        err(f"{where}: encoding must be jpeg, h264 or mp4")


def check_model(name, d):
    where = f"models.{name}"
    need_str(where, d, "model_path")
    in_range(where, d, "viz_threshold", 0, 1)
    in_range(where, d, "alpha", 0, 1)
    if "topN" in d and (not is_int(d["topN"]) or d["topN"] <= 0):
        err(f"{where}.topN: must be a positive integer (got {d['topN']!r})")


def check_model_remote(name, path, board):
    q = shlex.quote(path)
    cmd = ["ssh", board, f"test -f {q}/param.yaml && test -f {q}/dataset.yaml && "
           f"ls {q}/artifacts/*_net.bin >/dev/null 2>&1 && echo OK || echo MISSING"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    if out != "OK":
        err(f"models.{name}: {path} on {board} lacks param.yaml, dataset.yaml or artifacts/*_net.bin")


def size(d, key):
    v = d.get(key)
    return v if is_int(v) and v > 0 else None


def check_flows(ins, models, outs, flows):
    per_output = {}
    for n, f in flows.items():
        where = f"flows.{n}"
        if not isinstance(f, list) or len(f) not in (3, 4):
            err(f"{where}: expected [input, model, output] or [input, model, output, [x,y,w,h]]")
            continue
        i, m, o = f[:3]
        bad_ref = False
        for kind, key in (("input", i), ("model", m), ("output", o)):
            if not isinstance(key, str):
                err(f"{where}: the {kind} reference must be a name (string), got {key!r}")
                bad_ref = True
        if bad_ref:
            continue
        for kind, key, table in (("input", i, ins), ("model", m, models), ("output", o, outs)):
            if not isinstance(key, str) or key not in table:
                err(f"{where}: unknown {kind} {key!r}")
        iw, ih = (size(ins[i], "width"), size(ins[i], "height")) if isinstance(i, str) and isinstance(ins.get(i), dict) else (None, None)
        ow, oh = (size(outs[o], "width"), size(outs[o], "height")) if isinstance(o, str) and isinstance(outs.get(o), dict) else (None, None)
        if iw and ow and ih and oh and (ow > iw or oh > ih):
            err(f"{where}: output {o} ({ow}x{oh}) is larger than input {i} ({iw}x{ih}); the app refuses this")
        per_output.setdefault(o, []).append(n)
        if len(f) == 4:
            r = f[3]
            if not (isinstance(r, list) and len(r) == 4 and all(is_int(v) for v in r)):
                err(f"{where}: mosaic must be four integers [x, y, width, height] (got {r!r})")
                continue
            x, y, w, h = r
            if x < 0 or y < 0 or w <= 0 or h <= 0:
                err(f"{where}: mosaic {r} needs x,y >= 0 and width,height > 0")
            elif ow and oh and (x + w > ow or y + h > oh):
                err(f"{where}: mosaic {r} does not fit inside output {o} ({ow}x{oh})")
    for o, names in per_output.items():
        if len(names) > 1 and any(not isinstance(flows[n], list) or len(flows[n]) != 4 for n in names):
            err(f"output {o} is shared by {names}: every such flow needs a mosaic [x,y,w,h]")


def section(cfg, sec):
    v = cfg.get(sec)
    if not isinstance(v, dict) or not v:
        err(f"missing or empty section '{sec}' (must be a mapping)")
        return {}
    for k, d in v.items():
        if sec != "flows" and not isinstance(d, dict):
            err(f"{sec}.{k}: must be a mapping of options (got {type(d).__name__}: {d!r})")
    return v


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config")
    p.add_argument("--board", help="user@host to verify model folders over SSH")
    a = p.parse_args()
    try:
        with open(a.config) as f:
            cfg = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        err(f"cannot read/parse {a.config}: {e}")
        report()
    validate_cfg(cfg, a.board)
    report()


def validate_cfg(cfg, board=None):
    """Validate an already-parsed config; fills the module-level `errors` / `warnings` lists. Never raises on bad input."""
    if not isinstance(cfg, dict):
        err("the file must contain a YAML mapping with inputs/models/outputs/flows")
        return
    ins, models, outs, flows = (section(cfg, s) for s in ("inputs", "models", "outputs", "flows"))
    for n, d in ins.items():
        if isinstance(d, dict):
            check_input(n, d)
    for n, d in outs.items():
        if isinstance(d, dict):
            check_output(n, d)
    for n, d in models.items():
        if isinstance(d, dict):
            check_model(n, d)
            if board and isinstance(d.get("model_path"), str):
                check_model_remote(n, d["model_path"], board)
    check_flows(ins, models, outs, flows)


def report():
    for w in warnings:
        print("WARNING:", w)
    for e in errors:
        print("ERROR:", e)
    print("OK" if not errors else f"{len(errors)} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
