# Designing for TIDL

## Rules of thumb (TI guidance and tested deployments)
- **Activations**: ReLU / ReLU6 / LeakyReLU (bounded, quantization friendly). Avoid SiLU/Swish (unbounded, poor int8). HardSwish/Mish are
  supported by TIDL but check accuracy.
- **BatchNorm** after every conv (including every depthwise conv); the final prediction conv may omit it. **Weight decay ~1e-4**
  (not 1e-5) keeps weights compact for 8-bit.
- **Operators**: stay inside the accelerated list (`ti-edgeai-dev/references/tidl-ops-and-limits.md`); no dynamic shapes; avoid exotic
  slicing stems (Focus) - use a strided conv; global pooling instead of ReduceMean.
- **Detection heads** are the quantization-sensitive part (continuous regression outputs). Expect a few AP points of int8 loss; TI
  suggests 16-bit for first/last convs or QAT. Prefer families with a TIDL meta-architecture (YOLOX/v5/v7 type 6, SSD, YOLOv3, YOLOv8)
  so decode/NMS run on the accelerator.
- **Capacity vs speed**: model-only int8 times measured on a TDA4VM are in `ti-edgeai-profile-pipeline/references/baselines.md` (about
  3 ms for a small classifier up to ~12 ms for a YOLOX-s class detector). Latency scales roughly with pixels and network width. Pipeline FPS is usually limited by decode/encode/display, not the model (`ti-edgeai-profile-pipeline`).

## Input size and aspect
TI's gst pipeline (`tiovxmultiscaler`) resizes the camera frame to the model size **without padding**. So:
- train, evaluate, calibrate and deploy with the **same plain resize**; or deploy a pipeline that letterboxes and set `resize_with_pad`;
- choose the model input aspect close to the camera aspect (16:9 camera -> 352x640 or 360x640-ish multiple of 32; 4:3 -> 480x640);
- fully-convolutional detectors (YOLOX) can be trained at one size and exported at another; re-measure accuracy at the export size,
  and prefer to fine-tune at the final size/policy if the gap matters;
- small objects: objects below ~10 px at the *network* input are hardly learnable; raise resolution, tile, or redefine labels.

## Channel order and normalisation
Decide once: BGR or RGB, and mean/std. Write it down for the import step (`--channels`, `add_input_preprocessing.py`). YOLOX trains on
raw 0..255 BGR with no normalisation; torchvision-style models use RGB with ImageNet mean/std.

## Pretrained weights
Start from TI's published checkpoints (COCO / ImageNet) of the *lite* variant; replace only the task head. TI model zoo and
`edgeai-modelzoo` list them. Fine-tune with a lower LR than from-scratch.
