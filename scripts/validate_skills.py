#!/usr/bin/env python3
"""Lint every skill in skills/ (the repository's only automated test; no dependencies beyond PyYAML).

    python3 scripts/validate_skills.py            # all skills
    python3 scripts/validate_skills.py skills/ti-edgeai-dev

Checks, per skill:
  - SKILL.md has YAML frontmatter with `name` (== directory name, kebab-case) and a `description` (<= 1024 chars)
  - SKILL.md is <= 500 lines (move detail into references/)
  - every `references/...`, `scripts/...`, `assets/...` path named in SKILL.md exists
  - every cross-skill path (`ti-edgeai-<name>/references|scripts|assets/...`) written anywhere in the skill exists
  - every file in references/ is linked from SKILL.md or from another reference (no orphans)
  - scripts/*.py compile, scripts/*.sh pass `bash -n`
  - evals/evals.json is valid JSON: >= 3 prompts, unique ids, required keys, valid category, and >= 1 negative case (expected_skill null)
  - agents/openai.yaml (optional Codex metadata), when present, has interface.display_name / short_description / default_prompt, and
    default_prompt mentions $<skill-name>
  - no cache files, no private IPv4 addresses, no absolute home paths, no credentials
Repository-level: plugin.json, .claude-plugin/plugin.json and marketplace.json agree on name and version.
Exit status is non-zero when any check fails.
"""
import json
import py_compile
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PATH_RE = re.compile(r"(?<![A-Za-z0-9_/-])((?:references|scripts|assets)/[A-Za-z0-9_./-]*[A-Za-z0-9_])(?![{A-Za-z0-9_])")
FORBIDDEN = [
    (re.compile(r"\b(?:192\.168|10\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-5])|172\.(?:1[6-9]|2\d|3[01]))\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-5]|0)\.(?:[1-9]\d?|1\d\d|2[0-4]\d|25[0-5]|0)\b"), "private IPv4 address"),
    (re.compile(r"/home/[a-z0-9_-]+/"), "absolute home path"),
    (re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|secret)\s*[:=]\s*\S+"), "credential-looking text"),
]
XSKILL_RE = re.compile(r"\b(ti-edgeai-[a-z-]+)/((?:references|scripts|assets)/[A-Za-z0-9_./-]*[A-Za-z0-9_])(?![{A-Za-z0-9_])")
EVAL_CATEGORIES = {"positive", "negative", "prerequisite", "authorization", "partial", "recovery"}
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt", ".prototxt", ""}


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None


