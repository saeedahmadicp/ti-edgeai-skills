# TI training toolchains (read in TI docs; only the YOLOX route was run here)

| Need | Tool | Notes |
|---|---|---|
| Fastest path, configurable end-to-end (data -> train -> compile -> deploy) | `edgeai-modelmaker` (edgeai-tensorlab) | `./setup_gpu.sh` then `./run_modelmaker.sh TDA4VM config_detection.yaml`; Ubuntu 22.04, Python 3.10; COCO json (`images/`, `annotations/instances.json`); tasks: classification, detection, segmentation, keypoints; outputs under `data/projects/` with the side files for the board |
| Web GUI | Edge AI Studio Model Composer | data collection, annotation, training, compile, deploy |
| YOLOX detectors | `edgeai-yolox` (TI fork) | TI-lite models `yolox-{s,m,tiny,nano}-ti-lite`; `python -m yolox.tools.train -n yolox-tiny-ti-lite -d 8 -b 64 --fp16 -o [--cache]`; `tools/export_onnx.py --export-det` writes ONNX + prototxt for TIDL |
| MMDetection-based (SSD-lite, YOLOX, RetinaNet...) | `edgeai-mmdetection` | TI zoo prototxts for meta-architectures |
| Classification / segmentation backbones, QAT | `edgeai-torchvision`, `edgeai-modeloptimization` | QAT in "a few lines" (TI); needed when PTQ loses too much |
| Benchmarking / yaml generation for many models | `edgeai-benchmark` | produces param.yaml-style files |
| Plain PyTorch / upstream repos | your own training + `ti-edgeai-import-model` | verified route: upstream YOLOX + TI-lite experiment file |

All repos live under `https://github.com/TexasInstruments/` (edgeai-tensorlab holds modelmaker, mmdetection, torchvision, modeloptimization,
modelzoo). Pin versions that match your SDK era when TI offers tags/branches.

## QAT (when PTQ is not enough)
TI: QAT trains the 8-bit behaviour into the weights and records feature-map ranges in the model, so no advanced calibration is needed
and accuracy loss is typically near zero. Use `edgeai-modeloptimization` (torchmodelopt) wrappers around your PyTorch model, export
to ONNX; pre-quantized ONNX QDQ models import with `advanced_options:prequantized_model=1`. Not run here.

## Choosing
- No special needs, supported task -> ModelMaker.
- YOLOX with custom labels -> TI-lite template (this skill) or `edgeai-yolox`.
- A model family TI does not ship -> train as you like with the design rules, then ONNX-check it early
  (`ti-edgeai-import-model/scripts/check_onnx_for_tidl.py`) - before investing in training.
