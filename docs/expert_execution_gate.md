# P0–P3：真实路由下的传统执行边界

唯一研究主线为 `thermal_exploartion` 的 hybrid-bonded、DRAM-on-logic 架构。
固定合同为 121 mm²、32 GiB DRAM / 256 banks / 8 tiers、16 logic tiles、
128 TFLOP/s、36 MiB SRAM、32 TB/s HB、4×4 mesh 每方向32 GB/s。
这是 Stratum-inspired 条件性加速器模型；没有把 W2W 的 Gateway、带宽或 cold FFN 数据移入此合同。
计算全部在 logic；PIM 和 power delivery 不属于本轮。

完整结果、图表、有效/退役记录及复现入口见
[正式报告](../results/expert-execution-2026-10-11/findings.md)和
[冻结合同](../results/expert-execution-2026-10-11/experiment-contract.json)。
本轮不扩展 thermal DSE，不重新打开已关闭的 Fabric、Peripheral 或 Row-cycle RTL 分支。
Spatial Thermal 仍属于整体研究边界；上一轮温度结果不为本轮新执行策略提供独立资格。

## P0：Memory abstraction，不是完整前端验证

在 `83b1655` 的相同 flit、MAC、端口和有限缓冲执行器上，对照原生 Ramulator 与未按目标延迟拟合的 fluid memory。
五种真实模型 tensor shape、两种已付费 compute/SRAM profile，产生36个原始点、18个绝对延迟对照、9个相对 profile 对照。
这隔离了 DRAM service 抽象的误差；两者共享前端，所以没有独立验证整个前端，也没有为完整 H3 或先前的12.92%/7.06%全模型增益颁发精度资格。
旧的 whole-input/32KiB mismatch 控制继续保留。

时钟使用 native half-CK：逻辑 tick0.25ns、HBM3 CK0.5ns、native tick0.25ns，比例1。
先前 factor-two 校正已撤回，详情见[时钟勘误](clock-domain-erratum.md)。

## P1：容量失败须先排除已知软件实现

`b468306` 对 Qwen B32/C512、24层、全部128步比较128/36和152/18的 cohort 与64-row accumulation。
Rows 使用 bounded gated cohorts、完整 token accumulator、有限输出行；MAC、DRAM、HB保持相同工作量。
152/18仍需接受独立的面积缩放假设和 SRAM periphery 敏感性，不能把逻辑面积直接兑换成 DRAM 面积。
原 cohort 的有限调度失败被保留，不能概括成 B32 的硬件容量不可行。

## P2：已知机制要作为主基线

原始 checkpoint 的真实 routing 为四个 separate training prompts 和32个 holdout topic prompts；
训练先验只来自 separate prefill 的256个位置，权重 owner、tier、地址和 TP/EP 分组在执行前冻结。
主评估选 steps0/32/64/96/127 × layers0/7/15/23，B8/B32；
EP、TP4、TP16、固定 hybrid；两种 placement；barrier/static、overlap/static、overlap/dynamic LPT。
每个策略使用同一20个 cases，不允许逐点选择 placement oracle。

主融合基线 `15ad39e` 使用普通线性性：每 tile 支付完整 B×D×FP32 accumulator，
本地乘 routing weight 并累加，最后每个 output row 只做一次普通 tile-vector/tree reduction。
32KiB joint kernels、256KiB weight prefix、64KiB returns、64KiB output buffers、
128+128B/tick read 分配、128B/tick write、gated-state leases 和 shared resource arbitration 均保留。
Joint node 的时间包含 memory/MAC 服务，不可标作纯 MAC stall；总 busy windows 不可相加成 critical path。

`2f63ce6` 的 early concurrent reductions 会占满共享输出 credits，造成 B32 barrier deadlock；
`15ad39e` 采用普通调度：本地 partial drain 后，再逐行进入 final reduction。
没有增加队列或独立端口。旧结果归入 retired scheduling controls，不是硬件不可行证据。
这个保守 row admission 同样限制融合重叠；本模型不证明全局软件最优。

Row-down supplement 沿输出行冻结权重 shard、支付 hidden allgather，保持 tier bytes 和容量。
其6个 cases只与 column 的相同6个 cases比较，不与20个 cases的均值直接比较。
这是静态 software layout，收益还包含 macro-prefetch/tiling变化，并非只由 NoC 字节减少解释。

## P3：反事实是诊断，不是付费机器

最初矩阵对 B8/B32、step0/layer0、四种 partitions、两种 down layouts测试既定8个干预，作为overlap/dynamic调度控制保留。
`4648f3c` 追加 `native_only` 和 `hb_ingress_only`，并重新执行 `none`，核对原基线逐项一致。
Native-only 移除 DRAM service serialization/arrival latency，仍保留 HB、FIFO、有限 credits 和计算。
HB+ingress-only 同时移除这两个返回速率项，保留 DRAM、消费 FIFO 及其有限容量。
HB-only和ingress-only分别移除一个 max 项，另一个相同的500B/tick项仍然存在，不能据零增益断言接口无关。

P2汇总发现融合后barrier/static优于原overlap/dynamic；因此`7890865`在同样两种down layouts和四种partitions补跑10个干预，
以最强已测固定策略作为主P3。其none与P2的同层/步/策略基线在延迟、活动量和关键路径上逐项一致。
这反映当前保守joint资源预留及read-port分配，不证明现实软件只能选择这些策略。

所有干预保持完整 MAC 和权重读取字节。Bank-cycle 放松仍保留26.599TB/s shared guard；
uniform-fast-tier不是可制造的 equal-latency器件，ideal-memory和infinite-NoC不是付费架构。
不同干预收益重叠；仅两个 layer/step workload 不能建立整个模型或生产流量的结构性结论。

## 审计与决定

导出要求每个进程exit0、完整冻结case集合、clean source、routing/prior哈希、summary与point一致、
事件哈希、MAC/DRAM及critical parent chain闭合。
宏执行器的 packet DAG 只显式记录 prefetch，公开数据另外保存原 packet ledger，
并从完整 kernel ledger补齐 DRAM/HB与operand SRAM reads；全局及per-tile账目必须闭合。
该补齐用于活动账目，没有把 macro时序假装成原生 DRAM command trace。

真实路由是模型匹配的受控捕获，完整 numerical LLM是在capture CPU端执行；
架构执行器没有计算和比对完整 BF16 tensor值。两组 paired FP32/BF16控制使用相同 teacher-forced inputs，
保留 routing差异，不能宣称生产代表性或 FP32路由与BF16相同。

本轮可完成 Research Go 的证据链；新 Hardware Go 仍须提出具体不可由传统执行等价实现的机制，
补齐独立前端精度、器件成本与跨工作负载/热约束验证。
[相关论文边界](moe_architecture_reading.md)包含一手来源核对及未复现项。
