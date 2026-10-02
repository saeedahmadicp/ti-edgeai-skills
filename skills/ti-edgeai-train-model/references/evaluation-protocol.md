# Evaluation that predicts board behaviour

1. **Three tiers**: train (fit), val (select epoch/threshold/preprocessing), test (report once, group-held-out).
2. **Match deployment preprocessing**: evaluate float ONNX with the board's resize policy (`eval_onnx_det.py --hw H W` plain resize, or
   `--letterbox`), same channel order. Training-time evaluators that letterbox can overstate what the board delivers.
3. **Metrics**: detection COCO AP50:95, AP50, AR100 (+ AP by size); classification top-1/top-5; segmentation mIoU. Compare float vs int8
   (`ti-edgeai-import-model`); quote both and the *test* number for expectations.
4. **Selection noise**: with small, single-group validation sets, epoch-to-epoch swings are large during the high-LR phase; pick from the
   final stable epochs or average neighbours, and confirm on test.
5. **Overlays**: view predictions on val and test frames (and on background-only frames). Metrics hide stretched or shifted boxes.
6. **Thresholds**: the board app filters by `viz_threshold`; choose it from precision/recall on val, not from the compile-time confidence.
7. **Record**: checkpoint hash, exp file, dataset report, split groups, metrics at the deployment size - the next person needs them.
