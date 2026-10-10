# HB 与 DRAM 内部组织：小型必要上限审计

状态：Compute–Memory Fabric 正式关闭。保留固定 Local NPU，先检查供数边界，不提出新硬件。
脚本 `thermal_exploration.memory_audit` 是必要速率上限与既有 LP 的组合，不是周期级 DRAM 仿真器。
它不能证明普通 Mapping、Scheduling、Voxel Tracker、SALP 或已有 DRAM 技术无法消除瓶颈。

## 固定组织和假设

沿用 16 Tiles、16 Bank Groups、Compute/SRAM/queue 数量、DVFS 集合和冷却梯度 0.6。
HB 只取 1/16/32 TB/s 三个接口条件，空闲带宽不产生额外动态功耗；不增加 Fabric 搜索空间。
Batch-1 GEMV 与 Batch-32 GEMM 都必须完成既定工作；LP 仍为同一个 Kernel 的稳态可分流上界。
每个条件重新优化 Local 的普通静态数据放置、工作分配与 DVFS。

配置 `configs/memory_audit.json` 中所有时序、行大小、ACT/column-domain 数和能量拆分都是显式未校准假设，
不是 Loh/SALP/Stratum 的 HB 器件测量。不能把示例中的共享 ACT-domain 边界当作真实 HB 必需的边界。
32 Banks/Group；假设 1 个 ACT-domain 和 8 个 column-domain/Group，domain 内共享相应速率预算。
同时保留 full-row、quarter-row、small-row 与 bank-concentrated 流量，不过滤不利结果。
改善 useful bytes/ACT 和 busy banks 是普通 locality/scheduling/data-mapping 对照。

## DRAM 速率分解

令 q 为每次 ACT 实际交付的有效字节，b 为 busy Banks，a 为独立 ACT-domains，c 为 column-domains，
v 为一次 column 命令传输的有效字节。每个 Bank Group 的必要上限（byte/ns 除 1000 得 TB/s）为：

- Bank ACT/PRE：`q b / (tRAS+tRP)`。
- ACT 间距：`q a / tRRD`。
- 四次激活窗口：`4 q a / tFAW`。
- Shared column/periphery：`v c / tCCD`。

`B_internal <= min(上述各项)`。这些是稳态必要上限；它们的最小值仍可能无法由任何命令调度达到。
不将旧模型 `1/(1/Bpeak+serial_row_penalty)` 再加一次，以避免 ACT/PRE 双重收费。
`tRCD` 是首次 ACT→column 的等待，单独记录；本审计未生成命令依赖，不能据此宣称覆盖完整首次访问时延。
请求往返延迟仍使用原 50ns Little's Law 上限，缺少每次 row miss 的延迟分布。

增加一个已有 Subarray-overlap 技术的理想上界：仅将 Bank ACT/PRE 速率项乘 8，
**保留 tRRD/tFAW 和共享 column 上限**。这不是 MASA 的完整实现，也没有计入其新增面积/能量，
只用于检验：即使 Bank 内重叠理想化，ACT domain/column 限制是否仍然存在。

## Logic、功率与热

`B_noheat <= min(B_HB, B_internal, C_peak/I, Q transaction_bytes/read_latency)`。
既有 Local LP 施加四套热对照 T0/T1_scalar/T1_layer/T2，重新优化相同资源。
报告 noheat 限制项、实际模型流量、HB utilization、相对 T0 的热损失及只放开内部时序的收益上界。
只放开时序的对照保持 ACT/PRE 次数、能量与硬件预算一致，不能把能量消失误算为时序收益。

功率拆成 `N_ACT E_ACT + N_PRE E_PRE + useful_bytes (epsilon_array+epsilon_peripheral)`，
稳态每个新行一次 ACT/PRE。仅将旧 8nJ 拆成 6+2nJ、12pJ/byte 拆成 4+8pJ/byte，
这只是账目分解，不是物理校准，也没有定位真实外围电路热点。
全部 DRAM 费用进入原 DRAM 热节点；缺少 refresh、温度相关 leakage、无效 column 流量、PHY 静态增长。

## 决策边界

若充分 row reuse/bank spreading 后 T2 主要限制供数，则当前证据支持先校准功率/热预算。
若小粒度流量受到 ACT/PRE 或 domain 速率限制，先验证普通合并、Tracker、SALP 和 DRAM 调度能否解决。
只有真实 HB 组织与 trace 显示：已有技术后仍有显著、HB 特有的内部结构损失，才进入新硬件设计。
本脚本产生任何正的时序放松收益，都不能自动满足这一条件。
下一层验证应接入实际组织与时序规格、Ramulator/DRAMPower 或等价经过验证的命令级模型，
并匹配实际 HB 功率、供电/activation-domain scope、row geometry 和空间热边界。

运行：`python -m thermal_exploration.memory_audit --output outputs/memory-audit`。
HiTS CPU 校核仍在原 Linux 环境执行，HiTS 源码不变。
