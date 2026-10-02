# Sources and verification status

## TI documentation used (read for this skill set)
- SDK docs (9.1 text; structure the same in 11.0): inference_models (model folder, tools), configuration_file, edgeai_dataflows,
  measure_perf - `https://software-dl.ti.com/jacinto7/esd/processor-sdk-linux-sk-tda4vm/09_01_00/exports/edgeai-docs/common/`
- edgeai-tidl-tools (tags 11_00_06_00 / 11_00_08_00 cloned): `docs/version_compatibility_table.md`,
  `docs/custom_model_evaluation.md`, `docs/tidl_fsg_quantization.md`, `docs/tidl_fsg_od_meta_arch.md`,
  `docs/supported_ops_rts_versions.md`, `docs/tidl_osr_debug.md`, `docs/tidl_fsg_io_tensors_format.md`,
  `examples/osrt_python/README.md` (provider options), `examples/osrt_python/model_configs.py` (zoo entries incl. YOLOX)
  - `https://github.com/TexasInstruments/edgeai-tidl-tools`
- edgeai-yolox `README_2d_od.md` (TI-lite changes, `--export-det`) - `https://github.com/TexasInstruments/edgeai-yolox`
- edgeai-modelmaker README (config, `./run_modelmaker.sh <SoC name> config_detection.yaml`) -
  `https://github.com/TexasInstruments/edgeai-tensorlab/tree/main/edgeai-modelmaker`
- On-board source: `/opt/edgeai-gst-apps` (configs, apps_python, scripts/gst_tracers, scripts/perf_stats).

## Tested by running (SK-TDA4VM only, Edge AI SDK 11.0)
- Tools-tag pairing and artifact version stamps (all ten zoo models carry `29 04 25 20`); Docker build of the tools environment from the
  skill's Dockerfile; compile of three model kinds: a YOLOX-tiny TI-lite detector (OD meta layer, 1 subgraph), a float-input classifier
  with folded mean/scale (TI's `tidlOnnxModelOptimize`), and TI zoo models used as controls.
- Host-emulation outputs bit-identical to the board (max abs diff 0) for the detector (dets/labels) and the classifier.
- Board runs: image-sequence, H.264 video, classification and two-model mosaic configs (all exit 0, full offload, no errors);
  USB webcam run with file output (earlier); config generator/validator on working and deliberately broken configs.
- Timings for classification, segmentation and detection models; per-layer cycles at `debug_level 1`; GStreamer tracer parser.
- `param.yaml` `[H, W]` order; `SOC=j721e` (TDA4VM) pipeline vs ARM-only pipeline; ONNX preflight on a custom detector and TI zoo ONNX files.

## Read in TI docs but NOT run here (including every SoC other than TDA4VM)
HDMI display output (launched, never confirmed on screen), OpTIFlow, C++ app, CSI cameras (IMX219/IMX390), `perf_stats` (needs compiling),
mixed precision / QAT compiles, multi-C7x (`tidl_fsg_multi_c7x.md`), ModelMaker end-to-end, multi-class meta layer on a real model,
segmentation compile (only the param.yaml template and timing of a zoo model), TFLite/TVM runtimes, firmware update.
Treat statements in those areas as documentation, not field-verified.
