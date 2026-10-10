# thermal_exploartion

**When Does Compute–Memory Locality Become Suboptimal in Hybrid-Bonded 3D Accelerators?**

**研究决策：Compute–Memory Fabric 分支正式关闭；Thermal-aware Mapping 保留为基线。**
当前只执行 G3 Reference Machine 与最小 G4 命令验证，不预设新架构。G5–G7 尚未启动。

新任务书与不可校准项见 [Grounded HB–DRAM Validation](docs/grounded_validation.md)。
[Stratum Hardware Contract](configs/platforms/stratum_micro2025.json) 与旧 pilot 完全隔离，未知值保持 null。
G1、G2、Memory Audit 已共用 DRAM Service Model；现有解析扫描保留作历史证据。

原研究目标是检验空间热耦合是否改变 Compute–Memory 物理连接的最优性。
先做可证伪的小实验，结果允许支持 Local，也允许说明收益主要来自普通负载均衡。

首轮已完成 2340 个设计点、7020 个 LP：重新优化数据放置后，默认 GEMM 的理想连接收益
从约 16.44% 缩至 2.54%，加入 Fabric 开销后的净收益仅约 0.22%。
在本次扫描范围内，未得到足够强的 B 证据。
完整解读和图表见 [首轮实验报告](results/2026-10-09/findings.md)。

当前实现是 **chip-scale、未校准、稳态上界筛选模型**：20×20 mm 的 Logic/DRAM/spreader，
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
