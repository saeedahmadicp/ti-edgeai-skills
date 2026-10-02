"""Write build output into a fresh staging folder and move it into place only when the build succeeded, so a failed run never destroys
the previous good output. Stdlib only.

    staging = begin("artifacts")      # -> artifacts.staging-<pid>/ (empty)
    ... build into staging ...
    previous = commit(staging, "artifacts")   # an existing "artifacts" is renamed to artifacts.previous-<time>, never deleted
    abort(staging)                    # on failure: remove only the staging folder
"""
import os
import shutil
import time
from pathlib import Path


def begin(dest):
    dest = Path(dest)
    staging = dest.with_name(f"{dest.name}.staging-{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)          # stale staging folder of this very process id: ours by construction
    staging.mkdir(parents=True)
    return staging


def commit(staging, dest):
    """Move staging to dest. Returns the path the old dest was renamed to (or None)."""
    staging, dest = Path(staging), Path(dest)
    previous = None
    if dest.exists():
        previous = dest.with_name(f"{dest.name}.previous-{time.strftime('%Y%m%d-%H%M%S')}")
        n = 0
        while previous.exists():
            n += 1
            previous = dest.with_name(f"{dest.name}.previous-{time.strftime('%Y%m%d-%H%M%S')}-{n}")
        os.rename(dest, previous)
    os.rename(staging, dest)
    return previous


def abort(staging):
    shutil.rmtree(staging, ignore_errors=True)
