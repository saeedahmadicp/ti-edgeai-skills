# What runs on the C7x, constraints, and OD meta-architectures

Source: edgeai-tidl-tools `docs/supported_ops_rts_versions.md`, `tidl_fsg_od_meta_arch.md`, `tidl_fsg_quantization.md`
(tag 11_00_06_00). Anything TIDL cannot run executes on the ARM cores inside the ONNX Runtime graph (slower, and the
accelerator<->ARM hops add latency). A fully offloaded model shows `Final number of subgraphs created are : 1,
- Offloaded Nodes - N, Total Nodes - N` in the app/compile log.

## ONNX operators accelerated (TIDL layer) - highlights and gotchas
- Conv (one variable input, <=4 non-singleton dims), pooling (Max/Average/Global), Relu/PRelu/LeakyRelu/Sigmoid/Tanh/HardSwish/
  Elu/Clip (min<=0, max>0), BatchNormalization (inference), Add/Mul/Sub/Div/Sum/Max (constant operands need shape-inferred
  dims), Concat (axis -3/-2/-1, not batch), Slice/Split (4 inputs, 3 constant 1-D), Resize/Upsample (nearest, linear),
  ConvTranspose, Gemm/MatMul, Softmax (W/H axis), Reshape (constant shape), Transpose, Flatten, Squeeze/Unsqueeze,
  Pad (constant, W/H), ReduceMin/Max (along height), ReduceMean (only via fused patterns; use TI's onnx optimizer),
  ArgMax (axis -3), TopK (constant K), GridSample, LayerNorm, DeformConv (3x3 s1), Exp/Log/Sqrt/Pow/Abs/Floor/trig ops.
- **Cast only at the network input/output** (that is why a uint8 input + Cast first node is fine, and a Cast mid-graph
  is not).
- **SiLU/Swish is not quantization friendly** (unbounded) -> use ReLU variants ("TI-lite" YOLOX does).
- `Gather` data cannot be a constant; `Reshape` with variable shape is unsupported; DropOut alone is unsupported.
- NonMaxSuppression / NonZero / GatherND (an exported detection tail) are not accelerated as ONNX ops: the OD
  meta-architecture replaces that tail with a native TIDL detection layer (`dets_det`, ~0.3 ms at 640x352 on C7x).
- Some ops are accepted only in fused combinations (see the doc's "fused combinations" section).
- Re-check the exact table for your tag: `docs/supported_ops_rts_versions.md`.

## Object-detection meta-architectures (`object_detection:meta_arch_type`)
| Network family | type | Notes |
|---|---|---|
| TFLite SSD | 1 | prototxt from TI model zoo |
| ONNX SSD | 3 | prototxt in `examples/models/prototxt/mmdet` |
| YOLOv3 | 4 | |
| RetinaNet / EfficientDet | 5 | |
| **YOLOX, YOLOv5, YOLOv7** | **6** | prototxt lists the three head `Concat` outputs (stride 8/16/32 anchors), `CODE_TYPE_YOLO_X`, NMS params |
| PointPillars 3D | 7 | |
| YOLOv8 | 8 | |

YOLOX prototxt shape (what `export_yolox_tidl_det.py` writes; matches TI zoo files):
```
name: "yolox"
tidl_yolo {
  yolo_param { input: "<head0 Concat output>" anchor_width: 8.0  anchor_height: 8.0 }   # one per stride 8,16,32
  detection_output_param { num_classes: N share_location: true background_label_id: -1
    nms_param { nms_threshold: 0.45 top_k: 200 } code_type: CODE_TYPE_YOLO_X keep_top_k: 200 confidence_threshold: 0.1 }
  name: "yolox"  in_width: W  in_height: H  output: "dets"  output: "labels"  framework: "MMDetection" }
```
The head tensors feeding the meta layer are **raw logits** concatenated as `[x, y, logw, logh, obj, cls...]` per
location (no sigmoid): TIDL applies the activations and decoding. Outputs: `dets [N,5]` (x1,y1,x2,y2,score) and
`labels [N]` (the board's `DetectionBoxSL2BoxLS` formatter reorders to box/label/score).

## Quantization facts
- 8-bit PTQ is symmetric (`quantization_scale_type 0`) on every SoC; TI documents asymmetric per-channel (`4`) for all SoCs except
  TDA4VM, where only symmetric exists (symmetric run on TDA4VM; the asymmetric option has not been run here).
  `accuracy_level 0` = simple calibration; `1` = advanced bias calibration (use >=50
  frames); `9` = histogram activation clipping. `tensor_bits 16` for all-16-bit; mixed precision per layer via
  `advanced_options:output_feature_16bit_names_list` / `params_16bit_names_list`, or automatically via
  `advanced_options:mixed_precision_factor` (latency ratio T_mixed/T_8bit, e.g. 1.2; use accuracy_level 1,
  calibration_frames 50, iterations 50; compile is slow).
- Precision can change only for Convolution, BatchNorm, non-max Pooling and EltWise layers.
- Detection/regression heads quantize worst; TI recommends 16-bit for the first and last conv layers of such networks.
- QAT (edgeai-modeloptimization) removes most of the loss; pre-quantized ONNX QDQ models import with
  `advanced_options:prequantized_model=1`.
- Training hygiene that helps int8: weight decay ~1e-4, BatchNorm after every conv except the final prediction conv,
  ReLU-type activations.
