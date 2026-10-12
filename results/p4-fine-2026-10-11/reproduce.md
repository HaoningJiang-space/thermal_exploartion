# Reproduce the frozen P4-B experiment

Performance uses the original Qwen1.5 capture, real expert dimensions and finite resources. There is no smoke performance fallback. Small deterministic tensors validate only numerical semantics.

```sh
python3 -m venv /tmp/p4-b-env
/tmp/p4-b-env/bin/pip install -e .
git worktree add --detach /tmp/p4-b-main 3e1557a
git worktree add --detach /tmp/p4-b-native c95c2d7
gzip -dc configs/routing/qwen15_matched_c512_128steps.json.gz > /tmp/p4-b-routes.json
/tmp/p4-b-env/bin/python scripts/reproduce_p4_fine.py --source /tmp/p4-b-main --pin 3e1557a --routes /tmp/p4-b-routes.json --output /tmp/p4-b-runs --workers 2
/tmp/p4-b-env/bin/python scripts/reproduce_p4_fine.py --source /tmp/p4-b-native --pin c95c2d7 --routes /tmp/p4-b-routes.json --output /tmp/p4-b-native-runs --workers 2 --native-components --ramulator-root /path/to/ramulator2
```

Build Ramulator and native drivers using [the H2 contract](../../docs/h2_tensor_execution.md) and [grounded build instructions](../../docs/grounded_validation.md). Ramulator is pinned to `c6c7a5d`; clock/state qualification is unchanged. The native source pin differs only by a launcher import-path fix. The failed first launcher exited before any experimental point and is retained separately.

Main execution: 24 processes, 48 performance points and 48 FP32/BF16 small-tensor comparisons. B8/B32, TP4/TP16, row/column, macro/fine_fixed/fine_prefetch, original s0/l0. All experts and Shared are present. B8 is a subset of B32; these are not independent prompts or new holdouts.

Native execution: 8 processes, 16 tensor points, paired Native/Fluid. Actual captured token counts are 1 and 22. M=512, K=1024/2048 are legal submatrices within the real expert dimensions, using the existing detailed row/column tensor contract. They are qualification probes, not full-MoE performance or TP4/TP16 validation.

Use current-main reporting scripts outside clean execution worktrees:

```sh
/tmp/p4-b-env/bin/python scripts/audit_p4_fine.py --root /tmp/p4-b-runs --old-points results/p4-communication-2026-10-11/all-points.json --output /tmp/p4-b-public --workers 2
/tmp/p4-b-env/bin/python scripts/qualify_p4_fine.py --root /tmp/p4-b-native-runs --source /tmp/p4-b-native --output /tmp/p4-b-qualification
/tmp/p4-b-env/bin/python scripts/trace_p4_components.py --native /tmp/p4-b-native-runs --qualification /tmp/p4-b-qualification --output /tmp/p4-b-phases
```

The component builder reconstructs the same detailed tasks, input/output ownership, routing-independent tensor work, casts, SRAM bytes and byte-hops. It retains packet/flit and eager/spread port-service differences. Predeclared absolute 10% and relative 5% targets are checked per case; failures are exported, never averaged away or fitted out. Native/Fluid share a frontend, so their small error alone cannot qualify the Graph executor.

Copy the audited compact JSON files into a fresh results directory, along with `qualification.json` as `component-qualification.json` and `phases.json` as `component-phases.json`, then run:

```sh
/tmp/p4-b-env/bin/python scripts/plot_p4_fine.py --results /path/to/results
/tmp/p4-b-env/bin/python -m unittest discover -s tests -v
```

All output roots must be new. Host concurrency is not simulated hardware parallelism. `fine_fixed` changes resource reservation only; `fine_prefetch` separately relaxes current-route memory admission while preserving MAC/expert order and all shared capacities. Reference pipeline ledger timing is not actual fine-execution timing; actual service windows are the retained event records.

The [release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-fine-execution-2026-10-11) retains full event gzip files, detailed native transactions/commands/ports/flits, matched Graph component events, phase/task comparisons, layouts, numerical records, source/routing digests, process logs/exits and the pre-execution launcher failure. Six outer tar assets each contain per-run archives and a SHA256 manifest. Plain-text private absolute paths are replaced by `<run-root>`; manifests retain original and packaged digests separately. Event gzip bytes are unchanged.

Verify release size/SHA256 with `artifact-manifest.json`, then all inner entries with each `raw-manifest.json`. Source/layout/point/event digests and independent replay results are in the compact audit. Gzip headers may differ on reproduction; workload conservation and numerical tolerances are checked independently.

This experiment does not certify full-MoE absolute/relative fidelity, checkpoint BF16 numerical inference, thermal/PPA costs or production serving throughput. Failed component qualification blocks a Hardware Go based on these latency predictions.
