# AGENTS.md

Guidance for AI agents contributing to this repository. Read [CONTRIBUTING.md](CONTRIBUTING.md) first; it applies to you too.

- This repo is a set of skills (`skills/*/SKILL.md`), not an application. The product is the text and the tested scripts.
- Never write a claim as verified unless you ran it and have the output. Mark anything else "not verified".
- Keep content SDK-level and generic (see docs/architecture.md): SoC-dependent values belong in `ti-edgeai-dev/references/platforms.md` and in script parameters, not in prose.
- Keep content generic: no project names, datasets, board IPs, usernames or absolute home paths.
- Do not touch a board's system state (services, firmware, reboot, USB) without the user's explicit go-ahead.
- After any edit run `tests/run_tests.sh`; it must pass.
- Codex and Claude Code read the same `SKILL.md`; keep behaviour there. Never claim Codex behaviour you have not observed.
- Do not commit or push unless asked. Do not add compiled artifacts, ONNX files or datasets.
- Skill names are the directory names; renaming one means updating every cross-reference (the lint catches broken paths, not
  broken skill names, so grep).
