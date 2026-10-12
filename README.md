> **October 11 clock audit correction:** Ramulator serializes HBM3 CK into half-CK native ticks. The earlier claim that historical internal runs were twice too fast was incorrect and has been withdrawn. See [the generated-clock evidence and retained slow controls](docs/clock-domain-erratum.md). Historical artifacts remain immutable.

# thermal_exploartion

**Hybrid-Bonded 3D Accelerator Architecture Exploration**

研究主线仅为本仓库的 **Hybrid-Bonded 3D DRAM-on-Logic Architecture**：
真实 Dense/MoE LLM、Compute/Memory/NoC物理组织与Spatial Thermal；计算在logic，不做PIM或Power Delivery。

最新交付为 **[完整MoE因果审计：FIFO修复与物理资格保留](results/p4-complete-moe-2026-10-12/findings.md)**。
完成3个真实完整Expert/竞争场景和2个含Shared的完整MoE前端回归，Native/Fluid各六类trace逐行一致。
但一致的旧前端仍允许FIFO队首绕过：真实竞争记录24,314次；已补实际arrival-order FIFO及独立历史检查。
同一完整B32/TP4/Column程序修复前后Native仍是68.71525μs，402,711个node时间已改变，说明总延迟一致不能证明语义合法。
32KiB registered-reuse law尚无实际M/K、有限Matrix RF容量/端口与partial生命周期证明；Shared B32每tile至少需保留90,112B输出状态。
**完整架构G3/G4与Hardware Go仍未建立。** 原生前端的零误差共享DRAM与抽象builder，不能认证物理架构；批量排序资格矩阵因此暂不运行。
[合同](docs/p4_complete_moe_contract.md)、[逐点审计](results/p4-complete-moe-2026-10-12/execution-audit.json)与
[全部修复/退役原始记录](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-moe-causality-audit-2026-10-12)保留失败和模型边界，没有新NoC/MAC、P4-C或Thermal/微流道DSE。

**上一轮：[P4-B组件校准：同合同执行精度](results/p4-calibration-2026-10-11/findings.md)**。
独立Python有限flit/端口frontend复现所选C++参考合同，不使用记录中的到达时间或延迟拟合。
复用16个归档参考点、新增8个真实1408×2048投影形状Native/Fluid点，完成24个Python执行对照；
绝对10%门24/24、相对5%门6/6通过，最大Native误差2.54%、最大比值误差2.61%。
12个Fluid案例八类完整trace逐行一致，24点完整packet依赖/资源重放和140项回归通过。
退役f4fb4b7实际形状pilot：只绑定packet起始行会漏掉跨22-row块的producer；Cold Row中Native/Fluid分别提前读28/48个packet，最终延迟却不变。
有效ffdbe29重跑依赖全部相交MAC输出块；首次pilot和共享语义错误的原记录完整保留。
**资格只覆盖所选tensor组件合同：完整MoE Graph仍未接入校准frontend，原NoC Oracle与Hardware Go未获新认证。**
单Vector context是参考控制假设，不是物理必然性；没有新scheduler/network、DSE、RTL或Thermal扫描。
[合同](docs/p4_component_calibration.md)、[资格](results/p4-calibration-2026-10-11/qualification.json)、
[复现](results/p4-calibration-2026-10-11/reproduce.md)与
[原始记录](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-component-calibration-2026-10-11)明确独立实现与共享模型假设的边界。

**上一轮：[P4-B：细粒度资源占用与关键路径验证](results/p4-fine-2026-10-11/findings.md)**。
48个原始Qwen路由性能点、16个Native/Fluid组件点、48次小张量数值比较完成；
48点独立资源/事件重放、10个P4-A精确回归及134项测试通过。
TP16 row-down仅改变预留粒度的模型内延迟减少B8/B32为8.03%/6.33%；联合NoC诊断增益仍为27.27%/29.23%。
**原生时间资格未通过**：绝对10%门槛10/16（Native-only5/8），相对5%门槛1/4，完整MoE独立精度未建立。
保留所有精度失败与零实验点的launcher失败；不据此进入新NoC/MAC或P4-C硬件设计，先校准同合同执行。
[冻结合同](docs/p4_fine_execution_contract.md)、[审计](results/p4-fine-2026-10-11/audit.json)、
[原生资格](results/p4-fine-2026-10-11/component-qualification.json)、[复现](results/p4-fine-2026-10-11/reproduce.md)与
[完整原始记录](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-fine-execution-2026-10-11)分别保留资源正确性和时间精度边界。
本轮没有新scheduler/network、DSE、RTL或thermal扫描。

