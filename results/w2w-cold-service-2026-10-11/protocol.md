# Cold memory-service causal gate

This gate answers the published cold `e62/b8/gate` MC-full observation. It
executes the entire original 8-expert FFN at hidden 4096 / intermediate 1536,
using the ranked selection from the authorized Qwen3 capture
`mmlu/abstract_algebra/98.json`, original layer 0, zero-based decode step 16.
The complete normalized corpus and its independent coverage audit authenticate
that selection. No matrix dimension, expert, block or task is reduced.

**Scope is one actual cold token.** This is not completion of a real request,
94-layer inference, prefill validation or numerical execution. The separate
`full-request-r2` registration remains the complete-phase captured-request
comparison; it must not inherit timing conclusions from this cold gate.

## Registration and interventions

Execution source is `565f148`, in the isolated hn072 worktree
`/Projects/haoning/w2w-full-system-memory-causality-20261011/cold-source-sol-r1`.
Registered inputs and raw outputs are in its sibling `cold-gate-sol-r1`.
Each application uses the accepted BookSim and Ramulator bridge binaries,
real native command scheduling, refresh, request/ACK transport, contiguous
operands, two fetch slots and two compute contexts. Cache is disabled.
The full graph, weight addresses, placement, mathematical work and NoC policy
are identical. All 151,031,808 native bytes must actually execute.

| Case | Intervention | Preserved / charged distinction |
|---|---|---|
| baseline | Original Up-local execution | Must equal the complete independently audited historical physical record |
| mc16 | 8 → 16 shared MC and grouped-descriptor slots per Gateway | Return staging also doubles to 64 KiB/Gateway; corresponding command/ACK credit capacities increase. This is not a state-only or equal-area change |
| native_minimum_gaps | Optimistic row/CAS/refresh command gaps | Real 128-controller Ramulator; nBL=1, 3.76 ns bus, nREFI=1037 and finite queues remain. No device feasibility or fully ideal DRAM claim |
| collection_minimum | Data propagation set to one 3.76 ns tick | Coordinates and command/ACK timing unchanged. Deliberately violates data-wire timing; diagnostic only |
| gateway_output_relaxed | 32 → 4096 B/ns payload output per Gateway | Increased output resource recorded. Native/HB, staging, MC, actual BookSim and destination writes remain |
| native_round_robin | Row-batched → round-robin descriptor selection | Same native window, slots, rates, timings, addresses and physical resources; scheduling foil |
| return_capacity_relaxed | 64 → 1024 reserved return atoms per native domain | Reservation bytes and metadata explicitly increase; all other rates and slots remain fixed |

The Gateway-output experiment does **not** idealize the NoC. The minimum-gap
experiment does **not** increase the native data-bus rate. A zero or negative
result is retained. No automatic application retry or performance selection is
allowed. Native experiments run concurrently in separate directories, on
disjoint two-core affinities; measured simulated time, not host wall speed,
is the outcome.

## Required readback

`tools/audit_cold_service_gate.py` independently reads saved inputs and outputs,
checks source, graph and physical identities, repeats finite-service and
request/ACK audits, and checks exact completed tasks, request/address multisets,
native per-domain atoms, per-Gateway bytes and arithmetic work. The baseline
must equal the entire original `02dab2a` Up-local physical record, allowing only
declared provenance differences. All cases retain raw-result SHA-256 identities.

Report full-FFN makespan and fixed-block Gate finish separately. Reconstruct
three matched tail blocks and identify each execution's actual latest Gate.
MC ownership phases are disjoint slot lifetimes whose total must equal
capacity × full-window wall time; they are not independently removable stalls.
The geometry-based lifetime reader is intentionally withheld for the
nonphysical collection-delay override rather than modifying its physical
identity to make the reader accept it.

Both global and busiest-endpoint payload bounds are reported. At fixed
addresses, the maximum of individual Gateway and domain work/rate bounds can
be stronger than the total-byte/global-rate bound. None includes command gaps,
refresh, compute dependencies or physical cost.

## Decision boundary

Prefer a service-rate investigation only if native-gap relief measurably
improves end-to-end completion while return-path and state-capacity changes
are weak. Prefer a return/interface investigation if its specific interventions
recover substantial completion time. A beneficial equal-resource scheduling
foil must enter the baseline before claiming new hardware is necessary.

These interventions can reject a mechanism hypothesis on the motivating cold
workload. They cannot establish a new architecture's novelty, equal-PPA
advantage or generality. Broader claims require completed captured-request
results and an explicit physically feasible organization/cost model.

```sh
python -m tools.run_cold_service_gate --root NEW_STUDY --prepare \
  --historical AUDITED_COLD_STUDY --corpus AUDITED_COMPLETE_CORPUS
python -m tools.run_cold_service_gate --root NEW_STUDY --case CASE \
  --booksim-binary ACCEPTED_BOOKSIM
python -m tools.audit_cold_service_gate --root NEW_STUDY --output NEW_READBACK.json
```

Use a clean frozen source, an unused output directory, and the registered
`PYTHONPATH` / `W2W_RAMULATOR_BRIDGE`. Keep raw captures, environments and
native builds outside Git.

This is a frozen W2W execution contract archived in thermal_exploration. See [reproduce.md](reproduce.md) for the pinned external backend; do not run it as a thermal_exploration simulator experiment.
