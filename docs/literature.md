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
