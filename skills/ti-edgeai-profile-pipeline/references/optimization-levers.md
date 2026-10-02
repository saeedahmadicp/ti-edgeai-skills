# Levers (measure each; none is free)

| Lever | Effect | Cost / caveat |
|---|---|---|
| Smaller input (fewer pixels) | model time falls roughly with pixel count | fewer pixels per object; accuracy cost depends on object size, so re-evaluate at the new size |
| Match model aspect to the camera aspect | removes distortion, avoids wasted pixels | training resize must match deployment resize |
| Lower camera frame rate / mode | cuts decode, scale and encode work | some UVC webcams drop to ~10 fps at 1280x720 |
| Output to file/fakesink instead of display for benchmarks | removes the display path | not representative of the live app |
| Native detection meta layer (TIDL meta-architecture) | decode + NMS on the C7x, a fraction of a millisecond | needs prototxt + matching head names; confidence/NMS thresholds baked at compile |
| 16-bit for a few layers (mixed precision) | accuracy up | latency up by about the `mixed_precision_factor` you allow (1.2 = +20%) |
| All-16-bit (`tensor_bits 16`) | best int8-loss recovery short of QAT | roughly 2x compute/memory on affected layers; measure |
| Smaller backbone | lower model time | accuracy |
| `calibration`/`accuracy_level` | accuracy only, no speed change | longer compile |
| Reduce `drop`/queue depth, `out-pool-size` | latency/memory | tune only if the tracer shows queue backlog |

The multi-C7x options in TI's `tidl_fsg_multi_c7x.md` apply to SoCs with several C7x cores (see `ti-edgeai-dev/references/platforms.md`;
documentation only, not tested).
Rule: if the pipeline sustains the target fps with slack and the model time is far below the frame period (e.g. a few ms against 33 ms),
more speed is not the problem; look at accuracy, display size or camera mode instead.
