# Testing

Four levels, cheapest first. A change should pass the first two and show evidence for the others where it makes a claim at that level.

| Level | Command | Needs | Checks |
|---|---|---|---|
| 1. Lint | `python3 scripts/validate_skills.py` | PyYAML | frontmatter, naming, links, orphan references, script syntax, eval files, no IPs / home paths / credentials |
| 2. Unit tests (also run by CI, `.github/workflows/ci.yml`) | `tests/run_tests.sh` | Python 3; PyYAML, numpy, onnx for the tests that need them (they skip otherwise) | script behaviour that does not need hardware: lint fixtures, config generator + validator contracts, calibration sampling, packaging contracts, manifest, host-vs-board comparison gate, deployment safety (simulated board), camera discovery, artifact stamp, layer-cycle parser |
| 3. Skill evals | `evals/evals.json` in each skill, run with Claude Code's `skill-creator` (with vs without the skill) | an agent | that the skill triggers and changes behaviour as the `expected_behavior` list says |
| 4. Hardware | the commands in the skill, on a real board | a board + Docker host | that what the skill claims works; record board, SoC, SDK, tools tag and output |

## Terms
*Tested* = run on hardware with the result checked (recorded in `docs/verification-status.md` and `references/sources.md`).
*Simulated* = exercised in unit tests against stand-ins (for example `deploy_to_board.sh` against a fake ssh/scp board). *Documented only*
= taken from TI documentation. Never present the last two as the first.

## Hardware verification protocol
1. Note the board's SoC, SDK (`env | grep -i EDGEAI`) and the edgeai-tidl-tools tag used.
2. Follow the skill's phases literally; do not fix things silently.
3. Keep the gate outputs: `Subgraph Compiled Successfully`, version stamp check, `Offloaded Nodes N/N`, exit code, board-vs-host
   difference, and a viewed output frame for detectors.
4. Open a *Verification report* issue or a PR that moves the item in `docs/verification-status.md` and `references/sources.md`.

## Running the evals in Codex or Claude Code
The eval prompts are agent-neutral. For each `question` in a skill's `evals/evals.json`:
1. Start a fresh session in a scratch directory with a board stand-in (a stub `ssh` that records commands is enough for authorization and
   prerequisite cases). Run once with the skills installed (`scripts/install.sh --agent codex` or `--agent claude`) and once without
   (baseline), same model and settings.
2. Claude Code: `skill-creator`'s eval loop automates this. Codex: invoke implicitly with the plain question, and explicitly with
   `$<skill-name> <question>`; check implicit selection separately from explicit invocation.
3. Grade the transcript against `expected_behavior`: skill selected (or correctly not selected for `negative`), missing SDK/SoC
   information asked for instead of assumed, authorization requested *before* any board-state command, partial workflows stop where
   asked, failures diagnosed with the documented checks.
4. Keep sanitized transcripts, the assertions, agent/model versions, and timing with the result. Until that is done the prompts are
   specifications, not measurements.

## Writing evals
Each entry: `id`, `question` (what a user would really type, not naming the skill), `expected_skill`, `ground_truth` (a short correct
answer), `expected_behavior` (observable checks, including what the agent must not do). Each entry has a `category`: `positive`, `negative` (`expected_skill: null`, the skill
must not trigger), `prerequisite` (missing information, ask instead of assuming), `authorization` (board-state changes need a yes first),
`partial` (only one phase requested) or `recovery` (a failure to diagnose). The lint requires >= 1 negative per skill. The shipped prompts have
not been benchmarked against a no-skill baseline yet; that needs the skill-creator eval loop and sanitized logs kept with the results.
