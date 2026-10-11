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

## P0–P3 完成前的新增新意排查（2026-10-11）

以下均使用原作者/会议/出版社的一手来源；摘要级核对和全文核对分开记录。
这里是在限制我们可以声称的贡献，没有把这些论文的 speedup 当成本项目的性能数据，
也没有声称已经复现其完整调度器或器件。

| 工作 | 本次读取深度与已确认机制 | 对本项目的限制 |
|---|---|---|
| [MoEA, ASP-DAC 2026](https://ieeexplore.ieee.org/document/11420669/) | 出版社摘要：硬件 metadata queue 的 Direct Token Access、利用 token reuse 的动态 expert 顺序 | Direct token access 和 dynamic expert scheduling 本身已有先例；我们按 count 的 LPT 也不等价于其调度器 |
| [MONET, DATE 2026](https://past.date-conference.com/proceedings-archive/2026/DATA/1442.pdf) | 官方 proceedings 可检索正文/摘要：两级计算/通信组织、multicast 与 output aggregation | “给 MoE 加 multicast/reduction NoC”不构成充分的新意；未核对完整成本实现，不能宣称同成本胜出 |
| [DyNAMoE, DATE 2026](https://past.date-conference.com/proceedings-archive/2026/DATA/1217.pdf) | 官方摘要：动态可重构 NoC，token routing、input/weight distribution、result reduction | 动态 expert 通信已有硬件方案；不要与同名算法 DynaMoE 或 Apple inference 项目混淆 |
| [MoE-Hub](https://arxiv.org/html/2605.05888) | 公开全文与作者摘要：logical destination 与地址管理解耦，hub 处理分配及数据流；作者注明 ISCA 2026 | 普通 address/control 解耦已不是空白；本模型没有测量此类地址管理开销，不能借 oracle 推导同类贡献 |
| [DySHARP](https://arxiv.org/html/2605.05607) | 公开全文：dynamic multimem、token-centric fusion；GEMM epilogue 先乘 gate weight，再做 unweighted reduction | 本地 weighted accumulation + reduction 使用普通代数线性性；流量下降还需具体调度才能转成延迟收益，不能包装为独有机制 |
| [ThAME v2](https://arxiv.org/abs/2607.17074) | 原作者摘要及版本元数据：FeFET/DRAM heterogeneous 3D chiplets、compute mapping、专用 MoE NoC；未精读器件实现 | 3D memory + MoE + tailored NoC 组合已有同期工作；其异构存储合同与我们的 DRAM-only、logic compute 不同 |
| [SIGMA, HPCA 2020](https://doi.org/10.1109/HPCA47549.2020.00015) | 出版社摘要：irregular/sparse GEMM、flexible interconnect、Forwarding Adder Network | 灵活 shape/稀疏利用与 reduction tree 本身已有先例；没有把其工艺 PPA 移植进本项目 |
| [EIE, ISCA 2016](https://hanlab.mit.edu/projects/eie) | 作者页面摘要：compressed weights、weight sharing、sparse matrix-vector engine | 低复用供数问题不能被概括为首次发现；当前固定 BF16 数据量也不能免费采用其压缩收益 |

[HDA-MoE 的原作者摘要与版本说明](https://arxiv.org/abs/2609.08682)也再次核对：
其 hybrid-bonded NMP、offline hybrid deployment、online adaptive scheduling 与当前问题直接相邻。
本项目只实现 EP/TP4/TP16/固定 hybrid 与三种常规执行策略，不宣称完整复现 HDA-MoE。

因此，本轮允许得到的是：在明确合同和固定真实路由下，已知软件机制可以恢复多少损失、
剩余限制对哪些物理资源敏感。新硬件必须另有不可由这些机制等价实现的设计与成本证据；
P0–P3 完成不自动产生 ISCA/MICRO/HPCA/ASPLOS Hardware Go。
