# Architecture and design

## What the skills describe
The **TI Edge AI SDK**: edgeai-tidl-tools on a PC (compile, calibrate, emulate), and on the board the Linux image with the C7x
firmware, TIDL runtime, ONNX Runtime with the TIDL provider, the `tiovx*` GStreamer plugins and edgeai-gst-apps. They are written as
guidance for the SDK: general rules, exact option names, error tables and procedures, with no dependence on one model, one dataset
or one board.

## The five skills
```
ti-edgeai-train-model  -->  ti-edgeai-import-model  -->  ti-edgeai-generate-config  -->  ti-edgeai-profile-pipeline
        (checkpoint)            (compiled model)              (running pipeline)               (numbers, levers)
                         all share  ti-edgeai-dev  (platform facts, rules, errors)
```
| Skill | Scope | Typical trigger |
|---|---|---|
| `ti-edgeai-dev` | platform reference: components, version matching, rules, board services, errors | "what do I need for a TI board", any TIDL / edgeai-gst-apps error |
| `ti-edgeai-import-model` | ONNX -> compile -> verify -> package -> deploy -> board-vs-host check, for detection / classification / segmentation | "deploy my model on the TI device" |
| `ti-edgeai-generate-config` | edgeai-gst-apps configs for camera / video / images, display / file / stream, mosaics; validator | "run it on the webcam", "show it on the screen" |
| `ti-edgeai-profile-pipeline` | model latency, layer cycles, pipeline latency, optimization levers | "why is it slow", "how many fps" |
| `ti-edgeai-train-model` | architecture and toolchain choice, datasets, splits, mask-to-box, deployment-matched evaluation | "train a model for the TI board" |

## Design rules
1. **SDK-level, not project-level.** Examples use TI zoo models and placeholders. A lesson learned on one project goes in only as a
   general rule with its reason.
2. **SoC differences live in one lookup table** (`ti-edgeai-dev/references/platforms.md`) and in script parameters
   (`TOOLS_SOC`, `GST_SOC`, `--target-device`, `--quant-scale-type`); skills never hard-code one chip's values in prose.
3. **Read the reference, do not recall it.** Each `SKILL.md` tells the agent to read the matching reference before acting; option names,
   SoC keys and version pairings are exact.
4. **Gates, not steps.** Each workflow phase ends with an observable check (log line, number, file) and a report that says what was
   run and what was not.
5. **Say what is verified.** Claims are either run (and the run is recorded in `references/sources.md`) or labelled not verified.
6. **Safe by default.** Anything that changes a board's system state (services, firmware, USB, reboot) needs the owner's consent;
   scripts only copy model folders and run apps unless told otherwise.
7. **One contract, written once.** Preprocessing, classes, thresholds, target and file hashes travel in a model manifest
   (`ti-edgeai-import-model/scripts/model_manifest.py`) shared by training hand-off, compile, evaluation, packaging and checks.
8. **Separate gates.** Runtime equivalence (identical tensors, host vs board), application correctness (the real GStreamer path) and task accuracy
   (held-out data) are different questions; none implies another.
9. **Tested scripts.** Scripts have unit tests where they can run without hardware (`skills/*/tests`), and the lint guards the
   structure (`scripts/validate_skills.py`).

## Layout of a skill
```
skills/<name>/
  SKILL.md              frontmatter + workflow + critical rules + reference table (<= 500 lines)
  references/*.md       detail, read on demand
  scripts/              tools (python / bash), documented in their docstrings
  assets/               templates and example configs
  tests/                unit tests that need no board
  evals/evals.json      prompts + expected behaviour
```
