"""Compact G2 evidence; preserve full phase/flow/periodic raw files outside Git."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser();p.add_argument("--source",required=True,type=Path);p.add_argument("--destination",required=True,type=Path)
a=p.parse_args()
if a.destination.exists():raise SystemExit("Destination exists; preserve earlier evidence")
a.destination.mkdir(parents=True)
names=["summary.json","periodic_bounds.json","periodic_bounds.csv","results.csv","provenance.json",
       "thermal_validation.json","periodic_validation.json","g2_config.json","base_config.json","report.md"]
for name in names:shutil.copyfile(a.source/name,a.destination/name)
for src in a.source.glob("*.png"):shutil.copyfile(src,a.destination/src.name)
raw=json.loads((a.source/"results.json").read_text());phases=[];moves=[];audits=[]
for r in raw:
    keys={k:r[k] for k in ["scenario","case","thermal_regime","placement","fabric","thermal_mode"]}
    n=len(r["average_power_w"] )//2
    for i,phase in enumerate(r["phases"]):
        t=phase["spatial_steady_temperature_c"]
        row=dict(keys,phase_index=i,**{k:v for k,v in phase.items() if not isinstance(v,(list,dict))},
                 steady_logic_peak_c=max(t[:n]),steady_dram_peak_c=max(t[n:]))
        row.update({f"resident_fraction_bank_{j:02}":v for j,v in enumerate(phase["bank_fractions"])})
        phases.append(row)
    for m in r["migrations"]:
        moves.append(dict(keys,**{k:v for k,v in m.items() if not isinstance(v,(list,dict))}))
    if "periodic_audit" in r:
        pa=r["periodic_audit"]
        audits.append(dict(keys,pacing_factor=pa["factor"],paced_cycle_time_s=r["paced_cycle_time_s"],
                           unpaced_logic_peak_upper_c=pa["unpaced"]["logic_peak_upper_c"],
                           unpaced_dram_peak_upper_c=pa["unpaced"]["dram_peak_upper_c"],
                           paced_logic_peak_upper_c=pa["paced"]["logic_peak_upper_c"],
                           paced_dram_peak_upper_c=pa["paced"]["dram_peak_upper_c"],
                           periodic_closure_error_k=pa["paced"]["periodic_closure_error_k"],
                           mean_energy_balance_error_k=pa["paced"]["mean_energy_balance_error_k"],
                           maximum_interpolation_bound_gap_c=max(s["maximum_interpolation_bound_gap_c"] for s in pa["paced"]["segment_audits"])))
for name,rows in [("phase_metrics.csv",phases),("migration_metrics.csv",moves),("periodic_audits.csv",audits)]:
    with (a.destination/name).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
manifest={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(a.source.iterdir()) if f.is_file()}
(a.destination/"raw_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
