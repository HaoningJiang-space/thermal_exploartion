# Reproduce the complete-MoE causality audit

This reproduces frontend regressions and the FIFO correction, **not qualified architecture G3/G4**. Only original captured routing and full performance dimensions are allowed. The training/holdout architecture matrix currently refuses to launch until the actual M/K, finite RF and partial-state contract is closed.

Use a clean detached execution source and pinned Ramulator `c6c7a5de0cef35935d6fad7369e6271406798865`, built using the existing [native validation](../../docs/grounded_validation.md) and [H2](../../docs/h2_tensor_execution.md) instructions. The root must provide `libramulator.so`, Python bindings and source includes.

```sh
python3 -m venv /tmp/moe-env
/tmp/moe-env/bin/pip install -e .
git worktree add --detach /tmp/moe-source 0d5b89b95cdb28c7823514d38f20ea3168395512
gzip -dc configs/routing/qwen15_matched_c512_128steps.json.gz > /tmp/moe-routes.json
/tmp/moe-env/bin/python /tmp/moe-source/scripts/reproduce_moe_cycles.py --source /tmp/moe-source --pin 0d5b89b95cdb28c7823514d38f20ea3168395512 --routes /tmp/moe-routes.json --ramulator-root /path/to/ramulator2 --output /tmp/moe-experts --stage experts --workers 3
/tmp/moe-env/bin/python /tmp/moe-source/scripts/reproduce_moe_cycles.py --source /tmp/moe-source --pin 0d5b89b95cdb28c7823514d38f20ea3168395512 --routes /tmp/moe-routes.json --ramulator-root /path/to/ramulator2 --output /tmp/moe-full --stage fifo_regression --workers 2
```

The first stage executes Expert12/10 and Competition10/34 under s0/l0/B32/TP4/Column, retaining their actual1/22/22 token counts. Competition uses existing fine_prefetch, with MAC/expert order unchanged. The second executes full conditional MoE s0/l0/B32/TP4/Column and B8/TP16/Row, including actual Shared5632, scalar gate, bounded accumulation and physical tail padding/masks.

Each case runs the C++ native/frontend, C++ tier-fluid frontend, independent Python tier-fluid frontend and independent Python online-native frontend. The native-memory bridge dynamically sends the predictor's current requests, accepts current feedback and ticks its own pinned Ramulator instance. No recorded response table enters prediction. Online-native and C++ native share the device model; all four share the high-level semantic program and the unqualified byte-block MAC law. Exact trace matching is an execution implementation check.

Archive the two incomplete physical/dataflow policies distinctly. The component-style M/K comparison is a specified dataflow, not a universal SRAM lower bound. `physical-contract-audit.json` records missing RF capacity/ports/lifetimes and the retained output state, rather than inventing those resources. `qualification.json` exports `frontend_absolute_pass` and `architecture_g3_g4_qualified=false` separately.

For the pure FIFO pair, retain clean source `b2418754576b8a0fbd48dbf7be9a87b63d4945c2` and build its two drivers with the same Ramulator/toolchain. Run its module for only s0/l0/B32/TP4/Column/`--scope moe`, preserving the original source and all logs. Recover that exact archived control from `p4-moe-retired-fifo-control.tar` instead of recreating the full retired8-point matrix. Its program must have the same decompressed SHA256 as the corrected program; its FIFO execution is deliberately retired.

Use current-main independent analysis scripts without modifying either detached worktree:

```sh
/tmp/moe-env/bin/python scripts/audit_moe_fifo.py /tmp/control/program/program.json.gz /tmp/control/native/run-nodes.csv.gz --output /tmp/old-fifo.json
/tmp/moe-env/bin/python scripts/audit_moe_fifo_pair.py --retired /tmp/control --fixed /tmp/moe-full/s0-l0-b32-tp4-column-moe --output /tmp/fifo-pair.json
/tmp/moe-env/bin/python scripts/audit_moe_competition.py /tmp/moe-experts/s0-l0-b32-tp4-column-contending --output /tmp/competition.json
/tmp/moe-env/bin/python scripts/summarize_moe_causality.py --experts /tmp/moe-experts --full /tmp/moe-full --retired-control /tmp/control-root --output /tmp/execution-audit.json
```

`control-root` contains the control directory and its sibling `.exit/.log` files. When extracting raw per-case archives, move `process.exit/process.log` to these siblings; the completed-case summarizer requires them. Analyses take recorded events only after execution, never feed timings back into either predictor. Actual Expert34 RD-command issue clocks, rather than accepted→returned lifetimes, establish the reported overlap with Expert10 MAC windows.

The [release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-moe-causality-audit-2026-10-12) preserves all three retired Expert source cohorts, all8 retired full-MoE prototype exits (including the2 pre-Native failures), the corrected3 Expert and2 full-MoE cases, and the dedicated retired FIFO control. Five outer tar assets contain SHA256 manifests and full per-entry original/packaged digests. Gzip event bytes remain immutable; private paths in plaintext are sanitized. Same-named cases across source pins use distinct archive labels, preventing overwritten retirement evidence.

Use `artifact-manifest.json` and `raw-manifests/` to verify every asset and inner entry. Each archive includes program JSON/TSV, numeric/transport/physical checks, all six event classes for available executions, native transaction commands/state, driver output, process logs and exits. Failed prototypes retain only the evidence actually produced; a zero process exit alone does not certify architecture accuracy.

All five public assets (2,014,607,360B) were downloaded in full without authentication and their SHA256 matched the protected-scanned upload manifests and GitHub digests. See [public-verification.json](public-verification.json). Repeat with `python scripts/verify_moe_release.py --manifest results/p4-complete-moe-2026-10-12/artifact-manifest.json --output /tmp/moe-public-verification.json`.

146 full regression tests plus the new packaging preservation test passed. Numerical matrices are reduced semantic controls (same true routing/probabilities, fixed FP32 K order, unchanged tolerances); timing dimensions remain2048/1408/5632. No smoke benchmark or full checkpoint numerical qualification is claimed.
