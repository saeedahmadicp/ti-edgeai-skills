# Other model families and tasks

## Detection families (meta-architectures)
Pick `object_detection:meta_arch_type` and a prototxt (see `ti-edgeai-dev/references/tidl-ops-and-limits.md`): TFLite SSD 1, ONNX SSD 3,
YOLOv3 4, RetinaNet/EfficientDet 5, YOLOX/YOLOv5/YOLOv7 6, PointPillars 7, YOLOv8 8. TI ships prototxts in edgeai-tidl-tools
`examples/models/prototxt/{mmdet,yolo}` and next to each zoo ONNX. The prototxt names tensors (`input:`) and anchors; the ONNX must
contain those tensors. Study a TI zoo detector of the same family on the board (`/opt/model_zoo/ONR-OD-*/model/*.onnx` + `.prototxt`)
with `check_onnx_for_tidl.py` and Netron, then match its head layout. Adding a new family means matching an existing meta-architecture;
otherwise run decode/NMS on ARM (compile without `--meta`).

## Classification
No meta layer. `--task classification`, `--resize S --crop C` (TI zoo classifiers use resize 256 + centre-crop 224), `--channels` as
trained. `param.yaml`: `preprocess.{resize, crop, reverse_channels}`, `postprocess: {}`; the app shows top-N (`topN` in the config).
Verified end to end with a float-input CNN whose mean/scale were folded in by `add_input_preprocessing.py`.

## Segmentation
No meta layer. `--task segmentation`, usually `--hw H W`. End the network with ArgMax so the output is a uint8 class map (TI's
helper adds the uint8 cast); `param.yaml` uses `crop`/`resize` as `[H, W]` and `reverse_channels` as trained. The app blends the mask
(`alpha` in the config). Template taken from a TI zoo segmentation model; the compile + run flow was not exercised here.

## Other
- Keypoints/pose, depth, 3D: TI zoo has entries (e.g. YOLOX pose); their param.yaml uses other `postprocess` fields. Copy a zoo
  folder of the same kind and adapt (`ssh root@<ip> cat /opt/model_zoo/<m>/param.yaml`).
- TFLite / TVM-DLR: separate runtimes and compile APIs in edgeai-tidl-tools (`examples/osrt_python/tfl`, `tvm_dlr`); not exercised.
- Vision transformers: TI notes disabling ONNX Runtime graph optimisations for some (see `model_configs.py` `cl-ort-deit-tiny`);
  not exercised.

## TI's all-in-one alternatives
- Edge AI Studio Model Composer (web): data -> train -> compile -> deploy for supported models.
- `edgeai-modelmaker`: `./run_modelmaker.sh <SoC name> config_detection.yaml` (COCO json dataset; YOLOX/MobileNet/RegNet/DeepLab...);
  outputs under `data/projects/`. Not run here. Use it when no custom export is needed.
