#!/usr/bin/env python3
"""Check that compiled TIDL artifacts are loadable by the board's firmware.

The first 8 bytes of subgraph_*_tidl_net.bin carry a TIDL network-format version stamp. A model that the C7x
accepts has the same stamp as models already known to run on the board (e.g. TI zoo models in /opt/model_zoo).
When the stamp differs, the board fails at session creation with
    TIVX_CMD_NODE_CREATE failed ... Create state function failed
(verified: tools tag 11_00_08_00 -> stamp 30 06 25 20 rejected by an SDK 11.0 board; tag 11_00_06_00 -> 29 04 25 20 ok).

Usage:
    check_artifacts_version.py artifacts/subgraph_0_tidl_net.bin --board root@<board-ip>
    check_artifacts_version.py artifacts/subgraph_0_tidl_net.bin --ref /some/zoo/artifacts/subgraph_0_tidl_net.bin
"""
import argparse
import subprocess
import sys
from pathlib import Path


def stamp(data):
    return data[:4].hex(" ")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("net_bin", type=Path)
    p.add_argument("--ref", type=Path, help="local copy of a net.bin known to run on the board")
    p.add_argument("--board", help="user@host: read the stamp from every zoo model on the board and compare")
    a = p.parse_args()
    mine = stamp(a.net_bin.read_bytes())
    print(f"{a.net_bin}: stamp {mine}")
    refs = {}
    if a.ref:
        refs[str(a.ref)] = stamp(a.ref.read_bytes())
    if a.board:
        cmd = ["ssh", a.board, "for f in /opt/model_zoo/*/artifacts/subgraph_0_tidl_net.bin; do "
               "echo $f $(head -c 4 $f | od -An -tx1); done"]
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        for line in out.splitlines():
            path, _, hexes = line.partition(" ")
            if hexes.strip():
                refs[path] = hexes.strip()
    if not refs:
        sys.exit("give --ref or --board to compare against")
    stamps = {v for v in refs.values()}
    for path, st in sorted(refs.items()):
        print(f"  ref {st}  {path}")
    if mine in stamps:
        print("OK: matches a model that runs on this board")
    else:
        print("MISMATCH: rebuild with the tidl-tools tag that matches the board SDK (see references/compile-tidl.md)")
        sys.exit(1)


if __name__ == "__main__":
    main()
