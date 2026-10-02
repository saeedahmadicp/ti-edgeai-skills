# Model manifest

One JSON file carries the deployment contract between training, import, configuration and profiling, so the critical assumptions
(channel order, resize policy, classes, meta-architecture, toolchain versions) are written once instead of repeated as flags that can
drift apart. Tool: `scripts/model_manifest.py` (stdlib only).

```json
{
  "schema_version": 1, "name": "mymodel", "task": "detection",
  "input": {"hw": [352, 640], "channels": "bgr", "dtype": "uint8"},
  "classes": ["a", "b"],
  "postprocess": {"prototxt": "mymodel.prototxt", "meta_arch_type": 6, "viz_threshold": 0.3},
  "target": {"tools_soc": "am68pa", "tidl_tag": "11_00_06_00", "device": "TDA4VM", "board_sdk": "11.0"},
  "files": {"model/mymodel.onnx": "<sha256>", "artifacts/subgraph_0_tidl_net.bin": "<sha256>"}
}
```
- `input` has exactly one of `hw` (plain resize, TI's gst path), `letterbox`, or `resize`+`crop` (classification). `channels` is the
  order the MODEL expects; `dtype` is what the app feeds (uint8 with normalization folded in, TI's convention).
- `files` is written by `seal` and checked by `verify`; the packaged folder carries its own sealed copy as `manifest.json`.

## Lifecycle
1. **Train** (`ti-edgeai-train-model`): write the manifest at hand-off with `model_manifest.py init ...` (task, input policy, channels,
   classes, thresholds, target SoC and tools tag). `validate` checks it.
2. **Import**: `compile_tidl.py`, `eval_onnx_det.py`, `eval_classification.py` and `board_host_check.py dump` take `--manifest m.json`
   for preprocessing (and task, meta-architecture type and prototxt for compile). A flag that contradicts the manifest is an error, so
   calibration, evaluation and board checks cannot silently use different preprocessing.
3. **Package**: `package_model.py --manifest m.json ...` takes task, classes, preprocessing and device from it, then seals the
   packaged files' sha256 into `<package>/manifest.json`.
4. **Later**: `model_manifest.py verify <package>/manifest.json --root <package>` proves the folder on disk is the one that was
   packaged (use it before deploying or when a board result looks off). The same file tells `ti-edgeai-generate-config` which
   threshold to use and `ti-edgeai-profile-pipeline` which preprocessing the model expects.

The manifest records intent and integrity. It does not prove the model works: the gates in `SKILL.md` do.
