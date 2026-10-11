# Reproduce the relocated W2W evidence

This delivery belongs to **thermal_exploration**. The original seven native
runs used the **W2W V3 external backend**, not thermal_exploration's
Stratum-inspired accelerator. Moving the delivery changes its repository
location only; original input, execution, reader and raw-result identities
remain unchanged. Do not combine these timings with this project's crossover
or expert-execution results as though they used the same hardware contract.

## Checks and figures in this workspace

From the thermal_exploration repository:

```sh
.venv/bin/python scripts/verify_w2w_cold_service.py
.venv/bin/python scripts/plot_w2w_cold_service.py \
  --receipt results/w2w-cold-service-2026-10-11/evidence/native-study/independent-readback.json \
  --output outputs/w2w-cold-service-figures
```

The first command verifies the relocation manifest, original 24-file evidence
manifest, complete saved receipts, native-byte accounting and source identities.
It does not rerun native simulation. The second regenerates the figures from
the independently audited receipt.

## Frozen execution code

`reproduction/source/` preserves the exact driver, independent audit, plotting
code and directed checks. The driver and audit depend on the original W2W
architecture/kernel/native adapters; they are source records, not modules of
the thermal_exploration simulator.

`reproduction/w2w-cold-service.bundle` retains the four delivery commits through
`2a1d6ee5a4b9bf5287246e64b7ba013da6e080d6`. It requires the original W2W
commit `ed35357deb08bc1fc1457857a36c27d619358b7d`. In an existing W2W Git
repository containing that prerequisite, fetch the bundle and create a new
detached worktree; do not reset another developer's checkout:

```sh
git -C W2W_REPOSITORY bundle verify ABSOLUTE_PATH_TO_BUNDLE
git -C W2W_REPOSITORY fetch ABSOLUTE_PATH_TO_BUNDLE HEAD
git -C W2W_REPOSITORY worktree add --detach NEW_EXECUTION_WORKTREE \
  565f148
git -C W2W_REPOSITORY worktree add --detach NEW_READER_WORKTREE \
  0e5a8d4
```

The [frozen protocol](protocol.md) records actual native preparation/execution
and readback commands. Real runs need the original independently audited
captured corpus, historical cold baseline, accepted native tools and pinned
Ramulator Python environment. Those raw data/builds remain on hn072 at their
original recorded locations. They were not replaced with smoke inputs or
relabelled as a newly executed thermal_exploration trace.

`evidence/native-study/complete-request-status-snapshot.json` is a historical
snapshot of a separate ongoing full-request study, not a completed result.

The mistaken W2W main-branch delivery is reverted without rewriting history;
its frozen commits and raw execution directories remain available for audit.
