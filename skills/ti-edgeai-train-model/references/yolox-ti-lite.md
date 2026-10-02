# Worked example: YOLOX-tiny TI-lite with upstream YOLOX

Worked example (tested on one GPU and a TDA4VM deployment): upstream Megvii YOLOX repo + `assets/exp_ti_lite_template.py` + TI's
`yolox_tiny_ti_lite.pth` checkpoint.

```bash
cp assets/exp_ti_lite_template.py <YOLOX>/exps/example/custom/
cd <YOLOX>
DATA_DIR=datasets/mydata NUM_CLASSES=3 EXP_NAME=mydet INPUT_H=640 INPUT_W=640 MAX_EPOCH=100 \
python tools/train.py -f exps/example/custom/exp_ti_lite_template.py -d 1 -b 16 --fp16 \
    -c pretrained/yolox_tiny_ti_lite.pth -l tensorboard
```
- TI-lite changes: conv stem instead of Focus, ReLU, 3x3-pool SPP, BN eps 1e-3 / momentum .03. Loading TI's checkpoint into a new class
  count replaces only the class head (tested: all other tensors match; the template also loads its own trained checkpoints with
  `strict=True`).
- Fixed input size (no multi-scale) so deploy size == train size; `no_aug_epochs 10` (no mosaic at the end); `max_labels` derived from
  the data (never truncate boxes).
- Training log metric to watch: COCO AP on the val split every epoch; selection noise is large while LR is high.
- Export for the board: `ti-edgeai-import-model/scripts/export_yolox_tidl_det.py --exp-file <this exp> --checkpoint best_ckpt.pth
  --input-hw H W` (set the same env vars). Evaluate float at the export size and policy before compiling.
- Compare with TI's own fork (`edgeai-yolox`, `--export-det`) if you need TI's exact export.
- Batch 16 at 640x640 with fp16 fits in a few GB of GPU memory; on a shared machine data loading is the usual bottleneck.
