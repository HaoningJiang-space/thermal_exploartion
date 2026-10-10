# H1：横向通信需求与割集审计

本轮是Mode B、chip-scale的必要容量筛选，不是新NoC设计，也不是完整NoC排队/依赖模拟。
D2的输入广播、跨Tile归约共同理想化；H1首先补齐这些交通的来源与逐链路账目。

## 固定边界

4×4 Tiles、121mm²、128TFLOP/s、32GiB与36MiB SRAM；K32不再变化。
本地权重读取，不恢复跨Tile Memory Fabric。16个本地服务区域共享同一架构预算。
每条Mesh邻接链路两个方向独立，各32B/cycle、1GHz，即32GB/s/direction。
16/64GB/s仅为预先声明的容量敏感性，不能宣称免费增加布线/Router就实现了这些硬件。
NoC预留面积3mm²是工程假设，放在参考76.55mm²之外，总79.55mm²≤121mm²；不宣称综合闭合。

HB为1/4/16/32TB/s的带宽隔离反事实。DRAM服务上限固定采用已归档D1 baseline的26.599TB/s，
它是该内部时序代理的full-row观测，不是Stratum实测，也不保证所有算子能达到。
把该观测值冻结为本轮供数cap是一项额外架构假设，不是证明它约束了所有可能的Controller/轨迹。
本轮算子权重≤1GiB，可放入4GiB fast Tier；不据此讨论全32GiB或多Tier性能。
算子上界用`min(HB, D1 service)`，没有新的Ramulator运行，也没有删除ACT/PRE时间。
额外输入HB交通、SRAM端口、Router拥塞与关键路径未闭环，因此结果只报告乐观上界与通信需求。

## 张量与四种交通

FP16 GEMV/GEMM：`y = W x`，输入和最终输出都按连续元素均匀驻留16Tiles，权重本地分片。
使用square(4096×4096)、wide(1024×16384)、tall(16384×1024)，batch1/32；每种都是同一32MiB权重规模。
输入分片通过Broadcast到需要它的计算区域；部分输出按FP32归约，最后FP16输出落到相同约定的所有者。
不能忽略最终输出归属，使row/column对照不公平。所有方案完成相同`2mn×batch`MAC FLOP。
归约额外加法单独计入各Tile的64Gadd/s假设向量资源，不以免费路由器加法代替计算。

Redistribution是4096×32 FP16 tensor从row-block转column-block的完整置换；
它是受控布局转换，不冒充一个完整Attention执行。包含生产者/消费者布局对齐后不需要转换的对照。
MoE是256个4096维FP16 tokens、top2、16个固定专家、两个4096×4096线性投影。
确定性的均衡路由用于受控cohort：dispatch和combine均逐token展开，不能只统计其中一个方向。
所有512个expert assignments保留；权重共1GiB、计算32GiFLOP。
这不代表实际router概率、SwiGLU或端到端LLM serving。

## 三种理想对照与已有方法

1. **Infinite horizontal capacity**：只移除链路容量时间；交通与向量归约工作量仍记录，不作为付费硬件。
2. **Zero Broadcast/Reduction transport**：只移除这两类链路时间；保留Redistribution/All-to-all和所有归约加法。
3. **Ownership control**：枚举1×16、2×8、4×4、8×2、16×1矩阵切分、两个物理排列和XY/YX树。
   权重布局可静态优化，输入/最终输出驻留约定不变，未新增资源。
   这是有限集合中最佳的已知数据流对照，**不是任意所有权优化的严格全局上界**。
   容量等效时优先较少byte-hop，再优先较少向量加法，不把任意相同上界的首个设计当作唯一最优。
   Redistribution另理想化让初始DRAM tensor已按消费端布局驻留，最终输出归属不变；
   若tensor必须由前一算子的固定布局产生，这项初始条件就不免费可得，必须接入生产者后收费。
   MoE只允许16种静态循环expert placement，不改变路由。

树边只记录一次广播，反向树在计算Tile上逐级合并；没有用逐目标unicast高估已知collective流量。
容量条件为`time ≥ max(local DRAM/HB time, MAC time, per-Tile vector time, per-directed-link bytes/rate)`。
中心x/y割集分别报告两个方向的字节量和容量，不能把全双工两方向的容量混用。
不同限制可同时成立，不能把“瓶颈百分比”简单相加。有限搜索和两个理想交通松弛分别报告。

## Go/No-Go

只将某些合理容量下的逐链路/割集需求大于HB与Compute时间标为Research Signal。
若已知分块、树方向或二维切分即可消除，归为已知执行组织问题，保留负结果。
若优化后仍有明显余量，再接入带任务依赖、有限SRAM、NoC排队及收发反压的执行验证。
本轮不产生Hardware Go；不以容量上界之比当作实测speedup，不用削弱普通基线来创造动机。
Thermal保留为后续成本/可行性条件，不要求本轮出现热反转，不开始G5闭环。

面积注入∝面积、割集容量∝宽度只在固定资源密度和布线条件下成立。
代码附带4/8/16边长网格的假设扩展示例，不把它称为真实wafer-scale可制造配置。
研究真正的wafer-scale时须另给长线/reticle/冷却边界，不能扩放121mm²封装参数。

已有对照依据：[WaferLLM](https://www.usenix.org/conference/osdi25/presentation/he)的MeshGEMM/MeshGEMV、
[Eyeriss v2](https://arxiv.org/abs/1807.07928)的层次化网络与数据复用、
[Voxel](https://arxiv.org/html/2604.26821v2)的映射与NoC联合研究。
这些是机制/方法参考，本轮未复现或声称击败上述完整系统。

运行：`python -m thermal_exploration.run_horizontal --output <fresh-output>`。
