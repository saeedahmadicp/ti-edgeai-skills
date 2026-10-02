# Config schema (edgeai-gst-apps) and generator flags

Full option list with comments: `/opt/edgeai-gst-apps/configs/app_config_template.yaml` on the board (authoritative).
Shorter summary: `ti-edgeai-dev/references/gst-apps-and-plugins.md`. This file adds the rules the validator enforces.

## Rules (validator ERRORs unless noted)
| Rule | Origin |
|---|---|
| sections `inputs`, `models`, `outputs`, `flows` present and non-empty | schema |
| input needs `source`, `width`, `height`; model needs `model_path`; output needs `sink`, `width`, `height` | schema |
| types and ranges: strings non-empty; `width`/`height` positive integers (not bool, not strings); `framerate` > 0; `viz_threshold`, `alpha` in [0, 1]; `topN` positive integer; `port` 1..65535; `connector` >= 0; `loop` boolean; entries are mappings | validator (a wrong type is an ERROR, never a traceback) |
| flow = `[input, model, output]` or `[input, model, output, [x, y, w, h]]`, names must exist | app |
| flow output width/height <= input width/height | app exit: "Flow output resolution can not be greater than input resolution" |
| mosaic = four integers, x/y >= 0, w/h > 0, inside the output | app exit: "Mosaic is not with in the background buffer" |
| several flows to one output => each needs a mosaic | app exit: "Need mosaic to support multiple subflow" |
| image source / image sink contain a `%0Nd` pattern | image sequence naming |
| sink file types `.jpg .png .mkv .mp4 .mov` | app |
| `overlay-perf-type` graph/text; remote `encoding` jpeg/h264/mp4 | app |
| odd width/height (WARNING) | tiovxmultiscaler limitation |
| `format: jpeg` on a /dev/video source (WARNING) | only for MJPEG cameras; YUYV-only webcams need `auto` |

## Generator flags -> YAML
| flag | YAML |
|---|---|
| `--input usb|csi|video|image|rtsp|test`, `--source`, `--format`, `--width/--height`, `--framerate`, `--loop`, `--subdev-id` | `inputs.input0.*` |
| `--model PATH` (repeat), `--viz-threshold`, `--top-n`, `--alpha` | `models.modelN.*` |
| `--output display|file|image|stream|fakesink`, `--sink`, `--out-width/--out-height`, `--perf-overlay`, `--connector`, `--host/--port/--encoding` | `outputs.output0.*` |
| several `--model` | flows tiled in a grid: `[x, y, w, h]` with even sizes |

The generator emits one input and one output; for multi-input / multi-output layouts copy the blocks by hand, then validate.

## Choosing sizes
- Input `width x height` must be a mode the source delivers. Output defaults to the input size.
- For a model with input H x W, prefer a camera mode with the same aspect so TI's no-padding resize does not stretch objects.
- Large outputs cost encode/scale time; for FPS measurements use `fakesink` or a file sink, not the display.
