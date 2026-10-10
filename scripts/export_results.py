"""Export compact, reviewable evidence; keep full raw records outside Git."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser()
p.add_argument("--pilot",type=Path,required=True)
p.add_argument("--sensitivity",type=Path,required=True)
p.add_argument("--destination",type=Path,required=True)
a=p.parse_args()
if a.destination.exists():
    raise SystemExit("Destination already exists")
a.destination.mkdir(parents=True)
manifest={}
for label,source in [("pilot",a.pilot),("sensitivity",a.sensitivity)]:
    dst=a.destination/label;dst.mkdir()
    for name in ["summary.json","results.csv","report.md","provenance.json","thermal_validation.json","config.json"]:
        shutil.copyfile(source/name,dst/name)
        if name.endswith(".csv"):
            # Normalize presentation-only CRLF; raw hash below preserves exact originals.
            (dst/name).write_bytes((dst/name).read_bytes().replace(b"\r\n",b"\n"))
    for src in source.glob("*.png"):
        shutil.copyfile(src,dst/src.name)
    # Hash every raw file so untracked archives can be independently identified.
    manifest[label]={f.name:hashlib.sha256(f.read_bytes()).hexdigest()
                     for f in sorted(source.iterdir()) if f.is_file()}
    rows=json.loads((source/"results.json").read_text())
    manifest[label]["optimized_design_points"]=len(rows)
    manifest[label]["lp_solves"]=len(rows)*len(json.loads((source/"config.json").read_text())["tilings"])
(a.destination/"raw_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