**上一轮：[P4-A：通信语义与有界 Row-ready Reduction](results/p4-communication-2026-10-11/findings.md)**。
336个真实路由性能点、48个小张量数值对照、64个进程全部完成；所有性能点通过独立事件/资源重放，28个旧案例精确重放。
固定Shared权重布局下，Destination-only仍需覆盖全部16个Tile；独立Shared/Routed交付的重复通信全部付费。
保留输入复用的128-row Row-ready在相同64KiB输出空间内取得1.0243×主案例、1.0209×验证案例几何平均加速。
TP16 row-down的B8/B32 NoC诊断收益降至30.37%/30.84%，仍不能当作新硬件机会；Joint Kernel解耦留给P4-B。
[冻结合同](docs/p4_communication_contract.md)、[审计](results/p4-communication-2026-10-11/audit.json)、
[复现](results/p4-communication-2026-10-11/reproduce.md)和
[完整原始记录](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/p4-communication-2026-10-11)均保留负结果。

**上一轮：[P0–P3：真实路由下的传统 MoE 执行边界](results/expert-execution-2026-10-11/findings.md)**。
P0原生/Fluid共享前端36点完成，18个绝对延迟对照最大误差2.80%；它只验证Memory abstraction，未独立认证完整H3。
P1全部128步确认64-row软件累加能修复152TF/18MiB的Qwen B32调度失败。
P2完成EP/TP4/TP16/固定Hybrid、已付费local token fusion、冻结row-down权重布局；
P3在最强已测barrier/static策略下补齐DRAM-only与HB+ingress联合对照，保留有限容量与相同计算/权重字节。
TP16 row-down的B8/B32理想Memory余量仅约8%/2%，NoC约32%；B32的MAC余量约58%，这些仍是未付费oracle。
本轮3336个完整记录（3334成功、2个预期cohort失败）、1289个退役模型/调度控制和122项回归均有审计与归档。
[合同](docs/expert_execution_gate.md)、[逐点摘要/判决](results/expert-execution-2026-10-11/decision-summary.json)、
[复现入口](results/expert-execution-2026-10-11/reproduce.md)与
[完整原始记录](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/expert-execution-2026-10-11)可独立核对。
Research Go保持；尚无新Hardware Go。本轮没有新增RTL或thermal扫描，也没有将MoE子图延迟称作完整Serving吞吐。

**上一轮冻结记录：[Compute–Memory–Communication Architecture Crossover](results/crossover-2026-10-11/findings.md)。**
十组完整模型场景跨越供数与计算Roofline，保留275个点（185个成功、90个有限调度/面积失败）、
原始Qwen1.5路由、分项Memory/NoC反事实和固定121mm²面积前沿。
152TF/18MiB在条件性模型内使Llama B16提高12.92%、Qwen B16提高7.06%；35.25mm²未识别面积没有被使用。
19个默认热评价点均无需降速，最高周期Logic温度65.81°C。
113项回归通过；但大Batch交叉验证最大误差19.86%仍未达标，不能据此宣布新硬件预测合格。
[本轮合同](docs/crossover_architecture.md)、[复现说明](results/crossover-2026-10-11/reproduce.md)及
[完整公开原始数据](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/crossover-execution-2026-10-11)分别记录假设、控制和失败。
Research Go保持；尚无新Hardware Go，不推进RTL。

**历史冻结记录：Stage 1–4（849c796）**

