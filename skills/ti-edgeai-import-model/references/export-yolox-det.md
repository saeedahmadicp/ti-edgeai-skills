# Worked adapter: YOLOX (TI-lite) -> TIDL detector

One concrete instance of "detector with a TIDL meta-architecture". Use it as a template for other families.

## Why not just `torch.onnx.export(model)`
TIDL accelerates the convolutional body and its **detection meta-architecture** (decode + NMS on C7x). The ONNX must
(1) expose the three YOLOX head tensors as `Concat` nodes the prototxt can name, and (2) stay a valid graph for CPU runtimes,
as TI's zoo models do, by keeping the decode/NMS ops after those Concats and ending in `dets`/`labels`. TIDL cuts the graph at the
named Concats and swaps the tail for its native layer (`dets_det` in the layer list).

## TI-lite architecture (needed for good int8 and full offload)
Differences from stock YOLOX (TI `edgeai-yolox` README_2d_od): Focus slice-stem -> 3->12 stride-2 conv + 12->24 conv;
SiLU -> ReLU (unbounded SiLU is hostile to fixed point); SPP maxpool 5/9/13 -> repeated 3x3 stride-1 pools. TI publishes COCO
checkpoints (`yolox_*_ti_lite.pth`); fine-tune from them (all tensors match except the class head). A ready experiment file:
`ti-edgeai-train-model/assets/exp_ti_lite_template.py`.

## What `scripts/export_yolox_tidl_det.py` builds
- Input `images` uint8 `[1,3,H,W]`, BGR 0..255 (YOLOX trains without mean/scale); first node casts to float.
- Head outputs per stride (8/16/32): `[1, 5+nc, h, w]` = x, y, log w, log h, objectness logit, class logits (no sigmoid).
- Tail (CPU/verification only): decode `(xy+grid)*stride`, `exp(wh)*stride`, `score = sigmoid(obj) * max sigmoid(cls)`, threshold
  `--conf` (0.05), class-agnostic NMS (`--nms` 0.45), top-k 200 -> `dets [N,5]` (x1,y1,x2,y2,score), `labels [N]` (int64).
- Writes `<out>.prototxt` with the three Concat output names (found automatically: Concats whose 3 inputs are Convs), anchors
  8/16/32, `num_classes`, NMS 0.45/top-k 200, `confidence_threshold` (`--proto-conf`, 0.1), `in_width/in_height`.
- opset 11, static shapes. `--input-hw H W` (multiples of 32) exports a size different from training: YOLOX is fully
  convolutional, so the same weights run at another size (re-evaluate accuracy at that size).
- Any class count; the 1-class path was tested on a board, multi-class uses the same code but has not been run on a board.

## Choosing the input size
TI's `tiovxmultiscaler` squashes the camera frame to the model size (no padding). Training with letterbox and deploying with
squash stretches objects. Export at the camera's aspect (multiple of 32): 16:9 -> 352x640; 4:3 -> 480x640; square -> 640x640, and
evaluate float with the same plain resize (`eval_onnx_det.py --hw H W`). Smaller inputs are faster (YOLOX-tiny on C7x: 5.6 ms at
352x640 vs 8.0 ms at 640x640).

## Checks before compiling
1. `eval_onnx_det.py` float AP equals the trainer's AP (small differences come from the score threshold and any resize change).
2. If you changed only the exporter, outputs of old and new ONNX on the same images differ by 0.0.
3. `onnxsim` succeeds; `check_onnx_for_tidl.py` reports no ERRORs.

## TI's own export route
`edgeai-yolox/tools/export_onnx.py --export-det` writes an equivalent ONNX + prototxt (NMS 0.65, top-k 500, confidence 0.01).
Use it when training in TI's fork; this script exists for the upstream YOLOX repo plus a TI-lite experiment file.
