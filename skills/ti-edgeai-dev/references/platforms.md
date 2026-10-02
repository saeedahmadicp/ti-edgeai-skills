# Supported SoCs: lookup table

The skills describe the **TI Edge AI SDK** (edgeai-tidl-tools on the PC, edgeai-gst-apps and TIDL runtime on the board), which is
the same across the C7x/MMA Jacinto 7 / AM6xA family. What differs per SoC is a handful of names and options, collected here.
Read the SoC off the board (`cat /proc/device-tree/model`, `env | grep -i SOC`) and pick the row; never assume.

| SoC family (product names) | tools `SOC` (`TOOLS_SOC`) | gst-apps `SOC` (`GST_SOC`) | `--target-device` | asymmetric int8 (`--quant-scale-type 4`) |
|---|---|---|---|---|
| TDA4VM / J721E / AM68PA | `am68pa` | `j721e` | `TDA4VM` | no, symmetric only |
| AM68A / J721S2 / TDA4VL / TDA4AL | `am68a` | `j721s2` | `AM68A` | yes |
| AM69A / J784S4 / TDA4VH / TDA4AP / TDA4VP / TDA4AH | `am69a` | `j784s4` | `AM69A` | yes |
| AM67A / J722S / TDA4AEN | `am67a` | `j722s` | `AM67A` | yes |
| AM62A | `am62a` | `am62a` | `AM62A` | yes |

AM62 / AM62P / AM62X have no C7x accelerator in these tools (the gst-apps map uses `tiscaler`/`tidlpreproc`/`timosaic` for them) and
are out of scope. All five rows use the same `tiovx*` GStreamer elements in `configs/gst_plugins_map.yaml`.

Sources: edgeai-tidl-tools tag 11_00_06_00 `setup.sh`, `docs/tidl_fsg_quantization.md`, `docs/version_compatibility_table.md`;
edgeai-gst-apps `configs/gst_plugins_map.yaml`. Throughput differs a lot between SoCs (single C7x ~2 TOPS class, TDA4VM/AM68A ~8,
AM69A ~32 with several C7x cores; TI product pages, not measured here), so never reuse another SoC's latency numbers.

## Per-SoC differences to watch
- **Tools tag vs SDK**: per-SoC column in TI's compatibility table; AM62A has no 11_00_06_00 entry (see `sdk-versions.md`).
- **Quantization**: asymmetric per-channel exists everywhere but TDA4VM; try it first on other SoCs when int8 loses accuracy.
  TDA4VM-only: symmetric, so mixed precision or QAT are the levers.
- **`platform` option** of the TIDL provider: `J7` was used on TDA4VM; TI's README lists `J7` and `AM62A`.
- **AM69A** has several C7x cores (`docs/tidl_fsg_multi_c7x.md` in edgeai-tidl-tools); the guidance here targets one core.
- **Camera/ISP**: sensor and ISP plugins depend on the starter kit; set up with `setup_cameras.sh`.

## How the scripts take the SoC
| Where | Setting | Default |
|---|---|---|
| `ti-edgeai-import-model/scripts/Dockerfile.tidl-tools` | `--build-arg SOC=<tools soc> --build-arg TIDL_TAG=<tag>` | `am68pa`, `11_00_06_00` |
| `run_in_container.sh` | env `TOOLS_SOC`, `TIDL_TAG` (image `ti-tidl-tools:<tag>-<soc>`) | `am68pa`, `11_00_06_00` |
| `compile_tidl.py` | `--platform`, `--quant-scale-type` | `J7`, `0` |
| `package_model.py` | `--target-device` | `TDA4VM` |
| `deploy_to_board.sh`, `trace_pipeline.sh` | env `GST_SOC` | `j721e` |

## Test coverage
The workflow was exercised end to end on a TDA4VM (SDK 11.0) only; the other rows come from TI's documentation. See `sources.md`.
Reports from other boards: `CONTRIBUTING.md`.
