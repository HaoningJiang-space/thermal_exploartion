#!/usr/bin/env python3
"""Check FIFO head discipline independently of credit totals or simulator match.

Input histories may pass every byte/slot-capacity check and still permit a
younger flit to bypass a blocked head. This audit examines actual arrival and
consumer start times, without importing either execution implementation.
"""
import argparse
import csv
import gzip
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thermal_exploration.moe_fifo_audit import check_fifo


def opened(path):
    return (gzip.open if str(path).endswith('.gz') else open)(path, 'rt')


def audit(program, history):
    with opened(program) as f:
        p = json.load(f)
    with opened(history) as f:
        times = {int(r['id']): {k: int(v) for k, v in r.items()}
                 for r in csv.DictReader(f)}
    return check_fifo(p, times)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('program', type=Path)
    parser.add_argument('nodes', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(args.program, args.nodes)
    body = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(body)
    print(body)
