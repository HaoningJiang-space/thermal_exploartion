"""Compare v2 replay with immutable public CSV evidence (no raw archive needed)."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--baseline", type=Path, default=Path("results/2026-10-09"))
p.add_argument("--baseline-g2", type=Path, default=Path("results/g2-2026-10-09"))
p.add_argument("--replay", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
if a.output.exists():
    raise SystemExit("Choose a new verification output")
checks = {}; numerical = []; old_labels = []; new_labels = []; hashes = {}
for name in ("pilot", "sensitivity", "g2"):
    baseline = a.baseline_g2 if name == "g2" else a.baseline/name
    replay = a.replay/name
    keys = ["scenario", "case", "thermal_regime", "placement", "fabric", "thermal_mode"] if name == "g2" else ["scenario", "workload", "placement", "fabric", "thermal_mode"]
    metric = "cycle_time_s" if name == "g2" else "tflops"
    old = list(csv.DictReader((baseline/"results.csv").open()))
    new = list(csv.DictReader((replay/"results.csv").open()))
    table = {tuple(r[k] for k in keys): r for r in new}
    differences = [abs(float(table[tuple(r[k] for k in keys)][metric]) / float(r[metric]) - 1) for r in old]
    maximum = max(differences)
    if maximum > 1e-10:
        raise RuntimeError(f"{name} legacy metric changed: {maximum}")
    checks[name] = dict(common_design_points=len(old), replay_design_points=len(new), metric=metric,
                        max_relative_legacy_metric_difference=maximum)
    old_summary = json.loads((baseline/"summary.json").read_text())
    new_summary = json.loads((replay/"summary.json").read_text())
    old_labels.extend(r for r in old_summary if r.get("screening_class") == "B_candidate")
    new_labels.extend(new_summary)
    numerical.extend(json.loads((replay/"thermal_validation.json").read_text()))
    for root in (baseline, replay):
        for filename in ("results.csv", "summary.json", "provenance.json"):
            hashes[str(root/filename)] = hashlib.sha256((root/filename).read_bytes()).hexdigest()
old = json.loads((a.baseline_g2/"periodic_bounds.json").read_text())
new = json.loads((a.replay/"g2/periodic_bounds.json").read_text())
def key(r): return tuple(r[k] for k in ("scenario", "case", "placement", "candidate"))
table = {key(r): r for r in new}
maximum = max(abs(r["net_periodic_speedup_upper_bound"] - table[key(r)]["net_periodic_speedup_upper_bound"]) for r in old)
if maximum > 1e-10:
    raise RuntimeError("G2 periodic stopping bound changed")
checks["g2"]["max_absolute_periodic_bound_difference"] = maximum
result = dict(status="PASS", comparisons=checks,
              old_B_candidate_counts_by_placement=dict(Counter(r["placement"] for r in old_labels)),
              replay_screening_counts=dict(Counter(r["screening_class"] for r in new_labels)),
              architecture_gate_pass_count=sum(r["architecture_gate_pass"] for r in new_labels),
              hits_unit_source_solves=sum(2*r["nodes"]//3 for r in numerical),
              hits_max_original_relative_residual=max(r["hits_max_residual"] for r in numerical),
              hits_vs_direct_max_response_difference_k_per_w=max(r["hits_vs_direct_max_abs_k_per_w"] for r in numerical),
              input_sha256=hashes)
a.output.write_text(json.dumps(result, indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k != "input_sha256"}))
