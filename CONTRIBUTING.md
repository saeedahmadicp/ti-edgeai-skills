# Contributing

Every claim in these skills is either run on hardware or marked as not run, so a change needs evidence (command output, board, SDK
version), not only wording.

## What we welcome
- **Corrections** backed by a run: a wrong command, a stale SDK/tag mapping, a missing failure mode.
- **Verification reports**: you ran something listed as "not verified" (display, CSI camera, OpTIFlow, mixed precision, QAT,
  segmentation, other SDK lines or boards). Open a *Verification report* issue or a PR that moves the item to "verified" with output.
- **New model families** in `ti-edgeai-import-model/references/other-model-families.md`, with the TIDL meta-architecture settings you
  actually compiled.
- **Support for another TI processor**: the SoC lookup table (`ti-edgeai-dev/references/platforms.md`) already lists AM68A, AM69A,
  AM67A and AM62A from TI's documentation. Run the workflow on the real board, fix what differs, and move the row to verified in
  `docs/verification-status.md`. Only add a SoC-specific section where behaviour truly differs.
- **New skills**, if they cover a distinct workflow the existing five do not. Open an issue first; the set is intentionally small.

## What we do not accept
- Project-specific content: dataset names, model names from a private project, board IPs, hostnames, credentials, absolute home paths.
  `scripts/validate_skills.py` rejects the obvious ones.
- Guidance that only holds for one model, dataset or board and is written as if general.
- Claims copied from documentation but written as if tested.
- Bundled model weights, compiled artifacts (`*.bin`) or datasets.
- Rewrites for style only.

## Setup
```bash
git clone <repo> && cd ti-edgeai-skills
pip install pyyaml
tests/run_tests.sh                          # lint + unit tests; must pass before and after your change
scripts/install.sh                          # optional: link skills into ~/.claude/skills to try them
scripts/install.sh --agent codex --scope repo   # or into <repo>/.agents/skills for Codex (see README)
```

## Anatomy of a skill
```
skills/<kebab-case-name>/
  SKILL.md              required: frontmatter (name == directory, description) + workflow, <= 500 lines
  references/*.md       detail loaded on demand; link each one from SKILL.md (or another reference)
  scripts/              tested tools; each runs with --help and a documented example
  assets/               templates used in outputs
  tests/                unit tests for scripts that can run without a board
  evals/evals.json      >= 3 realistic prompts with the behaviour you expect (>= 1 negative)
  agents/openai.yaml    optional Codex metadata: interface.display_name, short_description, default_prompt (mention `$<skill-name>`)
```
Skill names are `ti-edgeai-<verb>-<noun>` and equal the directory name. See `docs/architecture.md` for the design rules and
`docs/testing.md` for the four test levels.

### Writing `SKILL.md`
- **The description is the trigger.** Say what the skill does and list the situations, phrases and error messages that should
  activate it, including cases where the user never says the tool's name. Descriptions that are too modest do not get loaded.
- **Explain why.** The reader is a capable model; a rule with its reason generalises, a bare "NEVER" does not. Put the reasons
  next to the rules that cost someone a day.
- **Negative and edge cases in evals.** Every skill's `evals/evals.json` needs at least one negative prompt (`expected_skill: null`); add
  prerequisite, authorization, partial-workflow and failure-recovery prompts where the skill can go wrong (`category` field).
- **Gates, not steps.** Each phase ends in a check with an observable result (a log line, a number, a file), and the report format
  says what was run and what was not.
- **Progressive disclosure.** Keep `SKILL.md` to the workflow; push tables, option lists and long error catalogues into `references/`.
- **Generic.** Use public models (TI zoo) in examples and placeholders (`<board-ip>`, `<images_dir>`). A project-specific lesson is
  welcome only when restated as a general rule with the reason.
- **Version-stamp what you tested**: SDK version, tools tag, board, in `metadata.tested_on`. Terms (see `docs/testing.md`): *tested* = run
  on hardware with the result checked; everything else is *documented only*.

### Scripts
- Python 3, standard library plus what the skill already requires; argparse with `--help` and a docstring that shows an example.
- No hidden state: paths, IPs and tags come from arguments or environment variables.
- Anything that changes the board (copying files, stopping services, rebooting) is explicit and documented. Scripts never delete: they
  refuse to overwrite and offer a backup-then-replace option; board-state changes need the user's authorization *before* they run
  (ask, wait, record the original state, give restore steps) in both the skill text and its eval.
- Scripts exit non-zero on failure, and a wrapper's exit status is the wrapped program's.
- Preprocessing and class information flows through the model manifest (`ti-edgeai-import-model/references/model-manifest.md`), not through
  re-typed flags.

## Codex and Claude Code parity
Both agents read the same `SKILL.md`; keep behaviour in it, never in agent-specific files. `agents/openai.yaml` only carries display
metadata and an invocation prompt. Do not claim Codex behaviour you have not observed: say "documented" or attach the transcript.

## Test your change
1. `tests/run_tests.sh` (lint + unit tests). Add a unit test with any script change that can be tested without hardware.
2. Run the script or command you touched, on real hardware where the claim is about hardware. Keep the output for the PR.
3. For behaviour changes, run the skill's eval prompts with and without the skill (the Claude Code `skill-creator` skill automates
   this) and check the new behaviour appears. Add a prompt that fails without your change.
4. Re-read the diff for anything that identifies your project, network or hardware inventory.

## Pull requests
- Branch from `main`; one concern per PR.
- Fill in the PR template: problem, change, evidence, environment (board, SDK, tools tag).
- Update `CHANGELOG.md` and bump the skill's `metadata.version` (patch for fixes, minor for new content).
- A PR that adds an unverified claim must label it "not verified" in the skill and list it in `references/sources.md` and
  `docs/verification-status.md`.

## Reporting problems
Use the issue templates. Include the board SDK (`env | grep -i EDGEAI`), the tools tag, and the output that shows the failure.

## Conduct
Be kind, be specific, assume good faith. Disagreements are settled by running the thing.
