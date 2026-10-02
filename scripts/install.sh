#!/bin/bash
# Symlink every skill in this repository into an agent's skills folder so it discovers them without a plugin system.
#
#   scripts/install.sh [--agent claude|codex] [--scope user|repo] [--target DIR] [--dry-run] [--force]
#   scripts/install.sh DIR                       # legacy form: same as --target DIR
#
#   agent/scope           folder
#   claude  user          ~/.claude/skills            (default)
#   claude  repo          <git root or cwd>/.claude/skills
#   codex   user          ~/.agents/skills
#   codex   repo          <git root or cwd>/.agents/skills
#
# Safety: nothing is deleted. An existing real folder, or a symlink that points somewhere other than this repository, is skipped
# (use --force to repoint a foreign symlink; a real folder is never replaced). --dry-run prints what would happen.
# Codex discovery and invocation (`$ti-edgeai-dev`) follow OpenAI's documentation; they have not been tested here.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
agent=claude scope=user target="" dry=0 force=0
while [ $# -gt 0 ]; do
  case "$1" in
    --agent) agent=${2:?}; shift 2;;
    --scope) scope=${2:?}; shift 2;;
    --target) target=${2:?}; shift 2;;
    --dry-run) dry=1; shift;;
    --force) force=1; shift;;
    -h|--help) sed -n '2,17p' "$0"; exit 0;;
    -*) echo "unknown option $1" >&2; exit 2;;
    *) target=$1; shift;;
  esac
done
case "$agent" in claude|codex) ;; *) echo "--agent must be claude or codex" >&2; exit 2;; esac
case "$scope" in user|repo) ;; *) echo "--scope must be user or repo" >&2; exit 2;; esac
if [ -z "$target" ]; then
  sub=$([ "$agent" = codex ] && echo .agents/skills || echo .claude/skills)
  if [ "$scope" = user ]; then base=$HOME; else base=$(git rev-parse --show-toplevel 2>/dev/null || pwd); fi
  target=$base/$sub
fi
[ "$dry" = 1 ] || mkdir -p "$target"
rc=0
for d in "$repo"/skills/*/; do
  name=$(basename "$d")
  dest=$target/$name
  src=${d%/}
  if [ -L "$dest" ]; then
    cur=$(readlink "$dest")
    if [ "$cur" = "$src" ]; then echo "ok      $name (already linked)"; continue; fi
    if [ "$force" != 1 ]; then echo "skip    $name: $dest is a symlink to $cur, not to this repository (use --force to repoint)" >&2; rc=1; continue; fi
  elif [ -e "$dest" ]; then
    echo "skip    $name: $dest exists and is not a symlink" >&2; rc=1; continue
  fi
  if [ "$dry" = 1 ]; then echo "would link $name -> $src"; else ln -sfn "$src" "$dest"; echo "linked  $name -> $src"; fi
done
echo "target: $target"
exit $rc
