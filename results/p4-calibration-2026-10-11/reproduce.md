# Reproduce P4-B component contract calibration

Freeze a clean detached source, original decompressed capture and fresh outputs.
No `--smoke` is used. Previous references are immutable and reused explicitly.

```sh
python3 -m venv /tmp/p4-cycle-env
/tmp/p4-cycle-env/bin/pip install -e .
git worktree add --detach /tmp/p4-cycle-source ffdbe29
gzip -dc configs/routing/qwen15_matched_c512_128steps.json.gz > /tmp/p4-cycle-routes.json
/tmp/p4-cycle-env/bin/python scripts/reproduce_p4_components.py --source /tmp/p4-cycle-source --pin ffdbe29 --routes /tmp/p4-cycle-routes.json --ramulator-root /path/to/ramulator2 --output /tmp/p4-cycle-shapes --workers 2
```

Build pinned Ramulator `c6c7a5d` using the existing [grounded](../../docs/grounded_validation.md) and [H2](../../docs/h2_tensor_execution.md) contracts. This executes four processes/eight full-projection-shape Native/Fluid points under the canonical H2 input/output contract. Actual capture counts1/22 and expert/token IDs are frozen in the launcher manifest. No padding or extra resource is introduced.

Recover the eight legacy reference directories and their sibling process logs/exits from `p4-b-native-and-controls.tar` in the [previous release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-fine-execution-2026-10-11).
For each per-run tar.gz, extract its complete directory; rename extracted `process.exit` and `process.log` to sibling `<directory>.exit/.log`. Recover `native-launcher.json` from `launch-metadata` as `<legacy-root>/launcher-manifest.json`. Preserve source/summary/transaction/command hashes. The earlier reproduction instructions can also regenerate the same16 reference points at `c95c2d7`.

```sh
/tmp/p4-cycle-env/bin/python scripts/qualify_p4_cycles.py --source /tmp/p4-cycle-source --legacy-root /path/to/legacy-native-root --shape-root /tmp/p4-cycle-shapes --output /tmp/p4-cycle-qualification
```

The predictor uses only the shared tensor contract and existing physical rate assumptions. Reference event times enter only the comparator after prediction completes. All source work, token counts, bytes, casts and port activity must match; all failed targets remain exported. The pure-Python frontend independently follows existing reference arbitration, MAC prorated demand, one Vector context and finite-flit credits. This is executor consistency, not silicon validation or a new scheduler/network.

The16 legacy plus8 new references produce24 independent Python executions/comparisons. Twelve Fluid traces compare all eight classes of events row by row. Independent observer replay validates port budgets, complete result-packet byte-range readiness, context exclusivity, link serialization and every byte/router lease. Absolute10% and relative5% targets remain per case.

`qualification.json` is the compact public export; event files include all tasks, requests, input joins, ports, flits, injections, vectors, and reserve/release transitions. Use current-main plotting tools and run regression tests:

```sh
/tmp/p4-cycle-env/bin/python scripts/plot_p4_calibration.py --results /path/to/public-results --old-results results/p4-fine-2026-10-11
/tmp/p4-cycle-env/bin/python -m unittest discover -s tests -v
```

The [new release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-component-calibration-2026-10-11) contains four SHA256-manifested raw outer tar assets: corrected8 Native/Fluid points, corrected24 Python execution records, the retired f4fb4b7 shape pilot, and the original mixed Python control archive. That last archive's legacyM512 records remain valid while its shape-validation records are retired. The older16 native reference records remain in their original release rather than being relabelled as new experiments. `artifact-manifest.json` records sizes/digests/retirement scope; each outer asset contains full per-entry `raw-manifest.json`.

The first pilot's start-row-only output binding missed packets straddling22-row MAC blocks. See `packet-retirement.json`; final latency agreement did not reveal the early packet reads. `ffdbe29` waits for every overlapping producer. Retired bytes are immutable and never counted in corrected qualification.

Private absolute paths in plain text are sanitized to `<run-root>`; original and packaged digests are retained separately. Event gzip bytes are immutable. Root launcher source/routing/selection metadata is in `shape-manifest.json`; each run's actual process exit is in its raw archive. No new full-MoE performance, checkpoint numeric, thermal or production-throughput qualification is claimed.
