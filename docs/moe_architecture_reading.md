# MoE architecture reading and novelty boundary (2026-10-11)

This is a primary-source reading record for P0–P3, not a reproduction of the
cited accelerators. Our machine remains DRAM-on-Logic, no array compute, fixed
121 mm²/32 GiB/36 MiB/128 TFLOP/s baseline. Only the already charged152/18
profile is examined for qualification and the known workspace repair.

| Primary source read | Mechanism / evidence | Consequence for this experiment |
|---|---|---|
| [SNAKE v2, §§3–6](https://arxiv.org/html/2604.04253v2) | Compute substrate and scheduling co-design; reconfigurable array/dataflow, buffer-to-compute area exchange, vector support reuse. SystemVerilog/ASAP7 and synthesis/activity energy, not manufactured HB measurements. Evaluation assumes uniform MoE routing and24 TB/s. | More MACs, less SRAM and flexible arrays are covered ideas. Our actual-routing resource conflict needs separate evidence. Abstract reports2.91× while HTML body reports2.90×; neither becomes our simulator calibration. |
| [Stratum, §§4–6](https://arxiv.org/html/2510.05245) | Local channel access, expert TP, attention PU groups, tier placement, overlapped nonlinear/collective work. High-voltage CUA and low-voltage bonded CMOS occupy distinct physical regions. | TP16 one-expert-at-a-time is an existing baseline. Tier capacity is regional, not freely pooled; total-byte energy is accounting, not command-energy identification. |
| [Patterns behind Chaos v5, §§III–VI](https://arxiv.org/html/2510.05497v5) | Real traces from four large2025 MoE models reveal cross-layer, token, prefill/decode and popularity/co-activation patterns; evaluates forecast/placement ideas on wafer-scale and existing systems. | Uniform routing is a control. Use independent training prefixes for placement, no future Decode IDs for prefetch. Our Qwen1.5 topic capture is smaller and a different model, so it cannot reproduce those population-level findings. [ISCA official award page](https://www.iscaconf.org/isca2026/index.php) confirms its Best Paper award. |
| [Duplex, §§III–VI](https://arxiv.org/html/2409.01141) | Per-expert effective batch changes operational intensity; heterogeneous xPU/logic-side near-memory expert co-processing, continuous batching and modified Ramulator modeling. | Effective expert count matters more than global batch. This is an existing heterogeneous mechanism, not evidence that our single-die ownership needs new hardware. |
| [3D-MoE, publisher record](https://ieeexplore.ieee.org/document/11240872/) | ICCAD2025 title/DOI located; full text could not be retrieved through the publisher's browser verification. | Keep DOI10.1109/ICCAD66269.2025.11240872 as an uncompleted full-text check. Do not claim detailed DCIM circuitry or reproduce its speedup from secondary summaries. The similarly named **spiking** MoE paper is a different work and is excluded from this citation. |

## Existing execution mechanisms, not hardware claims

[FlashMoE](https://github.com/osayamenja/FlashMoE) documents a fused, tile-pipelined
persistent Dispatch–Gated-MLP–Combine GPU kernel. Removing stage barriers alone
is therefore not novel. [DeepEP](https://github.com/deepseek-ai/DeepEP) provides
expert dispatch/combine infrastructure; [DeepGEMM](https://github.com/deepseek-ai/DeepGEMM)
provides grouped/masked matrix execution. We borrow the principle of explicit
runtime task dependencies and effective expert batches; we do **not** run these
CUDA libraries on our CPU simulator or claim their measured GPU performance.

[HDA-MoE](https://github.com/PKU-SEC-Lab/HDA-MoE-TCAD26) is a necessary TP/EP and
placement reference. Our frozen owner groups, training-prior placement and
runtime longest-first ordering are named conventional proxies, not HDA result
reproduction or exhaustive optimal scheduling. No expert replication or
unpriced weight migration is enabled. Hybrid assigns eight training-popular
experts TP16 and the remainder TP4, with every shard capacity charged.

[MoE-CAP](https://github.com/Auto-CAP/MoE-CAP) motivates sparse-aware reporting.
Our **MoE-subgraph** metrics separately record total expert model weights,
active unique weights, physical reads (including page padding), and executed
MAC FLOPs. Service-normalized sparse byte/FLOP utilization is explicitly a
model metric, not whole-LLM MBU/MFU or GPU measurement.

## Evidence hierarchy

* P0 command replay independently checks emitted commands against the pinned
  DRAM definition; the shared-frontend fluid control checks service abstraction
  under identical input microblocks, buffers, ports and reduction execution.
  Sharing the frontend prevents it from independently validating that frontend.
* P1 is an implementable software schedule with full-model work/byte closure,
  not a device calibration or novel memory hierarchy.
* P2 packet execution retains conventional ownership, actual captured routing,
  finite SRAM and actual collectives. A local joint kernel conservatively owns
  its group's service until its result rows drain. This admits useful comparisons
  but does not prove globally optimal FlashMoE-like instruction interleaving.
* P3 reports mixed memory/MAC kernel windows, exact packet dependencies and
  component counterfactuals separately. Their gains are nonadditive. Native
  command evidence for selected TP16 kernels cannot be renamed full EP or
  Mono3D command validation.

Other suggested works (MoEA, MONET, DyNAMoE, MoE-Hub, DySHARP, ThAME, SIGMA,
EIE, TETRIS) remain novelty checks before any hardware proposal. P0–P3 introduces
no reconfigurable array, in-network computation, new NoC or new Fabric.