def check_skill(d):
    errs = []
    skill_md = d / "SKILL.md"
    if not skill_md.is_file():
        return [f"{d.name}: missing SKILL.md"]
    text = skill_md.read_text()
    fm = frontmatter(text)
    if not isinstance(fm, dict):
        return [f"{d.name}: SKILL.md has no valid YAML frontmatter"]
    if fm.get("name") != d.name:
        errs.append(f"{d.name}: frontmatter name {fm.get('name')!r} != directory name")
    if not NAME_RE.match(str(fm.get("name", ""))):
        errs.append(f"{d.name}: name must be lowercase kebab-case")
    desc = str(fm.get("description", "")).strip()
    if not desc:
        errs.append(f"{d.name}: missing description")
    elif len(desc) > 1024:
        errs.append(f"{d.name}: description is {len(desc)} chars (limit 1024)")
    if text.count("\n") > 500:
        errs.append(f"{d.name}: SKILL.md is {text.count(chr(10))} lines (limit 500); move detail to references/")

    for rel in sorted(set(PATH_RE.findall(text))):
        if "<" in rel or "*" in rel:
            continue
        if not (d / rel.rstrip("/.")).exists():
            errs.append(f"{d.name}: SKILL.md mentions {rel} which does not exist")

    refs = list((d / "references").glob("*.md")) if (d / "references").is_dir() else []
    corpus = text + "".join(p.read_text() for p in refs)
    for r in refs:
        if r.name not in corpus.replace(f"references/{r.name}", r.name) or \
                not any(r.name in t for t in [text] + [p.read_text() for p in refs if p != r]):
            errs.append(f"{d.name}: references/{r.name} is not linked from SKILL.md or another reference")

    for f in (d / "scripts").glob("*") if (d / "scripts").is_dir() else []:
        if f.suffix == ".py":
            try:
                py_compile.compile(str(f), cfile=tempfile.mktemp(suffix=".pyc"), doraise=True)
            except py_compile.PyCompileError as e:
                errs.append(f"{d.name}: {f.name} does not compile: {e.msg.strip()}")
        elif f.suffix == ".sh":
            if subprocess.run(["bash", "-n", str(f)], capture_output=True).returncode:
                errs.append(f"{d.name}: {f.name} fails bash -n")

    ev = d / "evals" / "evals.json"
    if not ev.is_file():
        errs.append(f"{d.name}: missing evals/evals.json")
    else:
        try:
            items = json.loads(ev.read_text()).get("evals", [])
        except json.JSONDecodeError as e:
            items = None
            errs.append(f"{d.name}: evals.json invalid: {e}")
        if items is not None:
            if len(items) < 3:
                errs.append(f"{d.name}: evals.json has {len(items)} prompts (need >= 3)")
            ids = [e.get("id") for e in items]
            if len(set(ids)) != len(ids):
                errs.append(f"{d.name}: evals.json has duplicate ids")
            for e in items:
                missing = [k for k in ("id", "question", "expected_skill", "ground_truth", "expected_behavior") if k not in e]
                if missing:
                    errs.append(f"{d.name}: eval {e.get('id')} lacks {missing}")
                if e.get("category", "positive") not in EVAL_CATEGORIES:
                    errs.append(f"{d.name}: eval {e.get('id')} has unknown category {e.get('category')!r}")
            if not any(e.get("expected_skill") is None for e in items):
                errs.append(f"{d.name}: evals.json has no negative case (expected_skill null); see docs/testing.md")

    oy = d / "agents" / "openai.yaml"
    if oy.is_file():
        try:
            meta = yaml.safe_load(oy.read_text()) or {}
        except yaml.YAMLError as e:
            meta = {}
            errs.append(f"{d.name}: agents/openai.yaml invalid: {e}")
        iface = meta.get("interface") if isinstance(meta, dict) else None
        for k in ("display_name", "short_description", "default_prompt"):
            if not isinstance(iface, dict) or not isinstance(iface.get(k), str) or not iface[k].strip():
                errs.append(f"{d.name}: agents/openai.yaml needs interface.{k}")
        if isinstance(iface, dict) and isinstance(iface.get("default_prompt"), str) and f"${d.name}" not in iface["default_prompt"]:
            errs.append(f"{d.name}: agents/openai.yaml default_prompt should mention ${d.name}")

    for f in d.rglob("*"):
        if "__pycache__" in f.parts or f.suffix in {".pyc", ".pyo"}:
            errs.append(f"{d.name}: cache file {f.relative_to(d)}")
        elif f.is_file() and f.suffix in TEXT_SUFFIXES:
            body = f.read_text(errors="ignore")
            for skill, rel in sorted(set(XSKILL_RE.findall(body))):
                if "*" not in rel and "<" not in rel and not (d.parent / skill / rel.rstrip("/.")).exists():
                    errs.append(f"{d.name}: {f.relative_to(d)} points to {skill}/{rel} which does not exist")
            for rx, what in FORBIDDEN:
                m = rx.search(body)
                if m:
                    errs.append(f"{d.name}: {f.relative_to(d)} contains {what}: {m.group(0)!r}")
    return errs


def check_repo():
    errs, seen = [], {}
    for rel in ("plugin.json", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"):
        f = ROOT / rel
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            errs.append(f"{rel}: invalid JSON: {e}")
            continue
        if "plugins" in data:                       # marketplace entry
            data = data["plugins"][0] if data["plugins"] else {}
        seen[rel] = (data.get("name"), data.get("version"))
    if len(set(seen.values())) > 1:
        errs.append(f"plugin manifests disagree on name/version: {seen}")
    return errs


def main():
    dirs = [Path(a) for a in sys.argv[1:]] or sorted(p for p in (ROOT / "skills").iterdir() if p.is_dir())
    errs = []
    for d in dirs:
        e = check_skill(d.resolve())
        print(f"{'FAIL' if e else 'ok  '} {d.name}")
        errs += e
    if len(sys.argv) == 1:                          # repository-level checks only when linting everything
        errs += check_repo()
    for e in errs:
        print("  -", e)
    if not dirs:
        errs.append("no skills found")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
