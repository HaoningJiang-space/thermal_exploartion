# Reproduce P4-A on the original captured routing

Execution uses clean detached source pins, fresh output roots, and the published original Qwen capture.
No smoke/synthetic performance fallback. Small deterministic tensors are used only for numerical semantics.

```sh
python3 -m venv /tmp/hb-p4-env
/tmp/hb-p4-env/bin/pip install -e .
git worktree add --detach /tmp/hb-p4-main 2a1188b
git worktree add --detach /tmp/hb-p4-cohort 0f7eaa5
gzip -dc configs/routing/qwen15_matched_c512_128steps.json.gz > /tmp/hb-p4-routes.json
/tmp/hb-p4-env/bin/python scripts/reproduce_p4.py --source /tmp/hb-p4-main --pin 2a1188b --routes /tmp/hb-p4-routes.json --output /tmp/hb-p4-runs --workers 4
/tmp/hb-p4-env/bin/python scripts/reproduce_p4.py --source /tmp/hb-p4-cohort --pin 0f7eaa5 --routes /tmp/hb-p4-routes.json --output /tmp/hb-p4-cohort-runs --workers 2 --cohort-control
```

The initial matrix has56 processes:48 performance jobs (288 points) and8 numerical jobs (48 comparisons).
The independently frozen cohort control adds8 processes/48 performance points.
Primary s0/l0, holdouts s32/l7 and s127/l23; B8/B32, TP4/TP16, column/row, frozen B3 placement.
Host concurrency and wall time do not change simulated resources or count as accelerator performance.
The runner verifies the decompressed capture SHA, source cleanliness and actual case list.
Input probabilities come from the same original route records; numerical BF16 storage does not recapture or reroute tokens.

After all64 jobs complete, use current-main reporting tools. Export requires process exits, complete grids,
source/routing/layout/point/event hashes and independent replay of all resource/credit intervals.
It also exactly compares28 overlapping cases with the immutable old compact archive.

```sh
/tmp/hb-p4-env/bin/python scripts/export_p4.py --root /tmp/hb-p4-runs --cohort-root /tmp/hb-p4-cohort-runs --old-points results/expert-execution-2026-10-11/all-points.json --output /tmp/hb-p4-public --workers 4
/tmp/hb-p4-env/bin/python scripts/plot_p4.py --results /tmp/hb-p4-public
```

`--list-only` shows commands; it is not an experiment. Each output directory must be new.
All performance points retain full events, including oracles; source pins identify execution, reporting scripts are separate.
The original source pin's complete test suite has127 passes. The cohort pin's14 affected tests include real B32 credit regressions.

The [release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-communication-2026-10-11) contains four raw outer tar assets,
split by batch and TP. Each contains16 complete per-run tar.gz archives and a SHA256 manifest;
the B32/TP16 asset also includes launcher metadata. Process logs/exits, numerical summaries,
resident layouts, original full event gzip files and full kernel/semantic ledgers are retained.
Original event gzip bytes remain unchanged. Private absolute run paths in plain-text provenance are replaced by `<run-root>`;
the manifest records original and packaged digests separately. No routing or tensor content is altered.

Verify outer sizes/digests in `artifact-manifest.json`, then inner entry sizes/digests in each `raw-manifest.json`.
Event digests and point hashes are also in compact evidence; plain-text provenance may have a different sanitized digest.
Repeated execution need not produce byte-identical gzip headers; numerical tolerances and workload/resource conservation are checked independently.

This is P4-A fixed-layout communication analysis. The memory/MAC joint service is unchanged;
no independent native-MoE, full-checkpoint numerical, thermal/PPA or production-serving qualification is claimed.
