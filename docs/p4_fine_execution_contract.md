# P4-B：细粒度资源占用与关键路径验证

基线固定 `df33bb2`。不做新scheduler、NoC、Shared dataflow、P4-C或普通DSE。
性能只使用原始Qwen捕获s0/l0，真实d2048/h1408/shared5632、B8/B32、TP4/TP16、row/column、B3 frozen placement。
继续采用Broadcast-all与Row-ready128。当前route在MoE子图入口已知；只读取当前step，不使用未来router。

## 源码与资源粒度

保留macro的完整行为和回归控制。fine_fixed保持expert/row顺序及kernel输入/前序expert admission依赖，只改变局部资源占用。
每个32KiB registered-reuse block：1024B DRAM service、独立return latency、HB、有限response/FIFO、MAC block、operand SRAM服务和FIFO消费。
MAC仅占MAC执行context，不锁整个DRAM/HB或write port。Operand read按原有byte账目，在MAC起始窗口co-issue，占同一256B/tick read资源；FIFO仍为500B/tick。
这是eager operand服务政策，**不同于native frontend的均摊端口需求**；它合法且有界，但不能仅凭isolated timing一致宣称整个frontend已校准。
保持原MAC block duration=max(arithmetic、operand read、FIFO consume)，不将可重叠阶段串行相加。
所有权重先实际返回才允许对应MAC；所有激活数据依赖保持。局部partial writes/SiLU/weighted combine继续使用同样端口。
32KiB×8 weight slots、64×1024B returns、262144B FIFO、65536B返回、原SRAM/network credits均不增加。
为显式检查slot数量，8×32B和64×16B descriptor credits保守计入同一private budget；没有额外控制存储池。
HB采用fractional fluid ticks，避免每1024B强行向上取整制造21.85TB/s上限；MAC/operand block仍支付整tick服务。
这不是原生DRAM command或flit精度。

fine_prefetch是单独对照：保持所有expert/row/MAC依赖和任务顺序，允许当前已知地址的weight请求更早进入相同有限in-order队列。
所有kernel共享同一8-slot pool和response/FIFO，不能按kernel新增容量，也不重复计算prefetch字节。
它与fine_fixed的差异属于已知prefetch依赖放松，不能归因于reservation本身。

## 真实场景与矩阵

在s0/l0的B32捕获中：Cold expert12只有token8；Reused expert10有22个token；expert10与34各22个token且TP4同属tiles8–11。
B8投影中没有1-token expert，不能伪造cold B8路由；冷场景由B32的真实assignment提供。
完整子图保留全部活跃expert和Shared，避免孤立摘出expert后消除真实竞争。
主矩阵8个工作负载×macro/fine_fixed/fine_prefetch，24点。
B8/B32 TP16/row三个模式各追加link_only、flight_only、infinite_noc、MAC arithmetic-only，24点，共48点。
不逐点选择TP/placement，不根据oracle选择scheduler。

## 等待与Oracle

Link-only只消除link serialization；Flight-only只消除flight duration。二者均保留SRAM/vector work、payload、有限credit。
Infinite-NoC消除二者；收益不相加。MAC arithmetic-only移除算术时间项，保留operand/FIFO消费和真实work。
记录node dependency-ready、resource/operand-admission、credit/private-credit、queue等待；每个node的等待分区须闭合。
汇总busy windows不是critical path，也不可跨tile相加后称作延迟损失。
每个性能变化保留完整parent chain、expert finish、microblock/packet ledger、占用与资源释放事件。

## 原生与数值验收

Native/Fluid详细frontend选定来自真实cold/reused专家的合法tensor submatrices：M512、K1024/2048，batch1/22，row/column。
这些是实际d2048和Gate/Up维度内的子矩阵；不作为主性能或生产工作负载，也不将其16-way partition结果替代全MoE TP4/16排序。
采用原有Ramulator pin、refresh、actual physical addresses、32B flits、共享SRAM/FIFO与MAC frontend，保留原生command/transaction审计。
Native与Fluid共享详细frontend，最多验证memory abstraction；其结果不能独立认证Python fine executor。
另用Python Graph重建同一详细tensor task/input/reduction合同，与两个backend逐case比较，预设absolute10%、relative5个百分点；失败公开保留，不通过调参/平均抹去。
完整MoE的TP4/TP16及row/column排序比较是粒度敏感性结果；若没有同合同独立详细MoE frontend，G4不得写成独立精度通过。

G1 work/token/weight/semantic一致；G2 ports、credits、lease有限；G3 component native交叉验证；G4报告误差和排序资格；G5 causal/等待闭合；G6超用、早消费、非法co-issue负控制。
小张量数值沿用真实routing/probabilities，验证分片规则；不是完整checkpoint计算。
允许结论为qualification失败、需继续修正模型；不因更快就批准新硬件。
