# Reproduce the frozen real-route gate

Use the execution pins in `experiment-contract.json` and `run-manifest.json`.
The reporting/export scripts are from current main; execution uses clean detached worktrees.
Every output root must be new. This matrix runs actual captured Qwen1.5 routing and all128 P1 decode steps;
there is no smoke substitution or synthetic route fallback.

The original checkpoint pin is `1a758c50ecb6350748b9ce0a99d2352fd9fc11c9`.
Primary capture:32 holdout prompts,128 cached-decode steps,24 layers,C512,FP32.
Four separate training prompts supply256 prefill positions for the frozen placement prior.
Paired prompt controls:topic_short/code_math,FP32/BF16,same teacher-forced input IDs,B4,C128,8 steps.
Public capture files are sufficient; downloading model weights is unnecessary to replay architecture execution.
To recapture them, use `scripts/capture_qwen15_routes.py` and `scripts/check_qwen15_routing_precision.py`,
with their pinned model/dependency versions and capture contracts. CPU time is not accelerator throughput.

```sh
python3 -m venv /tmp/hb-expert-env
/tmp/hb-expert-env/bin/pip install -e .
gzip -dc configs/routing/qwen15_matched_c512_128steps.json.gz > /tmp/hb-primary-routes.json
mkdir /tmp/hb-paired-routes
for file in configs/routing/qwen15_precision_controls/*.json.gz; do
  gzip -dc "$file" > "/tmp/hb-paired-routes/$(basename "$file" .gz)"
done
for pin in 83b1655 b468306 3dad8cd 5380b5d 15ad39e 4648f3c 7890865; do
  git worktree add --detach "/tmp/hb-source-$pin" "$pin"
done
```

Capture SHA in the archived run provenance refers to the decompressed JSON used in that run;
the public compressed files have separate distribution hashes. Passing compressed JSON is supported,
but its input-file SHA will differ while route content stays identical.

`reproduce_expert_matrix.py` creates unique run directories, captures `.log` and `.exit`,
checks the source pin and clean tree, and runs a fixed matrix. Set `--workers` only for host parallelism;
it changes neither the simulated machine nor the routing/placement decisions.

```sh
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix rows --source /tmp/hb-source-b468306 --routes /tmp/hb-primary-routes.json --output /tmp/hb-replay-rows
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix eager --source /tmp/hb-source-3dad8cd --routes /tmp/hb-primary-routes.json --output /tmp/hb-replay-eager --workers 4
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix fused --source /tmp/hb-source-15ad39e --routes /tmp/hb-primary-routes.json --output /tmp/hb-replay-fused --workers 4
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix prompt_eager --source /tmp/hb-source-5380b5d --routes /tmp/hb-primary-routes.json --precision-root /tmp/hb-paired-routes --output /tmp/hb-replay-prompt-eager --workers 4
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix prompt_fused --source /tmp/hb-source-15ad39e --routes /tmp/hb-primary-routes.json --precision-root /tmp/hb-paired-routes --output /tmp/hb-replay-prompt-fused --workers 4
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix probes --source /tmp/hb-source-4648f3c --routes /tmp/hb-primary-routes.json --output /tmp/hb-replay-probes --workers 4
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix strong_probes --source /tmp/hb-source-7890865 --routes /tmp/hb-primary-routes.json --output /tmp/hb-replay-strong-probes --workers 4
```

P0 additionally needs Linux/g++, the pinned Ramulator `c6c7a5de0cef35935d6fad7369e6271406798865`,
and the shared native tensor frontend. Build/install instructions are in the existing G4/H2 qualification docs.
The P0 matrix contains20 processes/36 native-or-fluid tensor points and preserves the exact five shapes,
partitions and128/36 versus152/18 profiles. The fluid rate is the existing unfitted26.599TB/s service guard.

```sh
/tmp/hb-expert-env/bin/python scripts/reproduce_expert_matrix.py --matrix p0 --source /tmp/hb-source-83b1655 --routes /tmp/hb-primary-routes.json --ramulator-root /path/to/pinned-ramulator --output /tmp/hb-replay-p0 --workers 2
```

After all non-P0 runs finish, pass their individual run directories to the audited exporter.
The two152/18 cohort failures are expected P1 negative controls; an unexpected failure stops export.
The probe `none` replay must exactly match the corresponding original fused baseline.
Raw legacy provenance lists CLI-default selected_steps/layers even for supplements; the public manifest
adds actual executed_steps/layers from audited case files. Use those and the explicit CLI params.
The exporter checks complete grids, clean source, process exit, point/summary agreement,
route/prior/event digests, MAC/DRAM conservation and critical-chain closure.

```sh
PYTHONPATH=. /tmp/hb-expert-env/bin/python - <<'PYTHON'
from pathlib import Path
import subprocess,sys
roots=['rows','eager','fused','prompt-eager','prompt-fused','probes','strong-probes']
sources=[str(p) for name in roots for p in sorted(Path('/tmp/hb-replay-'+name).iterdir()) if p.is_dir()]
subprocess.run([sys.executable,'scripts/export_expert_gate.py','--sources',*sources,'--output','/tmp/hb-compact-replay'],check=True)
PYTHON
```

P0 native records and all old retired controls remain in separate raw release assets.
Each raw outer tar contains per-run tar.gz files and a SHA256 manifest. Original gzip records are retained
byte-for-byte; declared truncated retired records are preserved and never treated as complete successful runs.
Private run-root prefixes in text provenance/logs become `<run-root>`; original hashes are also recorded.
Full P1 phase events are retained. P2 keeps full DAG events for step0/layer0 and detailed kernel/critical records
for every point; P3 keeps full DAGs for all interventions. We do not claim full packet event retention for every P2 case.

The public all-points file preserves packet-only activity separately and normalizes DRAM/HB and operand reads
from the complete joint-kernel ledger, globally and per tile. That accounting step is not a command-level fidelity upgrade.
Regenerate summaries/figures with `summarize_expert_gate.py` and `plot_expert_gate.py` using this results directory.
