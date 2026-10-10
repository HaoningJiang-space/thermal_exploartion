# Research Go与Hardware Go分别决策

2026-10-10更新。历史实验的工作量、对照、原门槛和负结果保持，不因改变研究定位而重算或重命名收益。

**Research Go**表示已有可解释的发现，值得保留方法、检查机制或选择更合适的目标工作负载。
它不代表发现了新硬件，也不保证必须继续扫描同一参数空间。
**Hardware Go**要求一个明确的结构限制在充分优化已有方法后仍有可观收益，合理参数下稳健，且新增面积、功率、通信与时序成本闭合。

HB相关性、空间热相关性、新机制和净收益分别记录。只有声称“空间热改变最优组织”的研究才必须证明热最优性反转；
研究HB数据消费或通信瓶颈时，Thermal可以是成本与可行性约束，不必是唯一创新来源。
历史G1的自动候选标签、Organization的热反转检查、D2的Tier交互检查都是各自假设的判别，不能升格为通用研究禁令。

| 分支 | 保留的研究发现 | 当前硬件判断与边界 |
|---|---|---|
| G1/G2 Fabric | 布局对照识别了大部分表面连接收益；共享布局损失很小 | 关闭本轮Compute–Memory Fabric；不复开RTL |
| Memory Service Granularity | K16→32供数提高；带宽饱和后面积交换决定计算能力 | 关闭本轮新Peripheral；未支持预设空间热反转假设 |
| D1 Row-cycle | 原11.44%信号可由保留恢复时间的双Subarray代理恢复约92% | 关闭本轮Row-cycle新硬件；代理不等于真实Mono3D的MASA实现 |
| D2输入join | 布局/执行优化提高28.96%；精确到达序列证明消费端尾部极小 | 当前6GiB、T0输入消费单元Hardware No-Go；保留执行归因，重新选择依赖与通信场景 |

D2优化版在最后一个有效字节到达后3 tick完成；固定请求/DRAM/HB序列下，消费端收益上界约0.000307%。
这是针对到达后消费的因果边界，不是对改变数据供应、通信或整个NPU组织的全局上界。
高missing-input比例与低Useful MAC utilization不能单独作为新硬件动机。

下一步是 [H1横向通信需求与割集审计](horizontal_audit.md)：把D2共同理想化的广播、归约和跨Tile交付变成可核对的交通账目。
先识别必须传送与布局造成的流量，再决定是否需要把实际NoC排队接入依赖执行。
不重复6GiB工作量扫描，不预设一定存在Horizontal Wall，不以改变性能门槛替代机制证据。

H1容量上界只能产生Research Signal；没有耦合执行、已知数据流对照和实际硬件成本前，不产生Hardware Go。
后续Attention须包含已有的split-KV、流式softmax/归约和生产者—消费者布局基线；MoE须保存同一token路由与所有专家工作量。
Flash-Decoding已有分区KV局部计算再合并的执行方式，不能把这一步直接当作新的协作单元。
依据：[Flash-Decoding作者说明](https://crfm.stanford.edu/2023/10/12/flashdecoding.html)、
[FlashAttention](https://arxiv.org/abs/2205.14135)、[FlashInfer](https://arxiv.org/abs/2501.01005)。
