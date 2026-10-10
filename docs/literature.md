# 重点文献核对

核对日期：2026-10-09。只把可读取的一手论文作为技术结论依据。
没有进行全领域 novelty 排除；下表没有覆盖到的功能不能据此宣称不存在。

| 工作 | 已核对内容 | 对本实验的约束 |
|---|---|---|
| [Voxel](https://arxiv.org/html/2604.26821v2), §III、IV-C/D | 16 TB/s 配置 row-buffer conflict 占 decode 43.35%；已有相邻 core request tracker。支持详细空间热仿真，论文 DSE 使用已验证的 power-density throttling | 不能把跨 Tile 请求协调或详细热仿真本身当作新贡献 |
| [DeepStack](https://arxiv.org/html/2604.04750), §II-C、IV-A2/3 | Little's Law、transaction/bank 语义及 stacked/connected layers；主要 DSE 使用 `T=Tamb+R(m)P`，`R(m)=0.56+0.01m`，经 ANSYS Fluent 拟合并以 HotSpot 对照 | 要证明空间模型改变组织选择，不能只提高模型精度 |
| [SNAKE](https://arxiv.org/html/2604.04253v2), §6.2 | 重分配 SRAM/compute 面积并重构 SA；24 TB/s 设置，800 MHz，约 62 W Logic budget，HotSpot 热约束 | 避免把减少 SRAM、增加计算或重构 SA 作为本项目差异 |
| [Tasa](https://arxiv.org/html/2508.07252), §IV-C、V | 异构 P/E cores、热分布/floorplan 优化、局部 fat-tree bandwidth sharing、动态 KV placement | 与 Thermal-aware sharing 最直接重叠；需同资源对照，并单独研究物理 service connectivity |
| [Helios](https://arxiv.org/html/2603.04797), §III、V-A、VI-G | 分布式 tiled attention 与 spatially-aware KV block allocation；还讨论 channel-count 下 compute/bandwidth/thermal trade-off | 数据布局和跨 PE 负载均衡必须作为强基线 |
| [DAC 2025 HB-NPU](https://doi.org/10.1109/DAC63849.2025.11132870) | DOI 与出版入口已定位；本次接口未取得正文，centralized controller/dual-I/O 细节仍按用户提供线索待核对 | 不据未读取正文写技术数值或宣称创新空白 |

搜索还返回 SiloBreaker (DOI 10.1109/TCAD.2026.3737060) 的 resource-silo/NoC 相关线索，
但本次没有取得出版方正文，未把二手摘要用于技术结论。进一步 novelty review 应优先获取一手版本。

## 本实验自己的推导

固定工作负载有效数据量为 `B_used=F/I`。若 `P_L=P_L0+epsilon_L F`、
`P_D=P_D0+epsilon_D F/I` 且热响应固定，则

`F <= (DeltaTmax-H_LL P_L0-H_LD P_D0)/(H_LL epsilon_L+H_LD epsilon_D/I)`。

该式不含空闲的接口峰值带宽。增加峰值带宽不会自动降低持续算力；
若同时增加静态/PHY 功率、Bank activity、refresh 或改变访问效率，才需重新计算边界。
这是模型假设下的解析推导，不是对所有 DRAM 工作点的经验结论。

## 历史先例与已知 DRAM 机制

以下已读取一手正文，避免把 HB 场景下的旧思想重新包装为贡献。这里只判断直接重叠，不声称完成全领域 novelty 排除。

| 工作 | 正文定位与核心机制 | 对后续审计的要求 |
|---|---|---|
| [NUCA, ASPLOS 2002](https://www.cs.utexas.edu/~cart/trips/publications/asplos02.pdf) | 非均匀 wire delay；动态迁移数据靠近处理器 | 动态局部性与非均匀访问不是新命题 |
| [Thermal-Aware Memory Mapping, DATE 2009](https://past.date-conference.com/proceedings-archive/2009/DATE09/PDFFILES/10.6_1.PDF) | §II–IV：结合访问频率、层位置、散热条件做静态 3D DRAM 映射 | Thermal-aware data placement 有直接先例 |
| [Performance/Thermal-Aware 3D L2, TODAES 2012](https://ceca.pku.edu.cn/media/lw/736bedbbc7780f63c2bba7b5565ce025.pdf) | 3D cache way placement 与热控制 | 存储组织/性能/热协同并非空白 |
| [Temperature-Aware Runtime Power Management, ISQED 2014](https://si2.epfl.ch/demichel/publications/archive/2014/ISQED2014_Kyungsu_paper.pdf) | Cache partition/gating/data placement 与 per-core DVFS 联合优化 | Mapping/DVFS 必须作为强基线 |
| [Runtime 3-D Stacked Cache Data Management, ISQED 2014](https://www.isqed.org/English/Conference/pdf/ISQED_2014_Best_Paper_1.pdf) | Fig.1、§IV：垂直 local bank、远端 crossbar、共享 TSV 竞争；运行时温度/流量感知 bank placement | 与本项目候选 Memory Service Fabric 直接重叠；SRAM→HB DRAM 不足以证明创新 |
| [Loh, ISCA 2008](https://www.cs.cmu.edu/~18742/papers/Loh2008.pdf) | §IV：利用高密度互连重组内存；§V：改善内存后 L2 miss handling 成为限制 | 同时检查内部 DRAM 组织与 Logic 请求容量 |
| [SALP, ISCA 2012](https://istc-cc.cmu.edu/publications/papers/2012/SALP-isca12.pdf) | §II/IV/V：tRC=tRAS+tRP、shared global structures；SALP-1/2/MASA 放开部分跨 subarray 重叠；MASA 仍需满足 tRRD/tFAW | Subarray 并行不能免费倍增共享 column bus 或 ACT power-domain 带宽 |
| [Stratum, MICRO 2025](https://arxiv.org/html/2510.05245) | §II-A、evaluation：Mono3D staircase WL 造成层间 activation latency 差异，tiering 与 NMP 协同 | 普通 planar DRAM、TSV stacked die 和 Mono3D DRAM 参数不能混用 |

Voxel 已处理相邻核心 row 请求进度，DeepStack 已考虑 partial-row transaction、activation/precharge 和 direct/interleaved bank 连接，SNAKE 沿用 Stratum 并固定有效 24 TB/s。
这些已有机制必须逐个进入后续基线；不能把它们遗漏后得到的收益称为 HB-native 创新。
没有收到/定位到具体 HPCA 2015 标题，不将“HPCA 2015”作为已核对引用。

Compute–Memory Fabric 关闭的直接依据仍是本模型 G1/G2 的不足 5% 收益，历史重叠进一步削弱动机。
HB-native Memory Organization 目前仅进入文献与瓶颈分析，没有已确认的新机制。
