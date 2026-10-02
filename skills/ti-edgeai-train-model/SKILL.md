---
name: ti-edgeai-train-model
description: >
  Plan and run training/fine-tuning so a vision model (detector, classifier, segmenter) deploys well on TI Edge AI
  processors with a C7x/MMA accelerator (TDA4VM, AM68A, AM69A, AM67A, AM62A): pick a TIDL-friendly architecture and input size,
  choose TI's toolchain (edgeai-modelmaker, edgeai-yolox, edgeai-mmdetection, edgeai-torchvision, plain PyTorch), build datasets
  and leakage-safe splits, train with quantization-friendly settings, and evaluate with the same preprocessing the board uses before handing the checkpoint to
  ti-edgeai-import-model. Use this skill whenever the user wants to train, fine-tune, label, split or evaluate a model "for the
  TI board / edge NPU / C7x", asks which architecture or input size to use, why their detector scores near zero, how to make a
  model quantization-friendly, or how to prepare labels so the model is learnable - even before any deployment question comes up.
license: MIT
metadata:
  version: 0.1.0
  tested_on: "YOLOX-tiny TI-lite experiment template deployed on TDA4VM; other toolchains documented only"
---

# Train a Model that Deploys Well on TI Edge AI

When this skill is active, **read `references/model-design-for-tidl.md` before choosing an architecture.** Most deployment pain is
decided before training: architecture, activations, input size, resize policy and label quality. Then hand the checkpoint to
`ti-edgeai-import-model`. Platform facts: `ti-edgeai-dev`.

## Workflow

1. **Task and constraints** - ask: task (detect/classify/segment), classes, camera aspect and resolution, target FPS, acceptable
   accuracy loss from int8, and what training data exists (images, masks, boxes, video). Camera aspect decides the model input aspect
   (TI's gst path resizes without padding): `references/model-design-for-tidl.md`.
2. **Pick the architecture and toolchain** (`references/toolchains.md`): prefer a TI-published "lite" model with a TI pretrained
   checkpoint (ReLU, TIDL-supported ops): it deploys cleanly and fine-tunes fast. For YOLOX use TI-lite
   (`assets/exp_ti_lite_template.py`, worked example `references/yolox-ti-lite.md`).
3. **Dataset** (`references/dataset-prep.md`): COCO json for detection, class folders for classification, index masks for
   segmentation. Check label quality visually, not just by file validity, and keep the label type the user's task needs (do not turn
   a segmentation task into detection, or the reverse, unless asked; if boxes must be derived from masks see
   `references/dataset-prep.md`). Split **by group** (scene/recording/video), never by random frame.
4. **Train** with quantization-friendly settings (ReLU-type activations, BatchNorm after convs, weight decay ~1e-4 per TI), fixed
   input size equal to the deployment size, pretrained TI weights. Keep the test split untouched until the final report.
5. **Evaluate like deployment** (`references/evaluation-protocol.md`): same resize policy, channel order and score logic as the
   board; validation for selection, a *separate* group-held-out test set for reporting; look at overlays.
6. **Hand off**: checkpoint + experiment/definition file + a model manifest (`ti-edgeai-import-model/scripts/model_manifest.py init`:
   input HxW, channel order, resize policy, classes, thresholds, target SoC) -> `ti-edgeai-import-model` (Phase 1). If int8 loss is large the fix may be training-side (QAT, activations): `references/toolchains.md`.

## Quick diagnostics ("my detector scores ~0")
| Symptom | Check |
|---|---|
| Near-zero mAP, loss decreases | box size distribution at the training resolution: boxes a few pixels wide cannot be learned; revisit the labeling rule (merge fragments, minimum size) or raise input size |
| mAP fluctuates wildly epoch to epoch | high LR phase + small single-group validation set; wait for LR decay / no-aug epochs, select by smoothed metric, add validation groups |
| Great validation, poor test | validation shares scenes with training or was used for selection; split by group, report on a held-out group set |
| Good float, bad on board | resize/aspect mismatch between training and the no-padding pipeline; channel order; int8 loss (see import skill) |
| Boxes stretched on the board | trained with letterbox, deployed with plain resize (or the reverse) |

## Reference Documents
| File | Use when |
|---|---|
| [references/model-design-for-tidl.md](references/model-design-for-tidl.md) | operators, activations, input size and aspect for TIDL |
| [references/toolchains.md](references/toolchains.md) | which TI/open-source training stack to use, QAT |
| [references/dataset-prep.md](references/dataset-prep.md) | formats, label quality, group-wise splits |
| [references/evaluation-protocol.md](references/evaluation-protocol.md) | validation vs test, deployment-matched evaluation |
| [references/yolox-ti-lite.md](references/yolox-ti-lite.md) | worked example: YOLOX-tiny TI-lite |
| [references/lessons.md](references/lessons.md) | general lessons from past training runs |

## Files
- `assets/exp_ti_lite_template.py`: upstream-YOLOX experiment producing a TI-lite YOLOX-tiny (any class count, any input size via env vars).
