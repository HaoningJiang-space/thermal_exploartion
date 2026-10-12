# P4-B：完整 MoE G3/G4 冻结合同

仅 `thermal_exploartion`，基线 `09c99f2`。目标是完整 Expert 与竞争、完整 MoE 和排序资格；不新增 NoC/MAC、P4-C、Thermal/微流道或普通 DSE。

## 固定工作与数据

原始 Qwen1.5 捕获解压 SHA256 `24aba0d1337106563e6b05f4f54ea6d5861838a930a376d99ae5feac9bcdb9e6`。
真实 hidden2048、routed1408、shared5632；保留整个模型的 B3 frozen resident layout和所有层/专家的物理容量分配，不把活跃权重压到免费的 fast tier。

G3-A：s0/l0/B32/TP4/Column，Cold12（1 token）、Reused10（22 tokens）分别执行完整 Gate/Up→SiLU/product→Down→weighted local token accumulation→writeback/Combine。
G3-B：同条件 Experts10/34（各22 tokens，共享tiles8–11）。用已存在的 fine_prefetch 只放松已知地址的 memory admission；MAC/Expert顺序、全部有限credits不变。与G3-C的fine_fixed分开，不把调度收益归为reservation收益。
G3-C/G4：s0/l0 B8/B32 × TP4/TP16 × Row/Column，8个全MoE点。随后同矩阵检验s32/l7、s127/l23，共16个迁移点。这些不是新Prompt盲测。完整MoE必须包含真实Shared Expert、Broadcast-all、Fused Combine、Row-ready128，routed Row-down时Shared仍Column-down。
子图入口给定当前Top-4 IDs和routing probabilities；不含此前Routed Router/Top-k算子。Shared的scalar gate不免费：实际resident shared_router weights、16-way FP32 scores、Sigmoid（沿用6-op scalar/vector假设）和scale broadcast全部付费，Shared weighted-partial必须等待该scale。Scalar MAC读取实际local token operands，不能套用矩阵read-reuse近似。

每个点执行独立C++ Native和C++ Fluid参考，以及独立Python tier-fluid预测。共享语义DAG builder、物理假设和固定仲裁合同，执行状态不共享。预测器无原生到达时间输入，无倍率拟合或逐点调参。

## 逐tick执行，而非 Joint Kernel 时间表

原microtile生成器的32KiB registered-reuse blocks逐个进入有限weight slots；1024B requests→Native command/return或tier-fluid service→HB→FIFO→MAC。MAC按实际剩余周期均摊operand read，和Vector/NoC共享256B read、128B write；FIFO ingress/consume500B/tick，MAC2000FLOP/tick。

单Vector Context从read开始保持到ops/write结束。32B flit，4-tick directed-link串行化，8-tick flight；两类VC，每个physical input port/VC和local injection port各8 slots。Flit从发送前reserve至直接消费者启动后释放，覆盖flight、queue和SRAM背压。
网络是新完整程序的确定性DAG frontier仲裁扩展：MAC、单Vector、sink/source SRAM、links、HB、memory；同类按原ID顺序。Multicast保留共享前缀；本地接收与下游branch分别付费并保留credit。这**不是H2的逐port轮转实现**，不能沿用组件2.54%作为全MoE精度；完整C++/Python合同必须重新验证。没有为任一方案搜索仲裁策略。

保留原P4-A/P4-B macro/fine模式；不静默替换旧性能。当前完整程序仍使用已知registered partial reuse、每个gate/up和down-row的语义完成点；不宣称新GEMM调度或完整checkpoint数值。

## DRAM与物理账目

Pinned Ramulator `c6c7a5d`、16 physical channels、每channel两条既有PC路径，共16 banks/channel；不添加domain。
全部resident tensor按其实际tier分配唯一1024B地址：tier内bank-interleaved pages，row高位表示8个capacity tiers，所有tiers共享同一bank state。Native沿用TierTiming deadline extension、真实ACT/PRE/RD/REF和原时钟；refresh从执行开始计时。
Python保留预先存在26.599TB/s guard、tier row-cycle limit及tier return offset；它是Memory抽象，不是新的DRAM模型。每Tile最多发射一个request/tick，两种参考一致；没有用原生记录补齐预测。

Private SRAM、8×32KiB weight、64×1024B response、descriptor和output credit分区都不增加。所有已付费固定storage、动态workspace/receive/transmit/output leases及router slots显式重放。不得早消费、重复读权重、遗漏token/weight slot或通过额外contexts绕过端口限制。

## 验收与失败处理

G1：完整FP32/BF16小张量数值语义（非性能/非checkpoint），真实形状的MAC、weight、token、routing slot、Gate/Up/Down覆盖闭合。
数值验证固定FP32 K维累加顺序（非BLAS grouped GEMM的库相关顺序），以便Gate的GEMV/GEMM在BF16 gated-state舍入边界具有同一合同；容差仍为rtol2e-4/atol2e-6，不拟合或放宽。旧模式保持BLAS默认。首轮f0ee803 pilot的Reused/Competition在此合同差异处失败，全部原始失败记录保留，不混入新资格。
G2：每tick端口、每个MAC/Vector Context、packet依赖、weight/response/output/private/router reserve/release独立重放。
G3：完整MoE Native逐点绝对时间误差≤10%；Fluid五类完整节点/request/port/lease/router traces逐行比较。Native额外command/state/tag和tier-deadline检查。
G4：每cohort同路由的TP4/TP16和Row/Column逐点比值误差≤5%，核对排序。不能靠均值掩盖失败。
如有分歧，导出首次事件差异及依赖/资源/Memory归因；原始失败保留，禁止全局倍率拟合。
只有完整G3/G4通过后才运行qualified link/flight诊断；仍不是可实现硬件净收益。组件或Fluid一致不等于silicon认证。
