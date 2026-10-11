# Reproduce the crossover gate

Use an immutable checkout at `2bb172c` for primary execution and generated
command reference; `6bf1571` for supplemental oracles/default thermal;
`61922c8` for independent audits. Later render-only scripts improve figure
labels and preserve the same raw numerical data. Install the pinned upstreams
using the repository's existing G4/H2 instructions, not an arbitrary Ramulator.

Ramulator pin: `c6c7a5de0cef35935d6fad7369e6271406798865`.
HiTS pin: `c7f94d533cb663c2f098880e5ab333da9d83ff17`.
Python3.10 with numpy/scipy/matplotlib/yaml was used for remote execution.
Original route capture used torch2.6 CPU/transformers4.51.3, original checkpoint
revision `1a758c50ecb6350748b9ce0a99d2352fd9fc11c9`. Its CPU time is not an
accelerator performance observation. Copy the route asset from current main
(or commit7f3aeb4) before entering the earlier isolated source checkout; the
asset was published after the execution source was frozen. Decompress it first.

```sh
gzip -dc configs/routing/qwen15_matched_c512_128steps.json.gz > /tmp/qwen15-routes.json
PYTHONPATH=. python -m thermal_exploration.run_crossover --output /tmp/new-llama --cases llama_b1_c2k llama_b1_c32k llama_b4_c8k llama_b8_c2k llama_b16_c2k --uniform-control --service 26.599
PYTHONPATH=. python -m thermal_exploration.run_crossover --output /tmp/new-qwen --cases qwen_b1_c2k qwen_b2_c8k_context_control qwen_b8_c2k qwen_b16_c512 qwen_b32_c512 --routes /tmp/qwen15-routes.json --service 26.599
PYTHONPATH=. python scripts/remeasure_clocked_service.py --ramulator-root /path/to/pinned-ramulator --output /tmp/new-service
PYTHONPATH=. python -m thermal_exploration.run_h2 --ramulator-root /path/to/pinned-ramulator --output /tmp/new-qkv-b4 --shape 6144 4096 4 --cases row_fifo_k row_fifo_m column_fifo64 column_fifo_barrier
```

The archived primary eight directories merely split the same cases across
CPU processes. Every successful point still executed128 steps, with unique
step-major route records. Never rerun into an existing experimental directory.
A source-clean commit and file digests accompany the outputs. Scripts can also
be called with `python -m scripts.<module>` so the project root is importable.

Supplemental source at6bf1571:

```sh
PYTHONPATH=. python scripts/run_crossover_supplement.py --baselines /tmp/new-llama /tmp/new-qwen --routes /tmp/qwen15-routes.json --output /tmp/new-probes
PYTHONPATH=.:/path/to/pinned-HiTS python -m thermal_exploration.run_crossover_h5 --inputs /tmp/new-llama /tmp/new-qwen --output /tmp/new-thermal --backend hits
```

All event energy closes before thermal integration; oracles are excluded from
paid thermal evaluation. The route JSON has model-matched FP32 evidence and
explicit Context-transfer caveats. Do not rename Qwen2 routing as Qwen1.5.

`all-points.json` contains compact aggregate/step-latency statistics for every
point. Full per-step records, dependency events, request/command/NoC/port CSVs,
configuration and raw SHA256 manifests are in the release assets. Retired
ratio2 data and pooled-area/unbounded-FIFO attempts are separate controls,
not missing positive points or replacements for the original published data.
NoC and resource-probe speedups overlap. Plot macro labels and native task
occupancy as observations, not additive causal loss percentages.

113 regression tests passed on the final execution changes. The independent
FIFO, generated-clock, byte/FLOP and thermal checks are in this directory.
The two missed cross-fidelity targets are deliberately retained; this does
not qualify all large-Batch absolute performance predictions.
