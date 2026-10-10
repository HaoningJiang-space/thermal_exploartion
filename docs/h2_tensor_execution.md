# H2 — Physically Constrained Tensor Execution

H2-A：1024×16384 FP16 W，batch32，16本地Compute/Bank服务区域，128TFLOP/s，4×4 Mesh，
每方向32GB/s，36MiB私有SRAM。H3随后使用FFN、Attention与MoE的强基线。
H1的43.69/128TFLOP/s为容量上界；H2记录实际任务/请求/数据流完成时间，不复用统一26.599TB/s服务cap。

## 预设软件对照

Row(16×1)、Column(1×16)、2D(4×4)均允许blocked packing、m/k-major循环和就绪调度。
另比较bank-swizzled row-major、Column padded-row、不流式的归约屏障、8KiB权重缓冲和64B归约packet。
所有失败、负结果与拒绝点保留；屏障/小缓冲不是“优化传统NPU”的最终基线。
输出维度为m、输入维度为n，不能直接与Megatron的`Y=XW` Row/Column名字混用。
H2-B将使用Megatron式上投影输出分片→下投影输入分片配对，不能人为制造中间转置。
依据：[Megatron-LM §3](https://arxiv.org/html/1909.08053v4)、[NVIDIA说明](https://research.nvidia.com/labs/adlr/MegatronLM/)。

## 共同执行假设

延用冻结Ramulator内部宽端口时序代理；256 Banks、K32、4KiB Row，实际ACT/PRE/READ/Refresh。
权重32MiB驻留fast Tier，所有计算在Logic；不模拟PIM或Power Delivery。
每个逻辑W分片逐字节映射到1024B物理事务，blocked与row-major可采用不同Packing。
Bank XOR swizzle是公开的工程映射假设，逐地址验证无alias与容量守恒；padded-row占用额外容量但不复制有效权重。
预取缓存512KiB/Tile、在途/返回credit64KiB、归约缓冲64KiB、metadata预留64KiB，计入2.25MiB私有SRAM。
输入始终是16个相同的连续canonical shards；最终FP16输出同样canonical，不免费省掉输出归约。

Mesh采用32B flit、每link四个0.25ns tick可发一flit，hop延迟8ticks含序列化。
每input-port/virtual-network FIFO八flits；输入multicast与归约两个虚拟网络共同分享物理link。
Router multicast能力是所有方案共同的NoC假设，不作为新硬件。反向树归约实际在Tile向量单元执行。
256B归约packet等待必要child/local partial，读取→加法→写回后传给parent；允许不同packet与MAC流水重叠。
部分和FP32；根节点最终转换FP16同样收费。

MAC 2000FLOP/tick/Tile、向量16ops/tick、SRAM读256B/tick与写128B/tick均为合理的架构假设，非器件校准。
每tick端口额度在MAC、向量、NoC注入/接收及HB写回之间实际仲裁；容量与credit不足则停顿。
HB32TB/s，传输须等待真实DRAM返回和SRAM写端口。请求发出前预留返回credit，因此不使用无限返回队列。
Ideal transport只去掉网络传送时间，仍保留SRAM端口、缓冲和向量归约；它不是付费硬件。
Ideal memory保留所有请求/字节，假设一个tick后返回，仍计HB交付与SRAM写；不验证被绕过的DRAM命令性能。
Ideal buffer将private存储容量与预取window放大到足以容纳本算子，保留端口、链路、路由FIFO、MAC与Vector成本。
这些反事实分别放松不同边界，收益不可相加；额外存储不属于相同面积的可实现设计。

只验证执行/通信/字节/FLOP因果链，不执行实际浮点矩阵值，不声称精确复现Stratum器件。
T0首先辨别执行损失；不启动G5热反馈或以热反转作为通用Gate。

## 验收

每个物理请求ID对应合法Column命令和唯一返回；所有权重字节使用一次，允许事务在多个K-block中复用。
任务开始必须在input flits、weight SRAM写回与前一部分和完成之后；归约必须保留全部贡献。
逐link传送满足方向/序列化/FIFO约束；MAC/Vector/SRAM服务不超预算，最终返回同一全部输出。
记录重叠阶段窗口与互斥MAC空闲状态，不把DRAM/NoC/Compute/Reduction时间直接相加。
报告Packing/循环/Streaming分别恢复多少，剩余信号不能直接命名为HB特有瓶颈。
只有充分优化已有机制后的剩余损失，才决定是否值得进一步寻找新硬件。
