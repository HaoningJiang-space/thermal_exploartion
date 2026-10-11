# Compute–Memory–Communication crossover contract

This gate studies a **Stratum-inspired assumed accelerator**, not reconstructed
Stratum hardware. It freezes 121 mm², 32 GiB DRAM / 256 banks / eight capacity
Tiers, 16 Logic tiles, 32 TB/s HB, 4×4 Mesh with 32 GB/s directed links, and
BF16 model storage. All computation remains on Logic. No PIM, power delivery,
new Peripheral DSE, or RTL is introduced.

## Evidence and scope

The service reference is a generated-configuration-qualified Ramulator
surrogate. Python CK is 0.5 ns; HBM3's native half-CK tick is 0.25 ns. Both
resolved and serialized timing belong in the experiment record. See the
[withdrawn clock diagnosis](clock-domain-erratum.md); ratio2 data are retired
slow-timing controls, not replacements for published results.

Full-model execution uses bounded packet/microtile summaries, regional Tier
capacity, complete Layer/Token dependencies and independent byte/FLOP ledgers.
It abstracts per-command arbitration and physical address ordering. Native
QKV and Qwen expert checks retain these mechanisms. Agreement for a small
matrix is not qualification for every model, Batch or resource profile.

The six earlier scenarios remain, including Qwen B2/C8192+128 as an explicit
unsupported-context control. Four added scenarios are Llama B8/B16 C2048 and
Qwen B16/B32 C512, each128 Decode steps. All weights, all-layer KV growth,
page padding, 64MiB workspace and metadata must fit32GiB before execution.
These are structural Decode rates, not measured numerical LLM serving rates.

Original Qwen1.5 checkpoint inference supplies128×32×24 captured routing
records. The checkpoint and capture source are pinned. CPU FP32 routing is
model-matched; BF16-identical top-k is not established. The controlled topic
prompts are not production traffic. B1/B8/B16 use subsets with stride32;
contexts other than512 are labeled routing-transfer sensitivities. Independent
prefill prompts determine the placement prior; Decode records are not used
to train it. The previous Qwen2 projection is not the main routing source.

## Known execution mechanisms

Compare both capacity-striped B2 and prior-guided B3 resident layouts. For each,
run serial, finite adjacent-phase weight prefetch, 64-row producer/collective
overlap, and both. These adapt published mechanisms from
[SET](https://github.com/SET-Scheduling-Project/SET-ISCA2023/tree/a7bd73912f58d9fea10fadab693eebd4e6e3054d),
[SoMa](https://github.com/SET-Scheduling-Project/SoMa-HPCA2025/tree/6e808366f0005b0280cbab12a8a1d58cbbec827a) and
[DeepStack](https://github.com/tile-ai/DeepStack/tree/17e21bf54115e11b9e7c6edc0b2d1723d25d022b).
They are **not** reproductions of the full upstream optimizers and do not prove
an optimal software schedule. Global normalization, attention and layer
barriers remain conservative. Ordinary legal streaming may recover residual
losses before new hardware is needed.

Prefetch has256KiB/tile credits and64KiB returns, separate paid FIFO read/write
ports of500B/tick each; it cannot consume operands early or use unknown future
Expert IDs. MAC/collective overlap partitions the existing256B/tick SRAM read
port128+128; all writes share128B/tick. A whole local partial is reserved. Expert
cohorts are split by actual workspace and accumulated incrementally. Vocabulary
selection has two64-row buffers and associative max/index selection. None of
these is presented as new hardware.

## Typed area ledger

The Stratum reference in [§6](https://arxiv.org/html/2510.05245v1) separates
tensor MAC, Matrix RF, Row-swap RF, Psum storage and shared buffer. MAC13.9468928
plus Matrix RF5.0185472 mm² scale together. Row-swap RF4.8726592mm² remains
fixed with the unchanged banks/Tiers. Psum5.3103232 plus shared6.6176mm² scale
with storage using an assumed20% fixed peripheral /80% capacity split; report
phi0 and phi0.4 ledgers too. Vector/controller/NoC/HB resources stay fixed.
FIFO steering costs0.8mm² and its storage is inside the private-SRAM budget.
The extra LV-service budget7.4mm² and HB1mm² remain explicit assumptions.

Default active area is85.75mm². The remaining35.25mm² is **unidentified and
unavailable**, not spare MAC area. Profiles are64TF/47MiB,96/40,128/36,152/18,
192/24,192/6,256/12. The last three are rejection controls under the frozen
ledger. 152/18 represents19 rather than16 PE equivalents/tile, with both MAC
and Matrix RF paid. Array utilization and fixed port widths remain assumed.
An SRAM rejection is rejection of this finite schedule, not proof that known
row-blocked accumulation could not make that hardware feasible.

## Resource isolation

Llama B1/C2K, Llama B4/C8K and Qwen B8/C2K get individual probes for Tier
bank-cycle ceiling, Tier latency equalization, HB serialization, FIFO ingress,
and arithmetic consumption; the shared measured service guard is preserved.
The bank-cycle probe therefore does not erase all ACT/PRE/controller costs.
HB16 and ingress128B/tick are bottleneck-active negative controls. Matched
Infinite NoC and broad Ideal Memory are separate oracles. No oracle is a paid
architecture, and overlapping gains must not be summed.

Native checks record request/transaction identity, actual ACT/PRE/RD/REF,
returned-to-ingress timing, finite port service, byte-hops and exclusive MAC
tile states. Backpressure counters can overlap. Shared versus independent
command domains keep256physical banks, the same capacity and physical HB;
virtual controller identifiers do not add physical channels for free.

## Thermal and decision

Only selected feasible frontier points use the existing default0.3K/W package
boundary and HiTS/RC. The equivalent DRAM layer, source partition and energy
scales remain assumptions. Aggregate3.432pJ/B already includes memory interface
costs; no second full ACT/HB charge is added. MAC0.302pJ/FLOP, finite event
windows, static variable-area delta0.02W/mm² and periodic binning remain explicit.
No fabricated temperature/DVFS or refresh feedback is enabled. Continuous
periodic temperature is distinct from the128-step cold burst.

Research Go means a reproducible resource transition or unexplained execution
loss merits study. Hardware Go additionally needs a qualified relative model,
a strong existing execution baseline, and paid physical gains. A conventional
MAC/SRAM tradeoff or a capacity-only Ideal Memory speedup is not novelty. This
gate preserves every failed, infeasible and negative point and does not open RTL.
