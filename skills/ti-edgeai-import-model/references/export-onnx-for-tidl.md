# Making any model's ONNX TIDL-friendly

TIDL compiles a static-shape ONNX graph into C7x kernels. Everything it cannot run stays on the ARM cores inside ONNX Runtime
(slow, and each ARM island splits the accelerator into separate subgraphs). A good export has one subgraph.

## Checklist (run `scripts/check_onnx_for_tidl.py model.onnx`)
1. **Static shapes**: fixed batch 1 and fixed H x W. PyTorch: `torch.onnx.export(..., opset_version=11)` without `dynamic_axes`;
   TensorFlow/Keras via tf2onnx with fixed input signature. Then `python3 -m onnxsim in.onnx out.onnx` (constant-folds, infers
   shapes; without it the importer reports `Unknown input dimension, not supported by TIDL` for every layer).
2. **Opset**: TI zoo models use 11 (some 9). Use 11 unless a needed op requires more.
3. **Operators**: stay inside the accelerated list (`ti-edgeai-dev/references/tidl-ops-and-limits.md`). Common replacements:
   SiLU/Swish -> ReLU/ReLU6/LeakyReLU (retrain or fine-tune); HardSwish/Mish are supported but check accuracy; large depthwise
   kernels, Focus/space-to-depth slicing -> use a strided conv or `SpaceToDepth`; `ReduceMean` alone is unsupported (use
   AveragePool/GlobalAveragePool); mid-graph `Cast` blocks offload; dynamic `Reshape`/`Gather` with variable shapes are unsupported.
4. **Activations & BatchNorm**: ReLU-family activations, BatchNorm after each conv (not necessarily after the last prediction conv),
   sufficient weight decay in training (TI: ~1e-4) all help int8 accuracy. See `quantization-accuracy.md`.
5. **Input/output contract** (this is what the board app sees):
   - Input is **uint8** `[1,3,H,W]`, NCHW. The board's `tiovxdlpreproc` produces it from the camera frame.
   - If the model normalises float input, fold it into the graph: `scripts/add_input_preprocessing.py in.onnx out.onnx --mean m0 m1 m2
     --scale s0 s1 s2` (per channel, 0..255 pixel scale, in the channel order the model expects). This uses TI's helper and renames the
     input `<name>Net_IN`; TIDL absorbs the Cast/Add/Mul into the network.
   - Models that already begin with `uint8 -> Cast(float)` and need no normalisation (e.g. YOLOX trained on raw 0..255 BGR) need nothing.
   - Channel order: say which the model expects (`--channels bgr|rgb` at compile, `reverse_channels` in param.yaml).
   - Outputs: classification -> one float vector; segmentation -> end the net with ArgMax (the TI helper casts it to uint8) so the
     board returns a small class map; detection -> expose raw head tensors for a meta-architecture (below).
6. **Prove equivalence**: run the framework model and the ONNX on the same images; outputs must match to float tolerance before
   you quantize. Quantization noise on top of an export bug is undebuggable.

## Detection heads and meta-architectures
For supported families, let TIDL run decode + NMS (`object_detection:meta_arch_type` + prototxt): faster (~0.3 ms) and the model
returns `dets`/`labels`. The ONNX must keep the head tensors named in the prototxt as graph nodes (typically the `Concat` of
reg/obj/cls conv outputs per stride). Without a meta-architecture, decode/NMS ops either run on ARM or you post-process in
application code. See `export-yolox-det.md` (worked example) and `other-model-families.md`.

## Frameworks other than ONNX
TFLite and TVM-DLR flows exist in edgeai-tidl-tools (`examples/osrt_python/{tfl,tvm_dlr}`) but the apps/board runtime pairing and
compile options differ; this skill set exercised ONNX only. Convert TF models to ONNX when you can.

## Sanity: run it on CPU first
`onnxruntime` (plain pip) on the ONNX with a sample image; then the compile. If CPU works and compile fails, it is a TIDL
limitation (use the `deny_list` option to push the offending layer type to ARM, then fix the model).
