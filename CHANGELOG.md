# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Versions apply to the plugin as a whole; each skill also carries its own
`metadata.version`.

## [0.1.0] - 2026-10-02
First release.

### Added
- Five skills for the TI Edge AI SDK (C7x/MMA with TIDL): `ti-edgeai-dev`, `ti-edgeai-import-model`, `ti-edgeai-generate-config`,
  `ti-edgeai-profile-pipeline`, `ti-edgeai-train-model`.
- SoC lookup table (TDA4VM, AM68A, AM69A, AM67A, AM62A) and SoC parameters in the scripts (`TOOLS_SOC`, `TIDL_TAG`, `GST_SOC`,
  `--platform`, `--quant-scale-type`, `--target-device`).
- Tools: ONNX preflight (advisory), TIDL compile in Docker, detection/classification evaluators, artifact version check, packaging,
  non-destructive deployment with a meaningful exit status, host-vs-board output comparison, config generator and validator, camera
  discovery, model/layer/pipeline profiling, a model manifest with file hashes, staged compile output (a failed compile keeps the
  previous artifacts).
- Claude Code and Codex installation (`scripts/install.sh --agent claude|codex --scope user|repo`), optional `agents/openai.yaml`
  metadata per skill, root `plugin.json` (portable layout).
- Repository lint (`scripts/validate_skills.py`), unit tests (`tests/run_tests.sh`, plus `tests/` in each skill), eval prompts,
  `docs/` (architecture, testing, verification status), CI workflow, plugin manifest, contribution guide, issue/PR templates.

### Verified
- On an SK-TDA4VM with Edge AI SDK 11.0: tools container build, detector and classifier compile + deploy, host-emulation vs board
  outputs, image/video/classification/mosaic configs, profiling tools. Everything else is documentation-derived and labelled
  "not verified" (`docs/verification-status.md`).
