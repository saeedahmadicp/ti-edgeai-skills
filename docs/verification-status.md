# Verification status

"Run" means executed on hardware with the result checked; everything else was read from TI documentation. Update this file with
every verification report.

| Area | TDA4VM | AM68A | AM69A | AM67A | AM62A |
|---|---|---|---|---|---|
| Tools container build from the shipped Dockerfile | run (SDK 11.0, tag 11_00_06_00) | not run | not run | not run | not run |
| Detector compile (meta-architecture) + deploy | run | not run | not run | not run | not run |
| Classifier compile + deploy | run | not run | not run | not run | not run |
| Host emulation == board outputs | run (bit-identical, detector and classifier) | not run | not run | not run | not run |
| Image / video / classification / mosaic configs | run | not run | not run | not run | not run |
| USB webcam to file output | run | not run | not run | not run | not run |
| Profiling tools (model time, layer cycles, tracer) | run | not run | not run | not run | not run |
| Display output on screen | **not confirmed** | not run | not run | not run | not run |
| CSI cameras, OpTIFlow, C++ app | not run | not run | not run | not run | not run |
| Mixed precision / QAT compile | not run | not run | not run | not run | not run |
| Segmentation compile | not run (zoo model timing only) | not run | not run | not run | not run |
| Multi-class detector meta layer | not run | not run | not run | not run | not run |
| Asymmetric quantization (`--quant-scale-type 4`) | n/a (not supported) | not run | not run | not run | not run |
| Multi-C7x | n/a | n/a | not run | n/a | n/a |

Details of what was run, on which software versions, are in `skills/ti-edgeai-dev/references/sources.md`.

## Simulated or offline only (not run on a board)
| Item | How it was exercised |
|---|---|
| `deploy_to_board.sh` (staging, refusal to overwrite, backup-and-replace, exit status) | unit tests against a fake ssh/scp board; the previous version was run on a TDA4VM |
| `package_model.py` metadata-derived outputs and node coverage | unit tests and one run on previously compiled TDA4VM artifacts (no board involved) |
| `compile_tidl.py` calibration-count alignment, `--manifest`, `--quant-scale-type` | unit tests of the sampling helpers, plus one container smoke compile of a tiny float classifier through `--manifest` (5 calibration images used and reported honestly; that toy model produced no accelerator subgraph, so offload was not exercised); a real detector compile was not re-run |
| `board_host_check.py compare` (strict gate) | unit tests on synthetic outputs |
| `discover_cameras.sh` | unit tests with a simulated `v4l2-ctl` |
| `Dockerfile.tidl-tools` (pipefail, tools-path check, `SOC`/`TIDL_TAG` build args) | built once for `am68pa` / `11_00_06_00` after the change (setup layers were cached); other SoC values untested |
| `scripts/install.sh` options (`--agent`, `--scope`, `--dry-run`, `--force`) | unit tests with temporary HOME/cwd (symlink targets, idempotence, no replacement of foreign links or real folders) |
| `compile_tidl.py` staged output (failed compile keeps the previous artifacts; success keeps the old folder as `.previous-<time>`) | unit tests of the helper, plus container smoke runs of a toy model: success, replacement, and a failing compile that left the earlier artifacts untouched |

## Documented only (OpenAI Codex)
Skill discovery in `.agents/skills` / `~/.agents/skills`, symlink support, `$skill-name` invocation, `agents/openai.yaml` fields and the root
`plugin.json` layout come from OpenAI's documentation (learn.chatgpt.com/docs/build-skills, developers.openai.com/plugins/build/plugins).
No Codex session was run against these skills; the Codex marketplace entry (`.agents/plugins/marketplace.json`) was not created.