该轮里程碑为 **Simulator Qualification → Architecture Characterization → 条件性 Architecture Discovery → Thermal Evaluation**。
任务与证据边界见 [Stage 1–4 实验合同](docs/stage1_stage4.md)。
**[Stage 1–4 正式报告、全部结果与图表](results/stages-2026-10-10/findings.md)已完成并归档。**
H2–H3三个同合同案例误差均在10%内；实际复现一个ATLAS官方AE子案例。
六组完整模型结构化Decode各128步，60个执行对照、135个事件热评价点均保留。
默认最强已有方案约1544–8552模型tokens/s；这是合理假设下的结构化执行率，不是实测Serving吞吐。
Qwen路由为有标签的公开Qwen2投影，8192之后的128步明确采用Context扩展假设。
Stage 3未批准新硬件：已知输入复用、头分组KV与有限流式供数解释主要收益，不重启Fabric、Peripheral或Row-cycle RTL。
原始事件和逐文件摘要见[公开Release](https://github.com/HaoningJiang-space/thermal_exploartion/releases/tag/stages-execution-2026-10-10)。
[H2 正式结果](results/h2-2026-10-10/findings.md) 已归档：优化列切分模型吞吐124.23TFLOP/s，
相对128TFLOP/s计算上限的剩余收益不超过3.04%，不支持孤立Wide GEMM的新硬件。
旧H3的FFN/Attention/MoE合成子图保留为机制记录；本轮完整模型使用独立的层级执行器，不能混用两者的Token率。

**研究决策：Compute–Memory Fabric 分支正式关闭；Thermal-aware Mapping 保留为基线。**
已完成 [D1/D2判别实验](docs/d1_d2.md)：关闭已知Row-cycle信号，再检验多Tier数据返回与任务依赖。
不扩大Peripheral DSE；[Mode B 架构探索](docs/architecture_exploration.md)允许明确、相互一致的假设。
采用 [Stratum-inspired、带来源与假设区间的配置](configs/exploration/hb_npu_v1.json)。
Mode A 严格复现与 Mode B 条件性探索分别管理；尚未校准的器件参数不再禁止全部架构探索。

[Memory Service Granularity 结果与两张图](results/organization-2026-10-10/findings.md) 已完成。
默认 Shared-area 下 GEMM偏好K16、Mixed偏好K32，GEMV在K≥32供数基本饱和。
20个有限情景未发现T1_layer→T2的显著最优组织反转；行周期理想放松约11.44%收益在T0/T2相同。
因此不推进新的Peripheral组织或RTL，先把该信号留给SALP/FGDRAM等已有机制对照。

[D1结果](results/d1-2026-10-10/findings.md)已完成：保留30ns行恢复的双Subarray重叠代理恢复旧Oracle增量约92%，
Oracle相对该代理剩余仅0.83%。Row-cycle新硬件分支关闭；并修正命令驱动ACT/PRE能耗接口。
[D2结果](results/d2-2026-10-10/findings.md)使用实际访问的5GiB权重+1GiB KV，比较相同硬件上的普通双缓冲、优化执行与更细粒度流式探针。
布局/执行优化提高28.96%，更细消费相对优化版只有约0.000205%增益，等延迟负对照相同量级。
优化版距离固定到达序列的完成下界只有3 tick；仅改变消费端的收益上界约0.000307%。
当前受控任务模型的 **Hardware No-Go** 限于新的输入消费单元；**Research Go** 保留执行归因方法，转向依赖更强的工作负载选择。
判断规则与各分支范围见 [Research Go / Hardware Go](docs/research_decisions.md)。Thermal最优性反转只约束声称该机制的研究。
这些不是完整SALP或Stratum器件复现，独立功率校准仍未完成。

[H1横向通信审计](results/horizontal-2026-10-10/findings.md)已完成Broadcast/Reduction/Redistribution/All-to-all交通与逐方向割集账目。
宽矩阵Batch32的固定行切分容量上界为43.69TFLOP/s，已有列切分上界回到128TFLOP/s，byte-hop减少87.5%。
这是条件性容量证据，不是实测speedup；支持继续通信/依赖研究，尚未评估新硬件Go。
全部切分与负结果保留，不以无限NoC作为付费实现，不将chip-scale算术例子当作wafer-scale验证。

新任务书与不可校准项见 [Grounded HB–DRAM Validation](docs/grounded_validation.md)。
[Stratum Hardware Contract](configs/platforms/stratum_micro2025.json) 与旧 pilot 完全隔离，未知值保持 null。
G1、G2、Memory Audit 已共用 DRAM Service Model；现有解析扫描保留作历史证据。

[G3 +最小 G4 结果](results/grounded-2026-10-09/findings.md) 已完成：48 项服务一致性检查、
128 项官方 HBM3 测试、5 个有限轨迹/负向控制。18704 请求与 23580 命令核查通过。
Stratum Logic 功率组成仍有 6.51% 未解释差异，HB/cooling 和命令域未知；完整器件复现仍 NOT READY。
104.13 W 是同一论文的参考账目一致性，不能视为独立功率验证。本轮不会通过调参消除这些差异。

原研究目标是检验空间热耦合是否改变 Compute–Memory 物理连接的最优性。
先做可证伪的小实验，结果允许支持 Local，也允许说明收益主要来自普通负载均衡。

首轮已完成 2340 个设计点、7020 个 LP：重新优化数据放置后，默认 GEMM 的理想连接收益
从约 16.44% 缩至 2.54%，加入 Fabric 开销后的净收益仅约 0.22%。
在本次扫描范围内，未得到足够强的 B 证据。
完整解读和图表见 [首轮实验报告](results/2026-10-09/findings.md)。

历史 G1/G2 pilot 是 **chip-scale、未校准、稳态上界筛选模型**：20×20 mm 的 Logic/DRAM/spreader，
16 Compute Tiles + 16 Bank Groups，Batch-1 GEMV 与 Batch-32 GEMM。
它不是完整 Transformer 仿真器，也不是 wafer-scale 的 WoW 性能模型。

## 运行

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m thermal_exploration.run --output outputs/pilot-scipy
```

HiTS 路径采用其公开 `HiTS` API 的 CPU GMRES，独立比较每个单位功率响应与 SciPy direct solve，
同时检查原方程残差。32 个有源区域分别激励，得到完整空间响应矩阵 H。
HiTS 是求解器；本项目负责几何、边界条件和物理方程的组装。通过残差检查不等于物理参数已校准。

```bash
git clone https://github.com/HaoningJiang-space/HiTS.git external/HiTS
git -C external/HiTS checkout c7f94d533cb663c2f098880e5ab333da9d83ff17
PYTHONPATH="$PWD/external/HiTS${PYTHONPATH:+:$PYTHONPATH}" \
  python -m thermal_exploration.run --thermal-backend hits --output outputs/pilot-hits
PYTHONPATH="$PWD/external/HiTS${PYTHONPATH:+:$PYTHONPATH}" \
  python -m thermal_exploration.run --thermal-backend hits --suite sensitivity \
  --output outputs/sensitivity-hits
```

HiTS 是单独管理的依赖，使用上述路径需要该仓库的访问权限；公开的本项目默认 SciPy 路径可独立运行。
HiTS 的 GPU 路径有额外安装与资格要求，见其 README。小型 CPU 路径不需要构建 native CUDA kernels。
所有输出目录必须是新目录，避免覆盖旧实验。

## 对照矩阵

每种工作负载 × 4 个热条件 × 5 个连接选项 × 2 个数据放置选项，分别重新优化。
pilot 包含均匀分布、中心负载偏斜、冷却梯度三个场景，修正版总计 240 个设计点；
每个设计点枚举相同的 3 个访存 chunk/row-miss 选项，内部求解 720 个 LP。

| 维度 | 选项 |
|---|---|
| Thermal-0 | 无温度约束；仍保持计算、Bank、请求队列和链路限制 |
| Thermal-1 scalar（旧对照） | 单一全局 R，丢失两层差异，仅保留用于复现 |
| Thermal-1 layer（新增） | 同一 H 的 2×2 层平均热阻，保留两层功率来源和独立温度限制，移除横向位置 |
| Thermal-2 | Logic 和 DRAM 各区域均约束 `T = Tamb + H P` |
| Local | Compute i 只由 Bank Group i 服务 |
| Neighbor ideal | 理想零开销，相邻 Manhattan distance ≤1 可访问 |
| Global ideal | 理想零开销，全局服务，上界 |
| Mesh paid | XY 路由；有限链路带宽、逐跳延迟、链路能量、面积与静态功率 |
| Local matched | 与 Mesh paid 相同的路由面积及静态功率预算，关闭远端服务 |
| Fixed placement | 固定 Bank demand，检验对数据布局敏感的收益 |
| Free placement | 每个方案重新优化静态 Bank 数据份额，含相同容量份额上限 |

Mesh paid 与 Local matched 比较，使计算资源、SRAM、Bank、预留面积预算一致。
Mesh paid 与原始 Local 的比较另行保留，便于判断净收益是否足够支付新增硬件。
SRAM、Compute 总量、Controller 数量和请求跟踪能力不进行资源池化。
DVFS 离散点允许连续时间共享，因此这个 LP 是稳态调度的放松上界。

## 观察与停止条件

`summary.json` 记录 T0/T1_scalar/T1_layer/T2 speedup，空间交互使用 `speedup_T2 / speedup_T1_layer`，以及
Resource Ownership Loss 和 Local Spatial Penalty。比值交互不等于唯一的因果损失分解。
均匀模型是负对照：没有负载差异和冷却差异时应当观察不到凭空产生的理想共享收益。

- 理想连接在 Free placement 后仍没有收益：停止该配置的连接结构探索。
- 收益只在 Fixed placement 存在：优先研究 Mapping/data placement。
- 理想连接有效，付费连接失效：停止该开销区间的硬件方案。
- `fixed_placement_signal` 仅表示固定布局收益；`ideal_upper_bound_signal` 不包含真实连接开销。
- `architecture_candidate` 要求完整布局对照、优化布局、付费成本、T2 净收益及匹配收益均超过 5%，
  T0/T1_layer 净收益不超过 1%，T2/T1_layer 交互超过 1%；仍需执行与物理校准。

上述自动标签是历史G1的**空间热连接最优性反转**假设筛选，保持原门槛以便复现；不是所有HB研究的通用准入条件。

敏感性套件逐项扫描热耦合、冷却梯度、DRAM 能量、链路带宽/能量及面积。
不挑选最佳参数，不删除负结果。全部原始证据保存在输出目录，精选结果见 `results/`。

研究设计：[docs/research_plan.md](docs/research_plan.md)；
文献核对：[docs/literature.md](docs/literature.md)；
模型方程与局限：[docs/model.md](docs/model.md)。

第二轮只验证 [G2 Shared Data Placement](docs/g2_design.md)。保持同一权重 tensor 的共同容量，
固定 Prefill/Decode 工作量，对照独立布局 oracle、共同常驻布局与双向迁移计费。
运行 `python -m thermal_exploration.run_g2 --output outputs/g2`。

G2 已完成：648 个设计点、864 个 LP。当前模型中，Shared 布局下理想 Global 的周期净收益上界
最高约 2.97%，付费 Mesh 最高约 0.71%；共同布局相对独立 Oracle 的最大时间损失约 1.23%。
未通过 5% 门槛，因此结束本轮 Compute–Memory Fabric 分支，不推进 RTL。
详见 [G2 结果与证据](results/g2-2026-10-09/findings.md)。

P1 审计修正见 [docs/audit_p1.md](docs/audit_p1.md)。旧归档保留原始标量 T1 和旧标签，不能据此归因水平空间热机制。

新阶段设计与运行：[HB–DRAM 内部必要上限审计](docs/memory_audit.md)。

已完成 [P1 修正与逐点复现](results/audit-p1-2026-10-09/findings.md)：旧数值保持一致，58 个旧 B_candidate 全为固定布局信号，修正后 Gate 通过数为 0。

[HB–DRAM 小型必要上限审计](results/memory-audit-2026-10-09/findings.md) 已完成 192 点、384 个 LP，35 项回归通过。
满行/充分 Bank 并行的示例主要受热预算限制；小粒度示例受已知 ACT/PRE/domain 速率限制。
这些是未校准的解析上限，尚未发现普通 Mapping/Tracker/SALP 之后仍未解决的 HB 特有瓶颈。

## 工作区迁移档案

[W2W cold服务记录](results/w2w-cold-service-2026-10-11/findings.md)仅保留为先前迁移的外部机器档案；
其硬件合同与本项目不同，不参与thermal_exploartion主线的实验、图表、性能结论或架构判决。
迁移审计见[档案复现说明](results/w2w-cold-service-2026-10-11/reproduce.md)。
