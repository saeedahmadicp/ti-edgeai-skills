# Datasets, labels and splits

## Layouts
- Detection: COCO (`<split>2017/*.jpg`, `annotations/instances_<split>2017.json`, `categories` ids from 1). Boxes `[x, y, w, h]` in
  original pixels. ModelMaker wants `images/` + `annotations/instances.json`.
- Classification: `root/<class_name>/*.jpg`. Segmentation: image + index-mask PNG pairs (same stem).
- Use symlinks for splits so the raw data stays untouched.

## Label quality (look, do not just validate)
File checks (readable, sizes match, values in range) catch plumbing errors only. Overlay a sample (spread over groups and over
foreground fractions) and decide the labeling rule: what counts as the object, what is excluded (reflections, partial, tiny). Write the
rule down; inconsistent rules cap accuracy.

## Boxes from masks (only when the task is detection)
Segmentation masks and detection boxes are different tasks. Derive boxes only when the user wants a detector; otherwise train a
segmentation model. When deriving, the box rule is a labeling decision to write down and review, not a default:
- Per-component boxes are fine when each object is one connected blob. When one object is many disconnected pieces, per-component
  boxes can be a few pixels wide and unlearnable; decide how pieces merge (dilate then label, cluster by distance) and a minimum box
  size in original pixels.
- Look at overlays across groups and foreground fractions, and check the box-size distribution *at the training resolution* (divide
  by the resize factor) before training.
- Labels derived this way are a heuristic: strict-IoU metrics (AP75, mAP50:95) have a ceiling; AP50 and recall are more informative.
The conversion is dataset-specific; write it for your data and keep the script with the dataset report.

## Splits that do not leak
Group by the unit that makes frames similar (recording session, scene, video, patient, site) and assign whole groups to
train/val/test (greedy by size, or by hand for few groups). Consecutive frames of one video are near-duplicates: a random
split inflates validation. If one group dominates, the target fractions cannot be met; the honest fix is more groups. Keep the
test groups out of training, checkpoint selection and calibration.
Augmented copies of an image must stay with their source group.

## Calibration set
Draw >= 50 evenly spaced images from the **training** split for TIDL calibration (`compile_tidl.py --calib <dir>`).

## Class balance and empties
Include negative images (no object) if the camera will see them in deployment; otherwise false positives on clean scenes are
invisible in validation. State which backgrounds were never trained on.
