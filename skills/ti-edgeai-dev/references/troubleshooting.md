# Troubleshooting (symptom -> cause -> fix)

Order of investigation for "it does not work on the board": (1) does the same ONNX run on CPU/PC with correct
results? (2) does it compile for TIDL on the PC and run in host emulation (`TIDLExecutionProvider` on x86) with
acceptable accuracy? (3) only then debug the board.

## Compile (PC / container)
| Symptom | Cause / fix |
|---|---|
| `Unknown input dimension, not supported by TIDL` on every layer | no static shapes: `python3 -m onnxsim in.onnx out.onnx` (or `onnx.shape_inference`) |
| `Bus error (core dumped)` during import | Docker shm too small: `--shm-size=4g` |
| `tidl_graphVisualiser.out: libcgraph.so.6: cannot open shared object` | image lacks graphviz (`apt-get install graphviz libgraphviz-dev`) |
| `tidl_tools` folder missing after `setup.sh` | `SOC` was unset at setup time: `SOC=<tools soc> ./setup.sh ...` (`references/platforms.md`) |
| `IsADirectoryError ... artifacts/tempDir` | artifacts dir holds a subdirectory: `shutil.rmtree` the folder before compiling |
| `NoSuchFile ..._sim.onnx` | onnxsim failed silently (module missing / error hidden by redirect) |
| `Error in topologically sorting the network` | tail ops outside the meta layer; export the TI-style graph (head Concats + meta prototxt) |
| layers silently on ARM | `deny_list`, unsupported op, or dynamic dim: read the `allowedNode.txt` / compile log; set `debug_level 1-2` |
| ARM-only works but offload compile fails | try `deny_list:layer_type`, `ORT_DISABLE_ALL` graph optimization, `TIDL_RT_ONNX_VARDIM=1` |

## Board runtime
| Symptom | Cause / fix |
|---|---|
| `VX_ZONE_ERROR ... TIVX_CMD_NODE_CREATE failed ... [TIDL subgraph dets] Graph verify failed`, `Create state function failed. Return value:-1` | artifact format not accepted by firmware (wrong tools tag), or C7x memory exhausted by another app. Compare stamps (`check_artifacts_version.py`); verify a zoo model still runs (`configs/zoo_image_test.yaml` pattern in `ti-edgeai-generate-config`) |
| App exits immediately with no pipeline errors after ssh command returns | session cleanup killed it: use `systemd-run` (board-and-paths.md) |
| `Got invalid dimensions for input` | param.yaml `resize`/`crop` order `[H, W]` |
| Boxes stretched/offset, but no errors | ARM-only pipeline (no `SOC` exported) or model trained with letterbox while pipeline squashes |
| Nothing on HDMI although app runs | stock GUI owns the display: `systemctl stop edgeai-init` |
| `cbreak() returned ERR`, `setupterm` | no tty; use `script -qfc` / systemd-run / `TERM=xterm` |
| camera not listed | `lsusb`; `dmesg | grep usb`; USB hub enumeration failure -> power-cycle |

## Debug levels (provider option `debug_level`)
- 1: per-layer C7x cycle table on target (`ti-edgeai-profile-pipeline/scripts/layer_cycles.py`); verbose compile log.
- 2: more traces; run `/opt/vision_apps/vision_apps_init.sh` and the remote log reader to see C7x messages.
- 3: fixed-point layer dumps to `/tmp/tidl_trace*` (compare host emulation vs target bit-for-bit; first mismatching
  layer is the one to report; dataId->layer names in `*.layer_info.txt`).
- 4: float + fixed traces for feature-map comparison scripts (see edgeai-tidl-tools `docs/tidl_osr_debug.md`).
- `tensor_bits=32` compile (PC only) = TIDL float reference; if accuracy matches OSRT-without-offload, import is
  correct and any loss is quantization.

## Accuracy loss after int8
Follow TI's ladder: float via TIDL (32-bit) -> 8-bit with `accuracy_level 1`, >=50 calibration frames -> 16-bit ->
mixed precision (manual by layer or `mixed_precision_factor`) -> QAT. See `ti-edgeai-import-model/references/quantization-accuracy.md`.
