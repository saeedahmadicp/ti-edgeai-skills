"""YOLOX-Tiny "TI-lite" experiment for TI C7x/MMA deployment (tested on TDA4VM; upstream Megvii YOLOX repo + this file).

Copy into <YOLOX>/exps/example/custom/ and run, e.g.:
    DATA_DIR=datasets/mydata NUM_CLASSES=1 EXP_NAME=mydet INPUT_H=640 INPUT_W=640 \
    python tools/train.py -f exps/example/custom/exp_ti_lite_template.py -d 1 -b 16 --fp16 \
        -c pretrained/yolox_tiny_ti_lite.pth -l tensorboard

TI-lite = the architecture TI's edgeai-yolox uses so the network quantizes well and fully offloads to TIDL:
  * Focus slice-stem  -> conv 3->12 (3x3, stride 2) + conv 12->24 (3x3)      (conv_focus=True)
  * SiLU              -> ReLU
  * SPP maxpool 5/9/13 -> repeated 3x3 stride-1 maxpools (same receptive field)
  * BatchNorm eps 1e-3, momentum .03 (matches the TI checkpoints)
Dataset layout (COCO): DATA_DIR/{train2017,val2017,test2017}/*.jpg and DATA_DIR/annotations/instances_{train,val,test}2017.json.
Pretrained weights: TI's `yolox_tiny_ti_lite.pth` (COCO). Loading into a new class count replaces only the class head
(`cls_preds`); every other tensor matches (verified: 462 tensors match, 6 new).
"""
import json
import os
from pathlib import Path

import torch.nn as nn

from yolox.exp.default.yolox_tiny import Exp as TinyExp
from yolox.models.network_blocks import BaseConv


class Exp(TinyExp):
    def __init__(self):
        super().__init__()
        self.exp_name = os.environ.get("EXP_NAME", "ti_lite_detector")
        self.num_classes = int(os.environ.get("NUM_CLASSES", "1"))
        self.data_dir = os.environ["DATA_DIR"]
        self.output_dir = os.environ.get("OUTPUT_DIR", "./YOLOX_outputs")
        self.train_ann, self.val_ann, self.test_ann = (f"instances_{s}2017.json" for s in ("train", "val", "test"))
        self.eval_split = "val"                      # keep "test" for the final report only
        self.act = "relu"
        h, w = int(os.environ.get("INPUT_H", 640)), int(os.environ.get("INPUT_W", 640))
        self.input_size = self.test_size = (h, w)
        self.random_size = (h // 32, h // 32)        # fixed size (no multi-scale): keeps memory bounded, deploy size == train size
        self.multiscale_range = 0
        self.seed = 42
        self.max_epoch = int(os.environ.get("MAX_EPOCH", 100))
        self.no_aug_epochs = 10                      # last epochs without mosaic/mixup
        self.eval_interval = 1
        self.save_history_ckpt = False
        self.data_num_workers = int(os.environ.get("WORKERS", 4))
        self.print_interval = 5
        self.max_labels = 50
        ann = Path(self.data_dir) / "annotations" / self.train_ann
        if ann.exists():                             # never truncate boxes: size label capacity from the data
            counts = {}
            for a in json.loads(ann.read_text())["annotations"]:
                counts[a["image_id"]] = counts.get(a["image_id"], 0) + 1
            self.max_labels = max(50, max(counts.values(), default=0))

    # ---- data (COCO folders under DATA_DIR) ----
    def get_dataset(self, cache=False, cache_type="ram"):
        from yolox.data import COCODataset, TrainTransform
        return COCODataset(data_dir=self.data_dir, json_file=self.train_ann, name="train2017", img_size=self.input_size,
                           preproc=TrainTransform(max_labels=self.max_labels, flip_prob=self.flip_prob, hsv_prob=self.hsv_prob),
                           cache=cache, cache_type=cache_type)

    def get_data_loader(self, batch_size, is_distributed, no_aug=False, cache_img=None):
        from yolox.data import TrainTransform
        loader = super().get_data_loader(batch_size, is_distributed, no_aug, cache_img)
        # 4-image mosaic can hold 4x the labels of one image
        loader.dataset.preproc = TrainTransform(max_labels=self.max_labels * 4, flip_prob=self.flip_prob, hsv_prob=self.hsv_prob)
        return loader

    def get_eval_dataset(self, **kwargs):
        from yolox.data import COCODataset, ValTransform
        test = kwargs.get("testdev", False) or self.eval_split == "test"
        return COCODataset(data_dir=self.data_dir, json_file=self.test_ann if test else self.val_ann,
                           name="test2017" if test else "val2017", img_size=self.test_size,
                           preproc=ValTransform(legacy=kwargs.get("legacy", False)))

    # ---- TI-lite model ----
    def get_model(self):
        if getattr(self, "model", None) is None:
            model = super().get_model()
            backbone = model.backbone.backbone
            backbone.stem = nn.Sequential(BaseConv(3, 12, 3, 2, act=self.act),
                                          BaseConv(12, int(self.width * 64), 3, 1, act=self.act))
            backbone.dark5[1].m = nn.ModuleList([nn.Sequential(*[nn.MaxPool2d(3, 1, 1) for _ in range((k - 1) // 2)])
                                                 for k in (5, 9, 13)])
            for m in model.modules():
                if isinstance(m, nn.BatchNorm2d):
                    m.eps, m.momentum = 1e-3, .03
        return self.model
