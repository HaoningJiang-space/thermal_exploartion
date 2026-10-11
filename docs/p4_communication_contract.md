# P4-A：通信语义与有界 Row-ready Reduction

从 `26d1b02` 的强软件基线继续；只使用本仓库的硬件合同和原始 Qwen1.5 routing。
性能点全部采用真实形状、真实捕获路由，不使用 smoke 或生成的路由。
固定 B3 training-prior placement、128 TFLOP/s、36 MiB SRAM、原有 DRAM/HB、4×4 mesh、SRAM 端口、256 B packets、Joint Kernel。
本轮不改变 Joint Kernel 的保守资源预留；其影响留给 P4-B，不能把本轮剩余 Oracle 当作新硬件动机。

预先固定三组 Layer/Step：primary s0/l0；holdout s32/l7、s127/l23。
每组 B8/B32 × TP4/TP16 × column/row down × 三种输入交付 × 两种 reduction admission × baseline/infinite-NoC。
共288个性能点；不是普通 DSE，也不进行逐点 placement/scheduler 选择。
Column/row、各输入/reduction 方案只作同一 routing case 的配对比较。

## 输入交付的精确边界

原输入按 hidden 维度分布在16个源 Tile。每个源持有所有 Token 的1/16输入。
Routed 与 Shared Gate/Up 都是 intermediate-output sharding；Shared owner固定全部16 Tile。
因此每个 Token 的必要目的地集合为 routed owners 与 shared owners 的并集，仍是全部16 Tile。
Destination-only **不允许删除 Shared 的合法输入供给**。

* `broadcast_all`：保留26d1b02的 batch-level multicast、输入 barrier，作为精确重放控制。
* `destination_only`：逐 Token 按必要目的地并集 multicast，同一 endpoint 的 shared/routed input只交付一次；routed job只等其自身 Token。
  此处改变 packet 排序及输入就绪粒度；不声称收益都来自字节减少。MAC/端口的 barrier模式保持原样。
* `decoupled`：Shared 全量交付和 Routed owner-only交付独立进行，重复输入通信全部付费，最终复用同一 resident input地址。
  这是取消输入复用的合法对照，不声称它穷尽所有不同 Shared 权重划分。

没有迁移或复制 Shared 权重。改用 Shared 的 K-sharding 或 token-parallel computation需要重新布局权重、Gate/Up FP32 reduction、输入转换或远程 weight movement；本轮不免费引入这些变更。
本轮可回答固定权重布局下 dispatch/就绪调度是否解释 NoC Oracle；不能据此宣称所有 Shared dataflow 都已最优。

## Reduction 与有限 SRAM

`drain_all` 是旧控制：所有本地专家结果完成后，串行接纳128-row reduction。
`row_ready` 等当前128-row producer cohort的全部本地 contributions，随后按64-row网络 cohort串行接纳 reduction；允许与后续行计算重叠。
在原有64 KiB output空间内保留16 KiB local partial credits、48 KiB reduction credits；不是新增 buffer。
B32的128-row local partial最大16 KiB；64-row network cohort每个入边最大8 KiB，XY tree最大四个入边，最多32 KiB。
一次只允许一个网络 cohort；输入全部就绪才发射。局部生产者不依赖最终 reduction 完成。
不同 credit类共享同样的 private SRAM、读写端口、router/link资源；模拟器记录分项及合计高水位，验证所有资源占用无重叠、所有 lease归还。
更多 cohort付出的 admission/flight成本保留，不恢复旧的无界并发调度。

## 数值验证与归档

性能图附加 semantic ledger：Gate/Up intermediate区间、Down输出行/K区间、Token IDs、routing weight slot及对应 MAC/accumulate node。
独立检查 full-shape ledger每个元素覆盖一次、routing slot正确、MAC字节账目与原 baseline一致。
小张量数值参照采用同一真实 captured expert选择及概率，d256/h32/shared128；确定性生成的权重/输入只用于语义验证。
参照逐 Token计算完整矩阵；candidate解释图的 shard/token ledger，做本地加权融合与FP32 accumulation。
FP32/BF16分别比对，BF16 case对输入/权重/概率/gated state做round-to-nearest-even存储；不是训练checkpoint的数值验证。
捕获文件没有 Shared gate activation；小张量检查用确定性的 shared-router权重计算sigmoid，两边一致。

每个性能点保存完整 events、source/routing/layout/point hashes、真实执行case、原 packet与补齐 kernel活动账目、critical chain、finite-credit审计。
旧基线与归档26d1b02须精确重放；失败、负收益和不收缩的Oracle都保留。

## 有界 cohort 粒度补充对照

初始64-row方案在主案例中没有延迟净收益。为排除较保守cohort造成的额外序列化，追加同三组case、B8/B32、TP4/TP16、column/row的 `broadcast_all + row_ready_128` baseline/infinite-NoC，共48点。
沿用16/48 KiB信用划分、一次一个tree/root、所有该行producer ready的admission；128-row数据按256B packet逐包推进，最多四个incoming packet需要1 KiB才能使对应packet join就绪。
信用不足时停止对应packet注入，等待已就绪树内消费者释放；不需要为完整128-row的全部入边数据同时保留64 KiB。
所有真实点仍做独立事件与容量重放。此对照在观察64-row负结果后冻结并执行，不能写成最初预声明矩阵，也不混同增加buffer。
