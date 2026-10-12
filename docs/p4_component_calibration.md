# P4-B component calibration follow-up

The `f5f25ca` experiment remains immutable: Graph timing qualification failed.
This follow-up fixes the component abstraction, not a hardware architecture.
The full MoE Graph executor, macro controls and original48 performance points
are not silently switched to or certified by the new component frontend.

## Frozen mechanism and qualification

Independent Python cycle interpretation of the same H2 tasks, data ownership,
finite return/weight/collective credits, 32B flits, two virtual networks, eight
flits per input port/VC, 4-tick link serialization, 8-tick flight, and existing
256B/128B SRAM ports. MAC operand/write demand is spread across its occupied
cycles, sharing the actual residual per-tick budgets with vector and network
work. One active Vector context per tile runs packet read/add/write through
completion; no additional context or port is invented.

Arbitration is the existing C++ reference policy, independently implemented.
It is not a newly selected scheduling optimization. Native/Fluid continue
sharing the C++ frontend; the Python implementation is a separate executor
but shares the tensor contract builder and physical assumptions. No silicon
or independent device calibration is claimed.
One Vector context is the selected reference's control assumption, not a
proven universal hardware requirement. The old Graph's pipelined phases are
a different execution contract; their mismatch alone does not prove that
legal, explicitly paid multiple contexts are impossible or unnecessary.

Memory uses the existing26.599TB/s guard and26-tick fixed return offset.
No measured per-request/operand/network arrival time enters the predictor,
and there is no empirical latency multiplier, fitting or parameter search.
The detailed reference uses the existing fast-tier internal timing surrogate;
this does not validate all memory tiers or full-MoE refresh/dependency phases.

Replay the16 archived M512/K1024-or2048/B1-or22 Native/Fluid comparisons.
Targets remain absolute10% and Row/Column latency-ratio error5%, per case.
For Fluid reference cases additionally compare every task, input arrival,
memory/HB transaction, vector window, injection, directed-link flit and port
trace, not only final latency. Original Graph results/failures stay public.

Before running new native cases, freeze8 shape-validation points:
real Qwen routed Gate/Up M1408/K2048, batch1/22 (captured cold/reused counts),
row/column and Native/Fluid. Use32B reduction packets and the largest legal
row microtile no greater than32 rows (22 for1408/16=88). No padding, extra
MACs, replicated weights, changed total SRAM, ports or memory domains.
These are full projection shapes under the standalone H2 canonical-input /
canonical-output / BF16-cast contract, not the fused Gate/Up/SiLU protocol,
full MoE or independent routing prompts.
They are shape-transfer validation, not an independent blind holdout.

Every result packet depends on all final MAC microtiles intersecting its
complete flat FP32 byte interval. A packet can straddle two22-row blocks;
matching only its starting row is invalid. The f4fb4b7 shape pilot used that
shortcut and is retained as a retired contract control, even where final
latency/byte counts still matched. Old M512 cases have aligned packets and
remain valid references. Corrected C++/Python frontends and an independent
byte-range checker must reject early packet consumption before qualification.

G2 independently replays per-cycle port budgets, MAC/Vector exclusivity,
readiness, FIFO/HB references, link serialization and all router-credit
reserve/release transitions. Negative controls reject altered physical ports,
premature input/weight consumption and extra private storage.

Even if all component targets pass, G4 for full MoE TP4/TP16 under the same
corrected interface remains unestablished. Do not replace the old27%/29% NoC
Oracle with component numbers or advance P4-C on that basis.
