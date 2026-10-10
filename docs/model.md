# 模型方程、预算与适用范围

## 资源与功率

变量 `x[i,j,k]` 表示 Compute i 在 DVFS k 下、由 Bank Group j 提供数据时的有效 TFLOP/s。
完成率为 λ；Fixed placement 要求每个 Bank 的流量与 `λ p[j]` 一致，不能仅执行容易完成的 shards。
Free placement 约束总完成率，并要求每个 Bank 的数据份额不超过相同的容量份额上限。
它为每个稳定单算子选择可复用的静态数据布局，不表示真实运行中免费搬迁数据。

算术强度 `I = 2 B M K / (e (M K + B K + B M))`，一次乘加计 2 FLOP。
输入按理想广播处理。输出和输入的额外通信、部分和归约没有单独建模。

`sum_jk x[i,j,k] / (C_i f[k]) <= 1` 给出每个 Tile 的执行时间预算。
`V[k] = Vfloor + (1 - Vfloor) f[k]`；Logic 动态功率为 `epsilon_L V[k]^2 x[i,j,k]`。
静态功率与有效工作无关，始终加入预算。这个模型允许 clock gating、DVFS time sharing，
不建模切换延迟及瞬态温度；它不能证明所有实际 Scheduling/DVFS 都无法改善性能。

DRAM 使用带宽为 `B_j = sum_ik x[i,j,k] / I`。

`B_effective = 1 / (1/B_peak + miss_fraction t_miss/(chunk_bytes N_banks))`

这里用 Bank Group 内独立 Bank 并行度摊销激活延迟，仅是可解释的带宽放松模型，
未实现 tFAW/tRRD、read/write turnaround 或周期精确的 Bank 调度。

`P_D = P_D0 + (epsilon_D + E_ACT miss_fraction/chunk_bytes) B_used`

因此仅提高闲置的峰值 HB 带宽不会凭空增加 DRAM 动态功率。
实际吞吐率增加、Row ACT 效率变化和新增 PHY 静态功率才会改变热预算。
`chunk8k_tracker_bound` 是双方可用的理想 Row 协调上界，未实现 Voxel 的请求 Tracker。

请求队列满足 Little's Law：`sum_jk B[i,j,k] latency[i,j] / transaction_bytes <= Q_i`。
所有架构使用相同 Q 和 private SRAM，SRAM 只检查 chunk 的双缓冲可容纳性，未建模端口瓶颈。

## 连接成本

Local：只保留 i=j。Neighbor：保留 Manhattan 距离 ≤1。Global：全连接的理想服务上界。
付费 mesh 使用固定 XY 路由，逐个 directed link 约束流量；远端流量每跳消耗给定能量，
能量平均分配在该跳两个 Logic 区域。逐跳延迟进入请求队列占用，不直接等同于单算子延迟。
面积开销通过减少可用 MAC 吞吐率收费，private SRAM 不减少。
相同面积和静态功耗的 Local matched 保留完全相同资源，只关闭 remote service。
因此付费方案相对 Local matched 的收益是组织收益；相对原始 Local 才是增加 Fabric 的净收益。

## 热方程

三个 4×4 平面：Logic、DRAM 和被动 Copper spreader。温度为环境温度之上的升温。
`A theta = Q P`；A 的单位为 W/K，Q 把每个有源区域的总功率放入对应节点。
内部边使用对称导热通量；表面侧边绝热，顶层每个区域对环境进行 convection。
垂直边含两侧 half-cell thermal resistance 和显式 bond/TIM thermal resistance。
`H = A^-1 Q` 的 Logic/DRAM 行用于 Thermal-2 的所有温度限制。

Thermal-1 使用同一 H 在所有区域均匀、Logic/DRAM 等功率条件下最热层平均升温拟合单一 R。
新增 T1_layer 使用两层平均 2×2 resistance。若每层有 n 个区域，
`R_rs = sum_ij H[receiver_r_i, source_s_j] / n²`，扩展后的每个 n×n block 全部填 R_rs。
因此 `DeltaT_r = sum_s R_rs P_s_total`，保留独立 Logic/DRAM 温限。
它准确匹配每层均匀热源的平均温度，不代表非均匀热源下的热点。
空间交互改用 T2/T1_layer；T1_scalar→T1_layer 的差异单独记录。
整数模式 0/1/2 保持旧含义，新增模式 3 = T1_layer；输出同时包含 thermal_model 名称。
R 固定后，对每个架构使用相同模型。Logic/DRAM 功率比例不同，单一 R 的误差仍需单独评估。

HiTS 为每个单位功率列求解原始 A，不修改矩阵。验证 residual、H 非负及热互易性，
并独立对照 SciPy sparse direct solve。这里验证的是数值一致性，未验证真实封装温度。

## 仍需补齐

当前几何与所有参数均明确列为假设；不把 HBM-class 设置作为 wafer-scale 校准。
需要网格收敛、HotSpot/3D-ICE 原生组装对照、真实 HB 介质/接触参数和冷却边界。
需要真实功率轨迹、DRAM refresh/leakage 温度反馈、温度随时间变化与 DVFS 闭环。
需要多算子共同的数据容量约束、布局切换成本、NoC arbitration、输出归约与真实 transformer/MoE traces。
G2 已增加同一权重的共享容量、双向迁移计费与周期 RC 峰值检查，但多 tensor 生命周期和真实执行语义仍未覆盖。
这些未完成前，只能报告模型内筛选，不可宣称普遍 Architecture Design Principle。
