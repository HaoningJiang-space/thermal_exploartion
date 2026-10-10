# Stage 1 — Simulator Qualification

H2正式执行已归档，21个完成案例和1个有限时长内未完成的barrier负对照均保留。
本轮复现一个ATLAS官方DRAM Artifact子案例，并对H2/H3使用相同Wide GEMM、布局、工作量及总容量做交叉。
**结果为 PARTIAL QUALIFICATION，不是整个快速模型通过预测验证。**

|执行案例|H2 μs|H3 μs|H3误差|10%目标|
|---|---:|---:|---:|---|
|Row blocked K|30.4855|52.547|+72.37%|FAIL|
|Column blocked M|8.68425|8.91525|+2.66%|PASS|
|2D blocked K|15.39175|21.82275|+41.78%|FAIL|

三例FLOP、DRAM字节、NoC byte-hops、最终输出所有权均一致；每Tile2.25MiB、MAC/HB/SRAM端口和链路峰值相同。
H3补充了永久input/partial/output占用，并将4KiB packet staging计入同一总SRAM预算。
但它不是H2的32B逐flit FIFO：store-forward、请求服务抽象、收发credit和SRAM/MAC阶段仍不同。
因此误差不能视为架构speedup，Column单点通过也不能外推到完整Attention/MoE。
完整账目、阶段窗口、credit probes及SRAM流量差见[crossover.json](crossover.json)。

## ATLAS官方子案例

来源：[ATLAS b278739](https://github.com/pku-gsun/ATLAS-MICRO-2026/tree/b2787399408e32d327c820daee96d4e6610f551a)，
`tests/dram_dse_cloud.py:dse_interleave`和`tests/dram_test.py:test_matrix_access`中的合法矩阵子案例。
M64/K2048/N2048、tM16/tK512/tN128、BF16、OS；input/output row-major，weight非row-major。
保持官方HBDRAM_4Gb_1024pin、16channels、500Mbps时序，只比较官方interleave bit0/7。

|官方子案例|Latency μs|BW GB/s|BW utilization|
|---|---:|---:|---:|
|bit0|101.834|347.628|33.9481%|
|bit0确定性重复|101.834|347.628|33.9481%|
|bit7|78.766|449.437|43.8904%|

bit7相对bit0延迟减少约22.65%，同总接口预算下地址分布显著影响服务效率。
这是上游Artifact的实际软件执行，不是本项目的独立芯片测量，也不是完整ATLAS AE、热学或Stratum复现。
公开Artifact未提供此单点的独立数值golden，所以不报告虚构的“论文误差”。
[原始记录](record.json)、两次相同digest的日志、全部便携配置已保存。

本机Apple Clang/arm64只做编译兼容处理：`-Wno-register`；Ramulator模板成员访问加`template`关键字；
用上游BookSim同一28f43299提交的config.l/config.y重新生成C parser，替代上游携带的Linux archive。
这些不改变时序、控制器、地址映射或测试参数。构建失败日志与成功日志均保留；Linux可优先使用未修改的官方构建。
复现：先按ATLAS README初始化并应用官方RAM/BookSim patches，再构建`test_dram`；
`python scripts/qualify_atlas.py --atlas external/ATLAS --output outputs/atlas-case`（需要PyYAML）。

## 后续使用范围

完整层级模型采用显式有限流式kernel、同一资源预算和完整依赖，修正旧H3串行SRAM/MAC口径，作为Mode B条件性架构筛选。
它没有从上述单点反推经验系数，**尚未取得跨模型预测资格**。通信重场景、强正信号仍需返回H2/ATLAS详细检查。
Stage 2须报告完整参数、容量、路由来源、账目与反事实；Stage 3不因快速模型正收益直接批准新硬件。

另保留旧H3 `18adac9` 在`moe_uniform_b32/sram_ideal_collective`的有限credit调度失败：
该chosen packet policy无可继续执行事件。它不证明物理机器不可能执行，更不代表该Oracle有可实现性能。
旧等待H5的作业已停止；未完成情景不得用已完成FFN/Attention结果补齐。
