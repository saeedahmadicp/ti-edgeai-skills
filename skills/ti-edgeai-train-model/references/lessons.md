# General lessons

1. **A "broken" detector can be a labels problem.** If mAP is near zero while the loss falls, look at the box-size histogram at the
   training resolution before touching the model: boxes a few pixels wide cannot be learned. Fix the labeling rule, not the network.
2. **Split by group.** A split in which a couple of large groups dominate train and validation says little about generalization; keep
   whole groups (recording, scene, video) on one side and report on a group-held-out test set.
3. **Aspect/resize policy must match the pipeline.** A model trained with letterbox but fed plain-resized frames (TI's gst path does
   not pad) produces stretched boxes. Export at a camera-matched input size and calibrate with the same plain resize.
4. **Validation noise is large while the learning rate is high**; do not pick an early lucky epoch, use the stable final epochs.
5. **int8 usually costs some accuracy on detectors** (more on TDA4VM, which is symmetric-only); plan for 16-bit first/last layers,
   mixed precision, asymmetric quantization where the SoC supports it, or QAT.
6. **Negative scenes matter.** Without background-only training images a detector can fire on unrelated scenes; include the
   backgrounds the camera will see.
7. **Keep everything reproducible**: experiment file, dataset report (group assignment, box stats), checkpoint hash, export command.
