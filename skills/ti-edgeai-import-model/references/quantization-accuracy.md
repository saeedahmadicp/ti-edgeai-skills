# Int8 accuracy: measure, then escalate

## Measure properly
1. Float reference: `eval_onnx_det.py` / `eval_classification.py` on the folded+simplified ONNX (CPU).
2. Int8 host emulation (same container, same artifacts): add `--tidl-artifacts artifacts --tidl-tools $TIDL_TOOLS_PATH`. Slow
   (~0.8-1.3 s per frame for a detector at 640 px); run in the background.
3. Host emulation matches the board bit-for-bit (TI's claim, verified for a detector and a classifier with `board_host_check.py`),
   so host numbers are the board's numbers. Re-verify for each new model type.
4. Report validation **and** a held-out test set; choosing checkpoints/thresholds on validation makes it optimistic.
5. Label-free for classifiers: `eval_classification.py --reference-onnx float.onnx` gives top-1 agreement and output cosine similarity
   (a tiny conv classifier: 100% agreement, cosine 0.9994 after int8).

## Typical behaviour
Classification and segmentation backbones usually lose well under a point with `accuracy_level 1`; detectors (regression outputs) lose
more, a few AP points is common on TDA4VM because only symmetric quantization is available. Do not promise a number: measure.

## Escalation ladder (TI `tidl_fsg_quantization.md`, section E; TDA4VM = symmetric only)
1. More/representative calibration frames, `accuracy_level 1`, `calibration_iterations` 10 -> 50.
2. 16-bit for the first and last convolution layers (TI: beneficial for detection/regression nets):
   `--extra advanced_options:output_feature_16bit_names_list=<comma separated layer outputs>`; names are in
   `artifacts/tempDir/*.layer_info.txt` (original node names). Optionally `advanced_options:params_16bit_names_list`.
3. Automatic mixed precision: `--accuracy-level 1 --frames 50 --iterations 50 --extra advanced_options:mixed_precision_factor=1.2`
   (factor = tolerated latency ratio T_mixed / T_8bit; raise to 1.4 if needed). Slow compile: run detached.
4. `--tensor-bits 16` for the whole network (measure the speed cost with `ti-edgeai-profile-pipeline`).
5. QAT: retrain with edgeai-modeloptimization (TI) so ranges are learned; or import an ONNX QDQ model with
   `advanced_options:prequantized_model=1`.
Only conv, batchnorm, non-max pooling and eltwise layers can change precision; concat/resize inherit from neighbours.
(Steps 2-5 are from TI documentation; not run in this skill set's tests.)

## Diagnosing where the loss comes from
- Compile with `--tensor-bits 32` (PC-only float TIDL mode): equal to OSRT float => import is fine, loss is quantization.
- `debug_level 4` dumps per-layer float and fixed traces; compare with TI's activation-comparison script (`tidl_osr_debug.md`,
  "Feature Map Comparison") to find the layer with the worst error, then raise its precision.
- Training-side causes (TI): small weight decay (< 1e-4), conv without BatchNorm, unbounded activations (SiLU/Swish).
- Detection thresholds (`confidence_threshold`, `nms_threshold`, `top_k`) are compile-time inputs to the meta layer (inferred from how it
  is imported; changing them means re-compiling). Keep `confidence_threshold` low (0.05-0.1) and filter at display time with
  `viz_threshold`.
