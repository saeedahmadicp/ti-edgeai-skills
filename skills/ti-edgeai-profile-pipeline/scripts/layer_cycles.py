#!/usr/bin/env python3
"""Rank TIDL layers by C7x cycles from a debug_level=1 run (target only; host emulation prints no cycles).

    python3 bench_tidl.py <model_dir> --debug-level 1 --runs 20 > dbg.log 2>&1      # on the board
    python3 layer_cycles.py dbg.log --layer-info <model_dir>/artifacts/*.layer_info.txt --top 15

TIDL prints one `Layer, Layer Cycles, ...` table per invocation. Rows are averaged across invocations (the first
invocation after session creation is often slower, so --skip-first drops it). "Layer Cycles" is the number to use;
the other columns are TI-internal. Cycles -> ms: divide by the C7x clock (1 GHz measured on TDA4VM: ms = cycles / 1e6; read the clock of your SoC with k3conf).
layer_info.txt (written next to the compiled net.bin) maps layerId -> original node name.
"""
import argparse
import re
from collections import defaultdict

ROW = re.compile(r"^\s*(\d+),\s*(\d+),")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("log")
    p.add_argument("--layer-info")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--skip-first", action="store_true")
    p.add_argument("--clock-mhz", type=float, default=1000.0)
    a = p.parse_args()

    tables, cur = [], None
    for line in open(a.log, errors="ignore"):
        if line.lstrip().startswith("Layer,") and "Layer Cycles" in line:
            cur = {}
            tables.append(cur)
        elif cur is not None:
            m = ROW.match(line)
            if m:
                cur[int(m.group(1))] = int(m.group(2))
            elif line.strip() and not line.lstrip()[0].isdigit():
                cur = None
    if a.skip_first and len(tables) > 1:
        tables = tables[1:]
    if not tables:
        raise SystemExit("no 'Layer, Layer Cycles' tables found; run on the board with debug_level=1")

    names = {}
    if a.layer_info:
        for line in open(a.layer_info):
            parts = line.split(None, 2)
            if len(parts) == 3 and parts[0].isdigit():
                names[int(parts[0])] = parts[2].strip()

    acc = defaultdict(list)
    for t in tables:
        for k, v in t.items():
            acc[k].append(v)
    avg = {k: sum(v) / len(v) for k, v in acc.items()}
    total = sum(avg.values())
    print(f"{len(tables)} invocation(s), {len(avg)} layers; sum of layer cycles = {total:,.0f} "
          f"= {total / (a.clock_mhz * 1000):.2f} ms at {a.clock_mhz:.0f} MHz")
    print(f"{'layer':>6} {'cycles':>10} {'ms':>7} {'%':>6}  name")
    for k, v in sorted(avg.items(), key=lambda kv: -kv[1])[: a.top]:
        print(f"{k:>6} {v:>10,.0f} {v / (a.clock_mhz * 1000):>7.3f} {100 * v / total:>5.1f}%  {names.get(k, '')}")


if __name__ == "__main__":
    main()
