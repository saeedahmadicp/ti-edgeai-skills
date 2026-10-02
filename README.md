# ti-edgeai-skills

Agent skills for the Texas Instruments Edge AI SDK. They cover training, compiling, deploying, running and profiling neural
networks on TI processors with a C7x DSP and MMA accelerator (TDA4VM, AM68A, AM69A, AM67A, AM62A), using TI's
[edgeai-tidl-tools](https://github.com/TexasInstruments/edgeai-tidl-tools) on the PC and the Edge AI Linux SDK with
[edgeai-gst-apps](https://github.com/TexasInstruments/edgeai-gst-apps) on the board.

The skills work with Claude Code and Codex. They are written against the SDK rather than any particular model or board.

## Contents

- [Skills](#skills)
- [Installation](#installation)
- [Usage](#usage)
- [Requirements](#requirements)
- [Supported hardware](#supported-hardware)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## Skills

| Skill | Purpose |
|---|---|
| [`ti-edgeai-dev`](skills/ti-edgeai-dev) | SDK components, SoC lookup table, tools-to-SDK version matching, board services, troubleshooting |
| [`ti-edgeai-train-model`](skills/ti-edgeai-train-model) | Architecture and toolchain choice for TIDL, datasets and group-wise splits, deployment-matched evaluation |
| [`ti-edgeai-import-model`](skills/ti-edgeai-import-model) | ONNX preflight, TIDL compile in Docker, accuracy checks, packaging, deployment, host-versus-board comparison |
| [`ti-edgeai-generate-config`](skills/ti-edgeai-generate-config) | Generate, validate and run edgeai-gst-apps configs (camera, video, images, display, stream, mosaic) |
| [`ti-edgeai-profile-pipeline`](skills/ti-edgeai-profile-pipeline) | Model latency, per-layer C7x cycles, GStreamer element latency, optimization levers |

A typical project uses them in this order: `dev` for orientation, `train-model`, `import-model`, `generate-config`, `profile-pipeline`.
Each skill is a folder with a `SKILL.md`, plus `references/`, `scripts/`, `assets/`, `tests/` and `evals/` where needed.

## Installation

### Claude Code plugin

```
/plugin marketplace add /path/to/ti-edgeai-skills
/plugin install ti-edgeai-skills@ti-edgeai-skills-dev
```

Use `<owner>/ti-edgeai-skills` instead of the path once the repository is hosted on GitHub.

### Skills directory (Claude Code or Codex)

`scripts/install.sh` symlinks the skills into the folder the agent reads. It does not delete or overwrite anything.

| Command | Folder |
|---|---|
| `scripts/install.sh` | `~/.claude/skills` |
| `scripts/install.sh --agent claude --scope repo` | `<repo>/.claude/skills` |
| `scripts/install.sh --agent codex` | `~/.agents/skills` |
| `scripts/install.sh --agent codex --scope repo` | `<repo>/.agents/skills` |

Add `--dry-run` to preview. A root `plugin.json` (portable plugin layout) and per-skill `agents/openai.yaml` are included for Codex.
Codex discovery has not been tested; the paths follow OpenAI's documentation.

## Usage

Describe the task and the matching skill loads. In Codex a skill can also be named explicitly with `$`.

```
Which edgeai-tidl-tools release do I need for my TI board?
$ti-edgeai-import-model compile model.onnx for my board and deploy it
Run my detector on the USB camera and save the output
Why is my pipeline slower than 30 fps?
```

## Requirements

- A TI Edge AI board reachable over SSH, running the Edge AI SDK Linux image.
- Docker on a PC, for the TIDL tools container.
- Python 3 with PyYAML for the config tools. numpy, OpenCV and onnx are needed by some scripts and are present in the container.
- A GPU only for training.

Board addresses are placeholders (`root@<board-ip>`). Nothing in the repository stores credentials.

## Supported hardware

| SoC | Status |
|---|---|
| TDA4VM (J721E, AM68PA) | Tested end to end on Edge AI SDK 11.0 |
| AM68A, AM69A, AM67A, AM62A | Values taken from TI documentation, not tested |

SoC-specific values (tools `SOC`, gst-apps `SOC`, quantization support) are collected in
[`platforms.md`](skills/ti-edgeai-dev/references/platforms.md). What has and has not been run is listed in
[docs/verification-status.md](docs/verification-status.md).


## Documentation

- [docs/architecture.md](docs/architecture.md): how the skills fit together and the design rules
- [docs/testing.md](docs/testing.md): test levels, hardware verification protocol, running the evals
- [docs/verification-status.md](docs/verification-status.md): what was run, on which hardware
- [CHANGELOG.md](CHANGELOG.md)

## Testing

```bash
pip install pyyaml numpy opencv-python-headless onnx
tests/run_tests.sh
```

This runs the lint and the unit tests. No board or GPU is required. Tests that need a missing dependency are skipped.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Reports from boards other than the TDA4VM are the most useful contribution.

## License

MIT, see [LICENSE](LICENSE). TI's tools, SDK and model zoo are under their own licenses and are not redistributed here.
