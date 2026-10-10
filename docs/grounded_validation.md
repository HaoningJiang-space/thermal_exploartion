# Grounded HB–DRAM Bottleneck Validation

本轮只执行 G3 Reference Machine 和最小 G4 Execution Validation。Fabric 已关闭；G5–G7 均有进入条件。

## 冻结参考系统

[Hardware Contract](../configs/platforms/stratum_micro2025.json) 独立保存
[Stratum v1](https://arxiv.org/html/2510.05245v1) 的 Table 1（PDF p.10）、Table 3 / Figure 15（p.11）及 Figure 13。
数值采用 `Paper-reported` / `Derived` / `Unknown` 分类，逐参数记录出处；语义说明另标 Metadata。
不继承 pilot、SNAKE 或 Voxel。MAC/ALU 在 bonded Logic，DRAM 不执行计算。

16 channels ×16 banks 共 256 banks；8 timing tiers 分割各 bank 的行，不能乘成 2048 banks。
1024 physical wordline layers 不是 8 片常规 DRAM die。
MAT 拓扑推导 32 GiB、4 KiB row buffer；论文的 GB/KB 标签另存，不把二进制容量当十进制。
16 PU ×16 PE ×16×16 MAC，1 GHz，拓扑算力 131.072 TFLOP/s；论文 rounded 128 TFLOP/s 保留，两者相差 2.4%。
36 MiB SRAM 不重复计入 2 MiB row-swap RF。

八个 tRCD、tRAS=tRCD+27.50 ns、tRP=4.77 ns 可复现正文 19.01–30.34 TB/s 的
bank-cycle 必要上界。Table 3 的 34.34 TB/s 与正文不一致，保留两个值。
没有给 tRRD/tFAW/tCCD、ACT/column domain、subarray/address mapping、refresh 补填普通 DDR/HBM 时序。
因此不能称这些上界为实际可达带宽。

## 功率、面积与冷却

0.429 pJ/bit ×8 ×30.34 TB/s =104.12688 W，复现约 104 W aggregate DRAM 工作点。
它不识别命令级 ACT/PRE/RD/refresh/background 系数，不能再叠加完整 ACT/PRE 费用。
正文 stack 144.53 W − Logic 42.67 W =101.86 W；这个较详细值与近似 104 W 分开比较。

128 TFLOP/s /2 ×0.604 pJ/MAC =38.656 W。加 Figure 15 的 memory/communication group
6.79291 W 得 45.44891 W，比正文 Logic 42.67 W 高 6.51%，超过冻结的 5% 门槛。
这是 activity/统计范围尚未对齐的核查，不能据此断言论文错误，也不能调整未知能量来强行闭合。
Figure 15 的 compute group 与同一峰值 MAC 能量估计也不完全相同。
SRAM、NoC、controller、PHY、leakage 的独立系数仍为 null。

面积仅将层次结构的叶项相加：76.55 mm² 对报告 76.63 mm²，差 −0.104%。
combined router/reducer/SFE group 不假装拆成已知 NoC/controller/vector 面积。
低压 DRAM peripheral 位于 bonded Logic，HV decoder 位于 CUA；aggregate DRAM 功率无法完整分配到热节点。

旧 pilot 的 top-only cooling 必要上限是 96 W；16 TB/s ×12 pJ/B 已需 192 W。
因此旧配置在达到 16 TB/s 前必然节流，不能据此声称现实 HB 系统必然 Thermal-bound。
Stratum 封装几何、HB 面积热阻、完整 cooling boundary 和 tier-resolved 热源均未校准。
本轮不沿用旧 cooling 生成 Stratum 温度或持续性能。

## HB 与外部接口

内部 HB contract 要求数据/控制/供电连接、每连接速率、pad pitch、I/O 面积、功率及 peripheral-port 对应关系。
`B=N_data×R_connection/8` 只给必要数据速率，不能单独证明可制造性。
缺失量保留 null；带宽独立变化只能标为 bandwidth-only counterfactual。
1024 external DQ bits ×6.4 Gb/s /8 =0.8192 TB/s 是 xPU/interposer 路径，不能当作内部 HB 上限。

## 最小执行验证

Ramulator 固定到 [c6c7a5d](https://github.com/CMU-SAFARI/ramulator2/tree/c6c7a5de0cef35935d6fad7369e6271406798865)。
标准 HBM3 是独立集成对照，不能只替换 tRCD 就宣称实现 Stratum Mono3D。
上游 HBM3 preset 中标为 Guesstimate 的时序继续标为上游假设；通过测试不等于器件实测验证。
首先运行官方 device/controller/latency-throughput 测试，再运行 streaming、row-conflict 和一个 GEMV 地址轨迹。
逐请求保存接受、完成、消费时间，独立重放 issued commands 核查状态和时序。
完成数、字节、依赖及工作量必须守恒。

周期观察与反事实控制分别报告；不把重叠的 ACT/column/controller/consumer 限制百分比直接相加。
独立重放指独立状态实例，仍复用同一器件定义；不是第二个独立器件模型的交叉验证。

## Gate 与停止条件

| Gate | 验收与进入条件 |
|---|---|
| G3 | 结构来源匹配；完整工作点功率偏差 ≤5%；未知项不强行拟合；物理 HB/cooling 合同完整才能预测 |
| G4 | 所发命令合法；请求/工作量守恒；标准配置与官方对应测试一致；解析上界作用域一致 |
| G5 | G3/G4 通过后再执行功率–HiTS–执行反馈；T0/T1_layer/T2 和瞬态步长/网格收敛 |
| G6 | 先排除 mapping/scheduling/SALP/FGDRAM；理想单项物理修改约 ≥10% 且具有 HB、空间热交互证据 |
| G7 | G6 通过后设计；相同容量、面积、计算预算；真实成本后稳定净持续收益 >5% |

相关已知机制必须包含 [SALP](https://istc-cc.cmu.edu/publications/papers/2012/SALP-isca12.pdf)、
[FGDRAM](https://research.nvidia.com/publication/2017-10_fine-grained-dram-energy-efficient-dram-extreme-bandwidth-systems)、
[DreamRAM](https://arxiv.org/abs/2512.12106)、Stratum、Voxel、DeepStack。
FGDRAM 已重组 grains/local I/O；DreamRAM 已覆盖 partial-page、subarray、bank 与 routing 的 DSE。
普通 DRAM 并行化或模型搜索本身不能算新的 HB 架构贡献。

本轮决策允许 No-Go。标准 HBM3 集成通过仍不足以回答 Stratum 的现实主瓶颈；没有校准数据时保留未知，停在验证 Gate。

## 运行

```bash
python -m unittest discover -s tests -v
python -m thermal_exploration.calibrate --output outputs/g3-reference
```

共享服务的 48 项 G1/G2 单阶段退化检查在旧筛选机器上完成，仅用于入口一致性回归，不作为 Stratum 校准。
