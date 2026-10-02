"""Export an end-to-end YOLOX (TI-lite) detector for TIDL (SDK 11.0) in the TI model-zoo style.

The ONNX takes a uint8 BGR image [1,3,H,W] (no mean/scale; YOLOX trains on raw 0..255 BGR)
and returns `dets` [N,5] = x1,y1,x2,y2,score and `labels` [N]. The three raw head maps
[1,5+num_classes,h,w] (x,y,logw,logh,obj,cls... logits) are Concat outputs; TIDL replaces everything after
them with its native YOLOX detection layer described by the generated prototxt. The decode+NMS
tail left in the graph is used by CPU runtimes and for verification.
"""
import argparse
from pathlib import Path

import onnx
import torch
from torch import nn
from torchvision.ops import nms

from yolox.exp import get_exp

STRIDES = (8, 16, 32)


class Detector(nn.Module):
    def __init__(self, model, conf, nms_thr, top_k, num_classes):
        super().__init__()
        self.model, self.conf, self.nms_thr, self.top_k, self.nc = model, conf, nms_thr, top_k, num_classes

    def maps(self, x):
        head = self.model.head
        outs = []
        for i, f in enumerate(self.model.backbone(x)):
            f = head.stems[i](f)
            reg, cls = head.reg_convs[i](f), head.cls_convs[i](f)
            outs.append(torch.cat((head.reg_preds[i](reg), head.obj_preds[i](reg), head.cls_preds[i](cls)), 1))
        return outs

    def forward(self, image):
        x = image.float()
        rows = []
        for m, s in zip(self.maps(x), STRIDES):
            h, w = m.shape[2:]
            r = m.permute(0, 2, 3, 1).reshape(-1, 5 + self.nc)
            yy, xx = torch.meshgrid(torch.arange(h), torch.arange(w), indexing="ij")
            grid = torch.stack((xx, yy), -1).reshape(-1, 2).to(r)
            xy, wh = (r[:, :2] + grid) * s, r[:, 2:4].exp() * s
            score, label = (r[:, 4:5].sigmoid() * r[:, 5:].sigmoid()).max(1)  # best class per anchor
            rows.append(torch.cat((xy - wh / 2, xy + wh / 2, score[:, None], label[:, None].to(r.dtype)), 1))
        det = torch.cat(rows, 0)
        det = det[det[:, 4] >= self.conf]
        keep = nms(det[:, :4], det[:, 4], self.nms_thr)[: self.top_k]  # class-agnostic NMS
        det = det[keep]
        return det[:, :5], det[:, 5].to(torch.int64)


def head_concat_names(graph):
    """Output names of each head's Concat(reg, obj, cls), ordered stride 8/16/32."""
    prod = {o: n for n in graph.node for o in n.output}
    found = []
    for n in graph.node:
        if n.op_type == "Concat" and len(n.input) == 3 and all(prod.get(i) is not None and prod[i].op_type == "Conv" for i in n.input):
            found.append(n.output[0])
    return found


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--exp-file", type=Path, required=True, help="YOLOX experiment (TI-lite: ReLU, conv stem, 3x3 pools), num_classes set")
    p.add_argument("--output", type=Path, required=True, help="model .onnx path; .prototxt is written next to it")
    p.add_argument("--input-hw", type=int, nargs=2, help="override export H W (multiples of 32); default exp.test_size")
    p.add_argument("--conf", type=float, default=0.05, help="score threshold in the ONNX tail")
    p.add_argument("--proto-conf", type=float, default=0.1, help="confidence_threshold in the prototxt")
    p.add_argument("--nms", type=float, default=0.45)
    p.add_argument("--top-k", type=int, default=200)
    a = p.parse_args()
    exp = get_exp(str(a.exp_file), None)
    model = exp.get_model()
    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(ck.get("model", ck), strict=True)
    model.eval()
    H, W = a.input_hw or exp.test_size
    det = Detector(model, a.conf, a.nms, a.top_k, exp.num_classes).eval()
    a.output.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randint(0, 255, (1, 3, H, W), dtype=torch.uint8)
    torch.onnx.export(det, dummy, str(a.output), input_names=["images"], output_names=["dets", "labels"],
                      dynamic_axes={"dets": {0: "n"}, "labels": {0: "n"}}, opset_version=11, dynamo=False)
    m = onnx.load(str(a.output))
    names = head_concat_names(m.graph)
    assert len(names) == 3, f'expected 3 head Concat nodes, found {names}'
    onnx.checker.check_model(m)
    params = "".join(f'  yolo_param {{\n    input: "{n}"\n    anchor_width: {s}.0\n    anchor_height: {s}.0\n  }}\n'
                     for n, s in zip(names, STRIDES))
    proto = (f'name: "yolox"\ntidl_yolo {{\n{params}  detection_output_param {{\n    num_classes: {exp.num_classes}\n    share_location: true\n'
             f'    background_label_id: -1\n    nms_param {{\n      nms_threshold: {a.nms}\n      top_k: {a.top_k}\n    }}\n'
             f'    code_type: CODE_TYPE_YOLO_X\n    keep_top_k: {a.top_k}\n    confidence_threshold: {a.proto_conf}\n  }}\n'
             f'  name: "yolox"\n  in_width: {W}\n  in_height: {H}\n  output: "dets"\n  output: "labels"\n  framework: "MMDetection"\n}}')
    a.output.with_suffix(".prototxt").write_text(proto)
    print("head concat outputs:", names)


if __name__ == "__main__":
    main()
