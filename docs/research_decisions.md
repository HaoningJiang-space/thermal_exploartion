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

## 2026-10-11 — Architecture Crossover gate

本轮交付见[正式报告](../results/crossover-2026-10-11/findings.md)。
跨越4.812FLOP/B参考交叉点，新增Llama B8/B16与Qwen B16/B32；原始Qwen1.5受控FP32路由替换主实验的Qwen2投影。
185个成功执行点各128步，90个有限调度/面积失败全部保留。固定121mm²账目将35.25mm²未知面积冻结不可用。
MAC与Matrix RF一起缩放、Row-swap RF固定；152TF/18MiB的模型内Llama B16/Qwen B16收益为12.92%/7.06%。
Qwen B32的小SRAM失败属于所测调度的工作空间边界，不能当成硬件不可行证明。
默认19个热评价点最高65.81°C，Thermal不构成新架构核心动机。

Research Go：保留资源交叉与NoC–执行交互证据。
Hardware Go：未建立。当前结果不证明HB特有的新结构，也尚未排除更强的EP/TP和合法流式执行。
跨精度最大延迟误差19.86%与11.34%未被掩盖；普通软件边界应先在详细执行中验证。
已关闭的Fabric、Peripheral、Row-cycle硬件分支保持关闭，不以本轮正收益重启它们，也不否定整个HB方向。

本轮初始“历史时钟快一倍”的审计判断已撤回：上游序列化将0.5ns CK变成0.25ns原生半周期。
旧换算正确；新错误二分频及其衍生低service-guard模型归为retired controls。历史发布记录不改动。
