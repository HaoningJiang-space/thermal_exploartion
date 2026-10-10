# 研究命题与分阶段决策

当前状态：G2 Shared-Placement Gate 已完成，未通过 5% 净收益门槛，当前 Compute–Memory Fabric 分支结束。
结果见 [G2 报告](../results/g2-2026-10-09/findings.md)。下述进一步校准与硬件设计步骤是条件计划，本轮不执行。

目标：传统资源边界是否在 HB 高带宽和 3D 空间热耦合下成为持续性能限制？
核心命题为 **When Does Compute–Memory Locality Become Suboptimal in Hybrid-Bonded 3D Accelerators?**
不预设非局部连接应当胜出。

第一阶段只改变 Memory Service Ownership；Request tracker、SRAM 和计算资源总量保持同等预算。
Compute 可映射至不同 Tile，但不改变 MAC 组织；SRAM 不跨 Tile 池化。
理想 Global 是可撤销约束的上界，Neighbor 是有限范围候选，付费 Mesh 是开销筛选。
当前运行不包含新 Controller 或 Access Processor 的 RTL 设计。

## 第一阶段：证伪

1. 16 Tiles/16 Bank Groups，两片 active dies 和被动散热层；HB 峰值固定。
2. Batch-1 GEMV 与 Batch-32 GEMM；每次重新优化访存 chunk、Mapping、DVFS time shares。
3. 无热限制、全局单一 R、完整空间 H 分别优化。
4. Fixed demand 与可优化数据放置分别比较，防止夸大不能用软件解决的损失。
5. 均匀布局/冷却负对照，中心 demand 偏斜、非均匀冷却场景同时保留。
6. 加入 NoC 带宽/延迟/能量/面积，匹配硬件预算，也比较新增开销后的净收益。
7. 单因素敏感性扫描全部保留。5% 为事先指定的“值得继续校准”筛选门槛，非统计显著性门槛。

比值 `g_m = F_B,m / F_A,m`。`g_2/g_1 > 1` 表示相对收益存在空间模型交互；
还要检查 g_0、g_1 以及重新放置数据后的 g_2，才能辨别普通负载均衡。
Resource Ownership Loss：`1 - F_A,2/F_B,2`。
Local Spatial Penalty：`1 - F_A,2/F_A,1`，该数可为负，不能人为截为零。
二者不是正交的物理分量，不应简单相加或把所有差值归因于热。

A：所有理想候选均无明显收益，保留 Local。
B 候选：T0/T1 近似无收益，T2 明显受益，而且 Free placement、付费开销与热参数范围下仍成立。
C/混合：收益来自固定布局、负载偏斜、Bank conflict 或普通共享，重新定位问题。

## 第二阶段：物理及执行校准

第一阶段通过筛选后，再构建密集网格并进行 HiTS 原方程资格检查和独立 native thermal 对照。
HiTS 可继续作为求解器；HotSpot/3D-ICE 或经验证的几何组装器提供物理 A/M/b。
冷热区域的峰值、垂直温差和冷却梯度不能仅靠 coarse node temperatures 判断。
固定参数范围并对完整两种架构重复搜索，避免只为候选寻找最有利的工作点。

接入 Voxel/其他 event trace 与 Ramulator/DRAMPower 或等价已验证的 Bank/Row activity model。
将瞬态热响应与 Mapping/Scheduling/DVFS 闭环联动。
对比 Voxel request grouping、Tasa bandwidth sharing、Helios data placement 的等资源变体。
连接拓扑改变若不能战胜这些软件/已有硬件机制，就不应继续提出专门新 Fabric。

## 第三阶段：有限局部重构硬件

仅当校准后 B 稳定存在，才探索小组内可重构 Memory Service Fabric。
需对综合面积、线长/频率、仲裁延迟、能量、Row locality 和跨区 partial-sum traffic 做收费。
真正 wafer-scale WoW 要独立定义横向距离、跨区域冷却边界与封装结构，
不能从本实验 20×20 mm 芯片参数外推。
